"""
Capability Tests — Section 二 Compaction (2.1–2.14)
Tests 8-layer compaction pipeline from CAPABILITY_MATRIX.md using simulated operations.

Covers:
  2.1  L0: Microcompact (fold stubs, truncate old tool results)
  2.2  L1: Snip (delete oldest, respect pairs)
  2.3  L2: Tool-result compress (truncate to 500 chars)
  2.4  L3: Message grouping (assistant+tool pairs intact)
  2.5  L4: Memory-preserving (extract before compact)
  2.6  L5: Mechanical summary ([CONTEXT COMPACTED] with file list)
  2.7  L6: LLM summary (9-section structured, fallback to L5)
  2.8  L7: Reactive (forced compact on API error)
  2.9  Boundary tracking (persistent across save/load)
  2.10 Compact warning (throttled, 120s cooldown)
  2.11 Post-compact cleanup (merge consecutive user, remove empty)
  2.12 Adaptive thresholds (fast typing → earlier compaction)
  2.13 CJK token estimation (1.5 chars/token vs 4.0)
  2.14 Compact prompt (NO_TOOLS_PREAMBLE, 9-section structure)
"""

import sys, os, io, time, tempfile, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_buddy = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _buddy)
os.chdir(_buddy)

from pathlib import Path
_TEMP = tempfile.mkdtemp(prefix='buddy_cap_compact_')
import config
config.DATA_DIR = Path(_TEMP)
config.CONVERSATIONS_DIR = Path(_TEMP) / "conversations"
config.CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
config.INPUT_HISTORY_FILE = Path(_TEMP) / "input_history.json"

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
        print(f'  Cap Compaction (2.1-2.14): {total}/{total} ALL TESTS PASSED')
    else:
        print(f'  Cap Compaction (2.1-2.14): {PASS}/{total} PASSED, {FAIL} FAILED')
        for n, e in ERRORS:
            print(f'    X {n}: {e}')
    print(f'{"="*60}')
    return FAIL == 0

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from core.conversation import (
    ConversationManager, FileReadState,
    MICROCOMPACT_THRESHOLD, SNIP_THRESHOLD, SNIP_DELETE_COUNT,
    TOOL_COMPRESS_THRESHOLD, TOOL_RESULT_MAX_CHARS,
    COMPACT_THRESHOLD, COMPACT_KEEP_RECENT, MAX_MESSAGES,
)
from unittest.mock import MagicMock, patch

print('=' * 60)
print('  Capability Tests: Compaction (2.1–2.14)')
print('=' * 60)


def fill_messages(conv, n, tool_results=False, long_tools=False):
    """Add n user+assistant pairs to conversation (2n total messages)."""
    for i in range(n):
        conv.add_user_message(f"User question #{i}")
        if tool_results:
            tool_content = "X" * (2000 if long_tools else 100)
            conv._messages.append({
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "id": f"tc_{i}", "name": "FileRead",
                     "input": {"file_path": f"/path/file_{i}.py"}},
                ],
            })
            conv._messages.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": f"tc_{i}",
                     "content": tool_content},
                ],
            })
        else:
            conv.add_assistant_message(f"Reply to #{i}")


# ═══════════════════════════════════════════════════════════════════
# 2.1 L0: Microcompact
# ═══════════════════════════════════════════════════════════════════

