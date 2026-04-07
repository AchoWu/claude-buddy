"""
Tool Pool — CC-aligned dynamic tool assembly with deny-rule filtering.
CC: assembleToolPool() filters tools based on context, permissions, deny rules.
"""

from typing import Any
from core.providers.base import ToolDef


class ToolPool:
    """Dynamic tool pool with deny-rule filtering."""

    def __init__(self):
        self._all_tools: list[ToolDef] = []
        self._all_executors: dict[str, Any] = {}
        self._deny_rules: set[str] = set()  # tool names to deny
        self._context_filter: set[str] | None = None  # if set, only these tools allowed

    def set_tools(self, tools: list[ToolDef], executors: dict[str, Any]):
        """Set the full tool catalog."""
        self._all_tools = list(tools)
        self._all_executors = dict(executors)

    def add_deny_rule(self, tool_name: str):
        """CC: deny-rule — prevent a tool from being used."""
        self._deny_rules.add(tool_name)

    def remove_deny_rule(self, tool_name: str):
        self._deny_rules.discard(tool_name)

    def set_context_filter(self, allowed_tools: set[str] | None):
        """Restrict to only these tools (None = all allowed)."""
        self._context_filter = allowed_tools

    def assemble(self) -> tuple[list[ToolDef], dict[str, Any]]:
        """
        CC: assembleToolPool() — return filtered (tools, executors).
        Applies deny rules and context filter.
        """
        filtered_tools = []
        filtered_executors = {}
        for t in self._all_tools:
            # Skip denied tools
            if t.name in self._deny_rules:
                continue
            # Skip tools not in context filter (if set)
            if self._context_filter is not None and t.name not in self._context_filter:
                continue
            filtered_tools.append(t)
            if t.name in self._all_executors:
                filtered_executors[t.name] = self._all_executors[t.name]
        return filtered_tools, filtered_executors

    @property
    def denied_tools(self) -> set[str]:
        return set(self._deny_rules)

    def format_status(self) -> str:
        total = len(self._all_tools)
        denied = len(self._deny_rules)
        active = total - denied
        if self._context_filter:
            active = min(active, len(self._context_filter))
        lines = [f"Tool Pool: {active}/{total} active"]
        if self._deny_rules:
            lines.append(f"  Denied: {', '.join(sorted(self._deny_rules))}")
        if self._context_filter:
            lines.append(f"  Context filter: {len(self._context_filter)} tools allowed")
        return "\n".join(lines)
