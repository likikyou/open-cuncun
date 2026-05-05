"""聊天历史与统计仓储。"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from cachetools import LRUCache

from ...logger import logger
from ...time_utils import (
    get_local_day_utc_bounds,
    get_relative_local_day_utc_bounds,
    sqlite_utc_to_local_naive,
)
from ._sqlite_common import get_db_cursor
from .sqlite_conversation_repo import get_active_conversation_id, touch_conversation

_history_cache = LRUCache(maxsize=100)
_CONTEXT_AFTER_ID_KEY = "chat_context_after_id"


def _context_after_id_key(conversation_id: str | None = None) -> str:
    if conversation_id:
        return f"{_CONTEXT_AFTER_ID_KEY}:{conversation_id}"
    return _CONTEXT_AFTER_ID_KEY


def _invalidate_history_cache(user_id: str) -> None:
    """使指定用户的历史缓存失效。"""
    keys_to_del = [key for key in _history_cache.keys() if key[0] == user_id]
    for key in keys_to_del:
        del _history_cache[key]


def _get_context_after_id(
    user_id: str,
    *,
    conversation_id: str | None = None,
    cursor=None,
) -> int:
    """读取用户当前上下文边界。"""
    setting_key = _context_after_id_key(conversation_id)
    try:
        if cursor is None:
            with get_db_cursor(commit=False) as managed_cursor:
                managed_cursor.execute(
                    "SELECT setting_value FROM user_settings WHERE user_id = ? AND setting_key = ?",
                    (user_id, setting_key),
                )
                row = managed_cursor.fetchone()
        else:
            cursor.execute(
                "SELECT setting_value FROM user_settings WHERE user_id = ? AND setting_key = ?",
                (user_id, setting_key),
            )
            row = cursor.fetchone()

        if not row and not conversation_id:
            return 0
        if not row and conversation_id:
            return _get_context_after_id(user_id, cursor=cursor)
        if not row:
            return 0

        value = row["setting_value"] if hasattr(row, "keys") else row[0]
        return int(value or 0)
    except Exception as exc:
        logger.error(f"❌ 读取上下文边界失败: {exc}")
        return 0


def _set_context_after_id(
    user_id: str,
    after_id: int,
    *,
    conversation_id: str | None = None,
    cursor=None,
) -> bool:
    """写入用户当前上下文边界。"""
    setting_key = _context_after_id_key(conversation_id)
    try:
        if cursor is None:
            with get_db_cursor(commit=True) as managed_cursor:
                _set_context_after_id(
                    user_id,
                    after_id,
                    conversation_id=conversation_id,
                    cursor=managed_cursor,
                )
            return True

        if after_id > 0:
            cursor.execute(
                """
                INSERT INTO user_settings (user_id, setting_key, setting_value)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, setting_key)
                DO UPDATE SET setting_value = excluded.setting_value
                """,
                (user_id, setting_key, str(after_id)),
            )
        else:
            cursor.execute(
                "DELETE FROM user_settings WHERE user_id = ? AND setting_key = ?",
                (user_id, setting_key),
            )
        return True
    except Exception as exc:
        logger.error(f"❌ 写入上下文边界失败: {exc}")
        return False


def save_message(
    user_id: str,
    role: str,
    content: str,
    tokens: int = 0,
    *,
    conversation_id: str | None = None,
) -> bool:
    """保存一条对话消息。"""
    try:
        conversation_id = conversation_id or get_active_conversation_id(user_id)
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO chat_history (user_id, conversation_id, role, content, tokens_used)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, conversation_id, role, content, tokens),
            )
            touch_conversation(user_id, conversation_id, cursor=cursor)
        _invalidate_history_cache(user_id)
        return True
    except Exception as exc:
        logger.error(f"❌ 数据库保存失败: {exc}")
        return False


def get_last_interaction_time(user_id: str) -> Optional[datetime]:
    """获取用户最后一次交互时间。"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute(
                """
                SELECT timestamp FROM chat_history
                WHERE user_id = ?
                ORDER BY timestamp DESC LIMIT 1
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            if row:
                return sqlite_utc_to_local_naive(row["timestamp"])
    except Exception as exc:
        logger.error(f"获取最后交互时间失败: {exc}")
    return None


def get_recent_history(
    user_id: str,
    limit: int = 10,
    *,
    conversation_id: str | None = None,
) -> List[Dict[str, str]]:
    """获取最近 N 条对话，带 LRU 缓存。"""
    conversation_id = conversation_id or get_active_conversation_id(user_id)
    context_after_id = _get_context_after_id(user_id, conversation_id=conversation_id)
    cache_key = (user_id, conversation_id, limit, context_after_id)
    if cache_key in _history_cache:
        return _history_cache[cache_key]

    try:
        with get_db_cursor(commit=False) as cursor:
            if context_after_id > 0:
                cursor.execute(
                    """
                    SELECT role, content FROM chat_history
                    WHERE user_id = ? AND conversation_id = ? AND id > ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (user_id, conversation_id, context_after_id, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT role, content FROM chat_history
                    WHERE user_id = ? AND conversation_id = ?
                    ORDER BY id DESC LIMIT ?
                    """,
                    (user_id, conversation_id, limit),
                )
            rows = cursor.fetchall()

        history = [{"role": row["role"], "content": row["content"]} for row in reversed(rows)]
        _history_cache[cache_key] = history
        return history
    except Exception as exc:
        logger.error(f"❌ 数据库读取失败: {exc}")
        return []


def get_history_by_day_offset(
    user_id: str,
    day_offset: int,
    limit: int = 24,
    *,
    conversation_id: str | None = None,
) -> List[Dict[str, str]]:
    """读取指定相对日期的原始聊天记录，忽略当前上下文边界。"""
    if not user_id:
        return []

    try:
        conversation_id = conversation_id or get_active_conversation_id(user_id)
        start_utc, end_utc = get_relative_local_day_utc_bounds(day_offset)
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT role, content, timestamp
                FROM chat_history
                WHERE user_id = ?
                  AND conversation_id = ?
                  AND timestamp >= ?
                  AND timestamp < ?
                ORDER BY id DESC LIMIT ?
                """,
                (user_id, conversation_id, start_utc, end_utc, limit),
            )
            rows = cursor.fetchall()

        records: List[Dict[str, str]] = []
        for row in reversed(rows):
            local_dt = sqlite_utc_to_local_naive(row["timestamp"])
            records.append(
                {
                    "role": row["role"],
                    "content": row["content"],
                    "timestamp": row["timestamp"],
                    "local_time": local_dt.strftime("%H:%M"),
                    "local_date": local_dt.strftime("%Y-%m-%d"),
                }
            )
        return records
    except Exception as exc:
        logger.error(f"❌ 读取相对日期聊天记录失败: {exc}")
        return []


