"""Extract compact voice matching metadata from an AI reply."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from ..ports import LLMGateway

VOICE_EMOTIONS = (
    "平静",
    "开心",
    "撒娇",
    "傲娇",
    "嫌弃",
    "生气",
    "难过",
    "心疼",
    "鼓励",
    "打趣",
    "疲倦",
    "其他",
)
VOICE_THEMES = (
    "问候",
    "催促",
    "工作/搞钱",
    "吐槽",
    "深情表白",
    "讲故事",
    "调侃",
    "日常",
    "情绪宣泄",
    "教导",
)
DEFAULT_VOICE_EMOTION = "平静"
DEFAULT_VOICE_THEME = "日常"

SUMMARY_SYSTEM_PROMPT = (
    "你是一个对话意图与情绪提取器。现在有一个 AI 角色回复了用户一段话。\n"
    "请提炼该回复的核心口语意图，并判断角色表达的情感(emotion)和主题(theme)。\n"
    "要求：\n"
    "1. intent (意图): 必须是纯对话，不超过20字，越口语化越好。\n"
    f"2. emotion (情感): 从这几个词中选一个: {'、'.join(VOICE_EMOTIONS)}。\n"
    f"3. theme (主题): 从这几个词中选一个: {'、'.join(VOICE_THEMES)}。\n"
    "请严格输出合法的 JSON 字典，不要包含其他字符，格式如下：\n"
    '{"intent": "提取的核心短句", "emotion": "平静", "theme": "日常"}'
)
_LOCAL_SUMMARY_CLEANUP_RE = re.compile(r"\[.*?\]|（.*?）|\(.*?\)|【.*?】")

RecordAiRun = Callable[..., None]
ResolveProvider = Callable[[], dict[str, Any]]
NewRunId = Callable[[str], str]


@dataclass(frozen=True)
class AISummaryDependencies:
    resolve_provider: ResolveProvider
    llm_gateway: LLMGateway
    record_ai_run: RecordAiRun
    logger: Any
    new_run_id: NewRunId
    fallback_exhausted_error: type[Exception]


def empty_summary(intent: str = "") -> dict[str, str]:
    """Return a stable summary shape for callers that expect a dict."""
    return {
        "intent": intent,
        "emotion": DEFAULT_VOICE_EMOTION,
        "theme": DEFAULT_VOICE_THEME,
    }


def summarize_reply(
    user_text: str,
    assistant_reply: str,
    deps: AISummaryDependencies,
) -> dict[str, str]:
    if not user_text or not assistant_reply:
        return empty_summary()

    run_id = deps.new_run_id("summary")
    resolved = deps.resolve_provider()
    client = resolved.get("client")
    model = resolved.get("model")
    provider_name = resolved.get("name")
    if not client:
        deps.record_ai_run(
            "provider_unavailable",
            operation="summarize",
            provider=provider_name,
            model=model,
            run_id=run_id,
        )
        return empty_summary()

    try:
        start_time = time.time()
        messages = build_summary_messages(user_text, assistant_reply)
        deps.record_ai_run(
            "request_started",
            operation="summarize",
            provider=provider_name,
            model=model,
            run_id=run_id,
            message_count=len(messages),
            user_text_chars=len(user_text),
            assistant_reply_chars=len(assistant_reply),
        )
        content = _call_summary_model(
            client=client,
            model=model,
            provider_name=provider_name,
            messages=messages,
            deps=deps,
            run_id=run_id,
        )
        if content:
            return _parse_model_summary(
                content=str(content),
                deps=deps,
                provider_name=provider_name,
                model=model,
                run_id=run_id,
                start_time=start_time,
            )
        return _record_and_build_local_summary(
            assistant_reply,
            deps=deps,
            provider_name=provider_name,
            model=model,
            run_id=run_id,
            reason="empty_content",
        )
    except Exception as exc:
        deps.record_ai_run(
            "request_failed",
            operation="summarize",
            provider=provider_name,
            model=model,
            run_id=run_id,
            error_type=exc.__class__.__name__,
        )
        deps.logger.error(f"提取多维语音意图失败 [{provider_name}]: {exc}", exc_info=True)
        return build_local_summary(assistant_reply)


def build_summary_messages(user_text: str, assistant_reply: str) -> list[dict[str, str]]:
    user_prompt = f"【用户输入】\n{user_text}\n\n【角色的长回复】\n{assistant_reply}"
    return [
        {"role": "system", "content": SUMMARY_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]


def build_summary_extra_kwargs(provider_name: str | None) -> dict[str, float | int]:
    extra_kwargs: dict[str, float | int] = {"temperature": 0.5, "max_tokens": 50}
    if provider_name != "Cerebras":
        extra_kwargs["presence_penalty"] = 0.0
        extra_kwargs["frequency_penalty"] = 0.0
    return extra_kwargs


def parse_summary_content(content: str) -> dict[str, str]:
    clean_content = content.replace("```json", "").replace("```", "").strip()
    parsed = json.loads(clean_content)
    emotion = str(parsed.get("emotion", DEFAULT_VOICE_EMOTION)).strip()
    theme = str(parsed.get("theme", DEFAULT_VOICE_THEME)).strip()
    return {
        "intent": str(parsed.get("intent", "")).strip(),
        "emotion": emotion if emotion in VOICE_EMOTIONS else DEFAULT_VOICE_EMOTION,
        "theme": theme if theme in VOICE_THEMES else DEFAULT_VOICE_THEME,
    }


def build_local_summary(assistant_reply: str) -> dict[str, str]:
    if assistant_reply and isinstance(assistant_reply, str):
        clean_text = _LOCAL_SUMMARY_CLEANUP_RE.sub("", assistant_reply)
        return empty_summary(clean_text[:20].strip())
    return empty_summary()


def _call_summary_model(
    *,
    client: Any,
    model: str,
    provider_name: str,
    messages: list[dict[str, str]],
    deps: AISummaryDependencies,
    run_id: str,
) -> Any:
    try:
        return deps.llm_gateway.call_with_fallback(
            client,
            model,
            provider_name,
            messages,
            extra_kwargs=build_summary_extra_kwargs(provider_name),
            operation="summarize",
        )
    except deps.fallback_exhausted_error as exc:
        deps.record_ai_run(
            "fallback_exhausted",
            operation="summarize",
            provider=provider_name,
            model=model,
            run_id=run_id,
            fallback_attempted=True,
            error_type=exc.__class__.__name__,
            attempts=getattr(exc, "attempts", []),
        )
        deps.logger.warning(
            "⚠️ 意图提炼 AI 降级链路耗尽，改用本地摘要",
            extra={"provider": provider_name, "attempts": getattr(exc, "attempts", [])},
        )
        return None


def _parse_model_summary(
    *,
    content: str,
    deps: AISummaryDependencies,
    provider_name: str,
    model: str,
    run_id: str,
    start_time: float,
) -> dict[str, str]:
    duration_ms = (time.time() - start_time) * 1000
    deps.record_ai_run(
        "request_completed",
        operation="summarize",
        provider=provider_name,
        model=model,
        run_id=run_id,
        duration_ms=round(duration_ms, 1),
        response_chars=len(content),
    )
    deps.logger.info(f"⏱️ [性能] AI提炼多维意图 [{provider_name}]: {duration_ms:.0f}ms")
    try:
        return parse_summary_content(content)
    except Exception as exc:
        clean_content = content.replace("```json", "").replace("```", "").strip()
        deps.record_ai_run(
            "response_parse_failed",
            operation="summarize",
            provider=provider_name,
            model=model,
            run_id=run_id,
            error_type=exc.__class__.__name__,
            content_chars=len(content),
        )
        deps.logger.warning(f"JSON 解析失败: {exc.__class__.__name__}")
        return empty_summary(clean_content[:20].strip())


def _record_and_build_local_summary(
    assistant_reply: str,
    *,
    deps: AISummaryDependencies,
    provider_name: str,
    model: str,
    run_id: str,
    reason: str,
) -> dict[str, str]:
    deps.record_ai_run(
        "local_fallback",
        operation="summarize",
        provider=provider_name,
        model=model,
        run_id=run_id,
        fallback_attempted=True,
        reason=reason,
    )
    return build_local_summary(assistant_reply)
