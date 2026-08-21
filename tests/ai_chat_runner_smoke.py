import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ai_engine import _ThinkingTagStreamFilter, _strip_thinking_tags
from app.application.ai_chat_runner import (
    ChatToolRunState,
    EmptyChatResponseError,
    ToolCallLimitExceededError,
    iter_stream_tool_chat,
    run_sync_tool_chat,
)


class FakeGateway:
    def build_kwargs(self, model, provider_name, messages, temperature=1.0, max_tokens=2048):
        return {
            "model": model,
            "provider_name": provider_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }


class FakeCompletions:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.responses:
            raise AssertionError("unexpected extra model call")
        return self.responses.pop(0)


def _client_with_responses(responses):
    completions = FakeCompletions(responses)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    return client, completions


def _chat_response(*, content="", finish_reason="stop", tool_calls=None):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _tool_call(tool_id="tool_1", name="lookup", arguments='{"q":"x"}'):
    return SimpleNamespace(
        id=tool_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def _stream_chunk(content=None, tool_calls=None):
    delta = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(choices=[SimpleNamespace(delta=delta)])


def _tool_delta(index=0, tool_id=None, name=None, arguments=None):
    return SimpleNamespace(
        index=index,
        id=tool_id,
        function=SimpleNamespace(name=name, arguments=arguments),
    )


def test_sync_tool_chat_runs_tools_and_returns_final_content() -> None:
    client, completions = _client_with_responses(
        [
            _chat_response(
                finish_reason="tool_calls",
                tool_calls=[_tool_call(name="lookup", arguments='{"q":"weather"}')],
            ),
            _chat_response(content="final answer"),
        ]
    )
    messages = [{"role": "user", "content": "hi"}]
    batches = []

    result = run_sync_tool_chat(
        client=client,
        model="model-a",
        provider_name="Cerebras",
        messages=messages,
        llm_gateway=FakeGateway(),
        tools_enabled=True,
        available_tools=[{"type": "function", "function": {"name": "lookup"}}],
        execute_tool=lambda name, args: f"{name}:{args}",
        state=ChatToolRunState(),
        on_tool_batch=lambda turn, names, count: batches.append((turn, names, count)),
    )

    assert result.content == "final answer"
    assert result.state.turns == 2
    assert result.state.tool_call_count == 1
    assert result.state.unique_tool_names == ["lookup"]
    assert batches == [(1, ["lookup"], 1)]
    assert completions.calls[0]["tools"]
    assert messages[-1] == {
        "role": "tool",
        "tool_call_id": "tool_1",
        "content": 'lookup:{"q":"weather"}',
    }


@pytest.mark.parametrize("content", [None, "", "  \n", "<think>hidden</think>"])
def test_sync_tool_chat_rejects_empty_visible_content(content) -> None:
    client, _completions = _client_with_responses([_chat_response(content=content)])

    with pytest.raises(EmptyChatResponseError):
        run_sync_tool_chat(
            client=client,
            model="model-a",
            provider_name="Cerebras",
            messages=[{"role": "user", "content": "hi"}],
            llm_gateway=FakeGateway(),
            tools_enabled=False,
            available_tools=[],
            execute_tool=lambda name, args: f"{name}:{args}",
            content_filter=_strip_thinking_tags,
        )


def test_stream_tool_chat_filters_thinking_chunks() -> None:
    client, _completions = _client_with_responses(
        [
            iter(
                [
                    _stream_chunk("hello <thi"),
                    _stream_chunk("nk>hidden"),
                    _stream_chunk("</think> world"),
                ]
            )
        ]
    )
    state = ChatToolRunState()
    thinking_filter = _ThinkingTagStreamFilter()

    chunks = list(
        iter_stream_tool_chat(
            client=client,
            model="model-a",
            provider_name="Cerebras",
            messages=[{"role": "user", "content": "hi"}],
            llm_gateway=FakeGateway(),
            tools_enabled=False,
            available_tools=[],
            execute_tool=lambda name, args: f"{name}:{args}",
            state=state,
            content_filter=thinking_filter.feed,
        )
    )
    tail = thinking_filter.flush()
    if tail:
        chunks.append(tail)

    assert chunks == ["hello ", " world"]
    assert state.output_chars == len("hello  world")
    assert state.first_chunk_ms is not None
    assert state.turns == 1


def test_stream_tool_chat_rejects_empty_visible_content() -> None:
    client, _completions = _client_with_responses(
        [iter([_stream_chunk("  "), _stream_chunk("<think>hidden</think>")])]
    )
    thinking_filter = _ThinkingTagStreamFilter()

    with pytest.raises(EmptyChatResponseError):
        list(
            iter_stream_tool_chat(
                client=client,
                model="model-a",
                provider_name="Cerebras",
                messages=[{"role": "user", "content": "hi"}],
                llm_gateway=FakeGateway(),
                tools_enabled=False,
                available_tools=[],
                execute_tool=lambda name, args: f"{name}:{args}",
                content_filter=thinking_filter.feed,
            )
        )


def test_stream_tool_chat_runs_tool_then_continues_streaming() -> None:
    client, completions = _client_with_responses(
        [
            iter(
                [
                    _stream_chunk(
                        tool_calls=[
                            _tool_delta(
                                index=0,
                                tool_id="tool_1",
                                name="lookup",
                                arguments='{"q"',
                            )
                        ]
                    ),
                    _stream_chunk(tool_calls=[_tool_delta(index=0, arguments=':"weather"}')]),
                ]
            ),
            iter([_stream_chunk("tool answer")]),
        ]
    )
    messages = [{"role": "user", "content": "hi"}]
    batches = []
    state = ChatToolRunState()

    chunks = list(
        iter_stream_tool_chat(
            client=client,
            model="model-a",
            provider_name="Cerebras",
            messages=messages,
            llm_gateway=FakeGateway(),
            tools_enabled=True,
            available_tools=[{"type": "function", "function": {"name": "lookup"}}],
            execute_tool=lambda name, args: f"{name}:{args}",
            state=state,
            on_tool_batch=lambda turn, names, count: batches.append((turn, names, count)),
        )
    )

    assert chunks == ["tool answer"]
    assert batches == [(1, ["lookup"], 1)]
    assert state.turns == 2
    assert state.tool_call_count == 1
    assert state.output_chars == len("tool answer")
    assert len(completions.calls) == 2
    assert messages[-1] == {
        "role": "tool",
        "tool_call_id": "tool_1",
        "content": 'lookup:{"q":"weather"}',
    }


def test_stream_tool_chat_keeps_tool_delta_when_content_is_filtered_empty() -> None:
    client, _completions = _client_with_responses(
        [
            iter(
                [
                    _stream_chunk(
                        "<think>hidden</think>",
                        tool_calls=[
                            _tool_delta(
                                index=0,
                                tool_id="tool_1",
                                name="lookup",
                                arguments='{"q":"weather"}',
                            )
                        ],
                    ),
                ]
            ),
            iter([_stream_chunk("tool answer")]),
        ]
    )
    state = ChatToolRunState()
    thinking_filter = _ThinkingTagStreamFilter()

    chunks = list(
        iter_stream_tool_chat(
            client=client,
            model="model-a",
            provider_name="Cerebras",
            messages=[{"role": "user", "content": "hi"}],
            llm_gateway=FakeGateway(),
            tools_enabled=True,
            available_tools=[{"type": "function", "function": {"name": "lookup"}}],
            execute_tool=lambda name, args: f"{name}:{args}",
            state=state,
            content_filter=thinking_filter.feed,
        )
    )
    tail = thinking_filter.flush()
    if tail:
        chunks.append(tail)

    assert chunks == ["tool answer"]
    assert state.tool_call_count == 1
    assert state.output_chars == len("tool answer")


def test_sync_tool_chat_raises_when_tool_loop_is_exhausted() -> None:
    responses = [
        _chat_response(
            finish_reason="tool_calls",
            tool_calls=[_tool_call(tool_id=f"tool_{index}")],
        )
        for index in range(2)
    ]
    client, completions = _client_with_responses(responses)
    state = ChatToolRunState()

    with pytest.raises(ToolCallLimitExceededError):
        run_sync_tool_chat(
            client=client,
            model="model-a",
            provider_name="Cerebras",
            messages=[{"role": "user", "content": "hi"}],
            llm_gateway=FakeGateway(),
            tools_enabled=True,
            available_tools=[],
            execute_tool=lambda name, args: f"{name}:{args}",
            state=state,
            max_turns=2,
        )

    assert state.turns == 2
    assert state.tool_call_count == 2
    assert len(completions.calls) == 2


def test_stream_tool_chat_raises_when_tool_loop_is_exhausted() -> None:
    responses = [
        iter(
            [
                _stream_chunk(
                    tool_calls=[
                        _tool_delta(
                            tool_id=f"tool_{index}",
                            name="lookup",
                            arguments='{"q":"x"}',
                        )
                    ]
                )
            ]
        )
        for index in range(2)
    ]
    client, completions = _client_with_responses(responses)
    state = ChatToolRunState()

    with pytest.raises(ToolCallLimitExceededError):
        list(
            iter_stream_tool_chat(
                client=client,
                model="model-a",
                provider_name="Cerebras",
                messages=[{"role": "user", "content": "hi"}],
                llm_gateway=FakeGateway(),
                tools_enabled=True,
                available_tools=[],
                execute_tool=lambda name, args: f"{name}:{args}",
                state=state,
                max_turns=2,
            )
        )

    assert state.turns == 2
    assert state.tool_call_count == 2
    assert len(completions.calls) == 2
