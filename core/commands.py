"""
Command System v2 — 30 slash commands for the chat UI.
Aligned with Claude Code's commands.ts registry (~75 commands).

Commands are triggered by /name in the chat input.
Each command is a simple function that returns a result string.
Commands bypass the LLM — they execute directly.

Categories:
  Core:     /help /clear /exit /version
  Session:  /resume /session /diff /files /context
  Config:   /config /permissions /hooks /theme
  Mode:     /plan /fast /effort
  Cost:     /cost /status /model
  Memory:   /memory /compact
  Tasks:    /tasks
  Code:     /review /pr
  Tools:    /tools /plugins /skills
  Diag:     /doctor
"""

from __future__ import annotations
import os
import time
import platform
import subprocess
from typing import Callable, Any
from pathlib import Path


class Command:
    """A registered slash command."""
    def __init__(self, name: str, description: str, handler: Callable,
                 aliases: list[str] | None = None, category: str = ""):
        self.name = name
        self.description = description
        self.handler = handler
        self.aliases = aliases or []
        self.category = category


class CommandRegistry:
    """
    Central registry for slash commands.
    Commands are dispatched from the chat UI before messages reach the LLM.
    """

    def __init__(self):
        self._commands: dict[str, Command] = {}
        self._register_builtins()

    def register(self, name: str, description: str, handler: Callable,
                 aliases: list[str] | None = None, category: str = ""):
        cmd = Command(name, description, handler, aliases or [], category)
        self._commands[name] = cmd
        for alias in cmd.aliases:
            self._commands[alias] = cmd

    def get(self, name: str) -> Command | None:
        return self._commands.get(name.lstrip("/").lower())

    def is_command(self, text: str) -> bool:
        if not text.startswith("/"):
            return False
        parts = text.split(maxsplit=1)
        return parts[0].lstrip("/").lower() in self._commands

    def execute(self, text: str, context: dict | None = None) -> str | None:
        if not text.startswith("/"):
            return None
        parts = text.split(maxsplit=1)
        cmd_name = parts[0].lstrip("/").lower()
        args = parts[1] if len(parts) > 1 else ""

        cmd = self._commands.get(cmd_name)
        if not cmd:
            return f"Unknown command: /{cmd_name}. Type /help for available commands."

        try:
            return cmd.handler(args, context or {})
        except Exception as e:
            return f"Command error: {e}"

    def list_commands(self) -> list[tuple[str, str]]:
        seen = set()
        result = []
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                result.append((f"/{cmd.name}", cmd.description))
        return sorted(result)

    def list_commands_by_category(self) -> dict[str, list[tuple[str, str]]]:
        seen = set()
        cats: dict[str, list] = {}
        for cmd in self._commands.values():
            if cmd.name not in seen:
                seen.add(cmd.name)
                cat = cmd.category or "Other"
                cats.setdefault(cat, []).append((f"/{cmd.name}", cmd.description))
        return {k: sorted(v) for k, v in cats.items()}

    # ── Built-in Commands ─────────────────────────────────────────

    def _register_builtins(self):
        R = self.register
        # Core
        R("help", "Show available commands", _cmd_help, category="Core")
        R("clear", "Clear conversation history", _cmd_clear, ["reset"], "Core")
        R("exit", "Exit the application", _cmd_exit, ["quit"], "Core")
        R("version", "Show version info", _cmd_version, category="Core")

        # Session
        R("resume", "Resume the last conversation", _cmd_resume, category="Session")
        R("session", "Show session info", _cmd_session, category="Session")
        R("diff", "Show files changed in this session", _cmd_diff, category="Session")
        R("files", "List files read/written in this session", _cmd_files, category="Session")
        R("context", "Show current context (git, project, CWD)", _cmd_context, category="Session")

        # Config
        R("config", "View/set configuration", _cmd_config, category="Config")
        R("permissions", "Show or reset permissions", _cmd_permissions, ["perms"], "Config")
        R("hooks", "List registered hooks", _cmd_hooks, category="Config")
        R("theme", "Switch theme (dark/light)", _cmd_theme, category="Config")

        # Mode
        R("plan", "Enter/exit plan mode", _cmd_plan, category="Mode")
        R("fast", "Toggle fast mode (concise output)", _cmd_fast, category="Mode")
        R("effort", "Set reasoning effort (high/medium/low)", _cmd_effort, category="Mode")

        # Cost & Status
        R("cost", "Show session cost summary", _cmd_cost, category="Status")
        R("status", "Show engine status", _cmd_status, category="Status")
        R("model", "Show or switch current model", _cmd_model, category="Status")
        R("stats", "Show usage statistics", _cmd_stats, category="Status")
        R("flags", "Show or set feature flags", _cmd_flags, category="Status")

        # Memory & Compaction
        R("memory", "Show or manage memory", _cmd_memory, ["mem"], "Memory")
        R("compact", "Force conversation compaction", _cmd_compact, category="Memory")

        # Tasks (CC: /tasks shows background tasks dialog, NOT the task list)
        R("tasks", "Show background tasks", _cmd_bg_tasks, category="Tasks")

        # Code Review
        R("review", "Review current git diff", _cmd_review, category="Code")
        R("pr", "Create a pull request", _cmd_pr, category="Code")
        R("branch", "Git branch management", _cmd_branch, category="Code")

        # Tool Discovery
        R("tools", "List all available tools", _cmd_tools, category="Tools")

        # Output
        R("output-style", "Set output style (concise/detailed/default)", _cmd_output_style, category="Config")
        R("plugins", "List loaded plugins", _cmd_plugins, category="Tools")
        R("skills", "List available skills", _cmd_skills, category="Tools")

        # Diagnostics
        R("doctor", "Run system diagnostics", _cmd_doctor, category="Diagnostics")

        # Data
        R("export", "Export conversation to file", _cmd_export, category="Data")
        R("import", "Import conversation from file", _cmd_import, ["load"], "Data")

        # Agent Management
        R("agents", "List active agents", _cmd_agents, category="Agents")

        # Environment
        R("env", "Show/set environment variables", _cmd_env, category="Config")

        # Utility
        R("copy", "Copy last reply to clipboard", _cmd_copy, category="Utility")
        R("onboarding", "First-time setup guide", _cmd_onboarding, category="Utility")

        # Soul & Evolution
        R("soul", "Show BUDDY's soul status", _cmd_soul, category="Soul")
        R("diary", "Show BUDDY's diary", _cmd_diary, category="Soul")
        R("evolve", "Show evolution changelog", _cmd_evolve, category="Soul")
        R("rollback", "Rollback a file to previous version", _cmd_rollback, category="Soul")

        # Phase 6: CC-aligned new commands
        R("init", "Initialize project (generate CLAUDE.md)", _cmd_init, category="Core")
        R("add-dir", "Add directory to context", _cmd_add_dir, category="Session")
        R("mcp", "Manage MCP servers (list|add|remove)", _cmd_mcp, category="Config")
        R("vim", "Open file in terminal editor", _cmd_vim, category="Utility")
        R("feedback", "Submit feedback or bug report", _cmd_feedback, ["bug"], "Utility")
        R("terminal-setup", "Show terminal configuration guide", _cmd_terminal_setup, category="Config")
        R("allowed-tools", "Show allowed tools (alias for /permissions)", _cmd_permissions, category="Config")
        R("release-notes", "Show release notes / changelog", _cmd_release_notes, ["changelog"], "Utility")

        # ── Phase 3: CC-aligned bulk command registration ──────────
        # Prompt-based commands (send prompt to Claude via engine)
        R("security-review", "Security review of current code changes", _cmd_prompt_security_review, category="Code")
        R("ultrareview", "Deep architecture-level code review", _cmd_prompt_ultrareview, category="Code")
        R("insights", "Analyze conversation patterns and usage", _cmd_prompt_insights, category="Status")
        R("pr-comments", "Review PR comments from GitHub", _cmd_prompt_pr_comments, ["pr_comments"], "Code")
        R("advisor", "Get senior advisor perspective on approach", _cmd_prompt_advisor, category="Code")
        R("explain", "Explain selected code in detail", _cmd_prompt_explain, category="Code")
        R("simplify", "Suggest code simplifications", _cmd_prompt_simplify, category="Code")
        R("typehints", "Add type hints to Python code", _cmd_prompt_typehints, category="Code")
        R("docstrings", "Add docstrings to functions", _cmd_prompt_docstrings, category="Code")
        R("test-gen", "Generate tests for code", _cmd_prompt_test_gen, category="Code")
        R("optimize", "Suggest performance optimizations", _cmd_prompt_optimize, category="Code")
        R("refactor", "Suggest refactoring improvements", _cmd_prompt_refactor, category="Code")
        R("debug", "Help debug an error", _cmd_prompt_debug, category="Code")
        R("summarize", "Summarize this conversation", _cmd_prompt_summarize, category="Utility")

        # Local commands (return result directly)
        R("rename", "Rename current session", _cmd_rename, category="Session")
        R("usage", "Show API usage summary", _cmd_usage, category="Status")
        R("keybindings", "Show keyboard shortcuts", _cmd_keybindings, ["keys"], "Config")
        R("statusline", "Toggle status line display", _cmd_statusline, category="Config")
        R("sandbox-toggle", "Toggle sandbox mode", _cmd_sandbox_toggle, ["sandbox"], "Config")
        R("passes", "Set multi-pass count", _cmd_passes, category="Mode")
        R("btw", "Add a note without triggering AI response", _cmd_btw, category="Utility")
        R("thinkback", "Show recent thinking blocks", _cmd_thinkback, category="Utility")

        # Cron commands (Phase 2 integration)
        R("cron-create", "Create a scheduled cron job", _cmd_cron_create, category="Cron")
        R("cron-list", "List all cron jobs", _cmd_cron_list, category="Cron")
        R("cron-delete", "Delete a cron job by ID", _cmd_cron_delete, category="Cron")
        R("dream", "Trigger memory consolidation", _cmd_dream, category="Memory")

        # ── Round 2: Additional CC-aligned commands ───────────────
        R("rewind", "Rewind conversation to a prior message", _cmd_rewind, category="Session")
        R("fork", "Fork conversation into a sub-agent", _cmd_fork, category="Agents")
        R("tag", "Tag current session (add/remove/list)", _cmd_tag, category="Session")
        R("workflows", "List/manage workflows", _cmd_workflows, category="Tools")
        R("privacy-settings", "Manage data privacy preferences", _cmd_privacy_settings, ["privacy"], "Config")
        R("reload-plugins", "Hot-reload plugins without restart", _cmd_reload_plugins, category="Tools")


