"""
Real API tests for the command system (~10 tests).
Each test exercises a slash command via CommandRegistry.execute().
"""

import sys, os, io, time, tempfile
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from tests.real_api_helpers import (
    get_app, skip_no_api, make_real_engine, make_provider,
    run, summary, reset_counters, SignalBox,
)

app = get_app()
skip_no_api()

# ── Setup ─────────────────────────────────────────────────────────
ENGINE, BOX = make_real_engine()
from core.commands import CommandRegistry
cmd_reg = CommandRegistry()


def make_ctx():
    return {
        "engine": ENGINE,
        "conversation": ENGINE.conversation,
        "command_registry": cmd_reg,
        "tool_registry": None,
        "evolution_mgr": ENGINE._evolution_mgr,
        "task_manager": None,
    }


# ── Tests ─────────────────────────────────────────────────────────

def test_help():
    result = cmd_reg.execute("/help", make_ctx())
    assert result is not None, "help returned None"
    assert "Available" in result or "/help" in result, f"unexpected help output: {result[:200]}"


def test_version():
    result = cmd_reg.execute("/version", make_ctx())
    assert result is not None, "version returned None"
    assert "Buddy" in result or "v5" in result, f"unexpected version output: {result[:200]}"


def test_cost_after_message():
    """Send a real message first, then check /cost."""
    ENGINE.send_message("Say exactly: hello")
    BOX.wait(timeout=30)
    BOX.reset()
    result = cmd_reg.execute("/cost", make_ctx())
    assert result is not None, "cost returned None"
    # After at least one API call, should mention tokens or calls
    assert "token" in result.lower() or "call" in result.lower() or "cost" in result.lower() or "$" in result, \
        f"unexpected cost output: {result[:300]}"


def test_status():
    result = cmd_reg.execute("/status", make_ctx())
    assert result is not None, "status returned None"
    assert "Messages" in result or "Running" in result or "status" in result.lower(), \
        f"unexpected status output: {result[:200]}"


def test_session():
    result = cmd_reg.execute("/session", make_ctx())
    assert result is not None, "session returned None"
    assert "session" in result.lower() or "Messages" in result, \
        f"unexpected session output: {result[:200]}"


def test_flags():
    result = cmd_reg.execute("/flags", make_ctx())
    assert result is not None, "flags returned None"
    # May return flag names, status, or "not available" — all acceptable
    assert isinstance(result, str) and len(result) > 0, f"empty flags output"


def test_compact():
    """Add 55+ messages then run /compact — message count should decrease."""
    conv = ENGINE.conversation
    for i in range(28):
        conv.add_user_message(f"Test padding message user {i}: " + "x" * 60)
        conv.add_assistant_message(f"Test padding message assistant {i}: " + "y" * 60)
    before = conv.message_count
    assert before >= 55, f"Expected 55+ messages, got {before}"
    result = cmd_reg.execute("/compact", make_ctx())
    after = conv.message_count
    assert after < before, f"Expected compaction: before={before}, after={after}"
    assert result is not None


def test_memory():
    result = cmd_reg.execute("/memory", make_ctx())
    assert result is not None, "memory returned None"
    # "No memory stored" or actual memory content — both acceptable
    assert isinstance(result, str), "memory did not return a string"


def test_export():
    """Export to a temp directory and verify the file is created."""
    with tempfile.TemporaryDirectory() as td:
        from pathlib import Path
        import config as _cfg
        old_data_dir = _cfg.DATA_DIR
        try:
            _cfg.DATA_DIR = Path(td)
            # Re-add a message so there's something to export
            ENGINE.conversation.add_user_message("export test message")
            result = cmd_reg.execute("/export json", make_ctx())
            assert result is not None, "export returned None"
            export_file = Path(td) / "export.json"
            assert export_file.exists(), f"export.json not created at {export_file}"
        finally:
            _cfg.DATA_DIR = old_data_dir


def test_soul():
    result = cmd_reg.execute("/soul", make_ctx())
    assert result is not None, "soul returned None"
    # Should contain personality or soul-related info
    assert isinstance(result, str) and len(result) > 0, "soul returned empty string"


# ── Run ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    reset_counters()
    print("\n" + "=" * 60)
    print("  TEST SUITE: Real Commands")
    print("=" * 60 + "\n")

    run("CMD.1  /help",           test_help)
    run("CMD.2  /version",        test_version)
    run("CMD.3  /cost after msg", test_cost_after_message)
    run("CMD.4  /status",         test_status)
    run("CMD.5  /session",        test_session)
    run("CMD.6  /flags",          test_flags)
    run("CMD.7  /compact",        test_compact)
    run("CMD.8  /memory",         test_memory)
    run("CMD.9  /export",         test_export)
    run("CMD.10 /soul",           test_soul)

    ok = summary("Real Commands")
    sys.exit(0 if ok else 1)
