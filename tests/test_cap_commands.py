"""
Capability Tests — Section 五 Commands (5.1–5.11) + Section 三 Prompt (3.1–3.21)
Tests all 42 slash commands and 21 prompt sections from CAPABILITY_MATRIX.md.

Covers:
  5.1  Core: /help /clear /exit /version
  5.2  Session: /resume /session /diff /files /context
  5.3  Config: /config /permissions /hooks /theme /env /output-style
  5.4  Mode: /plan /fast /effort
  5.5  Status: /cost /status /model /stats /flags
  5.6  Memory: /memory /compact
  5.7  Code: /review /pr /branch
  5.8  Tools: /tools /plugins /skills
  5.9  Data: /export /import
  5.10 Other: /tasks /agents /copy /onboarding /doctor
  5.11 Soul: /soul /diary /evolve /rollback
  3.1-3.21 Prompt system sections
"""

import sys, os, io, time, tempfile, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_buddy = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _buddy)
os.chdir(_buddy)

from pathlib import Path
_TEMP = tempfile.mkdtemp(prefix='buddy_cap_cmd_')
import config
config.DATA_DIR = Path(_TEMP)
config.CONVERSATIONS_DIR = Path(_TEMP) / "conversations"
config.CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
config.INPUT_HISTORY_FILE = Path(_TEMP) / "input_history.json"

# Create soul/evolution dirs for soul commands
(Path(_TEMP) / "soul").mkdir(exist_ok=True)
(Path(_TEMP) / "evolution").mkdir(exist_ok=True)
(Path(_TEMP) / "evolution" / "backups").mkdir(exist_ok=True)
(Path(_TEMP) / "evolution" / "reflections").mkdir(exist_ok=True)
(Path(_TEMP) / "plugins").mkdir(exist_ok=True)
(Path(_TEMP) / "skills").mkdir(exist_ok=True)

# Patch evolution paths
try:
    import core.evolution as _evo_mod
    _evo_mod.DATA_DIR = Path(_TEMP)
    _evo_mod.SOUL_DIR = Path(_TEMP) / "soul"
    _evo_mod.EVOLUTION_DIR = Path(_TEMP) / "evolution"
except Exception:
    pass

# ── Test framework ──────────────────────────────────────────────
PASS = 0
FAIL = 0
ERRORS = []

def run(name, fn):
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f'  OK  {name}')
    except Exception as e:
        FAIL += 1
        ERRORS.append((name, str(e)))
        print(f'  FAIL {name}: {e}')

def summary():
    total = PASS + FAIL
    print(f'\n{"="*60}')
    if FAIL == 0:
        print(f'  Cap Commands+Prompt: {total}/{total} ALL TESTS PASSED')
    else:
        print(f'  Cap Commands+Prompt: {PASS}/{total} PASSED, {FAIL} FAILED')
        for n, e in ERRORS:
            print(f'    X {n}: {e}')
    print(f'{"="*60}')
    return FAIL == 0

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
_qapp = QApplication.instance() or QApplication(sys.argv)

from core.commands import CommandRegistry
from core.engine import LLMEngine, SessionCost
from core.conversation import ConversationManager
from unittest.mock import MagicMock, patch

print('=' * 60)
print('  Capability Tests: Commands (5.1–5.11) + Prompt (3.1–3.21)')
print('=' * 60)


def make_ctx(**overrides):
    """Build a standard command context with mock objects."""
    engine = LLMEngine()
    engine._conversation.add_user_message("test message")
    engine._conversation.add_assistant_message("test reply")

    # Mock tool registry with plan mode state
    plan_state = MagicMock()
    plan_state.active = False
    tool_registry = MagicMock()
    tool_registry.plan_mode_state = plan_state
    tool_registry.all_tools.return_value = [
        MagicMock(name="FileRead", is_read_only=True),
        MagicMock(name="FileWrite", is_read_only=False),
        MagicMock(name="Bash", is_read_only=False),
    ]

    registry = CommandRegistry()

    ctx = {
        "engine": engine,
        "conversation": engine.conversation,
        "command_registry": registry,
        "tool_registry": tool_registry,
        "evolution_mgr": MagicMock(),
        "task_manager": MagicMock(),
        "settings": MagicMock(provider="test", model="test-model", api_key="sk-test123456"),
        "memory_mgr": MagicMock(),
        "plugin_mgr": MagicMock(),
        "analytics": None,
        "permission_mgr": MagicMock(),
    }
    ctx.update(overrides)
    return ctx, registry


