"""
Base Provider — abstract interface for LLM API providers.
v4: CC-aligned parameter expansion:
  - Extended Thinking (adaptive/budget-limited)
  - Effort level (low/medium/high)
  - Prompt caching (cache_control)
  - Structured output (output_schema)
  - Cache token tracking (cache_read/cache_creation)
  - Stop reason forwarding
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generator, Iterator
import threading


@dataclass
class ToolCall:
    """Parsed tool call from any provider."""
    id: str
    name: str
    input: dict


@dataclass
class ToolDef:
    """Tool definition for provider formatting."""
    name: str
    description: str
    input_schema: dict  # JSON Schema


@dataclass
class StreamChunk:
    """A chunk from the streaming response."""
    type: str  # "text_delta", "tool_call_start", "tool_call_delta", "tool_call_end", "done"
    text: str = ""                   # text content for text_delta
    tool_call_id: str = ""           # for tool_call_* types
    tool_name: str = ""              # for tool_call_start
    tool_arguments_delta: str = ""   # partial JSON for tool_call_delta


@dataclass
class LLMCallParams:
    """
    CC-aligned: extended parameters for LLM API calls.
    Passed from engine to provider to control model behavior.
    """
    thinking: dict | None = None
    """Extended thinking config. CC: {"type":"enabled","budget_tokens":N} or None.
    Set to {"type":"enabled","budget_tokens":10000} to enable.
    Provider should auto-select adaptive vs budget-limited based on model."""

    effort: str | None = None
    """Reasoning effort level: "low", "medium", "high", or None.
    CC: Passed via anthropic-beta header."""

    cache_control: bool = False
    """Whether to add cache_control: {"type":"ephemeral"} to system + last user msg.
    CC: Enables prompt caching to reduce token costs on repeated system prompts."""

    output_schema: dict | None = None
    """JSON Schema for structured output. CC: response_format parameter.
    When set, model output is constrained to match this schema."""

    temperature: float | None = None
    """Temperature for sampling. CC: Only applied when thinking is disabled."""

    stop_sequences: list[str] | None = None
    """Optional stop sequences."""

    session_id: str | None = None
    """Session UUID for X-Claude-Code-Session-Id header tracking."""

    request_id: str | None = None
    """Previous request ID for streaming correlation (CC: request ID chaining)."""


class AbortSignal:
    """Thread-safe abort signal (like AbortController in JS)."""

    def __init__(self):
        self._event = threading.Event()
        self.reason: str = ""

    @property
    def aborted(self) -> bool:
        return self._event.is_set()

    def abort(self, reason: str = "user_cancel"):
        self.reason = reason
        self._event.set()

    def reset(self):
        self._event.clear()
        self.reason = ""

    def check(self):
        """Raise InterruptedError if aborted."""
        if self._event.is_set():
            raise InterruptedError(f"Aborted: {self.reason}")


class BaseProvider(ABC):
    """Abstract base for LLM API providers."""

    @abstractmethod
    def call_sync(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = 4096,
        abort_signal: AbortSignal | None = None,
        params: LLMCallParams | None = None,
    ) -> tuple[Any, list[ToolCall], str]:
        """
        Synchronous message creation (called from background thread).

        Args:
            messages: Conversation history
            system: System prompt
            tools: Formatted tool definitions
            max_tokens: Max output tokens
            abort_signal: Cancellation signal
            params: CC-aligned extended parameters (thinking, effort, cache, etc.)

        Returns:
            (raw_assistant_content, tool_calls, text_response)
            raw_assistant_content may include "_usage" dict with token tracking:
              {"_usage": {"input_tokens": N, "output_tokens": N,
                          "cache_creation_input_tokens": N, "cache_read_input_tokens": N},
               "_stop_reason": "end_turn"|"max_tokens"|"tool_use"|"stop_sequence"}
        """
        ...

    def call_stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = 4096,
        abort_signal: AbortSignal | None = None,
        params: LLMCallParams | None = None,
    ) -> Generator[StreamChunk, None, tuple[Any, list[ToolCall], str]]:
        """
        Streaming message creation. Yields StreamChunks as they arrive.
        Checks abort_signal between chunks and raises InterruptedError if aborted.
        """
        raw, tool_calls, text = self.call_sync(messages, system, tools, max_tokens, abort_signal, params)
        if text:
            yield StreamChunk(type="text_delta", text=text)
        yield StreamChunk(type="done")
        return raw, tool_calls, text

    @property
    def supports_streaming(self) -> bool:
        """Whether this provider supports real streaming."""
        return False

    @abstractmethod
    def format_tools(self, tools: list[ToolDef]) -> list[dict]:
        """Convert tool definitions to provider-specific format."""
        ...

    @abstractmethod
    def format_tool_results(self, tool_calls: list[ToolCall], results: list[dict]) -> dict:
        """
        Format tool results into a message for the provider.
        Returns a message dict {"role": ..., "content": ...}
        """
        ...
