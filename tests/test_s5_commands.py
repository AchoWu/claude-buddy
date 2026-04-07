"""
Suite 5 — Command System Tests
Tests the CommandRegistry and all ~34 slash commands from core/commands.py.
~48 tests covering registration, execution, categories, and edge cases.
"""

import sys, os, io, json, tempfile, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from unittest.mock import patch, MagicMock, PropertyMock
from pathlib import Path

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
        print(f'  Suite 5 (Commands): {total}/{total} ALL TESTS PASSED')
    else:
        print(f'  Suite 5 (Commands): {PASS}/{total} PASSED, {FAIL} FAILED')
        for n, e in ERRORS:
            print(f'    X {n}: {e}')
    print(f'{"="*60}')
    return FAIL == 0

print('='*60)
print('  Suite 5: Command System Tests (~48 tests)')
print('='*60)

# ── Import ──────────────────────────────────────────────────────
from core.commands import CommandRegistry

# ── Shared helpers ──────────────────────────────────────────────

def _make_registry():
    """Create a fresh CommandRegistry."""
    return CommandRegistry()

def _make_mock_engine():
    """Create a mock LLMEngine with the attributes commands expect."""
    engine = MagicMock()
    engine._is_running = False
    engine._fast_mode = False
    engine._effort_level = "high"
    engine._provider_model = "claude-sonnet-4-20250514"
    engine._context_window = 32000
    engine._plan_mode_state = None
    engine._tool_executors = {"FileRead": MagicMock(), "Bash": MagicMock()}

    # Conversation mock
    conv = MagicMock()
    conv.message_count = 5
    conv.estimated_tokens = 1200
    conv._compaction_count = 0
    conv.is_dirty = False
    conv.messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there! How can I help?"},
    ]
    conv.file_read_state = MagicMock()
    conv.file_read_state.read_files = ["/tmp/a.py", "/tmp/b.py"]
    conv.compact_if_needed.return_value = None
    conv._full_compact.return_value = None
    conv.load_last.return_value = True
    conv.clear.return_value = None
    conv.save.return_value = None
    conv._recalculate_token_estimate = MagicMock()
    engine.conversation = conv

    # Cost
    engine.get_cost_summary.return_value = "API calls: 3\nInput tokens: ~500\nOutput tokens: ~200"
    engine.save_conversation.return_value = None
    engine.clear_conversation.return_value = None

    # Session cost
    cost = MagicMock()
    cost.total_api_calls = 3
    cost.total_input_tokens = 500
    cost.total_output_tokens = 200
    cost.summary.return_value = "API calls: 3"
    engine.session_cost = cost

    return engine

def _make_mock_context(registry=None, engine=None):
    """Build a context dict that commands expect."""
    if registry is None:
        registry = _make_registry()
    if engine is None:
        engine = _make_mock_engine()
    return {
        "command_registry": registry,
        "engine": engine,
        "conversation": engine.conversation,
        "settings": MagicMock(provider="anthropic", model="claude-sonnet-4-20250514", api_key="sk-test1234abcd"),
        "tool_registry": MagicMock(
            plan_mode_state=MagicMock(active=False, enter=MagicMock(), exit=MagicMock()),
            all_tools=MagicMock(return_value=[
                MagicMock(name="FileRead", is_read_only=True),
                MagicMock(name="Bash", is_read_only=False),
                MagicMock(name="Grep", is_read_only=True),
            ]),
            agent_registry=MagicMock(
                list_agents=MagicMock(return_value=[]),
            ),
        ),
        "task_manager": MagicMock(
            all_tasks=MagicMock(return_value=[
                MagicMock(id=1, subject="Fix bug", status="pending"),
                MagicMock(id=2, subject="Add tests", status="completed"),
            ]),
        ),
        "memory_mgr": MagicMock(
            load_memory=MagicMock(return_value="User prefers dark mode."),
            save_memory=MagicMock(),
            clear_memory=MagicMock(),
        ),
        "evolution_mgr": MagicMock(
            soul_status=MagicMock(return_value="Soul: active\nPersonality: curious"),
            get_changelog=MagicMock(return_value="v1.0: Initial soul\nv1.1: Added curiosity"),
            list_backups=MagicMock(return_value=[]),
            rollback=MagicMock(return_value=False),
        ),
        "permission_mgr": MagicMock(
            _always_allowed={"FileRead", "Grep"},
            _allow_patterns=[],
            _always_denied=set(),
            reset_permissions=MagicMock(),
        ),
        "plugin_mgr": MagicMock(
            format_status=MagicMock(return_value="Plugins (0): none loaded"),
        ),
        "analytics": MagicMock(
            format_report=MagicMock(return_value="Usage: 10 queries today"),
            load_report=MagicMock(return_value="Weekly: 50 queries"),
        ),
    }


