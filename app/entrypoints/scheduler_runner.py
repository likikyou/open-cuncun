"""定时任务注册与运行入口。"""

from __future__ import annotations

import os
import schedule
import time

from ..ai_engine import call_ai, call_ai_summarize
from ..application.memory_maintenance_service import consolidate_memories, decay_and_forget
from ..application.post_reply_jobs import send_error_alert
from ..application.proactive_chat_service import (
    proactive_thought_task as _proactive_thought_task_service,
    sanitize_proactive_reply as _sanitize_proactive_reply_service,
)
from ..application.reminder_service import (
    _call_ai_with_fallback as _reminder_call_ai_with_fallback,
    brush_teeth_reminder as _brush_teeth_reminder_service,
    morning_greeting as _morning_greeting_service,
    night_reminder as _night_reminder_service,
)
from ..config import Config
from ..infrastructure.feishu import send_feishu, upload_audio_v2
from ..infrastructure.persistence.sqlite_history_repo import get_last_interaction_time, save_message
from ..logger import logger
from ..ops import backup_database_task
from ..time_utils import local_now_naive
from ..voice_matcher import match_voice_file
from ..weather import get_weather


def _sanitize_proactive_reply(reply: str) -> str:
    """清洗主动消息里的异常前缀。"""
    return _sanitize_proactive_reply_service(reply, logger=logger)


def _call_ai_with_fallback(system_prompt: str, user_prompt: str) -> str:
    """提醒任务统一走低成本 AI 调用入口。"""
    return _reminder_call_ai_with_fallback(system_prompt, user_prompt)


def _build_reminder_deps() -> dict:
    return {
        "logger": logger,
        "config": Config,
        "call_ai_with_fallback": _call_ai_with_fallback,
        "send_feishu": send_feishu,
        "send_error_alert": send_error_alert,
        "match_voice_file": match_voice_file,
        "call_ai_summarize": call_ai_summarize,
        "upload_audio_v2": upload_audio_v2,
        "get_weather": get_weather,
    }


def _build_proactive_deps() -> dict:
    return {
        "logger": logger,
        "config": Config,
        "get_last_interaction_time": get_last_interaction_time,
        "local_now_naive": local_now_naive,
        "call_ai": call_ai,
        "sanitize_reply": _sanitize_proactive_reply,
        "match_voice_file": match_voice_file,
        "call_ai_summarize": call_ai_summarize,
        "send_feishu": send_feishu,
        "send_error_alert": send_error_alert,
        "upload_audio_v2": upload_audio_v2,
        "save_message": save_message,
        "path_exists": os.path.exists,
    }


def _morning_greeting_task() -> None:
    _morning_greeting_service(deps=_build_reminder_deps())


def _night_reminder_task() -> None:
    _night_reminder_service(deps=_build_reminder_deps())


def _brush_teeth_reminder_task() -> None:
    _brush_teeth_reminder_service(deps=_build_reminder_deps())


def _memory_consolidation_task() -> None:
    count = consolidate_memories()
    logger.info(f"✅ 定时记忆整合完成，整合了 {count} 个主题")


def _memory_decay_task() -> None:
    stats = decay_and_forget()
    logger.info(f"✅ 定时记忆衰减完成: {stats}")


def _proactive_thought_task() -> None:
    _proactive_thought_task_service(deps=_build_proactive_deps())


def _build_scheduler_alert_message(job_name: str, exc: Exception) -> str:
    return f"Scheduler job failed: {job_name}\n{exc.__class__.__name__}: {exc}"


def _send_scheduler_alert(
    job_name: str,
    exc: Exception,
    *,
    logger_obj=logger,
    send_error_alert_fn=send_error_alert,
) -> None:
    try:
        send_error_alert_fn(_build_scheduler_alert_message(job_name, exc))
    except Exception as alert_exc:
        logger_obj.error(f"❌ Scheduler 告警发送失败: {alert_exc}", exc_info=True)


def run_scheduler_job(
    job_name: str,
    job_fn,
    *,
    logger_obj=logger,
    send_error_alert_fn=send_error_alert,
) -> None:
    """运行单个 scheduler job；失败时写日志并发飞书告警。"""
    try:
        job_fn()
    except Exception as exc:
        logger_obj.error(f"❌ Scheduler job 异常: {job_name}: {exc}", exc_info=True)
        _send_scheduler_alert(
            job_name,
            exc,
            logger_obj=logger_obj,
            send_error_alert_fn=send_error_alert_fn,
        )


def _wrap_scheduler_job(
    job_name: str,
    job_fn,
    *,
    logger_obj=logger,
    send_error_alert_fn=send_error_alert,
):
    def _wrapped_job():
        return run_scheduler_job(
            job_name,
            job_fn,
            logger_obj=logger_obj,
            send_error_alert_fn=send_error_alert_fn,
        )

    return _wrapped_job


