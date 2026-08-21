import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import Config
from app.vision import SAFE_IMAGE_FALLBACK, analyze_image
from app.vision_gemma import VisionProviderResult


PNG_BYTES = b"\x89PNG\r\n\x1a\nprimary-test-image"
GIF_BYTES = b"GIF89aprimary-test-image"
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBPprimary-test-image"


def _configure_gemma_primary(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(Config, "VISION_PROVIDER", "gemma")
    monkeypatch.setattr(Config, "VISION_PROVIDER_FALLBACK", "safe_text")
    monkeypatch.setattr(Config, "GEMMA_VISION_ENABLED", True)
    monkeypatch.setattr(Config, "GEMMA_VISION_MODEL", "gemma-4-31b")
    monkeypatch.setattr(Config, "GEMMA_VISION_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(Config, "GEMMA_VISION_MAX_IMAGE_MB", 5.0)
    monkeypatch.setattr(Config, "GEMMA_VISION_ALLOWED_MIME_TYPES", "image/png,image/jpeg")
    monkeypatch.setattr(Config, "GEMMA_VISION_SHADOW_STORE_PREVIEWS", False)
    monkeypatch.setattr(Config, "GEMMA_VISION_SHADOW_ARTIFACT_DIR", str(tmp_path))
    monkeypatch.setattr(Config, "CEREBRAS_API_KEY", "cerebras-key")


def _ok_result(**kwargs) -> VisionProviderResult:
    return VisionProviderResult(
        provider="cerebras",
        model=kwargs["model"],
        description="Gemma primary description",
        latency_ms=9,
        status="ok",
        error="",
        token_usage={"prompt_tokens": 12, "completion_tokens": 4},
        mime_type=kwargs["mime_type"],
        image_size_bytes=len(kwargs["image_bytes"]),
    )


def test_gemma_primary_calls_gemma_and_returns_description(monkeypatch, tmp_path) -> None:
    _configure_gemma_primary(monkeypatch, tmp_path)
    called = {}

    def fake_gemma(**kwargs):
        called.update(kwargs)
        return _ok_result(**kwargs)

    def fail_qwen(*_args, **_kwargs):
        raise AssertionError("DashScope/Qwen should not be called when VISION_PROVIDER=gemma")

    monkeypatch.setattr("app.vision.analyze_image_with_gemma", fake_gemma)
    monkeypatch.setattr("app.vision.http_session", SimpleNamespace(post=fail_qwen))

    assert analyze_image(PNG_BYTES) == "Gemma primary description"
    assert called["mime_type"] == "image/png"
    assert called["model"] == "gemma-4-31b"
    assert called["timeout_seconds"] == 1.0


def test_gemma_primary_does_not_schedule_shadow(monkeypatch, tmp_path) -> None:
    _configure_gemma_primary(monkeypatch, tmp_path)

    def fail_shadow(**_kwargs):
        raise AssertionError("Gemma primary should not schedule Gemma shadow")

    monkeypatch.setattr("app.vision.analyze_image_with_gemma", _ok_result)
    monkeypatch.setattr("app.vision.schedule_gemma_vision_shadow", fail_shadow)

    assert analyze_image(PNG_BYTES) == "Gemma primary description"
    assert not (tmp_path / "shadow_results.jsonl").exists()


def test_gemma_failure_returns_safe_fallback_without_qwen(monkeypatch, tmp_path) -> None:
    _configure_gemma_primary(monkeypatch, tmp_path)

    def failed_gemma(**kwargs):
        return VisionProviderResult(
            provider="cerebras",
            model=kwargs["model"],
            description="",
            latency_ms=12,
            status="error",
            error="RuntimeError: unavailable",
            token_usage=None,
            mime_type=kwargs["mime_type"],
            image_size_bytes=len(kwargs["image_bytes"]),
        )

    def fail_qwen(*_args, **_kwargs):
        raise AssertionError("Gemma failure must not fall back to Qwen")

    monkeypatch.setattr("app.vision.analyze_image_with_gemma", failed_gemma)
    monkeypatch.setattr("app.vision.http_session", SimpleNamespace(post=fail_qwen))

    assert analyze_image(PNG_BYTES) == SAFE_IMAGE_FALLBACK


def test_missing_cerebras_key_returns_safe_fallback(monkeypatch, tmp_path) -> None:
    _configure_gemma_primary(monkeypatch, tmp_path)
    monkeypatch.setattr(Config, "CEREBRAS_API_KEY", None)

    def fail_qwen(*_args, **_kwargs):
        raise AssertionError("Missing Cerebras key must not fall back to Qwen")

    monkeypatch.setattr("app.vision.http_session", SimpleNamespace(post=fail_qwen))

    assert analyze_image(PNG_BYTES) == SAFE_IMAGE_FALLBACK


def test_disallowed_mime_returns_safe_fallback_without_provider(monkeypatch, tmp_path) -> None:
    _configure_gemma_primary(monkeypatch, tmp_path)
    monkeypatch.setattr(Config, "GEMMA_VISION_ALLOWED_MIME_TYPES", "image/png")

    def fail_gemma(**_kwargs):
        raise AssertionError("Gemma should not be called for disallowed MIME")

    monkeypatch.setattr("app.vision.analyze_image_with_gemma", fail_gemma)

    assert analyze_image(GIF_BYTES) == SAFE_IMAGE_FALLBACK


def test_default_gemma_allowlist_rejects_webp_without_provider(monkeypatch, tmp_path) -> None:
    _configure_gemma_primary(monkeypatch, tmp_path)

    def fail_gemma(**_kwargs):
        raise AssertionError("Gemma should not be called for WebP under the default allowlist")

    monkeypatch.setattr("app.vision.analyze_image_with_gemma", fail_gemma)

    assert Config.GEMMA_VISION_ALLOWED_MIME_TYPES == "image/png,image/jpeg"
    assert analyze_image(WEBP_BYTES) == SAFE_IMAGE_FALLBACK


def test_unrecognized_image_bytes_return_safe_fallback_without_provider(
    monkeypatch, tmp_path
) -> None:
    _configure_gemma_primary(monkeypatch, tmp_path)

    def fail_gemma(**_kwargs):
        raise AssertionError("Gemma should not be called for unrecognized image bytes")

    monkeypatch.setattr("app.vision.analyze_image_with_gemma", fail_gemma)

    assert analyze_image(b"not-an-image") == SAFE_IMAGE_FALLBACK


def test_oversized_image_returns_safe_fallback_without_provider(monkeypatch, tmp_path) -> None:
    _configure_gemma_primary(monkeypatch, tmp_path)
    monkeypatch.setattr(Config, "GEMMA_VISION_MAX_IMAGE_MB", 0.000001)

    def fail_gemma(**_kwargs):
        raise AssertionError("Gemma should not be called for oversized images")

    monkeypatch.setattr("app.vision.analyze_image_with_gemma", fail_gemma)

    assert analyze_image(PNG_BYTES) == SAFE_IMAGE_FALLBACK


def test_safe_text_provider_returns_fallback(monkeypatch, tmp_path) -> None:
    _configure_gemma_primary(monkeypatch, tmp_path)
    monkeypatch.setattr(Config, "VISION_PROVIDER", "safe_text")

    def fail_gemma(**_kwargs):
        raise AssertionError("Gemma should not be called when VISION_PROVIDER=safe_text")

    monkeypatch.setattr("app.vision.analyze_image_with_gemma", fail_gemma)

    assert analyze_image(PNG_BYTES) == SAFE_IMAGE_FALLBACK


def test_qwen_legacy_only_when_explicitly_configured(monkeypatch, tmp_path) -> None:
    _configure_gemma_primary(monkeypatch, tmp_path)
    monkeypatch.setattr(Config, "VISION_PROVIDER", "qwen")
    monkeypatch.setattr(Config, "ALI_API_KEY", "dashscope-key")

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "Qwen legacy description"}}]}

    def fake_post(*_args, **_kwargs):
        return FakeResponse()

    monkeypatch.setattr("app.vision.http_session", SimpleNamespace(post=fake_post))
    monkeypatch.setattr("app.vision.schedule_gemma_vision_shadow", lambda **_kwargs: None)

    assert analyze_image(PNG_BYTES) == "Qwen legacy description"