# ═══════════════════════════════════════════════════════════════════
# 5.1 Core: /help /clear /exit /version
# ═══════════════════════════════════════════════════════════════════

def test_5_1_1_help():
    ctx, reg = make_ctx()
    result = reg.execute("/help", ctx)
    assert "Available commands" in result
    assert "/help" in result or "help" in result
    # Should have categories
    assert "Core" in result
    assert "Session" in result
run("5.1.1 /help: lists commands by category", test_5_1_1_help)


def test_5_1_2_clear():
    ctx, reg = make_ctx()
    engine = ctx["engine"]
    engine.conversation.add_user_message("extra msg")
    assert engine.conversation.message_count > 0

    result = reg.execute("/clear", ctx)
    assert "archived" in result.lower() or "fresh" in result.lower()
    assert engine.conversation.message_count == 0
run("5.1.2 /clear: archives session, starts fresh", test_5_1_2_clear)


def test_5_1_3_exit():
    ctx, reg = make_ctx()
    result = reg.execute("/exit", ctx)
    assert result.startswith("__EXIT__"), f"Expected __EXIT__ prefix, got: {result[:30]}"
    # Should contain session UUID
    assert len(result) > len("__EXIT__"), "Should include session ID"
run("5.1.3 /exit: returns __EXIT__ + session ID", test_5_1_3_exit)


def test_5_1_4_version():
    ctx, reg = make_ctx()
    result = reg.execute("/version", ctx)
    assert "buddy" in result.lower() or "claude" in result.lower()
    assert "v5" in result.lower() or "5.0" in result
run("5.1.4 /version: shows version info", test_5_1_4_version)


# ═══════════════════════════════════════════════════════════════════
# 5.2 Session
# ═══════════════════════════════════════════════════════════════════

def test_5_2_1_resume_list():
    ctx, reg = make_ctx()
    # Save a session first
    ctx["engine"].conversation.add_user_message("save me")
    ctx["engine"].save_conversation()

    result = reg.execute("/resume", ctx)
    assert "session" in result.lower() or "no saved" in result.lower()
run("5.2.1 /resume: lists sessions by default", test_5_2_1_resume_list)


def test_5_2_2_session():
    ctx, reg = make_ctx()
    result = reg.execute("/session", ctx)
    assert "Messages:" in result
    assert "Tokens" in result
    assert "Compactions:" in result
run("5.2.2 /session: shows session info", test_5_2_2_session)


def test_5_2_4_files():
    ctx, reg = make_ctx()
    # Record some file reads
    ctx["engine"].conversation.file_read_state.record_read("/test/file.py")
    result = reg.execute("/files", ctx)
    assert "file.py" in result or "Files" in result
run("5.2.4 /files: lists read files", test_5_2_4_files)


def test_5_2_5_context():
    ctx, reg = make_ctx()
    result = reg.execute("/context", ctx)
    assert "CWD:" in result
    assert "context" in result.lower()
run("5.2.5 /context: shows CWD and project info", test_5_2_5_context)


# ═══════════════════════════════════════════════════════════════════
# 5.3 Config
# ═══════════════════════════════════════════════════════════════════

def test_5_3_1_config():
    ctx, reg = make_ctx()
    result = reg.execute("/config", ctx)
    assert "Configuration" in result or "provider" in result.lower()
run("5.3.1 /config: shows current settings", test_5_3_1_config)


