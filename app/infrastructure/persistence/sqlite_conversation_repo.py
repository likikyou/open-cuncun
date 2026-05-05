"""多会话仓储。"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from ...logger import logger
from ._sqlite_common import get_db_cursor

ACTIVE_CONVERSATION_ID_KEY = "active_conversation_id"
DEFAULT_CONVERSATION_TITLE = "日常聊天"


def _default_conversation_id(user_id: str) -> str:
    return f"default:{user_id}"


def get_default_conversation_id(user_id: str) -> str:
    return _default_conversation_id(user_id)


def _row_to_dict(row) -> dict[str, Any]:
    return dict(row) if row else {}


def _clip_title(title: str, default: str = "新对话") -> str:
    compact = " ".join((title or "").strip().split())
    if not compact:
        return default
    return compact[:40]


def _get_setting(user_id: str, key: str, *, cursor) -> str:
    cursor.execute(
        "SELECT setting_value FROM user_settings WHERE user_id = ? AND setting_key = ?",
        (user_id, key),
    )
    row = cursor.fetchone()
    return (row["setting_value"] if row else "") or ""


def _set_setting(user_id: str, key: str, value: str, *, cursor) -> None:
    cursor.execute(
        """
        INSERT INTO user_settings (user_id, setting_key, setting_value)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id, setting_key)
        DO UPDATE SET setting_value = excluded.setting_value
        """,
        (user_id, key, value),
    )


def ensure_default_conversation(user_id: str, *, cursor=None) -> dict[str, Any]:
    """确保用户拥有默认日常会话。"""
    conversation_id = _default_conversation_id(user_id)
    try:
        if cursor is None:
            with get_db_cursor(commit=True) as managed_cursor:
                return ensure_default_conversation(user_id, cursor=managed_cursor)

        cursor.execute(
            """
            INSERT OR IGNORE INTO conversations (id, user_id, title, mode)
            VALUES (?, ?, ?, 'normal')
            """,
            (conversation_id, user_id, DEFAULT_CONVERSATION_TITLE),
        )
        cursor.execute(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
            (conversation_id, user_id),
        )
        return _row_to_dict(cursor.fetchone())
    except Exception as exc:
        logger.error(f"❌ 确保默认会话失败: {exc}")
        return {}


def get_conversation(user_id: str, conversation_id: str, *, cursor=None) -> dict[str, Any]:
    """读取指定会话。"""
    if not user_id or not conversation_id:
        return {}
    try:
        if cursor is None:
            with get_db_cursor(commit=False) as managed_cursor:
                return get_conversation(user_id, conversation_id, cursor=managed_cursor)

        cursor.execute(
            "SELECT * FROM conversations WHERE id = ? AND user_id = ? AND archived_at IS NULL",
            (conversation_id, user_id),
        )
        return _row_to_dict(cursor.fetchone())
    except Exception as exc:
        logger.error(f"❌ 读取会话失败: {exc}")
        return {}


def get_active_conversation(user_id: str, *, cursor=None) -> dict[str, Any]:
    """读取用户当前活跃会话；不存在时回到默认日常会话。"""
    if not user_id:
        return {}
    try:
        if cursor is None:
            with get_db_cursor(commit=True) as managed_cursor:
                return get_active_conversation(user_id, cursor=managed_cursor)

        active_id = _get_setting(user_id, ACTIVE_CONVERSATION_ID_KEY, cursor=cursor)
        if active_id:
            active = get_conversation(user_id, active_id, cursor=cursor)
            if active:
                return active

        default = ensure_default_conversation(user_id, cursor=cursor)
        if default:
            _set_setting(user_id, ACTIVE_CONVERSATION_ID_KEY, default["id"], cursor=cursor)
        return default
    except Exception as exc:
        logger.error(f"❌ 读取当前会话失败: {exc}")
        return {}


def get_active_conversation_id(user_id: str, *, cursor=None) -> str:
    conversation = get_active_conversation(user_id, cursor=cursor)
    return str(conversation.get("id") or _default_conversation_id(user_id))


def create_conversation(
    user_id: str,
    title: str = "",
    *,
    mode: str = "normal",
    summary: str = "",
    activate: bool = True,
) -> dict[str, Any]:
    """创建新会话，默认立即切换过去。"""
    conversation_id = f"conv_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:8]}"
    title = _clip_title(title)
    normalized_mode = mode if mode in {"normal", "qa", "story"} else "normal"
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO conversations (id, user_id, title, mode, summary)
                VALUES (?, ?, ?, ?, ?)
                """,
                (conversation_id, user_id, title, normalized_mode, summary or ""),
            )
            if activate:
                _set_setting(user_id, ACTIVE_CONVERSATION_ID_KEY, conversation_id, cursor=cursor)
            cursor.execute(
                "SELECT * FROM conversations WHERE id = ? AND user_id = ?",
                (conversation_id, user_id),
            )
            return _row_to_dict(cursor.fetchone())
    except Exception as exc:
        logger.error(f"❌ 创建会话失败: {exc}")
        return {}


