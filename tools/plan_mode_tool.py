"""
Plan Mode Tools — EnterPlanModeTool and ExitPlanModeTool.

Modeled after Claude Code's plan mode.  When plan mode is active the engine
should restrict tool execution to read-only tools only, allowing the model to
investigate and plan without making any changes to the filesystem or running
destructive commands.

Both tools share a ``PlanModeState`` object that is injected by the
ToolRegistry (or engine bootstrap).  The engine checks
``plan_mode_state.active`` before dispatching tool calls.
"""

from __future__ import annotations

from typing import Optional

from tools.base import BaseTool


class PlanModeState:
    """Shared mutable flag that tracks whether plan mode is active.

    Create one instance and inject it into both EnterPlanModeTool and
    ExitPlanModeTool (and into the engine so it can gate tool execution).

    Usage::

        state = PlanModeState()
        enter_tool._plan_mode_state = state
        exit_tool._plan_mode_state = state
        engine.plan_mode_state = state      # engine checks state.active
    """

    def __init__(self) -> None:
        self.active: bool = False
        self._on_change: list = []  # callbacks: fn(active: bool)

    def on_change(self, callback) -> None:
        """Register a callback to be notified when plan mode toggles."""
        self._on_change.append(callback)

    def enter(self) -> str:
        """Activate plan mode.  Returns a confirmation message."""
        if self.active:
            return "Plan mode is already active."
        self.active = True
        for cb in self._on_change:
            cb(True)
        return (
            "Plan mode activated. Only read-only tools are now available. "
            "You may investigate, search, and read files, but you cannot "
            "write, edit, or execute destructive commands until you exit "
            "plan mode."
        )

    def exit(self) -> str:
        """Deactivate plan mode.  Returns a confirmation message."""
        if not self.active:
            return "Plan mode is not active — nothing to exit."
        self.active = False
        for cb in self._on_change:
            cb(False)
        return (
            "Plan mode deactivated. All tools are now available again, "
            "including write and edit operations."
        )


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #


class EnterPlanModeTool(BaseTool):
    """Signal the engine to enter plan mode (read-only tools only).

    While plan mode is active the engine MUST reject any tool call where
    ``tool.is_read_only`` is ``False``.  This lets the model safely explore
    the codebase and form a plan before committing to changes.
    """

    name = "EnterPlanMode"
    description = (
        "Enter plan mode.\n\n"
        "While in plan mode only read-only tools (file reads, glob, grep, "
        "task list, web search, etc.) are available.  Write, edit, bash, and "
        "other mutating tools are blocked until you call ExitPlanMode.\n\n"
        "Use this when you want to investigate a problem, gather context, and "
        "form a plan before making any changes."
    )
    input_schema = {
        "type": "object",
        "properties": {},
    }
    is_read_only = True

    # Injected by ToolRegistry — shared with ExitPlanModeTool.
    _plan_mode_state: Optional[PlanModeState] = None

    def execute(self, input_data: dict) -> str:
        if self._plan_mode_state is None:
            return (
                "Error: PlanModeState not connected. "
                "The engine must inject a PlanModeState instance as "
                "`_plan_mode_state` before use."
            )
        return self._plan_mode_state.enter()


class ExitPlanModeTool(BaseTool):
    """Signal the engine to exit plan mode, re-enabling all tools."""

    name = "ExitPlanMode"
    description = (
        "Exit plan mode and restore full tool access.\n\n"
        "Call this after you have finished investigating and are ready to "
        "make changes.  All tools (including write, edit, and bash) become "
        "available again."
    )
    input_schema = {
        "type": "object",
        "properties": {},
    }
    is_read_only = True

    # Injected by ToolRegistry — shared with EnterPlanModeTool.
    _plan_mode_state: Optional[PlanModeState] = None

    def execute(self, input_data: dict) -> str:
        if self._plan_mode_state is None:
            return (
                "Error: PlanModeState not connected. "
                "The engine must inject a PlanModeState instance as "
                "`_plan_mode_state` before use."
            )
        return self._plan_mode_state.exit()