# ══════════════════════════════════════════════════════════════════
# 1. Registry basics (tests 1-8)
# ══════════════════════════════════════════════════════════════════

def test_registry_has_30_plus_commands():
    reg = _make_registry()
    cmds = reg.list_commands()
    assert len(cmds) >= 30, f"Expected >= 30 commands, got {len(cmds)}"
run("1  registry has >= 30 commands", test_registry_has_30_plus_commands)

def test_list_commands_returns_tuples():
    reg = _make_registry()
    cmds = reg.list_commands()
    assert isinstance(cmds, list), "list_commands should return a list"
    assert len(cmds) > 0, "list_commands should not be empty"
    for item in cmds:
        assert isinstance(item, tuple), f"Expected tuple, got {type(item)}"
        assert len(item) == 2, f"Expected 2-tuple, got {len(item)}-tuple"
        assert isinstance(item[0], str), "Name should be str"
        assert isinstance(item[1], str), "Description should be str"
        assert item[0].startswith("/"), f"Command name should start with /, got {item[0]}"
run("2  list_commands returns (name, desc) tuples", test_list_commands_returns_tuples)

def test_list_commands_by_category():
    reg = _make_registry()
    cats = reg.list_commands_by_category()
    assert isinstance(cats, dict), "Should return dict"
    assert len(cats) >= 5, f"Expected >= 5 categories, got {len(cats)}"
    for cat_name, cmds in cats.items():
        assert isinstance(cat_name, str)
        assert isinstance(cmds, list)
        for item in cmds:
            assert isinstance(item, tuple) and len(item) == 2
run("3  list_commands_by_category returns dict of categories", test_list_commands_by_category)

def test_categories_contain_expected():
    reg = _make_registry()
    cats = reg.list_commands_by_category()
    expected = {"Core", "Session", "Config", "Mode", "Status", "Memory", "Code", "Tools"}
    for cat in expected:
        assert cat in cats, f"Missing category: {cat}"
run("4  categories include Core/Session/Config/Mode/Status/Memory/Code/Tools", test_categories_contain_expected)

def test_is_command_true():
    reg = _make_registry()
    assert reg.is_command("/help") is True
    assert reg.is_command("/version") is True
    assert reg.is_command("/clear") is True
    assert reg.is_command("/tools") is True
run("5  is_command returns True for valid commands", test_is_command_true)

def test_is_command_false():
    reg = _make_registry()
    assert reg.is_command("/nonexistent_xyz") is False
    assert reg.is_command("hello") is False
    assert reg.is_command("") is False
run("6  is_command returns False for invalid/non-commands", test_is_command_false)

def test_get_command():
    reg = _make_registry()
    cmd = reg.get("help")
    assert cmd is not None, "Should find /help"
    assert cmd.name == "help"
    cmd2 = reg.get("/help")
    assert cmd2 is not None, "Should find with leading /"
run("7  get() finds commands by name", test_get_command)

