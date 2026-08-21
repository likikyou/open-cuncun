"""主动聊天任务应用服务。"""

from __future__ import annotations

import re

from ..prompt_builder import build_prompt
from .observation_service import observation_runtime_state


def sanitize_proactive_reply(reply: str, *, logger) -> str:
    """
    清洗主动消息里的异常前缀，避免偶发英文乱码污染聊天历史。
    """
    text = (reply or "").strip()
    if not text:
        return ""

    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'", "“", "”"}:
        text = text[1:-1].strip()

    first_cjk_match = re.search(r"[\u4e00-\u9fff]", text)
    if not first_cjk_match:
        return text

    prefix = text[: first_cjk_match.start()]
    if prefix:
        ascii_letters = re.findall(r"[A-Za-z]+", prefix)
        ascii_ratio = sum(ch.isascii() for ch in prefix) / max(len(prefix), 1)
        if len(ascii_letters) >= 2 and ascii_ratio >= 0.7:
            cleaned = text[first_cjk_match.start() :].strip()
            logger.warning(
                "⚠️ 主动消息检测到异常前缀，已完成清洗",
                extra={
                    "prefix_length": len(prefix),
                    "original_length": len(text),
                    "cleaned_length": len(cleaned),
                },
            )
            return cleaned

    return text


def proactive_thought_task(*, deps: dict) -> None:
    """模拟人类“想主动聊一句”的冲动。"""
    logger = deps["logger"]
    config = deps["config"]
    admin_id = getattr(config, "ADMIN_OPEN_ID", None)
    if not admin_id:
        return

    last_time = deps["get_last_interaction_time"](admin_id)
    if not last_time:
        return

    now = deps["local_now_naive"]()
    if not (9 <= now.hour <= 23):
        return

    hours_diff = (now - last_time).total_seconds() / 3600
    if hours_diff < 4:
        return

    logger.info(f"🤔 触发主动思绪机制 (距上次聊天 {hours_diff:.1f} 小时)")
    task_prompt = (
        f"【主动消息任务】\n"
        f"距离你和用户上次聊天已经过去了 {hours_diff:.1f} 个小时。\n"
        f"请遵循上述角色设定，判断现在是否适合主动跟用户说句话；内容与语气都应由角色设定决定。\n"
        f"如果有，请直接输出你想发送给用户的那句或那段话。\n"
        f"如果你觉得目前没打扰用户的必要，或者暂时不想主动，请严格且仅输出这五个大写字母：EMPTY\n"
        f"注意：字数尽量控制在 50-100 字，贴近真实的口语微聊感。不要有任何解释内容！"
    )
    build_prompt_fn = deps.get("build_prompt", build_prompt)
    prompt = f"{build_prompt_fn('[定时主动消息]')}\n\n{task_prompt}"

    try:
        with deps.get("observation_runtime_state", observation_runtime_state)(
            admin_id,
            "proactive",
        ):
            reply = deps["call_ai"](
                system_prompt=prompt,
                user_text="[定时任务：评估是否主动联系用户]",
                history=[],
                reply_mode="normal",
                user_id=admin_id,
            )

            reply = deps["sanitize_reply"](reply)
            if reply and reply != "EMPTY" and "EMPTY" not in reply:
                logger.info(
                    "💭 助手决定主动发消息",
                    extra={"reply_length": len(reply)},
                )

                voice_path = deps["match_voice_file"](
                    "主动消息",
                    reply,
                    deps["call_ai_summarize"],
                )
                deps["send_feishu"](admin_id, "text", {"text": reply})

                if voice_path and deps["path_exists"](voice_path):
                    audio_key = deps["upload_audio_v2"](voice_path)
                    if audio_key:
                        deps["send_feishu"](admin_id, "audio", {"file_key": audio_key})

                deps["save_message"](user_id=admin_id, role="assistant", content=reply)
                logger.info("✅ 主动意图对话推送完成")
            else:
                logger.info("💭 助手决定暂不主动发消息。")
    except Exception as exc:
        logger.error(f"主动思绪引擎异常: {exc}")
        send_error_alert = deps.get("send_error_alert")
        if send_error_alert:
            send_error_alert(
                f"Scheduler job failed: proactive_thought\n{exc.__class__.__name__}: {exc}"
            )