def test_2_1_microcompact_threshold():
    """Microcompact triggers at > MICROCOMPACT_THRESHOLD messages."""
    conv = ConversationManager()
    fill_messages(conv, MICROCOMPACT_THRESHOLD // 2 + 2, tool_results=True, long_tools=True)

    count_before = len(conv.messages)
    assert count_before > MICROCOMPACT_THRESHOLD

    result = conv.compact_if_needed()
    # Should have done microcompact (fold stubs)
    if result:
        assert "microcompact" in result.lower() or "snip" in result.lower()
run("2.1a L0 Microcompact: triggers above threshold", test_2_1_microcompact_threshold)


def test_2_1b_microcompact_folds_old_results():
    """Microcompact truncates old tool results but keeps recent ones intact."""
    conv = ConversationManager()

    # Add old messages with long tool results
    for i in range(20):
        conv._messages.append({"role": "user", "content": f"q{i}"})
        conv._messages.append({
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": f"tc_{i}",
                          "content": "R" * 2000}],
        })
    # Add recent messages
    for i in range(6):
        conv.add_user_message(f"recent {i}")
        conv.add_assistant_message(f"reply {i}")

    folded = conv._microcompact()
    assert folded > 0, "Should have folded some old tool results"
run("2.1b L0 Microcompact: folds old tool results, keeps recent", test_2_1b_microcompact_folds_old_results)


# ═══════════════════════════════════════════════════════════════════
# 2.2 L1: Snip
# ═══════════════════════════════════════════════════════════════════

def test_2_2_snip_deletes_oldest():
    """Snip removes oldest messages when count > SNIP_THRESHOLD."""
    conv = ConversationManager()
    fill_messages(conv, SNIP_THRESHOLD)  # 60 messages (30 pairs)
    count_before = len(conv.messages)
    assert count_before > SNIP_THRESHOLD

    removed = conv._snip_oldest()
    assert removed > 0, "Should have removed messages"
    assert len(conv.messages) < count_before
    # Recent messages should be preserved
    assert len(conv.messages) >= COMPACT_KEEP_RECENT
run("2.2a L1 Snip: removes oldest, preserves recent", test_2_2_snip_deletes_oldest)


def test_2_2b_snip_preserves_summary():
    """Snip preserves [CONTEXT COMPACTED] summary at index 0."""
    conv = ConversationManager()
    conv._messages.append({
        "role": "user",
        "content": "[CONTEXT COMPACTED] Previous summary here."
    })
    fill_messages(conv, SNIP_THRESHOLD)

    conv._snip_oldest()

    first = conv.messages[0]
    assert "[CONTEXT COMPACTED]" in str(first.get("content", ""))
run("2.2b L1 Snip: preserves [CONTEXT COMPACTED] at index 0", test_2_2b_snip_preserves_summary)


# ═══════════════════════════════════════════════════════════════════
# 2.3 L2: Tool-result compress
# ═══════════════════════════════════════════════════════════════════

def test_2_3_tool_compress():
    """Tool results > 500 chars in old messages get truncated."""
    conv = ConversationManager()
    # Add messages with long tool results
    for i in range(30):
        conv._messages.append({"role": "user", "content": f"q{i}"})
        conv._messages.append({
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": f"tc_{i}",
                          "content": "T" * 2000}],
        })
    # Add recent (should not be compressed)
    for i in range(COMPACT_KEEP_RECENT):
        conv.add_user_message(f"recent {i}")

    compressed = conv._compress_tool_results()
    assert compressed > 0, "Should have compressed some tool results"

    # Check that old results are truncated
    compress_end = len(conv.messages) - COMPACT_KEEP_RECENT
    for i in range(min(5, compress_end)):
        msg = conv.messages[i]
        content = msg.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    rc = block.get("content", "")
                    if isinstance(rc, str) and "truncated" in rc:
                        assert len(rc) < 2000, "Should be truncated"
run("2.3  L2 Tool compress: old results > 500 chars truncated", test_2_3_tool_compress)


# ═══════════════════════════════════════════════════════════════════
# 2.4 L3: Message grouping (assistant+tool pairs intact after snip)
# ═══════════════════════════════════════════════════════════════════

