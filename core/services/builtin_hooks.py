"""
Built-in hooks — registered automatically when HookRegistry is initialized.

destructive_guard: Blocks destructive tool calls unless AskUser was called
in the current query turn. Forces the model to confirm with the user before
performing irreversible actions.
"""

import re
from core.services.hooks import HookResult


# ── Destructive command patterns for Bash/PowerShell ────────────────────
# These regex patterns detect deletion/destructive shell commands.
_DESTRUCTIVE_CMD_PATTERNS = [
    r"\brm\s+(-[a-zA-Z]*\s+)*",          # rm, rm -rf, rm -f
    r"\brmdir\b",                          # rmdir
    r"\bdel\s+",                           # Windows del
    r"\brd\s+",                            # Windows rd
    r"\bgit\s+push\s+.*--force",           # git push --force
    r"\bgit\s+reset\s+--hard",             # git reset --hard
    r"\bgit\s+clean\s+-[a-zA-Z]*f",        # git clean -f/-fd
    r"\bgit\s+branch\s+-[dD]",             # git branch -d/-D
    r"\bgit\s+checkout\s+--\s",            # git checkout -- (discard changes)
    r"\bgit\s+restore\s+--staged\s+\.",    # git restore --staged .
    r"\bdrop\s+table\b",                   # SQL DROP TABLE
    r"\bdrop\s+database\b",                # SQL DROP DATABASE
    r"\btruncate\s+table\b",              # SQL TRUNCATE
    r"\bformat\b",                         # format drive
    r"\bmkfs\b",                           # make filesystem (destructive)
    r"\bsudo\s+rm\b",                      # sudo rm
]

_DESTRUCTIVE_RE = re.compile(
    "|".join(f"({p})" for p in _DESTRUCTIVE_CMD_PATTERNS),
    re.IGNORECASE,
)

# Tools that are inherently destructive (beyond bash commands)
_DESTRUCTIVE_TOOL_NAMES = {
    # FileWrite is only destructive when overwriting, but read-before-write
    # already guards that. We focus on truly irreversible operations.
}


def _is_destructive_bash(tool_name: str, tool_input: dict) -> bool:
    """Check if a Bash/PowerShell call contains destructive commands."""
    if tool_name not in ("Bash", "PowerShell"):
        return False
    command = tool_input.get("command", "")
    return bool(_DESTRUCTIVE_RE.search(command))


def destructive_guard(context: dict) -> HookResult:
    """
    pre_tool_use hook: block destructive operations unless AskUser was
    already called in this query turn.

    The hook receives:
      - tool: tool name
      - input: tool input dict
      - round: current round number
      - ask_user_called_this_turn: bool (injected by engine)
    """
    tool_name = context.get("tool", "")
    tool_input = context.get("input", {})
    ask_user_called = context.get("ask_user_called_this_turn", False)

    # Check if this is a destructive operation
    is_destructive = (
        tool_name in _DESTRUCTIVE_TOOL_NAMES
        or _is_destructive_bash(tool_name, tool_input)
    )

    if not is_destructive:
        return HookResult(success=True)

    # If AskUser was already called this turn, allow it
    if ask_user_called:
        return HookResult(success=True)

    # Block and instruct the model to ask the user first
    command_preview = ""
    if tool_name in ("Bash", "PowerShell"):
        cmd = tool_input.get("command", "")
        command_preview = f"\nCommand: {cmd[:100]}"

    return HookResult(
        success=True,
        block=True,
        output=(
            f"BLOCKED: {tool_name} contains a destructive/irreversible operation.{command_preview}\n"
            f"You MUST use AskUser first to confirm with the user before executing "
            f"destructive commands (rm, delete, force-push, reset --hard, DROP TABLE, etc.).\n"
            f"Call AskUser with a clear explanation of what will be deleted/destroyed, "
            f"then retry this tool call after receiving confirmation."
        ),
    )