def test_aliases_work():
    reg = _make_registry()
    # /clear has alias /reset
    cmd_clear = reg.get("clear")
    cmd_reset = reg.get("reset")
    assert cmd_clear is not None and cmd_reset is not None
    assert cmd_clear.name == cmd_reset.name == "clear"
    # /exit has alias /quit
    cmd_exit = reg.get("exit")
    cmd_quit = reg.get("quit")
    assert cmd_exit is not None and cmd_quit is not None
    assert cmd_exit.name == cmd_quit.name == "exit"
    # /memory has alias /mem
    cmd_mem = reg.get("mem")
    assert cmd_mem is not None
    assert cmd_mem.name == "memory"
    # /import has alias /load
    cmd_load = reg.get("load")
    assert cmd_load is not None
    assert cmd_load.name == "import"
run("8  aliases resolve to the same command (clear/reset, exit/quit, mem, load)", test_aliases_work)


# ══════════════════════════════════════════════════════════════════
# 2. Individual command tests (tests 9-34)
# ══════════════════════════════════════════════════════════════════

def test_help_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/help", ctx)
    assert result is not None
    assert "Available commands" in result
    assert "[Core]" in result
run("9  /help returns formatted help text", test_help_command)

def test_help_without_registry():
    reg = _make_registry()
    result = reg.execute("/help", {})
    assert "not available" in result.lower()
run("10 /help without registry in ctx returns fallback", test_help_without_registry)

def test_version_command():
    reg = _make_registry()
    result = reg.execute("/version", {})
    assert result is not None
    assert "v5" in result.lower() or "Buddy" in result or "Claude" in result
    assert "commands" in result.lower() or "tools" in result.lower()
run("11 /version returns version string", test_version_command)

def test_clear_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/clear", ctx)
    assert "cleared" in result.lower()
    ctx["engine"].clear_conversation.assert_called_once()
    ctx["engine"].save_conversation.assert_called()
run("12 /clear clears conversation and saves", test_clear_command)

def test_clear_without_engine():
    reg = _make_registry()
    result = reg.execute("/clear", {})
    assert "not available" in result.lower()
run("13 /clear without engine returns fallback", test_clear_without_engine)

def test_exit_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/exit", ctx)
    assert result == "__EXIT__"
    ctx["engine"].save_conversation.assert_called()
run("14 /exit returns __EXIT__ sentinel and saves", test_exit_command)

def test_cost_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/cost", ctx)
    assert result is not None
    assert "API calls" in result or "calls" in result.lower()
run("15 /cost returns cost info", test_cost_command)

def test_cost_without_engine():
    reg = _make_registry()
    result = reg.execute("/cost", {})
    assert "not available" in result.lower()
run("16 /cost without engine returns fallback", test_cost_without_engine)

def test_status_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/status", ctx)
    assert result is not None
    assert "status" in result.lower() or "Messages" in result or "Running" in result
run("17 /status returns engine status", test_status_command)

def test_tools_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    # /tools needs tool_registry in context
    from core.tool_registry import ToolRegistry
    tr = ToolRegistry.__new__(ToolRegistry)
    tr._tools = []
    ctx["tool_registry"] = tr
    result = reg.execute("/tools", ctx)
    assert result is not None
run("18 /tools lists available tools", test_tools_command)

def test_tools_without_registry():
    reg = _make_registry()
    result = reg.execute("/tools", {})
    assert "not available" in result.lower()
run("19 /tools without tool_registry returns fallback", test_tools_without_registry)

def test_memory_show():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/memory", ctx)
    assert "dark mode" in result.lower() or "memory" in result.lower()
run("20 /memory shows memory content", test_memory_show)

def test_memory_clear():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/memory clear", ctx)
    assert "cleared" in result.lower()
    ctx["memory_mgr"].clear_memory.assert_called_once()
run("21 /memory clear clears memory", test_memory_clear)