def clear_chat_history(
    user_id: str,
    *,
    conversation_id: str | None = None,
    cursor=None,
    invalidate_cache: bool = True,
) -> bool:
    """清空用户聊天上下文，但保留聊天记录。"""
    try:
        conversation_id = conversation_id or get_active_conversation_id(user_id, cursor=cursor)
        if cursor is None:
            with get_db_cursor(commit=True) as managed_cursor:
                managed_cursor.execute(
                    """
                    SELECT COALESCE(MAX(id), 0) FROM chat_history
                    WHERE user_id = ? AND conversation_id = ?
                    """,
                    (user_id, conversation_id),
                )
                max_id = int(managed_cursor.fetchone()[0] or 0)
                if not _set_context_after_id(
                    user_id,
                    max_id,
                    conversation_id=conversation_id,
                    cursor=managed_cursor,
                ):
                    raise RuntimeError("set_context_after_id failed")
        else:
            cursor.execute(
                """
                SELECT COALESCE(MAX(id), 0) FROM chat_history
                WHERE user_id = ? AND conversation_id = ?
                """,
                (user_id, conversation_id),
            )
            max_id = int(cursor.fetchone()[0] or 0)
            if not _set_context_after_id(
                user_id,
                max_id,
                conversation_id=conversation_id,
                cursor=cursor,
            ):
                raise RuntimeError("set_context_after_id failed")

        if invalidate_cache:
            _invalidate_history_cache(user_id)
        return True
    except Exception as exc:
        logger.error(f"❌ 清空上下文失败: {exc}")
        return False


def delete_chat_history(
    user_id: str,
    *,
    conversation_id: str | None = None,
    cursor=None,
    invalidate_cache: bool = True,
) -> bool:
    """彻底删除用户聊天记录。"""
    try:
        if cursor is None:
            with get_db_cursor(commit=True) as managed_cursor:
                if conversation_id:
                    managed_cursor.execute(
                        "DELETE FROM chat_history WHERE user_id = ? AND conversation_id = ?",
                        (user_id, conversation_id),
                    )
                else:
                    managed_cursor.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
                if not _set_context_after_id(
                    user_id,
                    0,
                    conversation_id=conversation_id,
                    cursor=managed_cursor,
                ):
                    raise RuntimeError("clear_context_after_id failed")
        else:
            if conversation_id:
                cursor.execute(
                    "DELETE FROM chat_history WHERE user_id = ? AND conversation_id = ?",
                    (user_id, conversation_id),
                )
            else:
                cursor.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
            if not _set_context_after_id(
                user_id,
                0,
                conversation_id=conversation_id,
                cursor=cursor,
            ):
                raise RuntimeError("clear_context_after_id failed")

        if invalidate_cache:
            _invalidate_history_cache(user_id)
        return True
    except Exception as exc:
        logger.error(f"❌ 删除聊天记录失败: {exc}")
        return False


def get_chat_counts() -> Tuple[int, int]:
    """获取今日与累计对话数。"""
    try:
        today_start_utc, tomorrow_start_utc = get_local_day_utc_bounds()
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) FROM chat_history
                WHERE role = 'user'
                  AND timestamp >= ?
                  AND timestamp < ?
                """,
                (today_start_utc, tomorrow_start_utc),
            )
            today_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM chat_history WHERE role = 'user'")
            total_count = cursor.fetchone()[0]
            return today_count, total_count
    except Exception as exc:
        logger.error(f"❌ 获取对话统计失败: {exc}")
        return 0, 0
