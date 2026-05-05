"""实时观察媒体任务占位服务。

第一阶段只搭状态流，不接真实图片/GIF/视频 API。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ..infrastructure.persistence.sqlite_observation_repo import (
    get_presence_snapshot,
    save_presence_snapshot,
)
from ..logger import logger
from .observation_service import (
    activate_presence_runtime_state,
    clear_presence_runtime_state_for_observation,
    get_or_create_observation_snapshot,
)

_MEDIA_TYPE_ALIASES = {
    "jpg": "image",
    "jpeg": "image",
    "png": "image",
    "image": "image",
    "gif": "gif",
    "mp4": "video",
    "video": "video",
}


def _get_dep(deps: Mapping[str, Any] | None, name: str, default: Any) -> Any:
    if deps and name in deps:
        return deps[name]
    return default


def normalize_observation_media_type(media_type: str | None) -> str:
    """把外部请求的媒体类型归一到 snapshot 内部值。"""
    cleaned = (media_type or "image").strip().lower()
    return _MEDIA_TYPE_ALIASES.get(cleaned, "image")


def build_observation_media_task(
    user_id: str,
    media_type: str = "image",
    *,
    force_refresh: bool = True,
    deps: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """创建媒体生成占位任务，并把 snapshot 媒体状态切到 pending。"""
    get_or_create_snapshot_fn = _get_dep(
        deps, "get_or_create_observation_snapshot", get_or_create_observation_snapshot
    )
    save_presence_snapshot_fn = _get_dep(deps, "save_presence_snapshot", save_presence_snapshot)
    activate_runtime_state_fn = _get_dep(
        deps, "activate_presence_runtime_state", activate_presence_runtime_state
    )
    logger_obj = _get_dep(deps, "logger", logger)

    normalized_media_type = normalize_observation_media_type(media_type)
    state_token = activate_runtime_state_fn(
        user_id,
        "media_rendering",
        scene_hint="她像是被一台看不见的镜头轻轻定格住，周围的光影正一点点聚焦成画面",
        ttl_seconds=600,
        deps=deps,
    )
    snapshot = dict(get_or_create_snapshot_fn(user_id, force_refresh=force_refresh, deps=deps))
    snapshot.update(
        {
            "media_type": normalized_media_type,
            "media_status": "pending",
            "media_key": "",
            "updated_reason": "media_task_prepared",
        }
    )
    save_presence_snapshot_fn(user_id, snapshot)

    logger_obj.info(
        "👁️ observation 媒体占位任务已创建",
        extra={"user_id": user_id, "media_type": normalized_media_type},
    )
    return {
        "status": "pending",
        "user_id": user_id,
        "media_type": normalized_media_type,
        "media_prompt": snapshot.get("media_prompt", ""),
        "state_token": state_token,
    }


def complete_observation_media_task(
    user_id: str,
    *,
    state_token: str | None = None,
    media_type: str = "image",
    media_key: str = "",
    success: bool = False,
    deps: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """结束媒体占位任务；未来真实 worker 可复用这个收口函数。"""
    get_presence_snapshot_fn = _get_dep(deps, "get_presence_snapshot", get_presence_snapshot)
    get_or_create_snapshot_fn = _get_dep(
        deps, "get_or_create_observation_snapshot", get_or_create_observation_snapshot
    )
    save_presence_snapshot_fn = _get_dep(deps, "save_presence_snapshot", save_presence_snapshot)
    clear_runtime_state_fn = _get_dep(
        deps,
        "clear_presence_runtime_state_for_observation",
        clear_presence_runtime_state_for_observation,
    )
    logger_obj = _get_dep(deps, "logger", logger)

    normalized_media_type = normalize_observation_media_type(media_type)
    snapshot = get_presence_snapshot_fn(user_id)
    if not snapshot:
        snapshot = get_or_create_snapshot_fn(user_id, force_refresh=False, deps=deps)
    snapshot = dict(snapshot)
    final_status = "ready" if success and media_key else "failed"
    snapshot.update(
        {
            "media_type": normalized_media_type,
            "media_status": final_status,
            "media_key": media_key if final_status == "ready" else "",
            "updated_reason": f"media_task_{final_status}",
        }
    )
    save_presence_snapshot_fn(user_id, snapshot)
    if state_token:
        clear_runtime_state_fn(user_id, state_token=state_token, deps=deps)

    logger_obj.info(
        "👁️ observation 媒体占位任务已收口",
        extra={"user_id": user_id, "media_type": normalized_media_type, "status": final_status},
    )
    return {
        "status": final_status,
        "user_id": user_id,
        "media_type": normalized_media_type,
        "media_key": media_key if final_status == "ready" else "",
    }
