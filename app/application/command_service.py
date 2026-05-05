"""命令处理服务。"""

from __future__ import annotations

from typing import Any, Mapping

from ..application.reset_service import clear_chat_context, clear_user_history
from ..application.observation_service import get_observation_text
from ..config import Config
from ..infrastructure.persistence.sqlite_conversation_repo import (
    create_conversation,
    ensure_default_conversation,
    get_active_conversation,
    list_conversations,
    rename_conversation,
    set_active_conversation,
    update_conversation_mode,
)
from ..infrastructure.persistence.sqlite_history_repo import get_chat_counts
from ..infrastructure.persistence.sqlite_memory_repo import (
    get_active_memories,
    get_bionic_state,
    get_memory_stats,
    mark_user_memories_forgotten,
)
from ..infrastructure.persistence.sqlite_settings_repo import (
    get_user_setting,
    set_user_setting,
)
from ..infrastructure.ai import (
    get_provider_configs,
    is_provider_available,
    resolve_active_provider,
)
from ..infrastructure.feishu import send_feishu, send_interactive_card
from ..logger import logger
from ..presentation.cards.builders import (
    build_clear_context_confirm_card,
    build_clear_context_done_card,
    build_chat_card,
    build_chat_current_card,
    build_chat_rename_card,
    build_help_card,
    build_memory_audit_card,
    build_memory_card,
    build_model_card,
    build_pure_mode_card,
    build_reply_mode_card,
    build_reset_confirm_card,
    build_reset_done_card,
    build_story_mode_card,
    build_status_card,
)
from ..domain.memory_rules import should_include_memory_in_context

_REPLY_MODE_MAP = {"1": "light", "2": "normal", "3": "qa"}
_REPLY_MODE_NAME_MAP = {
    "light": "💬 轻量闲聊",
    "normal": "💞 正常聊天",
    "qa": "🧠 问答检索",
}
_PURE_MODE_NAME_MAP = {
    "off": "⭕ 已关闭",
    "on": "🧪 已开启",
}
_LEGACY_REPLY_MODE_MAP = {"web": "qa", "all": "qa"}
_MEMORY_AUDIT_KEYWORDS = (
    "明星",
    "客户",
    "经纪人",
    "剧组",
    "红毯",
    "电影节",
    "通告",
    "行程",
    "直播间",
    "指甲样稿",
    "楼下",
    "奶茶店",
    "灯柱",
    "雨夜",
)


def _get_dep(deps: Mapping[str, Any] | None, name: str, default: Any) -> Any:
    if deps and name in deps:
        return deps[name]
    return default


def _normalize_reply_mode_setting(reply_mode: str) -> str:
    mode = (reply_mode or "normal").strip().lower()
    return _LEGACY_REPLY_MODE_MAP.get(mode, mode if mode in _REPLY_MODE_NAME_MAP else "normal")


def _normalize_pure_mode_setting(value: str) -> str:
    mode = (value or "off").strip().lower()
    return "on" if mode in {"1", "true", "on", "yes"} else "off"


def handle_command(open_id: str, command: str, *, deps: Mapping[str, Any] | None = None) -> None:
    """统一处理用户命令。"""
    parts = command.split(maxsplit=1)
    base_cmd = parts[0]
    sub_arg = parts[1].strip() if len(parts) > 1 else ""
    send_feishu_fn = _get_dep(deps, "send_feishu", send_feishu)

    cmd_map = {
        "/status": _handle_status_command,
        "/observe": _handle_observe_command,
        "/reset": _handle_reset_command,
        "/clear": _handle_clear_command,
        "/pure": _handle_pure_command,
        "/help": _handle_help_command,
        "/reply": _handle_reply_command,
        "/memory": _handle_memory_command,
        "/model": _handle_model_command,
        "/chat": _handle_chat_command,
        "/story": _handle_story_command,
    }

    handler = cmd_map.get(base_cmd)
    if handler:
        handler(open_id, sub_arg, deps=deps)
        return

    send_feishu_fn(open_id, "text", {"text": f"未知命令: {command}\n输入 /help 查看可用命令"})


def _handle_observe_command(
    open_id: str, sub_arg: str = "", *, deps: Mapping[str, Any] | None = None
) -> None:
    """处理 /observe 命令，返回实时观察文字。"""
    get_observation_text_fn = _get_dep(deps, "get_observation_text", get_observation_text)
    send_feishu_fn = _get_dep(deps, "send_feishu", send_feishu)
    logger_obj = _get_dep(deps, "logger", logger)

    force_refresh = sub_arg.strip().lower() == "refresh"
    try:
        observation_text = get_observation_text_fn(open_id, force_refresh=force_refresh)
        final_text = (
            "👁️ 【实时观察】\n\n"
            f"{observation_text}\n\n"
            "发送 `/observe refresh` 可以强制刷新一次画面。"
        )
        send_feishu_fn(open_id, "text", {"text": final_text})
        logger_obj.info(
            "👁️ 已发送实时观察文本",
            extra={"open_id": open_id, "force_refresh": force_refresh},
        )
    except Exception as exc:
        logger_obj.error(f"发送实时观察失败: {exc}")
        send_feishu_fn(
            open_id,
            "text",
            {"text": "👁️ 这会儿镜头有点糊，稍后再试试 `/observe` 吧。"},
        )


