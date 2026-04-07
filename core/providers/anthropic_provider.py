"""
Anthropic Provider — native Anthropic SDK integration.
v5: CC source-verified implementation:
  - Extended Thinking: adaptive (no budget) vs enabled (with budget)
  - Effort level: output_config.effort + betas array
  - Prompt caching: per-system-block cache_control + last message (user OR assistant)
  - Structured output: output_config.format + beta header (Anthropic format)
  - Cache token tracking (cache_read + cache_creation)
  - Stop reason forwarding
  - Session ID: embedded in metadata (not custom header)
  - Temperature conditional on thinking mode
  - Request ID: analytics/logging only (not sent as header)
"""

import os
import json
from typing import Any

import anthropic

from core.providers.base import BaseProvider, ToolCall, ToolDef, LLMCallParams


# ── Model capability detection (CC: thinking.ts) ────────────────
# Models that support thinking at all
_THINKING_CAPABLE_MODELS = {
    "claude-sonnet-4-20250514", "claude-opus-4-20250514",
    "claude-sonnet-4", "claude-opus-4",
    # 4.6 series (adaptive thinking)
    "claude-sonnet-4-6", "claude-opus-4-6",
    "claude-sonnet-4.6", "claude-opus-4.6",
}

# Models that support ADAPTIVE thinking (type: "adaptive", no budget_tokens)
# CC: modelSupportsAdaptiveThinking() — opus-4-6, sonnet-4-6
_ADAPTIVE_THINKING_MODELS = {
    "claude-sonnet-4-6", "claude-opus-4-6",
    "claude-sonnet-4.6", "claude-opus-4.6",
}

# CC: structured outputs beta header (betas.ts L8)
_STRUCTURED_OUTPUTS_BETA_HEADER = "structured-outputs-2025-12-15"

# CC: effort level beta header (betas.ts L15)
_EFFORT_BETA_HEADER = "effort-2025-11-24"


def _model_supports_thinking(model: str) -> bool:
    """CC: modelSupportsThinking() — check if model supports any thinking."""
    canonical = model.lower()
    for m in _THINKING_CAPABLE_MODELS:
        if m in canonical or canonical in m:
            return True
    return False


def _model_supports_adaptive(model: str) -> bool:
    """CC: modelSupportsAdaptiveThinking() — check if model supports adaptive mode."""
    canonical = model.lower()
    for m in _ADAPTIVE_THINKING_MODELS:
        if m in canonical or canonical in m:
            return True
    return False


