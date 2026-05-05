"""实时观察应用服务。"""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Mapping
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from ..config import Config
from ..domain.observation_rules import build_observation_context
from ..domain.reply_text import normalize_reply_text
from ..infrastructure.persistence.sqlite_history_repo import get_last_interaction_time, get_recent_history
from ..infrastructure.persistence.sqlite_memory_repo import get_active_memories, get_bionic_state
from ..infrastructure.persistence.sqlite_observation_repo import (
    clear_presence_runtime_state,
    get_presence_runtime_state,
    invalidate_presence_snapshot,
    get_presence_snapshot,
    save_presence_runtime_state,
    save_presence_snapshot,
)
from ..logger import logger
from ..time_utils import SQLITE_TIMESTAMP_FORMAT, local_now_naive, parse_sqlite_utc, sqlite_utc_to_local_naive, utc_now_naive
from ..weather import get_weather
from .memory_reflection_service import call_low_cost_ai

_RECENT_CHAT_WINDOW_SECONDS = 300
_LINGER_CHAT_WINDOW_SECONDS = 1800
_RUNTIME_STATE_PRESETS = {
    "replying": {
        "label": "正在回你消息",
        "scene_hint": "她低头捧着手机敲字，指尖停停续续，像是在斟酌下一句该怎么回你",
        "ttl_seconds": 180,
        "priority": 40,
    },
    "media_rendering": {
        "label": "镜头正在成像",
        "scene_hint": "她像是被一台看不见的镜头轻轻定格住，周围的光影正一点点聚焦成画面",
        "ttl_seconds": 600,
        "priority": 35,
    },
    "reflecting": {
        "label": "刚聊完还在回味",
        "scene_hint": "她把手机搁在手边，视线却还没从刚才的对话里抽开，像是在慢慢回味你们刚说过的话",
        "ttl_seconds": 180,
        "priority": 30,
    },
    "proactive": {
        "label": "想主动戳你一下",
        "scene_hint": "她抱着手机发了一会儿呆，删删改改好几次，像终于决定主动给你发点什么",
        "ttl_seconds": 240,
        "priority": 20,
    },
    "reminder": {
        "label": "正惦记着提醒你",
        "scene_hint": "她像是忽然想起什么似的摸过手机，皱着鼻尖敲下一句不太肯承认的提醒",
        "ttl_seconds": 240,
        "priority": 10,
    },
}


def _get_dep(deps: Mapping[str, Any] | None, name: str, default: Any) -> Any:
    if deps and name in deps:
        return deps[name]
    return default


def _format_sqlite_timestamp(dt: datetime) -> str:
    return dt.strftime(SQLITE_TIMESTAMP_FORMAT)


def _shorten_text(text: str, limit: int = 18) -> str:
    cleaned = normalize_reply_text(text or "")
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip() + "..."


def _to_local_iso(timestamp: str) -> str:
    return sqlite_utc_to_local_naive(timestamp).isoformat(timespec="seconds")


def _is_snapshot_fresh(snapshot: Mapping[str, Any] | None, now_utc: datetime) -> bool:
    if not snapshot:
        return False
    expires_at = snapshot.get("expires_at")
    if not isinstance(expires_at, str) or not expires_at:
        return False
    try:
        return parse_sqlite_utc(expires_at) > now_utc
    except Exception:
        return False


def _resolve_target_user_id(explicit_user_id: str | None, *, config=Config) -> str | None:
    user_id = (explicit_user_id or "").strip()
    if user_id:
        return user_id
    admin_id = getattr(config, "ADMIN_OPEN_ID", None)
    return admin_id.strip() if isinstance(admin_id, str) and admin_id.strip() else None


def _summarize_weather(weather_text: str) -> str:
    text = normalize_reply_text(weather_text or "")
    if not text:
        return "天气未知"
    if "：" in text:
        text = text.split("：", 1)[1]
    if "，" in text:
        text = text.split("，", 1)[0]
    return text.strip() or "天气未知"


