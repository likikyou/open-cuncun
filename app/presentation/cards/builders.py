"""飞书交互卡片 JSON 构建器。"""

from __future__ import annotations

from ...config import Config
from ..formatters.memory_formatter import (
    build_meter,
    format_memory_state,
    format_memory_summary,
)
from ..formatters.status_formatter import (
    build_status_fields,
    format_model_summary,
    format_status_summary,
)
from .assets import build_card_hero_image


def build_reply_mode_card(current_mode: str) -> dict:
    current_mode = (current_mode or "normal").strip().lower()
    elements = []
    hero_image = build_card_hero_image("reply", f"{Config.BOT_NAME} 回复模式主图")
    if hero_image:
        elements.append(hero_image)
    elements.extend(
        [
            {
                "tag": "action",
                "layout": "trisection",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary" if current_mode == "light" else "default",
                        "text": {"tag": "plain_text", "content": "轻量闲聊"},
                        "value": {"action": "set_reply_mode", "mode": "light"},
                    },
                    {
                        "tag": "button",
                        "type": "primary" if current_mode == "normal" else "default",
                        "text": {"tag": "plain_text", "content": "正常聊天"},
                        "value": {"action": "set_reply_mode", "mode": "normal"},
                    },
                    {
                        "tag": "button",
                        "type": "primary" if current_mode == "qa" else "default",
                        "text": {"tag": "plain_text", "content": "问答检索"},
                        "value": {"action": "set_reply_mode", "mode": "qa"},
                    },
                ],
            }
        ]
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": f"{Config.BOT_NAME} 回复模式设置",
            },
        },
        "elements": elements,
    }


def build_pure_mode_card(enabled: bool) -> dict:
    elements = []
    hero_image = build_card_hero_image("reply", f"{Config.BOT_NAME} 净聊测试主图")
    if hero_image:
        elements.append(hero_image)
    current_status = "🧪 已开启" if enabled else "⭕ 已关闭"
    elements.extend(
        [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**当前状态**：{current_status}\n"
                        "**模式说明**：临时关闭 `long_term + bionic`，保留人设、用户画像、关系层与实时信息。"
                    ),
                },
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary" if not enabled else "default",
                        "text": {"tag": "plain_text", "content": "开启净聊"},
                        "value": {"action": "set_pure_mode", "enabled": "on"},
                    },
                    {
                        "tag": "button",
                        "type": "primary" if enabled else "default",
                        "text": {"tag": "plain_text", "content": "关闭净聊"},
                        "value": {"action": "set_pure_mode", "enabled": "off"},
                    },
                ],
            },
        ]
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "indigo",
            "title": {
                "tag": "plain_text",
                "content": f"{Config.BOT_NAME} 净聊测试",
            },
        },
        "elements": elements,
    }


def build_help_card() -> dict:
    elements = []
    hero_image = build_card_hero_image("help", f"{Config.BOT_NAME} 命令中心主图")
    if hero_image:
        elements.append(hero_image)
    elements.extend(
        [
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "📊 状态看板"},
                        "value": {"action": "run_command", "command": "/status"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "💬 回复模式"},
                        "value": {"action": "run_command", "command": "/reply"},
                    },
                ],
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "👁️ 悄悄看一眼"},
                        "value": {"action": "run_command", "command": "/observe"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "🤖 切换模型"},
                        "value": {"action": "run_command", "command": "/model"},
                    },
                ],
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "🧠 仿生记忆"},
                        "value": {"action": "run_command", "command": "/memory"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "🗂️ 对话管理"},
                        "value": {"action": "run_command", "command": "/chat"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "🎬 剧情模式"},
                        "value": {"action": "run_command", "command": "/story"},
                    },
                ],
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "🧹 记忆审核"},
                        "value": {"action": "run_command", "command": "/memory audit"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "🧪 净聊测试"},
                        "value": {"action": "run_command", "command": "/pure"},
                    },
                ],
            },
            {"tag": "hr"},
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "🧼 清空上下文"},
                        "value": {"action": "run_command", "command": "/clear"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "📖 刷新帮助"},
                        "value": {"action": "run_command", "command": "/help"},
                    },
                ],
            },
            {"tag": "hr"},
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "danger",
                        "text": {"tag": "plain_text", "content": "🔄 重新开始"},
                        "value": {"action": "run_command", "command": "/reset"},
                    }
                ],
            },
        ]
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "turquoise",
            "title": {
                "tag": "plain_text",
                "content": f"{Config.BOT_NAME} 命令中心",
            },
        },
        "elements": elements,
    }


