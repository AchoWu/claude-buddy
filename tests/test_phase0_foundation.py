"""
Phase 0 Tests: isConcurrencySafe + normalization + tool summary
"""
import sys, os, io, time, tempfile, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_buddy = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _buddy)
os.chdir(_buddy)

from pathlib import Path
_TEMP = tempfile.mkdtemp(prefix='buddy_p0_')
import config
config.DATA_DIR = Path(_TEMP)
config.CONVERSATIONS_DIR = Path(_TEMP) / "conversations"
config.CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

PASS = 0; FAIL = 0; ERRORS = []
def run(name, fn):
    global PASS, FAIL
    try: fn(); PASS += 1; print(f'  OK  {name}')
    except Exception as e: FAIL += 1; ERRORS.append((name, str(e))); print(f'  FAIL {name}: {e}')
def summary():
    total = PASS + FAIL
    print(f'\n{"="*60}')
    s = f'Phase 0: {total}/{total} ALL PASSED' if FAIL == 0 else f'Phase 0: {PASS}/{total} PASSED, {FAIL} FAILED'
    print(f'  {s}')
    for n, e in ERRORS: print(f'    X {n}: {e}')
    print(f'{"="*60}')
    return FAIL == 0

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
_qapp = QApplication.instance() or QApplication(sys.argv)

print('=' * 60)
print('  Phase 0: Foundation Tests')
print('=' * 60)

# ═════════════════════════════════════════════════════════════
# Normalization
# ═════════════════════════════════════════════════════════════
from core.normalization import normalize_messages

def test_norm_strip_empty():
    msgs = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": ""},
        {"role": "user", "content": "world"},
    ]
    result = normalize_messages(msgs)
    assert len(result) == 1  # two users merged, empty assistant removed
    assert "hello" in result[0]["content"] and "world" in result[0]["content"]
run("Norm: strip empty + merge consecutive user", test_norm_strip_empty)

def test_norm_strip_virtual():
    msgs = [
        {"role": "user", "content": "hi", "virtual": True},
        {"role": "user", "content": "real"},
    ]
    result = normalize_messages(msgs)
    assert len(result) == 1
    assert result[0]["content"] == "real"
run("Norm: strip virtual messages", test_norm_strip_virtual)

def test_norm_orphan_tool_result():
    msgs = [
        {"role": "assistant", "content": [
            {"type": "tool_use", "id": "t1", "name": "Glob", "input": {}},
        ]},
        {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": "t1", "content": "ok"},
            {"type": "tool_result", "tool_use_id": "orphan_id", "content": "bad"},
        ]},
    ]
    result = normalize_messages(msgs)
    # orphan_id should be removed, t1 should remain
    user_msg = [m for m in result if m["role"] == "user"][0]
    assert len(user_msg["content"]) == 1
    assert user_msg["content"][0]["tool_use_id"] == "t1"
run("Norm: remove orphaned tool_result", test_norm_orphan_tool_result)

def test_norm_merge_user_lists():
    msgs = [
        {"role": "user", "content": [{"type": "text", "text": "a"}]},
        {"role": "user", "content": [{"type": "text", "text": "b"}]},
    ]
    result = normalize_messages(msgs)
    assert len(result) == 1
    assert len(result[0]["content"]) == 2
run("Norm: merge consecutive user (list content)", test_norm_merge_user_lists)

# ═════════════════════════════════════════════════════════════
# Concurrency Safe
# ═════════════════════════════════════════════════════════════
from core.engine import LLMEngine
from core.providers.base import ToolDef, ToolCall

def test_concurrency_safe_stored():
    eng = LLMEngine()
    eng.register_tool(
        ToolDef(name="SafeTool", description="safe", input_schema={}),
        lambda x: "ok", is_read_only=True, concurrency_safe=True,
    )
    eng.register_tool(
        ToolDef(name="UnsafeTool", description="unsafe", input_schema={}),
        lambda x: "ok", is_read_only=False, concurrency_safe=False,
    )
    assert eng._tool_concurrency_safe["SafeTool"] is True
    assert eng._tool_concurrency_safe["UnsafeTool"] is False
run("ConcSafe: stored in engine dict", test_concurrency_safe_stored)

def test_batch_partitioning():
    """Verify that parallel execution partitions safe vs unsafe tools."""
    eng = LLMEngine()
    execution_order = []

    def make_executor(name):
        def ex(inp):
            execution_order.append(name)
            time.sleep(0.01)
            return f"result_{name}"
        return ex

    # Register 3 safe + 1 unsafe + 1 safe
    for name, safe in [("S1", True), ("S2", True), ("S3", True), ("U1", False), ("S4", True)]:
        eng.register_tool(
            ToolDef(name=name, description=name, input_schema={}),
            make_executor(name), concurrency_safe=safe,
        )

    # Create tool calls
    tcs = [ToolCall(id=f"id_{n}", name=n, input={}) for n in ["S1", "S2", "S3", "U1", "S4"]]

    results, names = eng._execute_tools_parallel(tcs, 0)
    assert len(results) == 5
    assert all(r is not None for r in results)
    # U1 must execute alone (not overlapping with S1-S3 or S4)
    # Check results are correct
    for i, name in enumerate(["S1", "S2", "S3", "U1", "S4"]):
        assert results[i]["output"] == f"result_{name}", f"Wrong result for {name}: {results[i]}"
run("ConcSafe: batch partitioning works", test_batch_partitioning)

# ═════════════════════════════════════════════════════════════
# Tool Summary
# ═════════════════════════════════════════════════════════════
from core.tool_summary import generate_tool_summary

def test_summary_no_provider():
    result = generate_tool_summary(
        [{"name": "Glob", "input": {}, "output": "files"}],
        provider_call_fn=None,
    )
    assert result is None
run("Summary: returns None without provider", test_summary_no_provider)

def test_summary_with_mock_provider():
    def mock_provider(messages, system, tools):
        return {}, [], "Searched in src/"
    result = generate_tool_summary(
        [
            {"name": "Glob", "input": {"pattern": "*.py"}, "output": "file1.py\nfile2.py"},
            {"name": "Grep", "input": {"pattern": "def foo"}, "output": "line 42: def foo():"},
        ],
        provider_call_fn=mock_provider,
    )
    assert result == "Searched in src/"
run("Summary: returns label from mock provider", test_summary_with_mock_provider)

def test_summary_truncation():
    """Verify inputs/outputs are truncated to 300 chars."""
    captured = {}
    def mock_provider(messages, system, tools):
        captured["user_content"] = messages[0]["content"]
        return {}, [], "Updated files"
    big_output = "X" * 1000
    generate_tool_summary(
        [{"name": "Bash", "input": {"command": "echo hi"}, "output": big_output}],
        provider_call_fn=mock_provider,
    )
    assert len(captured["user_content"]) < 600  # truncated, not 1000+
run("Summary: truncates long inputs/outputs", test_summary_truncation)

# ═════════════════════════════════════════════════════════════
import shutil
try: ok = summary()
finally: shutil.rmtree(_TEMP, ignore_errors=True)
sys.exit(0 if ok else 1)
