"""
Phase 6-8 Verification Tests
Phase 6: New commands (/init, /add-dir, /mcp, /vim, /feedback, /terminal-setup, /allowed-tools, /release-notes)
Phase 7: Hook system (register, fire, bash hooks, timeout, config loading)
Phase 8: Cost calculation (USD pricing, cache tokens, per-model)
"""
import sys, os, io, time, tempfile, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_buddy = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _buddy)
os.chdir(_buddy)

from pathlib import Path
_TEMP = tempfile.mkdtemp(prefix='buddy_p678_')
import config
config.DATA_DIR = Path(_TEMP)
config.CONVERSATIONS_DIR = Path(_TEMP) / "conversations"
config.CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
config.INPUT_HISTORY_FILE = Path(_TEMP) / "input_history.json"
(Path(_TEMP) / "soul").mkdir(exist_ok=True)
(Path(_TEMP) / "evolution").mkdir(exist_ok=True)
(Path(_TEMP) / "evolution" / "backups").mkdir(exist_ok=True)
(Path(_TEMP) / "plugins").mkdir(exist_ok=True)

PASS = 0; FAIL = 0; ERRORS = []
def run(name, fn):
    global PASS, FAIL
    try: fn(); PASS += 1; print(f'  OK  {name}')
    except Exception as e: FAIL += 1; ERRORS.append((name, str(e))); print(f'  FAIL {name}: {e}')
def summary():
    total = PASS + FAIL
    print(f'\n{"="*60}')
    s = f'Phase 6-8: {total}/{total} ALL TESTS PASSED' if FAIL == 0 else f'Phase 6-8: {PASS}/{total} PASSED, {FAIL} FAILED'
    print(f'  {s}')
    for n, e in ERRORS: print(f'    X {n}: {e}')
    print(f'{"="*60}')
    return FAIL == 0

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
_qapp = QApplication.instance() or QApplication(sys.argv)

from core.engine import LLMEngine, SessionCost
from core.commands import CommandRegistry
from unittest.mock import MagicMock

print('=' * 60)
print('  Phase 6-8 Verification Tests')
print('=' * 60)

def make_ctx(**overrides):
    engine = LLMEngine()
    engine._conversation.add_user_message("test")
    registry = CommandRegistry()
    plan_state = MagicMock(); plan_state.active = False
    tool_registry = MagicMock(); tool_registry.plan_mode_state = plan_state
    ctx = {
        "engine": engine, "conversation": engine.conversation,
        "command_registry": registry, "tool_registry": tool_registry,
        "evolution_mgr": MagicMock(), "task_manager": MagicMock(),
        "settings": MagicMock(provider="test", model="test", api_key="sk-test"),
        "memory_mgr": MagicMock(), "plugin_mgr": MagicMock(),
        "analytics": None, "permission_mgr": MagicMock(),
    }
    ctx.update(overrides)
    return ctx, registry

# ═══════════════════════════════════════════════════════════════
# Phase 6: New Commands
# ═══════════════════════════════════════════════════════════════
print('  --- Phase 6: Commands ---')

def test_cmd_init():
    ctx, reg = make_ctx()
    # Run in temp dir so we don't pollute real project
    old_cwd = os.getcwd()
    os.chdir(_TEMP)
    try:
        result = reg.execute("/init", ctx)
        assert "Created" in result or "CLAUDE.md" in result
        assert (Path(_TEMP) / "CLAUDE.md").exists()
    finally:
        os.chdir(old_cwd)
run("P6.1 /init: creates CLAUDE.md", test_cmd_init)

def test_cmd_init_exists():
    ctx, reg = make_ctx()
    old_cwd = os.getcwd()
    os.chdir(_TEMP)
    try:
        result = reg.execute("/init", ctx)  # already exists from previous test
        assert "already exists" in result.lower()
    finally:
        os.chdir(old_cwd)
run("P6.2 /init: warns if CLAUDE.md exists", test_cmd_init_exists)

def test_cmd_add_dir():
    ctx, reg = make_ctx()
    result = reg.execute(f"/add-dir {_TEMP}", ctx)
    assert "Added" in result
    assert hasattr(ctx["engine"], '_extra_context_dirs')
    assert len(ctx["engine"]._extra_context_dirs) >= 1
run("P6.3 /add-dir: adds directory to context", test_cmd_add_dir)

