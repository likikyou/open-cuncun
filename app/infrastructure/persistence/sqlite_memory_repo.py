"""仿生记忆与运行时状态仓储。"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from ...logger import logger
from ._sqlite_common import get_db_cursor


def save_bionic_memory(
    user_id: str,
    content: str,
    theme: str = "",
    emotion: str = "",
    importance: float = 0.5,
    memory_type: str = "reflection",
) -> Optional[int]:
    """存入一条仿生记忆。"""
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO bionic_memories
                (user_id, memory_type, content, theme, emotion, importance)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, memory_type, content, theme, emotion, importance),
            )
            return cursor.lastrowid
    except Exception as exc:
        logger.error(f"❌ 仿生记忆存储失败: {exc}")
        return None


def get_active_memories(user_id: str, limit: int = 20) -> List[Dict]:
    """获取用户活跃记忆。"""
    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT id, content, theme, emotion, importance, strength,
                       recall_count, memory_type, created_at, last_recalled_at
                FROM bionic_memories
                WHERE user_id = ? AND status = 'active'
                ORDER BY strength DESC, importance DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
    except Exception as exc:
        logger.error(f"❌ 获取活跃记忆失败: {exc}")
        return []


def get_memories_by_theme(theme: str, status: str = "active") -> List[Dict]:
    """按主题获取记忆。"""
    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT id, user_id, content, theme, emotion, importance,
                       strength, recall_count, created_at
                FROM bionic_memories
                WHERE theme = ? AND status = ?
                ORDER BY created_at ASC
                """,
                (theme, status),
            )
            return [dict(row) for row in cursor.fetchall()]
    except Exception as exc:
        logger.error(f"❌ 按主题获取记忆失败: {exc}")
        return []


def get_memories_by_user_and_theme(user_id: str, theme: str, status: str = "active") -> List[Dict]:
    """按用户和主题获取记忆。"""
    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT id, user_id, content, theme, emotion, importance,
                       strength, recall_count, created_at
                FROM bionic_memories
                WHERE user_id = ? AND theme = ? AND status = ?
                ORDER BY created_at ASC
                """,
                (user_id, theme, status),
            )
            return [dict(row) for row in cursor.fetchall()]
    except Exception as exc:
        logger.error(f"❌ 按用户和主题获取记忆失败: {exc}")
        return []


def get_distinct_themes(status: str = "active") -> List[str]:
    """获取活跃主题列表。"""
    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT DISTINCT theme FROM bionic_memories
                WHERE status = ? AND theme != ''
                """,
                (status,),
            )
            return [row["theme"] for row in cursor.fetchall()]
    except Exception as exc:
        logger.error(f"❌ 获取主题列表失败: {exc}")
        return []


def get_distinct_user_theme_pairs(status: str = "active") -> List[Tuple[str, str]]:
    """获取去重用户-主题组合。"""
    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT DISTINCT user_id, theme FROM bionic_memories
                WHERE status = ? AND theme != ''
                """,
                (status,),
            )
            rows = cursor.fetchall()
            return [(row["user_id"], row["theme"]) for row in rows]
    except Exception as exc:
        logger.error(f"❌ 获取用户主题组合失败: {exc}")
        return []


def update_memory_strength(memory_id: int, new_strength: float) -> bool:
    """更新记忆强度。"""
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                "UPDATE bionic_memories SET strength = ? WHERE id = ?",
                (new_strength, memory_id),
            )
        return True
    except Exception as exc:
        logger.error(f"❌ 更新记忆强度失败: {exc}")
        return False


def boost_memory_recall(memory_id: int) -> bool:
    """记忆唤起加固。"""
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE bionic_memories
                SET recall_count = recall_count + 1,
                    strength = MIN(strength + 0.3, 1.0),
                    last_recalled_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (memory_id,),
            )
        return True
    except Exception as exc:
        logger.error(f"❌ 记忆唤起加强失败: {exc}")
        return False


def mark_memories_consolidated(memory_ids: List[int]) -> bool:
    """标记记忆已整合。"""
    if not memory_ids:
        return True
    try:
        placeholders = ",".join(["?" for _ in memory_ids])
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                f"UPDATE bionic_memories SET status = 'consolidated' WHERE id IN ({placeholders})",
                memory_ids,
            )
        return True
    except Exception as exc:
        logger.error(f"❌ 标记记忆已整合失败: {exc}")
        return False


def mark_memories_forgotten(memory_ids: List[int]) -> bool:
    """标记记忆已遗忘。"""
    if not memory_ids:
        return True
    try:
        placeholders = ",".join(["?" for _ in memory_ids])
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                f"UPDATE bionic_memories SET status = 'forgotten' WHERE id IN ({placeholders})",
                memory_ids,
            )
        return True
    except Exception as exc:
        logger.error(f"❌ 标记记忆已遗忘失败: {exc}")
        return False


def mark_user_memories_forgotten(user_id: str, memory_ids: List[int]) -> int:
    """仅将指定用户的活跃记忆标记为已遗忘，返回实际影响行数。"""
    if not user_id or not memory_ids:
        return 0
    try:
        placeholders = ",".join(["?" for _ in memory_ids])
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                f"""
                UPDATE bionic_memories
                SET status = 'forgotten'
                WHERE user_id = ? AND status = 'active' AND id IN ({placeholders})
                """,
                [user_id, *memory_ids],
            )
            return cursor.rowcount
    except Exception as exc:
        logger.error(f"❌ 标记用户记忆已遗忘失败: {exc}")
        return 0


def get_all_active_memories_for_decay() -> List[Dict]:
    """获取全部活跃记忆，用于衰减。"""
    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT id, importance, strength, last_recalled_at, created_at
                FROM bionic_memories
                WHERE status = 'active'
                """
            )
            return [dict(row) for row in cursor.fetchall()]
    except Exception as exc:
        logger.error(f"❌ 获取衰减记忆列表失败: {exc}")
        return []


