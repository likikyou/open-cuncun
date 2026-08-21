"""
AI 引擎模块
纯 AI 调用层，对上暴露统一 API
"""

import re
import time
from collections.abc import Iterable
from uuid import uuid4

from .application.ai_chat_runner import (
    ChatToolRunState,
    iter_stream_tool_chat,
    run_sync_tool_chat,
)
from .application.ai_summary_extractor import AISummaryDependencies, summarize_reply
from .application.context_assembler import build_messages
from .infrastructure.ai import (
    AIFallbackExhaustedError,
    FallbackLLMGateway,
    get_provider_configs,
    resolve_active_provider,
)
from .infrastructure.ai.provider_health import record_provider_failure, record_provider_success
from .logger import logger
from .observability import record_ai_run
from .ports import LLMGateway
from .tools_registry import AVAILABLE_TOOLS, execute_tool

_llm_gateway: LLMGateway = FallbackLLMGateway()


def _new_run_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


def _strip_thinking_tags(text: str) -> str:
    """过滤模型输出中的 <think>...</think> 思考过程标签及其内容。"""
    if not text:
        return text
    # 移除 <think>...</think> 及其包含的所有内容（包括跨行）
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    return text.strip()


def _safe_prefix_len_for_partial_tag(text: str, tag: str) -> int:
    max_suffix = min(len(tag) - 1, len(text))
    for suffix_len in range(max_suffix, 0, -1):
        if tag.startswith(text[-suffix_len:]):
            return len(text) - suffix_len
    return len(text)


class _ThinkingTagStreamFilter:
    """Remove <think>...</think> blocks from streamed model output."""

    _start_tag = "<think>"
    _end_tag = "</think>"

    def __init__(self) -> None:
        self._buffer = ""
        self._in_thinking_block = False

    def feed(self, chunk: str) -> str:
        self._buffer += chunk or ""
        output: list[str] = []

        while self._buffer:
            if self._in_thinking_block:
                end_index = self._buffer.find(self._end_tag)
                if end_index < 0:
                    safe_len = _safe_prefix_len_for_partial_tag(self._buffer, self._end_tag)
                    self._buffer = self._buffer[safe_len:]
                    return "".join(output)
                self._buffer = self._buffer[end_index + len(self._end_tag) :]
                self._in_thinking_block = False
                continue

            start_index = self._buffer.find(self._start_tag)
            if start_index < 0:
                safe_len = _safe_prefix_len_for_partial_tag(self._buffer, self._start_tag)
                output.append(self._buffer[:safe_len])
                self._buffer = self._buffer[safe_len:]
                return "".join(output)

            output.append(self._buffer[:start_index])
            self._buffer = self._buffer[start_index + len(self._start_tag) :]
            self._in_thinking_block = True

        return "".join(output)

    def flush(self) -> str:
        if self._in_thinking_block:
            self._buffer = ""
            self._in_thinking_block = False
            return ""
        output = self._buffer
        self._buffer = ""
        return output


def _iter_without_thinking_tags(chunks: Iterable[str]) -> Iterable[str]:
    thinking_filter = _ThinkingTagStreamFilter()
    for chunk in chunks:
        filtered = thinking_filter.feed(chunk)
        if filtered:
            yield filtered
    tail = thinking_filter.flush()
    if tail:
        yield tail


def is_ready() -> dict:
    from .retrieval import audio_collection

    return {
        "ai_engine": any(cfg.get("client") is not None for cfg in get_provider_configs().values()),
        "voice_db": audio_collection is not None,
    }


def call_ai_summarize(user_text: str, assistant_reply: str) -> dict[str, str]:
    return summarize_reply(
        user_text,
        assistant_reply,
        AISummaryDependencies(
            resolve_provider=resolve_active_provider,
            llm_gateway=_llm_gateway,
            record_ai_run=record_ai_run,
            logger=logger,
            new_run_id=_new_run_id,
            fallback_exhausted_error=AIFallbackExhaustedError,
        ),
    )