# ═══════════════════════════════════════════════════════════════════
# Command Handlers
# ═══════════════════════════════════════════════════════════════════

# ── Core ──────────────────────────────────────────────────────────

def _cmd_help(args: str, ctx: dict) -> str:
    registry = ctx.get("command_registry")
    if not registry:
        return "Command registry not available."
    cats = registry.list_commands_by_category()
    lines = ["Available commands:\n"]
    for cat in ["Core", "Session", "Config", "Mode", "Status", "Memory",
                "Tasks", "Code", "Tools", "Soul", "Diagnostics", "Other"]:
        cmds = cats.get(cat)
        if not cmds:
            continue
        lines.append(f"  [{cat}]")
        for name, desc in cmds:
            lines.append(f"    {name:20s} {desc}")
        lines.append("")
    return "\n".join(lines)


def _cmd_clear(args: str, ctx: dict) -> str:
    engine = ctx.get("engine")
    if engine:
        engine.conversation.archive()
        return "Session archived. Starting fresh."
    return "Engine not available."


def _cmd_exit(args: str, ctx: dict) -> str:
    # Save before exit; actual quit handled by UI
    engine = ctx.get("engine")
    if engine:
        engine.save_conversation()
        sid = engine.conversation._conversation_id
        return f"__EXIT__{sid}"  # sentinel for UI: __EXIT__ + session_id
    return "__EXIT__"


def _cmd_version(args: str, ctx: dict) -> str:
    return (
        "Claude Buddy v5.0\n"
        "Desktop Pet AI Assistant with Soul\n"
        "36 tools, 34 commands\n"
        "Self-evolution system enabled\n"
        "Aligned with Claude Code architecture"
    )


# ── Session ───────────────────────────────────────────────────────

def _cmd_resume(args: str, ctx: dict) -> str:
    engine = ctx.get("engine")
    if not engine:
        return "Engine not available."

    sub = args.strip()

    # Helper: format session list
    def _format_session_list(sessions, header="Recent sessions:"):
        if not sessions:
            return "No saved sessions found."
        lines = [f"{header}\n"]
        from datetime import datetime
        for i, s in enumerate(sessions, 1):
            ts = datetime.fromtimestamp(s["saved_at"]).strftime("%m-%d %H:%M") if s["saved_at"] else "?"
            sid_short = s["id"][:8]
            lines.append(f"  {i}. [{ts}] {s['title']}  ({s['message_count']} msgs)")
            lines.append(f"     ID: {sid_short}")
        lines.append(f"\nUse /resume <ID> to restore (first 8 chars is enough).")
        return "\n".join(lines)

    if sub and sub != "list":
        # Resume a specific session by ID or number
        from core.conversation import ConversationManager
        sessions = ConversationManager.list_sessions(50)

        match = None
        # Try as a number first (e.g. /resume 1)
        if sub.isdigit():
            idx = int(sub) - 1
            if 0 <= idx < len(sessions):
                match = sessions[idx]

        # Try as ID prefix
        if not match:
            for s in sessions:
                if s["id"] == sub or s["id"].startswith(sub):
                    match = s
                    break

        if not match:
            return f"Session not found: {sub}\n" + _format_session_list(sessions)

        engine.conversation.load(match["id"])
        return f"Resumed session: {match['title']} ({engine.conversation.message_count} messages)"

    # Default (no args or "list"): show session list
    from core.conversation import ConversationManager
    sessions = ConversationManager.list_sessions(10)
    return _format_session_list(sessions)

    # No args: resume last session
    loaded = engine.conversation.load_last()
    if loaded:
        return f"Resumed conversation ({engine.conversation.message_count} messages)."
    return "No previous conversation found."


def _cmd_session(args: str, ctx: dict) -> str:
    engine = ctx.get("engine")
    if not engine:
        return "Engine not available."
    c = engine.conversation
    lines = [
        f"Session info:",
        f"  Messages: {c.message_count}",
        f"  Tokens (est): ~{c.estimated_tokens:,}",
        f"  Compactions: {c._compaction_count}",
        f"  Files read: {len(c.file_read_state.read_files)}",
        f"  Dirty: {c.is_dirty}",
    ]
    return "\n".join(lines)


