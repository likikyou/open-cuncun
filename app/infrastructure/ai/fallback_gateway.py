"""AI fallback 调用网关。"""

from __future__ import annotations

import time

from ...logger import logger
from ...observability import record_degradation
from .provider_health import record_provider_failure, record_provider_success
from .provider_registry import get_fallback_client


class AIFallbackExhaustedError(RuntimeError):
    """AI 主引擎与 fallback 链路都失败时抛出。"""

    def __init__(
        self,
        primary_name: str,
        *,
        fallback_name: str | None = None,
        stream: bool = False,
        attempts: list[dict] | None = None,
    ) -> None:
        self.primary_name = primary_name
        self.fallback_name = fallback_name
        self.stream = stream
        self.attempts = attempts or []
        mode = "stream" if stream else "sync"
        chain = f"{primary_name}->{fallback_name}" if fallback_name else primary_name
        super().__init__(f"AI fallback exhausted ({mode}): {chain}")


def _build_attempt(provider_name: str, exc: Exception) -> dict[str, str]:
    return {
        "provider": provider_name,
        "error_type": exc.__class__.__name__,
        "message": str(exc),
    }


def _build_skipped_attempt(provider_name: str) -> dict[str, str]:
    return {
        "provider": provider_name,
        "error_type": "PrimaryAlreadyFailed",
        "message": "primary provider was already attempted by caller",
    }


def build_kwargs(
    model: str,
    provider_name: str,
    messages: list,
    temperature: float = 1.0,
    max_tokens: int = 2048,
) -> dict:
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if provider_name not in ("Cerebras", "Groq"):
        kwargs["presence_penalty"] = 0.4
        kwargs["frequency_penalty"] = 0.3
    return kwargs


