"""
AI 引擎模块
纯 AI 调用层，对上暴露统一 API
"""

import re
import time
from functools import lru_cache
from typing import Dict
from uuid import uuid4

from .application.context_assembler import build_messages
from .infrastructure.ai import (
    AIFallbackExhaustedError,
    build_kwargs,
    call_with_fallback,
    get_provider_configs,
    resolve_active_provider,
)
from .infrastructure.ai.provider_health import record_provider_failure, record_provider_success
from .logger import logger
from .observability import record_ai_run
from .tools_registry import AVAILABLE_TOOLS, execute_tool

SUMMARIZE_CACHE_SIZE = 200


def _preview_text(text: str, limit: int = 80) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def _new_run_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


def _strip_thinking_tags(text: str) -> str:
    """过滤模型输出中的 <think>...</think> 思考过程标签及其内容。"""
    if not text:
        return text
    # 移除 <think>...</think> 及其包含的所有内容（包括跨行）
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


def _empty_summary(intent: str = "") -> Dict[str, str]:
    """返回统一结构的摘要结果，避免调用方处理混合返回类型。"""
    return {
        "intent": intent,
        "emotion": "平静",
        "theme": "日常",
    }


def is_ready() -> dict:
    from .retrieval import audio_collection

    return {
        "ai_engine": any(cfg.get("client") is not None for cfg in get_provider_configs().values()),
        "voice_db": audio_collection is not None,
    }


@lru_cache(maxsize=SUMMARIZE_CACHE_SIZE)
def _cached_summarize(user_text: str, assistant_reply: str) -> Dict[str, str]:
    return _do_ai_summarize(user_text, assistant_reply)