def _get_current_model_info(open_id: str | None = None):
    """获取当前配置的模型信息。"""
    resolved = resolve_active_provider(open_id, reserve_probe=False)
    provider_configs = get_provider_configs()
    provider = resolved["provider"] or Config.AI_PROVIDER
    model = resolved["model"]
    if model:
        return provider, model, resolved["is_default"]
    fallback_model = provider_configs.get(provider, {}).get("model", "unknown")
    return provider, fallback_model, resolved["is_default"]


def _handle_model_command(
    open_id: str, sub_arg: str = "", *, deps: Mapping[str, Any] | None = None
) -> None:
    """处理 /model 命令。"""
    send_feishu_fn = _get_dep(deps, "send_feishu", send_feishu)
    send_interactive_card_fn = _get_dep(deps, "send_interactive_card", send_interactive_card)
    set_user_setting_fn = _get_dep(deps, "set_user_setting", set_user_setting)
    build_model_card_fn = _get_dep(deps, "build_model_card", build_model_card)
    logger_obj = _get_dep(deps, "logger", logger)
    provider_configs = get_provider_configs()

    provider, _, is_default = _get_current_model_info(open_id)

    if sub_arg == "default":
        set_user_setting_fn(open_id, "ai_provider", "")
        default_provider = Config.AI_PROVIDER
        default_name = provider_configs.get(default_provider, {}).get("name", default_provider)
        send_feishu_fn(open_id, "text", {"text": f"✅ 已恢复全局默认模型：{default_name}。"})
        logger_obj.info(f"👤 用户 {open_id} 恢复默认模型 {default_provider}")
        return

    if sub_arg in provider_configs:
        if not is_provider_available(sub_arg):
            model_name = provider_configs[sub_arg]["name"]
            send_feishu_fn(
                open_id, "text", {"text": f"⚠️ {model_name} 当前未配置或不可用，未切换。"}
            )
            logger_obj.warning(f"👤 用户 {open_id} 尝试切换到不可用模型 {sub_arg}")
            return
        set_user_setting_fn(open_id, "ai_provider", sub_arg)
        model_name = provider_configs[sub_arg]["name"]
        send_feishu_fn(open_id, "text", {"text": f"✅ 模型已切换为 {model_name}。"})
        logger_obj.info(f"👤 用户 {open_id} 切换模型至 {sub_arg}")
        return

    card_content = build_model_card_fn(provider, is_default)
    if send_interactive_card_fn(open_id, card_content):
        logger_obj.info(f"⚙️ 已发送模型选择卡片给 {open_id}")
        return

    fallback_text = (
        "⚙️ 【模型切换】\n\n"
        f"当前模型: {provider}\n\n"
        "发送文字命令切换：\n"
        "/model cerebras\n"
        "/model groq\n"
        "/model deepseek\n"
        "/model default → 恢复 .env 默认\n"
    )
    send_feishu_fn(open_id, "text", {"text": fallback_text})


def _handle_help_command(
    open_id: str, sub_arg: str = "", *, deps: Mapping[str, Any] | None = None
) -> None:
    """处理 /help 命令，返回帮助信息。"""
    send_feishu_fn = _get_dep(deps, "send_feishu", send_feishu)
    send_interactive_card_fn = _get_dep(deps, "send_interactive_card", send_interactive_card)
    build_help_card_fn = _get_dep(deps, "build_help_card", build_help_card)
    logger_obj = _get_dep(deps, "logger", logger)

    help_card = build_help_card_fn()
    if send_interactive_card_fn(open_id, help_card):
        logger_obj.info(f"📖 已发送帮助卡片给 {open_id}")
        return

    help_text = (
        f"📖 【{Config.BOT_NAME} 命令帮助】\n\n"
        "🖥️ /status - 查看数据看板\n"
        "   显示机器人信息、模型、API状态等\n\n"
        "👁️ /observe - 悄悄看一眼\n"
        "   用第三人称画面描述助手这会儿在干嘛\n\n"
        "🤖 /model - 切换大模型\n"
        "   支持切换 Cerebras / Groq / DeepSeek，也可恢复默认\n\n"
        "🔄 /reset - 开启新对话\n"
        "   清除历史记录，重新开始聊天\n\n"
        "🧼 /clear - 清空上下文\n"
        "   只清除最近对话，不影响长期记忆\n\n"
        "💬 /reply - 设置回复模式\n"
        "   会弹出按钮卡片，点一下就能切换\n\n"
        "🧪 /pure - 净聊测试开关\n"
        "   临时关闭长期记忆和仿生记忆，便于测回复\n\n"
        "🗂️ /chat - 多重对话\n"
        "   新建、查看和切换不同聊天上下文\n\n"
        "🎬 /story - 剧情模式\n"
        "   开启独立剧情对话，剧情不会写入现实仿生记忆\n\n"
        "🧠 /memory - 查看仿生记忆\n"
        "   查看助手的记忆状态看板\n\n"
        "📖 /help - 查看帮助信息\n"
        "   显示所有可用命令"
    )

    send_feishu_fn(open_id, "text", {"text": help_text})
    logger_obj.info(f"📖 帮助卡片发送失败，已回退文字帮助给 {open_id}")


