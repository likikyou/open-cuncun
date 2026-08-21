"""用户画像与关系洞察仓储。"""

from __future__ import annotations

from typing import Dict, List, Optional

from ...logger import logger
from ._sqlite_common import get_db_cursor


def upsert_user_profile_fact(
    user_id: str,
    fact: str,
    category: str = "",
    stability: str = "medium",
    confidence: float = 0.7,
    source: str = "",
    source_turn_ids: str = "",
    vector_id: str = "",
    status: str = "active",
) -> Optional[int]:
    """写入或更新用户画像事实。"""
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO user_profile_facts
                (user_id, vector_id, fact, category, stability, confidence, source, source_turn_ids, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, fact) DO UPDATE SET
                    vector_id = excluded.vector_id,
                    category = excluded.category,
                    stability = excluded.stability,
                    confidence = excluded.confidence,
                    source = excluded.source,
                    source_turn_ids = excluded.source_turn_ids,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    vector_id or None,
                    fact,
                    category,
                    stability,
                    max(0.0, min(1.0, confidence)),
                    source,
                    source_turn_ids,
                    status,
                ),
            )
            cursor.execute(
                "SELECT id FROM user_profile_facts WHERE user_id = ? AND fact = ?",
                (user_id, fact),
            )
            row = cursor.fetchone()
            return row["id"] if row else None
    except Exception as exc:
        logger.error(f"❌ 用户画像写入失败: {exc}")
        return None


def upsert_relationship_insight(
    user_id: str,
    insight: str,
    category: str = "",
    stability: str = "medium",
    confidence: float = 0.7,
    source: str = "",
    source_turn_ids: str = "",
    vector_id: str = "",
    status: str = "active",
) -> Optional[int]:
    """写入或更新关系层洞察。"""
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO relationship_insights
                (user_id, vector_id, insight, category, stability, confidence, source, source_turn_ids, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id, insight) DO UPDATE SET
                    vector_id = excluded.vector_id,
                    category = excluded.category,
                    stability = excluded.stability,
                    confidence = excluded.confidence,
                    source = excluded.source,
                    source_turn_ids = excluded.source_turn_ids,
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    user_id,
                    vector_id or None,
                    insight,
                    category,
                    stability,
                    max(0.0, min(1.0, confidence)),
                    source,
                    source_turn_ids,
                    status,
                ),
            )
            cursor.execute(
                "SELECT id FROM relationship_insights WHERE user_id = ? AND insight = ?",
                (user_id, insight),
            )
            row = cursor.fetchone()
            return row["id"] if row else None
    except Exception as exc:
        logger.error(f"❌ 关系洞察写入失败: {exc}")
        return None


def get_active_user_profile_facts(user_id: str, limit: int = 20) -> List[Dict]:
    """获取活跃用户画像。"""
    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT id, user_id, vector_id, fact, category, stability, confidence, source, source_turn_ids, status, created_at, updated_at
                FROM user_profile_facts
                WHERE user_id = ? AND status = 'active'
                ORDER BY confidence DESC, updated_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
    except Exception as exc:
        logger.error(f"❌ 获取用户画像失败: {exc}")
        return []


def get_active_relationship_insights(user_id: str, limit: int = 20) -> List[Dict]:
    """获取活跃关系洞察。"""
    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT id, user_id, vector_id, insight, category, stability, confidence, source, source_turn_ids, status, created_at, updated_at
                FROM relationship_insights
                WHERE user_id = ? AND status = 'active'
                ORDER BY confidence DESC, updated_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
    except Exception as exc:
        logger.error(f"❌ 获取关系洞察失败: {exc}")
        return []


def clear_profile_data(user_id: str, *, cursor=None) -> bool:
    """删除用户画像和关系洞察。"""
    try:
        if cursor is None:
            with get_db_cursor(commit=True) as managed_cursor:
                managed_cursor.execute(
                    "DELETE FROM user_profile_facts WHERE user_id = ?", (user_id,)
                )
                managed_cursor.execute(
                    "DELETE FROM relationship_insights WHERE user_id = ?", (user_id,)
                )
        else:
            cursor.execute("DELETE FROM user_profile_facts WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM relationship_insights WHERE user_id = ?", (user_id,))
        return True
    except Exception as exc:
        logger.error(f"❌ 清空画像数据失败: {exc}")
        return False
