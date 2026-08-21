"""提醒任务应用服务。"""

from __future__ import annotations

from ..prompt_builder import build_prompt
from .memory_reflection_service import call_low_cost_ai
from .observation_service import observation_runtime_state


def _call_ai_with_fallback(system_prompt: str, user_prompt: str) -> str:
    """提醒任务统一走低成本 AI 调用入口。"""
    return call_low_cost_ai(system_prompt, user_prompt, max_tokens=1000)


def execute_reminder_task(
    task_name: str,
    system_prompt: str,
    user_prompt: str,
    fallback_text: str,
    observation_scene_hint: str = "",
    *,
    deps: dict,
) -> None:
    """通用提醒任务执行逻辑。"""
    logger = deps["logger"]
    config = deps["config"]
    build_prompt_fn = deps.get("build_prompt", build_prompt)
    admin_id = config.ADMIN_OPEN_ID
    if not admin_id:
        logger.error(f"❌ 未配置 ADMIN_OPEN_ID，跳过 {task_name}")
        return

    try:
        with deps.get("observation_runtime_state", observation_runtime_state)(
            admin_id,
            "reminder",
            scene_hint=observation_scene_hint,
        ):
            persona_prompt = build_prompt_fn(user_prompt)
            effective_system_prompt = f"{persona_prompt}\n\n【定时提醒任务】\n{system_prompt}"
            text = deps["call_ai_with_fallback"](effective_system_prompt, user_prompt)
            if not text or "我有点累了" in text or len(text) < 5:
                text = fallback_text
                logger.warning(f"⚠️ {task_name} AI 生成失败或内容过短，使用兜底文案")

            deps["send_feishu"](admin_id, "text", {"text": text})

            voice_path = deps["match_voice_file"](user_prompt, text, deps["call_ai_summarize"])
            if voice_path:
                file_key = deps["upload_audio_v2"](voice_path)
                if file_key:
                    deps["send_feishu"](admin_id, "audio", {"file_key": file_key})

        logger.info(f"✅ {task_name} 执行成功")
    except Exception as exc:
        logger.error(f"❌ {task_name} 执行异常: {exc}")
        send_error_alert = deps.get("send_error_alert")
        if send_error_alert:
            send_error_alert(f"Scheduler job failed: {task_name}\n{exc.__class__.__name__}: {exc}")


def morning_greeting(*, deps: dict) -> None:
    """早晨起床提醒（含天气）。"""
    config = deps["config"]
    weather_location = getattr(config, "DEFAULT_WEATHER_LOCATION", "北京")
    try:
        weather_info = deps["get_weather"]()
    except Exception:
        weather_info = "天气查询失败"

    system_prompt = (
        "在不改变上述角色设定的前提下，不新增或推断角色的性格、性别或与用户的关系。 "
        "根据提供的天气信息生成一段早晨起床提醒。 "
        "内容必须包括：1. 早晨问候 2. 今天的天气变化 3. 针对天气的穿衣或出行建议 "
        "4. 对新一天的简短鼓励。字数控制在100字以内，表达自然。"
    )
    user_prompt = (
        f"用户目前在{weather_location}，现在的天气概况是：{weather_info}。请告诉用户该起床啦！"
    )
    fallback_text = (
        f"早上好，现在是早上9点。天气是：{weather_info}。请根据天气安排穿衣和出行，祝你今天顺利。"
    )

    execute_reminder_task(
        "早晨提醒",
        system_prompt,
        user_prompt,
        fallback_text,
        "助手刚从睡意中清醒，拿起手机把早安和天气一点点发给用户",
        deps=deps,
    )


def night_reminder(*, deps: dict) -> None:
    """凌晨晚安提醒。"""
    system_prompt = (
        "在不改变上述角色设定的前提下，不新增或推断角色的性格、性别或与用户的关系。 "
        "现在是凌晨12点，用户还没睡。生成一段晚安提醒，提醒用户早点休息并避免继续熬夜。 "
        "字数控制在50字左右，表达自然。"
    )
    user_prompt = "提醒用户已经很晚了，该早点休息。"
    fallback_text = "已经很晚了，尽量别再熬夜，早点休息。祝你睡个好觉。"

    execute_reminder_task(
        "深夜提醒",
        system_prompt,
        user_prompt,
        fallback_text,
        "夜深了，助手拿起手机，准备提醒用户该休息了",
        deps=deps,
    )


def brush_teeth_reminder(*, deps: dict) -> None:
    """晚上刷牙提醒。"""
    system_prompt = (
        "在不改变上述角色设定的前提下，不新增或推断角色的性格、性别或与用户的关系。 "
        "现在是晚上10点，提醒用户刷牙并准备睡觉。字数控制在50字以内，表达自然。"
    )
    user_prompt = "提醒用户刷牙并准备睡觉。"
    fallback_text = "已经晚上10点了，记得刷牙并准备休息。"

    execute_reminder_task(
        "刷牙提醒",
        system_prompt,
        user_prompt,
        fallback_text,
        "助手看了眼时间，拿起手机提醒用户刷牙并准备睡觉",
        deps=deps,
    )