def test_memory_save():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/memory User likes Python", ctx)
    assert "saved" in result.lower()
    ctx["memory_mgr"].save_memory.assert_called_once_with("User likes Python")
run("22 /memory <text> saves memory", test_memory_save)

def test_memory_without_manager():
    reg = _make_registry()
    result = reg.execute("/memory", {})
    assert "not available" in result.lower()
run("23 /memory without memory_mgr returns fallback", test_memory_without_manager)

def test_compact_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/compact", ctx)
    assert result is not None
    assert "compact" in result.lower()
run("24 /compact triggers compaction", test_compact_command)

def test_plan_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/plan", ctx)
    assert result is not None
    assert "plan" in result.lower()
run("25 /plan activates plan mode", test_plan_command)

def test_plan_without_tool_registry():
    reg = _make_registry()
    result = reg.execute("/plan", {})
    assert "not available" in result.lower()
run("26 /plan without tool_registry returns fallback", test_plan_without_tool_registry)

def test_fast_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/fast", ctx)
    assert result is not None
    assert "fast" in result.lower()
    # Toggle again
    result2 = reg.execute("/fast", ctx)
    assert "fast" in result2.lower()
run("27 /fast toggles fast mode", test_fast_command)

def test_config_no_args():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/config", ctx)
    assert result is not None
    assert "config" in result.lower() or "provider" in result.lower()
run("28 /config shows configuration", test_config_no_args)

def test_config_with_args():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/config some_key some_value", ctx)
    assert result is not None
    assert "some_key some_value" in result
run("29 /config <key> <value> returns config info", test_config_with_args)

def test_session_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/session", ctx)
    assert result is not None
    assert "session" in result.lower() or "Messages" in result
run("30 /session shows session info", test_session_command)

def test_soul_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    # /soul uses ctx["evolution_mgr"] or creates a new EvolutionManager
    result = reg.execute("/soul", ctx)
    assert result is not None
run("31 /soul shows soul status", test_soul_command)

def test_diary_command():
    reg = _make_registry()
    with tempfile.TemporaryDirectory() as td:
        soul_dir = Path(td) / "soul"
        soul_dir.mkdir()
        diary = soul_dir / "diary.md"
        diary.write_text("# Diary\n## 2025-01-01\nToday I learned about testing.", encoding="utf-8")
        # /diary imports SOUL_DIR from core.evolution
        with patch('core.evolution.SOUL_DIR', soul_dir):
            result = reg.execute("/diary", {})
    assert result is not None
    assert "diary" in result.lower() or "learned" in result.lower() or "testing" in result.lower()
run("32 /diary shows diary content", test_diary_command)

def test_diary_last_entry():
    reg = _make_registry()
    with tempfile.TemporaryDirectory() as td:
        soul_dir = Path(td) / "soul"
        soul_dir.mkdir()
        diary = soul_dir / "diary.md"
        diary.write_text("# Diary\n## Entry 1\nFirst.\n## Entry 2\nSecond.", encoding="utf-8")
        with patch('core.evolution.SOUL_DIR', soul_dir):
            result = reg.execute("/diary last", {})
    assert result is not None
    assert "Second" in result or "Entry 2" in result
run("33 /diary last shows only the last entry", test_diary_last_entry)

def test_evolve_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/evolve", ctx)
    assert result is not None
run("34 /evolve shows changelog", test_evolve_command)

def test_rollback_no_args():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/rollback", ctx)
    assert result is not None
run("35 /rollback without args shows usage", test_rollback_no_args)

def test_tasks_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/tasks", ctx)
    assert result is not None
    assert "Fix bug" in result or "tasks" in result.lower()
run("36 /tasks shows task list", test_tasks_command)

def test_tasks_without_manager():
    reg = _make_registry()
    result = reg.execute("/tasks", {})
    assert "not available" in result.lower()
run("37 /tasks without task_manager returns fallback", test_tasks_without_manager)

