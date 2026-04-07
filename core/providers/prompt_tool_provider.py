"""
Prompt-Based Tool Provider — for APIs that DON'T support function calling.

Works with any OpenAI-compatible chat API (e.g., Taiji/腾讯太极, older models).
Tool definitions are injected into the system prompt, and the model outputs
structured JSON blocks to invoke tools.

Protocol:
  - Tools described in system prompt
  - Model outputs <tool_call>{"name": "...", "arguments": {...}}</tool_call> to call tools
  - Tool results are sent back as user messages
  - Model outputs plain text for normal replies
"""

import json
import re
import uuid
from openai import OpenAI
from typing import Any

from core.providers.base import BaseProvider, ToolCall, ToolDef

# ── System prompt suffix: teaches the model how to use tools ─────────

TOOL_SYSTEM_SUFFIX = """

# Available Tools

You have access to the following tools to help the user. To use a tool, you MUST output a JSON block wrapped in <tool_call> tags:

<tool_call>
{{"name": "ToolName", "arguments": {{"param1": "value1"}}}}
</tool_call>

Rules:
1. When you need to perform an action (create files, run commands, search, etc.), you MUST use a tool — do NOT just describe what you would do.
2. You may include text before or after a <tool_call> block.
3. You can make multiple tool calls in one response — use one <tool_call> block per tool.
4. After each tool call, you will receive the tool's output. Then you can continue or call another tool.
5. When no tool is needed, just respond with normal text (no <tool_call> tags).

Available tools:

{tool_list}
"""

# Regex to extract <tool_call>...</tool_call> blocks
_TOOL_CALL_RE = re.compile(
    r'<tool_call>\s*(\{.*?\})\s*</tool_call>',
    re.DOTALL,
)