def _handle_status_command(
    open_id: str, sub_arg: str = "", *, deps: Mapping[str, Any] | None = None
) -> None:
    """处理 /status 命令，返回数据看板。"""
    get_chat_counts_fn = _get_dep(deps, "get_chat_counts", get_chat_counts)
    get_user_setting_fn = _get_dep(deps, "get_user_setting", get_user_setting)
    send_feishu_fn = _get_dep(deps, "send_feishu", send_feishu)
    send_interactive_card_fn = _get_dep(deps, "send_interactive_card", send_interactive_card)
    build_status_card_fn = _get_dep(deps, "build_status_card", build_status_card)
    logger_obj = _get_dep(deps, "logger", logger)

    try:
        today_count, total_count = get_chat_counts_fn()
        provider, model_name, _ = _get_current_model_info(open_id)

        token_status = "✅ 已配置"
        if provider == "cerebras" and not Config.CEREBRAS_API_KEY:
            token_status = "❌ 未配置"
        elif provider == "groq" and not Config.GROQ_API_KEY:
            token_status = "❌ 未配置"
        elif provider == "deepseek" and not Config.DEEPSEEK_API_KEY:
            token_status = "❌ 未配置"

        context_chars = 12
        deep_thinking = "✅ 已开启" if Config.DEEP_THINKING else "❌ 未开启"

        reply_mode_raw = get_user_setting_fn(open_id, "reply_mode", "normal")
        reply_mode = _normalize_reply_mode_setting(reply_mode_raw)
        reply_mode_display = _REPLY_MODE_NAME_MAP.get(reply_mode, reply_mode)
        pure_mode = _normalize_pure_mode_setting(get_user_setting_fn(open_id, "pure_mode", "off"))
        pure_mode_display = _PURE_MODE_NAME_MAP[pure_mode]

        status_card = build_status_card_fn(
            provider=provider,
            model_name=model_name,
            token_status=token_status,
            deep_thinking=deep_thinking,
            reply_mode_display=reply_mode_display,
            pure_mode_display=pure_mode_display,
            today_count=today_count,
            total_count=total_count,
        )
        if send_interactive_card_fn(open_id, status_card):
            logger_obj.info(f"📊 已发送状态卡片给 {open_id}")
            return

        status_text = (
            f"📊 【{Config.BOT_NAME} 数据看板】\n\n"
            f"🤖 机器人：{Config.BOT_NAME}\n"
            f"🧠 使用模型：{model_name} ({provider})\n"
            f"🔑 API Token：{token_status}\n"
            f"📝 上下文：{context_chars} 条对话\n"
            f"💭 深度思考：{deep_thinking}\n"
            f"⚙️ 回复模式：{reply_mode_display}\n"
            f"🧪 净聊测试：{pure_mode_display}\n"
            f"💬 今日对话：{today_count} 次\n"
            f"📈 总对话数：{total_count} 次"
        )

        send_feishu_fn(open_id, "text", {"text": status_text})
        logger_obj.info(f"📊 状态卡片发送失败，已回退文字看板给 {open_id}")
    except Exception as exc:
        logger_obj.error(f"发送状态看板失败: {exc}")