def register_jobs(
    *,
    schedule_module,
    config,
    backup_task,
    morning_task,
    night_task,
    brush_teeth_task,
    memory_consolidation_task,
    memory_decay_task,
    proactive_thought_task,
    logger_obj=logger,
    send_error_alert_fn=send_error_alert,
) -> None:
    """注册全部定时任务。"""
    schedule_module.every().day.at(config.SCHEDULE_BACKUP).do(
        _wrap_scheduler_job(
            "backup_database",
            backup_task,
            logger_obj=logger_obj,
            send_error_alert_fn=send_error_alert_fn,
        )
    )
    schedule_module.every().day.at(config.SCHEDULE_MORNING).do(
        _wrap_scheduler_job(
            "morning_greeting",
            morning_task,
            logger_obj=logger_obj,
            send_error_alert_fn=send_error_alert_fn,
        )
    )
    schedule_module.every().day.at(config.SCHEDULE_NIGHT).do(
        _wrap_scheduler_job(
            "night_reminder",
            night_task,
            logger_obj=logger_obj,
            send_error_alert_fn=send_error_alert_fn,
        )
    )
    schedule_module.every().day.at(config.SCHEDULE_BRUSH_TEETH).do(
        _wrap_scheduler_job(
            "brush_teeth_reminder",
            brush_teeth_task,
            logger_obj=logger_obj,
            send_error_alert_fn=send_error_alert_fn,
        )
    )
    schedule_module.every().day.at(config.SCHEDULE_MEMORY_CONSOLIDATE).do(
        _wrap_scheduler_job(
            "memory_consolidation",
            memory_consolidation_task,
            logger_obj=logger_obj,
            send_error_alert_fn=send_error_alert_fn,
        )
    )
    schedule_module.every().day.at(config.SCHEDULE_MEMORY_DECAY).do(
        _wrap_scheduler_job(
            "memory_decay",
            memory_decay_task,
            logger_obj=logger_obj,
            send_error_alert_fn=send_error_alert_fn,
        )
    )
    schedule_module.every(30).minutes.do(
        _wrap_scheduler_job(
            "proactive_thought",
            proactive_thought_task,
            logger_obj=logger_obj,
            send_error_alert_fn=send_error_alert_fn,
        )
    )


def run_scheduler_loop(
    *,
    schedule_module,
    sleep_fn,
    logger,
    config,
    backup_task,
    morning_task,
    night_task,
    brush_teeth_task,
    memory_consolidation_task,
    memory_decay_task,
    proactive_thought_task,
    send_error_alert_fn=send_error_alert,
) -> None:
    """注册任务并运行 pending loop。"""
    register_jobs(
        schedule_module=schedule_module,
        config=config,
        backup_task=backup_task,
        morning_task=morning_task,
        night_task=night_task,
        brush_teeth_task=brush_teeth_task,
        memory_consolidation_task=memory_consolidation_task,
        memory_decay_task=memory_decay_task,
        proactive_thought_task=proactive_thought_task,
        logger_obj=logger,
        send_error_alert_fn=send_error_alert_fn,
    )

    logger.info(
        f"⏰ 定时任务已启动 | "
        f"早安:{config.SCHEDULE_MORNING} "
        f"刷牙:{config.SCHEDULE_BRUSH_TEETH} "
        f"晚安:{config.SCHEDULE_NIGHT} "
        f"备份:{config.SCHEDULE_BACKUP} "
        f"记忆整合:{config.SCHEDULE_MEMORY_CONSOLIDATE} "
        f"记忆衰减:{config.SCHEDULE_MEMORY_DECAY}"
    )

    while True:
        try:
            schedule_module.run_pending()
            sleep_fn(60)
        except Exception as exc:
            logger.error(f"定时任务循环异常: {exc}", exc_info=True)
            _send_scheduler_alert(
                "scheduler_loop",
                exc,
                logger_obj=logger,
                send_error_alert_fn=send_error_alert_fn,
            )
            sleep_fn(60)


def run_scheduler() -> None:
    """调度线程真实入口。"""
    run_scheduler_loop(
        schedule_module=schedule,
        sleep_fn=time.sleep,
        logger=logger,
        config=Config,
        backup_task=backup_database_task,
        morning_task=_morning_greeting_task,
        night_task=_night_reminder_task,
        brush_teeth_task=_brush_teeth_reminder_task,
        memory_consolidation_task=_memory_consolidation_task,
        memory_decay_task=_memory_decay_task,
        proactive_thought_task=_proactive_thought_task,
    )