def _build_recent_chat_hint(
    user_id: str,
    *,
    now_local: datetime,
    get_last_interaction_time_fn,
    get_recent_history_fn,
) -> tuple[str, str]:
    last_time = get_last_interaction_time_fn(user_id)
    if not last_time:
        return "", "routine"

    delta_seconds = max(0.0, (now_local - last_time).total_seconds())
    if delta_seconds > _LINGER_CHAT_WINDOW_SECONDS:
        return "", "routine"

    recent_history = get_recent_history_fn(user_id, limit=2) or []
    latest_user_text = ""
    for item in reversed(recent_history):
        if item.get("role") == "user":
            latest_user_text = _shorten_text(item.get("content", ""), limit=14)
            break

    if delta_seconds <= _RECENT_CHAT_WINDOW_SECONDS:
        if latest_user_text:
            return f"她刚看完你发来的“{latest_user_text}”，手机还扣在手边。", "recent_chat"
        return "她刚把手机扣在手边，屏幕像是还停在和你的对话框上。", "recent_chat"

    if latest_user_text:
        return f"她隔一会儿会看一眼手机，像是在等关于“{latest_user_text}”的新消息。", "recent_chat"
    return "她隔一会儿会看一眼手机，像是在等新的消息。", "recent_chat"


def _build_memory_hint(user_id: str, *, get_active_memories_fn) -> str:
    memories = get_active_memories_fn(user_id, limit=3) or []
    for memory in memories:
        content = _shorten_text(memory.get("content", ""), limit=28)
        if content:
            return content
    return ""


def _get_runtime_state_preset(state_code: str) -> dict[str, Any]:
    return dict(_RUNTIME_STATE_PRESETS.get((state_code or "").strip().lower(), {}))


def _get_active_runtime_state(
    user_id: str,
    *,
    now_utc: datetime,
    get_presence_runtime_state_fn,
) -> dict[str, Any] | None:
    runtime_state = get_presence_runtime_state_fn(user_id)
    if not runtime_state:
        return None

    expires_at = runtime_state.get("expires_at")
    if not isinstance(expires_at, str) or not expires_at:
        return None

    try:
        if parse_sqlite_utc(expires_at) <= now_utc:
            return None
    except Exception:
        return None
    return dict(runtime_state)


def _build_media_prompt(snapshot: Mapping[str, Any], *, current_time: str) -> str:
    parts = [
        f"时间：{current_time}",
        f"场景：{snapshot.get('routine_label', '')}",
        f"动作：{snapshot.get('scene_detail', '')}",
    ]
    if snapshot.get("weather_summary"):
        parts.append(f"天气：{snapshot['weather_summary']}")
    if snapshot.get("accident_text"):
        parts.append(f"意外：{snapshot['accident_text']}")
    if snapshot.get("recent_chat_hint"):
        parts.append(f"手机细节：{snapshot['recent_chat_hint']}")
    return "；".join(part for part in parts if part)


def _build_fallback_observation(snapshot: Mapping[str, Any]) -> str:
    scene_detail = snapshot.get("scene_detail") or "她安静待在自己的角落里"
    accident_text = snapshot.get("accident_text", "")
    recent_chat_hint = snapshot.get("recent_chat_hint", "")
    weather_summary = snapshot.get("weather_summary", "")

    parts = [scene_detail]
    if accident_text:
        parts.append(accident_text)
    if recent_chat_hint:
        parts.append(recent_chat_hint)
    elif weather_summary:
        parts.append(f"外头的天气像是{weather_summary}")

    text = "，".join(part.strip("，。 ") for part in parts if part).strip()
    if not text:
        text = "她这会儿安安静静待着，像是刚从一天的忙乱里偷出一点自己的时间。"
    if not text.endswith(("。", "！", "？")):
        text += "。"
    return normalize_reply_text(text)


