import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.application.ai_summary_extractor import (
    SUMMARY_SYSTEM_PROMPT,
    VOICE_EMOTIONS,
    VOICE_THEMES,
    parse_summary_content,
)


def test_summary_voice_contract_uses_compatible_enums() -> None:
    assert VOICE_EMOTIONS == (
        "平静",
        "开心",
        "撒娇",
        "傲娇",
        "嫌弃",
        "生气",
        "难过",
        "心疼",
        "鼓励",
        "打趣",
        "疲倦",
        "其他",
    )
    assert VOICE_THEMES == (
        "问候",
        "催促",
        "工作/搞钱",
        "吐槽",
        "深情表白",
        "讲故事",
        "调侃",
        "日常",
        "情绪宣泄",
        "教导",
    )
    assert "、".join(VOICE_EMOTIONS) in SUMMARY_SYSTEM_PROMPT
    assert "、".join(VOICE_THEMES) in SUMMARY_SYSTEM_PROMPT


def test_parse_summary_content_preserves_compatible_voice_tags() -> None:
    content = json.dumps(
        {"intent": "今天继续搞钱", "emotion": "傲娇", "theme": "工作/搞钱"},
        ensure_ascii=False,
    )

    assert parse_summary_content(content) == {
        "intent": "今天继续搞钱",
        "emotion": "傲娇",
        "theme": "工作/搞钱",
    }


def test_parse_summary_content_falls_back_for_unknown_voice_tags() -> None:
    content = json.dumps(
        {"intent": "我会陪着你", "emotion": "亲近", "theme": "关系表达"},
        ensure_ascii=False,
    )

    assert parse_summary_content(content) == {
        "intent": "我会陪着你",
        "emotion": "平静",
        "theme": "日常",
    }