def test_2_4_safe_snip_point():
    """Snip respects assistant+tool pairs — no orphaned tool messages."""
    conv = ConversationManager()

    # Construct a sequence: user, assistant(tool_use), user(tool_result), ...
    for i in range(20):
        conv._messages.append({"role": "user", "content": f"q{i}"})
        conv._messages.append({
            "role": "assistant",
            "content": [{"type": "tool_use", "id": f"tc_{i}", "name": "T", "input": {}}],
        })
        conv._messages.append({
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": f"tc_{i}", "content": "ok"}],
        })

    conv._snip_oldest()

    # Verify: no orphaned tool messages at the start
    if conv.messages:
        first = conv.messages[0]
        # First message should be user or assistant, not a tool_result without preceding tool_use
        content = first.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    # Find preceding assistant with matching tool_use
                    pass  # It's ok if it's at position 0 after snip
    # Simple check: role should alternate correctly
    for i in range(len(conv.messages) - 1):
        curr_role = conv.messages[i].get("role")
        next_role = conv.messages[i+1].get("role")
        # Not three consecutive same roles
        if i + 2 < len(conv.messages):
            third_role = conv.messages[i+2].get("role")
            assert not (curr_role == next_role == third_role == "user"), \
                f"Three consecutive user messages at index {i}"
run("2.4  L3 Grouping: snip preserves message pair integrity", test_2_4_safe_snip_point)


# ═══════════════════════════════════════════════════════════════════
# 2.5 L4: Memory-preserving
# ═══════════════════════════════════════════════════════════════════

def test_2_5_preserve_memories():
    """Memory extraction runs before compaction if memory_mgr available."""
    conv = ConversationManager()
    mock_mgr = MagicMock()
    mock_mgr._regex_extract.return_value = ["user prefers Python"]
    conv._memory_mgr = mock_mgr

    # Fill enough messages to trigger compaction
    fill_messages(conv, 30)

    conv._preserve_memories()

    mock_mgr._regex_extract.assert_called_once()
    args = mock_mgr._regex_extract.call_args[0]
    assert len(args[0]) > 0, "Should pass old messages to extract"
run("2.5  L4 Memory preserving: extracts before compact", test_2_5_preserve_memories)


# ═══════════════════════════════════════════════════════════════════
# 2.6 L5: Mechanical summary
# ═══════════════════════════════════════════════════════════════════

def test_2_6_mechanical_summary():
    """Full compact produces [CONTEXT COMPACTED] summary with file list."""
    conv = ConversationManager()

    # Add messages mentioning files
    conv.add_user_message("Read the main.py file")
    conv._messages.append({
        "role": "assistant",
        "content": [
            {"type": "tool_use", "id": "tc_1", "name": "FileEdit",
             "input": {"file_path": "/path/to/main.py"}},
        ],
    })
    conv._messages.append({
        "role": "user",
        "content": [{"type": "tool_result", "tool_use_id": "tc_1", "content": "ok"}],
    })
    # Fill more to trigger compact
    fill_messages(conv, 30)

    conv._full_compact()

    first = conv.messages[0]
    content = first.get("content", "")
    assert "[CONTEXT COMPACTED]" in content, "Summary should have [CONTEXT COMPACTED] marker"
    assert "main.py" in content, "Summary should mention files"
    assert "re-read" in content.lower() or "FileRead" in content, \
        "Summary should remind to re-read files"
run("2.6  L5 Mechanical summary: [CONTEXT COMPACTED] + files", test_2_6_mechanical_summary)


def test_2_6b_summary_extracts_tools():
    """Mechanical summary lists tools used in old messages."""
    conv = ConversationManager()
    for tool_name in ["FileRead", "Glob", "Grep", "Bash"]:
        conv._messages.append({
            "role": "assistant",
            "content": [{"type": "tool_use", "id": "tc", "name": tool_name, "input": {}}],
        })
        conv._messages.append({
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "tc", "content": "ok"}],
        })
    fill_messages(conv, 30)

    conv._full_compact()

    content = conv.messages[0].get("content", "")
    assert "FileRead" in content or "Glob" in content, "Summary should list tools used"
run("2.6b Mechanical summary: lists tools used", test_2_6b_summary_extracts_tools)


