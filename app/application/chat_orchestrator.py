"""主对话编排服务。"""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from typing import Any, Mapping

from ..config import Config
from ..infrastructure.persistence.sqlite_conversation_repo import get_active_conversation
from ..infrastructure.persistence.sqlite_history_repo import get_recent_history, save_message
from ..logger import logger
from ..presentation.parsers.feishu_event_parser import parse_message
from .command_service import handle_command
from .observation_service import observation_runtime_state
from .post_reply_jobs import async_reflect, async_voice_reply, background_executor, send_error_alert
from .reply_service import generate_reply

# 入口线程池：仅用于承接飞书事件，避免与后台任务互相挤占。
executor = ThreadPoolExecutor(max_workers=Config.INGRESS_MAX_WORKERS)

_logic_locks = defaultdict(Lock)
_logic_locks_lock = Lock()
_MAX_MESSAGE_LENGTH = 5000


def _get_dep(deps: Mapping[str, Any] | None, name: str, default: Any) -> Any:
    if deps and name in deps:
        return deps[name]
    return default


def _get_user_logic_lock(user_id: str) -> Lock:
    """获取指定用户的逻辑锁，同一用户串行化。"""
    with _logic_locks_lock:
        return _logic_locks[user_id]


def _normalize_reply_result(reply_result: Any) -> tuple[str, Any]:
    """兼容历史 tuple 契约与新 ReplyResult 字典。"""
    if isinstance(reply_result, tuple) and len(reply_result) == 2:
        return reply_result[0], reply_result[1]
    if isinstance(reply_result, dict):
        return str(reply_result.get("reply_text", "") or ""), reply_result.get("summary")
    return str(reply_result or ""), None


def core_logic(data: dict, *, deps: Mapping[str, Any] | None = None) -> None:
    """接收飞书消息后的核心处理流程。"""
    parse_message_fn = _get_dep(deps, "parse_message", parse_message)
    handle_command_fn = _get_dep(deps, "handle_command", handle_command)
    get_recent_history_fn = _get_dep(deps, "get_recent_history", get_recent_history)
    get_active_conversation_fn = _get_dep(
        deps, "get_active_conversation", get_active_conversation
    )
    save_message_fn = _get_dep(deps, "save_message", save_message)
    generate_reply_fn = _get_dep(deps, "generate_reply", generate_reply)
    handle_ai_reply_fn = _get_dep(deps, "handle_ai_reply", None)
    observation_runtime_state_fn = _get_dep(
        deps, "observation_runtime_state", observation_runtime_state
    )
    background_executor_obj = _get_dep(deps, "background_executor", background_executor)
    async_reflect_fn = _get_dep(deps, "async_reflect", async_reflect)
    async_voice_reply_fn = _get_dep(deps, "async_voice_reply", async_voice_reply)
    send_error_alert_fn = _get_dep(deps, "send_error_alert", send_error_alert)
    logger_obj = _get_dep(deps, "logger", logger)

    try:
        open_id, user_text = parse_message_fn(data)
        if not open_id or not user_text:
            return

        with _get_user_logic_lock(open_id):
            if user_text.strip().startswith("/"):
                handle_command_fn(open_id, user_text.strip())
                return

            if len(user_text) > _MAX_MESSAGE_LENGTH:
                user_text = user_text[:_MAX_MESSAGE_LENGTH]
                logger_obj.warning(f"⚠️ 用户消息过长，已截断至 {_MAX_MESSAGE_LENGTH} 字符")

            conversation = get_active_conversation_fn(open_id)
            conversation_id = str(conversation.get("id") or "")
            conversation_mode = str(conversation.get("mode") or "normal")
            history = get_recent_history_fn(
                open_id,
                limit=12,
                conversation_id=conversation_id or None,
            )
            save_message_fn(open_id, "user", user_text, conversation_id=conversation_id or None)

            with observation_runtime_state_fn(open_id, "replying", deps=deps):
                if handle_ai_reply_fn is not None:
                    reply_result = handle_ai_reply_fn(open_id, user_text, history)
                else:
                    reply_result = generate_reply_fn(open_id, user_text, history)

            reply, summary_info = _normalize_reply_result(reply_result)
            if isinstance(summary_info, dict):
                extracted_summary = summary_info.get("intent")
                emotion = summary_info.get("emotion")
                theme = summary_info.get("theme")
            else:
                extracted_summary, emotion, theme = None, None, None

            if len(reply) > _MAX_MESSAGE_LENGTH:
                reply = reply[:_MAX_MESSAGE_LENGTH]

            save_message_fn(open_id, "assistant", reply, conversation_id=conversation_id or None)
            background_executor_obj.submit(
                async_reflect_fn,
                open_id,
                user_text,
                reply,
                conversation_id=conversation_id or None,
                conversation_mode=conversation_mode,
            )
            background_executor_obj.submit(
                async_voice_reply_fn,
                open_id,
                user_text,
                reply,
                extracted_summary,
                emotion,
                theme,
            )
    except Exception as exc:
        error_info = f"Core Logic Error: {exc}"
        logger_obj.error(error_info, exc_info=True)
        send_error_alert_fn(error_info)
