"""卡片主图资源管理。"""

from __future__ import annotations

import json
import os
from threading import Lock
from typing import Callable

from ...config import Config
from ...logger import logger

UploadImageFn = Callable[[str], str | None]

_CARD_IMAGE_DIR = os.path.join(Config.PROJECT_ROOT, "assets", "card_images")
_CARD_IMAGE_CACHE_DIR = os.path.join(Config.PROJECT_ROOT, "data", "cache")
_CARD_IMAGE_CACHE_PATH = os.path.join(_CARD_IMAGE_CACHE_DIR, "card_image_keys.json")
_CARD_IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
_CARD_IMAGE_NAME_MAP = {
    "help": "命令中心.png",
    "reply": "回复模式.png",
    "status": "状态看板.png",
    "memory": "仿生记忆.png",
    "reset": "重新开始.png",
}

_card_image_lock = Lock()
_card_image_cache: dict[str, dict[str, str | None]] = {}


def _resolve_upload_image_fn(upload_image_fn: UploadImageFn | None) -> UploadImageFn:
    if upload_image_fn is not None:
        return upload_image_fn
    from ...infrastructure.feishu.media_store import upload_image

    return upload_image


def _get_card_image_mtime(image_path: str) -> str:
    try:
        return str(int(os.path.getmtime(image_path)))
    except OSError:
        return ""


def _load_card_image_cache_from_disk(*, logger_obj=logger) -> None:
    if not os.path.exists(_CARD_IMAGE_CACHE_PATH):
        return
    try:
        with open(_CARD_IMAGE_CACHE_PATH, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)
        if not isinstance(data, dict):
            return
        for card_type, item in data.items():
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            image_key = item.get("image_key")
            mtime = item.get("mtime")
            if not path or not image_key or not mtime or not os.path.exists(path):
                continue
            current_mtime = _get_card_image_mtime(path)
            if current_mtime == mtime:
                _card_image_cache[card_type] = {
                    "path": path,
                    "image_key": image_key,
                    "mtime": mtime,
                }
        if _card_image_cache:
            logger_obj.info(f"🖼️ 已加载 {len(_card_image_cache)} 个卡片主图缓存")
    except Exception as exc:
        logger_obj.warning(f"⚠️ 读取卡片主图缓存失败: {exc}")


def _save_card_image_cache_to_disk(*, logger_obj=logger) -> None:
    try:
        os.makedirs(_CARD_IMAGE_CACHE_DIR, exist_ok=True)
        with open(_CARD_IMAGE_CACHE_PATH, "w", encoding="utf-8") as file_obj:
            json.dump(_card_image_cache, file_obj, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger_obj.warning(f"⚠️ 写入卡片主图缓存失败: {exc}")


def _get_card_image_path(card_type: str, *, logger_obj=logger) -> str | None:
    if not os.path.isdir(_CARD_IMAGE_DIR):
        return None
    try:
        preferred_name = _CARD_IMAGE_NAME_MAP.get(card_type)
        if preferred_name:
            preferred_path = os.path.join(_CARD_IMAGE_DIR, preferred_name)
            if os.path.exists(preferred_path):
                return preferred_path

        candidates = sorted(
            os.path.join(_CARD_IMAGE_DIR, name)
            for name in os.listdir(_CARD_IMAGE_DIR)
            if name.lower().endswith(_CARD_IMAGE_EXTENSIONS)
        )
        return candidates[0] if candidates else None
    except Exception as exc:
        logger_obj.warning(f"⚠️ 获取卡片主图失败: {exc}")
        return None


def _get_card_image_key(
    card_type: str,
    *,
    upload_image_fn: UploadImageFn | None = None,
    logger_obj=logger,
) -> str | None:
    image_path = _get_card_image_path(card_type, logger_obj=logger_obj)
    if not image_path:
        return None
    image_mtime = _get_card_image_mtime(image_path)
    upload_fn = _resolve_upload_image_fn(upload_image_fn)

    with _card_image_lock:
        cached = _card_image_cache.get(card_type, {})
        if (
            cached.get("path") == image_path
            and cached.get("image_key")
            and cached.get("mtime") == image_mtime
        ):
            return cached["image_key"]

        image_key = upload_fn(image_path)
        if image_key:
            _card_image_cache[card_type] = {
                "path": image_path,
                "image_key": image_key,
                "mtime": image_mtime,
            }
            _save_card_image_cache_to_disk(logger_obj=logger_obj)
            logger_obj.info(f"🖼️ 卡片主图已缓存 [{card_type}]: {os.path.basename(image_path)}")
            return image_key

    return None


def preload_card_images(*, upload_image_fn: UploadImageFn | None = None, logger_obj=logger) -> None:
    """启动时预热卡片主图，避免首张卡片触发上传延迟。"""
    with _card_image_lock:
        if not _card_image_cache:
            _load_card_image_cache_from_disk(logger_obj=logger_obj)

    warmed = 0
    for card_type in ("help", "reply", "status", "memory", "reset"):
        if _get_card_image_key(card_type, upload_image_fn=upload_image_fn, logger_obj=logger_obj):
            warmed += 1
    logger_obj.info(f"🖼️ 卡片主图预热完成: {warmed}/5")


def build_card_hero_image(
    card_type: str,
    alt_text: str,
    *,
    upload_image_fn: UploadImageFn | None = None,
    logger_obj=logger,
) -> dict | None:
    image_key = _get_card_image_key(
        card_type, upload_image_fn=upload_image_fn, logger_obj=logger_obj
    )
    if not image_key:
        return None
    return {
        "tag": "img",
        "img_key": image_key,
        "alt": {
            "tag": "plain_text",
            "content": alt_text,
        },
    }
