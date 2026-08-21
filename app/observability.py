"""运行时观测：降级事件与 AI 运行摘要。"""

from __future__ import annotations

import time
from collections import Counter, deque
from datetime import datetime
from threading import Lock
from typing import Any

_MAX_RECENT_DEGRADATIONS = 200
_recent_degradations: deque[dict[str, Any]] = deque(maxlen=_MAX_RECENT_DEGRADATIONS)
_recent_degradations_lock = Lock()
_MAX_RECENT_AI_RUNS = 200
_recent_ai_runs: deque[dict[str, Any]] = deque(maxlen=_MAX_RECENT_AI_RUNS)
_recent_ai_runs_lock = Lock()


def _compact_value(value: Any, *, max_length: int = 120) -> Any:
    if isinstance(value, str):
        compact = " ".join(value.split())
        if len(compact) <= max_length:
            return compact
        return compact[:max_length].rstrip() + "..."
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        compact_items = [_compact_value(item, max_length=max_length) for item in value[:8]]
        if len(value) > 8:
            compact_items.append(f"...(+{len(value) - 8})")
        return compact_items
    if isinstance(value, dict):
        compact_dict: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= 12:
                compact_dict["..."] = f"+{len(value) - 12} more"
                break
            compact_dict[str(key)] = _compact_value(item, max_length=max_length)
        return compact_dict
    return _compact_value(str(value), max_length=max_length)


def record_degradation(
    component: str,
    reason: str,
    *,
    severity: str = "warning",
    **details: Any,
) -> dict[str, Any]:
    """记录一次可观测的降级事件，供健康检查与排障查看。"""
    event: dict[str, Any] = {
        "timestamp": time.time(),
        "component": component,
        "reason": reason,
        "severity": severity,
    }
    compact_details = {
        key: value for key, value in details.items() if value is not None and value != ""
    }
    if compact_details:
        event["details"] = compact_details

    with _recent_degradations_lock:
        _recent_degradations.append(event)
    return event


def record_ai_run(
    stage: str,
    *,
    operation: str = "chat",
    provider: str | None = None,
    model: str | None = None,
    user_id: str | None = None,
    stream: bool = False,
    **details: Any,
) -> dict[str, Any]:
    """记录一次 AI 运行事件，供 /health 与排障查看。"""
    event: dict[str, Any] = {
        "timestamp": time.time(),
        "stage": stage,
        "operation": operation,
        "stream": bool(stream),
    }
    if provider:
        event["provider"] = provider
    if model:
        event["model"] = model
    if user_id:
        event["user_id"] = user_id

    compact_details = {
        key: _compact_value(value)
        for key, value in details.items()
        if value is not None and value != ""
    }
    if compact_details:
        event["details"] = compact_details

    with _recent_ai_runs_lock:
        _recent_ai_runs.append(event)
    return event


def get_recent_degradations(window_seconds: int = 300) -> list[dict[str, Any]]:
    """返回最近窗口内的降级事件快照。"""
    cutoff = time.time() - max(window_seconds, 0)
    with _recent_degradations_lock:
        return [
            dict(event)
            for event in _recent_degradations
            if float(event.get("timestamp", 0.0)) >= cutoff
        ]


def summarize_recent_degradations(
    window_seconds: int = 300,
    *,
    recent_limit: int = 5,
) -> dict[str, Any]:
    """聚合最近窗口内的降级统计，供 /health 使用。"""
    events = get_recent_degradations(window_seconds)
    by_component = Counter(str(event.get("component", "unknown")) for event in events)
    by_severity = Counter(str(event.get("severity", "warning")) for event in events)
    by_reason = Counter(
        f"{event.get('component', 'unknown')}:{event.get('reason', 'unknown')}" for event in events
    )

    recent_events = []
    for event in events[-recent_limit:]:
        recent_events.append(
            {
                "timestamp": datetime.fromtimestamp(float(event.get("timestamp", 0.0))).isoformat(),
                "component": event.get("component"),
                "reason": event.get("reason"),
                "severity": event.get("severity"),
                "details": event.get("details", {}),
            }
        )

    return {
        "window_seconds": window_seconds,
        "count": len(events),
        "by_component": dict(by_component),
        "by_severity": dict(by_severity),
        "top_reasons": dict(by_reason.most_common(5)),
        "recent": recent_events,
    }


def get_recent_ai_runs(window_seconds: int = 300) -> list[dict[str, Any]]:
    """返回最近窗口内的 AI 运行事件快照。"""
    cutoff = time.time() - max(window_seconds, 0)
    with _recent_ai_runs_lock:
        return [
            dict(event) for event in _recent_ai_runs if float(event.get("timestamp", 0.0)) >= cutoff
        ]


def summarize_recent_ai_runs(
    window_seconds: int = 300,
    *,
    recent_limit: int = 5,
) -> dict[str, Any]:
    """聚合最近窗口内的 AI 运行概况，供 /health 使用。"""
    events = get_recent_ai_runs(window_seconds)
    by_stage = Counter(str(event.get("stage", "unknown")) for event in events)
    by_operation = Counter(str(event.get("operation", "unknown")) for event in events)
    by_provider = Counter(str(event.get("provider", "unknown")) for event in events)
    stream_count = sum(1 for event in events if bool(event.get("stream")))
    fallback_attempts = sum(
        1 for event in events if bool(event.get("details", {}).get("fallback_attempted"))
    )

    tool_counter: Counter[str] = Counter()
    recent_events = []
    for event in events[-recent_limit:]:
        details = dict(event.get("details", {}))
        tool_names = details.get("tool_names")
        if isinstance(tool_names, list):
            for tool_name in tool_names:
                if tool_name:
                    tool_counter[str(tool_name)] += 1
        recent_events.append(
            {
                "timestamp": datetime.fromtimestamp(float(event.get("timestamp", 0.0))).isoformat(),
                "stage": event.get("stage"),
                "operation": event.get("operation"),
                "provider": event.get("provider"),
                "model": event.get("model"),
                "stream": bool(event.get("stream")),
                "details": details,
            }
        )

    return {
        "window_seconds": window_seconds,
        "count": len(events),
        "by_stage": dict(by_stage),
        "by_operation": dict(by_operation),
        "by_provider": dict(by_provider),
        "stream_count": stream_count,
        "fallback_attempts": fallback_attempts,
        "top_tools": dict(tool_counter.most_common(5)),
        "recent": recent_events,
    }