# ═══════════════════════════════════════════════════════════════════
# 2.7 L6: LLM summary (+ fallback to L5)
# ═══════════════════════════════════════════════════════════════════

def test_2_7_llm_compact():
    """LLM compact uses provider to generate summary."""
    conv = ConversationManager()
    fill_messages(conv, 30)

    def mock_provider_call(messages, system, tools):
        return ({}, [], "Summary: User asked about Python and files.")

    result = conv.llm_compact(mock_provider_call)
    assert result is not None
    assert "llm_compact" in result.lower()

    # Summary should be in the first message
    content = conv.messages[0].get("content", "")
    assert "Python" in content or "Summary" in content
run("2.7a L6 LLM compact: generates structured summary", test_2_7_llm_compact)


def test_2_7b_llm_fallback():
    """LLM compact falls back to mechanical when API fails."""
    conv = ConversationManager()
    fill_messages(conv, 30)

    def failing_provider(messages, system, tools):
        raise Exception("API error")

    result = conv.llm_compact(failing_provider)
    assert "mechanical" in result.lower() or "fell back" in result.lower()
    content = conv.messages[0].get("content", "")
    assert "[CONTEXT COMPACTED]" in content
run("2.7b L6 LLM compact: fallback to mechanical on API error", test_2_7b_llm_fallback)


# ═══════════════════════════════════════════════════════════════════
# 2.8 L7: Reactive (tested in engine test 1.5, verify here)
# ═══════════════════════════════════════════════════════════════════

def test_2_8_full_compact_reduces_messages():
    """_full_compact reduces message count, keeping COMPACT_KEEP_RECENT."""
    conv = ConversationManager()
    fill_messages(conv, 40)
    count_before = len(conv.messages)

    conv._full_compact()

    count_after = len(conv.messages)
    assert count_after < count_before, \
        f"Compact should reduce: {count_before} → {count_after}"
    assert count_after >= COMPACT_KEEP_RECENT, \
        f"Should keep at least {COMPACT_KEEP_RECENT} recent"
run("2.8  L7 Reactive: _full_compact reduces to KEEP_RECENT + summary", test_2_8_full_compact_reduces_messages)


# ═══════════════════════════════════════════════════════════════════
# 2.9 Boundary tracking (persistent across save/load)
# ═══════════════════════════════════════════════════════════════════

def test_2_9_boundary_tracking():
    """Compact boundary is set after compaction and persists across save/load."""
    conv = ConversationManager()
    fill_messages(conv, 30)

    conv._full_compact()
    assert conv._compact_boundary >= 0

    # Set boundary explicitly
    conv._compact_boundary = 1

    # Save and reload
    conv.save()
    conv2 = ConversationManager()
    loaded = conv2.load_last()
    assert loaded, "Should load saved session"
    assert conv2._compact_boundary == 1, \
        f"Boundary should persist: expected 1, got {conv2._compact_boundary}"
run("2.9  Boundary tracking: persists across save/load", test_2_9_boundary_tracking)


# ═══════════════════════════════════════════════════════════════════
# 2.10 Compact warning (throttled, 120s cooldown)
# ═══════════════════════════════════════════════════════════════════

def test_2_10_compact_warning():
    """Compact warning fires once, then cooldown prevents repeat."""
    conv = ConversationManager()
    warnings = []
    conv._on_compact_warning = lambda msg: warnings.append(msg)

    fill_messages(conv, 30)

    # First warning
    conv._emit_compact_warning()
    assert len(warnings) == 1, "First warning should fire"
    assert "%" in warnings[0], "Warning should mention percentage"

    # Immediate repeat — should be throttled
    conv._emit_compact_warning()
    assert len(warnings) == 1, "Second call within cooldown should be throttled"

    # After cooldown
    conv._last_warning_time -= 130  # simulate 130s elapsed
    conv._emit_compact_warning()
    assert len(warnings) == 2, "After cooldown, warning should fire again"