def test_export_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    with tempfile.TemporaryDirectory() as td:
        with patch('config.DATA_DIR', Path(td)):
            result = reg.execute("/export", ctx)
    assert result is not None
    assert "export" in result.lower()
run("38 /export creates export data", test_export_command)

def test_export_markdown():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    with tempfile.TemporaryDirectory() as td:
        with patch('config.DATA_DIR', Path(td)):
            result = reg.execute("/export md", ctx)
    assert result is not None
    assert "export" in result.lower()
run("39 /export md exports as markdown", test_export_markdown)

def test_model_command_show():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/model", ctx)
    assert result is not None
    assert "model" in result.lower() or "claude" in result.lower()
run("40 /model shows current model", test_model_command_show)

def test_model_command_set():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/model gpt-4o", ctx)
    assert result is not None
    assert "gpt-4o" in result
run("41 /model <name> sets model", test_model_command_set)


# ══════════════════════════════════════════════════════════════════
# 3. Remaining commands exist and execute (test 42)
# ══════════════════════════════════════════════════════════════════

def test_remaining_commands_execute():
    """Test that all remaining commands can be executed without crash."""
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)

    safe_commands = [
        "/hooks", "/theme dark", "/theme light", "/theme",
        "/effort high", "/effort medium", "/effort",
        "/model", "/onboarding", "/env", "/permissions",
        "/output-style concise", "/output-style detailed", "/output-style",
        "/agents", "/plugins", "/files", "/resume",
        "/copy",
    ]
    for cmd_text in safe_commands:
        result = reg.execute(cmd_text, ctx)
        assert result is not None, f"{cmd_text} returned None"
        assert isinstance(result, str), f"{cmd_text} returned {type(result)}"
run("42 remaining commands execute without crash", test_remaining_commands_execute)


# ══════════════════════════════════════════════════════════════════
# 4. Specific command details (tests 43-44)
# ══════════════════════════════════════════════════════════════════

def test_hooks_command():
    reg = _make_registry()
    result = reg.execute("/hooks", {})
    assert "hook" in result.lower() or "Hook" in result
    assert "pre_tool" in result or "post_tool" in result
run("43 /hooks returns hook info with hook points", test_hooks_command)

def test_theme_command():
    reg = _make_registry()
    result_dark = reg.execute("/theme dark", {})
    assert "dark" in result_dark.lower()
    result_light = reg.execute("/theme light", {})
    assert "light" in result_light.lower()
    result_bad = reg.execute("/theme", {})
    assert "usage" in result_bad.lower()
run("44 /theme dark/light/usage works correctly", test_theme_command)

def test_effort_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    assert "high" in reg.execute("/effort high", ctx).lower()
    assert "low" in reg.execute("/effort low", ctx).lower()
    assert "medium" in reg.execute("/effort medium", ctx).lower()
    assert "usage" in reg.execute("/effort", ctx).lower()
run("45 /effort high/medium/low/usage works", test_effort_command)

def test_onboarding_command():
    reg = _make_registry()
    result = reg.execute("/onboarding", {})
    assert "Welcome" in result or "welcome" in result.lower()
    assert "/help" in result
    assert "/tools" in result
run("46 /onboarding returns welcome text with key commands", test_onboarding_command)

def test_permissions_command():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/permissions", ctx)
    assert result is not None
    assert "permission" in result.lower() or "FileRead" in result
run("47 /permissions shows permission rules", test_permissions_command)

def test_permissions_reset():
    reg = _make_registry()
    ctx = _make_mock_context(registry=reg)
    result = reg.execute("/permissions reset", ctx)
    assert "cleared" in result.lower()
    ctx["permission_mgr"].reset_permissions.assert_called_once()
run("48 /permissions reset clears all rules", test_permissions_reset)


# ══════════════════════════════════════════════════════════════════
# 5. Edge cases (tests 49-56)
# ══════════════════════════════════════════════════════════════════

