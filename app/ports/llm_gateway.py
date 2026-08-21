"""LLM gateway port used by application services."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Protocol

ChatMessage = dict[str, Any]
LLMResponse = str | Iterable[str] | None


class LLMGateway(Protocol):
    def build_kwargs(
        self,
        model: str,
        provider_name: str,
        messages: list[ChatMessage],
        temperature: float = 1.0,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Build provider-specific chat completion kwargs."""

    def call_with_fallback(
        self,
        primary_client: Any,
        primary_model: str,
        primary_name: str,
        messages: list[ChatMessage],
        stream: bool = False,
        extra_kwargs: dict[str, Any] | None = None,
        operation: str = "chat",
        skip_primary: bool = False,
        primary_error: Exception | None = None,
    ) -> LLMResponse:
        """Call the selected model and fall back through the provider chain."""
