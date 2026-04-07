"""
CtxInspectTool — CC-aligned context window inspection.
CC: feature-gated behind CONTEXT_COLLAPSE.
Reports token usage breakdown and context window stats.
"""

from tools.base import BaseTool


class CtxInspectTool(BaseTool):
    name = "CtxInspect"
    description = (
        "Inspect the current context window: message count, token estimates, "
        "system prompt size, tool count, and compression stats. "
        "Useful for understanding token budget and optimizing context."
    )
    input_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }
    is_read_only = True
    concurrency_safe = True

    _engine = None  # injected by tool_registry

    def execute(self, input_data: dict) -> str:
        if not self._engine:
            return "Error: Engine not available."

        eng = self._engine
        conv = eng._conversation if hasattr(eng, '_conversation') else None
        if not conv:
            return "No conversation context available."

        lines = ["## Context Window Inspection"]

        # Message stats
        msgs = conv.messages
        lines.append(f"\nMessages: {len(msgs)}")
        role_counts = {}
        for m in msgs:
            role = m.get("role", "unknown")
            role_counts[role] = role_counts.get(role, 0) + 1
        for role, count in sorted(role_counts.items()):
            lines.append(f"  {role}: {count}")

        # Token estimate
        est_tokens = conv.estimated_tokens
        ctx_window = getattr(eng, '_context_window', 32000)
        pct = (est_tokens / ctx_window * 100) if ctx_window > 0 else 0
        lines.append(f"\nToken Estimate: ~{est_tokens:,} / {ctx_window:,} ({pct:.1f}%)")

        # Tool count
        tool_count = len(eng._tools) if hasattr(eng, '_tools') else 0
        lines.append(f"Tools Registered: {tool_count}")

        # Compaction stats
        lines.append(f"Compaction Count: {conv._compaction_count}")
        lines.append(f"Compact Boundary: {conv._compact_boundary}")
        lines.append(f"Compact Failures: {conv._consecutive_compact_failures}")

        # Cost summary
        cost = eng.session_cost if hasattr(eng, '_session_cost') else None
        if cost:
            lines.append(f"\nAPI Calls: {cost.total_api_calls}")
            lines.append(f"Total Input Tokens: {cost.total_input_tokens:,}")
            lines.append(f"Total Output Tokens: {cost.total_output_tokens:,}")

        return "\n".join(lines)
