"""回复后的异步任务与告警。"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from ..ai_engine import call_ai_summarize
from ..config import Config
from ..infrastructure.feishu import send_feishu, upload_audio_v2
from ..logger import logger
from ..voice_matcher import match_voice_file
from .observation_service import observation_runtime_state
from .memory_reflection_service import reflect_on_conversation

# 后台线程池：承接反思、语音匹配等慢任务。
background_executor = ThreadPoolExecutor(max_workers=Config.EXECUTOR_MAX_WORKERS)


def send_error_alert(
    error_msg: str,
    *,
    send_feishu_fn=send_feishu,
    logger_obj=logger,
) -> None:
    """当系统崩溃时，给管理员发送飞书告警。"""
    try:
        alert_text = (
            "⚠️ 【系统告警】\n"
            f"时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"内容：{error_msg}"
        )
        admin_id = getattr(Config, "ADMIN_OPEN_ID", None)
        if admin_id:
            send_feishu_fn(admin_id, "text", {"text": alert_text})
            logger_obj.info("已发送错误告警至管理员")
    except Exception as exc:
        logger_obj.error(f"发送告警失败: {exc}")


def async_voice_reply(
    open_id,
    user_text,
    reply_text,
    summary=None,
    emotion=None,
    theme=None,
    *,
    match_voice_file_fn=match_voice_file,
    call_ai_summarize_fn=call_ai_summarize,
    upload_audio_v2_fn=upload_audio_v2,
    send_feishu_fn=send_feishu,
    logger_obj=logger,
):
    """异步语音匹配与发送。"""
    try:
        v_path = match_voice_file_fn(
            user_text,
            reply_text,
            call_ai_summarize_fn,
            summary,
            emotion,
            theme,
        )
        if v_path:
            file_key = upload_audio_v2_fn(v_path)
            if file_key:
                send_feishu_fn(open_id, "audio", {"file_key": file_key})
    except Exception as exc:
        logger_obj.error(f"异步语音回复失败: {exc}")


def async_reflect(
    open_id,
    user_text,
    reply_text,
    conversation_id=None,
    conversation_mode=None,
    *,
    reflect_on_conversation_fn=reflect_on_conversation,
    observation_runtime_state_fn=observation_runtime_state,
    logger_obj=logger,
):
    """异步调用反思引擎。"""
    try:
        if conversation_mode == "story":
            logger_obj.info(
                "🎬 剧情对话跳过现实仿生记忆反思",
                extra={"open_id": open_id, "conversation_id": conversation_id},
            )
            return
        with observation_runtime_state_fn(open_id, "reflecting"):
            reflect_on_conversation_fn(open_id, user_text, reply_text)
    except Exception as exc:
        logger_obj.error(f"仿生记忆反思失败: {exc}")
