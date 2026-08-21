"""飞书媒体上传与下载。"""

from __future__ import annotations

import functools
import glob
import os
from typing import Optional

from ...logger import logger
from .client import feishu_client


@functools.lru_cache(maxsize=4)
def _get_emoticon_files(emoticon_dir: str) -> tuple:
    """获取表情包文件列表，带缓存避免重复扫描目录。"""
    files = (
        glob.glob(os.path.join(emoticon_dir, "*.webp"))
        + glob.glob(os.path.join(emoticon_dir, "*.png"))
        + glob.glob(os.path.join(emoticon_dir, "*.jpg"))
        + glob.glob(os.path.join(emoticon_dir, "*.gif"))
    )
    return tuple(files)


def upload_audio_v2(file_path: str) -> Optional[str]:
    """上传音频文件到飞书，返回 file_key。"""
    if not os.path.exists(file_path):
        logger.error("❌ 待上传音频文件不存在")
        return None

    url = "https://open.feishu.cn/open-apis/im/v1/files"
    filename = os.path.basename(file_path)
    try:
        with open(file_path, "rb") as file_obj:
            files = {
                "file_type": (None, "opus"),
                "file_name": (None, filename),
                "file": (filename, file_obj.read(), "application/octet-stream"),
            }
            response = feishu_client.request("POST", url, files=files, timeout=30)
            if response and response.status_code == 200:
                result = response.json()
                if result.get("code") == 0:
                    file_key = result.get("data", {}).get("file_key")
                    if file_key:
                        logger.info("✅ 音频上传成功")
                        return file_key
                    logger.error("❌ 音频上传成功但响应缺少 file_key")
                else:
                    logger.error(
                        "❌ 音频上传业务失败",
                        extra={"error_code": result.get("code")},
                    )
            else:
                logger.error(
                    "❌ 音频上传 HTTP 失败",
                    extra={"status_code": response.status_code if response else None},
                )
    except Exception as error:
        logger.error(
            "❌ 音频上传异常",
            extra={"error_type": type(error).__name__},
        )
    return None


def upload_image(file_path: str) -> Optional[str]:
    """上传图片文件到飞书，返回 image_key。"""
    if not os.path.exists(file_path):
        logger.error("❌ 待上传图片文件不存在")
        return None

    url = "https://open.feishu.cn/open-apis/im/v1/images"
    filename = os.path.basename(file_path)
    try:
        with open(file_path, "rb") as file_obj:
            files = {
                "image_type": (None, "message"),
                "image": (filename, file_obj.read(), "application/octet-stream"),
            }
            response = feishu_client.request("POST", url, files=files, timeout=30)
            if response and response.status_code == 200:
                result = response.json()
                if result.get("code") == 0:
                    image_key = result.get("data", {}).get("image_key")
                    if image_key:
                        logger.info("✅ 图片上传成功")
                        return image_key
                    logger.error("❌ 图片上传成功但响应缺少 image_key")
                else:
                    logger.error(
                        "❌ 图片上传业务失败",
                        extra={"error_code": result.get("code")},
                    )
            else:
                logger.error(
                    "❌ 图片上传 HTTP 失败",
                    extra={"status_code": response.status_code if response else None},
                )
    except Exception as error:
        logger.error(
            "❌ 图片上传异常",
            extra={"error_type": type(error).__name__},
        )
    return None


def upload_video(file_path: str) -> Optional[str]:
    """上传视频文件到飞书，返回 file_key。"""
    if not os.path.exists(file_path):
        logger.error("❌ 待上传视频文件不存在")
        return None

    url = "https://open.feishu.cn/open-apis/im/v1/files"
    filename = os.path.basename(file_path)
    try:
        with open(file_path, "rb") as file_obj:
            files = {
                "file_type": (None, "mp4"),
                "file_name": (None, filename),
                "file": (filename, file_obj.read(), "video/mp4"),
            }
            response = feishu_client.request("POST", url, files=files, timeout=60)
            if response and response.status_code == 200:
                result = response.json()
                if result.get("code") == 0:
                    file_key = result.get("data", {}).get("file_key")
                    if file_key:
                        logger.info("✅ 视频上传成功")
                        return file_key
                    logger.error("❌ 视频上传成功但响应缺少 file_key")
                else:
                    logger.error(
                        "❌ 视频上传业务失败",
                        extra={"error_code": result.get("code")},
                    )
            else:
                logger.error(
                    "❌ 视频上传 HTTP 失败",
                    extra={"status_code": response.status_code if response else None},
                )
    except Exception as error:
        logger.error(
            "❌ 视频上传异常",
            extra={"error_type": type(error).__name__},
        )
    return None


def download_resource(
    message_id: str, file_key: str, resource_type: str = "image"
) -> Optional[bytes]:
    """下载消息中的图片/文件资源。"""
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}?type={resource_type}"
    response = feishu_client.request("GET", url, stream=True, timeout=30)
    if response and response.status_code == 200:
        return response.content
    logger.error(
        "❌ 下载飞书资源失败",
        extra={
            "resource_type": resource_type,
            "status_code": response.status_code if response else None,
        },
    )
    return None