def _do_ai_summarize(user_text: str, assistant_reply: str) -> Dict[str, str]:
    run_id = _new_run_id("summary")
    resolved = resolve_active_provider()
    client = resolved.get("client")
    model = resolved.get("model")
    provider_name = resolved.get("name")
    if not client:
        record_ai_run(
            "provider_unavailable",
            operation="summarize",
            provider=provider_name,
            model=model,
            run_id=run_id,
        )
        return _empty_summary()

    sys_prompt = (
        "你是一个对话意图与情绪提取器。现在有一名傲娇、嘴硬心软的女性助手回复了用户一段话。\n"
        "请你预测这段回复将要匹配哪段语音，提炼出助手回复的核心口语意图，并判断她的情感(emotion)和主题(theme)。\n"
        "要求：\n"
        "1. intent (意图): 必须是纯对话，不超过20字，越口语化越好。\n"
        "2. emotion (情感): 从这几个词中选一个: 平静、开心、撒娇、傲娇、嫌弃、生气、难过、心疼、鼓励、打趣、疲倦、其他。\n"
        "3. theme (主题): 从这几个词中选一个: 问候、催促、工作/搞钱、吐槽、深情表白、讲故事、调侃、日常、情绪宣泄、教导。\n"
        "请必须严格输出合法的 JSON 格式字典，不要包含其他字符，格式如下：\n"
        '{"intent": "提取的核心短句", "emotion": "傲娇", "theme": "日常"}'
    )
    user_prompt = f"【用户输入】\n{user_text}\n\n【助手的长回复】\n{assistant_reply}"

    try:
        start_time = time.time()
        extra_kwargs = {"temperature": 0.5, "max_tokens": 50}
        if provider_name != "Cerebras":
            extra_kwargs["presence_penalty"] = 0.0
            extra_kwargs["frequency_penalty"] = 0.0

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ]
        record_ai_run(
            "request_started",
            operation="summarize",
            provider=provider_name,
            model=model,
            run_id=run_id,
            message_count=len(messages),
            user_text_preview=_preview_text(user_text),
            assistant_reply_preview=_preview_text(assistant_reply),
        )
        try:
            content = call_with_fallback(
                client,
                model,
                provider_name,
                messages,
                extra_kwargs=extra_kwargs,
                operation="summarize",
            )
        except AIFallbackExhaustedError as exc:
            record_ai_run(
                "fallback_exhausted",
                operation="summarize",
                provider=provider_name,
                model=model,
                run_id=run_id,
                fallback_attempted=True,
                error_type=exc.__class__.__name__,
                attempts=exc.attempts,
            )
            logger.warning(
                "⚠️ 意图提炼 AI 降级链路耗尽，改用本地摘要",
                extra={"provider": provider_name, "attempts": exc.attempts},
            )
            content = None
        if content:
            duration_ms = (time.time() - start_time) * 1000
            record_ai_run(
                "request_completed",
                operation="summarize",
                provider=provider_name,
                model=model,
                run_id=run_id,
                duration_ms=round(duration_ms, 1),
                response_chars=len(content),
            )
            logger.info(f"⏱️ [性能] AI提炼多维意图 [{provider_name}]: {duration_ms:.0f}ms")
            # 清理 markdown 可能的包裹
            import json

            clean_content = content.replace("```json", "").replace("```", "").strip()
            try:
                parsed = json.loads(clean_content)
                return {
                    "intent": str(parsed.get("intent", "")).strip(),
                    "emotion": str(parsed.get("emotion", "平静")).strip() or "平静",
                    "theme": str(parsed.get("theme", "日常")).strip() or "日常",
                }
            except Exception as e:
                record_ai_run(
                    "response_parse_failed",
                    operation="summarize",
                    provider=provider_name,
                    model=model,
                    run_id=run_id,
                    error_type=e.__class__.__name__,
                    content_preview=_preview_text(content),
                )
                logger.warning(f"JSON 解析失败: {e}, 原始返回: {content}")
                return _empty_summary(clean_content[:20].strip())

        if assistant_reply and isinstance(assistant_reply, str):
            record_ai_run(
                "local_fallback",
                operation="summarize",
                provider=provider_name,
                model=model,
                run_id=run_id,
                fallback_attempted=True,
                reason="empty_content",
            )
            clean_text = re.sub(r"\[.*?\]|（.*?）|\(.*?\)|【.*?】", "", assistant_reply)
            return _empty_summary(clean_text[:20].strip())
        return _empty_summary()
    except Exception as e:
        record_ai_run(
            "request_failed",
            operation="summarize",
            provider=provider_name,
            model=model,
            run_id=run_id,
            error_type=e.__class__.__name__,
        )
        logger.error(f"提取多维语音意图失败 [{provider_name}]: {e}", exc_info=True)
        if assistant_reply and isinstance(assistant_reply, str):
            clean_text = re.sub(r"\[.*?\]|（.*?）|\(.*?\)|【.*?】", "", assistant_reply)
            return _empty_summary(clean_text[:20].strip())
        return _empty_summary()


def call_ai_summarize(user_text: str, assistant_reply: str) -> Dict[str, str]:
    if not user_text or not assistant_reply:
        return _empty_summary()
    return _cached_summarize(user_text, assistant_reply)


