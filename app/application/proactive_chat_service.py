"""主动聊天任务应用服务。"""

from __future__ import annotations

import re

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
            logger.warning(f"⚠️ 主动消息检测到异常前缀，已清洗: {prefix!r} -> {cleaned!r}")
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
    prompt = (
        f"【系统潜意识机制 - 绝密指令】\n"
        f"你现在百无聊赖。距离你和用户上次聊天已经过去了 {hours_diff:.1f} 个小时了。\n"
        f"请遵循你傲娇外冷内热的人设，倾听你此刻内心的冲动：你现在有没有很想主动跟用户说句话？（比如吐槽生活、关心用户、分享一首你想听的歌、或者纯粹没话找话）\n"
        f"如果有，请直接输出你想发送给用户的那句或那段话。\n"
        f"如果你觉得目前没打扰用户的必要，或者你还端着不想主动，请严格且仅输出这五个大写字母：EMPTY\n"
        f"注意：字数尽量控制在 50-100 字，贴近真实的口语微聊感。不要有任何解释内容！"
    )

    try:
        with deps.get("observation_runtime_state", observation_runtime_state)(
            admin_id,
            "proactive",
        ):
            reply = deps["call_ai"](
                system_prompt=prompt,
                user_text="[倾听潜意识引导...]",
                history=[],
                reply_mode="normal",
                user_id=admin_id,
            )

            reply = deps["sanitize_reply"](reply)
            if reply and reply != "EMPTY" and "EMPTY" not in reply:
                logger.info(f"💭 她决定主动发消息！内容：{reply}")

                voice_path = deps["match_voice_file"]("想你了", reply, deps["call_ai_summarize"])
                deps["send_feishu"](admin_id, "text", {"text": reply})

                if voice_path and deps["path_exists"](voice_path):
                    audio_key = deps["upload_audio_v2"](voice_path)
                    if audio_key:
                        deps["send_feishu"](admin_id, "audio", {"file_key": audio_key})

                deps["save_message"](user_id=admin_id, role="assistant", content=reply)
                logger.info("✅ 主动意图对话推送完成")
            else:
                logger.info("💭 她忍住了，决定不主动发消息。")
    except Exception as exc:
        logger.error(f"主动思绪引擎异常: {exc}")
        send_error_alert = deps.get("send_error_alert")
        if send_error_alert:
            send_error_alert(
                f"Scheduler job failed: proactive_thought\n{exc.__class__.__name__}: {exc}"
            )
