"""状态与模型卡片文案格式化。"""

from __future__ import annotations

from ...config import Config


def format_status_summary(
    *,
    provider: str,
    model_name: str,
    token_status: str,
    reply_mode_display: str,
    pure_mode_display: str,
) -> str:
    """构建状态看板头部摘要。"""
    return (
        f"**机器人**：{Config.BOT_NAME}\n"
        f"**当前模型**：`{model_name}` ({provider})\n"
        f"**API 状态**：{token_status}\n"
        f"**回复模式**：{reply_mode_display}\n"
        f"**净聊测试**：{pure_mode_display}"
    )


def build_status_fields(*, deep_thinking: str, today_count: int, total_count: int) -> list[dict]:
    """构建状态看板的统计字段。"""
    return [
        {
            "is_short": True,
            "text": {
                "tag": "lark_md",
                "content": "**上下文窗口**\n最近 12 条",
            },
        },
        {
            "is_short": True,
            "text": {
                "tag": "lark_md",
                "content": f"**深度思考**\n{deep_thinking}",
            },
        },
        {
            "is_short": True,
            "text": {
                "tag": "lark_md",
                "content": f"**今日对话**\n`{today_count}` 次",
            },
        },
        {
            "is_short": True,
            "text": {
                "tag": "lark_md",
                "content": f"**总对话数**\n`{total_count}` 次",
            },
        },
    ]


def format_model_summary(*, current_model: str, current_display: str, is_default: bool) -> str:
    """构建模型切换卡片的当前模型说明。"""
    default_tag = "（全局默认）" if is_default else "（个人设置）"
    return f"**当前模型**：`{current_model}` ({current_display}) {default_tag}"
