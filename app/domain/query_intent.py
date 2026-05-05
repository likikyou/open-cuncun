"""查询意图识别。"""

from __future__ import annotations

import os
from typing import Mapping, Sequence

DEFAULT_WEATHER_LOCATION = os.getenv("DEFAULT_WEATHER_LOCATION", "中国北京")


_MEMORY_RECALL_MARKERS = (
    "记得",
    "记不记得",
    "还记得",
    "记忆里",
    "记忆里面",
    "回忆里",
    "回忆一下",
    "想不想得起",
)

_MEMORY_SCOPE_MARKERS = (
    "我",
    "我们",
    "咱们",
    "关于我的",
    "关于我们",
    "和你",
)

_MEMORY_TIMELINE_MARKERS = (
    "昨天",
    "前天",
    "刚刚",
    "刚才",
    "之前",
    "上次",
    "那天",
    "最近",
    "以前",
    "说了什么",
    "聊了什么",
    "提过什么",
    "讲过什么",
    "怎么说的",
    "发生了什么",
)

_MEMORY_DIRECT_PATTERNS = (
    "关于我的记忆",
    "关于我们之间的记忆",
    "你记忆里面有哪些",
    "你记忆里有哪些",
)

_MEMORY_FOLLOWUP_PATTERNS = (
    "那前天呢",
    "前天呢",
    "那昨天呢",
    "昨天呢",
    "那上次呢",
    "上次呢",
    "那天呢",
    "然后呢",
)

_CURRENT_TIME_PATTERNS = (
    "现在几点",
    "几点了",
    "多少点了",
    "现在多少点",
    "现在什么时间",
    "现在是什么时间",
    "当前时间",
    "几点钟",
    "现在几号",
    "今天几号",
    "今天几月几号",
    "现在几月几号",
)

_WEATHER_PATTERNS = (
    "天气",
    "下雨",
    "气温",
    "温度",
    "冷不冷",
    "热不热",
    "会不会冷",
    "会不会热",
)

_AMBIGUOUS_WEATHER_LOCATION_MARKERS = (
    "你那边",
    "你那里",
    "那边",
    "这边",
    "这里",
    "当地",
    "外面",
)

_EXPLICIT_WEATHER_LOCATION_MARKERS = (
    "北京",
    "上海",
    "广州",
    "深圳",
    "杭州",
    "南京",
    "成都",
    "重庆",
    "武汉",
    "长沙",
    "南昌",
)

_PERSONA_PRIVATE_SUBJECT_MARKERS = (
    "你",
)

_PERSONA_PRIVATE_LIFE_MARKERS = (
    "休息",
    "上班",
    "下班",
    "工作",
    "忙吗",
    "在忙",
    "在干嘛",
    "干嘛呢",
    "行程",
    "安排",
    "客户",
    "明星",
    "化妆",
    "跟妆",
    "航班",
    "机票",
    "登机",
    "出差",
    "去哪里",
    "去哪",
    "在哪里",
    "在哪",
    "吃饭了吗",
    "睡了吗",
)

_USER_SELF_LIFE_MARKERS = (
    "我的工作",
    "我工作",
    "我上班",
    "我休息",
    "我今天工作",
    "我明天工作",
    "我最近工作",
    "我今天休息",
    "我明天休息",
)

_TECHNICAL_MEMORY_MARKERS = (
    "记忆库",
    "知识库",
    "向量",
    "embedding",
    "vector",
    "api",
    "接口",
    "代码",
    "bug",
    "报错",
    "prompt",
)

_RELATIVE_DAY_MARKERS = (
    (3, ("大前天",)),
    (2, ("前天",)),
    (1, ("昨天",)),
    (0, ("今天", "刚刚", "刚才")),
)


def _get_last_user_message(history: Sequence[Mapping[str, str]] | None) -> str:
    if not history:
        return ""
    for item in reversed(history):
        if (item.get("role") or "").strip() == "user":
            return (item.get("content") or "").strip()
    return ""


def _find_recent_memory_recall_reference(history: Sequence[Mapping[str, str]] | None) -> str:
    if not history:
        return ""
    for item in reversed(history):
        if (item.get("role") or "").strip() != "user":
            continue
        content = (item.get("content") or "").strip()
        if _is_direct_memory_recall_query(content):
            return content
    return ""


def _contains_any(text: str, markers: Sequence[str]) -> bool:
    return any(marker in text for marker in markers)