def render_observation_text(snapshot: Mapping[str, Any], *, deps: Mapping[str, Any] | None = None) -> tuple[str, str]:
    """把 snapshot 渲染成第三人称观察白描。"""
    call_low_cost_ai_fn = _get_dep(deps, "call_low_cost_ai", call_low_cost_ai)
    logger_obj = _get_dep(deps, "logger", logger)

    system_prompt = (
        "你是一个隐形摄像机，正在客观描述助手此刻的画面。\n"
        "你只能写第三人称画面白描，不能写第一人称，不能解释心理活动。\n"
        "请用动作、环境、手部细节、表情和手机反应来表现她当下的状态。\n"
        "输出必须是 30-70 字的单段中文，不要加引号，不要解释。"
    )
    user_prompt = (
        f"当前时间：{snapshot.get('current_time', '')}\n"
        f"基础行程：{snapshot.get('routine_label', '')}\n"
        f"基础画面：{snapshot.get('scene_detail', '')}\n"
        f"天气：{snapshot.get('weather_summary', '')}\n"
        f"情绪：{snapshot.get('mood', '平静')}\n"
        f"突发意外：{snapshot.get('accident_text', '无')}\n"
        f"最近聊天提示：{snapshot.get('recent_chat_hint', '无')}\n"
        f"长期记忆提示：{snapshot.get('memory_hint', '无')}\n"
    )

    raw = normalize_reply_text(call_low_cost_ai_fn(system_prompt, user_prompt, max_tokens=120))
    if raw:
        cleaned = raw.strip("“”\"' ")
        if cleaned:
            return cleaned, "ai"

    logger_obj.info("👁️ observation 渲染未命中 AI 结果，回退模板文案")
    return _build_fallback_observation(snapshot), "template"


def activate_presence_runtime_state(
    user_id: str,
    state_code: str,
    *,
    scene_hint: str = "",
    ttl_seconds: int | None = None,
    deps: Mapping[str, Any] | None = None,
) -> str | None:
    """写入显式运行时状态，并让缓存 snapshot 立即过期。"""
    save_presence_runtime_state_fn = _get_dep(
        deps, "save_presence_runtime_state", save_presence_runtime_state
    )
    get_presence_runtime_state_fn = _get_dep(
        deps, "get_presence_runtime_state", get_presence_runtime_state
    )
    invalidate_presence_snapshot_fn = _get_dep(
        deps, "invalidate_presence_snapshot", invalidate_presence_snapshot
    )
    utc_now_naive_fn = _get_dep(deps, "utc_now_naive", utc_now_naive)
    logger_obj = _get_dep(deps, "logger", logger)

    normalized_state_code = (state_code or "").strip().lower()
    if not user_id or not normalized_state_code:
        return None

    preset = _get_runtime_state_preset(normalized_state_code)
    if not preset:
        logger_obj.warning(
            "⚠️ observation runtime_state 未知，已跳过",
            extra={"user_id": user_id, "state_code": normalized_state_code},
        )
        return None

    now_utc = utc_now_naive_fn()
    current = _get_active_runtime_state(
        user_id,
        now_utc=now_utc,
        get_presence_runtime_state_fn=get_presence_runtime_state_fn,
    )
    new_priority = int(preset["priority"])
    if current and int(current.get("state_priority", 0) or 0) > new_priority:
        logger_obj.info(
            "👁️ observation runtime_state 优先级较低，保留现有状态",
            extra={
                "user_id": user_id,
                "state_code": normalized_state_code,
                "current_state_code": current.get("state_code", ""),
            },
        )
        return None

    expires_at = now_utc + timedelta(seconds=max(1, ttl_seconds or int(preset["ttl_seconds"])))
    state_token = uuid4().hex
    runtime_state = {
        "state_code": normalized_state_code,
        "state_label": preset["label"],
        "state_priority": new_priority,
        "scene_hint": scene_hint.strip() or preset["scene_hint"],
        "state_token": state_token,
        "started_at": _format_sqlite_timestamp(now_utc),
        "expires_at": _format_sqlite_timestamp(expires_at),
        "updated_at": _format_sqlite_timestamp(now_utc),
    }
    if save_presence_runtime_state_fn(user_id, runtime_state):
        invalidate_presence_snapshot_fn(user_id)
        logger_obj.info(
            "👁️ 已写入 observation runtime_state",
            extra={"user_id": user_id, "state_code": normalized_state_code},
        )
        return state_token
    return None