def build_story_mode_card(active_conversation: dict) -> dict:
    mode = active_conversation.get("mode") or "normal"
    title = active_conversation.get("title") or "日常聊天"
    summary = active_conversation.get("summary") or "未设置剧情开场"
    enabled = mode == "story"
    elements = []
    hero_image = build_card_hero_image("reply", f"{Config.BOT_NAME} 剧情模式主图")
    if hero_image:
        elements.append(hero_image)
    status_text = "🎬 已在剧情对话中" if enabled else "⭕ 当前不是剧情对话"
    elements.extend(
        [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**当前对话**：{title}\n"
                        f"**状态**：{status_text}\n"
                        f"**剧情设定**：{summary}\n\n"
                        "剧情模式会被限制在独立对话里，不会写入现实仿生记忆。"
                    ),
                },
            },
            {
                "tag": "action",
                "layout": "trisection",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "开启剧情"},
                        "value": {"action": "run_command", "command": "/story on"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "退出剧情"},
                        "value": {"action": "run_command", "command": "/story off"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "查看状态"},
                        "value": {"action": "run_command", "command": "/story status"},
                    },
                ],
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "对话列表"},
                        "value": {"action": "run_command", "command": "/chat"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "帮助中心"},
                        "value": {"action": "run_command", "command": "/help"},
                    },
                ],
            },
        ]
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "purple",
            "title": {
                "tag": "plain_text",
                "content": f"{Config.BOT_NAME} 剧情模式",
            },
        },
        "elements": elements,
    }


def build_chat_card(conversations: list[dict], active_conversation_id: str) -> dict:
    elements = []
    hero_image = build_card_hero_image("reply", f"{Config.BOT_NAME} 对话列表主图")
    if hero_image:
        elements.append(hero_image)

    active = next(
        (item for item in conversations if item.get("id") == active_conversation_id),
        {},
    )
    active_title = active.get("title") or "日常聊天"
    active_mode = "剧情" if active.get("mode") == "story" else "普通"

    elements.extend(
        [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**当前对话**：{active_title}\n"
                        f"**类型**：{active_mode}\n"
                        "下面这些按钮会直接执行对应命令，切换后只带当前对话的上下文。"
                    ),
                },
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "➕ 新建对话"},
                        "value": {"action": "run_command", "command": "/chat new"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "🔁 切换对话"},
                        "value": {"action": "run_command", "command": "/chat switch"},
                    },
                ],
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "✏️ 重命名"},
                        "value": {"action": "run_command", "command": "/chat rename"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "📍 当前对话"},
                        "value": {"action": "run_command", "command": "/chat current"},
                    },
                ],
            },
            {"tag": "hr"},
        ]
    )

    if not conversations:
        elements.append(
            {
                "tag": "div",
                "text": {"tag": "lark_md", "content": "还没有对话，点下面的新建对话就行。"},
            }
        )
    else:
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "**选择一个对话继续聊。**",
                },
            }
        )
        for item in conversations[:8]:
            conversation_id = item.get("id", "")
            title = item.get("title") or "未命名对话"
            message_count = int(item.get("message_count") or 0)
            is_active = conversation_id == active_conversation_id
            prefix = "✓ " if is_active else ""
            elements.append(
                {
                    "tag": "action",
                    "layout": "bisected",
                    "actions": [
                        {
                            "tag": "button",
                            "type": "primary" if is_active else "default",
                            "text": {
                                "tag": "plain_text",
                                "content": f"{prefix}{title[:18]} · {message_count}条",
                            },
                            "value": {
                                "action": "run_command",
                                "command": f"/chat switch {conversation_id}",
                            },
                        }
                    ],
                }
            )

    elements.extend(
        [
            {"tag": "hr"},
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "新建对话"},
                        "value": {"action": "run_command", "command": "/chat new"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "剧情模式"},
                        "value": {"action": "run_command", "command": "/story"},
                    },
                ],
            },
        ]
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "purple",
            "title": {
                "tag": "plain_text",
                "content": f"{Config.BOT_NAME} 多重对话",
            },
        },
        "elements": elements,
    }


