"""
Tool Use Summary — CC-aligned post-tool-round summarizer.
CC: toolUseSummaryGenerator.ts — calls Haiku after multi-tool rounds
to generate a git-commit-style ≤30-char label.

Non-blocking, fire-and-forget. Failures silently swallowed.
"""

import threading
import json
from typing import Callable, Any


# CC: system prompt for tool use summary generation
_SUMMARY_SYSTEM_PROMPT = """You are a concise labeler. Given a list of tool calls (name, input, output), generate a SINGLE git-commit-style label of at most 30 characters.

Rules:
- Past tense ("Searched", "Fixed", "Created", "Read", "Ran")
- Drop articles and connectors ("a", "the", "and")
- Focus on the most distinctive noun/action
- No quotes, no punctuation at end

Examples:
- "Searched in auth/"
- "Fixed NPE in UserService"
- "Created signup endpoint"
- "Read config.json"
- "Ran failing tests"
- "Updated 3 files"

Reply with ONLY the label, nothing else."""


def generate_tool_summary(
    tool_infos: list[dict],
    provider_call_fn: Callable | None,
    last_assistant_text: str = "",
) -> str | None:
    """
    Generate a tool use summary label.
    tool_infos: list of {"name": str, "input": str, "output": str}
    Returns label string or None on failure.
    """
    if not provider_call_fn or not tool_infos:
        return None

    try:
        # Build user content: tool names + truncated inputs/outputs (300 chars)
        parts = []
        for info in tool_infos:
            name = info.get("name", "unknown")
            inp = _truncate(json.dumps(info.get("input", {}), ensure_ascii=False), 300)
            out = _truncate(str(info.get("output", "")), 300)
            parts.append(f"Tool: {name}\nInput: {inp}\nOutput: {out}")

        user_content = "\n---\n".join(parts)
        if last_assistant_text:
            user_content += f"\n\nContext (assistant's last text): {last_assistant_text[:200]}"

        _, _, summary = provider_call_fn(
            messages=[{"role": "user", "content": user_content}],
            system=_SUMMARY_SYSTEM_PROMPT,
            tools=[],
        )
        if summary and len(summary.strip()) <= 60:
            return summary.strip()
        return None
    except Exception:
        return None  # CC: failures never block


def generate_tool_summary_async(
    tool_infos: list[dict],
    provider_call_fn: Callable | None,
    callback: Callable[[str | None], None] | None = None,
    last_assistant_text: str = "",
):
    """
    CC-aligned: fire-and-forget async summary generation.
    Spawns a background thread. Optional callback with result.
    """
    def _run():
        result = generate_tool_summary(tool_infos, provider_call_fn, last_assistant_text)
        if callback and result:
            try:
                callback(result)
            except Exception:
                pass

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[:max_len - 3] + "..."