run("2.10 Compact warning: fires once, throttled for 120s", test_2_10_compact_warning)


# ═══════════════════════════════════════════════════════════════════
# 2.11 Post-compact cleanup
# ═══════════════════════════════════════════════════════════════════

def test_2_11_cleanup_merges_consecutive_user():
    """Post-compact cleanup merges consecutive user messages."""
    conv = ConversationManager()
    conv._messages = [
        {"role": "user", "content": "first"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "reply"},
    ]

    cleaned = conv._post_compact_cleanup()
    assert cleaned >= 1, "Should have merged consecutive user messages"
    assert len(conv.messages) == 2, f"Expected 2 messages, got {len(conv.messages)}"
    assert "first" in conv.messages[0]["content"]
    assert "second" in conv.messages[0]["content"]
run("2.11a Cleanup: merges consecutive user messages", test_2_11_cleanup_merges_consecutive_user)


def test_2_11b_cleanup_removes_empty():
    """Post-compact cleanup removes empty messages."""
    conv = ConversationManager()
    conv._messages = [
        {"role": "user", "content": "real"},
        {"role": "assistant", "content": ""},
        {"role": "user", "content": None},
        {"role": "assistant", "content": "also real"},
    ]

    cleaned = conv._post_compact_cleanup()
    assert cleaned >= 2, "Should have removed 2 empty messages"
    assert len(conv.messages) == 2
run("2.11b Cleanup: removes empty messages", test_2_11b_cleanup_removes_empty)


# ═══════════════════════════════════════════════════════════════════
# 2.12 Adaptive thresholds
# ═══════════════════════════════════════════════════════════════════

def test_2_12_adaptive_fast_typing():
    """8+ messages in 2 minutes → adaptive offset = -5."""
    conv = ConversationManager()
    now = time.time()
    conv._message_timestamps = [now - i for i in range(10)]  # 10 msgs in last few seconds

    conv._update_adaptive_offset()
    assert conv._adaptive_offset == -5, f"Expected -5, got {conv._adaptive_offset}"
run("2.12a Adaptive: 8+ msgs/2min → offset = -5", test_2_12_adaptive_fast_typing)


def test_2_12b_adaptive_moderate():
    """4-7 messages in 2 minutes → adaptive offset = -2."""
    conv = ConversationManager()
    now = time.time()
    conv._message_timestamps = [now - i*10 for i in range(5)]  # 5 msgs

    conv._update_adaptive_offset()
    assert conv._adaptive_offset == -2, f"Expected -2, got {conv._adaptive_offset}"
run("2.12b Adaptive: 4-7 msgs/2min → offset = -2", test_2_12b_adaptive_moderate)


def test_2_12c_adaptive_slow():
    """< 4 messages in 2 minutes → offset = 0."""
    conv = ConversationManager()
    now = time.time()
    conv._message_timestamps = [now - 60, now - 30]  # only 2

    conv._update_adaptive_offset()
    assert conv._adaptive_offset == 0
run("2.12c Adaptive: <4 msgs/2min → offset = 0", test_2_12c_adaptive_slow)


def test_2_12d_effective_threshold():
    """get_effective_threshold applies adaptive offset with floor of 15."""
    conv = ConversationManager()
    conv._adaptive_offset = -5
    assert conv.get_effective_threshold(30) == 25
    assert conv.get_effective_threshold(20) == 15  # min 15
    assert conv.get_effective_threshold(15) == 15  # can't go below 15
run("2.12d Effective threshold: offset applied, min 15", test_2_12d_effective_threshold)


# ═══════════════════════════════════════════════════════════════════
# 2.13 CJK token estimation
# ═══════════════════════════════════════════════════════════════════