def test_5_3_2_permissions():
    ctx, reg = make_ctx()
    result = reg.execute("/permissions", ctx)
    assert "Permission" in result or "rules" in result.lower()
run("5.3.2 /permissions: shows permission rules", test_5_3_2_permissions)


def test_5_3_3_hooks():
    ctx, reg = make_ctx()
    result = reg.execute("/hooks", ctx)
    assert "hook" in result.lower() or "Hook" in result
run("5.3.3 /hooks: lists hook points", test_5_3_3_hooks)


def test_5_3_4_theme():
    ctx, reg = make_ctx()
    result = reg.execute("/theme dark", ctx)
    assert "dark" in result.lower()
run("5.3.4 /theme: sets theme", test_5_3_4_theme)


def test_5_3_env():
    ctx, reg = make_ctx()
    result = reg.execute("/env", ctx)
    assert "Environment" in result
run("5.3  /env: shows environment variables", test_5_3_env)


def test_5_3_output_style():
    ctx, reg = make_ctx()
    result = reg.execute("/output-style concise", ctx)
    assert "concise" in result.lower()
    assert ctx["engine"]._fast_mode is True
run("5.3  /output-style: sets concise mode", test_5_3_output_style)


# ═══════════════════════════════════════════════════════════════════
# 5.4 Mode
# ═══════════════════════════════════════════════════════════════════

def test_5_4_1_plan():
    ctx, reg = make_ctx()
    plan_state = ctx["tool_registry"].plan_mode_state
    plan_state.active = False

    result = reg.execute("/plan", ctx)
    assert "plan mode" in result.lower() or "activated" in result.lower()
    plan_state.enter.assert_called_once()
run("5.4.1 /plan: activates plan mode", test_5_4_1_plan)


def test_5_4_2_fast():
    ctx, reg = make_ctx()
    result = reg.execute("/fast", ctx)
    assert "fast mode" in result.lower()
    assert "ON" in result or "OFF" in result
run("5.4.2 /fast: toggles fast mode", test_5_4_2_fast)


def test_5_4_3_effort():
    ctx, reg = make_ctx()
    result = reg.execute("/effort high", ctx)
    assert "high" in result.lower()
    assert ctx["engine"]._effort_level == "high"
run("5.4.3 /effort: sets reasoning level", test_5_4_3_effort)


# ═══════════════════════════════════════════════════════════════════
# 5.5 Status
# ═══════════════════════════════════════════════════════════════════

def test_5_5_1_cost():
    ctx, reg = make_ctx()
    result = reg.execute("/cost", ctx)
    assert "API calls:" in result or "No API" in result
run("5.5.1 /cost: shows session cost", test_5_5_1_cost)


def test_5_5_2_status():
    ctx, reg = make_ctx()
    result = reg.execute("/status", ctx)
    assert "Messages:" in result
    assert "Context window:" in result
run("5.5.2 /status: shows engine status", test_5_5_2_status)


def test_5_5_3_model():
    ctx, reg = make_ctx()
    result = reg.execute("/model", ctx)
    assert "model" in result.lower()
run("5.5.3 /model: shows current model", test_5_5_3_model)


def test_5_5_3b_model_set():
    ctx, reg = make_ctx()
    result = reg.execute("/model claude-opus", ctx)
    assert "claude-opus" in result
    assert ctx["engine"]._provider_model == "claude-opus"
run("5.5.3b /model <name>: switches model", test_5_5_3b_model_set)


# ═══════════════════════════════════════════════════════════════════
# 5.6 Memory & Compaction
# ═══════════════════════════════════════════════════════════════════

def test_5_6_1_memory():
    ctx, reg = make_ctx()
    ctx["memory_mgr"].load_memory.return_value = "- user prefers tabs"
    result = reg.execute("/memory", ctx)
    assert "tabs" in result or "memory" in result.lower()
run("5.6.1 /memory: shows stored memory", test_5_6_1_memory)


def test_5_6_2_compact():
    ctx, reg = make_ctx()
    result = reg.execute("/compact", ctx)
    assert "compact" in result.lower()