def _handle_reset_command(
    open_id: str, sub_arg: str = "", *, deps: Mapping[str, Any] | None = None
) -> None:
    """处理 /reset 命令，清除历史记录并开启新对话。"""
    clear_user_history_fn = _get_dep(deps, "clear_user_history", clear_user_history)
    send_feishu_fn = _get_dep(deps, "send_feishu", send_feishu)
    send_interactive_card_fn = _get_dep(deps, "send_interactive_card", send_interactive_card)
    build_reset_confirm_card_fn = _get_dep(
        deps, "build_reset_confirm_card", build_reset_confirm_card
    )
    build_reset_done_card_fn = _get_dep(deps, "build_reset_done_card", build_reset_done_card)
    logger_obj = _get_dep(deps, "logger", logger)

    try:
        if sub_arg != "confirm":
            reset_card = build_reset_confirm_card_fn()
            if send_interactive_card_fn(open_id, reset_card):
                logger_obj.info(f"🔄 已发送重开确认卡片给 {open_id}")
                return
            send_feishu_fn(
                open_id,
                "text",
                {"text": "⚠️ 卡片发送失败。若确认重新开始，请发送 `/reset confirm`。"},
            )
            logger_obj.info(f"🔄 重开确认卡片发送失败，已回退文字确认给 {open_id}")
            return

        clear_user_history_fn(open_id)
        _, model_name, _ = _get_current_model_info(open_id)
        reset_done_card = build_reset_done_card_fn(model_name)
        if send_interactive_card_fn(open_id, reset_done_card):
            logger_obj.info(f"🔄 已为用户 {open_id} 开启新会话（卡片）")
            return

        reset_text = f"✨ 【新会话已开启】\n🧠 当前模型：{model_name}"
        send_feishu_fn(open_id, "text", {"text": reset_text})
        logger_obj.info(f"🔄 已为用户 {open_id} 开启新会话")
    except Exception as exc:
        logger_obj.error(f"重置会话失败: {exc}")


def _handle_clear_command(
    open_id: str, sub_arg: str = "", *, deps: Mapping[str, Any] | None = None
) -> None:
    """处理 /clear 命令，仅清空当前聊天上下文。"""
    clear_chat_context_fn = _get_dep(deps, "clear_chat_context", clear_chat_context)
    send_feishu_fn = _get_dep(deps, "send_feishu", send_feishu)
    send_interactive_card_fn = _get_dep(deps, "send_interactive_card", send_interactive_card)
    build_clear_context_confirm_card_fn = _get_dep(
        deps,
        "build_clear_context_confirm_card",
        build_clear_context_confirm_card,
    )
    build_clear_context_done_card_fn = _get_dep(
        deps,
        "build_clear_context_done_card",
        build_clear_context_done_card,
    )
    logger_obj = _get_dep(deps, "logger", logger)

    try:
        if sub_arg != "confirm":
            clear_card = build_clear_context_confirm_card_fn()
            if send_interactive_card_fn(open_id, clear_card):
                logger_obj.info(f"🧼 已发送清空上下文确认卡片给 {open_id}")
                return
            send_feishu_fn(
                open_id,
                "text",
                {"text": "⚠️ 卡片发送失败。若确认清空上下文，请发送 `/clear confirm`。"},
            )
            logger_obj.info(f"🧼 清空上下文确认卡片发送失败，已回退文字确认给 {open_id}")
            return

        clear_chat_context_fn(open_id)
        _, model_name, _ = _get_current_model_info(open_id)
        done_card = build_clear_context_done_card_fn(model_name)
        if send_interactive_card_fn(open_id, done_card):
            logger_obj.info(f"🧼 已为用户 {open_id} 清空上下文（卡片）")
            return

        done_text = (
            f"🧼 【上下文已清空】\n🧠 当前模型：{model_name}\n"
            "💡 历史聊天记录、长期记忆和仿生记忆仍然保留。"
        )
        send_feishu_fn(open_id, "text", {"text": done_text})
        logger_obj.info(f"🧼 已为用户 {open_id} 清空上下文")
    except Exception as exc:
        logger_obj.error(f"清空上下文失败: {exc}")