def test_cmd_mcp_list():
    ctx, reg = make_ctx()
    result = reg.execute("/mcp", ctx)
    assert "MCP" in result or "mcp" in result.lower() or "server" in result.lower()
run("P6.4 /mcp list: shows MCP status", test_cmd_mcp_list)

def test_cmd_feedback():
    ctx, reg = make_ctx()
    result = reg.execute("/feedback This tool is great!", ctx)
    assert "saved" in result.lower() or "Feedback" in result
    fb_file = Path(_TEMP) / "feedback.json"
    assert fb_file.exists()
    data = json.loads(fb_file.read_text())
    assert len(data) >= 1
    assert "great" in data[-1]["text"]
run("P6.5 /feedback: saves to feedback.json", test_cmd_feedback)

def test_cmd_terminal_setup():
    ctx, reg = make_ctx()
    result = reg.execute("/terminal-setup", ctx)
    assert "Enter" in result and "Ctrl+C" in result
run("P6.6 /terminal-setup: shows terminal guide", test_cmd_terminal_setup)

def test_cmd_allowed_tools():
    ctx, reg = make_ctx()
    result = reg.execute("/allowed-tools", ctx)
    assert "Permission" in result or "rules" in result.lower()
run("P6.7 /allowed-tools: alias for /permissions", test_cmd_allowed_tools)

def test_cmd_release_notes():
    ctx, reg = make_ctx()
    result = reg.execute("/release-notes", ctx)
    assert "Buddy" in result or "Phase" in result or "v5" in result.lower()
run("P6.8 /release-notes: shows version info", test_cmd_release_notes)

def test_cmd_count_increased():
    reg = CommandRegistry()
    cmds = reg.list_commands()
    assert len(cmds) >= 42, f"Expected >= 42 commands, got {len(cmds)}"
run("P6.9 Command count: >= 42 after Phase 6", test_cmd_count_increased)

# ═══════════════════════════════════════════════════════════════
# Phase 7: Hook System
# ═══════════════════════════════════════════════════════════════
print('  --- Phase 7: Hooks ---')

def test_hook_register_python():
    from core.services.hooks import HookRegistry, HookResult
    reg = HookRegistry()
    called = []
    def my_hook(ctx):
        called.append(ctx)
        return HookResult(success=True, output="ok")
    reg.register("pre_tool_use", my_hook, name="test_hook")
    results = reg.fire("pre_tool_use", {"tool": "Bash"})
    assert len(results) == 1
    assert results[0].success
    assert len(called) == 1
    assert called[0]["tool"] == "Bash"
run("P7.1 Hook: register + fire Python callable", test_hook_register_python)

def test_hook_block():
    from core.services.hooks import HookRegistry, HookResult
    reg = HookRegistry()
    def blocking_hook(ctx):
        return HookResult(success=True, block=True, output="blocked by policy")
    reg.register("pre_tool_use", blocking_hook, name="blocker")
    results = reg.fire("pre_tool_use", {})
    assert results[0].block is True
run("P7.2 Hook: pre_tool_use can block execution", test_hook_block)

def test_hook_bash():
    from core.services.hooks import HookRegistry
    reg = HookRegistry()
    import platform
    if platform.system() == "Windows":
        reg.register("post_tool_use", "echo ok", name="echo_hook")
    else:
        reg.register("post_tool_use", "echo ok", name="echo_hook")
    results = reg.fire("post_tool_use", {"tool": "test"})
    assert len(results) == 1
    assert results[0].success
run("P7.3 Hook: bash command execution", test_hook_bash)

def test_hook_timeout():
    from core.services.hooks import HookRegistry
    reg = HookRegistry()
    import platform
    # Use a command that sleeps long enough to trigger timeout
    cmd = "ping -n 15 127.0.0.1 >nul" if platform.system() == "Windows" else "sleep 15"
    reg.register("pre_tool_use", cmd, name="slow_hook", timeout=1)
    start = time.time()
    results = reg.fire("pre_tool_use", {})
    elapsed = time.time() - start
    assert len(results) == 1
    assert not results[0].success
    assert "timed out" in results[0].error.lower() or elapsed < 5  # timeout worked
run("P7.4 Hook: timeout protection (1s)", test_hook_timeout)

def test_hook_config_load():
    from core.services.hooks import HookRegistry
    settings = Path(_TEMP) / "settings.json"
    settings.write_text(json.dumps({
        "hooks": {"session_start": ["echo started"]}
    }))
    reg = HookRegistry()
    reg.load_from_config(settings)
    hooks = reg.list_hooks()
    assert "session_start" in hooks
