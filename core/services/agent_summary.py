"""
Agent Summary — CC-aligned sub-agent completion summary.
CC: generates summary when sub-agents complete, improving parent context.
Reuses tool_summary logic.
"""

from core.tool_summary import generate_tool_summary


def generate_agent_summary(
    agent_id: str,
    agent_result: str,
    provider_call_fn=None,
) -> str | None:
    """
    Generate a one-line summary of what a sub-agent accomplished.
    Returns summary string or None.
    """
    if not provider_call_fn or not agent_result:
        return None

    try:
        _, _, summary = provider_call_fn(
            messages=[{"role": "user", "content": (
                f"Summarize what agent '{agent_id}' accomplished in one sentence (max 60 chars):\n\n"
                f"{agent_result[:1000]}"
            )}],
            system="Reply with ONLY a one-sentence summary, nothing else.",
            tools=[],
        )
        if summary and len(summary.strip()) <= 100:
            return summary.strip()
    except Exception:
        pass
    # Fallback: first line of result
    first_line = agent_result.strip().split("\n")[0][:80]
    return first_line or None