def _handle_chat_command(
    open_id: str, sub_arg: str = "", *, deps: Mapping[str, Any] | None = None
) -> None:
    """处理 /chat 命令，管理同一飞书私聊里的多个会话上下文。"""
    create_conversation_fn = _get_dep(deps, "create_conversation", create_conversation)
    get_active_conversation_fn = _get_dep(
        deps, "get_active_conversation", get_active_conversation
    )
    list_conversations_fn = _get_dep(deps, "list_conversations", list_conversations)
    set_active_conversation_fn = _get_dep(
        deps, "set_active_conversation", set_active_conversation
    )
    rename_conversation_fn = _get_dep(deps, "rename_conversation", rename_conversation)
    send_feishu_fn = _get_dep(deps, "send_feishu", send_feishu)
    send_interactive_card_fn = _get_dep(deps, "send_interactive_card", send_interactive_card)
    build_chat_card_fn = _get_dep(deps, "build_chat_card", build_chat_card)
    build_chat_current_card_fn = _get_dep(
        deps, "build_chat_current_card", build_chat_current_card
    )
    build_chat_rename_card_fn = _get_dep(deps, "build_chat_rename_card", build_chat_rename_card)
    logger_obj = _get_dep(deps, "logger", logger)

    parts = sub_arg.split(maxsplit=1)
    action = parts[0].strip().lower() if parts else ""
    value = parts[1].strip() if len(parts) > 1 else ""

    if action == "new":
        story_markers = ("剧情", "故事", "story")
        is_story = any((value or "").lower().startswith(marker) for marker in story_markers)
        conversation = create_conversation_fn(
            open_id,
            value or "新对话",
            mode="story" if is_story else "normal",
            summary=value if is_story else "",
        )
        if conversation:
            title = conversation.get("title", "新对话")
            mode_label = "剧情对话" if conversation.get("mode") == "story" else "新对话"
            current_card = build_chat_current_card_fn(conversation)
            if send_interactive_card_fn(open_id, current_card):
                logger_obj.info(
                    "🗂️ 已创建并切换新对话",
                    extra={"open_id": open_id, "conversation_id": conversation.get("id")},
                )
                return
            send_feishu_fn(
                open_id,
                "text",
                {"text": f"🗂️ 已开启{mode_label}：{title}\n接下来我只会带这个对话里的上下文。"},
            )
            logger_obj.info(
                "🗂️ 已创建并切换新对话",
                extra={"open_id": open_id, "conversation_id": conversation.get("id")},
            )
            return
        send_feishu_fn(open_id, "text", {"text": "新建对话失败了，等下再试。"})
        return

    if action == "switch" and value:
        conversation = set_active_conversation_fn(open_id, value)
        if conversation:
            title = conversation.get("title", "未命名对话")
            current_card = build_chat_current_card_fn(conversation)
            if send_interactive_card_fn(open_id, current_card):
                logger_obj.info(
                    "🗂️ 已切换对话",
                    extra={"open_id": open_id, "conversation_id": conversation.get("id")},
                )
                return
            send_feishu_fn(open_id, "text", {"text": f"已切回对话：{title}。"})
            logger_obj.info(
                "🗂️ 已切换对话",
                extra={"open_id": open_id, "conversation_id": conversation.get("id")},
            )
            return
        send_feishu_fn(open_id, "text", {"text": "没找到这个对话，可能已经被清掉了。"})
        return

    if action == "rename":
        active = get_active_conversation_fn(open_id)
        active_id = active.get("id")
        if not active_id:
            send_feishu_fn(open_id, "text", {"text": "当前还没有可重命名的对话。"})
            return
        if not value:
            rename_card = build_chat_rename_card_fn(active)
            if send_interactive_card_fn(open_id, rename_card):
                logger_obj.info(f"✏️ 已发送对话重命名卡片给 {open_id}")
                return
            send_feishu_fn(
                open_id,
                "text",
                {"text": "发送 `/chat rename 新标题` 就能重命名当前对话。"},
            )
            return
        conversation = rename_conversation_fn(open_id, active_id, value)
        title = conversation.get("title") if conversation else ""
        if title:
            current_card = build_chat_current_card_fn(conversation)
            if send_interactive_card_fn(open_id, current_card):
                return
            send_feishu_fn(open_id, "text", {"text": f"当前对话已改名为：{title}。"})
            return
        send_feishu_fn(open_id, "text", {"text": "重命名失败了，等下再试。"})
        return

    if action == "current":
        active = get_active_conversation_fn(open_id)
        title = active.get("title", "日常聊天")
        current_card = build_chat_current_card_fn(active)
        if send_interactive_card_fn(open_id, current_card):
            logger_obj.info(f"📍 已发送当前对话卡片给 {open_id}")
            return
        send_feishu_fn(open_id, "text", {"text": f"当前对话：{title}"})
        return

    conversations = list_conversations_fn(open_id, limit=8)
    active = get_active_conversation_fn(open_id)
    active_id = str(active.get("id") or "")
    chat_card = build_chat_card_fn(conversations, active_id)
    if send_interactive_card_fn(open_id, chat_card):
        logger_obj.info(f"🗂️ 已发送多重对话卡片给 {open_id}")
        return

    fallback_lines = ["🗂️ 【多重对话】", "", "文字命令：", "/chat new 标题 → 新建对话", "/chat current → 当前对话"]
    if conversations:
        fallback_lines.extend(["", "最近对话："])
        for item in conversations[:8]:
            mark = "当前 " if item.get("id") == active_id else ""
            fallback_lines.append(
                f"- {mark}{item.get('title', '未命名对话')}：/chat switch {item.get('id')}"
            )
    send_feishu_fn(open_id, "text", {"text": "\n".join(fallback_lines)})
    logger_obj.info(f"🗂️ 多重对话卡片发送失败，已回退文字列表给 {open_id}")


def _default_story_scene() -> str:
    return "雨夜，她下班后突然出现在你楼下，嘴上说只是顺路，伞沿却一直往你这边偏。"


def _story_title_from_scene(scene: str) -> str:
    clean_scene = " ".join((scene or "").strip().split())
    if not clean_scene:
        return "剧情：雨夜楼下"
    if clean_scene.startswith("剧情"):
        return clean_scene[:40]
    return f"剧情：{clean_scene[:30]}"