def call_ai(
    system_prompt: str,
    user_text: str,
    history: list = None,
    reply_mode: str = "normal",
    user_id: str = "",
) -> str:
    run_id = _new_run_id("chat")
    resolved = resolve_active_provider(user_id)
    client = resolved.get("client")
    model = resolved.get("model")
    provider_name = resolved.get("name")
    if not client:
        record_ai_run(
            "provider_unavailable",
            operation="chat",
            provider=provider_name,
            model=model,
            user_id=user_id,
            run_id=run_id,
            stream=False,
        )
        return "AI 未连接"

    messages = build_messages(
        system_prompt, user_text, history, reply_mode=reply_mode, user_id=user_id
    )
    tools_enabled = provider_name in ["Cerebras", "DeepSeek"]
    tool_names: list[str] = []
    tool_call_count = 0
    record_ai_run(
        "request_started",
        operation="chat",
        provider=provider_name,
        model=model,
        user_id=user_id,
        stream=False,
        run_id=run_id,
        reply_mode=reply_mode,
        history_items=len(history or []),
        message_count=len(messages),
        tools_enabled=tools_enabled,
        user_text_preview=_preview_text(user_text),
    )

    try:
        start_time = time.time()
        max_turns = 5
        turn = 0

        while turn < max_turns:
            kwargs = build_kwargs(model, provider_name, messages)
            if tools_enabled:
                kwargs["tools"] = AVAILABLE_TOOLS

            res = client.chat.completions.create(**kwargs)
            message = res.choices[0].message

            if res.choices[0].finish_reason != "tool_calls" or not message.tool_calls:
                # 无需调用工具，直接返回内容
                duration = float(time.time() - start_time)
                response_text = _strip_thinking_tags(message.content or "")
                record_ai_run(
                    "request_completed",
                    operation="chat",
                    provider=provider_name,
                    model=model,
                    user_id=user_id,
                    stream=False,
                    run_id=run_id,
                    duration_ms=round(duration * 1000, 1),
                    turns=turn + 1,
                    tool_call_count=tool_call_count,
                    tool_names=sorted(set(tool_names)),
                    finish_reason=res.choices[0].finish_reason,
                    response_chars=len(response_text),
                )
                record_provider_success(provider_name, operation="chat", stream=False)
                logger.info(
                    f"⏱️ [性能] AI 响应完成 [{provider_name}]: {duration * 1000:.0f}ms, 轮次={turn + 1}"
                )
                return response_text

            # 处理工具调用
            tool_calls = message.tool_calls
            messages.append(message)
            current_tool_names = []

            for tool_call in tool_calls:
                func_name = tool_call.function.name
                func_args = tool_call.function.arguments
                current_tool_names.append(func_name)
                tool_names.append(func_name)
                tool_call_count += 1
                func_result = execute_tool(func_name, func_args)
                messages.append(
                    {"role": "tool", "tool_call_id": tool_call.id, "content": func_result}
                )
            record_ai_run(
                "tool_batch_completed",
                operation="chat",
                provider=provider_name,
                model=model,
                user_id=user_id,
                stream=False,
                run_id=run_id,
                turn=turn + 1,
                tool_call_count=tool_call_count,
                tool_names=current_tool_names,
            )

            turn += 1
            logger.info(f"🛠️ 第 {turn} 轮工具调用完成，继续推理...")

        # 超过最大轮数
        record_ai_run(
            "max_turns_reached",
            operation="chat",
            provider=provider_name,
            model=model,
            user_id=user_id,
            stream=False,
            run_id=run_id,
            turns=max_turns,
            tool_call_count=tool_call_count,
            tool_names=sorted(set(tool_names)),
        )
        record_provider_success(provider_name, operation="chat", stream=False)
        logger.warning(f"⚠️ 达到最大工具调用次数 ({max_turns})，强制终止。")
        return message.content

    except Exception as e:
        record_provider_failure(
            provider_name,
            error_type=e.__class__.__name__,
            operation="chat",
            stream=False,
        )
        record_ai_run(
            "request_failed",
            operation="chat",
            provider=provider_name,
            model=model,
            user_id=user_id,
            stream=False,
            run_id=run_id,
            error_type=e.__class__.__name__,
            tool_call_count=tool_call_count,
            tool_names=sorted(set(tool_names)),
        )
        logger.error(f"AI 错误 [{provider_name}]: {e}", exc_info=True)
        # P3 修复：降级时不传 tools，避免 fallback 引擎返回 tool_calls 而非文本
        try:
            result = call_with_fallback(
                client,
                model,
                provider_name,
                messages,
                stream=False,
                extra_kwargs=None,
                skip_primary=True,
                primary_error=e,
            )
            if result:
                record_ai_run(
                    "fallback_completed",
                    operation="chat",
                    provider=provider_name,
                    model=model,
                    user_id=user_id,
                    stream=False,
                    run_id=run_id,
                    fallback_attempted=True,
                    response_chars=len(result),
                    tool_call_count=tool_call_count,
                    tool_names=sorted(set(tool_names)),
                )
                return result
        except AIFallbackExhaustedError as exc:
            record_ai_run(
                "fallback_exhausted",
                operation="chat",
                provider=provider_name,
                model=model,
                user_id=user_id,
                stream=False,
                run_id=run_id,
                fallback_attempted=True,
                error_type=exc.__class__.__name__,
                attempts=exc.attempts,
                tool_call_count=tool_call_count,
                tool_names=sorted(set(tool_names)),
            )
            logger.warning(
                "⚠️ AI 降级链路耗尽，返回边界层兜底文案",
                extra={"provider": provider_name, "attempts": exc.attempts},
            )
        return "我有点累了，稍等一下。"