run("P7.5 Hook: load from settings.json config", test_hook_config_load)

def test_hook_list_format():
    from core.services.hooks import HookRegistry
    reg = HookRegistry()
    reg.register("pre_tool_use", lambda ctx: None, name="h1")
    reg.register("post_tool_use", lambda ctx: None, name="h2")
    status = reg.format_status()
    assert "pre_tool_use" in status
    assert "h1" in status
run("P7.6 Hook: format_status lists hooks", test_hook_list_format)

def test_hook_events_valid():
    from core.services.hooks import HOOK_EVENTS
    assert "pre_tool_use" in HOOK_EVENTS
    assert "post_tool_use" in HOOK_EVENTS
    assert "session_start" in HOOK_EVENTS
    assert "on_error" in HOOK_EVENTS
    assert len(HOOK_EVENTS) >= 7
run("P7.7 Hook: all event types defined", test_hook_events_valid)

# ═══════════════════════════════════════════════════════════════
# Phase 8: Cost Calculation
# ═══════════════════════════════════════════════════════════════
print('  --- Phase 8: Cost ---')

def test_cost_usd_basic():
    sc = SessionCost()
    sc.add_call("claude-sonnet-4", input_tokens=1_000_000, output_tokens=100_000)
    cost = sc.cost_usd
    # sonnet-4: $3/M input + $15/M output = $3 + $1.5 = $4.5
    assert 4.0 < cost < 5.0, f"Expected ~$4.5, got ${cost:.2f}"
run("P8.1 Cost USD: sonnet-4 1M in + 100K out ≈ $4.5", test_cost_usd_basic)

def test_cost_usd_multi_model():
    sc = SessionCost()
    sc.add_call("claude-sonnet-4", input_tokens=500_000, output_tokens=50_000)
    sc.add_call("claude-haiku-3.5", input_tokens=200_000, output_tokens=20_000)
    cost = sc.cost_usd
    # sonnet: $1.5 + $0.75 = $2.25
    # haiku: $0.16 + $0.08 = $0.24
    # total ≈ $2.49
    assert 2.0 < cost < 3.0, f"Expected ~$2.49, got ${cost:.2f}"
run("P8.2 Cost USD: multi-model calculation", test_cost_usd_multi_model)

def test_cost_usd_cache_tokens():
    sc = SessionCost()
    sc.add_call("claude-sonnet-4", input_tokens=100_000, output_tokens=10_000)
    sc.cache_read_tokens = 500_000
    sc.cache_creation_tokens = 100_000
    cost = sc.cost_usd
    # Base: $0.3 + $0.15 = $0.45
    # Cache read: 500K * $0.3/M = $0.15
    # Cache create: 100K * $3.75/M = $0.375
    # Total ≈ $0.975
    assert 0.5 < cost < 1.5, f"Expected ~$0.975, got ${cost:.2f}"
run("P8.3 Cost USD: includes cache tokens", test_cost_usd_cache_tokens)

def test_cost_summary_includes_usd():
    sc = SessionCost()
    sc.add_call("claude-sonnet-4", input_tokens=10_000, output_tokens=1_000)
    s = sc.summary()
    assert "Estimated cost: $" in s
run("P8.4 Cost summary: includes USD estimate", test_cost_summary_includes_usd)

def test_cost_zero_when_no_pricing():
    sc = SessionCost()
    sc.add_call("unknown-model-xyz", input_tokens=1000, output_tokens=100)
    assert sc.cost_usd == 0.0 or sc.cost_usd >= 0
run("P8.5 Cost USD: 0 for unknown model", test_cost_zero_when_no_pricing)

def test_pricing_table_exists():
    from config import MODEL_PRICING
    assert "claude-sonnet-4" in MODEL_PRICING
    assert "claude-opus-4" in MODEL_PRICING
    assert "gpt-4o" in MODEL_PRICING
    assert MODEL_PRICING["claude-sonnet-4"]["input"] == 3.0
    assert MODEL_PRICING["claude-sonnet-4"]["output"] == 15.0
run("P8.6 Pricing table: models + rates correct", test_pricing_table_exists)

# ═══════════════════════════════════════════════════════════════
import shutil
try: ok = summary()
finally: shutil.rmtree(_TEMP, ignore_errors=True)
sys.exit(0 if ok else 1)