def _is_direct_memory_recall_query(text: str) -> bool:
    if not text:
        return False
    lowered = text.lower()
    if any(marker.lower() in lowered for marker in _TECHNICAL_MEMORY_MARKERS):
        return False

    if _contains_any(text, _MEMORY_DIRECT_PATTERNS):
        return True

    has_recall_marker = _contains_any(text, _MEMORY_RECALL_MARKERS)
    has_scope_marker = _contains_any(text, _MEMORY_SCOPE_MARKERS)
    has_timeline_marker = _contains_any(text, _MEMORY_TIMELINE_MARKERS)
    return has_recall_marker and (has_scope_marker or has_timeline_marker)


def _extract_relative_day_offset(text: str) -> int | None:
    if not text:
        return None
    for day_offset, markers in _RELATIVE_DAY_MARKERS:
        if _contains_any(text, markers):
            return day_offset
    return None


def is_memory_recall_query(
    user_text: str,
    history: Sequence[Mapping[str, str]] | None = None,
) -> bool:
    """是否是在追问双方对话/个人相关记忆。"""
    text = (user_text or "").strip()
    if not text:
        return False

    if _is_direct_memory_recall_query(text):
        return True

    last_user_text = _find_recent_memory_recall_reference(history)
    if not last_user_text:
        return False

    return _extract_relative_day_offset(text) is not None or _contains_any(
        text, _MEMORY_FOLLOWUP_PATTERNS
    )


def get_memory_recall_day_offset(
    user_text: str,
    history: Sequence[Mapping[str, str]] | None = None,
) -> int | None:
    """提取回忆问题对应的相对日期偏移量。"""
    text = (user_text or "").strip()
    if not is_memory_recall_query(text, history=history):
        return None

    day_offset = _extract_relative_day_offset(text)
    if day_offset is not None:
        return day_offset

    last_user_text = _find_recent_memory_recall_reference(history)
    return _extract_relative_day_offset(last_user_text)


def is_current_time_query(user_text: str) -> bool:
    """是否是在询问当前本地时间/日期。"""
    text = (user_text or "").strip()
    if not text:
        return False
    return any(pattern in text for pattern in _CURRENT_TIME_PATTERNS)


def is_weather_query(user_text: str) -> bool:
    """是否是在询问天气、气温或冷暖。"""
    text = (user_text or "").strip()
    if not text:
        return False
    return any(pattern in text for pattern in _WEATHER_PATTERNS)


def _has_explicit_weather_location(text: str) -> bool:
    if any(marker in text for marker in _EXPLICIT_WEATHER_LOCATION_MARKERS):
        return True
    if any(marker in text for marker in _AMBIGUOUS_WEATHER_LOCATION_MARKERS):
        return False
    weather_idx = text.find("天气")
    if weather_idx <= 0:
        return False
    prefix = text[:weather_idx]
    for marker in _AMBIGUOUS_WEATHER_LOCATION_MARKERS:
        prefix = prefix.replace(marker, "")
    prefix = prefix.strip(" ，,。？！?!啊呀呢么吗今天明天现在当前")
    return len(prefix) >= 2


def _recent_assistant_has_private_life_claim(
    history: Sequence[Mapping[str, str]] | None,
) -> bool:
    if not history:
        return False
    for item in reversed(history[-6:]):
        if (item.get("role") or "").strip() != "assistant":
            continue
        content = item.get("content") or ""
        if any(marker in content for marker in _PERSONA_PRIVATE_LIFE_MARKERS):
            return True
    return False


def normalize_weather_query(user_text: str) -> str:
    """天气问句无明确地点时，默认查询配置的默认位置。"""
    text = (user_text or "").strip()
    if not is_weather_query(text):
        return text
    if _has_explicit_weather_location(text):
        return text
    return f"{DEFAULT_WEATHER_LOCATION}天气 {text}".strip()


def is_persona_private_life_query(
    user_text: str,
    history: Sequence[Mapping[str, str]] | None = None,
) -> bool:
    """是否是在问助手自己的私人生活、工作、客户或行程。"""
    text = (user_text or "").strip()
    if not text:
        return False
    if is_weather_query(text):
        return False
    if any(marker in text for marker in _USER_SELF_LIFE_MARKERS):
        return False

    has_subject = any(marker in text for marker in _PERSONA_PRIVATE_SUBJECT_MARKERS)
    has_private_marker = any(marker in text for marker in _PERSONA_PRIVATE_LIFE_MARKERS)
    if has_private_marker and _recent_assistant_has_private_life_claim(history):
        return True
    return has_subject and has_private_marker