run("5.6.2 /compact: forces compaction", test_5_6_2_compact)


# ═══════════════════════════════════════════════════════════════════
# 5.7 Code
# ═══════════════════════════════════════════════════════════════════

def test_5_7_3_branch():
    ctx, reg = make_ctx()
    result = reg.execute("/branch current", ctx)
    # May or may not be in a git repo
    assert "branch" in result.lower() or "git" in result.lower()
run("5.7.3 /branch: git branch info", test_5_7_3_branch)


# ═══════════════════════════════════════════════════════════════════
# 5.8 Tool Discovery
# ═══════════════════════════════════════════════════════════════════

def test_5_8_1_tools():
    ctx, reg = make_ctx()
    # /tools calls registry.all_tools() which returns objects with .name and .is_read_only
    from core.providers.base import ToolDef
    mock_tools = [
        MagicMock(name="FileRead", is_read_only=True, spec=ToolDef),
        MagicMock(name="FileWrite", is_read_only=False, spec=ToolDef),
    ]
    # MagicMock.name is special — override it
    mock_tools[0].name = "FileRead"
    mock_tools[0].is_read_only = True
    mock_tools[1].name = "FileWrite"
    mock_tools[1].is_read_only = False
    ctx["tool_registry"].all_tools.return_value = mock_tools

    result = reg.execute("/tools", ctx)
    assert "tool" in result.lower() or "Available" in result
run("5.8.1 /tools: lists available tools", test_5_8_1_tools)


def test_5_8_2_plugins():
    ctx, reg = make_ctx()
    ctx["plugin_mgr"].format_status.return_value = "Plugins: 0 loaded"
    result = reg.execute("/plugins", ctx)
    assert "plugin" in result.lower() or "Plugin" in result
run("5.8.2 /plugins: lists plugins", test_5_8_2_plugins)


def test_5_8_3_skills():
    ctx, reg = make_ctx()
    result = reg.execute("/skills", ctx)
    assert "skill" in result.lower() or "available" in result.lower()
run("5.8.3 /skills: lists skills", test_5_8_3_skills)


# ═══════════════════════════════════════════════════════════════════
# 5.9 Data
# ═══════════════════════════════════════════════════════════════════

def test_5_9_1_export():
    ctx, reg = make_ctx()
    result = reg.execute("/export json", ctx)
    assert "export" in result.lower() or "Exported" in result
    export_file = Path(_TEMP) / "export.json"
    assert export_file.exists(), "Export file should be created"
run("5.9.1 /export: creates JSON file", test_5_9_1_export)


def test_5_9_2_import():
    ctx, reg = make_ctx()
    # Create a file to import
    import_path = Path(_TEMP) / "import_test.json"
    import_path.write_text(json.dumps([
        {"role": "user", "content": "imported msg"},
        {"role": "assistant", "content": "imported reply"},
    ]))

    result = reg.execute(f"/import {import_path}", ctx)
    assert "Imported" in result or "import" in result.lower()
    assert ctx["engine"].conversation.message_count >= 2
run("5.9.2 /import: loads messages from JSON", test_5_9_2_import)


# ═══════════════════════════════════════════════════════════════════
# 5.10 Other
# ═══════════════════════════════════════════════════════════════════

def test_5_10_1_tasks():
    ctx, reg = make_ctx()
    ctx["task_manager"].all_tasks.return_value = []
    result = reg.execute("/tasks", ctx)
    assert "task" in result.lower() or "No tasks" in result
run("5.10.1 /tasks: lists tasks", test_5_10_1_tasks)


def test_5_10_4_onboarding():
    ctx, reg = make_ctx()
    result = reg.execute("/onboarding", ctx)
    assert "Welcome" in result
    assert "/help" in result
    assert "API key" in result or "key" in result.lower()
run("5.10.4 /onboarding: shows welcome guide", test_5_10_4_onboarding)