def clear_presence_runtime_state_for_observation(
    user_id: str,
    state_token: str | None = None,
    *,
    deps: Mapping[str, Any] | None = None,
) -> bool:
    """清理显式运行时状态，并让缓存 snapshot 立即过期。"""
    clear_presence_runtime_state_fn = _get_dep(
        deps, "clear_presence_runtime_state", clear_presence_runtime_state
    )
    invalidate_presence_snapshot_fn = _get_dep(
        deps, "invalidate_presence_snapshot", invalidate_presence_snapshot
    )
    logger_obj = _get_dep(deps, "logger", logger)

    if not user_id:
        return False
    cleared = clear_presence_runtime_state_fn(user_id, state_token=state_token)
    if cleared:
        invalidate_presence_snapshot_fn(user_id)
        logger_obj.info("👁️ 已清理 observation runtime_state", extra={"user_id": user_id})
    return cleared


@contextmanager
def observation_runtime_state(
    user_id: str,
    state_code: str,
    *,
    scene_hint: str = "",
    ttl_seconds: int | None = None,
    deps: Mapping[str, Any] | None = None,
):
    """在一段执行期间挂上显式运行时状态。"""
    state_token = activate_presence_runtime_state(
        user_id,
        state_code,
        scene_hint=scene_hint,
        ttl_seconds=ttl_seconds,
        deps=deps,
    )
    try:
        yield state_token
    finally:
        if state_token:
            clear_presence_runtime_state_for_observation(
                user_id,
                state_token=state_token,
                deps=deps,
            )