def _handle_story_command(
    open_id: str, sub_arg: str = "", *, deps: Mapping[str, Any] | None = None
) -> None:
    """处理 /story 命令，把剧情模式绑定到独立会话。"""
    create_conversation_fn = _get_dep(deps, "create_conversation", create_conversation)
    ensure_default_conversation_fn = _get_dep(
        deps, "ensure_default_conversation", ensure_default_conversation
    )
    get_active_conversation_fn = _get_dep(
        deps, "get_active_conversation", get_active_conversation
    )
    set_active_conversation_fn = _get_dep(
        deps, "set_active_conversation", set_active_conversation
    )
    update_conversation_mode_fn = _get_dep(
        deps, "update_conversation_mode", update_conversation_mode
    )
    send_feishu_fn = _get_dep(deps, "send_feishu", send_feishu)
    send_interactive_card_fn = _get_dep(deps, "send_interactive_card", send_interactive_card)
    build_story_mode_card_fn = _get_dep(deps, "build_story_mode_card", build_story_mode_card)
    logger_obj = _get_dep(deps, "logger", logger)

    parts = sub_arg.split(maxsplit=1)
    action = parts[0].strip().lower() if parts else ""
    scene = parts[1].strip() if len(parts) > 1 else ""

    if action == "on":
        scene = scene or _default_story_scene()
        active = get_active_conversation_fn(open_id)
        if active.get("mode") == "story":
            conversation = update_conversation_mode_fn(
                open_id,
                active["id"],
                mode="story",
                summary=scene,
            )
        else:
            conversation = create_conversation_fn(
                open_id,
                _story_title_from_scene(scene),
                mode="story",
                summary=scene,
            )
        if conversation:
            story_card = build_story_mode_card_fn(conversation)
            if send_interactive_card_fn(open_id, story_card):
                logger_obj.info(
                    "🎬 已开启剧情模式",
                    extra={"open_id": open_id, "conversation_id": conversation.get("id")},
                )
                return
            send_feishu_fn(
                open_id,
                "text",
                {
                    "text": (
                        f"🎬 剧情模式已开启：{conversation.get('title', '剧情对话')}\n"
                        f"设定：{scene}\n"
                        "这个剧情只存在于当前对话里，不会写进现实记忆。"
                    )
                },
            )
            logger_obj.info(
                "🎬 已开启剧情模式",
                extra={"open_id": open_id, "conversation_id": conversation.get("id")},
            )
            return
        send_feishu_fn(open_id, "text", {"text": "剧情模式开启失败了，等下再试。"})
        return

    if action == "off":
        default = ensure_default_conversation_fn(open_id)
        default_id = default.get("id")
        if default_id:
            default = set_active_conversation_fn(open_id, default_id) or default
        story_card = build_story_mode_card_fn(default)
        if send_interactive_card_fn(open_id, story_card):
            logger_obj.info(f"🎬 用户 {open_id} 退出剧情模式")
            return
        send_feishu_fn(open_id, "text", {"text": "🎬 已退出剧情模式，切回日常聊天。"})
        logger_obj.info(f"🎬 用户 {open_id} 退出剧情模式")
        return

    if action in {"status", "current"}:
        active = get_active_conversation_fn(open_id)
        story_card = build_story_mode_card_fn(active)
        if send_interactive_card_fn(open_id, story_card):
            logger_obj.info(f"🎬 已发送剧情状态卡片给 {open_id}")
            return
        status = "剧情模式" if active.get("mode") == "story" else "普通对话"
        scene_text = active.get("summary") or "无剧情设定"
        send_feishu_fn(
            open_id,
            "text",
            {"text": f"当前对话：{active.get('title', '日常聊天')}\n模式：{status}\n设定：{scene_text}"},
        )
        return

    active = get_active_conversation_fn(open_id)
    story_card = build_story_mode_card_fn(active)
    if send_interactive_card_fn(open_id, story_card):
        logger_obj.info(f"🎬 已发送剧情模式卡片给 {open_id}")
        return

    fallback_text = (
        "🎬 【剧情模式】\n\n"
        "/story on 设定 → 新建并进入剧情对话\n"
        "/story off → 退出剧情，切回日常聊天\n"
        "/story status → 查看当前剧情状态"
    )
    send_feishu_fn(open_id, "text", {"text": fallback_text})
    logger_obj.info(f"🎬 剧情模式卡片发送失败，已回退文字菜单给 {open_id}")


