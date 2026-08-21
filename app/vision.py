"""
视觉识别模块
图片默认使用安全占位文本；可显式启用 Cerebras gemma-4-31b。
DashScope qwen-vl-plus-latest 仅作为显式 legacy provider 保留。
"""

import base64
import time

from .config import Config
from .http_client import http_session
from .logger import logger
from .vision_gemma import analyze_image_with_gemma
from .vision_shadow import schedule_gemma_vision_shadow

SAFE_IMAGE_FALLBACK = "我看到了你发来一张图片，但当前图片识别暂时不可用。"
LEGACY_QWEN_MODEL = "qwen-vl-plus-latest"


def _get_image_media_type(image_bytes: bytes) -> str | None:
    """根据图片文件头判断 MIME 类型"""
    if image_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    elif image_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    elif image_bytes[:4] == b"RIFF" and image_bytes[8:12] == b"WEBP":
        return "image/webp"
    elif image_bytes[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    elif image_bytes[:2] == b"BM":
        return "image/bmp"
    return None


def _allowed_mime_types() -> set[str]:
    return {
        item.strip().lower()
        for item in Config.GEMMA_VISION_ALLOWED_MIME_TYPES.split(",")
        if item.strip()
    }


def _max_image_bytes() -> int:
    return int(Config.GEMMA_VISION_MAX_IMAGE_MB * 1024 * 1024)


def _vision_provider() -> str:
    return (Config.VISION_PROVIDER or "safe_text").strip().lower()


def _fallback_description() -> str:
    if (Config.VISION_PROVIDER_FALLBACK or "safe_text").strip().lower() != "safe_text":
        logger.warning(
            "Unsupported VISION_PROVIDER_FALLBACK configured; using safe_text",
            extra={"vision_provider_fallback": Config.VISION_PROVIDER_FALLBACK},
        )
    return SAFE_IMAGE_FALLBACK


def _return_with_legacy_shadow(
    *,
    image_bytes: bytes,
    media_type: str,
    description: str,
    started_at: float,
    qwen_status: str = "returned",
    qwen_error: str = "",
) -> str:
    qwen_latency_ms = round((time.perf_counter() - started_at) * 1000)
    try:
        schedule_gemma_vision_shadow(
            image_bytes=image_bytes,
            mime_type=media_type,
            qwen_description=description,
            qwen_latency_ms=qwen_latency_ms,
            qwen_status=qwen_status,
            qwen_error=qwen_error,
        )
    except Exception as exc:
        logger.warning(f"Gemma vision shadow scheduling failed without affecting reply: {exc}")
    return description


def _analyze_image_with_gemma_primary(image_bytes: bytes, media_type: str) -> str:
    if not Config.GEMMA_VISION_ENABLED:
        logger.warning(
            "Gemma vision primary disabled; using safe fallback",
            extra={"vision_provider": "gemma", "reason": "gemma_vision_disabled"},
        )
        return _fallback_description()

    if len(image_bytes) > _max_image_bytes():
        logger.warning(
            "Gemma vision skipped oversized image; using safe fallback",
            extra={
                "vision_provider": "gemma",
                "image_size_bytes": len(image_bytes),
                "max_image_bytes": _max_image_bytes(),
            },
        )
        return _fallback_description()

    if media_type.lower() not in _allowed_mime_types():
        logger.warning(
            "Gemma vision skipped disallowed MIME type; using safe fallback",
            extra={"vision_provider": "gemma", "mime_type": media_type},
        )
        return _fallback_description()

    result = analyze_image_with_gemma(
        image_bytes=image_bytes,
        mime_type=media_type,
        model=Config.GEMMA_VISION_MODEL,
        timeout_seconds=Config.GEMMA_VISION_TIMEOUT_SECONDS,
    )
    if result.status == "ok" and result.description.strip():
        logger.info(
            "👁️ Gemma 图片识别完成",
            extra={
                "vision_provider": result.provider,
                "vision_model": result.model,
                "vision_status": result.status,
                "vision_latency_ms": result.latency_ms,
                "mime_type": media_type,
                "image_size_bytes": len(image_bytes),
            },
        )
        return result.description.strip()

    logger.warning(
        "Gemma vision primary failed; using safe fallback",
        extra={
            "vision_provider": result.provider,
            "vision_model": result.model,
            "vision_status": result.status,
            "vision_error": result.error[:300],
            "vision_latency_ms": result.latency_ms,
            "mime_type": media_type,
            "image_size_bytes": len(image_bytes),
        },
    )
    return _fallback_description()


def _analyze_image_with_qwen_legacy(image_bytes: bytes, media_type: str) -> str:
    """Legacy DashScope Qwen-VL path, used only when VISION_PROVIDER=qwen."""
    started_at = time.perf_counter()
    ali_key = Config.ALI_API_KEY
    if not ali_key:
        return _return_with_legacy_shadow(
            image_bytes=image_bytes,
            media_type=media_type,
            description="暂时无法查看图片内容（未配置阿里 API Key）",
            started_at=started_at,
            qwen_status="skipped",
            qwen_error="missing_ali_api_key",
        )

    base64_image = base64.b64encode(image_bytes).decode("utf-8")

    # 阿里 DashScope OpenAI 兼容接口
    url = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    headers = {"Authorization": f"Bearer {ali_key}", "Content-Type": "application/json"}

    payload = {
        "model": "qwen-vl-plus-latest",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "请非常仔细地观察这张图片的每一个细节。"
                            "你需要准确识别出图片中的主要物体、动物或人物。"
                            "描述时请包括：1. 主体是什么（如果是动物请准确说出种类）"
                            "2. 颜色、形状、大小等特征 3. 所处的环境和背景。"
                            "用简洁的中文回答，100字以内。"
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{base64_image}"},
                    },
                ],
            }
        ],
        "max_tokens": 300,
    }

    try:
        r = http_session.post(url, json=payload, headers=headers, timeout=30)
        if r.status_code == 200:
            res_data = r.json()
            choices = res_data.get("choices")
            if choices and choices[0] and choices[0].get("message"):
                description = choices[0]["message"].get("content", "图片内容识别失败")
                return _return_with_legacy_shadow(
                    image_bytes=image_bytes,
                    media_type=media_type,
                    description=description,
                    started_at=started_at,
                    qwen_status="ok",
                )
            return _return_with_legacy_shadow(
                image_bytes=image_bytes,
                media_type=media_type,
                description="图片内容识别失败",
                started_at=started_at,
                qwen_status="error",
                qwen_error="missing_qwen_message_content",
            )
        else:
            logger.error(f"阿里视觉模型请求失败: {r.status_code} {r.text[:200]}")
            return _return_with_legacy_shadow(
                image_bytes=image_bytes,
                media_type=media_type,
                description="看起来这张图有点神秘，我竟然没看透...",
                started_at=started_at,
                qwen_status="error",
                qwen_error=f"dashscope_http_{r.status_code}",
            )
    except Exception as e:
        logger.error(f"视觉分析异常: {e}")
        return _return_with_legacy_shadow(
            image_bytes=image_bytes,
            media_type=media_type,
            description="哎呀，刚才盯着图看太久，眼睛有点花，没看清内容呢。",
            started_at=started_at,
            qwen_status="error",
            qwen_error=f"{e.__class__.__name__}: {str(e)[:200]}",
        )


def analyze_image(image_bytes: bytes) -> str:
    """Return a best-effort text description for a Feishu image message."""
    provider = _vision_provider()

    if provider == "safe_text":
        logger.info("Vision provider safe_text selected; returning safe fallback")
        return _fallback_description()

    if provider not in {"gemma", "qwen"}:
        logger.warning(
            "Unknown VISION_PROVIDER configured; using safe fallback",
            extra={"vision_provider": provider},
        )
        return _fallback_description()

    media_type = _get_image_media_type(image_bytes)
    if media_type is None:
        logger.warning(
            "Vision provider skipped unrecognized image bytes; using safe fallback",
            extra={
                "vision_provider": provider,
                "image_size_bytes": len(image_bytes),
            },
        )
        return _fallback_description()

    if provider == "gemma":
        return _analyze_image_with_gemma_primary(image_bytes, media_type)

    if provider == "qwen":
        logger.warning(
            "Using legacy Qwen vision provider because VISION_PROVIDER=qwen",
            extra={"vision_provider": "qwen", "vision_model": LEGACY_QWEN_MODEL},
        )
        return _analyze_image_with_qwen_legacy(image_bytes, media_type)

    return _fallback_description()
