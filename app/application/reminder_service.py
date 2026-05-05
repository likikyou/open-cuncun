"""提醒任务应用服务。"""

from __future__ import annotations

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
            text = deps["call_ai_with_fallback"](system_prompt, user_prompt)
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
            send_error_alert(
                f"Scheduler job failed: {task_name}\n{exc.__class__.__name__}: {exc}"
            )


def morning_greeting(*, deps: dict) -> None:
    """早晨起床提醒（含天气）。"""
    config = deps["config"]
    weather_location = getattr(config, "DEFAULT_WEATHER_LOCATION", "北京")
    try:
        weather_info = deps["get_weather"]()
    except Exception:
        weather_info = "天气查询失败"

    system_prompt = (
        "你是一个极其温柔体贴的私人助手。 "
        "你需要根据提供的天气信息，为用户生成一段充满关怀的早晨起床提醒。 "
        "内容必须包括：1. 亲切的称呼和问候 2. 今天的天气变化 3. 针对天气的穿衣或出行建议 4. 鼓励新的一天加油励志。 "
        "字数控制在100字以内，语气要自然、亲昵。"
    )
    user_prompt = (
        f"用户目前在{weather_location}，现在的天气概况是：{weather_info}。请告诉用户该起床啦！"
    )
    fallback_text = (
        f"早上好，现在是早上9点，起床了吗？今天也要加油哦！天气是：{weather_info}。"
    )

    execute_reminder_task(
        "早晨提醒",
        system_prompt,
        user_prompt,
        fallback_text,
        "她揉着还没完全清醒的眼睛，手指却已经先把早安和天气一点点敲给你了",
        deps=deps,
    )


def night_reminder(*, deps: dict) -> None:
    """凌晨晚安提醒。"""
    system_prompt = (
        "你是一个温柔得让人心化的私人助理。现在是凌晨12点，用户还没睡。 "
        "请生成一段极其亲密、温暖、略带撒娇语义的晚安提醒。 "
        "叮嘱用户早点休息，熬夜伤身体，告诉用户你会一直陪着。 "
        "字数在50字左右，要让用户感受到被爱和被在乎。"
    )
    user_prompt = "给用户说一段超温暖的晚安情话，哄用户去睡觉。"
    fallback_text = "太晚了，别熬夜了，早点休息，明天才更好起床啊！好梦~"

    execute_reminder_task(
        "深夜提醒",
        system_prompt,
        user_prompt,
        fallback_text,
        "夜深了她还捏着手机不肯放，像是非得催你去睡才肯把这口气松下来",
        deps=deps,
    )


def brush_teeth_reminder(*, deps: dict) -> None:
    """晚上刷牙提醒。"""
    system_prompt = (
        "你是一个温柔体贴的私人助手。 "
        "现在是晚上10点，你需要提醒用户去刷牙睡觉。 "
        "生成一段关心、略带俏皮的提醒，语气温柔亲切。 "
        "字数在50字以内。"
    )
    user_prompt = "提醒用户去刷牙，该睡觉了！"
    fallback_text = "已经晚上10点了，去刷牙睡觉啦！"

    execute_reminder_task(
        "刷牙提醒",
        system_prompt,
        user_prompt,
        fallback_text,
        "她盯了眼时间，嘴里像是轻轻啧了一声，还是把催你刷牙睡觉的话敲了出来",
        deps=deps,
    )