def _handle_pure_command(
    open_id: str, sub_arg: str = "", *, deps: Mapping[str, Any] | None = None
) -> None:
    """处理 /pure 命令，切换净聊测试模式。"""
    get_user_setting_fn = _get_dep(deps, "get_user_setting", get_user_setting)
    set_user_setting_fn = _get_dep(deps, "set_user_setting", set_user_setting)
    send_feishu_fn = _get_dep(deps, "send_feishu", send_feishu)
    send_interactive_card_fn = _get_dep(deps, "send_interactive_card", send_interactive_card)
    build_pure_mode_card_fn = _get_dep(deps, "build_pure_mode_card", build_pure_mode_card)
    logger_obj = _get_dep(deps, "logger", logger)

    current_mode = _normalize_pure_mode_setting(get_user_setting_fn(open_id, "pure_mode", "off"))

    if sub_arg in {"on", "off"}:
        set_user_setting_fn(open_id, "pure_mode", sub_arg)
        confirm_text = (
            "🧪 净聊测试已开启：接下来会临时关闭长期记忆和仿生记忆。"
            if sub_arg == "on"
            else "⭕ 净聊测试已关闭：已恢复长期记忆和仿生记忆。"
        )
        send_feishu_fn(open_id, "text", {"text": confirm_text})
        logger_obj.info(f"🧪 用户 {open_id} 切换净聊测试模式至 {sub_arg}")
        return

    card_content = build_pure_mode_card_fn(current_mode == "on")
    if send_interactive_card_fn(open_id, card_content):
        logger_obj.info(f"🧪 已发送净聊测试卡片给 {open_id}")
        return

    current_display = _PURE_MODE_NAME_MAP[current_mode]
    fallback_text = (
        "🧪 【净聊测试】\n\n"
        f"当前状态: {current_display}\n\n"
        "卡片发送失败了，你也可以继续用文字命令：\n"
        "/pure on → 开启净聊测试\n"
        "/pure off → 关闭净聊测试"
    )
    send_feishu_fn(open_id, "text", {"text": fallback_text})
    logger_obj.info(f"🧪 净聊测试卡片发送失败，已回退文字菜单给 {open_id}")


def _handle_reply_command(
    open_id: str, sub_arg: str = "", *, deps: Mapping[str, Any] | None = None
) -> None:
    """处理 /reply 命令。"""
    get_user_setting_fn = _get_dep(deps, "get_user_setting", get_user_setting)
    set_user_setting_fn = _get_dep(deps, "set_user_setting", set_user_setting)
    send_feishu_fn = _get_dep(deps, "send_feishu", send_feishu)
    send_interactive_card_fn = _get_dep(deps, "send_interactive_card", send_interactive_card)
    build_reply_mode_card_fn = _get_dep(deps, "build_reply_mode_card", build_reply_mode_card)
    logger_obj = _get_dep(deps, "logger", logger)

    current_mode_raw = get_user_setting_fn(open_id, "reply_mode", "normal")
    current_mode = _normalize_reply_mode_setting(current_mode_raw)

    if sub_arg in _REPLY_MODE_MAP:
        new_mode = _REPLY_MODE_MAP[sub_arg]
        set_user_setting_fn(open_id, "reply_mode", new_mode)
        confirm_text = f"✅ 设置成功！现在已切换为 {_REPLY_MODE_NAME_MAP[new_mode]} 模式。"
        send_feishu_fn(open_id, "text", {"text": confirm_text})
        logger_obj.info(f"👤 用户 {open_id} 切换模式至 {new_mode}")
        return

    card_content = build_reply_mode_card_fn(current_mode)
    if send_interactive_card_fn(open_id, card_content):
        logger_obj.info(f"⚙️ 已发送模式选择卡片给 {open_id}")
        return

    current_display = _REPLY_MODE_NAME_MAP.get(current_mode, current_mode)
    fallback_text = (
        "⚙️ 【回复模式设置】\n\n"
        f"当前模式: {current_display}\n\n"
        "卡片发送失败了，你也可以继续用文字命令：\n"
        "/reply 1 → 💬 轻量闲聊\n"
        "/reply 2 → 💞 正常聊天\n"
        "/reply 3 → 🧠 问答检索"
    )
    send_feishu_fn(open_id, "text", {"text": fallback_text})
    logger_obj.info(f"⚙️ 卡片发送失败，已回退文字菜单给 {open_id}")


def _memory_audit_reason(content: str) -> str:
    matched = [keyword for keyword in _MEMORY_AUDIT_KEYWORDS if keyword in (content or "")]
    if matched:
        return "命中：" + "、".join(matched[:4])
    return "像是只来自角色临场发挥"


def _get_memory_audit_candidates(
    open_id: str,
    get_active_memories_fn,
    *,
    scan_limit: int = 300,
    display_limit: int = 8,
) -> list[dict]:
    memories = get_active_memories_fn(open_id, limit=scan_limit)
    candidates = []
    for memory in memories:
        content = str(memory.get("content") or "")
        if not content:
            continue
        if should_include_memory_in_context("", content):
            continue
        candidate = dict(memory)
        candidate["reason"] = _memory_audit_reason(content)
        candidates.append(candidate)
    candidates.sort(key=lambda item: int(item.get("id") or 0), reverse=True)
    return candidates[:display_limit]


