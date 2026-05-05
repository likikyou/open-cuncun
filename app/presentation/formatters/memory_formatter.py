"""记忆看板文案格式化。"""

from __future__ import annotations

_RELATIONSHIP_STAGE_LABELS = {
    1: "初识",
    2: "熟悉中",
    3: "渐渐靠近",
    4: "有点依赖",
    5: "熟识",
    6: "亲近",
    7: "很亲密",
    8: "黏人阶段",
    9: "离不开你",
    10: "绑定级亲密",
}


def build_meter(value: float, length: int = 10) -> str:
    """把 0~1 的数值格式化为块状进度条。"""
    value = max(0.0, min(1.0, value or 0.0))
    filled = round(value * length)
    return "█" * filled + "░" * (length - filled)


def relationship_stage_label(stage: int) -> str:
    """格式化关系阶段展示。"""
    try:
        stage_num = int(stage)
    except (TypeError, ValueError):
        stage_num = 1
    stage_num = max(1, min(10, stage_num))
    return f"{stage_num}/10 · {_RELATIONSHIP_STAGE_LABELS.get(stage_num, '熟识')}"


def trim_memory_preview(text: str, limit: int = 34) -> str:
    """截断单条记忆预览，避免卡片过宽。"""
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def format_memory_state(
    *,
    current_mood: str,
    mood_intensity: float,
    relationship_stage: int,
    total_reflections: int,
) -> str:
    """构建记忆看板的状态摘要。"""
    return (
        f"**当前心情**：{current_mood}  `[{build_meter(mood_intensity)}] {mood_intensity:.0%}`\n"
        f"**关系阶段**：{relationship_stage_label(relationship_stage)}\n"
        f"**累计反思**：`{total_reflections}` 次"
    )


def format_memory_summary(top_memories: list[dict]) -> str:
    """构建高优先级记忆摘要列表。"""
    memory_lines = []
    for idx, memory in enumerate(top_memories, 1):
        importance = float(memory.get("importance", 0) or 0.0)
        strength = float(memory.get("strength", 0) or 0.0)
        preview = trim_memory_preview(memory.get("content", ""))
        memory_lines.append(f"{idx}. `{preview}`\n重要度 {importance:.0%} · 强度 {strength:.0%}")
    return "\n\n".join(memory_lines) if memory_lines else "还没有足够清晰的高优先级记忆。"