def build_chat_current_card(active_conversation: dict) -> dict:
    title = active_conversation.get("title") or "日常聊天"
    mode = active_conversation.get("mode") or "normal"
    summary = active_conversation.get("summary") or "无"
    conversation_id = active_conversation.get("id") or "default"
    mode_display = "剧情模式" if mode == "story" else "普通对话"
    elements = []
    hero_image = build_card_hero_image("reply", f"{Config.BOT_NAME} 当前对话主图")
    if hero_image:
        elements.append(hero_image)
    elements.extend(
        [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**当前对话**：{title}\n"
                        f"**模式**：{mode_display}\n"
                        f"**对话 ID**：`{conversation_id}`\n"
                        f"**设定**：{summary}"
                    ),
                },
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "对话面板"},
                        "value": {"action": "run_command", "command": "/chat"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "重命名"},
                        "value": {"action": "run_command", "command": "/chat rename"},
                    },
                ],
            },
        ]
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": f"{Config.BOT_NAME} 当前对话",
            },
        },
        "elements": elements,
    }


def build_chat_rename_card(active_conversation: dict) -> dict:
    title = active_conversation.get("title") or "日常聊天"
    elements = []
    hero_image = build_card_hero_image("reply", f"{Config.BOT_NAME} 对话重命名主图")
    if hero_image:
        elements.append(hero_image)
    elements.extend(
        [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**当前名称**：{title}\n"
                        "点下面的预设可以立即改名；想自定义名称，也可以继续用文字命令完成。"
                    ),
                },
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "日常聊天"},
                        "value": {"action": "run_command", "command": "/chat rename 日常聊天"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "工作吐槽"},
                        "value": {"action": "run_command", "command": "/chat rename 工作吐槽"},
                    },
                ],
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "项目脑暴"},
                        "value": {"action": "run_command", "command": "/chat rename 项目脑暴"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "剧情草稿"},
                        "value": {"action": "run_command", "command": "/chat rename 剧情草稿"},
                    },
                ],
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "返回对话面板"},
                        "value": {"action": "run_command", "command": "/chat"},
                    }
                ],
            },
        ]
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "indigo",
            "title": {
                "tag": "plain_text",
                "content": f"{Config.BOT_NAME} 重命名对话",
            },
        },
        "elements": elements,
    }


def build_status_card(
    provider: str,
    model_name: str,
    token_status: str,
    deep_thinking: str,
    reply_mode_display: str,
    pure_mode_display: str,
    today_count: int,
    total_count: int,
) -> dict:
    elements = []
    hero_image = build_card_hero_image("status", f"{Config.BOT_NAME} 状态看板主图")
    if hero_image:
        elements.append(hero_image)
    elements.extend(
        [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": format_status_summary(
                        provider=provider,
                        model_name=model_name,
                        token_status=token_status,
                        reply_mode_display=reply_mode_display,
                        pure_mode_display=pure_mode_display,
                    ),
                },
            },
            {
                "tag": "div",
                "fields": build_status_fields(
                    deep_thinking=deep_thinking,
                    today_count=today_count,
                    total_count=total_count,
                ),
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "清空上下文"},
                        "value": {"action": "run_command", "command": "/clear"},
                    },
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "刷新状态"},
                        "value": {"action": "run_command", "command": "/status"},
                    },
                ],
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "净聊测试"},
                        "value": {"action": "run_command", "command": "/pure"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "切换模型"},
                        "value": {"action": "run_command", "command": "/model"},
                    },
                ],
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "帮助中心"},
                        "value": {"action": "run_command", "command": "/help"},
                    },
                ],
            },
        ]
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "green",
            "title": {
                "tag": "plain_text",
                "content": f"{Config.BOT_NAME} 状态看板",
            },
        },
        "elements": elements,
    }


