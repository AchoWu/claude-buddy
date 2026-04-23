"""
OpenAI-Compatible Provider — works with GPT-4o, DeepSeek, Qwen, Ollama, vLLM, etc.
Requires the API to support native function calling (tools parameter).
"""

import json
from openai import OpenAI
from typing import Any

from core.providers.base import BaseProvider, ToolCall, ToolDef, StreamChunk, AbortSignal, LLMCallParams


class OpenAIProvider(BaseProvider):
    """OpenAI-compatible provider. Requires native function calling support."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str | None = None,
        reasoning_enabled: bool = False,
    ):
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self._model = model
        self._reasoning_enabled = reasoning_enabled

    def call_sync(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = 4096,
        abort_signal: AbortSignal | None = None,
        params: LLMCallParams | None = None,
    ) -> tuple[Any, list[ToolCall], str]:
        # Build messages with system prompt
        api_messages = [{"role": "system", "content": system}]

        for msg in messages:
            converted = self._convert_message(msg)
            if isinstance(converted, list):
                api_messages.extend(converted)
            else:
                api_messages.append(converted)

        kwargs = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools

        # CC-aligned: inject reasoning for OpenRouter / compatible providers
        # when effort or thinking is requested.
        reasoning_body = self._build_reasoning_extra_body(params)
        if reasoning_body:
            kwargs["extra_body"] = reasoning_body

        response = self._client.chat.completions.create(**kwargs)

        # Defensive: handle None/empty responses from the API
        if not response or not response.choices:
            raise RuntimeError(
                "API returned an empty response (no choices). "
                "Check your API key, base URL, and model name. "
                f"Response: {response}"
            )

        choice = response.choices[0]
        message = choice.message

        # Parse tool calls
        tool_calls: list[ToolCall] = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    input=args,
                ))

        text = message.content or ""
        raw_content = self._build_raw_assistant(message)

        # Extract real token usage
        if response.usage:
            raw_content["_usage"] = {
                "input_tokens": response.usage.prompt_tokens or 0,
                "output_tokens": response.usage.completion_tokens or 0,
            }

        return raw_content, tool_calls, text

    def format_tools(self, tools: list[ToolDef]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.input_schema,
                },
            }
            for t in tools
        ]

    def format_tool_results(self, tool_calls: list[ToolCall], results: list[dict]) -> dict:
        """Format as OpenAI tool messages (one message per tool result)."""
        tool_messages = []
        for tc, result in zip(tool_calls, results):
            tool_messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": result.get("output", ""),
            })
        return {"_multi_messages": tool_messages}

    # ── Internal ─────────────────────────────────────────────────────

    @property
    def supports_streaming(self) -> bool:
        return True

    def call_stream(self, messages, system, tools, max_tokens=4096, abort_signal=None, params=None):
        """
        Streaming call that yields StreamChunks as they arrive.
        Checks abort_signal between chunks for fast cancellation.
        Returns the same tuple as call_sync when done.
        """
        api_messages = [{"role": "system", "content": system}]
        for msg in messages:
            converted = self._convert_message(msg)
            if isinstance(converted, list):
                api_messages.extend(converted)
            else:
                api_messages.append(converted)

        kwargs = {
            "model": self._model,
            "messages": api_messages,
            "max_tokens": max_tokens,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        # CC-aligned: inject reasoning for OpenRouter / compatible providers
        reasoning_body = self._build_reasoning_extra_body(params)
        if reasoning_body:
            kwargs["extra_body"] = reasoning_body

        stream = self._client.chat.completions.create(**kwargs)

        # Accumulate full response for return value
        text_parts = []
        tool_calls_acc: dict[int, dict] = {}  # index -> {id, name, args_str}

        try:
            for chunk in stream:
                # Check abort signal between every chunk — fast cancellation
                if abort_signal and abort_signal.aborted:
                    # Close the stream to release the connection
                    try:
                        stream.close()
                    except Exception:
                        pass
                    raise InterruptedError(f"Aborted: {abort_signal.reason}")

                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # Text content
                if delta.content:
                    text_parts.append(delta.content)
                    yield StreamChunk(type="text_delta", text=delta.content)

                # Tool call deltas
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_calls_acc:
                            tool_calls_acc[idx] = {"id": "", "name": "", "args": ""}

                        acc = tool_calls_acc[idx]
                        if tc_delta.id:
                            acc["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                acc["name"] = tc_delta.function.name
                                yield StreamChunk(
                                    type="tool_call_start",
                                    tool_call_id=acc["id"],
                                    tool_name=acc["name"],
                                )
                            if tc_delta.function.arguments:
                                acc["args"] += tc_delta.function.arguments
                                yield StreamChunk(
                                    type="tool_call_delta",
                                    tool_call_id=acc["id"],
                                    tool_arguments_delta=tc_delta.function.arguments,
                                )
        except InterruptedError:
            raise  # re-raise abort
        except Exception:
            pass  # stream may have been closed

        yield StreamChunk(type="done")

        # Build final return value
        full_text = "".join(text_parts)
        tool_calls = []
        for idx in sorted(tool_calls_acc.keys()):
            acc = tool_calls_acc[idx]
            try:
                args = json.loads(acc["args"])
            except (json.JSONDecodeError, TypeError):
                args = {}
            tool_calls.append(ToolCall(id=acc["id"], name=acc["name"], input=args))

        # Build raw content for conversation history
        raw = {"role": "assistant", "content": full_text}
        if tool_calls:
            raw["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.input)},
                }
                for tc in tool_calls
            ]

        return raw, tool_calls, full_text

    def _build_reasoning_extra_body(self, params: LLMCallParams | None) -> dict | None:
        """Build extra_body for reasoning (OpenRouter-compatible).
        Returns {"reasoning": {...}} when reasoning is enabled via settings
        or when effort/thinking is explicitly configured.

        Reasoning config:
        - reasoning_enabled=True (settings toggle) → {"reasoning": {"enabled": True}}
        - effort='low'/'medium'/'high' → adds {"effort": ...}
        - thinking={"budget_tokens": N} → adds {"max_tokens": N}
        """
        effort = getattr(params, "effort", None) if params else None
        thinking = getattr(params, "thinking", None) if params else None

        if not self._reasoning_enabled and not effort and not thinking:
            return None

        reasoning: dict = {"enabled": True}
        if effort in ("low", "medium", "high"):
            reasoning["effort"] = effort
        if isinstance(thinking, dict):
            budget = thinking.get("budget_tokens")
            if isinstance(budget, int) and budget > 0:
                reasoning["max_tokens"] = budget
        return {"reasoning": reasoning}

    @staticmethod
    def _build_raw_assistant(message) -> dict:
        """Build a storable assistant message from OpenAI response."""
        raw = {"role": "assistant", "content": message.content or ""}
        if message.tool_calls:
            raw["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]
        return raw

    def _convert_message(self, msg: dict) -> dict | list[dict]:
        """Convert internal message format to OpenAI API format."""
        role = msg.get("role", "user")
        content = msg.get("content")

        # Multi-message wrapper from format_tool_results
        if isinstance(msg, dict) and "_multi_messages" in msg:
            return msg["_multi_messages"]

        # OpenAI-native assistant with tool_calls
        if role == "assistant" and "tool_calls" in msg:
            return msg

        # OpenAI tool role
        if role == "tool":
            return msg

        # Simple string content
        if isinstance(content, str):
            return {"role": role, "content": content}

        # Nested message format — unwrap
        if isinstance(content, dict) and "role" in content:
            return {"role": content.get("role", role), "content": str(content.get("content", ""))}

        # Anthropic-style list of content blocks
        if isinstance(content, list) and content:
            first = content[0] if isinstance(content[0], dict) else None
            if not first:
                return {"role": role, "content": str(content)}

            block_type = first.get("type", "")

            # tool_result blocks → expand to individual tool messages
            if block_type == "tool_result":
                return [
                    {
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id", "unknown"),
                        "content": block.get("content", ""),
                    }
                    for block in content
                    if isinstance(block, dict) and block.get("type") == "tool_result"
                ]

            # text + tool_use blocks → assistant message with tool_calls
            text_parts = []
            tool_uses = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                bt = block.get("type", "")
                if bt == "text":
                    text_parts.append(block.get("text", ""))
                elif bt == "tool_use":
                    tool_uses.append({
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input", {})),
                        },
                    })

            result = {"role": role, "content": "\n".join(text_parts) if text_parts else ""}
            if tool_uses:
                result["tool_calls"] = tool_uses
            return result

        # Fallback
        return {"role": role, "content": str(content) if content else ""}