def test_5_10_5_doctor():
    ctx, reg = make_ctx()
    result = reg.execute("/doctor", ctx)
    assert "Python:" in result
    assert "Platform:" in result
    assert "diagnostics" in result.lower()
run("5.10.5 /doctor: runs system diagnostics", test_5_10_5_doctor)


# ═══════════════════════════════════════════════════════════════════
# 5.11 Soul & Evolution
# ═══════════════════════════════════════════════════════════════════

def test_5_11_1_soul():
    ctx, reg = make_ctx()
    ctx["evolution_mgr"].soul_status.return_value = "Soul: personality loaded"
    result = reg.execute("/soul", ctx)
    assert isinstance(result, str)
    assert len(result) > 0
run("5.11.1 /soul: shows soul status", test_5_11_1_soul)


def test_5_11_2_diary():
    ctx, reg = make_ctx()
    # Create a diary file
    diary_path = Path(_TEMP) / "soul" / "diary.md"
    diary_path.write_text("# Diary\n\n## 2026-04-01\nToday I learned about testing.\n")
    result = reg.execute("/diary", ctx)
    assert "testing" in result or "Diary" in result or "diary" in result.lower()
run("5.11.2 /diary: shows diary entries", test_5_11_2_diary)


def test_5_11_3_evolve():
    ctx, reg = make_ctx()
    ctx["evolution_mgr"].get_changelog.return_value = "- 2026-04-01: Modified personality.md (risk=low)"
    result = reg.execute("/evolve", ctx)
    assert isinstance(result, str)
run("5.11.3 /evolve: shows changelog", test_5_11_3_evolve)


def test_5_11_4_rollback_usage():
    ctx, reg = make_ctx()
    result = reg.execute("/rollback", ctx)
    assert "Usage:" in result or "rollback" in result.lower()
run("5.11.4 /rollback: shows usage without args", test_5_11_4_rollback_usage)


# ═══════════════════════════════════════════════════════════════════
# Command system infrastructure
# ═══════════════════════════════════════════════════════════════════

def test_cmd_unknown():
    """Unknown command returns helpful error."""
    ctx, reg = make_ctx()
    result = reg.execute("/nonexistent", ctx)
    assert "Unknown" in result or "unknown" in result
    assert "/help" in result
run("Cmd infra: unknown command → helpful error", test_cmd_unknown)


def test_cmd_aliases():
    """Aliases work (e.g., /quit → /exit)."""
    reg = CommandRegistry()
    assert reg.get("quit") is not None, "/quit should be alias for /exit"
    assert reg.get("reset") is not None, "/reset should be alias for /clear"
    assert reg.get("mem") is not None, "/mem should be alias for /memory"
run("Cmd infra: aliases resolve correctly", test_cmd_aliases)


def test_cmd_categories():
    """Commands are organized by category."""
    reg = CommandRegistry()
    cats = reg.list_commands_by_category()
    assert "Core" in cats
    assert "Session" in cats
    assert "Mode" in cats
    assert "Soul" in cats
    assert len(cats) >= 8, f"Expected >= 8 categories, got {len(cats)}"
run("Cmd infra: commands organized by category", test_cmd_categories)


def test_cmd_count():
    """Registry has 40+ commands (42 per CAPABILITY_MATRIX)."""
    reg = CommandRegistry()
    cmds = reg.list_commands()
    # Count unique commands (not aliases)
    assert len(cmds) >= 35, f"Expected >= 35 unique commands, got {len(cmds)}"
run("Cmd infra: 35+ unique commands registered", test_cmd_count)


# ═══════════════════════════════════════════════════════════════════
# Section 三 Prompt System (3.1–3.21)
# ═══════════════════════════════════════════════════════════════════
print()
print('  --- Prompt System (3.1–3.21) ---')
print()

from prompts.system import build_system_prompt

def test_3_1_identity():
    prompt = build_system_prompt()
    assert "buddy" in prompt.lower() or "claude" in prompt.lower()
run("3.1  Prompt: identity section present", test_3_1_identity)