def call_with_fallback(
    primary_client,
    primary_model: str,
    primary_name: str,
    messages: list,
    stream: bool = False,
    extra_kwargs: dict | None = None,
    operation: str = "chat",
    skip_primary: bool = False,
    primary_error: Exception | None = None,
):
    start_time = time.time()
    kwargs = build_kwargs(primary_model, primary_name, messages)
    if extra_kwargs:
        kwargs.update(extra_kwargs)
    if stream:
        kwargs["stream"] = True

        def generate():
            attempts: list[dict[str, str]] = []
            if skip_primary:
                attempts.append(
                    _build_attempt(primary_name, primary_error)
                    if primary_error
                    else _build_skipped_attempt(primary_name)
                )
            else:
                try:
                    stream_obj = primary_client.chat.completions.create(**kwargs)
                    for chunk in stream_obj:
                        if chunk.choices and chunk.choices[0].delta.content:
                            yield chunk.choices[0].delta.content
                    record_provider_success(primary_name, operation=operation, stream=True)
                    duration = time.time() - start_time
                    logger.info(
                        f"✅ AI流式响应完成 [{primary_name}]",
                        extra={"duration": round(duration, 2)},
                    )
                    return
                except Exception as exc:
                    attempts.append(_build_attempt(primary_name, exc))
                    record_provider_failure(
                        primary_name,
                        error_type=exc.__class__.__name__,
                        operation=operation,
                        stream=True,
                    )
                    logger.error(f"❌ AI错误 [{primary_name}]: {exc}", exc_info=True)

            fallback = get_fallback_client(primary_name)
            if not fallback:
                record_degradation(
                    "ai_fallback",
                    "stream_no_fallback_available",
                    severity="error",
                    primary_provider=primary_name,
                    attempts=attempts,
                )
                raise AIFallbackExhaustedError(
                    primary_name,
                    stream=True,
                    attempts=attempts,
                )

            _, fb_client, fb_model, fb_name = fallback
            logger.info(f"⚡ [{primary_name}] 失败，自动切换到 [{fb_name}]")
            fb_kwargs = build_kwargs(fb_model, fb_name, messages)
            if extra_kwargs:
                safe_kwargs = {
                    key: value
                    for key, value in extra_kwargs.items()
                    if key not in ("tools", "tool_choice")
                }
                fb_kwargs.update(safe_kwargs)
            fb_kwargs["stream"] = True

            try:
                stream_obj = fb_client.chat.completions.create(**fb_kwargs)
                for chunk in stream_obj:
                    if chunk.choices and chunk.choices[0].delta.content:
                        yield chunk.choices[0].delta.content
                record_provider_success(fb_name, operation=operation, stream=True)
                duration = time.time() - start_time
                record_degradation(
                    "ai_fallback",
                    "stream_fallback_succeeded",
                    severity="warning",
                    primary_provider=primary_name,
                    fallback_provider=fb_name,
                    attempts=attempts,
                )
                logger.info(
                    f"✅ [{fb_name}] 流式降级回复完成", extra={"duration": round(duration, 2)}
                )
                return
            except Exception as exc:
                attempts.append(_build_attempt(fb_name, exc))
                record_provider_failure(
                    fb_name,
                    error_type=exc.__class__.__name__,
                    operation=operation,
                    stream=True,
                )
                record_degradation(
                    "ai_fallback",
                    "stream_fallback_exhausted",
                    severity="error",
                    primary_provider=primary_name,
                    fallback_provider=fb_name,
                    attempts=attempts,
                )
                logger.error(f"❌ [{fb_name}] 降级也失败: {exc}", exc_info=True)
                raise AIFallbackExhaustedError(
                    primary_name,
                    fallback_name=fb_name,
                    stream=True,
                    attempts=attempts,
                ) from exc

        return generate()

    primary_exc = primary_error
    primary_attempt = (
        _build_attempt(primary_name, primary_error)
        if primary_error
        else _build_skipped_attempt(primary_name)
    )
    if not skip_primary:
        try:
            response = primary_client.chat.completions.create(**kwargs)
            record_provider_success(primary_name, operation=operation, stream=False)
            duration = time.time() - start_time
            logger.info(f"✅ AI响应成功 [{primary_name}]", extra={"duration": round(duration, 2)})
            return response.choices[0].message.content
        except Exception as exc:
            primary_exc = exc
            primary_attempt = _build_attempt(primary_name, exc)
            record_provider_failure(
                primary_name,
                error_type=exc.__class__.__name__,
                operation=operation,
                stream=False,
            )
            logger.error(f"❌ AI错误 [{primary_name}]: {exc}", exc_info=True)

    fallback = get_fallback_client(primary_name)
    if not fallback:
        record_degradation(
            "ai_fallback",
            "sync_no_fallback_available",
            severity="error",
            primary_provider=primary_name,
            attempts=[primary_attempt],
        )
        raise AIFallbackExhaustedError(
            primary_name,
            stream=False,
            attempts=[primary_attempt],
        ) from primary_exc

    _, fb_client, fb_model, fb_name = fallback
    logger.info(f"⚡ [{primary_name}] 失败，自动切换到 [{fb_name}]")
    try:
        kwargs = build_kwargs(fb_model, fb_name, messages)
        if extra_kwargs:
            safe_kwargs = {
                key: value
                for key, value in extra_kwargs.items()
                if key not in ("tools", "tool_choice")
            }
            kwargs.update(safe_kwargs)
        response = fb_client.chat.completions.create(**kwargs)
        record_provider_success(fb_name, operation=operation, stream=False)
        duration = time.time() - start_time
        record_degradation(
            "ai_fallback",
            "sync_fallback_succeeded",
            severity="warning",
            primary_provider=primary_name,
            fallback_provider=fb_name,
            attempts=[primary_attempt],
        )
        logger.info(f"✅ [{fb_name}] 降级回复完成", extra={"duration": round(duration, 2)})
        return response.choices[0].message.content
    except Exception as exc:
        fallback_attempt = _build_attempt(fb_name, exc)
        record_provider_failure(
            fb_name,
            error_type=exc.__class__.__name__,
            operation=operation,
            stream=False,
        )
        attempts = [primary_attempt, fallback_attempt]
        record_degradation(
            "ai_fallback",
            "sync_fallback_exhausted",
            severity="error",
            primary_provider=primary_name,
            fallback_provider=fb_name,
            attempts=attempts,
        )
        logger.error(f"❌ [{fb_name}] 降级也失败: {exc}", exc_info=True)
        raise AIFallbackExhaustedError(
            primary_name,
            fallback_name=fb_name,
            stream=False,
            attempts=attempts,
        ) from exc