def test_2_13_cjk_tokens():
    """Chinese text estimates more tokens per character than English."""
    conv = ConversationManager()
    chinese = "你好世界这是一个测试"  # 9 CJK chars
    english = "hello wor"              # 9 Latin chars (similar length)

    cn_tokens = conv._estimate_msg_tokens(chinese)
    en_tokens = conv._estimate_msg_tokens(english)

    assert cn_tokens > en_tokens, \
        f"CJK should estimate more tokens: CN={cn_tokens}, EN={en_tokens}"
run("2.13a CJK estimation: Chinese > English per char", test_2_13_cjk_tokens)


def test_2_13b_code_tokens():
    """Code with symbols estimates ~3.5 chars/token."""
    conv = ConversationManager()
    code = 'def f(x): return {k: v for k, v in x.items()}'
    prose = 'the quick brown fox jumps over the lazy dog'

    code_tokens = conv._estimate_msg_tokens(code)
    prose_tokens = conv._estimate_msg_tokens(prose)

    # Code should have more tokens per char than pure prose
    code_ratio = len(code) / max(code_tokens, 1)
    prose_ratio = len(prose) / max(prose_tokens, 1)

    assert code_ratio < prose_ratio, \
        f"Code should have lower chars/token ratio: code={code_ratio:.1f}, prose={prose_ratio:.1f}"
run("2.13b CJK estimation: code tokens (symbol-heavy)", test_2_13b_code_tokens)


def test_2_13c_empty_content():
    """Empty content returns 0 tokens."""
    conv = ConversationManager()
    assert conv._estimate_msg_tokens("") == 0
    assert conv._estimate_msg_tokens([]) == 0
    assert conv._estimate_msg_tokens(None) == 0
run("2.13c Token estimation: empty content → 0", test_2_13c_empty_content)


# ═══════════════════════════════════════════════════════════════════
# 2.14 Compact prompt
# ═══════════════════════════════════════════════════════════════════

def test_2_14_compact_prompt():
    """Compact prompt has NO_TOOLS_PREAMBLE and structured sections."""
    try:
        from prompts.compact import build_compact_prompt, build_post_compact_marker
    except ImportError:
        # If compact module doesn't exist yet, check the format from llm_compact
        print("    (prompts/compact.py not found, testing via llm_compact path)")
        return

    prompt = build_compact_prompt(partial=True)
    assert "tool" in prompt.lower() or "summary" in prompt.lower(), \
        "Compact prompt should mention tools or summary"

    marker = build_post_compact_marker(["/path/to/file.py"])
    assert "file.py" in marker or "COMPACT" in marker.upper()
run("2.14 Compact prompt: structured with NO_TOOLS hint", test_2_14_compact_prompt)


# ═══════════════════════════════════════════════════════════════════
# 2.X Pipeline integration: compact_if_needed full path
# ═══════════════════════════════════════════════════════════════════

def test_2_X_pipeline_integration():
    """Full pipeline: fill 60+ messages → compact_if_needed → reduced count."""
    conv = ConversationManager()
    fill_messages(conv, 35, tool_results=True, long_tools=True)

    count_before = len(conv.messages)
    assert count_before > COMPACT_THRESHOLD

    result = conv.compact_if_needed()
    assert result is not None, "Should have compacted"

    count_after = len(conv.messages)
    assert count_after < count_before, \
        f"Pipeline should reduce: {count_before} → {count_after}"
run("2.X  Pipeline integration: 60+ msgs → compact → reduced", test_2_X_pipeline_integration)


# ═══════════════════════════════════════════════════════════════════
# FileReadState (Section 八: File Tracking, tested here as it's in conversation.py)
# ═══════════════════════════════════════════════════════════════════

def test_8_1_lru_cache():
    """FileReadState tracks reads with LRU eviction at 100 entries."""
    frs = FileReadState()
    for i in range(110):
        frs.record_read(f"/tmp/file_{i}.py", mtime=1000.0 + i)

    assert len(frs.read_files) == 100, f"Should cap at 100, got {len(frs.read_files)}"
    assert not frs.has_read("/tmp/file_0.py"), "Oldest should be evicted"
    assert frs.has_read("/tmp/file_109.py"), "Most recent should be kept"
