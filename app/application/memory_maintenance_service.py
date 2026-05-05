"""仿生记忆整合与遗忘应用服务。"""

from __future__ import annotations

import json
from datetime import timedelta

from ..config import Config
from ..infrastructure.persistence.sqlite_memory_repo import (
    get_all_active_memories_for_decay,
    get_distinct_user_theme_pairs,
    get_memories_by_user_and_theme,
    mark_memories_consolidated,
    mark_memories_forgotten,
    save_bionic_memory,
    update_memory_strength,
)
from ..domain.memory_rules import (
    calculate_retention,
    clamp_importance,
    select_memories_for_consolidation,
    should_consolidate_memories,
    should_forget_memory,
)
from ..logger import logger
from ..retrieval import bio_collection, get_embedding
from ..time_utils import parse_sqlite_utc, utc_now_naive
from .memory_reflection_service import _call_ai_cheap


def consolidate_memories() -> int:
    """把同主题碎片记忆整合成浓缩记忆。"""
    user_theme_pairs = get_distinct_user_theme_pairs(status="active")
    if not user_theme_pairs:
        logger.info("🧬 整合引擎：暂无需要整合的记忆")
        return 0

    consolidated_count = 0
    for user_id, theme in user_theme_pairs:
        memories = get_memories_by_user_and_theme(user_id, theme, status="active")
        if not should_consolidate_memories(len(memories)):
            continue

        to_merge = select_memories_for_consolidation(memories, limit=10)
        fragments = "\n".join(
            f"- [{memory['emotion']}] {memory['content']} (重要度:{memory['importance']:.1f})"
            for memory in to_merge
        )

        system_prompt = (
            "你是一个记忆整合器。将多条碎片化的记忆合并为一条高度浓缩的长期记忆。\n"
            "要求：\n"
            "1. 保留最关键的事实和情感，删除冗余细节\n"
            "2. 用两三句话概括，第三人称视角\n"
            "3. 严格按以下 JSON 格式输出：\n"
            "{\n"
            '  "content": "整合后的记忆内容",\n'
            '  "emotion": "整体情感基调",\n'
            '  "importance": 0.1到1.0\n'
            "}"
        )
        user_prompt = f"【主题：{theme}】\n以下是 {len(to_merge)} 条碎片记忆：\n{fragments}"

        raw = _call_ai_cheap(system_prompt, user_prompt, max_tokens=200)
        if not raw:
            continue

        try:
            json_str = raw
            if "```" in raw:
                import re

                match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
                if match:
                    json_str = match.group(1)

            data = json.loads(json_str)
            content = data.get("content", "")
            emotion = data.get("emotion", "平静")
            importance = clamp_importance(float(data.get("importance", 0.5)))
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"⚠️ 整合引擎 JSON 解析失败，跳过主题: {theme}")
            continue

        if not content:
            continue

        max_importance = max(memory["importance"] for memory in to_merge)
        importance = max(importance, max_importance)

        new_id = save_bionic_memory(
            user_id=user_id,
            content=content,
            theme=theme,
            emotion=emotion,
            importance=importance,
            memory_type="consolidation",
        )

        if not new_id:
            continue

        if bio_collection is not None:
            try:
                vector = get_embedding(content)
                if vector:
                    bio_collection.add(
                        ids=[f"bionic_{new_id}"],
                        embeddings=[vector],
                        documents=[content],
                        metadatas=[
                            {
                                "memory_id": new_id,
                                "user_id": user_id,
                                "theme": theme,
                                "emotion": emotion,
                                "importance": importance,
                                "source": "bionic_consolidation",
                            }
                        ],
                    )
            except Exception as exc:
                logger.warning(f"⚠️ 整合记忆向量化失败: {exc}")

        merged_ids = [memory["id"] for memory in to_merge]
        mark_memories_consolidated(merged_ids)

        if bio_collection is not None:
            try:
                bio_collection.delete(ids=[f"bionic_{memory_id}" for memory_id in merged_ids])
            except Exception as exc:
                logger.warning(f"⚠️ 整合后清理向量库失败: {exc}")

        consolidated_count += 1
        logger.info(
            f"🧬 记忆整合完成 | user_id={user_id} 主题={theme} "
            f"合并 {len(merged_ids)} 条碎片 → 1 条浓缩记忆"
        )

    logger.info(f"🧬 整合引擎 | 本轮共整合 {consolidated_count} 个主题")
    return consolidated_count


def decay_and_forget() -> dict:
    """对所有活跃记忆执行强度衰减，并标记遗忘项。"""
    memories = get_all_active_memories_for_decay()
    if not memories:
        logger.info("💤 遗忘引擎：暂无活跃记忆需要衰减")
        return {"decayed": 0, "forgotten": 0}

    now = utc_now_naive()
    forget_threshold = Config.MEMORY_FORGET_THRESHOLD
    importance_protect = Config.MEMORY_IMPORTANCE_PROTECT

    decayed_count = 0
    to_forget = []

    for memory in memories:
        try:
            last_recalled = parse_sqlite_utc(memory["last_recalled_at"])
        except (ValueError, TypeError):
            try:
                last_recalled = parse_sqlite_utc(memory["created_at"])
            except (ValueError, TypeError):
                last_recalled = now - timedelta(hours=24)

        hours_elapsed = max((now - last_recalled).total_seconds() / 3600, 0)
        retention = calculate_retention(hours_elapsed, memory["importance"])
        new_strength = memory["strength"] * retention

        update_memory_strength(memory["id"], round(new_strength, 4))
        decayed_count += 1

        if should_forget_memory(
            new_strength,
            memory["importance"],
            forget_threshold,
            importance_protect,
        ):
            to_forget.append(memory["id"])

    if to_forget:
        mark_memories_forgotten(to_forget)
        if bio_collection is not None:
            try:
                bio_collection.delete(ids=[f"bionic_{memory_id}" for memory_id in to_forget])
            except Exception as exc:
                logger.warning(f"⚠️ 清理向量库中遗忘记忆失败: {exc}")

    stats = {"decayed": decayed_count, "forgotten": len(to_forget)}
    logger.info(
        f"💤 遗忘引擎完成 | 衰减 {decayed_count} 条记忆, "
        f"遗忘 {len(to_forget)} 条 (阈值: strength<{forget_threshold}, importance<{importance_protect})"
    )
    return stats
