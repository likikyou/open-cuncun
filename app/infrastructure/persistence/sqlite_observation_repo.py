"""实时观察 snapshot 仓储。"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from ...logger import logger
from ._sqlite_common import get_db_cursor

_SNAPSHOT_COLUMNS = (
    "snapshot_version",
    "state_source",
    "routine_slot",
    "routine_label",
    "weather_summary",
    "accident_code",
    "accident_text",
    "mood",
    "mood_intensity",
    "recent_chat_hint",
    "memory_hint",
    "observation_text",
    "media_type",
    "media_status",
    "media_prompt",
    "media_key",
    "generated_by",
    "generated_at",
    "expires_at",
    "updated_reason",
)

_RUNTIME_STATE_COLUMNS = (
    "state_code",
    "state_label",
    "state_priority",
    "scene_hint",
    "state_token",
    "started_at",
    "expires_at",
    "updated_at",
)


def get_presence_snapshot(user_id: str) -> Optional[Dict[str, Any]]:
    """读取指定用户的 observation snapshot。"""
    if not user_id:
        return None

    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT user_id, snapshot_version, state_source, routine_slot, routine_label,
                       weather_summary, accident_code, accident_text, mood, mood_intensity,
                       recent_chat_hint, memory_hint, observation_text,
                       media_type, media_status, media_prompt, media_key,
                       generated_by, generated_at, expires_at, updated_reason
                FROM presence_snapshot
                WHERE user_id = ?
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as exc:
        logger.error(f"❌ 读取 observation snapshot 失败: {exc}")
        return None


def save_presence_snapshot(user_id: str, snapshot: Mapping[str, Any]) -> bool:
    """写入或更新指定用户的 observation snapshot。"""
    if not user_id:
        return False

    values = {column: snapshot.get(column, "") for column in _SNAPSHOT_COLUMNS}
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO presence_snapshot (
                    user_id, snapshot_version, state_source, routine_slot, routine_label,
                    weather_summary, accident_code, accident_text, mood, mood_intensity,
                    recent_chat_hint, memory_hint, observation_text,
                    media_type, media_status, media_prompt, media_key,
                    generated_by, generated_at, expires_at, updated_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    snapshot_version = excluded.snapshot_version,
                    state_source = excluded.state_source,
                    routine_slot = excluded.routine_slot,
                    routine_label = excluded.routine_label,
                    weather_summary = excluded.weather_summary,
                    accident_code = excluded.accident_code,
                    accident_text = excluded.accident_text,
                    mood = excluded.mood,
                    mood_intensity = excluded.mood_intensity,
                    recent_chat_hint = excluded.recent_chat_hint,
                    memory_hint = excluded.memory_hint,
                    observation_text = excluded.observation_text,
                    media_type = excluded.media_type,
                    media_status = excluded.media_status,
                    media_prompt = excluded.media_prompt,
                    media_key = excluded.media_key,
                    generated_by = excluded.generated_by,
                    generated_at = excluded.generated_at,
                    expires_at = excluded.expires_at,
                    updated_reason = excluded.updated_reason
                """,
                (
                    user_id,
                    values["snapshot_version"],
                    values["state_source"],
                    values["routine_slot"],
                    values["routine_label"],
                    values["weather_summary"],
                    values["accident_code"],
                    values["accident_text"],
                    values["mood"],
                    values["mood_intensity"],
                    values["recent_chat_hint"],
                    values["memory_hint"],
                    values["observation_text"],
                    values["media_type"],
                    values["media_status"],
                    values["media_prompt"],
                    values["media_key"],
                    values["generated_by"],
                    values["generated_at"],
                    values["expires_at"],
                    values["updated_reason"],
                ),
            )
        return True
    except Exception as exc:
        logger.error(f"❌ 写入 observation snapshot 失败: {exc}")
        return False


def invalidate_presence_snapshot(user_id: str) -> bool:
    """让指定用户的 observation snapshot 立即过期。"""
    if not user_id:
        return False

    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                UPDATE presence_snapshot
                SET expires_at = CURRENT_TIMESTAMP,
                    updated_reason = 'runtime_state_changed'
                WHERE user_id = ?
                """,
                (user_id,),
            )
        return True
    except Exception as exc:
        logger.warning(f"⚠️ 失效 observation snapshot 失败: {exc}")
        return False


def get_presence_runtime_state(user_id: str) -> Optional[Dict[str, Any]]:
    """读取指定用户的显式运行时观察状态。"""
    if not user_id:
        return None

    try:
        with get_db_cursor(commit=False) as cursor:
            cursor.execute(
                """
                SELECT user_id, state_code, state_label, state_priority,
                       scene_hint, state_token, started_at, expires_at, updated_at
                FROM presence_runtime_state
                WHERE user_id = ?
                """,
                (user_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    except Exception as exc:
        logger.error(f"❌ 读取 observation runtime_state 失败: {exc}")
        return None


def save_presence_runtime_state(user_id: str, runtime_state: Mapping[str, Any]) -> bool:
    """写入或更新指定用户的显式运行时观察状态。"""
    if not user_id:
        return False

    values = {column: runtime_state.get(column, "") for column in _RUNTIME_STATE_COLUMNS}
    try:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute(
                """
                INSERT INTO presence_runtime_state (
                    user_id, state_code, state_label, state_priority,
                    scene_hint, state_token, started_at, expires_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    state_code = excluded.state_code,
                    state_label = excluded.state_label,
                    state_priority = excluded.state_priority,
                    scene_hint = excluded.scene_hint,
                    state_token = excluded.state_token,
                    started_at = excluded.started_at,
                    expires_at = excluded.expires_at,
                    updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    values["state_code"],
                    values["state_label"],
                    values["state_priority"],
                    values["scene_hint"],
                    values["state_token"],
                    values["started_at"],
                    values["expires_at"],
                    values["updated_at"],
                ),
            )
        return True
    except Exception as exc:
        logger.error(f"❌ 写入 observation runtime_state 失败: {exc}")
        return False


def clear_presence_runtime_state(user_id: str, state_token: str | None = None) -> bool:
    """清除指定用户的显式运行时观察状态；带 token 时只清自己的状态。"""
    if not user_id:
        return False

    try:
        with get_db_cursor(commit=True) as cursor:
            if state_token:
                cursor.execute(
                    """
                    DELETE FROM presence_runtime_state
                    WHERE user_id = ? AND state_token = ?
                    """,
                    (user_id, state_token),
                )
            else:
                cursor.execute(
                    "DELETE FROM presence_runtime_state WHERE user_id = ?",
                    (user_id,),
                )
        return True
    except Exception as exc:
        logger.warning(f"⚠️ 清理 observation runtime_state 失败: {exc}")
        return False
