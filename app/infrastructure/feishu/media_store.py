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
        logger.error(f"❌ 文件不存在: {file_path}")
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
                        logger.info(f"✅ 上传成功 Key: {file_key}")
                        return file_key
                    logger.error(f"❌ 上传成功但无 file_key: {result}")
                else:
                    logger.error(f"❌ 上传业务失败: {result}")
            else:
                logger.error(
                    f"❌ 上传 HTTP 失败: {response.status_code if response else 'No Response'}"
                )
    except Exception as exc:
        logger.error(f"❌ 上传异常: {exc}")
    return None


def upload_image(file_path: str) -> Optional[str]:
    """上传图片文件到飞书，返回 image_key。"""
    if not os.path.exists(file_path):
        logger.error(f"❌ 文件不存在: {file_path}")
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
                        logger.info(f"✅ 图片上传成功 Key: {image_key}")
                        return image_key
                    logger.error(f"❌ 上传成功但无 image_key: {result}")
                else:
                    logger.error(f"❌ 上传图片业务失败: {result}")
            else:
                logger.error(
                    f"❌ 上传图片 HTTP 失败: {response.status_code if response else 'No Response'}"
                )
    except Exception as exc:
        logger.error(f"❌ 上传图片异常: {exc}")
    return None


def upload_video(file_path: str) -> Optional[str]:
    """上传视频文件到飞书，返回 file_key。"""
    if not os.path.exists(file_path):
        logger.error(f"❌ 文件不存在: {file_path}")
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
                        logger.info(f"✅ 视频上传成功 Key: {file_key}")
                        return file_key
                    logger.error(f"❌ 上传成功但无 file_key: {result}")
                else:
                    logger.error(f"❌ 上传视频业务失败: {result}")
            else:
                logger.error(
                    f"❌ 上传视频 HTTP 失败: {response.status_code if response else 'No Response'}"
                )
    except Exception as exc:
        logger.error(f"❌ 上传视频异常: {exc}")
    return None


def download_resource(
    message_id: str, file_key: str, resource_type: str = "image"
) -> Optional[bytes]:
    """下载消息中的图片/文件资源。"""
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{file_key}?type={resource_type}"
    response = feishu_client.request("GET", url, stream=True, timeout=30)
    if response and response.status_code == 200:
        return response.content
    logger.error(f"❌ 下载资源失败: {url}")
    return None