class AnthropicProvider(BaseProvider):
    """Anthropic Claude provider using the native SDK."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    def call_sync(
        self,
        messages: list[dict],
        system: str,
        tools: list[dict],
        max_tokens: int = 4096,
        abort_signal=None,
        params: LLMCallParams | None = None,
    ) -> tuple[Any, list[ToolCall], str]:
        params = params or LLMCallParams()

        # ── Build kwargs ──────────────────────────────────────────
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        # ── System prompt with optional cache_control ─────────────
        # CC-aligned: when caching, each system block gets its own cache_control
        if params.cache_control:
            # CC: buildSystemPromptBlocks — each block gets cache_control independently
            kwargs["system"] = [{
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }]
        else:
            kwargs["system"] = system

        # ── Tools ─────────────────────────────────────────────────
        if tools:
            kwargs["tools"] = tools

        # ── Extended Thinking (CC: claude.ts lines 1596-1630) ─────
        # CC has two modes:
        #   adaptive: {"type": "adaptive"} — no budget_tokens, model decides
        #   enabled: {"type": "enabled", "budget_tokens": N} — clamped
        has_thinking = False
        if params.thinking:
            disable_thinking = os.environ.get("CLAUDE_CODE_DISABLE_THINKING", "").lower() in ("1", "true")
            disable_adaptive = os.environ.get("CLAUDE_CODE_DISABLE_ADAPTIVE_THINKING", "").lower() in ("1", "true")

            if not disable_thinking and _model_supports_thinking(self._model):
                has_thinking = True
                if not disable_adaptive and _model_supports_adaptive(self._model):
                    # CC: adaptive thinking — no budget_tokens
                    kwargs["thinking"] = {"type": "adaptive"}
                else:
                    # CC: budget-limited thinking
                    budget = params.thinking.get("budget_tokens", 10000) if isinstance(params.thinking, dict) else 10000
                    # CC: clamp to min(maxOutputTokens - 1, budget)
                    budget = min(max_tokens - 1, budget)
                    kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}

        # ── Temperature (CC: claude.ts 1691-1695) ─────────────────
        # CC: only send temperature when thinking is DISABLED
        if not has_thinking:
            if params.temperature is not None:
                kwargs["temperature"] = params.temperature

        # ── Effort level (CC: claude.ts 440-466) ──────────────────
        # CC: effort goes in output_config + betas array
        # CC: outputConfig = {}; outputConfig.effort = effortValue; kwargs.output_config = outputConfig
        betas: list[str] = []
        output_config: dict[str, Any] = {}
        if params.effort:
            betas.append(_EFFORT_BETA_HEADER)
            output_config["effort"] = params.effort  # CC: outputConfig.effort = effortValue

        # ── Structured output (CC: claude.ts 1579-1588) ───────────
        # CC: outputConfig.format = outputFormat; betas.push(STRUCTURED_OUTPUTS_BETA_HEADER)
        if params.output_schema:
            betas.append(_STRUCTURED_OUTPUTS_BETA_HEADER)
            output_config["format"] = params.output_schema  # CC: outputConfig.format

        # Apply output_config if any fields set
        if output_config:
            kwargs["output_config"] = output_config

        # ── Apply betas as extra headers ──────────────────────────
        extra_headers = {}
        if betas:
            extra_headers["anthropic-beta"] = ",".join(betas)

        # ── Session ID (CC: embedded in user_id JSON, NOT a custom header) ──
        # CC packs {device_id, account_uuid, session_id} into user_id field
        # For BUDDY, we pass it as metadata since we don't have OAuth device_id
        if params.session_id:
            kwargs.setdefault("metadata", {})
            kwargs["metadata"]["user_id"] = json.dumps({"session_id": params.session_id})

        # ── Request ID: CC uses this for analytics/logging ONLY ───
        # CC does NOT send previousRequestId as an HTTP header
        # We store it for logging but don't send it to API
        # (params.request_id is read by engine for analytics)

        if extra_headers:
            kwargs["extra_headers"] = extra_headers

        # ── Stop sequences ────────────────────────────────────────
        if params.stop_sequences:
            kwargs["stop_sequences"] = params.stop_sequences

        # ── Prompt caching on last message (user OR assistant) ────
        # CC: addCacheBreakpoints — adds cache_control to the LAST message
        # (not just last user message — can be assistant too)
        # CC also excludes thinking/redacted_thinking blocks from cache_control
        if params.cache_control and messages:
            messages = self._inject_cache_control(messages)
            kwargs["messages"] = messages

        # ── API Call ──────────────────────────────────────────────
        response = self._client.messages.create(**kwargs)

        # Defensive: handle None/empty responses from the API
        if not response or not response.content:
            raise RuntimeError(
                "API returned an empty response (no content). "
                "Check your API key and model name. "
                f"Response: {response}"
            )

        # ── Parse response ────────────────────────────────────────
        tool_calls: list[ToolCall] = []
        text_parts: list[str] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "thinking":
                # Extended thinking content — not shown to user but tracked
                pass
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    input=block.input,
                ))

        # Raw content for message history (serialize to dicts)
        raw_content = []
        for block in response.content:
            if block.type == "text":
                raw_content.append({"type": "text", "text": block.text})
            elif block.type == "thinking":
                raw_content.append({"type": "thinking", "thinking": block.thinking})
            elif block.type == "tool_use":
                raw_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        # ── Usage tracking (CC-aligned: include cache tokens) ─────
        usage_data = {}
        if hasattr(response, "usage") and response.usage:
            usage_data = {
                "input_tokens": getattr(response.usage, "input_tokens", 0),
                "output_tokens": getattr(response.usage, "output_tokens", 0),
                "cache_creation_input_tokens": getattr(response.usage, "cache_creation_input_tokens", 0),
                "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
            }

        # ── Stop reason ──────────────────────────────────────────
        stop_reason = getattr(response, "stop_reason", "end_turn") or "end_turn"

        # ── Request ID (for engine analytics/logging, NOT sent to API) ──
        request_id = getattr(response, "id", None) or ""

        # Attach metadata to raw_content for engine consumption
        if isinstance(raw_content, list):
            raw_content = {
                "role": "assistant",
                "content": raw_content,
                "_usage": usage_data,
                "_stop_reason": stop_reason,
                "_request_id": request_id,
            }

        return raw_content, tool_calls, "\n".join(text_parts)

    def _inject_cache_control(self, messages: list[dict]) -> list[dict]:
        """
        CC-aligned: add cache_control to the LAST message's last content block.
        CC: addCacheBreakpoints — targets the last message (user OR assistant),
        not just the last user message.
        Excludes thinking/redacted_thinking blocks from getting cache_control.
        """
        if not messages:
            return messages

        # Deep copy to avoid mutating original
        messages = [dict(m) for m in messages]

        # Find the last message (user OR assistant — CC doesn't restrict to user)
        last_idx = len(messages) - 1
        msg = messages[last_idx]
        content = msg.get("content")

        if isinstance(content, str):
            messages[last_idx]["content"] = [{
                "type": "text",
                "text": content,
                "cache_control": {"type": "ephemeral"},
            }]
        elif isinstance(content, list) and content:
            # CC: skip thinking/redacted_thinking blocks — find last eligible block
            eligible_idx = None
            for j in range(len(content) - 1, -1, -1):
                block = content[j]
                if isinstance(block, dict):
                    btype = block.get("type", "")
                    if btype not in ("thinking", "redacted_thinking", "connector_text"):
                        eligible_idx = j
                        break
            if eligible_idx is not None:
                new_content = list(content)
                last_block = dict(new_content[eligible_idx])
                last_block["cache_control"] = {"type": "ephemeral"}
                new_content[eligible_idx] = last_block
                messages[last_idx]["content"] = new_content

        return messages

    def format_tools(self, tools: list[ToolDef]) -> list[dict]:
        return [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
            }
            for t in tools
        ]

    def format_tool_results(self, tool_calls: list[ToolCall], results: list[dict]) -> dict:
        """Format as Anthropic tool_result content blocks."""
        content = []
        for tc, result in zip(tool_calls, results):
            content.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": result.get("output", ""),
                **({"is_error": True} if result.get("is_error") else {}),
            })
        return {"role": "user", "content": content}