def get_or_create_observation_snapshot(
    user_id: str,
    *,
    force_refresh: bool = False,
    deps: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """读取或生成 observation snapshot。"""
    get_presence_snapshot_fn = _get_dep(deps, "get_presence_snapshot", get_presence_snapshot)
    get_presence_runtime_state_fn = _get_dep(
        deps, "get_presence_runtime_state", get_presence_runtime_state
    )
    save_presence_snapshot_fn = _get_dep(deps, "save_presence_snapshot", save_presence_snapshot)
    local_now_naive_fn = _get_dep(deps, "local_now_naive", local_now_naive)
    utc_now_naive_fn = _get_dep(deps, "utc_now_naive", utc_now_naive)
    get_weather_fn = _get_dep(deps, "get_weather", get_weather)
    get_bionic_state_fn = _get_dep(deps, "get_bionic_state", get_bionic_state)
    get_last_interaction_time_fn = _get_dep(
        deps, "get_last_interaction_time", get_last_interaction_time
    )
    get_recent_history_fn = _get_dep(deps, "get_recent_history", get_recent_history)
    get_active_memories_fn = _get_dep(deps, "get_active_memories", get_active_memories)
    build_observation_context_fn = _get_dep(
        deps, "build_observation_context", build_observation_context
    )
    render_observation_text_fn = _get_dep(deps, "render_observation_text", render_observation_text)
    logger_obj = _get_dep(deps, "logger", logger)
    config = _get_dep(deps, "config", Config)

    now_utc = utc_now_naive_fn()
    cached = get_presence_snapshot_fn(user_id)
    if not force_refresh and _is_snapshot_fresh(cached, now_utc):
        return dict(cached)

    now_local = local_now_naive_fn()
    weather_summary = _summarize_weather(get_weather_fn())
    state = get_bionic_state_fn(user_id) or {}
    mood = state.get("current_mood", "平静") or "平静"
    mood_intensity = float(state.get("mood_intensity", 0.5) or 0.5)

    base_context = build_observation_context_fn(
        user_id,
        now_local,
        weather_summary=weather_summary,
        mood=mood,
    )
    active_runtime_state = _get_active_runtime_state(
        user_id,
        now_utc=now_utc,
        get_presence_runtime_state_fn=get_presence_runtime_state_fn,
    )
    recent_chat_hint, state_source = _build_recent_chat_hint(
        user_id,
        now_local=now_local,
        get_last_interaction_time_fn=get_last_interaction_time_fn,
        get_recent_history_fn=get_recent_history_fn,
    )
    memory_hint = _build_memory_hint(user_id, get_active_memories_fn=get_active_memories_fn)
    routine_label = base_context["routine_label"]
    scene_detail = base_context["scene_detail"]
    if active_runtime_state:
        state_source = active_runtime_state.get("state_code", "routine") or "routine"
        routine_label = active_runtime_state.get("state_label", routine_label) or routine_label
        scene_detail = active_runtime_state.get("scene_hint", scene_detail) or scene_detail
    elif state_source == "routine" and base_context.get("accident_code", "").startswith("mood_"):
        state_source = "mood"

    snapshot = {
        "snapshot_version": 1,
        "state_source": state_source,
        "routine_slot": base_context["routine_slot"],
        "routine_label": routine_label,
        "weather_summary": weather_summary,
        "accident_code": base_context["accident_code"],
        "accident_text": base_context["accident_text"],
        "mood": mood,
        "mood_intensity": round(mood_intensity, 2),
        "recent_chat_hint": recent_chat_hint,
        "memory_hint": memory_hint,
        "media_type": "text",
        "media_status": "none",
        "media_key": "",
        "updated_reason": active_runtime_state.get("state_code", "") if active_runtime_state else ("force_refresh" if force_refresh else "cache_miss"),
        "current_time": now_local.strftime("%Y-%m-%d %H:%M"),
        "scene_detail": scene_detail,
    }
    observation_text, generated_by = render_observation_text_fn(snapshot, deps=deps)
    generated_at = now_utc
    expires_at = now_utc + timedelta(seconds=config.OBSERVATION_CACHE_SECONDS)

    stored_snapshot = {
        **snapshot,
        "observation_text": observation_text,
        "media_prompt": _build_media_prompt(snapshot, current_time=snapshot["current_time"]),
        "generated_by": generated_by,
        "generated_at": _format_sqlite_timestamp(generated_at),
        "expires_at": _format_sqlite_timestamp(expires_at),
    }
    save_presence_snapshot_fn(user_id, stored_snapshot)
    logger_obj.info(
        "👁️ 已更新 observation snapshot",
        extra={
            "user_id": user_id,
            "state_source": stored_snapshot["state_source"],
            "routine_slot": stored_snapshot["routine_slot"],
            "generated_by": stored_snapshot["generated_by"],
        },
    )
    return stored_snapshot


def get_observation_text(
    user_id: str,
    *,
    force_refresh: bool = False,
    deps: Mapping[str, Any] | None = None,
) -> str:
    """返回给 `/observe` 的文字结果。"""
    snapshot = get_or_create_observation_snapshot(user_id, force_refresh=force_refresh, deps=deps)
    return snapshot.get("observation_text") or _build_fallback_observation(snapshot)


def build_presence_payload(
    explicit_user_id: str | None = None,
    *,
    force_refresh: bool = False,
    deps: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """构建 `/presence` 的只读返回。"""
    config = _get_dep(deps, "config", Config)
    user_id = _resolve_target_user_id(explicit_user_id, config=config)
    if not user_id:
        return {"status": "error", "message": "missing user_id and ADMIN_OPEN_ID"}

    snapshot = get_or_create_observation_snapshot(user_id, force_refresh=force_refresh, deps=deps)
    return {
        "status": "ok",
        "snapshot": {
            "snapshot_version": snapshot.get("snapshot_version", 1),
            "user_id": user_id,
            "state_source": snapshot.get("state_source", "routine"),
            "routine_slot": snapshot.get("routine_slot", ""),
            "routine_label": snapshot.get("routine_label", ""),
            "weather_summary": snapshot.get("weather_summary", ""),
            "accident_text": snapshot.get("accident_text", ""),
            "mood": snapshot.get("mood", "平静"),
            "mood_intensity": snapshot.get("mood_intensity", 0.5),
            "recent_chat_hint": snapshot.get("recent_chat_hint", ""),
            "memory_hint": snapshot.get("memory_hint", ""),
            "observation_text": snapshot.get("observation_text", ""),
            "media": {
                "type": snapshot.get("media_type", "text"),
                "status": snapshot.get("media_status", "none"),
                "prompt": snapshot.get("media_prompt", ""),
                "key": snapshot.get("media_key") or None,
            },
            "generated_by": snapshot.get("generated_by", "template"),
            "generated_at": _to_local_iso(snapshot.get("generated_at", _format_sqlite_timestamp(utc_now_naive()))),
            "expires_at": _to_local_iso(snapshot.get("expires_at", _format_sqlite_timestamp(utc_now_naive()))),
        },
    }