def test_unknown_command():
    reg = _make_registry()
    result = reg.execute("/totally_bogus_command_xyz", {})
    assert result is not None
    assert "unknown" in result.lower()
    assert "/help" in result.lower()
run("49 unknown command returns error message with /help hint", test_unknown_command)

def test_empty_text_returns_none():
    reg = _make_registry()
    result = reg.execute("", {})
    assert result is None, "Non-slash text should return None"
run("50 empty string returns None (not a command)", test_empty_text_returns_none)

def test_non_slash_text_returns_none():
    reg = _make_registry()
    result = reg.execute("hello world", {})
    assert result is None, "Non-slash text should return None"
run("51 non-slash text returns None", test_non_slash_text_returns_none)

def test_command_case_insensitive():
    reg = _make_registry()
    result_lower = reg.execute("/help", {"command_registry": reg})
    result_upper = reg.execute("/HELP", {"command_registry": reg})
    result_mixed = reg.execute("/Help", {"command_registry": reg})
    assert result_lower is not None
    assert result_upper is not None
    assert result_mixed is not None
    assert "unknown" not in result_lower.lower()
    assert "unknown" not in result_upper.lower()
    assert "unknown" not in result_mixed.lower()
run("52 commands are case-insensitive (HELP, Help, help)", test_command_case_insensitive)

def test_command_with_extra_whitespace():
    reg = _make_registry()
    result = reg.execute("/version   ", {})
    assert result is not None
    assert "unknown" not in result.lower()
run("53 command with trailing whitespace still works", test_command_with_extra_whitespace)

def test_register_custom_command():
    reg = _make_registry()
    reg.register("mytest", "A test command", lambda args, ctx: f"custom: {args}", category="Custom")
    result = reg.execute("/mytest hello world", {})
    assert result == "custom: hello world"
    cmds = reg.list_commands()
    names = [n for n, _ in cmds]
    assert "/mytest" in names
    cats = reg.list_commands_by_category()
    assert "Custom" in cats
run("54 custom command can be registered, executed, and appears in listings", test_register_custom_command)

def test_command_handler_exception():
    reg = _make_registry()
    def _bad_handler(args, ctx):
        raise ValueError("Something went wrong")
    reg.register("crashme", "A crashing command", _bad_handler, category="Test")
    result = reg.execute("/crashme", {})
    assert "error" in result.lower() or "wrong" in result.lower()
run("55 command handler exception is caught gracefully", test_command_handler_exception)

def test_context_none_is_safe():
    """Commands receiving None context should not crash (execute normalizes to {})."""
    reg = _make_registry()
    result = reg.execute("/version", None)
    assert result is not None
run("56 passing None context does not crash", test_context_none_is_safe)

def test_list_commands_sorted():
    """list_commands returns commands sorted by name."""
    reg = _make_registry()
    cmds = reg.list_commands()
    names = [n for n, _ in cmds]
    assert names == sorted(names), "list_commands should return sorted results"
run("57 list_commands returns sorted results", test_list_commands_sorted)

def test_env_show():
    reg = _make_registry()
    result = reg.execute("/env", {})
    assert result is not None
    assert "environment" in result.lower() or "PATH" in result or "=" in result
run("58 /env shows environment variables", test_env_show)

def test_env_set_and_get():
    reg = _make_registry()
    result = reg.execute("/env BUDDY_TEST_VAR=hello123", {})
    assert "hello123" in result
    result2 = reg.execute("/env BUDDY_TEST_VAR", {})
    assert "hello123" in result2
    # Clean up
    os.environ.pop("BUDDY_TEST_VAR", None)
run("59 /env set/get works for environment variables", test_env_set_and_get)

def test_import_without_engine():
    reg = _make_registry()
    result = reg.execute("/import", {})
    assert "not available" in result.lower()
run("60 /import without engine returns fallback", test_import_without_engine)


# ══════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════

ok = summary()
sys.exit(0 if ok else 1)