def build_memory_card(stats: dict, state: dict | None) -> dict:
    active = stats.get("active", 0)
    consolidated = stats.get("consolidated", 0)
    forgotten = stats.get("forgotten", 0)
    avg_strength = stats.get("avg_strength", 0.0)
    top_memories = stats.get("top_memories", [])

    current_mood = (state or {}).get("current_mood", "平静")
    mood_intensity = float((state or {}).get("mood_intensity") or 0.0)
    relationship_stage = (state or {}).get("relationship_stage", 1)
    total_reflections = (state or {}).get("total_reflections", 0)

    elements = []
    hero_image = build_card_hero_image("memory", f"{Config.BOT_NAME} 仿生记忆主图")
    if hero_image:
        elements.append(hero_image)
    elements.extend(
        [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": format_memory_state(
                        current_mood=current_mood,
                        mood_intensity=mood_intensity,
                        relationship_stage=relationship_stage,
                        total_reflections=total_reflections,
                    ),
                },
            },
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": True,
                        "text": {"tag": "lark_md", "content": f"**活跃记忆**\n`{active}` 条"},
                    },
                    {
                        "is_short": True,
                        "text": {"tag": "lark_md", "content": f"**已整合**\n`{consolidated}` 条"},
                    },
                    {
                        "is_short": True,
                        "text": {"tag": "lark_md", "content": f"**已遗忘**\n`{forgotten}` 条"},
                    },
                    {
                        "is_short": True,
                        "text": {
                            "tag": "lark_md",
                            "content": f"**平均强度**\n`[{build_meter(avg_strength)}] {avg_strength:.0%}`",
                        },
                    },
                ],
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": f"**最重要的记忆**\n\n{format_memory_summary(top_memories)}",
                },
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "刷新记忆"},
                        "value": {"action": "run_command", "command": "/memory"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "记忆审核"},
                        "value": {"action": "run_command", "command": "/memory audit"},
                    },
                ],
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "状态看板"},
                        "value": {"action": "run_command", "command": "/status"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "回复模式"},
                        "value": {"action": "run_command", "command": "/reply"},
                    },
                ],
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "帮助中心"},
                        "value": {"action": "run_command", "command": "/help"},
                    },
                ],
            },
        ]
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "wathet",
            "title": {
                "tag": "plain_text",
                "content": f"{Config.BOT_NAME} 仿生记忆看板",
            },
        },
        "elements": elements,
    }