def call_ai_stream(
    system_prompt: str,
    user_text: str,
    history: list = None,
    reply_mode: str = "normal",
    user_id: str = "",
    summary_container: dict = None,
):
    run_id = _new_run_id("stream")
    resolved = resolve_active_provider(user_id)
    client = resolved.get("client")
    model = resolved.get("model")
    provider_name = resolved.get("name")
    if not client:
        record_ai_run(
            "provider_unavailable",
            operation="chat",
            provider=provider_name,
            model=model,
            user_id=user_id,
            stream=True,
            run_id=run_id,
        )
        yield "AI 未连接"
        return

    t0 = time.perf_counter()
    thinking_buffer = ""
    in_thinking_block = False
    messages = build_messages(
        system_prompt, user_text, history, reply_mode=reply_mode, user_id=user_id
    )
    build_ms = (time.perf_counter() - t0) * 1000
    start_time = time.time()
    tools_enabled = provider_name in ["Cerebras", "DeepSeek"]
    tool_names: list[str] = []
    tool_call_count = 0
    output_chars = 0
    first_chunk_ms: float | None = None
    record_ai_run(
        "request_started",
        operation="chat",
        provider=provider_name,
        model=model,
        user_id=user_id,
        stream=True,
        run_id=run_id,
        reply_mode=reply_mode,
        history_items=len(history or []),
        message_count=len(messages),
        tools_enabled=tools_enabled,
        build_ms=round(build_ms, 1),
        user_text_preview=_preview_text(user_text),
    )

    try:
        max_turns = 5
        turn = 0

        while turn < max_turns:
            kwargs = build_kwargs(model, provider_name, messages)
            kwargs["stream"] = True
            if tools_enabled:
                kwargs["tools"] = AVAILABLE_TOOLS

            stream = client.chat.completions.create(**kwargs)
            tool_calls_buffer = {}

            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                if delta.content:
                    content = delta.content
                    # 状态机处理流式中的思考标签
                    if "<think>" in content:
                        in_thinking_block = True
                        parts = content.split("<think>", 1)
                        if parts[0]:
                            output_chars += len(parts[0])
                            yield parts[0]
                        thinking_buffer += parts[1]
                    elif in_thinking_block:
                        if "</think>" in content:
                            parts = content.split("</think>", 1)
                            thinking_buffer += parts[0]
                            in_thinking_block = False
                            if parts[1]:
                                output_chars += len(parts[1])
                                yield parts[1]
                        else:
                            thinking_buffer += content
                    else:
                        output_chars += len(content)
                        if first_chunk_ms is None:
                            first_chunk_ms = round((time.time() - start_time) * 1000, 1)
                            record_ai_run(
                                "first_chunk",
                                operation="chat",
                                provider=provider_name,
                                model=model,
                                user_id=user_id,
                                stream=True,
                                run_id=run_id,
                                first_chunk_ms=first_chunk_ms,
                            )
                        yield content

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_buffer:
                            tool_calls_buffer[idx] = {
                                "id": tc.id,
                                "name": tc.function.name,
                                "arguments": "",
                            }
                        if tc.function.arguments:
                            tool_calls_buffer[idx]["arguments"] += tc.function.arguments

            if not tool_calls_buffer:
                # 本轮没有工具调用，结束整个推理流程
                break

            # 处理本轮收集到的所有工具调用
            assistant_msg = {"role": "assistant", "tool_calls": []}
            for idx, tc in tool_calls_buffer.items():
                assistant_msg["tool_calls"].append(
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": tc["arguments"]},
                    }
                )
            messages.append(assistant_msg)

            current_tool_names = []
            for idx, tc in tool_calls_buffer.items():
                current_tool_names.append(tc["name"])
                tool_names.append(tc["name"])
                tool_call_count += 1
                res_str = execute_tool(tc["name"], tc["arguments"])
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": res_str})
            record_ai_run(
                "tool_batch_completed",
                operation="chat",
                provider=provider_name,
                model=model,
                user_id=user_id,
                stream=True,
                run_id=run_id,
                turn=turn + 1,
                tool_call_count=tool_call_count,
                tool_names=current_tool_names,
            )

            turn += 1
            logger.info(f"🛠️ [Stream] 第 {turn} 轮工具调用完成，继续流式生成...")

        duration = float(time.time() - start_time)
        record_ai_run(
            "request_completed",
            operation="chat",
            provider=provider_name,
            model=model,
            user_id=user_id,
            stream=True,
            run_id=run_id,
            build_ms=round(build_ms, 1),
            duration_ms=round(duration * 1000, 1),
            first_chunk_ms=first_chunk_ms,
            turns=turn + 1,
            tool_call_count=tool_call_count,
            tool_names=sorted(set(tool_names)),
            response_chars=output_chars,
        )
        record_provider_success(provider_name, operation="chat", stream=True)
        logger.info(
            f"⏱️ [性能] AI 流式响应完成 [{provider_name}]: 构建上下文 {(build_ms):.0f}ms + AI生成 {duration * 1000:.0f}ms, 轮次={turn + 1}"
        )

    except Exception as e:
        record_provider_failure(
            provider_name,
            error_type=e.__class__.__name__,
            operation="chat",
            stream=True,
        )
        record_ai_run(
            "request_failed",
            operation="chat",
            provider=provider_name,
            model=model,
            user_id=user_id,
            stream=True,
            run_id=run_id,
            error_type=e.__class__.__name__,
            build_ms=round(build_ms, 1),
            first_chunk_ms=first_chunk_ms,
            tool_call_count=tool_call_count,
            tool_names=sorted(set(tool_names)),
            response_chars=output_chars,
        )
        logger.error(f"AI 流式错误 [{provider_name}]: {e}", exc_info=True)
        # P3 修复：降级时不传 tools 参数，因为 fallback 引擎（如 Groq/Llama）
        # 收到 tools 后可能以 tool_calls 返回内容，而非 delta.content，
        # 导致 generate() 中 yield 0 个 chunk，卡片显示空白。
        try:
            result = call_with_fallback(
                client,
                model,
                provider_name,
                messages,
                stream=True,
                extra_kwargs=None,
                skip_primary=True,
                primary_error=e,
            )
            if result:
                record_ai_run(
                    "fallback_completed",
                    operation="chat",
                    provider=provider_name,
                    model=model,
                    user_id=user_id,
                    stream=True,
                    run_id=run_id,
                    fallback_attempted=True,
                    build_ms=round(build_ms, 1),
                    first_chunk_ms=first_chunk_ms,
                    tool_call_count=tool_call_count,
                    tool_names=sorted(set(tool_names)),
                )
                yield from result
                return
        except AIFallbackExhaustedError as exc:
            record_ai_run(
                "fallback_exhausted",
                operation="chat",
                provider=provider_name,
                model=model,
                user_id=user_id,
                stream=True,
                run_id=run_id,
                fallback_attempted=True,
                error_type=exc.__class__.__name__,
                attempts=exc.attempts,
                build_ms=round(build_ms, 1),
                first_chunk_ms=first_chunk_ms,
                tool_call_count=tool_call_count,
                tool_names=sorted(set(tool_names)),
            )
            logger.warning(
                "⚠️ AI 流式降级链路耗尽，返回边界层兜底文案",
                extra={"provider": provider_name, "attempts": exc.attempts},
            )
        yield "我有点累了，稍等一下。"