def _record_chat_tool_batch(
    *,
    provider_name: str,
    model: str,
    user_id: str,
    stream: bool,
    run_id: str,
    turn: int,
    current_tool_names: list[str],
    tool_call_count: int,
) -> None:
    record_ai_run(
        "tool_batch_completed",
        operation="chat",
        provider=provider_name,
        model=model,
        user_id=user_id,
        stream=stream,
        run_id=run_id,
        turn=turn,
        tool_call_count=tool_call_count,
        tool_names=current_tool_names,
    )
    prefix = "🛠️ [Stream]" if stream else "🛠️"
    logger.info(f"{prefix} 第 {turn} 轮工具调用完成，继续推理...")


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
    state = ChatToolRunState()
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
        user_text_chars=len(user_text or ""),
    )

    try:
        start_time = time.time()
        result = run_sync_tool_chat(
            client=client,
            model=model,
            provider_name=provider_name,
            messages=messages,
            llm_gateway=_llm_gateway,
            tools_enabled=tools_enabled,
            available_tools=AVAILABLE_TOOLS,
            execute_tool=execute_tool,
            state=state,
            max_turns=5,
            on_tool_batch=lambda turn, names, count: _record_chat_tool_batch(
                provider_name=provider_name,
                model=model,
                user_id=user_id,
                stream=False,
                run_id=run_id,
                turn=turn,
                current_tool_names=names,
                tool_call_count=count,
            ),
            content_filter=_strip_thinking_tags,
        )
        state = result.state

        duration = float(time.time() - start_time)
        response_text = _strip_thinking_tags(result.content)
        record_ai_run(
            "request_completed",
            operation="chat",
            provider=provider_name,
            model=model,
            user_id=user_id,
            stream=False,
            run_id=run_id,
            duration_ms=round(duration * 1000, 1),
            turns=state.turns,
            tool_call_count=state.tool_call_count,
            tool_names=state.unique_tool_names,
            finish_reason=result.finish_reason,
            response_chars=len(response_text),
        )
        record_provider_success(provider_name, operation="chat", stream=False)
        logger.info(
            f"⏱️ [性能] AI 响应完成 [{provider_name}]: {duration * 1000:.0f}ms, 轮次={state.turns}"
        )
        return response_text

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
            tool_call_count=state.tool_call_count,
            tool_names=state.unique_tool_names,
        )
        logger.error(f"AI 错误 [{provider_name}]: {e}", exc_info=True)
        # P3 修复：降级时不传 tools，避免 fallback 引擎返回 tool_calls 而非文本
        try:
            result = _llm_gateway.call_with_fallback(
                client,
                model,
                provider_name,
                messages,
                stream=False,
                extra_kwargs=None,
                skip_primary=True,
                primary_error=e,
            )
            fallback_text = _strip_thinking_tags(result or "")
            if fallback_text:
                record_ai_run(
                    "fallback_completed",
                    operation="chat",
                    provider=provider_name,
                    model=model,
                    user_id=user_id,
                    stream=False,
                    run_id=run_id,
                    fallback_attempted=True,
                    response_chars=len(fallback_text),
                    tool_call_count=state.tool_call_count,
                    tool_names=state.unique_tool_names,
                )
                return fallback_text
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
                tool_call_count=state.tool_call_count,
                tool_names=state.unique_tool_names,
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
    messages = build_messages(
        system_prompt, user_text, history, reply_mode=reply_mode, user_id=user_id
    )
    build_ms = (time.perf_counter() - t0) * 1000
    start_time = time.time()
    tools_enabled = provider_name in ["Cerebras", "DeepSeek"]
    state = ChatToolRunState()
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
        user_text_chars=len(user_text or ""),
    )

    try:
        thinking_filter = _ThinkingTagStreamFilter()

        def record_first_chunk(first_chunk_ms: float) -> None:
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

        yield from iter_stream_tool_chat(
            client=client,
            model=model,
            provider_name=provider_name,
            messages=messages,
            llm_gateway=_llm_gateway,
            tools_enabled=tools_enabled,
            available_tools=AVAILABLE_TOOLS,
            execute_tool=execute_tool,
            state=state,
            start_time=start_time,
            max_turns=5,
            on_first_chunk=record_first_chunk,
            on_tool_batch=lambda turn, names, count: _record_chat_tool_batch(
                provider_name=provider_name,
                model=model,
                user_id=user_id,
                stream=True,
                run_id=run_id,
                turn=turn,
                current_tool_names=names,
                tool_call_count=count,
            ),
            content_filter=thinking_filter.feed,
        )

        tail = thinking_filter.flush()
        if tail:
            state.output_chars += len(tail)
            if tail.strip():
                state.has_visible_content = True
            if state.first_chunk_ms is None:
                state.first_chunk_ms = round((time.time() - start_time) * 1000, 1)
                record_first_chunk(state.first_chunk_ms)
            yield tail

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
            first_chunk_ms=state.first_chunk_ms,
            turns=state.turns,
            tool_call_count=state.tool_call_count,
            tool_names=state.unique_tool_names,
            response_chars=state.output_chars,
        )
        record_provider_success(provider_name, operation="chat", stream=True)
        logger.info(
            f"⏱️ [性能] AI 流式响应完成 [{provider_name}]: 构建上下文 {(build_ms):.0f}ms + AI生成 {duration * 1000:.0f}ms, 轮次={state.turns}"
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
            first_chunk_ms=state.first_chunk_ms,
            tool_call_count=state.tool_call_count,
            tool_names=state.unique_tool_names,
            response_chars=state.output_chars,
        )
        logger.error(f"AI 流式错误 [{provider_name}]: {e}", exc_info=True)
        # P3 修复：降级时不传 tools 参数，因为 fallback 引擎（如 Groq/Llama）
        # 收到 tools 后可能以 tool_calls 返回内容，而非 delta.content，
        # 导致 generate() 中 yield 0 个 chunk，卡片显示空白。
        try:
            result = _llm_gateway.call_with_fallback(
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
                fallback_chars = 0
                fallback_has_visible_content = False
                for chunk in _iter_without_thinking_tags(result):
                    fallback_chars += len(chunk)
                    if chunk.strip():
                        fallback_has_visible_content = True
                    yield chunk
                if fallback_has_visible_content:
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
                        first_chunk_ms=state.first_chunk_ms,
                        response_chars=fallback_chars,
                        tool_call_count=state.tool_call_count,
                        tool_names=state.unique_tool_names,
                    )
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
                first_chunk_ms=state.first_chunk_ms,
                tool_call_count=state.tool_call_count,
                tool_names=state.unique_tool_names,
            )
            logger.warning(
                "⚠️ AI 流式降级链路耗尽，返回边界层兜底文案",
                extra={"provider": provider_name, "attempts": exc.attempts},
            )
        yield "我有点累了，稍等一下。"
