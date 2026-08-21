"""Gemma vision provider for production and shadow image understanding."""

from __future__ import annotations

import base64
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable

from openai import OpenAI

from .config import Config

DEFAULT_GEMMA_VISION_PROMPT = (
    "请用中文描述这张图片，并指出其中最重要的信息。"
    "如果是界面、文档或图表，请优先说明可见的标题、指标、趋势和异常点。"
)


@dataclass
class VisionProviderResult:
    provider: str
    model: str
    description: str
    latency_ms: int
    status: str
    error: str
    token_usage: dict[str, Any] | None
    mime_type: str
    image_size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_gemma_vision_messages(
    *,
    image_bytes: bytes,
    mime_type: str,
    prompt: str = DEFAULT_GEMMA_VISION_PROMPT,
) -> list[dict[str, Any]]:
    encoded_image = base64.b64encode(image_bytes).decode("ascii")
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{encoded_image}"},
                },
            ],
        }
    ]


def _usage_dict(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return usage
    return {"raw": str(usage)}


def analyze_image_with_gemma(
    *,
    image_bytes: bytes,
    mime_type: str,
    prompt: str = DEFAULT_GEMMA_VISION_PROMPT,
    model: str | None = None,
    timeout_seconds: float | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
    client_factory: Callable[..., Any] = OpenAI,
) -> VisionProviderResult:
    """Call Cerebras Chat Completions with Gemma vision input.

    Errors are normalized into a result object so callers can keep production
    image handling best-effort and non-blocking.
    """
    started = time.perf_counter()
    resolved_model = model or Config.GEMMA_VISION_MODEL
    resolved_key = api_key if api_key is not None else Config.CEREBRAS_API_KEY
    if not resolved_key:
        return VisionProviderResult(
            provider="cerebras",
            model=resolved_model,
            description="",
            latency_ms=round((time.perf_counter() - started) * 1000),
            status="skipped",
            error="missing_cerebras_api_key",
            token_usage=None,
            mime_type=mime_type,
            image_size_bytes=len(image_bytes),
        )

    try:
        client = client_factory(
            api_key=resolved_key,
            base_url=base_url or Config.CEREBRAS_API_BASE,
            timeout=timeout_seconds or Config.GEMMA_VISION_TIMEOUT_SECONDS,
        )
        response = client.chat.completions.create(
            model=resolved_model,
            messages=build_gemma_vision_messages(
                image_bytes=image_bytes,
                mime_type=mime_type,
                prompt=prompt,
            ),
            max_tokens=800,
            temperature=0.2,
            timeout=timeout_seconds or Config.GEMMA_VISION_TIMEOUT_SECONDS,
        )
        description = response.choices[0].message.content or ""
        return VisionProviderResult(
            provider="cerebras",
            model=resolved_model,
            description=description,
            latency_ms=round((time.perf_counter() - started) * 1000),
            status="ok",
            error="",
            token_usage=_usage_dict(response),
            mime_type=mime_type,
            image_size_bytes=len(image_bytes),
        )
    except Exception as exc:
        return VisionProviderResult(
            provider="cerebras",
            model=resolved_model,
            description="",
            latency_ms=round((time.perf_counter() - started) * 1000),
            status="error",
            error=f"{exc.__class__.__name__}: {str(exc)[:500]}",
            token_usage=None,
            mime_type=mime_type,
            image_size_bytes=len(image_bytes),
        )