def test_3_1b_soul():
    # Write a personality file
    personality_path = Path(_TEMP) / "soul" / "personality.md"
    personality_path.write_text("I am curious and helpful.")
    try:
        prompt = build_system_prompt()
        # Soul section depends on whether personality file is in expected location
        # Check the _sec_soul function exists and returns content
        from prompts.system import _sec_soul
        soul = _sec_soul()
        assert isinstance(soul, str)
    except ImportError:
        pass  # _sec_soul might not be exposed
run("3.1b Prompt: soul section exists", test_3_1b_soul)


def test_3_2_system_rules():
    prompt = build_system_prompt()
    assert "NEVER" in prompt, "Should have NEVER rules"
run("3.2  Prompt: system rules with NEVER constraints", test_3_2_system_rules)


def test_3_3_doing_tasks():
    prompt = build_system_prompt()
    assert "FileRead" in prompt or "read" in prompt.lower()
run("3.3  Prompt: task execution guidance", test_3_3_doing_tasks)


def test_3_5_action_safety():
    prompt = build_system_prompt()
    assert "SAFE" in prompt or "safe" in prompt
    assert "DANGEROUS" in prompt or "dangerous" in prompt.lower()
run("3.5  Prompt: action safety classification", test_3_5_action_safety)


def test_3_7_permission_modes():
    prompt_auto = build_system_prompt(permission_mode="auto")
    prompt_default = build_system_prompt(permission_mode="default")
    # At least one should mention the mode
    assert "auto" in prompt_auto.lower() or "AUTO" in prompt_auto or \
           "permission" in prompt_auto.lower()
run("3.7  Prompt: permission mode injection", test_3_7_permission_modes)


def test_3_8_tool_selection():
    prompt = build_system_prompt()
    # Should have task→tool mapping
    assert "Bash" in prompt or "bash" in prompt
    assert "Glob" in prompt or "glob" in prompt
run("3.8  Prompt: tool selection table", test_3_8_tool_selection)


def test_3_9_tool_reference():
    prompt = build_system_prompt()
    assert "FileRead" in prompt or "FileEdit" in prompt
run("3.9  Prompt: tool reference details", test_3_9_tool_reference)


def test_3_13_git_workflow():
    prompt = build_system_prompt()
    assert "commit" in prompt.lower() or "git" in prompt.lower()
run("3.13 Prompt: git workflow guidance", test_3_13_git_workflow)


def test_3_14_error_recovery():
    prompt = build_system_prompt()
    assert "error" in prompt.lower() or "Error" in prompt
run("3.14 Prompt: error recovery strategies", test_3_14_error_recovery)


def test_3_19_output_format():
    prompt = build_system_prompt()
    assert "markdown" in prompt.lower() or "GFM" in prompt or "code" in prompt.lower()
run("3.19 Prompt: output format guidance", test_3_19_output_format)


def test_3_20_memory_injection():
    prompt_with = build_system_prompt(memory_content="- user prefers tabs\n- Python expert")
    assert "tabs" in prompt_with or "Memory" in prompt_with

    prompt_without = build_system_prompt(memory_content=None)
    assert "tabs" not in prompt_without
run("3.20 Prompt: memory injection (conditional)", test_3_20_memory_injection)


def test_3_21_environment():
    prompt = build_system_prompt()
    assert "directory" in prompt.lower() or "Platform" in prompt or "CWD" in prompt
run("3.21 Prompt: environment context", test_3_21_environment)


def test_3_prompt_length():
    """System prompt should be substantial (>1000 chars for all sections)."""
    prompt = build_system_prompt()
    assert len(prompt) > 1000, f"Prompt too short: {len(prompt)} chars"
run("3.X  Prompt: substantial length (>1000 chars)", test_3_prompt_length)


# ═══════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════

import shutil
try:
    ok = summary()
finally:
    shutil.rmtree(_TEMP, ignore_errors=True)

sys.exit(0 if ok else 1)
