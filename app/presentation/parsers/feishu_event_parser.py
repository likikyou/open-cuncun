"""飞书事件解析器。"""

from __future__ import annotations

import json
import threading
from typing import Any

from ...infrastructure.feishu import download_resource, send_random_emoticon
from ...logger import logger
from ...vision import analyze_image

_CARD_COMMAND_ALLOWLIST = {
    "/status",
    "/observe",
    "/reply",
    "/memory",
    "/help",
    "/reset",
    "/model",
    "/clear",
    "/pure",
    "/chat",
    "/story",
}


def _is_allowed_card_command(command: str) -> bool:
    base_command = (command or "").strip().split(maxsplit=1)[0]
    return base_command in _CARD_COMMAND_ALLOWLIST


def _find_first_nested_value(data: Any, key: str) -> Any:
    """递归查找嵌套结构中的第一个指定 key 的值。"""
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for value in data.values():
            found = _find_first_nested_value(value, key)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = _find_first_nested_value(item, key)
            if found is not None:
                return found
    return None


def _extract_card_action_value(event: dict) -> dict:
    """尽量兼容不同层级的卡片回传结构，提取 action.value。"""
    if not isinstance(event, dict):
        return {}

    action = event.get("action")
    if isinstance(action, dict) and isinstance(action.get("value"), dict):
        return action["value"]

    action = _find_first_nested_value(event, "action")
    if isinstance(action, dict) and isinstance(action.get("value"), dict):
        return action["value"]

    value = _find_first_nested_value(event, "value")
    return value if isinstance(value, dict) else {}


def _extract_card_open_id(event: dict) -> str | None:
    """尽量兼容不同层级的卡片回传结构，提取操作人 open_id。"""
    if not isinstance(event, dict):
        return None

    operator = event.get("operator")
    if isinstance(operator, dict):
        open_id = operator.get("open_id")
        if open_id:
            return open_id
        operator_id = operator.get("operator_id")
        if isinstance(operator_id, dict) and operator_id.get("open_id"):
            return operator_id["open_id"]

    sender = event.get("sender")
    if isinstance(sender, dict):
        sender_id = sender.get("sender_id")
        if isinstance(sender_id, dict) and sender_id.get("open_id"):
            return sender_id["open_id"]

    found = _find_first_nested_value(event, "open_id")
    return found if isinstance(found, str) and found else None


def parse_message(
    data: dict,
    *,
    download_resource_fn=download_resource,
    analyze_image_fn=analyze_image,
    send_random_emoticon_fn=send_random_emoticon,
    logger_obj=logger,
) -> tuple[str | None, str | None]:
    """
    解析飞书事件数据，提取 open_id 和 user_text。

    返回:
        (open_id, user_text) 或 (None, None) 表示无效消息。
    """
    header = data.get("header", {})
    event_type = header.get("event_type")
    event = data.get("event", {})
    message = event.get("message", {})

    if event_type == "card.action.trigger":
        open_id = _extract_card_open_id(event)
        action_value = _extract_card_action_value(event)
        action_name = action_value.get("action")
        mode = action_value.get("mode")
        mode_to_command = {"light": "/reply 1", "normal": "/reply 2", "qa": "/reply 3"}

        if open_id and action_name == "set_reply_mode" and mode in mode_to_command:
            logger_obj.info(
                "🃏 收到卡片按钮回调",
                extra={"open_id": open_id, "action": action_name, "mode": mode},
            )
            return open_id, mode_to_command[mode]

        pure_enabled = action_value.get("enabled")
        pure_to_command = {"on": "/pure on", "off": "/pure off"}
        if open_id and action_name == "set_pure_mode" and pure_enabled in pure_to_command:
            logger_obj.info(
                "🃏 收到净聊模式切换回调",
                extra={"open_id": open_id, "action": action_name, "enabled": pure_enabled},
            )
            return open_id, pure_to_command[pure_enabled]

        provider = action_value.get("provider")
        provider_to_command = {
            "cerebras": "/model cerebras",
            "groq": "/model groq",
            "deepseek": "/model deepseek",
            "default": "/model default",
        }
        if open_id and action_name == "set_ai_provider" and provider in provider_to_command:
            logger_obj.info(
                "🃏 收到卡片模型切换回调",
                extra={"open_id": open_id, "action": action_name, "provider": provider},
            )
            return open_id, provider_to_command[provider]

        if open_id and action_name == "confirm_reset":
            logger_obj.info(
                "🃏 收到重开确认回调",
                extra={"open_id": open_id, "action": action_name},
            )
            return open_id, "/reset confirm"

        if open_id and action_name == "confirm_clear_context":
            logger_obj.info(
                "🃏 收到清空上下文确认回调",
                extra={"open_id": open_id, "action": action_name},
            )
            return open_id, "/clear confirm"

        command = action_value.get("command")
        if open_id and action_name == "run_command" and _is_allowed_card_command(command):
            logger_obj.info(
                "🃏 收到卡片命令回调",
                extra={"open_id": open_id, "action": action_name, "command": command},
            )
            return open_id, command

        logger_obj.warning(f"⚠️ 未识别的卡片回调: {event}")
        return None, None

    sender = event.get("sender", {}).get("sender_id", {})
    open_id = sender.get("open_id")
    if not open_id:
        logger_obj.warning("❌ 收到消息但无法获取 open_id")
        return None, None

    msg_type = message.get("message_type")
    msg_id = message.get("message_id")

    if msg_type == "text":
        content_json = message.get("content", "{}")
        if isinstance(content_json, str):
            try:
                content_obj = json.loads(content_json)
                user_text = content_obj.get("text", "").strip()
            except json.JSONDecodeError:
                user_text = str(content_json).strip()
        else:
            user_text = str(content_json).strip()
        logger_obj.info("📩 收到用户消息", extra={"user_text": user_text, "open_id": open_id})
        return open_id, user_text

    if msg_type == "image":
        try:
            content_obj = json.loads(message.get("content", "{}"))
            image_key = content_obj.get("image_key")
            logger_obj.info(f"🖼️ 收到图片消息: {image_key}", extra={"open_id": open_id})

            image_data = download_resource_fn(msg_id, image_key, "image")
            if image_data:
                description = analyze_image_fn(image_data)
                logger_obj.info(f"👁️ 图片识别结果: {description[:50]}...")
                return open_id, f"[你给我发送了一张图片，内容描述如下：{description}]"
            return open_id, "[你给我发送了一张图片，但由于网络错误我没能看清。]"
        except Exception as exc:
            logger_obj.error(f"❌ 处理图片消息失败: {exc}")
            return None, None

    if msg_type == "sticker":
        logger_obj.info("🎭 收到表情包", extra={"open_id": open_id})

        # 使用线程异步发送表情包，网络延迟本身足以模拟真人找图。
        threading.Thread(
            target=send_random_emoticon_fn,
            args=(open_id,),
            daemon=True,
        ).start()

        prompt_text = (
            "【系统提示：我刚才给你发了一个表情包（注：是你的动态图或者图片）。"
            "请根据你傲娇女友的性格，用一两句简短的文字随便吐槽一下我爱发表情包的行为，"
            '或者傲娇地表示"我也给你发一个自己的表情包"来进行反击。'
            "切记不要凭空编造表情包的内容。】"
        )
        return open_id, prompt_text

    logger_obj.info(
        f"📨 收到未处理的消息类型: {msg_type}, content: {message.get('content', '')[:200]}",
        extra={"open_id": open_id},
    )
    return open_id, None
