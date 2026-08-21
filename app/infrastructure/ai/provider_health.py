"""AI provider 熔断状态与运行健康摘要。"""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime
from threading import Lock
from typing import Any

from ...config import Config
from ...logger import logger
from ...observability import record_degradation

_PROVIDER_ALIASES = {
    "cerebras": "cerebras",
    "Cerebras": "cerebras",
    "deepseek": "deepseek",
    "DeepSeek": "deepseek",
    "groq": "groq",
    "Groq": "groq",
}
_PROVIDER_DISPLAY = {
    "cerebras": "Cerebras",
    "deepseek": "DeepSeek",
    "groq": "Groq",
}
_CIRCUITS: dict[str, dict[str, Any]] = {}
_LOCK = Lock()


def normalize_provider_key(provider: str | None) -> str | None:
    if not provider:
        return None
    return _PROVIDER_ALIASES.get(provider, provider.lower())


def _new_circuit() -> dict[str, Any]:
    return {
        "state": "closed",
        "failures": deque(),
        "opened_until": 0.0,
        "probe_in_flight": False,
        "last_failure_at": None,
        "last_opened_at": None,
        "last_recovered_at": None,
        "last_error_type": None,
    }


def _get_circuit(provider_key: str) -> dict[str, Any]:
    if provider_key not in _CIRCUITS:
        _CIRCUITS[provider_key] = _new_circuit()
    return _CIRCUITS[provider_key]


def _prune_failures(circuit: dict[str, Any], now: float) -> None:
    cutoff = now - Config.AI_CIRCUIT_WINDOW_SECONDS
    failures = circuit["failures"]
    while failures and failures[0] < cutoff:
        failures.popleft()


def _timestamp_to_iso(timestamp: float | None) -> str | None:
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp).isoformat()


def _open_circuit(
    provider_key: str,
    circuit: dict[str, Any],
    now: float,
    *,
    reason: str,
    error_type: str | None,
    operation: str,
    stream: bool,
) -> None:
    circuit["state"] = "open"
    circuit["opened_until"] = now + Config.AI_CIRCUIT_OPEN_SECONDS
    circuit["probe_in_flight"] = False
    circuit["last_opened_at"] = now
    circuit["last_error_type"] = error_type

    display_name = _PROVIDER_DISPLAY.get(provider_key, provider_key)
    logger.warning(
        "⚡ AI provider 熔断开启",
        extra={
            "provider": display_name,
            "reason": reason,
            "failure_count": len(circuit["failures"]),
            "open_seconds": Config.AI_CIRCUIT_OPEN_SECONDS,
        },
    )
    record_degradation(
        "ai_circuit",
        reason,
        severity="warning",
        provider=display_name,
        provider_key=provider_key,
        operation=operation,
        stream=stream,
        error_type=error_type,
        failure_count=len(circuit["failures"]),
        window_seconds=Config.AI_CIRCUIT_WINDOW_SECONDS,
        open_seconds=Config.AI_CIRCUIT_OPEN_SECONDS,
    )


def can_try_provider(
    provider: str | None,
    *,
    now: float | None = None,
    reserve_probe: bool = True,
) -> tuple[bool, str | None]:
    """判断 provider 当前是否允许被调用；真实调用时会占用半开探测名额。"""
    if not Config.AI_CIRCUIT_ENABLED:
        return True, None

    provider_key = normalize_provider_key(provider)
    if not provider_key:
        return True, None

    now = time.time() if now is None else now
    with _LOCK:
        circuit = _get_circuit(provider_key)
        _prune_failures(circuit, now)

        if circuit["state"] == "open":
            if now < circuit["opened_until"]:
                return False, "circuit_open"
            if not reserve_probe:
                return True, "circuit_half_open_ready"
            circuit["state"] = "half_open"
            circuit["probe_in_flight"] = True
            return True, "circuit_half_open_probe"

        if circuit["state"] == "half_open":
            if circuit["probe_in_flight"]:
                return False, "circuit_half_open_probe_in_flight"
            if not reserve_probe:
                return True, "circuit_half_open_ready"
            circuit["probe_in_flight"] = True
            return True, "circuit_half_open_probe"

    return True, None