class PromptToolProvider(BaseProvider):
    """
    Provider for APIs without native function calling.
    Injects tool descriptions into the system prompt and parses
    <tool_call> JSON blocks from model output.
    """

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str | None = None,
    ):
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self._model = model
        self._tool_defs: list[ToolDef] = []

    def call_sync(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],  # ignored — we use self._tool_defs instead
        max_tokens: int = 4096,
        abort_signal=None,
        params=None,
    ) -> tuple[Any, list[ToolCall], str]:
        # Enhance system prompt with tool descriptions
        enhanced_system = system
        if self._tool_defs:
            enhanced_system += TOOL_SYSTEM_SUFFIX.format(
                tool_list=self._format_tool_list()
            )

        # Build messages
        api_messages = [{"role": "system", "content": enhanced_system}]
        for msg in messages:
            api_messages.append(self._simplify_message(msg))

        response = self._client.chat.completions.create(
            model=self._model,
            messages=api_messages,
            max_tokens=max_tokens,
        )

        # Defensive: handle None/empty responses from the API
        if not response or not response.choices:
            raise RuntimeError(
                "API returned an empty response (no choices). "
                "Check your API key, base URL, and model name. "
                f"Response: {response}"
            )

        full_text = response.choices[0].message.content or ""

        # Extract real token usage from API response
        usage = None
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens or 0,
                "output_tokens": response.usage.completion_tokens or 0,
            }

        # Parse tool calls from the text
        tool_calls = self._parse_tool_calls(full_text)

        # Strip <tool_call> blocks from display text
        display_text = _TOOL_CALL_RE.sub("", full_text).strip()

        raw_content = {"role": "assistant", "content": full_text}
        if usage:
            raw_content["_usage"] = usage
        return raw_content, tool_calls, display_text

    @property
    def supports_streaming(self) -> bool:
        return True

    def call_stream(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = 4096,
    ):
        """Real streaming: yield text deltas as they arrive from the API."""
        from core.providers.base import StreamChunk

        enhanced_system = system
        if self._tool_defs:
            enhanced_system += TOOL_SYSTEM_SUFFIX.format(
                tool_list=self._format_tool_list()
            )

        api_messages = [{"role": "system", "content": enhanced_system}]
        for msg in messages:
            api_messages.append(self._simplify_message(msg))

        stream = self._client.chat.completions.create(
            model=self._model,
            messages=api_messages,
            max_tokens=max_tokens,
            stream=True,
        )

        full_text = ""
        usage = None
        for chunk in stream:
            # Capture usage from chunks — only keep non-zero values
            if hasattr(chunk, 'usage') and chunk.usage:
                u = chunk.usage
                if (u.prompt_tokens and u.prompt_tokens > 0) or \
                   (u.completion_tokens and u.completion_tokens > 0):
                    usage = {
                        "input_tokens": u.prompt_tokens or 0,
                        "output_tokens": u.completion_tokens or 0,
                    }
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta and delta.content:
                full_text += delta.content
                yield StreamChunk(type="text_delta", text=delta.content)

        yield StreamChunk(type="done")

        # Parse tool calls from the accumulated text
        tool_calls = self._parse_tool_calls(full_text)
        display_text = _TOOL_CALL_RE.sub("", full_text).strip()
        raw_content = {"role": "assistant", "content": full_text}
        if usage:
            raw_content["_usage"] = usage
        return raw_content, tool_calls, display_text

    def format_tools(self, tools: list[ToolDef]) -> list[dict]:
        """Cache tool defs for prompt injection. Return empty (no native tools)."""
        self._tool_defs = tools
        return []  # no native tool format needed

    def format_tool_results(self, tool_calls: list[ToolCall], results: list[dict]) -> dict:
        """Format tool results as a readable user message."""
        parts = []
        for tc, result in zip(tool_calls, results):
            output = result.get("output", "")
            is_error = result.get("is_error", False)
            status = "ERROR" if is_error else "OK"
            parts.append(
                f"[Tool Result: {tc.name}] ({status})\n"
                f"```\n{output}\n```"
            )
        return {"role": "user", "content": "\n\n".join(parts)}

    # ── Internal ─────────────────────────────────────────────────────

    def _format_tool_list(self) -> str:
        """Build a human-readable tool list for the system prompt."""
        lines = []
        for t in self._tool_defs:
            props = t.input_schema.get("properties", {})
            required = set(t.input_schema.get("required", []))
            param_parts = []
            for pname, pinfo in props.items():
                req = " (required)" if pname in required else ""
                desc = pinfo.get("description", "")
                param_parts.append(f"      - {pname}: {desc}{req}")
            params_str = "\n".join(param_parts) if param_parts else "      (no parameters)"
            lines.append(
                f"  ## {t.name}\n"
                f"  {t.description}\n"
                f"    Parameters:\n{params_str}\n"
            )
        return "\n".join(lines)

    def _parse_tool_calls(self, text: str) -> list[ToolCall]:
        """Extract tool calls from <tool_call> blocks in model output."""
        valid_names = {t.name for t in self._tool_defs}
        tool_calls = []

        for match in _TOOL_CALL_RE.finditer(text):
            try:
                data = json.loads(match.group(1))
                name = data.get("name", "")
                arguments = data.get("arguments", {})
                if name not in valid_names:
                    continue
                tool_calls.append(ToolCall(
                    id=f"pt_{uuid.uuid4().hex[:12]}",
                    name=name,
                    input=arguments,
                ))
            except (json.JSONDecodeError, KeyError, TypeError):
                continue

        return tool_calls

    @staticmethod
    def _simplify_message(msg: dict) -> dict:
        """Convert any message format to simple {role, content} for the API."""
        role = msg.get("role", "user")
        content = msg.get("content", "")

        # Already simple string
        if isinstance(content, str):
            return {"role": role, "content": content}

        # Nested message (old bug format)
        if isinstance(content, dict) and "content" in content:
            return {"role": role, "content": str(content["content"])}

        # Anthropic-style content blocks
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        parts.append(f"[Tool Result]: {block.get('content', '')}")
            return {"role": role, "content": "\n".join(parts) if parts else str(content)}

        return {"role": role, "content": str(content) if content else ""}
