from contextlib import nullcontext
from datetime import datetime, timedelta
from types import SimpleNamespace

from app.application import (
    command_service,
    memory_reflection_service,
    observation_media_service,
    observation_service,
    proactive_chat_service,
    reply_service,
    reminder_service,
)
from app import retrieval, tools_registry
from app.presentation.formatters.memory_formatter import relationship_stage_label


class _RecordingLogger:
    def __init__(self) -> None:
        self.records = []

    def info(self, message, *args, **kwargs) -> None:
        self.records.append(("info", message, args, kwargs))

    def warning(self, message, *args, **kwargs) -> None:
        self.records.append(("warning", message, args, kwargs))

    def error(self, message, *args, **kwargs) -> None:
        self.records.append(("error", message, args, kwargs))


def test_reminder_tasks_follow_configured_persona_without_forcing_one(monkeypatch) -> None:
    calls = []

    def capture_reminder(*args, **kwargs) -> None:
        calls.append((args, kwargs))

    monkeypatch.setattr(reminder_service, "execute_reminder_task", capture_reminder)
    deps = {
        "config": SimpleNamespace(DEFAULT_WEATHER_LOCATION="上海"),
        "get_weather": lambda: "晴，18℃",
    }

    reminder_service.morning_greeting(deps=deps)
    reminder_service.night_reminder(deps=deps)
    reminder_service.brush_teeth_reminder(deps=deps)

    assert [args[0] for args, _kwargs in calls] == ["早晨提醒", "深夜提醒", "刷牙提醒"]
    forbidden = ("极其温柔", "撒娇", "情话", "被爱", "一直陪着", "俏皮", "亲昵")
    for args, kwargs in calls:
        system_prompt, user_prompt, fallback_text, scene_hint = args[1:5]
        assert "不改变上述角色设定" in system_prompt
        assert not any(term in system_prompt + user_prompt + fallback_text for term in forbidden)
        assert "助手" in scene_hint
        assert "她" not in scene_hint
        assert kwargs["deps"] is deps


def test_reminder_execution_includes_deployment_persona() -> None:
    captured = {}

    reminder_service.execute_reminder_task(
        "测试提醒",
        "只执行中性的提醒任务。",
        "提醒用户测试。",
        "测试兜底。",
        deps={
            "logger": _RecordingLogger(),
            "config": SimpleNamespace(ADMIN_OPEN_ID="user-1"),
            "build_prompt": lambda _text: "DEPLOYMENT PERSONA SENTINEL",
            "observation_runtime_state": lambda *_args, **_kwargs: nullcontext(),
            "call_ai_with_fallback": lambda system_prompt, user_prompt: captured.update(
                {"system_prompt": system_prompt, "user_prompt": user_prompt}
            )
            or "提醒结果",
            "send_feishu": lambda *_args: None,
            "match_voice_file": lambda *_args: None,
            "call_ai_summarize": lambda *_args: {},
            "upload_audio_v2": lambda *_args: "",
        },
    )

    assert captured["system_prompt"].startswith("DEPLOYMENT PERSONA SENTINEL")
    assert "【定时提醒任务】" in captured["system_prompt"]
    assert "只执行中性的提醒任务" in captured["system_prompt"]


def test_observation_copy_uses_neutral_companion_references() -> None:
    preset_hints = " ".join(
        preset["scene_hint"] for preset in observation_service._RUNTIME_STATE_PRESETS.values()
    )
    assert "助手" in preset_hints
    assert "她" not in preset_hints

    now = datetime(2026, 8, 21, 12, 0, 0)
    recent_hint, source = observation_service._build_recent_chat_hint(
        "user-1",
        now_local=now,
        get_last_interaction_time_fn=lambda _user_id: now - timedelta(minutes=1),
        get_recent_history_fn=lambda _user_id, limit: [{"role": "user", "content": "今天怎么样"}],
    )
    assert source == "recent_chat"
    assert recent_hint.startswith("助手")
    assert "她" not in recent_hint

    fallback = observation_service._build_fallback_observation({})
    assert fallback.startswith("助手")
    assert "她" not in fallback


def test_observation_renderer_explicitly_avoids_gender_assumptions() -> None:
    captured = {}

    def call_low_cost_ai(system_prompt, user_prompt, max_tokens):
        captured.update(
            {
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
                "max_tokens": max_tokens,
            }
        )
        return ""

    text, source = observation_service.render_observation_text(
        {},
        deps={
            "call_low_cost_ai": call_low_cost_ai,
            "logger": _RecordingLogger(),
        },
    )

    assert source == "template"
    assert text.startswith("助手")
    assert "表现助手当下的状态" in captured["system_prompt"]
    assert "不要推断性别" in captured["system_prompt"]
    assert "她" not in captured["system_prompt"]


