"""上下文装配策略规则。"""

from __future__ import annotations

from typing import Callable, Mapping, Sequence

from .query_intent import is_current_time_query, is_memory_recall_query, is_weather_query

_CONTEXT_LIMITS = {
    "persona": 120,
    "long_term": 300,
    "bionic": 250,
    "user_profile": 160,
    "relationship": 140,
    "knowledge": 400,
    "web": 1200,
    "chat_recall": 900,
    "runtime": 120,
}

_LIGHT_CHAT_CONTEXT_LIMITS = {
    "runtime": 80,
}


def _adjust_effective_mode_for_pure_mode(
    manual_mode: str,
    effective_mode: str,
    pure_mode_enabled: bool,
) -> str:
    """pure_mode 打开时，避免自动 light 进一步收缩上下文。"""
    if pure_mode_enabled and manual_mode == "normal" and effective_mode == "light":
        return "normal"
    return effective_mode


def _should_retrieve_context(effective_mode: str) -> bool:
    """当前模式是否拉检索型上下文。"""
    return effective_mode in ("normal", "qa")


def _should_include_knowledge(
    effective_mode: str,
    user_text: str,
    *,
    history: Sequence[Mapping[str, str]] | None = None,
) -> bool:
    """当前模式是否拉知识库上下文。"""
    return (
        effective_mode == "qa"
        and not is_memory_recall_query(user_text, history=history)
        and not is_current_time_query(user_text)
    )


def _should_search_web(
    effective_mode: str,
    user_text: str,
    *,
    should_search_fn: Callable[[str], bool],
    history: Sequence[Mapping[str, str]] | None = None,
) -> bool:
    """当前模式是否触发联网搜索。"""
    return (
        effective_mode == "qa"
        and not is_memory_recall_query(user_text, history=history)
        and (not is_current_time_query(user_text) or is_weather_query(user_text))
        and should_search_fn(user_text)
    )


def _get_context_limit(block_name: str, *, light_chat_mode: bool = False) -> int:
    """获取指定上下文块的裁剪长度。"""
    if light_chat_mode and block_name in _LIGHT_CHAT_CONTEXT_LIMITS:
        return _LIGHT_CHAT_CONTEXT_LIMITS[block_name]
    return _CONTEXT_LIMITS[block_name]
