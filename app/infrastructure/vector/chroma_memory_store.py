"""Chroma 记忆向量存储适配器。"""

from __future__ import annotations

from ...logger import logger
from ...retrieval import bio_collection, relationship_collection, user_profile_collection


def delete_bionic_memory_vectors(memory_ids: list[int]) -> bool:
    """删除仿生记忆向量。"""
    if not memory_ids or bio_collection is None:
        return True

    try:
        bio_collection.delete(ids=[f"bionic_{memory_id}" for memory_id in memory_ids])
        return True
    except Exception as exc:
        logger.warning(f"⚠️ reset 时清理 ChromaDB 向量失败: {exc}")
        return False


def delete_user_profile_vectors(user_id: str) -> bool:
    """删除用户画像向量。"""
    if user_profile_collection is None:
        return True

    try:
        user_profile_collection.delete(where={"user_id": user_id})
        return True
    except Exception as exc:
        logger.warning(f"⚠️ reset 时清理 用户画像 向量失败: {exc}")
        return False


def delete_relationship_vectors(user_id: str) -> bool:
    """删除关系洞察向量。"""
    if relationship_collection is None:
        return True

    try:
        relationship_collection.delete(where={"user_id": user_id})
        return True
    except Exception as exc:
        logger.warning(f"⚠️ reset 时清理 关系洞察 向量失败: {exc}")
        return False
