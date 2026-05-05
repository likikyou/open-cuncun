"""回复模式领域规则。"""

from __future__ import annotations

from typing import Callable, Mapping, Sequence

from .query_intent import is_memory_recall_query, is_persona_private_life_query

_QA_QUERY_KEYWORDS = (
    "为什么",
    "怎么",
    "如何",
    "分析",
    "解释",
    "总结",
    "建议",
    "计划",
    "帮我",
    "天气",
    "新闻",
    "价格",
    "多少钱",
    "几点",
    "时间",
    "地址",
    "代码",
    "bug",
    "报错",
    "接口",
    "部署",
    "配置",
    "知识库",
    "记忆",
    "搜索",
    "查询",
    "介绍",
    "推荐",
    "区别",
    "对比",
    "步骤",
    "原理",
)

_LIGHT_CHAT_SHORT_PHRASES = {
    "好",
    "好的",
    "好呀",
    "好哦",
    "嗯",
    "嗯嗯",
    "哦",
    "哦哦",
    "行",
    "行吧",
    "在吗",
    "在嘛",
    "晚安",
    "早安",
    "午安",
    "睡了",
    "困了",
    "哈哈",
    "哈哈哈",
    "嘿嘿",
    "嘿嘿嘿",
    "笑死",
    "想你",
    "抱抱",
    "亲亲",
    "么么",
    "爱你",
    "收到",
}


def _normalize_reply_mode(reply_mode: str) -> str:
    """规范化外部 reply_mode 输入。"""
    mode = (reply_mode or "normal").strip().lower()
    legacy_map = {
        "all": "qa",
        "web": "qa",
        "normal": "normal",
        "light": "light",
        "qa": "qa",
    }
    return legacy_map.get(mode, "normal")


def _is_qa_query(
    user_text: str,
    *,
    should_search_fn: Callable[[str], bool],
    history: Sequence[Mapping[str, str]] | None = None,
) -> bool:
    """判断输入是否更适合走问答/事实查询模式。"""
    text = (user_text or "").strip()
    if not text:
        return False
    if is_memory_recall_query(text, history=history):
        return False
    if is_persona_private_life_query(text, history=history):
        return False
    if should_search_fn(text):
        return True
    if any(keyword in text for keyword in _QA_QUERY_KEYWORDS):
        return True
    return len(text) > 8 and any(mark in text for mark in ("?", "？"))


def _is_light_chat(
    user_text: str,
    *,
    should_search_fn: Callable[[str], bool],
    history: Sequence[Mapping[str, str]] | None = None,
) -> bool:
    """判断输入是否应走轻聊分支。"""
    text = (user_text or "").strip()
    if not text:
        return False
    if is_memory_recall_query(text, history=history):
        return False
    if _is_qa_query(text, should_search_fn=should_search_fn, history=history):
        return False
    if "\n" in text:
        return False

    normalized = text.rstrip("。！？!?~～…")
    if len(normalized) <= 6:
        return True
    if normalized in _LIGHT_CHAT_SHORT_PHRASES:
        return True
    if any(sep in normalized for sep in ("，", ",", "；", ";", "：", ":")):
        return False
    punctuation_count = sum(normalized.count(ch) for ch in "。！？?!.")
    return len(normalized) <= 10 and punctuation_count <= 1


def _resolve_reply_mode(
    user_text: str,
    reply_mode: str,
    *,
    should_search_fn: Callable[[str], bool],
    history: Sequence[Mapping[str, str]] | None = None,
) -> tuple[str, str]:
    """返回 manual_mode 与 effective_mode。"""
    manual_mode = _normalize_reply_mode(reply_mode)
    if manual_mode in ("light", "qa"):
        return manual_mode, manual_mode
    if _is_light_chat(user_text, should_search_fn=should_search_fn, history=history):
        return manual_mode, "light"
    if _is_qa_query(user_text, should_search_fn=should_search_fn, history=history):
        return manual_mode, "qa"
    return manual_mode, "normal"
