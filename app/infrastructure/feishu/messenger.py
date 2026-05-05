"""飞书消息发送与卡片投递。"""

from __future__ import annotations

import json
import os
import random
import time
from typing import Optional

from ...config import Config
from ...logger import logger
from .client import feishu_client
from .media_store import _get_emoticon_files, upload_image


def send_feishu(receive_id: str, msg_type: str, content: dict) -> bool:
    """通用飞书消息发送函数。"""
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    headers = {"Content-Type": "application/json"}
    response = feishu_client.request(
        "POST",
        url,
        headers=headers,
        json={
            "receive_id": receive_id,
            "msg_type": msg_type,
            "content": json.dumps(content),
        },
        timeout=10,
    )
    if response and response.status_code == 200:
        result = response.json()
        if result.get("code") == 0:
            return True
        logger.error(f"❌ 发送消息业务失败: {result}")
    return False


def send_interactive_card(receive_id: str, card_content: dict) -> bool:
    """发送交互式卡片。"""
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    headers = {"Content-Type": "application/json"}
    payload = {
        "receive_id": receive_id,
        "msg_type": "interactive",
        "content": json.dumps(card_content),
    }
    response = feishu_client.request("POST", url, headers=headers, json=payload, timeout=10)
    if response and response.status_code == 200 and response.json().get("code") == 0:
        return True
    logger.error(f"❌ 发送交互式卡片失败: {response.text if response else 'No Response'}")
    return False


def send_image(receive_id: str, image_key: str) -> bool:
    """发送图片消息。"""
    result = send_feishu(receive_id, "image", {"image_key": image_key})
    if result:
        logger.info(f"✅ 图片消息发送成功: {image_key}")
    return result


def send_video(receive_id: str, video_key: str) -> bool:
    """发送视频消息。"""
    result = send_feishu(receive_id, "media", {"file_key": video_key})
    if result:
        logger.info(f"✅ 视频消息发送成功: {video_key}")
    return result


def send_random_emoticon(receive_id: str, emoticon_dir: str | None = None) -> bool:
    """随机发送一个表情包。"""
    if emoticon_dir is None:
        emoticon_dir = getattr(
            Config, "EMOTICON_DIR", os.path.join(Config.PROJECT_ROOT, "emoticon")
        )

    emoticon_files = _get_emoticon_files(emoticon_dir)
    if not emoticon_files:
        logger.warning(f"⚠️ 表情包目录为空: {emoticon_dir}")
        return False

    chosen = random.choice(emoticon_files)
    logger.info(f"🎭 随机选择表情包: {chosen}")
    image_key = upload_image(chosen)
    if image_key:
        return send_image(receive_id, image_key)
    return False


def create_streaming_card(element_id: str = "streaming_text") -> Optional[str]:
    """创建支持流式更新的卡片实体。"""
    start = time.perf_counter()
    url = "https://open.feishu.cn/open-apis/cardkit/v1/cards"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    card_json = {
        "schema": "2.0",
        "config": {
            "streaming_mode": True,
            "update_multi": True,
            "streaming_config": {
                "print_frequency_ms": {"default": 30, "android": 30, "ios": 30, "pc": 30},
                "print_step": {"default": 2, "android": 2, "ios": 2, "pc": 2},
                "print_strategy": "fast",
            },
        },
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "content": "💭 思考中...",
                    "element_id": element_id,
                }
            ]
        },
    }
    response = feishu_client.request(
        "POST",
        url,
        headers=headers,
        json={"type": "card_json", "data": json.dumps(card_json, ensure_ascii=False)},
        timeout=10,
    )
    if response and response.status_code == 200:
        result = response.json()
        if result.get("code") == 0:
            card_id = result.get("data", {}).get("card_id")
            if card_id:
                logger.info(f"✅ 流式卡片创建成功: {card_id}")
                logger.info(
                    f"⏱️ [性能] create_streaming_card: {(time.perf_counter() - start) * 1000:.0f}ms"
                )
                return card_id
            logger.error(f"❌ 创建成功但无 card_id: {result}")
        else:
            logger.error(f"❌ 创建流式卡片业务失败: {result}")
    logger.info(
        f"⏱️ [性能] create_streaming_card 失败: {(time.perf_counter() - start) * 1000:.0f}ms"
    )
    return None


def send_card_message(receive_id: str, card_id: str) -> Optional[str]:
    """通过 card_id 发送卡片消息。"""
    start = time.perf_counter()
    url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id"
    headers = {"Content-Type": "application/json"}
    response = feishu_client.request(
        "POST",
        url,
        headers=headers,
        json={
            "receive_id": receive_id,
            "msg_type": "interactive",
            "content": json.dumps({"type": "card", "data": {"card_id": card_id}}),
        },
        timeout=10,
    )
    if response and response.status_code == 200:
        result = response.json()
        if result.get("code") == 0:
            message_id = result.get("data", {}).get("message_id")
            if message_id:
                logger.info(f"✅ 卡片消息发送成功: {message_id}")
                logger.info(
                    f"⏱️ [性能] send_card_message: {(time.perf_counter() - start) * 1000:.0f}ms"
                )
                return message_id
            logger.error(f"❌ 发送成功但无 message_id: {result}")
        else:
            logger.error(f"❌ 发送卡片消息业务失败: {result}")
    logger.info(f"⏱️ [性能] send_card_message 失败: {(time.perf_counter() - start) * 1000:.0f}ms")
    return None


def stream_update_card_text(
    card_id: str, text: str, sequence: int, element_id: str = "streaming_text"
) -> bool:
    """流式更新卡片元素文本。"""
    start = time.perf_counter()
    url = (
        f"https://open.feishu.cn/open-apis/cardkit/v1/cards/{card_id}/elements/{element_id}/content"
    )
    headers = {"Content-Type": "application/json; charset=utf-8"}
    response = feishu_client.request(
        "PUT",
        url,
        headers=headers,
        json={"content": text, "sequence": sequence},
        timeout=5,
    )

    elapsed_ms = (time.perf_counter() - start) * 1000
    if elapsed_ms > 500:
        logger.info(f"⏱️ [性能] stream_update_card_text seq={sequence}: {elapsed_ms:.0f}ms ⚠️ 较慢")

    if response and response.status_code == 200:
        result = response.json()
        if result.get("code") != 0:
            logger.error(f"❌ 流式更新业务失败 seq={sequence}: {result}")
            return False
        return True
    logger.warning(
        f"⚠️ 流式更新HTTP失败 seq={sequence}: status={response.status_code if response else 'None'}, card_id={card_id}"
    )
    return False


def finish_streaming(card_id: str, sequence: int) -> bool:
    """关闭卡片的流式更新模式。"""
    start = time.perf_counter()
    url = f"https://open.feishu.cn/open-apis/cardkit/v1/cards/{card_id}/settings"
    headers = {"Content-Type": "application/json; charset=utf-8"}
    settings_payload = json.dumps({"config": {"streaming_mode": False}})
    response = feishu_client.request(
        "PATCH",
        url,
        headers=headers,
        json={"settings": settings_payload, "sequence": sequence},
        timeout=5,
    )
    if response and response.status_code == 200 and response.json().get("code") == 0:
        logger.info(f"✅ 流式模式已关闭: {card_id}")
        logger.info(f"⏱️ [性能] finish_streaming: {(time.perf_counter() - start) * 1000:.0f}ms")
        return True
    logger.error(f"❌ 关闭流式模式失败: {card_id}")
    return False