def list_conversations(
    user_id: str,
    *,
    limit: int = 8,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """列出用户会话，按最近更新时间倒序。"""
    try:
        with get_db_cursor(commit=True) as cursor:
            ensure_default_conversation(user_id, cursor=cursor)
            if include_archived:
                cursor.execute(
                    """
                    SELECT c.*,
                           COUNT(h.id) AS message_count,
                           MAX(h.timestamp) AS last_message_at
                    FROM conversations c
                    LEFT JOIN chat_history h
                      ON h.user_id = c.user_id AND h.conversation_id = c.id
                    WHERE c.user_id = ?
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                )
            else:
                cursor.execute(
                    """
                    SELECT c.*,
                           COUNT(h.id) AS message_count,
                           MAX(h.timestamp) AS last_message_at
                    FROM conversations c
                    LEFT JOIN chat_history h
                      ON h.user_id = c.user_id AND h.conversation_id = c.id
                    WHERE c.user_id = ? AND c.archived_at IS NULL
                    GROUP BY c.id
                    ORDER BY c.updated_at DESC
                    LIMIT ?
                    """,
                    (user_id, limit),
                )
            return [_row_to_dict(row) for row in cursor.fetchall()]
    except Exception as exc:
        logger.error(f"❌ 列出会话失败: {exc}")
        return []


def set_active_conversation(user_id: str, conversation_id: str) -> dict[str, Any]:
    """切换当前活跃会话。"""
    try:
        with get_db_cursor(commit=True) as cursor:
            conversation = get_conversation(user_id, conversation_id, cursor=cursor)
            if not conversation:
                return {}
            _set_setting(user_id, ACTIVE_CONVERSATION_ID_KEY, conversation_id, cursor=cursor)
            return conversation
    except Exception as exc:
        logger.error(f"❌ 切换会话失败: {exc}")
        return {}


def rename_conversation(user_id: str, conversation_id: str, title: str) -> dict[str, Any]:
    """重命名会话。"""
    title = _clip_title(title)
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE conversations
                SET title = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND user_id = ? AND archived_at IS NULL
                """,
                (title, conversation_id, user_id),
            )
            return get_conversation(user_id, conversation_id, cursor=cursor)
    except Exception as exc:
        logger.error(f"❌ 重命名会话失败: {exc}")
        return {}


def update_conversation_mode(
    user_id: str,
    conversation_id: str,
    *,
    mode: str,
    summary: str | None = None,
) -> dict[str, Any]:
    """更新会话模式和可选摘要/剧情设定。"""
    normalized_mode = mode if mode in {"normal", "qa", "story"} else "normal"
    try:
        with get_db_cursor(commit=True) as cursor:
            if summary is None:
                cursor.execute(
                    """
                    UPDATE conversations
                    SET mode = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND user_id = ? AND archived_at IS NULL
                    """,
                    (normalized_mode, conversation_id, user_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE conversations
                    SET mode = ?, summary = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND user_id = ? AND archived_at IS NULL
                    """,
                    (normalized_mode, summary, conversation_id, user_id),
                )
            return get_conversation(user_id, conversation_id, cursor=cursor)
    except Exception as exc:
        logger.error(f"❌ 更新会话模式失败: {exc}")
        return {}


def touch_conversation(user_id: str, conversation_id: str, *, cursor=None) -> None:
    """刷新会话更新时间。"""
    if not user_id or not conversation_id:
        return
    try:
        if cursor is None:
            with get_db_cursor(commit=True) as managed_cursor:
                touch_conversation(user_id, conversation_id, cursor=managed_cursor)
            return
        cursor.execute(
            """
            UPDATE conversations
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (conversation_id, user_id),
        )
    except Exception as exc:
        logger.error(f"❌ 刷新会话时间失败: {exc}")


def delete_conversations(user_id: str, *, cursor=None) -> bool:
    """删除用户所有会话元数据，用于 /reset。"""
    try:
        if cursor is None:
            with get_db_cursor(commit=True) as managed_cursor:
                return delete_conversations(user_id, cursor=managed_cursor)
        cursor.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        cursor.execute(
            "DELETE FROM user_settings WHERE user_id = ? AND setting_key = ?",
            (user_id, ACTIVE_CONVERSATION_ID_KEY),
        )
        cursor.execute(
            "DELETE FROM user_settings WHERE user_id = ? AND setting_key LIKE ?",
            (user_id, "chat_context_after_id:%"),
        )
        return True
    except Exception as exc:
        logger.error(f"❌ 删除会话元数据失败: {exc}")
        return False
