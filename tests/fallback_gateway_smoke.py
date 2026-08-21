import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.infrastructure.ai import fallback_gateway
from app.infrastructure.ai.fallback_gateway import (
    AIFallbackExhaustedError,
    call_with_fallback,
)


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)

    def create(self, **_kwargs):
        return self.responses.pop(0)


def _client(*responses):
    completions = FakeCompletions(responses)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def _stream_chunk(content=None):
    delta = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _response(content):
    message = SimpleNamespace(content=content)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _configure_fallback(monkeypatch, fallback_client) -> None:
    monkeypatch.setattr(
        fallback_gateway,
        "get_fallback_client",
        lambda _primary_name: ("fallback", fallback_client, "fallback-model", "Fallback"),
    )
    monkeypatch.setattr(fallback_gateway, "record_provider_success", lambda *_a, **_kw: None)
    monkeypatch.setattr(fallback_gateway, "record_provider_failure", lambda *_a, **_kw: None)
    monkeypatch.setattr(fallback_gateway, "record_degradation", lambda *_a, **_kw: None)


def test_empty_primary_stream_uses_fallback(monkeypatch) -> None:
    primary_client = _client(iter([]))
    fallback_client = _client(iter([_stream_chunk("fallback answer")]))
    _configure_fallback(monkeypatch, fallback_client)

    chunks = list(
        call_with_fallback(
            primary_client,
            "primary-model",
            "Primary",
            [{"role": "user", "content": "hello"}],
            stream=True,
        )
    )

    assert chunks == ["fallback answer"]


def test_empty_sync_primary_uses_fallback(monkeypatch) -> None:
    primary_client = _client(_response(""))
    fallback_client = _client(_response("fallback answer"))
    _configure_fallback(monkeypatch, fallback_client)

    result = call_with_fallback(
        primary_client,
        "primary-model",
        "Primary",
        [{"role": "user", "content": "hello"}],
    )

    assert result == "fallback answer"


def test_empty_fallback_stream_is_exhausted(monkeypatch) -> None:
    primary_client = _client(iter([]))
    fallback_client = _client(iter([_stream_chunk("   ")]))
    _configure_fallback(monkeypatch, fallback_client)

    with pytest.raises(AIFallbackExhaustedError):
        list(
            call_with_fallback(
                primary_client,
                "primary-model",
                "Primary",
                [{"role": "user", "content": "hello"}],
                stream=True,
            )
        )