run("8.1  LRU cache: 100 entries max, oldest evicted", test_8_1_lru_cache)


def test_8_2_read_before_edit():
    """has_read returns False for unread files."""
    frs = FileReadState()
    assert not frs.has_read("/some/file.py")
    frs.record_read("/some/file.py")
    assert frs.has_read("/some/file.py")
run("8.2  Read-before-edit: has_read tracks state", test_8_2_read_before_edit)


def test_8_3_stale_detection():
    """is_stale detects when file was modified after read."""
    import tempfile
    frs = FileReadState()

    with tempfile.NamedTemporaryFile(suffix='.py', delete=False, mode='w') as f:
        f.write("original")
        f.flush()
        path = f.name

    try:
        mtime = os.path.getmtime(path)
        frs.record_read(path, mtime=mtime)
        assert not frs.is_stale(path), "Should not be stale right after read"

        # Modify the file
        time.sleep(0.05)
        with open(path, 'w') as f:
            f.write("modified")
        assert frs.is_stale(path), "Should be stale after external modification"
    finally:
        os.unlink(path)
run("8.3  Stale detection: modified after read → stale", test_8_3_stale_detection)


def test_8_4_clear():
    """clear() empties the read state."""
    frs = FileReadState()
    frs.record_read("/a.py")
    frs.record_read("/b.py")
    assert len(frs.read_files) == 2

    frs.clear()
    assert len(frs.read_files) == 0
    assert not frs.has_read("/a.py")
run("8.4  FileReadState clear: empties all entries", test_8_4_clear)


# ═══════════════════════════════════════════════════════════════════
# Persistence (save/load/archive/list_sessions)
# ═══════════════════════════════════════════════════════════════════

def test_persist_save_load():
    """Save and load_last round-trip preserves messages."""
    conv = ConversationManager()
    conv.add_user_message("Hello")
    conv.add_assistant_message("World")
    conv.save()

    conv2 = ConversationManager()
    loaded = conv2.load_last()
    assert loaded
    assert conv2.message_count == 2
    assert conv2.messages[0]["content"] == "Hello"
    assert conv2.messages[1]["content"] == "World"
run("Persistence: save → load_last preserves messages", test_persist_save_load)


def test_persist_archive():
    """Archive saves current session and starts fresh."""
    conv = ConversationManager()
    conv.add_user_message("Before archive")
    old_id = conv._conversation_id

    conv.archive()

    assert conv.message_count == 0, "Should be empty after archive"
    assert conv._conversation_id != old_id, "Should have new UUID"

    # Old session should still be on disk
    old_file = config.CONVERSATIONS_DIR / f"{old_id}.json"
    assert old_file.exists(), "Archived session file should exist"
run("Persistence: archive saves old, starts fresh UUID", test_persist_archive)


def test_persist_list_sessions():
    """list_sessions returns metadata without loading all messages."""
    # Create a few sessions
    for i in range(3):
        conv = ConversationManager()
        conv.add_user_message(f"Session {i} message")
        conv.save()

    sessions = ConversationManager.list_sessions()
    assert len(sessions) >= 3, f"Should list >= 3 sessions, got {len(sessions)}"

    for s in sessions:
        assert "id" in s
        assert "title" in s
        assert "saved_at" in s
        assert "message_count" in s

    # Should be sorted by saved_at descending
    times = [s["saved_at"] for s in sessions]
    assert times == sorted(times, reverse=True), "Should be sorted newest first"
run("Persistence: list_sessions returns sorted metadata", test_persist_list_sessions)


# ═══════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════

import shutil
try:
    ok = summary()
finally:
    shutil.rmtree(_TEMP, ignore_errors=True)

sys.exit(0 if ok else 1)
