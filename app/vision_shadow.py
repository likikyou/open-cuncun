"""Best-effort Gemma vision shadow runner.

The shadow runner never returns content to the user-facing reply path. It records
comparison metadata only when explicitly enabled. Description previews are a
separate opt-in; default artifacts contain hashes and operational metadata only.
When Gemma is the production provider, scheduling is skipped to avoid duplicate
Gemma calls.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

from .config import Config
from .logger import logger
from .vision_gemma import VisionProviderResult, analyze_image_with_gemma

_WRITE_LOCK = threading.Lock()
_SHADOW_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gemma-vision-shadow")
_SHADOW_PENDING = threading.BoundedSemaphore(value=4)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _preview(text: str | None, limit: int = 300) -> str:
    normalized = (text or "").replace("\r", " ").replace("\n", "\\n")
    return normalized[:limit]


def _error_code(error: str | None) -> str:
    """Return a bounded error category without persisting provider text."""
    prefix = (error or "").strip().split(":", 1)[0]
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", prefix).strip("_")
    return normalized[:80] if normalized else ""


def _hash_text(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _allowed_mime_types() -> set[str]:
    return {
        item.strip().lower()
        for item in Config.GEMMA_VISION_ALLOWED_MIME_TYPES.split(",")
        if item.strip()
    }


def _max_image_bytes() -> int:
    return int(Config.GEMMA_VISION_MAX_IMAGE_MB * 1024 * 1024)


def _artifact_path() -> str:
    return os.path.join(Config.GEMMA_VISION_SHADOW_ARTIFACT_DIR, "shadow_results.jsonl")


def _skip_result(*, reason: str, mime_type: str, image_size_bytes: int) -> VisionProviderResult:
    return VisionProviderResult(
        provider="cerebras",
        model=Config.GEMMA_VISION_MODEL,
        description="",
        latency_ms=0,
        status="skipped",
        error=reason,
        token_usage=None,
        mime_type=mime_type,
        image_size_bytes=image_size_bytes,
    )


def _build_artifact_record(
    *,
    result: VisionProviderResult,
    qwen_description: str,
    qwen_latency_ms: int | None,
    qwen_status: str,
    qwen_error: str,
) -> dict:
    store_previews = bool(Config.GEMMA_VISION_SHADOW_STORE_PREVIEWS)
    record = {
        "created_at": _utc_now(),
        "shadow_mode": True,
        "production_provider": "dashscope",
        "production_model": "qwen-vl-plus-latest",
        "production_status": qwen_status,
        "production_error": _error_code(qwen_error),
        "production_description_hash": _hash_text(qwen_description),
        "production_description_length": len(qwen_description or ""),
        "production_latency_ms": qwen_latency_ms,
        "shadow_provider": result.provider,
        "shadow_model": result.model,
        "shadow_status": result.status,
        "shadow_error": _error_code(result.error),
        "shadow_description_hash": _hash_text(result.description),
        "shadow_description_length": len(result.description or ""),
        "shadow_latency_ms": result.latency_ms,
        "shadow_token_usage": result.token_usage,
        "mime_type": result.mime_type,
        "image_size_bytes": result.image_size_bytes,
        "raw_image_saved": False,
        "previews_stored": store_previews,
    }
    if store_previews:
        record["production_description_preview"] = _preview(qwen_description)
        record["shadow_description_preview"] = _preview(result.description)
    return record


def _append_artifact(record: dict) -> None:
    path = _artifact_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _WRITE_LOCK:
            with open(path, "a", encoding="utf-8") as file_obj:
                file_obj.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except Exception as exc:
        logger.warning(f"Gemma vision shadow artifact write failed: {exc}")


def run_gemma_vision_shadow(
    *,
    image_bytes: bytes,
    mime_type: str,
    qwen_description: str,
    qwen_latency_ms: int | None = None,
    qwen_status: str = "returned",
    qwen_error: str = "",
    provider_fn: Callable[..., VisionProviderResult] = analyze_image_with_gemma,
) -> VisionProviderResult | None:
    """Run one privacy-preserving Gemma vision shadow attempt.

    Disabled mode performs no provider call and creates no artifact. Enabled
    mode never stores raw image bytes and stores text previews only by opt-in.
    """
    if not Config.GEMMA_VISION_ENABLED or not Config.GEMMA_VISION_SHADOW_MODE:
        return None
    if len(image_bytes) > _max_image_bytes():
        result = _skip_result(
            reason="image_too_large",
            mime_type=mime_type,
            image_size_bytes=len(image_bytes),
        )
    elif mime_type.lower() not in _allowed_mime_types():
        result = _skip_result(
            reason="mime_type_not_allowed",
            mime_type=mime_type,
            image_size_bytes=len(image_bytes),
        )
    else:
        try:
            result = provider_fn(
                image_bytes=image_bytes,
                mime_type=mime_type,
                model=Config.GEMMA_VISION_MODEL,
                timeout_seconds=Config.GEMMA_VISION_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            result = VisionProviderResult(
                provider="cerebras",
                model=Config.GEMMA_VISION_MODEL,
                description="",
                latency_ms=0,
                status="error",
                error=f"{exc.__class__.__name__}: {str(exc)[:500]}",
                token_usage=None,
                mime_type=mime_type,
                image_size_bytes=len(image_bytes),
            )

    _append_artifact(
        _build_artifact_record(
            result=result,
            qwen_description=qwen_description,
            qwen_latency_ms=qwen_latency_ms,
            qwen_status=qwen_status,
            qwen_error=qwen_error,
        )
    )
    return result


def schedule_gemma_vision_shadow(
    *,
    image_bytes: bytes,
    mime_type: str,
    qwen_description: str,
    qwen_latency_ms: int | None = None,
    qwen_status: str = "returned",
    qwen_error: str = "",
) -> None:
    """Schedule background shadow work when enabled.

    This function intentionally swallows all exceptions to preserve the
    production image description path.
    """
    if not Config.GEMMA_VISION_ENABLED or not Config.GEMMA_VISION_SHADOW_MODE:
        return
    if getattr(Config, "VISION_PROVIDER", "safe_text").strip().lower() != "qwen":
        return
    if not _SHADOW_PENDING.acquire(blocking=False):
        logger.warning("Gemma vision shadow skipped because pending queue is full")
        return

    def _target() -> None:
        try:
            run_gemma_vision_shadow(
                image_bytes=image_bytes,
                mime_type=mime_type,
                qwen_description=qwen_description,
                qwen_latency_ms=qwen_latency_ms,
                qwen_status=qwen_status,
                qwen_error=qwen_error,
            )
        except Exception as exc:
            logger.warning(f"Gemma vision shadow failed without affecting reply: {exc}")
        finally:
            _SHADOW_PENDING.release()

    try:
        _SHADOW_EXECUTOR.submit(_target)
    except Exception as exc:
        _SHADOW_PENDING.release()
        logger.warning(f"Gemma vision shadow submit failed without affecting reply: {exc}")
