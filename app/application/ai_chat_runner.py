"""Chat completion loops with tool-call support."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from ..ports import LLMGateway

ToolExecutor = Callable[[str, str], str]
ToolBatchCallback = Callable[[int, list[str], int], None]
FirstChunkCallback = Callable[[float], None]
ContentFilter = Callable[[str], str]


class ToolCallLimitExceededError(RuntimeError):
    """Raised when the model keeps requesting tools without a final answer."""

    def __init__(self, max_turns: int) -> None:
        self.max_turns = max_turns
        super().__init__(f"tool-call loop exhausted after {max_turns} turns")


class EmptyChatResponseError(RuntimeError):
    """Raised when a chat run completes without user-visible text."""

    def __init__(self) -> None:
        super().__init__("chat provider returned no user-visible text")


@dataclass
class ChatToolRunState:
    turns: int = 0
    tool_call_count: int = 0
    tool_names: list[str] = field(default_factory=list)
    output_chars: int = 0
    has_visible_content: bool = False
    first_chunk_ms: float | None = None

    @property
    def unique_tool_names(self) -> list[str]:
        return sorted(set(self.tool_names))


@dataclass
class SyncChatRunResult:
    content: str
    finish_reason: str
    state: ChatToolRunState


def run_sync_tool_chat(
    *,
    client: Any,
    model: str,
    provider_name: str,
    messages: list,
    llm_gateway: LLMGateway,
    tools_enabled: bool,
    available_tools: list[dict],
    execute_tool: ToolExecutor,
    state: ChatToolRunState | None = None,
    max_turns: int = 5,
    on_tool_batch: ToolBatchCallback | None = None,
    content_filter: ContentFilter | None = None,
) -> SyncChatRunResult:
    state = state or ChatToolRunState()
    for turn_index in range(max_turns):
        turn = turn_index + 1
        kwargs = llm_gateway.build_kwargs(model, provider_name, messages)
        if tools_enabled:
            kwargs["tools"] = available_tools

        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        message = choice.message
        finish_reason = choice.finish_reason

        if finish_reason != "tool_calls" or not message.tool_calls:
            state.turns = turn
            content = message.content or ""
            if content_filter:
                content = content_filter(content)
            if not content.strip():
                raise EmptyChatResponseError()
            return SyncChatRunResult(
                content=content,
                finish_reason=finish_reason,
                state=state,
            )

        messages.append(message)
        current_tool_names = _append_sync_tool_results(
            messages=messages,
            tool_calls=message.tool_calls,
            execute_tool=execute_tool,
            state=state,
        )
        if on_tool_batch:
            on_tool_batch(turn, current_tool_names, state.tool_call_count)
        state.turns = turn

    state.turns = max_turns
    raise ToolCallLimitExceededError(max_turns)


def iter_stream_tool_chat(
    *,
    client: Any,
    model: str,
    provider_name: str,
    messages: list,
    llm_gateway: LLMGateway,
    tools_enabled: bool,
    available_tools: list[dict],
    execute_tool: ToolExecutor,
    state: ChatToolRunState | None = None,
    start_time: float | None = None,
    max_turns: int = 5,
    on_first_chunk: FirstChunkCallback | None = None,
    on_tool_batch: ToolBatchCallback | None = None,
    content_filter: ContentFilter | None = None,
) -> Iterator[str]:
    state = state or ChatToolRunState()
    started_at = start_time if start_time is not None else time.time()

    for turn_index in range(max_turns):
        turn = turn_index + 1
        kwargs = llm_gateway.build_kwargs(model, provider_name, messages)
        kwargs["stream"] = True
        if tools_enabled:
            kwargs["tools"] = available_tools

        stream = client.chat.completions.create(**kwargs)
        tool_calls_buffer: dict[int, dict[str, str]] = {}

        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta

            if delta.content:
                content = content_filter(delta.content) if content_filter else delta.content
                if not content:
                    if delta.tool_calls:
                        for tool_call_delta in delta.tool_calls:
                            _append_stream_tool_delta(tool_calls_buffer, tool_call_delta)
                    continue
                state.output_chars += len(content)
                if content.strip():
                    state.has_visible_content = True
                if state.first_chunk_ms is None:
                    state.first_chunk_ms = round((time.time() - started_at) * 1000, 1)
                    if on_first_chunk:
                        on_first_chunk(state.first_chunk_ms)
                yield content

            if delta.tool_calls:
                for tool_call_delta in delta.tool_calls:
                    _append_stream_tool_delta(tool_calls_buffer, tool_call_delta)

        if not tool_calls_buffer:
            state.turns = turn
            if not state.has_visible_content:
                raise EmptyChatResponseError()
            return

        messages.append(_build_stream_assistant_message(tool_calls_buffer))
        current_tool_names = _append_stream_tool_results(
            messages=messages,
            tool_calls_buffer=tool_calls_buffer,
            execute_tool=execute_tool,
            state=state,
        )
        if on_tool_batch:
            on_tool_batch(turn, current_tool_names, state.tool_call_count)
        state.turns = turn

    state.turns = max_turns
    raise ToolCallLimitExceededError(max_turns)


def _append_sync_tool_results(
    *,
    messages: list,
    tool_calls: list,
    execute_tool: ToolExecutor,
    state: ChatToolRunState,
) -> list[str]:
    current_tool_names: list[str] = []
    for tool_call in tool_calls:
        func_name = tool_call.function.name
        func_args = tool_call.function.arguments
        current_tool_names.append(func_name)
        state.tool_names.append(func_name)
        state.tool_call_count += 1
        func_result = execute_tool(func_name, func_args)
        messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": func_result})
    return current_tool_names


def _append_stream_tool_delta(
    tool_calls_buffer: dict[int, dict[str, str]],
    tool_call_delta: Any,
) -> None:
    idx = int(tool_call_delta.index)
    entry = tool_calls_buffer.setdefault(idx, {"id": "", "name": "", "arguments": ""})
    if tool_call_delta.id:
        entry["id"] = tool_call_delta.id
    function = tool_call_delta.function
    if function.name:
        entry["name"] = function.name
    if function.arguments:
        entry["arguments"] += function.arguments


def _build_stream_assistant_message(tool_calls_buffer: dict[int, dict[str, str]]) -> dict:
    assistant_msg = {"role": "assistant", "tool_calls": []}
    for _, tool_call in sorted(tool_calls_buffer.items()):
        assistant_msg["tool_calls"].append(
            {
                "id": tool_call["id"],
                "type": "function",
                "function": {
                    "name": tool_call["name"],
                    "arguments": tool_call["arguments"],
                },
            }
        )
    return assistant_msg


def _append_stream_tool_results(
    *,
    messages: list,
    tool_calls_buffer: dict[int, dict[str, str]],
    execute_tool: ToolExecutor,
    state: ChatToolRunState,
) -> list[str]:
    current_tool_names: list[str] = []
    for _, tool_call in sorted(tool_calls_buffer.items()):
        name = tool_call["name"]
        arguments = tool_call["arguments"]
        current_tool_names.append(name)
        state.tool_names.append(name)
        state.tool_call_count += 1
        result = execute_tool(name, arguments)
        messages.append({"role": "tool", "tool_call_id": tool_call["id"], "content": result})
    return current_tool_names
