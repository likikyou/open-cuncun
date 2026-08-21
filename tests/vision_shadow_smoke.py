import json
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Config
from app.vision import analyze_image
from app.vision_gemma import VisionProviderResult, build_gemma_vision_messages
from app.vision_shadow import run_gemma_vision_shadow


PNG_BYTES = b"\x89PNG\r\n\x1a\nshadow-test-image"


def _configure_shadow(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Config, "GEMMA_VISION_ENABLED", True)
    monkeypatch.setattr(Config, "GEMMA_VISION_SHADOW_MODE", True)
    monkeypatch.setattr(Config, "GEMMA_VISION_MODEL", "gemma-4-31b")
    monkeypatch.setattr(Config, "GEMMA_VISION_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(Config, "GEMMA_VISION_MAX_IMAGE_MB", 5.0)
    monkeypatch.setattr(Config, "GEMMA_VISION_ALLOWED_MIME_TYPES", "image/png,image/jpeg")
    monkeypatch.setattr(Config, "GEMMA_VISION_SHADOW_STORE_PREVIEWS", False)
    monkeypatch.setattr(Config, "GEMMA_VISION_SHADOW_ARTIFACT_DIR", str(tmp_path))


def _artifact_records(tmp_path: Path) -> list[dict]:
    path = tmp_path / "shadow_results.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_gemma_provider_builds_base64_data_uri() -> None:
    messages = build_gemma_vision_messages(
        image_bytes=b"abc",
        mime_type="image/png",
        prompt="describe",
    )

    content = messages[0]["content"]
    assert content[0] == {"type": "text", "text": "describe"}
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == "data:image/png;base64,YWJj"


def test_disabled_shadow_does_not_call_provider(monkeypatch, tmp_path) -> None:
    _configure_shadow(monkeypatch, tmp_path)
    monkeypatch.setattr(Config, "GEMMA_VISION_ENABLED", False)

    def fail_provider(**_kwargs):
        raise AssertionError("provider should not be called when shadow is disabled")

    result = run_gemma_vision_shadow(
        image_bytes=PNG_BYTES,
        mime_type="image/png",
        qwen_description="Qwen production description",
        provider_fn=fail_provider,
    )

    assert result is None
    assert not (tmp_path / "shadow_results.jsonl").exists()


def test_shadow_mode_off_creates_no_artifact(monkeypatch, tmp_path) -> None:
    _configure_shadow(monkeypatch, tmp_path)
    monkeypatch.setattr(Config, "GEMMA_VISION_SHADOW_MODE", False)

    def fail_provider(**_kwargs):
        raise AssertionError("provider should not be called when shadow mode is off")

    result = run_gemma_vision_shadow(
        image_bytes=PNG_BYTES,
        mime_type="image/png",
        qwen_description="private image text",
        provider_fn=fail_provider,
    )

    assert result is None
    assert not (tmp_path / "shadow_results.jsonl").exists()


def test_shadow_rejects_disallowed_mime_without_provider_call(monkeypatch, tmp_path) -> None:
    _configure_shadow(monkeypatch, tmp_path)
    monkeypatch.setattr(Config, "GEMMA_VISION_ALLOWED_MIME_TYPES", "image/png")

    def fail_provider(**_kwargs):
        raise AssertionError("provider should not be called for disallowed MIME")

    result = run_gemma_vision_shadow(
        image_bytes=b"gif-bytes",
        mime_type="image/gif",
        qwen_description="Qwen production description",
        qwen_latency_ms=12,
        provider_fn=fail_provider,
    )

    assert result is not None
    assert result.status == "skipped"
    assert result.error == "mime_type_not_allowed"
    artifact_text = (tmp_path / "shadow_results.jsonl").read_text(encoding="utf-8")
    assert "data:image" not in artifact_text
    assert "Z2lmLWJ5dGVz" not in artifact_text


def test_shadow_rejects_large_image_without_provider_call(monkeypatch, tmp_path) -> None:
    _configure_shadow(monkeypatch, tmp_path)
    monkeypatch.setattr(Config, "GEMMA_VISION_MAX_IMAGE_MB", 0.000001)

    def fail_provider(**_kwargs):
        raise AssertionError("provider should not be called for oversized images")

    result = run_gemma_vision_shadow(
        image_bytes=PNG_BYTES,
        mime_type="image/png",
        qwen_description="Qwen production description",
        provider_fn=fail_provider,
    )

    assert result is not None
    assert result.status == "skipped"
    assert result.error == "image_too_large"


def test_missing_cerebras_key_is_recorded_as_safe_skip(monkeypatch, tmp_path) -> None:
    _configure_shadow(monkeypatch, tmp_path)
    monkeypatch.setattr(Config, "CEREBRAS_API_KEY", None)

    result = run_gemma_vision_shadow(
        image_bytes=PNG_BYTES,
        mime_type="image/png",
        qwen_description="Qwen production description",
    )

    assert result is not None
    assert result.status == "skipped"
    assert result.error == "missing_cerebras_api_key"
    records = _artifact_records(tmp_path)
    assert records[0]["shadow_error"] == "missing_cerebras_api_key"
    assert records[0]["raw_image_saved"] is False


def test_provider_error_is_recorded_without_losing_qwen_result(monkeypatch, tmp_path) -> None:
    _configure_shadow(monkeypatch, tmp_path)

    def failing_provider(**_kwargs):
        raise RuntimeError("provider unavailable")

    qwen_description = "Qwen production description"
    result = run_gemma_vision_shadow(
        image_bytes=PNG_BYTES,
        mime_type="image/png",
        qwen_description=qwen_description,
        qwen_latency_ms=33,
        provider_fn=failing_provider,
    )

    assert result is not None
    assert result.status == "error"
    records = _artifact_records(tmp_path)
    assert records[0]["production_description_length"] == len(qwen_description)
    assert len(records[0]["production_description_hash"]) == 64
    assert "production_description_preview" not in records[0]
    assert records[0]["production_latency_ms"] == 33
    assert records[0]["shadow_status"] == "error"


def test_shadow_result_contains_no_raw_image_or_base64(monkeypatch, tmp_path) -> None:
    _configure_shadow(monkeypatch, tmp_path)

    def ok_provider(**kwargs):
        return VisionProviderResult(
            provider="cerebras",
            model=kwargs["model"],
            description="Gemma saw a dashboard.",
            latency_ms=7,
            status="ok",
            error="",
            token_usage={"prompt_tokens": 12, "completion_tokens": 5},
            mime_type=kwargs["mime_type"],
            image_size_bytes=len(kwargs["image_bytes"]),
        )

    run_gemma_vision_shadow(
        image_bytes=PNG_BYTES,
        mime_type="image/png",
        qwen_description="Qwen production description",
        provider_fn=ok_provider,
    )

    artifact_text = (tmp_path / "shadow_results.jsonl").read_text(encoding="utf-8")
    assert "data:image" not in artifact_text
    assert "c2hhZG93LXRlc3QtaW1hZ2U=" not in artifact_text
    records = _artifact_records(tmp_path)
    assert records[0]["shadow_description_length"] == len("Gemma saw a dashboard.")
    assert "shadow_description_preview" not in records[0]
    assert "Qwen production description" not in artifact_text
    assert records[0]["raw_image_saved"] is False
    assert records[0]["previews_stored"] is False


def test_analyze_image_returns_qwen_result_when_shadow_scheduler_fails(monkeypatch) -> None:
    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "Qwen production description"}}]}

    def fake_post(*_args, **_kwargs):
        return FakeResponse()

    def broken_shadow(**_kwargs):
        raise RuntimeError("shadow scheduling failed")

    monkeypatch.setattr(Config, "VISION_PROVIDER", "qwen")
    monkeypatch.setattr(Config, "ALI_API_KEY", "dashscope-key")
    monkeypatch.setattr("app.vision.http_session", SimpleNamespace(post=fake_post))
    monkeypatch.setattr("app.vision.schedule_gemma_vision_shadow", broken_shadow)

    assert analyze_image(PNG_BYTES) == "Qwen production description"