def build_memory_audit_card(candidates: list[dict]) -> dict:
    elements = []
    hero_image = build_card_hero_image("memory", f"{Config.BOT_NAME} 记忆审核主图")
    if hero_image:
        elements.append(hero_image)

    count = len(candidates)
    if count == 0:
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        "**审核结果**：没有发现明显的剧情污染候选。\n"
                        "这里会扫描活跃仿生记忆里的私人行程、明星客户、临场地点等可疑内容。"
                    ),
                },
            }
        )
    else:
        elements.append(
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        f"**审核结果**：发现 `{count}` 条疑似剧情污染候选。\n"
                        "确认不是现实记忆后，可以点“标记遗忘”。"
                    ),
                },
            }
        )
        for item in candidates[:6]:
            memory_id = item.get("id")
            content = " ".join(str(item.get("content") or "").split())
            if len(content) > 140:
                content = content[:140].rstrip() + "..."
            theme = item.get("theme") or "其他"
            emotion = item.get("emotion") or "平静"
            importance = float(item.get("importance") or 0)
            reason = item.get("reason") or "命中临场剧情规则"
            elements.extend(
                [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": (
                                f"**记忆 #{memory_id}** · {theme} / {emotion} / {importance:.0%}\n"
                                f"{content}\n"
                                f"**疑似原因**：{reason}"
                            ),
                        },
                    },
                    {
                        "tag": "action",
                        "layout": "bisected",
                        "actions": [
                            {
                                "tag": "button",
                                "type": "danger",
                                "text": {"tag": "plain_text", "content": "标记遗忘"},
                                "value": {
                                    "action": "run_command",
                                    "command": f"/memory forget {memory_id}",
                                },
                            },
                            {
                                "tag": "button",
                                "type": "default",
                                "text": {"tag": "plain_text", "content": "暂时保留"},
                                "value": {"action": "run_command", "command": "/memory audit"},
                            },
                        ],
                    },
                ]
            )

    elements.extend(
        [
            {"tag": "hr"},
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "刷新审核"},
                        "value": {"action": "run_command", "command": "/memory audit"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "记忆看板"},
                        "value": {"action": "run_command", "command": "/memory"},
                    },
                ],
            },
        ]
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "orange",
            "title": {
                "tag": "plain_text",
                "content": f"{Config.BOT_NAME} 记忆审核",
            },
        },
        "elements": elements,
    }


def build_model_card(current_provider: str, is_default: bool = False) -> dict:
    from ...infrastructure.ai.provider_registry import _PROVIDER_CONFIG

    current_cfg = _PROVIDER_CONFIG.get(current_provider, {})
    current_model = current_cfg.get("model", "unknown")
    current_display = current_cfg.get("name", current_provider)
    elements = []

    hero_image = build_card_hero_image("status", f"{Config.BOT_NAME} 模型切换")
    if hero_image:
        elements.append(hero_image)

    elements.extend(
        [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": format_model_summary(
                        current_model=current_model,
                        current_display=current_display,
                        is_default=is_default,
                    ),
                },
            },
            {
                "tag": "action",
                "layout": "trisection",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary" if current_provider == "cerebras" else "default",
                        "text": {"tag": "plain_text", "content": "Cerebras"},
                        "value": {"action": "set_ai_provider", "provider": "cerebras"},
                    },
                    {
                        "tag": "button",
                        "type": "primary" if current_provider == "groq" else "default",
                        "text": {"tag": "plain_text", "content": "Groq"},
                        "value": {"action": "set_ai_provider", "provider": "groq"},
                    },
                    {
                        "tag": "button",
                        "type": "primary" if current_provider == "deepseek" else "default",
                        "text": {"tag": "plain_text", "content": "DeepSeek"},
                        "value": {"action": "set_ai_provider", "provider": "deepseek"},
                    },
                ],
            },
            {"tag": "hr"},
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "↩ 恢复默认"},
                        "value": {"action": "set_ai_provider", "provider": "default"},
                    }
                ],
            },
        ]
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "blue",
            "title": {
                "tag": "plain_text",
                "content": f"{Config.BOT_NAME} 模型切换",
            },
        },
        "elements": elements,
    }


def build_reset_confirm_card() -> dict:
    elements = []
    hero_image = build_card_hero_image("reset", f"{Config.BOT_NAME} 重新开始主图")
    if hero_image:
        elements.append(hero_image)
    elements.extend(
        [
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "返回帮助"},
                        "value": {"action": "run_command", "command": "/help"},
                    },
                    {
                        "tag": "button",
                        "type": "danger",
                        "text": {"tag": "plain_text", "content": "确认重开"},
                        "value": {"action": "confirm_reset"},
                    },
                ],
            }
        ]
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "red",
            "title": {
                "tag": "plain_text",
                "content": f"{Config.BOT_NAME} 重新开始",
            },
        },
        "elements": elements,
    }


