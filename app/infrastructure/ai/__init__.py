"""AI 基础设施公共入口。"""

from .fallback_gateway import AIFallbackExhaustedError, build_kwargs, call_with_fallback
from .provider_health import get_provider_circuit_summary
from .provider_registry import (
    get_active_client,
    get_fallback_client,
    get_provider_configs,
    is_provider_available,
    resolve_active_provider,
)

__all__ = [
    "AIFallbackExhaustedError",
    "build_kwargs",
    "call_with_fallback",
    "get_active_client",
    "get_fallback_client",
    "get_provider_circuit_summary",
    "get_provider_configs",
    "is_provider_available",
    "resolve_active_provider",
]