def _handle_memory_command(
    open_id: str, sub_arg: str = "", *, deps: Mapping[str, Any] | None = None
) -> None:
    """处理 /memory 命令，查看仿生记忆状态看板。"""
    get_active_memories_fn = _get_dep(deps, "get_active_memories", get_active_memories)
    get_memory_stats_fn = _get_dep(deps, "get_memory_stats", get_memory_stats)
    get_bionic_state_fn = _get_dep(deps, "get_bionic_state", get_bionic_state)
    mark_user_memories_forgotten_fn = _get_dep(
        deps, "mark_user_memories_forgotten", mark_user_memories_forgotten
    )
    send_feishu_fn = _get_dep(deps, "send_feishu", send_feishu)
    send_interactive_card_fn = _get_dep(deps, "send_interactive_card", send_interactive_card)
    build_memory_audit_card_fn = _get_dep(
        deps, "build_memory_audit_card", build_memory_audit_card
    )
    build_memory_card_fn = _get_dep(deps, "build_memory_card", build_memory_card)
    logger_obj = _get_dep(deps, "logger", logger)

    try:
        parts = sub_arg.split(maxsplit=1)
        action = parts[0].strip().lower() if parts else ""
        value = parts[1].strip() if len(parts) > 1 else ""

        if action == "forget" and value.isdigit():
            affected = mark_user_memories_forgotten_fn(open_id, [int(value)])
            candidates = _get_memory_audit_candidates(open_id, get_active_memories_fn)
            audit_card = build_memory_audit_card_fn(candidates)
            if send_interactive_card_fn(open_id, audit_card):
                logger_obj.info(
                    "🧹 已处理记忆审核项",
                    extra={"open_id": open_id, "memory_id": int(value), "affected": affected},
                )
                return
            result_text = "已标记遗忘。" if affected else "没有找到这条可处理的活跃记忆。"
            send_feishu_fn(open_id, "text", {"text": result_text})
            return

        if action == "audit":
            candidates = _get_memory_audit_candidates(open_id, get_active_memories_fn)
            audit_card = build_memory_audit_card_fn(candidates)
            if send_interactive_card_fn(open_id, audit_card):
                logger_obj.info(
                    "🧹 已发送记忆审核卡片",
                    extra={"open_id": open_id, "candidate_count": len(candidates)},
                )
                return
            if not candidates:
                send_feishu_fn(open_id, "text", {"text": "记忆审核完成：没有发现明显的剧情污染候选。"})
                return
            fallback_lines = ["🧹 【记忆审核】", "疑似剧情污染候选："]
            for item in candidates:
                fallback_lines.append(f"- #{item.get('id')} {item.get('content', '')[:80]}")
            send_feishu_fn(open_id, "text", {"text": "\n".join(fallback_lines)})
            return

        stats = get_memory_stats_fn(open_id)
        if not stats:
            send_feishu_fn(
                open_id, "text", {"text": "🧠 我脑子里还没记住什么有趣的事呢，多跟我聊聊吧～"}
            )
            return

        state = get_bionic_state_fn(open_id)
        active = stats.get("active", 0)
        consolidated = stats.get("consolidated", 0)
        forgotten = stats.get("forgotten", 0)
        avg_strength = stats.get("avg_strength", 0.0)
        top_memories = stats.get("top_memories", [])

        memory_card = build_memory_card_fn(stats, state)
        if send_interactive_card_fn(open_id, memory_card):
            logger_obj.info(f"🧠 已发送记忆卡片给 {open_id}")
            return

        strength_bar = "█" * int(avg_strength * 10) + "░" * (10 - int(avg_strength * 10))
        memory_text = (
            f"🧠 【{Config.BOT_NAME} 仿生记忆看板】\n\n"
            f"🟢 活跃记忆：{active} 条\n"
            f"🔵 已整合：{consolidated} 条\n"
            f"⚪ 已遗忘：{forgotten} 条\n"
            f"📊 平均强度：[{strength_bar}] {avg_strength:.0%}\n"
        )

        if top_memories:
            memory_text += "\n✨ 最重要的记忆：\n"
            for index, memory in enumerate(top_memories, 1):
                importance = memory.get("importance", 0)
                content = memory.get("content", "")[:60]
                memory_text += f"  {index}. [{importance:.0%}] {content}\n"

        memory_text += (
            "\n━━━━━━━━━━━━━━━\n"
            "💡 每次对话后自动反思\n"
            "🌙 凌晨自动整合同主题记忆\n"
            "🌿 低重要度记忆会自然淡化"
        )

        send_feishu_fn(open_id, "text", {"text": memory_text})
        logger_obj.info(f"🧠 已发送记忆看板给 {open_id}")
    except Exception as exc:
        logger_obj.error(f"记忆看板失败: {exc}")
        send_feishu_fn(open_id, "text", {"text": "❤️ 我脑子里暂时有点乱，晚点再整理好再给你看哦～"})