def build_clear_context_confirm_card() -> dict:
    elements = []
    hero_image = build_card_hero_image("reset", f"{Config.BOT_NAME} 清空上下文主图")
    if hero_image:
        elements.append(hero_image)
    elements.extend(
        [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": (
                        "**将要清空**：从下一轮开始带给模型的聊天上下文\n"
                        "**不会删除**：历史聊天记录、长期记忆、仿生记忆、用户画像、知识库"
                    ),
                },
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "返回帮助"},
                        "value": {"action": "run_command", "command": "/help"},
                    },
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "确认清空"},
                        "value": {"action": "confirm_clear_context"},
                    },
                ],
            },
        ]
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "orange",
            "title": {
                "tag": "plain_text",
                "content": f"{Config.BOT_NAME} 清空上下文",
            },
        },
        "elements": elements,
    }


def build_clear_context_done_card(model_name: str) -> dict:
    elements = []
    hero_image = build_card_hero_image("reset", f"{Config.BOT_NAME} 上下文已清空主图")
    if hero_image:
        elements.append(hero_image)
    elements.extend(
        [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": True,
                        "text": {"tag": "lark_md", "content": f"**当前模型**\n`{model_name}`"},
                    },
                    {
                        "is_short": True,
                        "text": {"tag": "lark_md", "content": "**上下文状态**\n已清空"},
                    },
                ],
            },
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "接下来聊天会像刚开一轮新对话，但历史聊天记录会保留，长期记忆和你们之间的关系记忆也都会保留。",
                },
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "继续聊天"},
                        "value": {"action": "run_command", "command": "/help"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "状态看板"},
                        "value": {"action": "run_command", "command": "/status"},
                    },
                ],
            },
        ]
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "orange",
            "title": {
                "tag": "plain_text",
                "content": f"{Config.BOT_NAME} 上下文已清空",
            },
        },
        "elements": elements,
    }


def build_reset_done_card(model_name: str) -> dict:
    elements = []
    hero_image = build_card_hero_image("reset", f"{Config.BOT_NAME} 新会话主图")
    if hero_image:
        elements.append(hero_image)
    elements.extend(
        [
            {
                "tag": "div",
                "fields": [
                    {
                        "is_short": True,
                        "text": {"tag": "lark_md", "content": f"**当前模型**\n`{model_name}`"},
                    },
                    {
                        "is_short": True,
                        "text": {"tag": "lark_md", "content": "**会话状态**\n已重新开始"},
                    },
                ],
            },
            {
                "tag": "action",
                "layout": "bisected",
                "actions": [
                    {
                        "tag": "button",
                        "type": "primary",
                        "text": {"tag": "plain_text", "content": "状态看板"},
                        "value": {"action": "run_command", "command": "/status"},
                    },
                    {
                        "tag": "button",
                        "type": "default",
                        "text": {"tag": "plain_text", "content": "帮助中心"},
                        "value": {"action": "run_command", "command": "/help"},
                    },
                ],
            },
        ]
    )
    return {
        "config": {
            "wide_screen_mode": True,
            "enable_forward": True,
        },
        "header": {
            "template": "red",
            "title": {
                "tag": "plain_text",
                "content": f"{Config.BOT_NAME} 新会话已开启",
            },
        },
        "elements": elements,
    }


__all__ = [
    "build_chat_card",
    "build_chat_current_card",
    "build_chat_rename_card",
    "build_clear_context_confirm_card",
    "build_clear_context_done_card",
    "build_help_card",
    "build_memory_audit_card",
    "build_memory_card",
    "build_model_card",
    "build_pure_mode_card",
    "build_reply_mode_card",
    "build_reset_confirm_card",
    "build_reset_done_card",
    "build_status_card",
]