def test_observation_media_scene_hint_is_neutral() -> None:
    captured = {}

    def activate_runtime_state(user_id, state_code, **kwargs):
        captured.update({"user_id": user_id, "state_code": state_code, **kwargs})
        return "state-token"

    task = observation_media_service.build_observation_media_task(
        "user-1",
        deps={
            "activate_presence_runtime_state": activate_runtime_state,
            "get_or_create_observation_snapshot": (
                lambda _user_id, force_refresh=False, deps=None: {"media_prompt": "prompt"}
            ),
            "save_presence_snapshot": lambda _user_id, _snapshot: None,
            "logger": _RecordingLogger(),
        },
    )

    assert task["state_token"] == "state-token"
    assert captured["scene_hint"].startswith("助手")
    assert "她" not in captured["scene_hint"]


def test_story_and_memory_fallbacks_do_not_assume_gender(monkeypatch) -> None:
    scene = command_service._default_story_scene()
    assert "角色" in scene
    assert "她" not in scene
    assert "嘴上说" not in scene

    content, _theme, _emotion, _importance = memory_reflection_service._build_reflection_fallback(
        "最近压力有点大", "知道了"
    )
    assert content.startswith("用户提到")
    assert "助手" in content
    assert "他" not in content
    assert "她" not in content

    monkeypatch.setattr(
        memory_reflection_service,
        "get_bionic_state",
        lambda _user_id: {
            "current_mood": "平静",
            "mood_intensity": 0.5,
            "relationship_stage": 1,
        },
    )
    runtime_context = memory_reflection_service.get_runtime_state_context("user-1")
    assert "你对用户的感觉" in runtime_context
    assert "你对他的感觉" not in runtime_context


def test_memory_copy_does_not_impose_a_relationship_style(monkeypatch) -> None:
    monkeypatch.setattr(
        retrieval,
        "_query_collection_documents",
        lambda *_args, **_kwargs: ["用户偏好简洁回答"],
    )

    profile = retrieval.get_user_profile_memory("偏好", "user-1")
    stage = relationship_stage_label(10)

    assert profile.lstrip().startswith("【关于用户的稳定印象】")
    assert "关于他的" not in profile
    assert not any(term in stage for term in ("离不开", "绑定", "黏人"))


def test_direct_time_reply_is_a_neutral_fact(monkeypatch) -> None:
    monkeypatch.setattr(
        tools_registry,
        "local_now_naive",
        lambda: datetime(2026, 8, 21, 15, 4, 0),
    )
    sent = []

    result = reply_service.generate_reply(
        "user-1",
        "现在几点",
        history=[],
        deps={
            "send_feishu": lambda _open_id, msg_type, payload: sent.append((msg_type, payload)),
            "normalize_reply_text": lambda text: text,
            "logger": _RecordingLogger(),
        },
    )

    assert result["reply_text"] == "现在是下午3点04分（15:04）。"
    assert result["summary"] == {
        "intent": "报当前时间",
        "emotion": "平静",
        "theme": "日常",
    }
    assert sent == [("text", {"text": result["reply_text"]})]


def test_proactive_logs_never_include_message_bodies() -> None:
    logger = _RecordingLogger()
    raw = "META NOTE 用户你好"
    cleaned = proactive_chat_service.sanitize_proactive_reply(raw, logger=logger)

    assert cleaned == "用户你好"
    assert raw not in repr(logger.records)
    assert cleaned not in repr(logger.records)
    assert logger.records[0][3]["extra"] == {
        "prefix_length": 10,
        "original_length": len(raw),
        "cleaned_length": len(cleaned),
    }

    logger.records.clear()
    private_reply = "这是不应进入日志的正文"
    now = datetime(2026, 8, 21, 12, 0, 0)
    voice_inputs = []
    ai_inputs = []
    proactive_chat_service.proactive_thought_task(
        deps={
            "logger": logger,
            "config": SimpleNamespace(ADMIN_OPEN_ID="user-1"),
            "build_prompt": lambda _text: "DEPLOYMENT PERSONA SENTINEL",
            "get_last_interaction_time": lambda _user_id: now - timedelta(hours=6),
            "local_now_naive": lambda: now,
            "observation_runtime_state": lambda *_args, **_kwargs: nullcontext(),
            "call_ai": lambda **kwargs: ai_inputs.append(kwargs) or private_reply,
            "sanitize_reply": lambda reply: reply,
            "match_voice_file": lambda *args: voice_inputs.append(args) or None,
            "call_ai_summarize": lambda *_args: "",
            "send_feishu": lambda *_args: None,
            "path_exists": lambda _path: False,
            "upload_audio_v2": lambda _path: "",
            "save_message": lambda **_kwargs: None,
        }
    )

    records_repr = repr(logger.records)
    assert private_reply not in records_repr
    decision_records = [record for record in logger.records if record[1] == "💭 助手决定主动发消息"]
    assert decision_records[0][3]["extra"] == {"reply_length": len(private_reply)}
    assert voice_inputs[0][0] == "主动消息"
    assert ai_inputs[0]["system_prompt"].startswith("DEPLOYMENT PERSONA SENTINEL")
    assert "【主动消息任务】" in ai_inputs[0]["system_prompt"]