def _cmd_diff(args: str, ctx: dict) -> str:
    """CC-aligned: show uncommitted git changes + files modified in this session."""
    parts = []

    # Part 1: Git diff (if in a repo)
    try:
        r = subprocess.run(
            ["git", "diff", "--stat", "HEAD"], capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        if r.returncode == 0 and r.stdout.strip():
            parts.append(f"## Uncommitted changes (git diff HEAD)\n{r.stdout.strip()}")
        elif r.returncode == 0:
            parts.append("## Uncommitted changes\nWorking tree is clean.")
    except Exception:
        pass  # Not in git repo — skip git section

    # Part 2: Session file changes (extracted from conversation tool_use messages)
    conversation = ctx.get("conversation")
    if conversation:
        written_files = set()
        edited_files = set()
        import re
        # Pattern for <tool_call>{"name": "FileWrite/FileEdit", "arguments": {"file_path": ...}}</tool_call>
        tool_call_re = re.compile(
            r'<tool_call>\s*(\{.*?\})\s*</tool_call>', re.DOTALL
        )
        for msg in conversation.messages:
            content = msg.get("content")

            # Format 1: Anthropic API list format [{type: "tool_use", ...}]
            if isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    name = block.get("name", "")
                    inp = block.get("input", {})
                    fp = inp.get("file_path", "")
                    if not fp:
                        continue
                    if name == "FileWrite":
                        written_files.add(fp)
                    elif name == "FileEdit":
                        edited_files.add(fp)

            # Format 2: BUDDY string format <tool_call>{"name":...}</tool_call>
            elif isinstance(content, str) and "<tool_call>" in content:
                import json as _json
                for m in tool_call_re.finditer(content):
                    try:
                        data = _json.loads(m.group(1))
                        name = data.get("name", "")
                        args = data.get("arguments", {})
                        fp = args.get("file_path", "")
                        if not fp:
                            continue
                        if name == "FileWrite":
                            written_files.add(fp)
                        elif name == "FileEdit":
                            edited_files.add(fp)
                    except (ValueError, TypeError):
                        pass

            # Format 3: OpenAI format — dict/str with tool_calls array
            # {"role": "assistant", "content": "...", "tool_calls": [{id, function: {name, arguments}}]}
            tool_calls_list = msg.get("tool_calls")
            if isinstance(tool_calls_list, list):
                import json as _json
                for tc in tool_calls_list:
                    func = tc.get("function", {}) if isinstance(tc, dict) else {}
                    name = func.get("name", "")
                    args_raw = func.get("arguments", "{}")
                    try:
                        args = _json.loads(args_raw) if isinstance(args_raw, str) else args_raw
                    except (ValueError, TypeError):
                        args = {}
                    fp = args.get("file_path", "") if isinstance(args, dict) else ""
                    if not fp:
                        continue
                    if name == "FileWrite":
                        written_files.add(fp)
                    elif name == "FileEdit":
                        edited_files.add(fp)

        if written_files or edited_files:
            lines = ["## Session file changes"]
            for f in sorted(written_files):
                tag = " (also edited)" if f in edited_files else ""
                lines.append(f"  + {f}{tag}")
            for f in sorted(edited_files - written_files):
                lines.append(f"  ~ {f}")
            parts.append("\n".join(lines))

    if not parts:
        return "No changes detected. Not in a git repo and no files modified this session."
    return "\n\n".join(parts)


def _cmd_files(args: str, ctx: dict) -> str:
    engine = ctx.get("engine")
    if not engine:
        return "Engine not available."
    files = engine.conversation.file_read_state.read_files
    if not files:
        return "No files read/written in this session."
    lines = [f"Files accessed ({len(files)}):"]
    for f in files[-30:]:
        lines.append(f"  {f}")
    if len(files) > 30:
        lines.append(f"  ... and {len(files) - 30} more")
    return "\n".join(lines)


def _cmd_context(args: str, ctx: dict) -> str:
    from core.context_injection import collect_context
    context = collect_context()
    lines = ["Current context:"]
    lines.append(f"  CWD: {os.getcwd()}")
    if context.get("git_branch"):
        lines.append(f"  Git branch: {context['git_branch']}")
    if context.get("git_status"):
        lines.append(f"  Git status:\n    {context['git_status'][:500]}")
    if context.get("project_type"):
        lines.append(f"  Project type: {context['project_type']}")
    if context.get("project_files"):
        lines.append(f"  Project files: {context['project_files']}")
    if context.get("claude_md"):
        lines.append(f"  CLAUDE.md: loaded ({len(context['claude_md'])} chars)")
    return "\n".join(lines)


# ── Config ────────────────────────────────────────────────────────

def _cmd_config(args: str, ctx: dict) -> str:
    if not args.strip():
        # Show current settings
        settings = ctx.get("settings")
        if settings:
            lines = ["Configuration:"]
            for attr in ["provider", "model", "api_key"]:
                val = getattr(settings, attr, None)
                if attr == "api_key" and val:
                    val = val[:8] + "..."
                lines.append(f"  {attr}: {val}")
            return "\n".join(lines)
        return "Settings not available. Use /config <key> <value> to set."
    return f"Config: {args.strip()} (use Settings dialog for changes)"


def _cmd_permissions(args: str, ctx: dict) -> str:
    perm_mgr = ctx.get("permission_mgr")
    if not perm_mgr:
        return "Permission manager not available."
    if args.strip() == "reset":
        perm_mgr.reset_permissions()
        return "All permission rules cleared."
    allowed = sorted(getattr(perm_mgr, '_always_allowed', set()))
    patterns = getattr(perm_mgr, '_allow_patterns', [])
    denied = sorted(getattr(perm_mgr, '_always_denied', set()))
    lines = ["Permission rules:"]
    if allowed:
        lines.append(f"  Always allowed: {', '.join(allowed)}")
    if patterns:
        lines.append(f"  Allow patterns: {', '.join(patterns)}")
    if denied:
        lines.append(f"  Always denied: {', '.join(denied)}")
    if len(lines) == 1:
        lines.append("  (no rules set)")
    return "\n".join(lines)


def _cmd_hooks(args: str, ctx: dict) -> str:
    return (
        "Hooks:\n"
        "  Hooks can be configured in ~/.claude-buddy/settings.json\n"
        "  Available hook points:\n"
        "    pre_tool:   Run before each tool execution\n"
        "    post_tool:  Run after each tool execution\n"
        "    pre_commit: Run before git commit\n"
        "    on_error:   Run when an error occurs\n"
        "  (No hooks currently configured)"
    )


def _cmd_theme(args: str, ctx: dict) -> str:
    theme = args.strip().lower()
    if theme in ("dark", "light"):
        return f"Theme set to: {theme} (will apply on next restart)"
    return "Usage: /theme dark | /theme light"


# ── Mode ──────────────────────────────────────────────────────────

def _cmd_plan(args: str, ctx: dict) -> str:
    registry = ctx.get("tool_registry")
    if not registry:
        return "Tool registry not available."
    state = registry.plan_mode_state
    if args.strip() == "exit":
        state.exit()
        return "Plan mode deactivated. Full tool access restored."
    if state.active:
        return "Plan mode is already active. Use /plan exit to deactivate."
    state.enter()
    return (
        "Plan mode activated.\n"
        "Write tools (FileEdit, FileWrite, Bash, etc.) are blocked.\n"
        "Only read-only tools (FileRead, Glob, Grep, etc.) are available.\n"
        "Use /plan exit to restore full access."
    )


def _cmd_fast(args: str, ctx: dict) -> str:
    # Toggle a fast-mode flag in engine or settings
    engine = ctx.get("engine")
    if not engine:
        return "Engine not available."
    current = getattr(engine, '_fast_mode', False)
    engine._fast_mode = not current
    state = "ON" if engine._fast_mode else "OFF"
    return f"Fast mode: {state} (concise responses, minimal explanations)"


def _cmd_effort(args: str, ctx: dict) -> str:
    level = args.strip().lower()
    if level in ("high", "medium", "low"):
        engine = ctx.get("engine")
        if engine:
            engine._effort_level = level
        return f"Reasoning effort set to: {level}"
    return "Usage: /effort high | /effort medium | /effort low"


# ── Cost & Status ─────────────────────────────────────────────────

def _cmd_cost(args: str, ctx: dict) -> str:
    engine = ctx.get("engine")
    if engine:
        return engine.get_cost_summary() or "No API calls yet."
    return "Engine not available."


def _cmd_status(args: str, ctx: dict) -> str:
    engine = ctx.get("engine")
    if not engine:
        return "Engine not available."
    c = engine.conversation
    lines = [
        f"Running: {engine._is_running}",
        f"Messages: {c.message_count}",
        f"Tokens (est): ~{c.estimated_tokens:,}",
        f"Context window: {engine._context_window:,}",
        f"Compactions: {c._compaction_count}",
        f"Files read: {len(c.file_read_state.read_files)}",
        f"Plan mode: {'active' if engine._plan_mode_state and engine._plan_mode_state.active else 'off'}",
        f"Fast mode: {'on' if getattr(engine, '_fast_mode', False) else 'off'}",
    ]
    return "Engine status:\n" + "\n".join(f"  {l}" for l in lines)


def _cmd_model(args: str, ctx: dict) -> str:
    engine = ctx.get("engine")
    if not engine:
        return "Engine not available."
    if args.strip():
        engine._provider_model = args.strip()
        return f"Model set to: {args.strip()} (takes effect on next API call)"
    return f"Current model: {engine._provider_model or '(not set)'}"


def _cmd_stats(args: str, ctx: dict) -> str:
    """Show usage statistics."""
    analytics = ctx.get("analytics")
    if analytics:
        sub = args.strip()
        if sub == "week":
            return analytics.load_report(days=7)
        elif sub == "today":
            return analytics.format_report("Today's Statistics")
        elif sub == "flush":
            analytics.flush()
            return "Analytics flushed to disk."
        return analytics.format_report()
    # Fallback: try global singleton
    try:
        from core.services.analytics import get_analytics
        return get_analytics().format_report()
    except Exception:
        return "Analytics not available."


def _cmd_flags(args: str, ctx: dict) -> str:
    """Show or set feature flags."""
    try:
        from core.services.analytics import get_feature_flags
        ff = get_feature_flags()
    except Exception:
        return "Feature flags not available."

    sub = args.strip()
    if not sub or sub == "show":
        return ff.format_status()
    elif sub == "reload":
        ff.reload()
        return "Feature flags reloaded from disk."
    elif "=" in sub:
        key, _, value = sub.partition("=")
        key = key.strip()
        value = value.strip()
        # Parse value
        if value.lower() in ("true", "on", "yes", "1"):
            ff.set(key, True)
        elif value.lower() in ("false", "off", "no", "0"):
            ff.set(key, False)
        else:
            try:
                ff.set(key, int(value))
            except ValueError:
                ff.set(key, value)
        return f"Flag set: {key} = {ff.get(key)}"
    return "Usage: /flags [show|reload|key=value]"


# ── Memory & Compaction ───────────────────────────────────────────

def _cmd_memory(args: str, ctx: dict) -> str:
    memory_mgr = ctx.get("memory_mgr")
    if not memory_mgr:
        return "Memory system not available."
    sub = args.strip()

    if sub == "clear":
        memory_mgr.clear_memory()
        return "Memory cleared."
    elif sub == "show":
        content = memory_mgr.load_memory()
        if content:
            return f"Stored memory:\n{content}"
        return "No memory stored."
    elif not sub:
        # CC-aligned: try to open memory file in editor
        from config import DATA_DIR
        memory_file = DATA_DIR / "memory" / "MEMORY.md"
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        if not memory_file.exists():
            memory_file.write_text("# Memory\n\n", encoding="utf-8")

        editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
        if editor:
            import subprocess
            try:
                subprocess.Popen([editor, str(memory_file)])
                return f"Opened {memory_file} in {editor}"
            except Exception as e:
                return f"Failed to open editor: {e}\n\nUse `/memory show` to view memory."
        else:
            # Fallback: show content
            content = memory_mgr.load_memory()
            if content:
                return f"Stored memory:\n{content}\n\n(Set $EDITOR to edit directly)"
            return "No memory stored. (Set $EDITOR to edit directly)"
    else:
        # /memory <text> — save with CC-aligned auto-categorization
        category = "user"
        lower = sub.lower()
        if any(w in lower for w in ("jira", "slack", "url", "link", "grafana", "linear")):
            category = "reference"
        elif any(w in lower for w in ("project", "architecture", "decision", "deadline", "roadmap")):
            category = "project"
        elif any(w in lower for w in ("don't", "do not", "always use", "never mock", "policy", "approach")):
            category = "feedback"
        memory_mgr.save_memory(sub, category=category, name=sub[:40])
        return f"Memory saved [{category}]: {sub[:100]}"


def _cmd_compact(args: str, ctx: dict) -> str:
    engine = ctx.get("engine")
    if engine:
        result = engine.conversation.compact_if_needed()
        if result:
            return f"Compaction: {result}"
        engine.conversation._full_compact()
        return "Forced compaction complete."
    return "Engine not available."


# ── Tasks (CC: background tasks, NOT task list) ──────────────────

def _cmd_bg_tasks(args: str, ctx: dict) -> str:
    """CC-aligned: /tasks shows background tasks (running Bash, agents, etc.).
    Task list (TaskCreate/TaskList/TaskGet/TaskUpdate) is tools-only, not a command."""
    engine = ctx.get("engine")
    if not engine:
        return "Engine not available."

    bg_tasks = getattr(engine, '_background_tasks', {})
    if not bg_tasks:
        return "No background tasks."

    lines = ["Background tasks:"]
    for tid, rec in bg_tasks.items():
        status = rec.get("status", "unknown")
        cmd = rec.get("command", rec.get("description", ""))
        if isinstance(cmd, str) and len(cmd) > 60:
            cmd = cmd[:60] + "..."
        icon = {"running": "🔄", "completed": "✅", "stopped": "⏹", "error": "❌"}.get(status, "❓")
        lines.append(f"  {icon} [{tid}] {status}: {cmd}")
    return "\n".join(lines)


# ── Code Review ───────────────────────────────────────────────────

def _cmd_review(args: str, ctx: dict) -> str:
    """Generate a review prompt from current git diff."""
    try:
        r = subprocess.run(
            ["git", "diff"], capture_output=True, text=True, timeout=15,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        diff = r.stdout.strip()
        if not diff:
            r = subprocess.run(
                ["git", "diff", "--cached"], capture_output=True, text=True, timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
            )
            diff = r.stdout.strip()
        if not diff:
            return "No changes to review. Stage changes with git add first."
        # Return as a prompt for the LLM to review
        truncated = diff[:8000] + ("\n... (truncated)" if len(diff) > 8000 else "")
        return f"__LLM_PROMPT__Please review this diff for bugs, style issues, and improvements:\n\n```diff\n{truncated}\n```"
    except Exception:
        return "Not in a git repository, or git not available."


def _cmd_pr(args: str, ctx: dict) -> str:
    """Generate a PR creation prompt for the LLM."""
    try:
        # Get branch info
        r = subprocess.run(
            ["git", "branch", "--show-current"], capture_output=True, text=True, timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        branch = r.stdout.strip()
        r2 = subprocess.run(
            ["git", "log", "--oneline", "main..HEAD"], capture_output=True, text=True, timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        )
        commits = r2.stdout.strip() or "(no commits ahead of main)"
        return (
            f"__LLM_PROMPT__Create a pull request for branch '{branch}'.\n"
            f"Commits:\n{commits}\n\n"
            f"Please: 1) Push if needed, 2) Create PR with title+description using gh or git."
        )
    except Exception:
        return "Not in a git repository, or git not available."


# ── Branch + Output Style ─────────────────────────────────────────

def _cmd_branch(args: str, ctx: dict) -> str:
    """Git branch management."""
    sub = args.strip()
    try:
        if not sub or sub == "list":
            r = subprocess.run(["git", "branch", "-a"], capture_output=True, text=True, timeout=10,
                               creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0)
            return r.stdout.strip() if r.stdout.strip() else "No branches found."
        elif sub == "current":
            r = subprocess.run(["git", "branch", "--show-current"], capture_output=True, text=True, timeout=5,
                               creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0)
            return f"Current branch: {r.stdout.strip()}"
        elif sub.startswith("switch ") or sub.startswith("checkout "):
            branch = sub.split(maxsplit=1)[1]
            return f"__LLM_PROMPT__Switch to branch '{branch}'. Use: git checkout {branch}"
        elif sub.startswith("create "):
            branch = sub.split(maxsplit=1)[1]
            return f"__LLM_PROMPT__Create branch '{branch}'. Use: git checkout -b {branch}"
        return "Usage: /branch [list|current|switch <name>|create <name>]"
    except Exception:
        return "Not in a git repository, or git not available."


def _cmd_output_style(args: str, ctx: dict) -> str:
    """Set output style."""
    style = args.strip().lower()
    engine = ctx.get("engine")
    if style in ("concise", "brief"):
        if engine: engine._fast_mode = True
        return "Output style: concise (brief responses, minimal explanation)"
    elif style in ("detailed", "verbose"):
        if engine: engine._fast_mode = False
        return "Output style: detailed (full explanations, thorough analysis)"
    elif style in ("default", "normal", ""):
        if engine: engine._fast_mode = False
        return "Output style: default"
    return "Usage: /output-style [concise|detailed|default]"


# ── Tool Discovery ────────────────────────────────────────────────

def _cmd_tools(args: str, ctx: dict) -> str:
    registry = ctx.get("tool_registry")
    if not registry:
        return "Tool registry not available."
    tools = registry.all_tools()
    lines = [f"Available tools ({len(tools)}):"]
    for t in sorted(tools, key=lambda x: x.name):
        ro = " (read-only)" if t.is_read_only else ""
        lines.append(f"  {t.name:20s}{ro}")
    return "\n".join(lines)


def _cmd_plugins(args: str, ctx: dict) -> str:
    plugin_mgr = ctx.get("plugin_mgr")
    if plugin_mgr:
        sub = args.strip().lower()
        if sub.startswith("reload "):
            name = sub[7:].strip()
            return plugin_mgr.reload(name,
                                     tool_registry=ctx.get("tool_registry"),
                                     command_registry=ctx.get("command_registry"))
        return plugin_mgr.format_status()
    # Fallback: just list directory
    plugins_dir = Path.home() / ".claude-buddy" / "plugins"
    if not plugins_dir.exists():
        return f"No plugins directory. Create {plugins_dir}/ to add plugins."
    plugins = [p.stem for p in plugins_dir.iterdir() if p.is_dir() or p.suffix == ".py"]
    if not plugins:
        return f"No plugins found in {plugins_dir}/"
    return f"Plugins ({len(plugins)}):\n" + "\n".join(f"  {p}" for p in sorted(plugins))


def _cmd_skills(args: str, ctx: dict) -> str:
    from config import DATA_DIR
    skills_dir = DATA_DIR / "skills"
    skills = []
    if skills_dir.exists():
        skills = [f.stem for f in skills_dir.iterdir() if f.suffix in (".json", ".md")]
    # Also list commands as skills
    registry = ctx.get("command_registry")
    cmd_names = []
    if registry:
        cmd_names = [n.lstrip("/") for n, _ in registry.list_commands()]
    all_skills = sorted(set(skills + cmd_names))
    if not all_skills:
        return "No skills available."
    return f"Available skills ({len(all_skills)}):\n" + "\n".join(f"  {s}" for s in all_skills)


# ── Diagnostics ───────────────────────────────────────────────────

def _cmd_doctor(args: str, ctx: dict) -> str:
    """Run system diagnostics."""
    import shutil
    lines = ["System diagnostics:\n"]

    # Python
    import sys
    lines.append(f"  Python: {sys.version.split()[0]}")

    # OS
    lines.append(f"  Platform: {platform.platform()}")

    # Git
    git = shutil.which("git")
    if git:
        try:
            r = subprocess.run(["git", "--version"], capture_output=True, text=True, timeout=5)
            lines.append(f"  Git: {r.stdout.strip()}")
        except Exception:
            lines.append(f"  Git: found at {git} (version check failed)")
    else:
        lines.append("  Git: NOT FOUND")

    # ripgrep
    rg = shutil.which("rg")
    lines.append(f"  Ripgrep: {'found' if rg else 'not found (Grep will use Python fallback)'}")

    # gh CLI
    gh = shutil.which("gh")
    lines.append(f"  GitHub CLI (gh): {'found' if gh else 'not found'}")

    # Node
    node = shutil.which("node")
    lines.append(f"  Node.js: {'found' if node else 'not found'}")

    # Engine
    engine = ctx.get("engine")
    if engine:
        lines.append(f"\n  Engine: OK")
        lines.append(f"  Provider: {engine._provider_model or '(not set)'}")
        lines.append(f"  Tools: {len(engine._tool_executors)}")
        lines.append(f"  Context window: {engine._context_window:,} tokens")
    else:
        lines.append(f"\n  Engine: NOT AVAILABLE")

    # Memory
    from config import DATA_DIR
    lines.append(f"\n  Data directory: {DATA_DIR}")
    lines.append(f"  Data dir exists: {DATA_DIR.exists()}")
    mem_dir = DATA_DIR / "memory"
    lines.append(f"  Memory dir: {'exists' if mem_dir.exists() else 'not created yet'}")

    # Disk space
    try:
        usage = shutil.disk_usage(str(DATA_DIR))
        free_gb = usage.free / (1024**3)
        lines.append(f"  Disk free: {free_gb:.1f} GB")
    except Exception:
        pass

    lines.append("\n  All checks complete.")
    return "\n".join(lines)


# ── Data (export/import) ─────────────────────────────────────────

def _cmd_export(args: str, ctx: dict) -> str:
    """Export conversation to a file."""
    import json as _json
    engine = ctx.get("engine")
    if not engine:
        return "Engine not available."
    fmt = args.strip().lower() or "json"
    msgs = engine.conversation.messages

    if fmt == "json":
        from config import DATA_DIR
        export_path = DATA_DIR / "export.json"
        with open(export_path, "w", encoding="utf-8") as f:
            _json.dump(msgs, f, ensure_ascii=False, indent=2, default=str)
        return f"Exported {len(msgs)} messages to {export_path}"
    elif fmt in ("md", "markdown"):
        from config import DATA_DIR
        export_path = DATA_DIR / "export.md"
        lines = []
        for m in msgs:
            role = m.get("role", "?")
            content = m.get("content", "")
            if isinstance(content, str):
                lines.append(f"**{role}**: {content[:2000]}\n")
        with open(export_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return f"Exported {len(msgs)} messages to {export_path}"
    return "Usage: /export [json|md]"


def _cmd_import(args: str, ctx: dict) -> str:
    """Import conversation from a JSON file."""
    import json as _json
    engine = ctx.get("engine")
    if not engine:
        return "Engine not available."
    file_path = args.strip()
    if not file_path:
        from config import DATA_DIR
        file_path = str(DATA_DIR / "export.json")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            msgs = _json.load(f)
        if not isinstance(msgs, list):
            return "Error: file must contain a JSON array of messages."
        engine.conversation._messages = msgs
        engine.conversation._recalculate_token_estimate()
        return f"Imported {len(msgs)} messages from {file_path}"
    except FileNotFoundError:
        return f"File not found: {file_path}"
    except Exception as e:
        return f"Error importing: {e}"


# ── Agent Management ──────────────────────────────────────────────

def _cmd_agents(args: str, ctx: dict) -> str:
    """List active agents."""
    registry = ctx.get("tool_registry")
    if not registry or not hasattr(registry, 'agent_registry'):
        return "Agent registry not available."
    agents = registry.agent_registry.list_agents()
    if not agents:
        return "No active agents."
    lines = [f"Active agents ({len(agents)}):"]
    for a in agents:
        team = f" [team: {a.get('team', '')}]" if a.get("team") else ""
        lines.append(f"  {a['id']}: {a.get('name', '?')}{team} ({a.get('status', '?')})")
    return "\n".join(lines)


# ── Environment ──────────────────────────────────────────────────

def _cmd_env(args: str, ctx: dict) -> str:
    """Show or set environment variables."""
    sub = args.strip()
    if not sub or sub == "show":
        # Show relevant env vars (hide sensitive ones)
        safe_keys = ["PATH", "HOME", "USER", "SHELL", "COMSPEC", "PWD", "LANG",
                     "TERM", "PYTHONPATH", "VIRTUAL_ENV", "CONDA_DEFAULT_ENV"]
        lines = ["Environment:"]
        for key in safe_keys:
            val = os.environ.get(key)
            if val:
                display = val[:100] + "..." if len(val) > 100 else val
                lines.append(f"  {key}={display}")
        return "\n".join(lines)
    elif "=" in sub:
        key, _, value = sub.partition("=")
        key = key.strip()
        value = value.strip()
        os.environ[key] = value
        return f"Set {key}={value}"
    else:
        val = os.environ.get(sub)
        if val:
            return f"{sub}={val}"
        return f"Environment variable '{sub}' not set."


# ── Utility ──────────────────────────────────────────────────────

def _cmd_copy(args: str, ctx: dict) -> str:
    """Copy last assistant reply to clipboard."""
    engine = ctx.get("engine")
    if not engine:
        return "Engine not available."
    msgs = engine.conversation.messages
    # Find last assistant message
    for msg in reversed(msgs):
        if msg.get("role") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, str) and content.strip():
                try:
                    if platform.system() == "Windows":
                        subprocess.run(["clip"], input=content.encode("utf-8"),
                                       check=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    elif platform.system() == "Darwin":
                        subprocess.run(["pbcopy"], input=content.encode("utf-8"), check=True)
                    else:
                        subprocess.run(["xclip", "-selection", "clipboard"],
                                       input=content.encode("utf-8"), check=True)
                    return f"Copied {len(content)} chars to clipboard."
                except Exception as e:
                    return f"Clipboard copy failed: {e}. Content:\n{content[:200]}"
    return "No assistant message found to copy."


def _cmd_onboarding(args: str, ctx: dict) -> str:
    """First-time setup guide."""
    return """\
Welcome to Claude Buddy!

Quick Start:
  1. Set your API key: click the gear icon or use /config
  2. Start chatting: type a message and press Enter
  3. Use tools: I can read/write files, run commands, search the web

Key Commands:
  /help        Show all commands
  /tools       List available tools
  /status      Check engine status
  /doctor      Run system diagnostics
  /memory      Manage persistent memory
  /plugins     List loaded plugins
  /stats       View usage statistics

Tips:
  - I can edit files directly — just tell me what to change
  - I track which files I've read, so I won't make blind edits
  - Use /compact if the conversation gets too long
  - Right-click the pet for more options

Need help? Just ask!"""


# ═══════════════════════════════════════════════════════════════════
# Phase 6: CC-aligned New Commands
# ═══════════════════════════════════════════════════════════════════

def _cmd_init(args: str, ctx: dict) -> str:
    """CC-aligned: /init sends a prompt to the model to analyze the codebase
    and generate CLAUDE.md. The model uses tools (FileRead, Glob, Grep) to
    explore the project, then writes CLAUDE.md via FileWrite.

    If CLAUDE.md exists: model reads it and proposes improvements as diffs.
    """
    claude_md = Path(os.getcwd()) / "CLAUDE.md"
    exists = claude_md.exists()

    # CC-aligned: this is a prompt-type command — the model does the work
    prompt = f"""Please analyze this codebase and {"improve the existing" if exists else "create a"} CLAUDE.md file.

Current working directory: {os.getcwd()}
{"CLAUDE.md already exists — read it first, then propose specific improvements. Do NOT silently overwrite." if exists else "No CLAUDE.md found — create one from scratch."}

**Step 1: Explore the codebase**
Use Glob, FileRead, and Grep to discover:
- Manifest files (package.json, pyproject.toml, Cargo.toml, go.mod, requirements.txt, etc.)
- README.md, Makefile, CI config, existing CLAUDE.md
- Build/test/lint commands
- Languages, frameworks, project structure
- Code style conventions (formatter configs: prettier, ruff, black, etc.)

**Step 2: Write CLAUDE.md**
Every line must pass: "Would removing this cause Claude to make mistakes?"

Include:
- Build/test/lint commands that can't be guessed
- Code style rules that differ from language defaults
- Testing instructions and quirks
- Repo etiquette (branch naming, PR conventions, commit style)
- Required env vars or setup steps
- Non-obvious gotchas or architectural decisions
- Important parts from existing AI configs (.cursor/rules, .cursorrules, .github/copilot-instructions.md)

Exclude:
- File-by-file structure (Claude can discover this with tools)
- Standard language conventions everyone knows
- Generic development advice
- Detailed API docs (use @path/to/file references instead)

Prefix the file with:
```
# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.
```

{"Read the existing CLAUDE.md first, then propose specific changes as diffs and explain why each improves it. Do not silently overwrite." if exists else "Write the file using FileWrite."}"""

    return f"__LLM_PROMPT__{prompt}"


def _cmd_add_dir(args: str, ctx: dict) -> str:
    """Add a directory to the context for the current session."""
    dir_path = args.strip()
    if not dir_path:
        return "Usage: /add-dir <path>\nAdds directory to context for this session."

    resolved = Path(dir_path).resolve()
    if not resolved.is_dir():
        return f"Error: Not a directory: {resolved}"

    engine = ctx.get("engine")
    if engine:
        if not hasattr(engine, '_extra_context_dirs'):
            engine._extra_context_dirs = []
        if str(resolved) not in engine._extra_context_dirs:
            engine._extra_context_dirs.append(str(resolved))
        return f"Added {resolved} to context. ({len(engine._extra_context_dirs)} dirs total)"
    return "Engine not available."


def _cmd_mcp(args: str, ctx: dict) -> str:
    """Manage MCP servers."""
    sub = args.strip().lower()

    try:
        from core.services.mcp import MCPManager
    except ImportError:
        return "MCP module not available."

    # Try to get existing manager or create new one
    mcp = None
    registry = ctx.get("tool_registry")
    if registry and hasattr(registry, '_mcp_manager'):
        mcp = registry._mcp_manager
    if not mcp:
        mcp = MCPManager()

    if not sub or sub == "list":
        servers = mcp.list_servers()
        if not servers:
            return "No MCP servers configured.\nUse `/mcp add <name> <command>` to add one."
        if isinstance(servers, list):
            lines = ["MCP Servers:"]
            for s in servers:
                if isinstance(s, dict):
                    lines.append(f"  {s.get('name', '?')}: {s.get('status', '?')}")
                else:
                    lines.append(f"  {s}")
            return "\n".join(lines)
        return str(servers)

    if sub.startswith("add "):
        parts = sub[4:].strip().split(maxsplit=1)
        if len(parts) < 2:
            return "Usage: /mcp add <name> <command>"
        name, command = parts
        try:
            mcp.add_server(name, command)
            return f"Added MCP server: {name}"
        except Exception as e:
            return f"Error adding server: {e}"

    if sub.startswith("remove "):
        name = sub[7:].strip()
        try:
            mcp.remove_server(name)
            return f"Removed MCP server: {name}"
        except Exception as e:
            return f"Error removing server: {e}"

    return "Usage: /mcp [list|add <name> <cmd>|remove <name>]"


def _cmd_vim(args: str, ctx: dict) -> str:
    """Open a file in terminal editor (vim/nano/notepad)."""
    file_path = args.strip()
    if not file_path:
        return "Usage: /vim <file_path>"

    resolved = Path(file_path)
    if not resolved.exists():
        return f"File not found: {resolved}"

    import shutil
    if platform.system() == "Windows":
        editor = shutil.which("notepad") or "notepad"
    else:
        editor = os.environ.get("EDITOR", shutil.which("vim") or shutil.which("nano") or "vi")

    try:
        # Launch editor in background (non-blocking)
        if platform.system() == "Windows":
            subprocess.Popen([editor, str(resolved)],
                             creationflags=subprocess.CREATE_NO_WINDOW)
        else:
            subprocess.Popen([editor, str(resolved)])
        return f"Opened {resolved} in {Path(editor).name}"
    except Exception as e:
        return f"Error opening editor: {e}"


def _cmd_feedback(args: str, ctx: dict) -> str:
    """Save user feedback to disk."""
    text = args.strip()
    if not text:
        return "Usage: /feedback <your feedback text>\nSaves feedback for improvement."

    import json as _json
    from config import DATA_DIR
    feedback_file = DATA_DIR / "feedback.json"

    entries = []
    if feedback_file.exists():
        try:
            entries = _json.loads(feedback_file.read_text(encoding="utf-8"))
        except Exception:
            entries = []

    entries.append({
        "text": text,
        "timestamp": time.time(),
        "session": ctx.get("engine", None) and ctx["engine"].conversation._conversation_id,
    })

    feedback_file.write_text(_json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"Feedback saved. ({len(entries)} total entries in {feedback_file})"


def _cmd_terminal_setup(args: str, ctx: dict) -> str:
    """Show terminal configuration guide."""
    return """\
Terminal Setup Guide:

Keyboard Shortcuts:
  Enter        Send message
  Shift+Enter  New line (in supported terminals)
  ↑ / ↓        Browse input history
  Ctrl+C       Cancel current operation
  Escape       Close dialog

Configuration:
  Settings are stored in: ~/.claude-buddy/settings.json
  Conversation history:   ~/.claude-buddy/conversations/
  Memory & plugins:       ~/.claude-buddy/

For best experience:
  - Use a terminal with UTF-8 support
  - Set font to a monospace font (Consolas, SF Mono, JetBrains Mono)
  - Enable 256-color mode for proper styling"""


def _cmd_release_notes(args: str, ctx: dict) -> str:
    """Show release notes from CHANGELOG.md."""
    from config import APP_DIR
    changelog = APP_DIR / "CHANGELOG.md"
    if not changelog.exists():
        # Try alternate locations
        for name in ["CHANGELOG.md", "CHANGES.md", "HISTORY.md"]:
            alt = APP_DIR / name
            if alt.exists():
                changelog = alt
                break

    if not changelog.exists():
        return (
            "Claude Buddy v5.1\n"
            "Phase 1-5 complete: Extended Thinking, Prompt Caching, Effort Level,\n"
            "Structured Output, Response Withholding, Streaming Fallback,\n"
            "Curly Quote Normalization, UTF-16 Support, Image/PDF Reading,\n"
            "Agent Model Override, Parallel Tool Execution.\n"
            "\nNo CHANGELOG.md found. Create one at the project root."
        )

    content = changelog.read_text(encoding="utf-8", errors="replace")
    if len(content) > 5000:
        return content[:5000] + "\n\n(truncated — showing first 5000 chars)"
    return content


# ═══════════════════════════════════════════════════════════════════
# Soul & Evolution Commands
# ═══════════════════════════════════════════════════════════════════

def _cmd_soul(args: str, ctx: dict) -> str:
    """Show BUDDY's soul status."""
    try:
        from core.evolution import EvolutionManager
        evo = ctx.get("evolution_mgr")
        if not evo:
            evo = EvolutionManager()

        sub = args.strip().lower()
        if sub == "personality":
            return evo._read_soul_file("personality.md") or "No personality file found."
        elif sub == "aspirations":
            return evo._read_soul_file("aspirations.md") or "No aspirations file found."
        elif sub == "relationships":
            return evo._read_soul_file("relationships.md") or "No relationships file found."
        elif sub == "all":
            soul = evo.read_soul()
            parts = []
            for name, content in soul.items():
                if content:
                    parts.append(f"═══ {name} ═══\n{content}")
            return "\n\n".join(parts) if parts else "Soul files are empty."
        else:
            return evo.soul_status()
    except Exception as e:
        return f"Error reading soul: {e}"


def _cmd_diary(args: str, ctx: dict) -> str:
    """Show BUDDY's diary."""
    try:
        from core.evolution import EvolutionManager, SOUL_DIR
        diary_path = SOUL_DIR / "diary.md"
        if not diary_path.exists():
            return "No diary entries yet."

        content = diary_path.read_text(encoding="utf-8")
        sub = args.strip()

        if sub == "last":
            # Show only the last entry
            sections = content.split("\n## ")
            if len(sections) > 1:
                return "## " + sections[-1]
            return content

        if sub.isdigit():
            # Show last N entries
            n = int(sub)
            sections = content.split("\n## ")
            if len(sections) > 1:
                recent = sections[-n:] if n < len(sections) else sections[1:]
                return "\n\n## ".join(recent)
            return content

        # Default: show full diary (truncated if too long)
        if len(content) > 5000:
            return content[-5000:] + "\n\n(Showing last 5000 chars. Use /diary <N> for last N entries.)"
        return content
    except Exception as e:
        return f"Error reading diary: {e}"


def _cmd_evolve(args: str, ctx: dict) -> str:
    """Show evolution changelog."""
    try:
        from core.evolution import EvolutionManager
        evo = ctx.get("evolution_mgr")
        if not evo:
            evo = EvolutionManager()

        sub = args.strip()
        lines = 30
        if sub.isdigit():
            lines = int(sub)

        changelog = evo.get_changelog(lines)
        return changelog if changelog else "No evolution changes recorded yet."
    except Exception as e:
        return f"Error reading changelog: {e}"


def _cmd_rollback(args: str, ctx: dict) -> str:
    """Rollback a file to its previous version."""
    try:
        from core.evolution import EvolutionManager, BUDDY_ROOT, SOUL_DIR
        evo = ctx.get("evolution_mgr")
        if not evo:
            evo = EvolutionManager()

        file_path = args.strip()
        if not file_path:
            return (
                "Usage: /rollback <file_path>\n"
                "Examples:\n"
                "  /rollback prompts/system.py\n"
                "  /rollback soul/personality.md\n"
                "  /rollback core/engine.py\n"
                "  /rollback <absolute_path>"
            )

        # Resolve path
        if file_path.startswith("soul/"):
            resolved = str(SOUL_DIR / file_path[5:])
        elif not Path(file_path).is_absolute():
            resolved = str(BUDDY_ROOT / file_path)
        else:
            resolved = file_path

        # List available backups
        backups = evo.list_backups(resolved)
        if not backups:
            return f"No backups found for: {file_path}"

        # Show backups and perform rollback
        backup_list = "\n".join(
            f"  {i+1}. {b['name']} ({b['time']}, {b['size']} bytes)"
            for i, b in enumerate(backups[:5])
        )

        ok = evo.rollback(resolved)
        if ok:
            return (
                f"✅ Rolled back: {file_path}\n"
                f"Available backups (most recent first):\n{backup_list}"
            )
        return f"❌ Rollback failed for: {file_path}"
    except Exception as e:
        return f"Error during rollback: {e}"


# ═══════════════════════════════════════════════════════════════════
# Phase 3: Prompt-based Commands (CC-aligned)
# These return a PROMPT string that gets sent to the LLM engine.
# The command returns {"_prompt": "..."} and the main handler sends it.
# ═══════════════════════════════════════════════════════════════════

def _make_prompt_cmd(prompt_template: str):
    """Factory for prompt-based commands. Returns handler."""
    def handler(args: str, ctx: dict) -> str:
        prompt = prompt_template
        if args.strip():
            prompt += f"\n\nContext from user: {args.strip()}"
        # Return as _prompt marker for the main handler to send to engine
        return f"__PROMPT_CMD__:{prompt}"
    return handler

_cmd_prompt_security_review = _make_prompt_cmd(
    "Review the current code changes for security vulnerabilities. "
    "Check for: injection flaws, auth issues, data exposure, insecure dependencies, "
    "hardcoded secrets, CSRF, XSS, and other OWASP Top 10 risks. "
    "For each finding, rate severity (Critical/High/Medium/Low) and suggest a fix."
)

_cmd_prompt_ultrareview = _make_prompt_cmd(
    "Perform a deep architecture-level code review of the current changes. "
    "Analyze: design patterns, SOLID principles, performance implications, "
    "error handling completeness, edge cases, test coverage gaps, "
    "and maintainability concerns. Be thorough and specific."
)

_cmd_prompt_insights = _make_prompt_cmd(
    "Analyze our recent conversation and provide insights: "
    "What patterns emerged? What was accomplished? What areas need more attention? "
    "Suggest next steps based on the conversation trajectory."
)

_cmd_prompt_pr_comments = _make_prompt_cmd(
    "Review the PR comments. Run `gh pr view --json comments,reviews` to fetch them, "
    "then summarize the feedback and suggest responses or code changes for each comment."
)

_cmd_prompt_advisor = _make_prompt_cmd(
    "Act as a senior technical advisor. Review my current approach and provide "
    "strategic guidance: Is this the right architecture? What risks am I missing? "
    "What would you do differently? Be candid and constructive."
)

_cmd_prompt_explain = _make_prompt_cmd(
    "Explain the code in detail. Break down: what it does, how it works, "
    "key design decisions, and any non-obvious behavior. "
    "Use clear language suitable for a code review."
)

_cmd_prompt_simplify = _make_prompt_cmd(
    "Suggest simplifications for this code. Look for: unnecessary complexity, "
    "redundant logic, opportunities to use standard library, "
    "cleaner patterns, and dead code. Show before/after for each suggestion."
)

_cmd_prompt_typehints = _make_prompt_cmd(
    "Add comprehensive Python type hints to the code. Include: function signatures, "
    "return types, variable annotations where helpful, and generic types. "
    "Follow PEP 484/585 conventions. Use modern syntax (X | Y instead of Union[X, Y])."
)

_cmd_prompt_docstrings = _make_prompt_cmd(
    "Add Google-style docstrings to all public functions and classes. "
    "Include: one-line summary, Args, Returns, Raises sections as appropriate. "
    "Be concise but complete."
)

_cmd_prompt_test_gen = _make_prompt_cmd(
    "Generate comprehensive tests for this code. Include: happy path, edge cases, "
    "error handling, boundary conditions. Use pytest conventions. "
    "Mock external dependencies. Aim for high coverage."
)

_cmd_prompt_optimize = _make_prompt_cmd(
    "Suggest performance optimizations. Analyze: algorithmic complexity, "
    "I/O patterns, memory usage, caching opportunities, lazy evaluation, "
    "and parallelism potential. Quantify expected improvement where possible."
)

_cmd_prompt_refactor = _make_prompt_cmd(
    "Suggest refactoring improvements. Look for: code duplication, "
    "long methods, deep nesting, unclear naming, missing abstractions, "
    "and coupling issues. Propose specific refactoring patterns."
)

_cmd_prompt_debug = _make_prompt_cmd(
    "Help debug this issue. Analyze the error message and code context. "
    "Identify potential root causes, suggest diagnostic steps, "
    "and propose fixes ranked by likelihood."
)

_cmd_prompt_summarize = _make_prompt_cmd(
    "Summarize this conversation concisely. Cover: what was requested, "
    "what was accomplished, key decisions made, and any outstanding items."
)


# ═══════════════════════════════════════════════════════════════════
# Phase 3: Local Commands
# ═══════════════════════════════════════════════════════════════════

def _cmd_rename(args: str, ctx: dict) -> str:
    """Rename current session."""
    engine = ctx.get("engine")
    new_name = args.strip()
    if not new_name:
        return "Usage: /rename <new_name>"
    if engine and hasattr(engine, '_conversation'):
        engine._conversation._conversation_id = new_name
        engine._conversation._dirty = True
        return f"Session renamed to: {new_name}"
    return "No active session to rename."


def _cmd_usage(args: str, ctx: dict) -> str:
    """Show API usage summary (alias for detailed /cost)."""
    engine = ctx.get("engine")
    if not engine:
        return "Engine not available."
    cost = engine.session_cost
    lines = [
        "API Usage Summary",
        "─" * 40,
        f"  API calls:     {cost.total_api_calls}",
        f"  Tool calls:    {cost.total_tool_calls}",
        f"  Input tokens:  {cost.total_input_tokens:,}",
        f"  Output tokens: {cost.total_output_tokens:,}",
    ]
    if cost.cache_read_tokens or cost.cache_creation_tokens:
        lines.append(f"  Cache read:    {cost.cache_read_tokens:,}")
        lines.append(f"  Cache create:  {cost.cache_creation_tokens:,}")
    usd = cost.cost_usd
    if usd > 0:
        lines.append(f"  Est. cost:     ${usd:.4f}")
    if cost.model_usage:
        lines.append("\n  By model:")
        for model, usage in cost.model_usage.items():
            lines.append(f"    {model}: {usage['calls']} calls, {usage['input']:,}+{usage['output']:,} tokens")
    return "\n".join(lines)


def _cmd_keybindings(args: str, ctx: dict) -> str:
    """Show keyboard shortcuts."""
    return """Keyboard Shortcuts
─────────────────────────────────
  Enter          Send message
  Shift+Enter    New line in input
  Ctrl+C         Cancel current operation
  Ctrl+L         Clear screen
  Up/Down        Navigate input history
  Ctrl+/         Toggle compact mode
  Escape         Close dialogs
"""


def _cmd_statusline(args: str, ctx: dict) -> str:
    """Toggle status line display."""
    engine = ctx.get("engine")
    if not engine:
        return "Engine not available."
    current = getattr(engine, '_statusline_visible', True)
    engine._statusline_visible = not current
    return f"Status line {'hidden' if current else 'shown'}."


def _cmd_sandbox_toggle(args: str, ctx: dict) -> str:
    """Toggle sandbox mode."""
    engine = ctx.get("engine")
    if not engine:
        return "Engine not available."
    current = getattr(engine, '_sandbox_enabled', False)
    engine._sandbox_enabled = not current
    state = "enabled" if not current else "disabled"
    return f"Sandbox mode {state}. Tool execution will {'be restricted' if not current else 'run normally'}."


def _cmd_passes(args: str, ctx: dict) -> str:
    """Set multi-pass execution count."""
    engine = ctx.get("engine")
    count = args.strip()
    if not count:
        current = getattr(engine, '_max_passes', 1) if engine else 1
        return f"Current multi-pass count: {current}. Usage: /passes <count>"
    try:
        n = int(count)
        if n < 1 or n > 10:
            return "Pass count must be 1-10."
        if engine:
            engine._max_passes = n
        return f"Multi-pass count set to {n}."
    except ValueError:
        return "Invalid count. Usage: /passes <number>"


def _cmd_btw(args: str, ctx: dict) -> str:
    """Add a note without triggering AI response (CC: /btw)."""
    note = args.strip()
    if not note:
        return "Usage: /btw <note>"
    engine = ctx.get("engine")
    if engine and hasattr(engine, '_conversation'):
        engine._conversation._messages.append({
            "role": "user",
            "content": f"[Note: {note}]",
            "timestamp": __import__('time').time(),
            "virtual": True,  # won't be sent to API
        })
        engine._conversation._dirty = True
    return f"Note added: {note}"


def _cmd_thinkback(args: str, ctx: dict) -> str:
    """Show recent thinking blocks from Claude's extended thinking."""
    engine = ctx.get("engine")
    if not engine or not hasattr(engine, '_conversation'):
        return "No conversation available."
    thinking_blocks = []
    for msg in reversed(engine._conversation.messages[-20:]):
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "thinking":
                    text = block.get("thinking", "")[:500]
                    thinking_blocks.append(text)
        if len(thinking_blocks) >= 3:
            break
    if not thinking_blocks:
        return "No thinking blocks found in recent messages. Enable Extended Thinking in Settings."
    return "Recent Thinking:\n" + "\n─────\n".join(thinking_blocks)


# ── Cron commands ────────────────────────────────────────────────

def _cmd_cron_create(args: str, ctx: dict) -> str:
    """Create a scheduled cron job."""
    parts = args.strip().split(maxsplit=5)
    if len(parts) < 6:
        return (
            "Usage: /cron-create <min> <hour> <dom> <mon> <dow> <prompt>\n"
            "Example: /cron-create */5 * * * * Check for new issues"
        )
    cron_expr = " ".join(parts[:5])
    prompt = parts[5]
    engine = ctx.get("engine")
    scheduler = getattr(engine, '_cron_scheduler', None) if engine else None
    if not scheduler:
        return "Cron scheduler not available."
    try:
        job = scheduler.create(cron_expr, prompt, recurring=True, durable=True)
        return f"Cron job created: ID={job.id}, cron='{cron_expr}', prompt='{prompt[:50]}...'"
    except Exception as e:
        return f"Error creating cron job: {e}"


def _cmd_cron_list(args: str, ctx: dict) -> str:
    """List all cron jobs."""
    engine = ctx.get("engine")
    scheduler = getattr(engine, '_cron_scheduler', None) if engine else None
    if not scheduler:
        return "Cron scheduler not available."
    jobs = scheduler.list_jobs()
    if not jobs:
        return "No cron jobs scheduled."
    lines = ["Scheduled Jobs:"]
    for j in jobs:
        lines.append(f"  {j['id']} | {j['cron']} | {'recurring' if j['recurring'] else 'one-shot'} | {j['prompt'][:40]}...")
    return "\n".join(lines)


def _cmd_cron_delete(args: str, ctx: dict) -> str:
    """Delete a cron job by ID."""
    job_id = args.strip()
    if not job_id:
        return "Usage: /cron-delete <job_id>"
    engine = ctx.get("engine")
    scheduler = getattr(engine, '_cron_scheduler', None) if engine else None
    if not scheduler:
        return "Cron scheduler not available."
    if scheduler.delete(job_id):
        return f"Cron job {job_id} deleted."
    return f"Job {job_id} not found."


def _cmd_dream(args: str, ctx: dict) -> str:
    """Trigger memory consolidation (CC: Dream/AutoDream)."""
    engine = ctx.get("engine")
    dream_mgr = getattr(engine, '_dream_manager', None) if engine else None
    if not dream_mgr:
        return "Dream manager not available."
    if not dream_mgr.should_dream():
        return "Dream conditions not met (need 24h+ since last dream and 5+ sessions)."
    # Gather recent conversation summaries
    summaries = []
    if engine and hasattr(engine, '_conversation'):
        for msg in engine._conversation.messages[-30:]:
            content = msg.get("content", "")
            if isinstance(content, str) and len(content) > 50:
                summaries.append(content[:200])
    provider_fn = engine._provider.call_sync if engine and engine._provider else None
    dream_mgr.dream_async(summaries, provider_fn)
    return "Dream triggered — memory consolidation running in background."


# ═══════════════════════════════════════════════════════════════════
# Round 2: Additional Commands
# ═══════════════════════════════════════════════════════════════════

def _cmd_rewind(args: str, ctx: dict) -> str:
    """CC: /rewind — rewind conversation to a prior point."""
    engine = ctx.get("engine")
    if not engine or not hasattr(engine, '_conversation'):
        return "No conversation available."
    conv = engine._conversation
    msgs = conv.messages

    if not args.strip():
        # Show recent messages with indices
        lines = ["Recent messages (use /rewind <number> to rewind to that point):"]
        start = max(0, len(msgs) - 15)
        for i in range(start, len(msgs)):
            m = msgs[i]
            role = m.get("role", "?")
            content = str(m.get("content", ""))[:60].replace("\n", " ")
            lines.append(f"  [{i}] {role}: {content}...")
        lines.append(f"\nTotal: {len(msgs)} messages. /rewind <N> keeps first N messages.")
        return "\n".join(lines)

    try:
        n = int(args.strip())
        if n < 1 or n >= len(msgs):
            return f"Invalid index. Must be 1-{len(msgs) - 1}."
        removed = len(msgs) - n
        conv._messages = msgs[:n]
        conv._dirty = True
        conv._recalculate_token_estimate()
        return f"Rewound to message {n}. Removed {removed} messages."
    except ValueError:
        return "Usage: /rewind [number]"


def _cmd_fork(args: str, ctx: dict) -> str:
    """CC: /fork — fork conversation into a sub-agent."""
    engine = ctx.get("engine")
    if not engine:
        return "Engine not available."
    prompt = args.strip() or "Continue the current task in this forked conversation."

    # Build context from current conversation
    msgs = engine._conversation.messages[-20:]
    context_parts = []
    for m in msgs:
        role = m.get("role", "")
        content = m.get("content", "")
        if isinstance(content, str) and content.strip():
            context_parts.append(f"[{role}]: {content[:200]}")
    context = "\n".join(context_parts[-10:])

    system = (
        "You are a forked sub-agent. The parent conversation context is below.\n"
        "Continue working on the task without repeating what was already done.\n\n"
        f"## Parent Context:\n{context}"
    )

    import threading
    def _run():
        try:
            result = engine.run_sub_agent(
                system_prompt=system,
                user_prompt=prompt,
                agent_id="fork",
            )
            engine.response_text.emit(f"[Fork result]: {result}")
        except Exception as e:
            engine.error.emit(f"Fork failed: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return f"Forked conversation. Sub-agent working on: {prompt[:80]}..."


def _cmd_tag(args: str, ctx: dict) -> str:
    """CC: /tag — tag/label sessions for organization."""
    engine = ctx.get("engine")
    if not engine or not hasattr(engine, '_conversation'):
        return "No conversation available."
    conv = engine._conversation

    # Tags stored in conversation metadata
    if not hasattr(conv, '_tags'):
        conv._tags = []

    parts = args.strip().split(maxsplit=1)
    action = parts[0].lower() if parts else "list"

    if action == "add" and len(parts) > 1:
        tag = parts[1].strip()
        if tag not in conv._tags:
            conv._tags.append(tag)
            conv._dirty = True
        return f"Tag added: {tag}. Tags: {', '.join(conv._tags)}"
    elif action == "remove" and len(parts) > 1:
        tag = parts[1].strip()
        if tag in conv._tags:
            conv._tags.remove(tag)
            conv._dirty = True
            return f"Tag removed: {tag}. Tags: {', '.join(conv._tags) or '(none)'}"
        return f"Tag '{tag}' not found."
    elif action == "list" or not args.strip():
        if conv._tags:
            return f"Session tags: {', '.join(conv._tags)}"
        return "No tags. Usage: /tag add <name> | /tag remove <name> | /tag list"
    else:
        # Single word = add that tag
        tag = args.strip()
        if tag not in conv._tags:
            conv._tags.append(tag)
            conv._dirty = True
        return f"Tag added: {tag}. Tags: {', '.join(conv._tags)}"


def _cmd_workflows(args: str, ctx: dict) -> str:
    """CC: /workflows — list/manage workflows via WorkflowTool."""
    try:
        from tools.workflow_tool import _workflows
    except ImportError:
        return "WorkflowTool not available."

    action = args.strip().lower() or "list"

    if action == "list":
        if not _workflows:
            return "No active workflows. Create one with the Workflow tool."
        lines = ["Active Workflows:"]
        for name, wf in _workflows.items():
            lines.append(f"  {name}: step {wf['current']}/{len(wf['steps'])}")
            if wf['current'] < len(wf['steps']):
                lines.append(f"    Next: {wf['steps'][wf['current']]}")
        return "\n".join(lines)
    elif action.startswith("delete "):
        name = action[7:].strip()
        if _workflows.pop(name, None):
            return f"Workflow '{name}' deleted."
        return f"Workflow '{name}' not found."
    elif action.startswith("status "):
        name = action[7:].strip()
        if name not in _workflows:
            return f"Workflow '{name}' not found."
        wf = _workflows[name]
        lines = [f"Workflow: {name} ({wf['current']}/{len(wf['steps'])} steps)"]
        for i, step in enumerate(wf["steps"]):
            mark = "✅" if i < wf["current"] else ("▶" if i == wf["current"] else "⬜")
            lines.append(f"  {mark} {i+1}. {step}")
        return "\n".join(lines)
    else:
        return "Usage: /workflows [list|status <name>|delete <name>]"


def _cmd_privacy_settings(args: str, ctx: dict) -> str:
    """CC: /privacy-settings — manage data privacy preferences."""
    engine = ctx.get("engine")
    settings = {}
    try:
        from config import DATA_DIR
        import json as _json
        path = DATA_DIR / "privacy.json"
        if path.exists():
            settings = _json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass

    if not args.strip():
        lines = [
            "Privacy Settings",
            "─" * 40,
            f"  analytics_enabled:  {settings.get('analytics_enabled', True)}",
            f"  memory_enabled:     {settings.get('memory_enabled', True)}",
            f"  cost_tracking:      {settings.get('cost_tracking', True)}",
            f"  conversation_save:  {settings.get('conversation_save', True)}",
            "",
            "Usage: /privacy-settings <key>=<true|false>",
            "Example: /privacy-settings analytics_enabled=false",
        ]
        return "\n".join(lines)

    # Parse key=value
    if "=" in args:
        key, val = args.strip().split("=", 1)
        key = key.strip()
        val = val.strip().lower()
        valid_keys = {"analytics_enabled", "memory_enabled", "cost_tracking", "conversation_save"}
        if key not in valid_keys:
            return f"Unknown setting: {key}. Valid: {', '.join(valid_keys)}"
        settings[key] = val in ("true", "1", "yes")
        try:
            from config import DATA_DIR
            import json as _json
            path = DATA_DIR / "privacy.json"
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(_json.dumps(settings, indent=2), encoding="utf-8")
        except Exception as e:
            return f"Error saving: {e}"
        return f"Set {key} = {settings[key]}"
    return "Usage: /privacy-settings <key>=<true|false>"


def _cmd_reload_plugins(args: str, ctx: dict) -> str:
    """CC: /reload-plugins — hot-reload plugins without restart."""
    engine = ctx.get("engine")
    try:
        from core.services.plugins import PluginManager
        pm = PluginManager()
        before = len(pm.loaded_plugins) if hasattr(pm, 'loaded_plugins') else 0
        pm.reload()
        after = len(pm.loaded_plugins) if hasattr(pm, 'loaded_plugins') else 0
        return f"Plugins reloaded. Before: {before}, After: {after}."
    except ImportError:
        return "Plugin system not available."
    except Exception as e:
        return f"Reload failed: {e}"


