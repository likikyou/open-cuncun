"""上下文组装应用服务。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Mapping

from ..domain.context_policy import (
    _adjust_effective_mode_for_pure_mode,
    _get_context_limit,
    _should_include_knowledge,
    _should_retrieve_context,
    _should_search_web,
)
from ..domain.query_intent import (
    get_memory_recall_day_offset,
    is_memory_recall_query,
    normalize_weather_query,
)
from ..domain.reply_mode import _resolve_reply_mode
from ..logger import logger
from ..observability import record_degradation
from ..retrieval import (
    get_knowledge_memory,
    get_long_term_memory,
    get_persona_memory,
    get_relationship_memory,
    get_user_profile_memory,
)
from ..search import search_web_bocha, should_search

_retrieval_executor = ThreadPoolExecutor(max_workers=4)


@dataclass(frozen=True)
class ContextFetchResult:
    value: str = ""
    degraded: bool = False
    reason: str | None = None


def _compact_preview(text: str, limit: int = 80) -> str:
    if not text:
        return ""
    preview = " ".join(text.strip().split())
    if len(preview) <= limit:
        return preview
    return preview[:limit].rstrip() + "..."


def _count_context_items(text: str) -> int:
    if not text:
        return 0
    return sum(1 for line in text.splitlines() if line.strip().startswith("- "))


def _log_context_observability(
    *,
    logger,
    user_id: str,
    user_text: str,
    manual_mode: str,
    effective_mode: str,
    need_retrieval: bool,
    need_knowledge: bool,
    need_web: bool,
    pure_mode_enabled: bool,
    context_blocks: dict,
    context_degradations: dict[str, str],
) -> None:
    previews = {name: _compact_preview(text) for name, text in context_blocks.items() if text}
    hits = {name: bool(text) for name, text in context_blocks.items()}
    item_counts = {
        name: _count_context_items(text)
        for name, text in context_blocks.items()
        if text and name in ("persona", "relationship", "user_profile", "long_term")
    }
    logger.info(
        "🔎 上下文命中概览",
        extra={
            "open_id": user_id or "",
            "user_text": user_text,
            "manual_mode": manual_mode,
            "effective_mode": effective_mode,
            "need_retrieval": need_retrieval,
            "need_knowledge": need_knowledge,
            "need_web": need_web,
            "pure_mode_enabled": pure_mode_enabled,
            "context_hits": hits,
            "context_item_counts": item_counts,
            "context_previews": previews,
            "context_degraded": bool(context_degradations),
            "context_degradations": context_degradations,
        },
    )


def _get_futures_result(futures: dict, key: str, name: str, *, logger) -> ContextFetchResult:
    future = futures.get(key)
    if future is None:
        return ContextFetchResult()
    try:
        return ContextFetchResult(value=future.result() or "")
    except Exception as exc:
        reason = getattr(exc, "degradation_reason", f"{key}_lookup_failed")
        severity = getattr(exc, "degradation_severity", "warning")
        component = getattr(exc, "degradation_component", "context_assembler")
        details = {
            "source": key,
            "label": name,
            "error_type": exc.__class__.__name__,
        }
        extra_details = getattr(exc, "degradation_details", None)
        if isinstance(extra_details, dict):
            details.update(extra_details)
        record_degradation(
            component,
            reason,
            severity=severity,
            **details,
        )
        logger.warning(f"⚠️ {name} 检索异常: {exc}", exc_info=True)
        return ContextFetchResult(degraded=True, reason=reason)


def _clip_context(text: str, limit: int) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def _append_block(lines: list[str], block: str) -> None:
    if block:
        lines.append(block)


def _format_story_block(story_scene: str) -> str:
    scene_text = story_scene or "一段只属于当前对话的虚构剧情。"
    return (
        "\n\n### 🎬 当前剧情模式（只作用于本会话）\n"
        f"【剧情设定】{scene_text}\n"
        "（这是你和用户在当前对话里共同进入的虚构剧情。"
        "可以自然描写场景、动作、环境和情绪推进，但要保持角色嘴硬心软、亲密又有分寸的表达。"
        "剧情里的地点、相遇、客户、行程和事件都只属于这个会话，不要当作现实经历或长期事实。"
        '不要跳出角色解释"这是剧情模式"，除非用户直接问。）'
    )


def _clip_chat_line(text: str, limit: int = 120) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[:limit].rstrip() + "..."


def _relative_day_label(day_offset: int) -> str:
    if day_offset == 0:
        return "今天"
    if day_offset == 1:
        return "昨天"
    if day_offset == 2:
        return "前天"
    if day_offset == 3:
        return "大前天"
    return f"{day_offset}天前"


def _format_chat_recall_context(records: list[dict], *, day_offset: int | None) -> str:
    label = _relative_day_label(day_offset or 0)
    header = f"【真实对话回看：{label}】"
    if not records:
        return f"{header}\n- 未找到这一天的原始聊天记录。"

    lines = [header]
    for item in records:
        role = item.get("role", "")
        role_label = "用户" if role == "user" else "你"
        time_label = item.get("local_time", "")
        prefix = f"- [{time_label}] {role_label}：" if time_label else f"- {role_label}："
        lines.append(prefix + _clip_chat_line(item.get("content", "")))
    return "\n".join(lines)


def _default_get_user_setting(user_id: str, key: str, default: str = "") -> str:
    from ..infrastructure.persistence.sqlite_settings_repo import get_user_setting

    return get_user_setting(user_id, key, default)


def _default_get_runtime_state_context(user_id: str) -> str:
    from .memory_reflection_service import get_runtime_state_context

    return get_runtime_state_context(user_id)


def _default_get_active_conversation(user_id: str) -> dict:
    from ..infrastructure.persistence.sqlite_conversation_repo import get_active_conversation

    return get_active_conversation(user_id)


def _default_retrieve_bionic_memories(user_id: str, user_text: str) -> str:
    from .memory_reflection_service import retrieve_bionic_memories

    return retrieve_bionic_memories(user_id, user_text)


def _default_get_history_by_day_offset(
    user_id: str, day_offset: int, limit: int = 24
) -> list[dict]:
    from ..infrastructure.persistence.sqlite_history_repo import get_history_by_day_offset

    return get_history_by_day_offset(user_id, day_offset, limit=limit)


def _get_dep(deps: Mapping[str, Any] | None, name: str, default: Any) -> Any:
    if deps and name in deps:
        return deps[name]
    return default


def build_messages(
    system_prompt: str,
    user_text: str,
    history: list | None = None,
    reply_mode: str = "normal",
    user_id: str = "",
    *,
    deps: Mapping[str, Any] | None = None,
) -> list:
    """按策略组装最终 messages。"""
    if history is None:
        history = []

    logger_obj = _get_dep(deps, "logger", logger)
    should_search_fn = _get_dep(deps, "should_search", should_search)
    get_user_setting_fn = _get_dep(deps, "get_user_setting", _default_get_user_setting)
    get_runtime_state_context_fn = _get_dep(
        deps,
        "get_runtime_state_context",
        _default_get_runtime_state_context,
    )
    get_active_conversation_fn = _get_dep(
        deps,
        "get_active_conversation",
        _default_get_active_conversation,
    )
    get_persona_memory_fn = _get_dep(deps, "get_persona_memory", get_persona_memory)
    get_long_term_memory_fn = _get_dep(deps, "get_long_term_memory", get_long_term_memory)
    retrieve_bionic_memories_fn = _get_dep(
        deps,
        "retrieve_bionic_memories",
        _default_retrieve_bionic_memories,
    )
    get_user_profile_memory_fn = _get_dep(deps, "get_user_profile_memory", get_user_profile_memory)
    get_relationship_memory_fn = _get_dep(deps, "get_relationship_memory", get_relationship_memory)
    get_knowledge_memory_fn = _get_dep(deps, "get_knowledge_memory", get_knowledge_memory)
    search_web_bocha_fn = _get_dep(deps, "search_web_bocha", search_web_bocha)
    get_history_by_day_offset_fn = _get_dep(
        deps,
        "get_history_by_day_offset",
        _default_get_history_by_day_offset,
    )

    manual_mode, effective_mode = _resolve_reply_mode(
        user_text,
        reply_mode,
        should_search_fn=should_search_fn,
        history=history,
    )
    memory_recall_query = is_memory_recall_query(user_text, history=history)
    memory_recall_day_offset = get_memory_recall_day_offset(user_text, history=history)

    pure_mode_enabled = False
    if user_id:
        try:
            pure_mode_enabled = (
                get_user_setting_fn(user_id, "pure_mode", "off") or ""
            ).strip().lower() == "on"
        except Exception as exc:
            record_degradation(
                "context_assembler",
                "pure_mode_lookup_failed",
                severity="warning",
                user_id=user_id,
                error_type=exc.__class__.__name__,
            )
            logger_obj.warning(f"⚠️ 获取净聊测试模式异常: {exc}", exc_info=True)

    effective_mode = _adjust_effective_mode_for_pure_mode(
        manual_mode,
        effective_mode,
        pure_mode_enabled,
    )
    light_chat_mode = effective_mode == "light"
    if light_chat_mode and history:
        history = history[-2:]

    runtime_state = ""
    active_conversation = {}
    if user_id:
        try:
            runtime_state = get_runtime_state_context_fn(user_id)
        except Exception as exc:
            record_degradation(
                "context_assembler",
                "runtime_state_lookup_failed",
                severity="warning",
                user_id=user_id,
                error_type=exc.__class__.__name__,
            )
            logger_obj.warning(f"⚠️ 获取运行时状态异常: {exc}", exc_info=True)
        try:
            active_conversation = get_active_conversation_fn(user_id) or {}
        except Exception as exc:
            record_degradation(
                "context_assembler",
                "active_conversation_lookup_failed",
                severity="warning",
                user_id=user_id,
                error_type=exc.__class__.__name__,
            )
            logger_obj.warning(f"⚠️ 获取当前会话异常: {exc}", exc_info=True)
    story_mode_enabled = active_conversation.get("mode") == "story"
    story_scene = (active_conversation.get("summary") or active_conversation.get("title") or "").strip()

    need_retrieval = _should_retrieve_context(effective_mode)
    need_knowledge = _should_include_knowledge(
        effective_mode,
        user_text,
        history=history,
    )
    need_web = _should_search_web(
        effective_mode,
        user_text,
        should_search_fn=should_search_fn,
        history=history,
    )

    futures = {}
    if need_retrieval:
        futures["persona"] = _retrieval_executor.submit(
            get_persona_memory_fn,
            user_text,
            1,
        )
        if not pure_mode_enabled:
            futures["long_term"] = _retrieval_executor.submit(
                get_long_term_memory_fn,
                user_text,
                distance_threshold=1.0,
                user_id=user_id,
            )
            futures["bionic"] = _retrieval_executor.submit(
                retrieve_bionic_memories_fn,
                user_id,
                user_text,
            )
        if user_id:
            futures["user_profile"] = _retrieval_executor.submit(
                get_user_profile_memory_fn,
                user_text,
                user_id,
                2,
            )
            futures["relationship"] = _retrieval_executor.submit(
                get_relationship_memory_fn,
                user_text,
                user_id,
                2,
            )
        if need_knowledge:
            futures["knowledge"] = _retrieval_executor.submit(
                get_knowledge_memory_fn,
                user_text,
            )
        if memory_recall_query and user_id and memory_recall_day_offset is not None:
            futures["chat_recall"] = _retrieval_executor.submit(
                get_history_by_day_offset_fn,
                user_id,
                memory_recall_day_offset,
                24,
            )

    if need_web:
        futures["web"] = _retrieval_executor.submit(
            search_web_bocha_fn,
            normalize_weather_query(user_text),
        )

    persona_result = (
        _get_futures_result(futures, "persona", "人设底稿", logger=logger_obj)
        if need_retrieval
        else ContextFetchResult()
    )
    long_term_result = (
        _get_futures_result(futures, "long_term", "长期记忆", logger=logger_obj)
        if need_retrieval
        else ContextFetchResult()
    )
    bionic_result = (
        _get_futures_result(futures, "bionic", "仿生记忆", logger=logger_obj)
        if need_retrieval
        else ContextFetchResult()
    )
    user_profile_result = (
        _get_futures_result(futures, "user_profile", "用户画像", logger=logger_obj)
        if need_retrieval and user_id
        else ContextFetchResult()
    )
    relationship_result = (
        _get_futures_result(futures, "relationship", "关系洞察", logger=logger_obj)
        if need_retrieval and user_id
        else ContextFetchResult()
    )
    knowledge_result = (
        _get_futures_result(futures, "knowledge", "知识库", logger=logger_obj)
        if need_knowledge
        else ContextFetchResult()
    )
    web_result = (
        _get_futures_result(futures, "web", "联网搜索", logger=logger_obj)
        if need_web
        else ContextFetchResult()
    )
    chat_recall_result = (
        _get_futures_result(futures, "chat_recall", "原始对话回看", logger=logger_obj)
        if memory_recall_query and user_id and memory_recall_day_offset is not None
        else ContextFetchResult()
    )
    chat_recall_records = (
        chat_recall_result.value if isinstance(chat_recall_result.value, list) else []
    )

    persona_info = _clip_context(persona_result.value, _get_context_limit("persona"))
    long_term_info = _clip_context(long_term_result.value, _get_context_limit("long_term"))
    bionic_info = _clip_context(bionic_result.value, _get_context_limit("bionic"))
    user_profile_info = _clip_context(user_profile_result.value, _get_context_limit("user_profile"))
    relationship_info = _clip_context(relationship_result.value, _get_context_limit("relationship"))
    knowledge_info = _clip_context(knowledge_result.value, _get_context_limit("knowledge"))
    real_time_info = _clip_context(web_result.value, _get_context_limit("web"))
    chat_recall_info = ""
    if memory_recall_query and user_id and memory_recall_day_offset is not None:
        chat_recall_info = _clip_context(
            _format_chat_recall_context(
                chat_recall_records or [], day_offset=memory_recall_day_offset
            ),
            _get_context_limit("chat_recall"),
        )
    runtime_state = _clip_context(
        runtime_state,
        _get_context_limit("runtime", light_chat_mode=light_chat_mode),
    )

    context_degradations = {
        name: result.reason
        for name, result in {
            "persona": persona_result,
            "long_term": long_term_result,
            "bionic": bionic_result,
            "user_profile": user_profile_result,
            "relationship": relationship_result,
            "chat_recall": chat_recall_result,
            "knowledge": knowledge_result,
            "web": web_result,
        }.items()
        if result.degraded and result.reason
    }

    context_blocks = {
        "persona": persona_info,
        "relationship": relationship_info,
        "user_profile": user_profile_info,
        "long_term": long_term_info,
        "bionic": bionic_info,
        "runtime": runtime_state,
        "chat_recall": chat_recall_info,
        "knowledge": knowledge_info,
        "web": real_time_info,
    }
    _log_context_observability(
        logger=logger_obj,
        user_id=user_id,
        user_text=user_text,
        manual_mode=manual_mode,
        effective_mode=effective_mode,
        need_retrieval=need_retrieval,
        need_knowledge=need_knowledge,
        need_web=need_web,
        pure_mode_enabled=pure_mode_enabled,
        context_blocks=context_blocks,
        context_degradations=context_degradations,
    )

    role_state_block = "\n\n### 💡 角色的意识流与状态\n"
    role_state_block += "（这一层也可以理解成角色的意识流与外界感知。）\n"
    story_block = _format_story_block(story_scene) if story_mode_enabled else ""

    if light_chat_mode:
        if runtime_state:
            role_state_block += f"{runtime_state}\n"
        role_state_block += "（此时此刻，顺着当下的心情和用户聊聊就好。默认用一个连贯自然段说完，动作和停顿尽量内嵌在句子里，少量括号点到为止，不要换行分段，也不要主动翻出那些重复的老关心点，除非用户先提。）"
        enhanced_system_prompt = f"{system_prompt}{role_state_block}{story_block}"
        return (
            [{"role": "system", "content": enhanced_system_prompt}]
            + history
            + [{"role": "user", "content": user_text}]
        )

    role_state_lines = []
    bionic_prompt_info = bionic_info
    if memory_recall_query and chat_recall_info:
        bionic_prompt_info = ""
    _append_block(role_state_lines, persona_info)
    _append_block(role_state_lines, relationship_info)
    _append_block(role_state_lines, user_profile_info)
    _append_block(role_state_lines, long_term_info)
    _append_block(role_state_lines, bionic_prompt_info)
    _append_block(role_state_lines, runtime_state)
    if role_state_lines:
        role_state_block += "\n" + "\n".join(role_state_lines)
    role_state_block += "\n（把这些与你有关的底色、记忆、关系和当下状态，自然融进语气、态度与措辞里。它们定义你是谁，不需要像播报资料一样逐条复述。）"

    chat_recall_block = ""
    if chat_recall_info:
        chat_recall_block = "\n\n### 🗂 真实对话回看（优先用于回忆问题）\n"
        chat_recall_block += chat_recall_info
        chat_recall_block += (
            "\n（当用户在问昨天、前天、上次聊了什么时，优先根据这里回答。"
            "能说清楚就说清楚，记不清就坦白，不要把抽象记忆硬编成具体原话。）"
        )

    reference_block = ""
    reference_lines = []
    _append_block(reference_lines, knowledge_info)
    _append_block(reference_lines, real_time_info)
    if reference_lines:
        reference_block = "\n\n### 🌐 现实参考（仅供事实判断）\n"
        reference_block += "\n".join(reference_lines)
        reference_block += (
            "\n（这里是外部知识与联网信息，不是你的内心独白。"
            "只在涉及事实、时效、地点、价格、步骤、知识判断时吸收其中有用的部分；"
            "外部新闻不能变成你的客户、出行安排或私人经历；"
            '不要照抄搜索摘要，不要把"搜索结果显示""资料写着""标题写着"挂在嘴边，除非用户明确要你给来源；'
            "即使使用这些事实，也必须保持你原本的口吻、情绪和关系连续性。）"
        )

    enhanced_system_prompt = (
        f"{system_prompt}{role_state_block}{story_block}{chat_recall_block}{reference_block}"
    )
    return (
        [{"role": "system", "content": enhanced_system_prompt}]
        + history
        + [{"role": "user", "content": user_text}]
    )