def get_all_memory_ids_for_user(user_id: str) -> List[int]:
    """获取用户全部仿生记忆 ID。"""
    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute("SELECT id FROM bionic_memories WHERE user_id = ?", (user_id,))
            return [row["id"] for row in cursor.fetchall()]
    except Exception as exc:
        logger.error(f"❌ 获取用户记忆ID列表失败: {exc}")
        return []


def get_memory_stats(user_id: str) -> Dict:
    """获取用户记忆统计。"""
    try:
        with get_db_cursor(commit=False) as cursor:
            stats = {}
            for status in ["active", "consolidated", "forgotten"]:
                cursor.execute(
                    "SELECT COUNT(*) FROM bionic_memories WHERE user_id = ? AND status = ?",
                    (user_id, status),
                )
                stats[status] = cursor.fetchone()[0]

            cursor.execute(
                "SELECT AVG(strength) FROM bionic_memories WHERE user_id = ? AND status = 'active'",
                (user_id,),
            )
            avg = cursor.fetchone()[0]
            stats["avg_strength"] = round(avg, 2) if avg else 0.0

            cursor.execute(
                """
                SELECT content, importance, strength FROM bionic_memories
                WHERE user_id = ? AND status = 'active'
                ORDER BY importance DESC LIMIT 3
                """,
                (user_id,),
            )
            stats["top_memories"] = [dict(row) for row in cursor.fetchall()]
            return stats
    except Exception as exc:
        logger.error(f"❌ 获取记忆统计失败: {exc}")
        return {}


def get_bionic_state(user_id: str) -> Optional[Dict]:
    """获取用户运行时状态。"""
    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT current_mood, mood_intensity, relationship_stage,
                       last_mood_updated_at, last_interaction_at, total_reflections
                FROM bionic_state WHERE user_id = ?
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            if row:
                return {
                    "current_mood": row[0],
                    "mood_intensity": row[1],
                    "relationship_stage": row[2],
                    "last_mood_updated_at": row[3],
                    "last_interaction_at": row[4],
                    "total_reflections": row[5],
                }
    except Exception as exc:
        logger.warning(f"⚠️ 获取仿生状态失败: {exc}")
    return None


def init_bionic_state(user_id: str) -> None:
    """初始化运行时状态。"""
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("INSERT OR IGNORE INTO bionic_state (user_id) VALUES (?)", (user_id,))
    except Exception as exc:
        logger.warning(f"⚠️ 初始化仿生状态失败: {exc}")


def update_bionic_mood(user_id: str, mood: str, intensity: float = 0.5) -> None:
    """更新当前情绪。"""
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE bionic_state
                SET current_mood = ?, mood_intensity = ?,
                    last_mood_updated_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (mood, max(0.0, min(1.0, intensity)), user_id),
            )
    except Exception as exc:
        logger.warning(f"⚠️ 更新仿生情绪失败: {exc}")


def bump_relationship_stage(user_id: str, delta: int = 0) -> int:
    """调整关系阶段并返回新值。"""
    new_stage = 1
    try:
        with get_db_cursor(commit=True) as cursor:
            if delta != 0:
                cursor.execute(
                    """
                    UPDATE bionic_state
                    SET relationship_stage = MIN(10, MAX(1, relationship_stage + ?)),
                        last_interaction_at = CURRENT_TIMESTAMP
                    WHERE user_id = ?
                    """,
                    (delta, user_id),
                )
            cursor.execute(
                "SELECT relationship_stage FROM bionic_state WHERE user_id = ?", (user_id,)
            )
            row = cursor.fetchone()
            if row:
                new_stage = row[0]
    except Exception as exc:
        logger.warning(f"⚠️ 更新关系阶段失败: {exc}")
    return new_stage


def increment_reflection_count(user_id: str) -> None:
    """反思计数 +1。"""
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE bionic_state
                SET total_reflections = total_reflections + 1,
                    last_interaction_at = CURRENT_TIMESTAMP
                WHERE user_id = ?
                """,
                (user_id,),
            )
    except Exception as exc:
        logger.warning(f"⚠️ 反思计数失败: {exc}")


def clear_bionic_data(user_id: str, *, cursor=None) -> bool:
    """删除用户仿生记忆与状态。"""
    try:
        if cursor is None:
            with get_db_cursor(commit=True) as managed_cursor:
                managed_cursor.execute("DELETE FROM bionic_memories WHERE user_id = ?", (user_id,))
                managed_cursor.execute("DELETE FROM bionic_state WHERE user_id = ?", (user_id,))
        else:
            cursor.execute("DELETE FROM bionic_memories WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM bionic_state WHERE user_id = ?", (user_id,))
        return True
    except Exception as exc:
        logger.error(f"❌ 清空仿生记忆失败: {exc}")
        return False
