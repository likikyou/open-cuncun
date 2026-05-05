"""重置与清理服务。"""

from __future__ import annotations

from ..infrastructure.persistence._sqlite_common import get_db_cursor
from ..infrastructure.persistence.sqlite_conversation_repo import delete_conversations
from ..infrastructure.persistence.sqlite_history_repo import (
    _invalidate_history_cache,
    clear_chat_history,
    delete_chat_history,
)
from ..infrastructure.persistence.sqlite_memory_repo import (
    clear_bionic_data,
    get_all_memory_ids_for_user,
)
from ..infrastructure.persistence.sqlite_profile_repo import clear_profile_data
from ..infrastructure.vector.chroma_memory_store import (
    delete_bionic_memory_vectors,
    delete_relationship_vectors,
    delete_user_profile_vectors,
)
from ..logger import logger


def clear_user_history(user_id: str) -> bool:
    """彻底清空用户聊天、仿生记忆和画像数据。"""
    try:
        memory_ids = get_all_memory_ids_for_user(user_id)

        delete_bionic_memory_vectors(memory_ids)
        delete_user_profile_vectors(user_id)
        delete_relationship_vectors(user_id)

        with get_db_cursor(commit=True) as cursor:
            if not delete_chat_history(user_id, cursor=cursor, invalidate_cache=False):
                raise RuntimeError("delete_chat_history failed")
            if not delete_conversations(user_id, cursor=cursor):
                raise RuntimeError("delete_conversations failed")
            if not clear_bionic_data(user_id, cursor=cursor):
                raise RuntimeError("clear_bionic_data failed")
            if not clear_profile_data(user_id, cursor=cursor):
                raise RuntimeError("clear_profile_data failed")

        _invalidate_history_cache(user_id)
        logger.info(f"🧹 用户 {user_id} 的历史记忆和仿生状态已清空")
        return True
    except Exception as exc:
        logger.error(f"❌ 清空记忆失败: {exc}")
        return False


def clear_chat_context(user_id: str) -> bool:
    """仅清空当前聊天上下文，不影响长期记忆与画像。"""
    if not clear_chat_history(user_id):
        return False

    logger.info(f"🧼 用户 {user_id} 的上下文对话已清空")
    return True
