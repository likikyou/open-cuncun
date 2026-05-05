"""仿生记忆领域规则。"""

from __future__ import annotations

import math
from typing import Sequence

_POSITIVE_EMOTIONS = {"开心", "感动", "撒娇", "思念"}
_NEGATIVE_EMOTIONS = {"难过", "愤怒", "焦虑"}

_SHARED_EXPERIENCE_MARKERS = (
    "我们",
    "咱们",
    "一起",
    "见面",
    "见你",
    "见我",
    "陪你",
    "陪我",
    "吃饭",
    "吃火锅",
    "吃面",
    "玩玩",
    "去玩",
    "一起玩",
    "密室",
    "看电影",
    "旅行",
    "散步",
    "纪念",
    "拍照",
    "约会",
)

_ASSISTANT_PRIVATE_CLAIM_MARKERS = (
    "舒淇",
    "影后",
    "明星",
    "客户",
    "经纪人",
    "剧本",
    "剧组",
    "综艺",
    "跟妆",
    "片单",
    "红毯",
    "电影节",
    "北京",
    "上海",
    "航班",
    "机票",
    "登机牌",
    "直播间",
    "通告",
    "行程",
    "楼下",
    "奶茶店",
    "灯柱",
    "雨夜",
)

_AFFECTION_MARKERS = ("想你", "爱你", "抱抱", "亲亲", "mua", "么么", "喜欢你")

_USER_OWNED_FACT_MARKERS = (
    "我在",
    "我去",
    "我要去",
    "我今天去",
    "我明天去",
    "我刚到",
    "我出差",
    "我的机票",
    "我的航班",
    "用户在",
    "用户去",
    "用户要去",
    "用户今天去",
    "用户明天去",
    "用户刚到",
    "用户出差",
    "用户的机票",
    "用户的航班",
)

_ASSISTANT_SELF_MARKERS = ("她",)


def clamp_importance(importance: float) -> float:
    """把重要度稳定在合法区间。"""
    return max(0.1, min(1.0, float(importance)))


def is_shared_experience_text(text: str) -> bool:
    """用户明确提到双方共同经历、约定或纪念场景。"""
    normalized = text or ""
    return any(marker in normalized for marker in _SHARED_EXPERIENCE_MARKERS)


def _is_user_owned_private_fact(text: str) -> bool:
    return any(marker in text for marker in _USER_OWNED_FACT_MARKERS) and any(
        marker in text for marker in _ASSISTANT_PRIVATE_CLAIM_MARKERS
    )


def classify_reflection_scope(
    user_text: str,
    assistant_reply: str,
    content: str = "",
) -> str:
    """
    判断一轮反思应该怎样进入记忆。

    shared_experience: 用户明确提到双方一起吃饭、玩、见面、约会等，值得长期保留。
    assistant_private_claim: 主要来自助手回复里的客户、明星、私人行程等剧情，不应固化。
    relationship_moment/user_fact: 可作为普通仿生记忆保留。
    """
    user_text = user_text or ""
    assistant_reply = assistant_reply or ""
    content = content or ""

    assistant_has_private_claim = any(
        marker in assistant_reply or marker in content for marker in _ASSISTANT_PRIVATE_CLAIM_MARKERS
    )
    user_mentions_private_claim = any(
        marker in user_text for marker in _ASSISTANT_PRIVATE_CLAIM_MARKERS
    )
    if assistant_has_private_claim and not user_mentions_private_claim:
        return "assistant_private_claim"

    if is_shared_experience_text(user_text):
        return "shared_experience"

    if _is_user_owned_private_fact(user_text):
        return "user_fact"

    if assistant_has_private_claim:
        return "assistant_private_claim"

    combined = f"{user_text}\n{assistant_reply}\n{content}"
    if any(marker in combined for marker in _AFFECTION_MARKERS):
        return "relationship_moment"
    if user_text.strip():
        return "user_fact"
    return "ephemeral"


def should_save_reflection_scope(scope: str) -> bool:
    """是否写入可检索仿生记忆。"""
    return scope in {"shared_experience", "relationship_moment", "user_fact"}


def should_include_memory_in_context(query_text: str, memory_text: str) -> bool:
    """旧记忆注入前再过滤一次，避免历史临场剧情继续污染上下文。"""
    memory_text = memory_text or ""
    if not memory_text:
        return False
    if is_shared_experience_text(memory_text) or _is_user_owned_private_fact(memory_text):
        return True
    has_assistant_self = any(marker in memory_text for marker in _ASSISTANT_SELF_MARKERS)
    has_private_claim = any(marker in memory_text for marker in _ASSISTANT_PRIVATE_CLAIM_MARKERS)
    if has_assistant_self and has_private_claim:
        return False
    return classify_reflection_scope(query_text, "", memory_text) != "assistant_private_claim"


def adjust_importance_for_memory_scope(importance: float, scope: str) -> float:
    """共同经历应更稳定；临场私人剧情不应被强化。"""
    importance = clamp_importance(importance)
    if scope == "shared_experience":
        return max(importance, 0.75)
    if scope == "assistant_private_claim":
        return min(importance, 0.2)
    return importance


def calculate_retention(hours_since_recall: float, importance: float) -> float:
    """计算记忆保留率。"""
    lambda_val = max(importance, 0.1) * 720
    return math.exp(-hours_since_recall / lambda_val)


def should_consolidate_memories(memories_count: int) -> bool:
    """同主题至少 3 条碎片才值得整合。"""
    return memories_count >= 3


def select_memories_for_consolidation(memories: Sequence[dict], limit: int = 10) -> list[dict]:
    """选择本轮进入整合的记忆。"""
    return list(memories[:limit])


def get_relationship_stage_delta(emotion: str, importance: float) -> int:
    """根据情绪和重要度计算关系阶段变化。"""
    if emotion in _POSITIVE_EMOTIONS:
        return 1
    if emotion in _NEGATIVE_EMOTIONS and importance >= 0.5:
        return -1
    return 0


def get_mood_intensity(emotion: str, importance: float) -> float:
    """根据情绪类型计算运行时情绪强度。"""
    if emotion in _POSITIVE_EMOTIONS:
        return importance
    return 0.5


def should_forget_memory(
    new_strength: float,
    importance: float,
    forget_threshold: float,
    importance_protect: float,
) -> bool:
    """判断记忆是否达到遗忘条件。"""
    return new_strength < forget_threshold and importance < importance_protect


def describe_runtime_mood(mood: str, intensity: float) -> str:
    """把运行时情绪转换成自然语言。"""
    if intensity >= 0.8:
        return f"强烈{mood}"
    if intensity >= 0.5:
        return mood
    return f"有点{mood}"


def describe_relationship_stage(stage: int) -> str:
    """把关系阶段转换成自然语言。"""
    if stage <= 2:
        return "初识"
    if stage <= 4:
        return "认识"
    if stage <= 6:
        return "熟识"
    if stage <= 8:
        return "亲近"
    return "亲密"