def record_provider_success(
    provider: str | None,
    *,
    operation: str = "chat",
    stream: bool = False,
) -> None:
    if not Config.AI_CIRCUIT_ENABLED:
        return

    provider_key = normalize_provider_key(provider)
    if not provider_key:
        return

    now = time.time()
    with _LOCK:
        circuit = _get_circuit(provider_key)
        previous_state = circuit["state"]
        circuit["state"] = "closed"
        circuit["failures"].clear()
        circuit["opened_until"] = 0.0
        circuit["probe_in_flight"] = False
        if previous_state in {"open", "half_open"}:
            circuit["last_recovered_at"] = now
        circuit["last_error_type"] = None

    if previous_state in {"open", "half_open"}:
        display_name = _PROVIDER_DISPLAY.get(provider_key, provider_key)
        logger.info(
            "✅ AI provider 熔断恢复",
            extra={"provider": display_name, "operation": operation, "stream": stream},
        )
        record_degradation(
            "ai_circuit",
            "provider_circuit_recovered",
            severity="info",
            provider=display_name,
            provider_key=provider_key,
            operation=operation,
            stream=stream,
        )


def record_provider_failure(
    provider: str | None,
    *,
    error_type: str | None = None,
    operation: str = "chat",
    stream: bool = False,
) -> None:
    if not Config.AI_CIRCUIT_ENABLED:
        return

    provider_key = normalize_provider_key(provider)
    if not provider_key:
        return

    now = time.time()
    should_open = False
    open_reason = "provider_circuit_opened"

    with _LOCK:
        circuit = _get_circuit(provider_key)
        circuit["failures"].append(now)
        circuit["last_failure_at"] = now
        circuit["last_error_type"] = error_type
        _prune_failures(circuit, now)

        if circuit["state"] == "half_open":
            should_open = True
            open_reason = "provider_circuit_probe_failed"
        elif circuit["state"] == "closed" and len(circuit["failures"]) >= Config.AI_CIRCUIT_FAILURE_THRESHOLD:
            should_open = True

        if should_open:
            _open_circuit(
                provider_key,
                circuit,
                now,
                reason=open_reason,
                error_type=error_type,
                operation=operation,
                stream=stream,
            )
        elif circuit["state"] == "half_open":
            circuit["probe_in_flight"] = False


def get_provider_circuit_summary(*, now: float | None = None) -> dict[str, Any]:
    now = time.time() if now is None else now
    with _LOCK:
        providers: dict[str, Any] = {}
        for provider_key in _PROVIDER_DISPLAY:
            circuit = _get_circuit(provider_key)
            _prune_failures(circuit, now)
            remaining_open_seconds = 0.0
            state = circuit["state"]
            if circuit["state"] == "open":
                remaining_open_seconds = max(0.0, circuit["opened_until"] - now)
                if remaining_open_seconds <= 0:
                    state = "half_open_ready"

            providers[provider_key] = {
                "name": _PROVIDER_DISPLAY.get(provider_key, provider_key),
                "state": state,
                "recent_failures": len(circuit["failures"]),
                "remaining_open_seconds": round(remaining_open_seconds, 1),
                "probe_in_flight": bool(circuit["probe_in_flight"]),
                "last_failure_at": _timestamp_to_iso(circuit["last_failure_at"]),
                "last_opened_at": _timestamp_to_iso(circuit["last_opened_at"]),
                "last_recovered_at": _timestamp_to_iso(circuit["last_recovered_at"]),
                "last_error_type": circuit["last_error_type"],
            }

    return {
        "enabled": Config.AI_CIRCUIT_ENABLED,
        "failure_threshold": Config.AI_CIRCUIT_FAILURE_THRESHOLD,
        "window_seconds": Config.AI_CIRCUIT_WINDOW_SECONDS,
        "open_seconds": Config.AI_CIRCUIT_OPEN_SECONDS,
        "providers": providers,
    }


def reset_provider_circuits() -> None:
    """测试与人工排障使用：重置所有 provider 熔断状态。"""
    with _LOCK:
        _CIRCUITS.clear()
