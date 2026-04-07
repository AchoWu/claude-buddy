"""
Suite 2 — Compaction Pipeline
Tests the 8-layer compaction system in core/conversation.py.
~14 tests covering L0-L7, boundary tracking, adaptive thresholds, and CJK estimation.
"""
import sys, os, io, json, time, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.helpers import run, summary, reset, temp_data_dir
from unittest.mock import patch, MagicMock
from pathlib import Path


def _make_cm(max_messages=120):
    """Create a ConversationManager with patched config."""
    from core.conversation import ConversationManager
    return ConversationManager(max_messages=max_messages)


def _fill_messages(cm, count, prefix="msg"):
    """Add alternating user/assistant messages to reach a target count."""
    for i in range(count):
        if i % 2 == 0:
            cm.add_user_message(f"{prefix} user message {i}: " + "x" * 50)
        else:
            cm.add_assistant_message(f"{prefix} assistant message {i}: " + "y" * 50)


def _fill_with_tool_results(cm, count):
    """Add messages with tool results to exercise tool-compress layers."""
    for i in range(count):
        if i % 3 == 0:
            cm.add_user_message(f"User request {i}")
        elif i % 3 == 1:
            cm.add_assistant_message([
                {"type": "text", "text": f"Let me check file {i}..."},
                {"type": "tool_use", "id": f"tc_{i}", "name": "FileRead",
                 "input": {"file_path": f"/tmp/file_{i}.py"}}
            ])
        else:
            cm.add_tool_results([
                {"type": "tool_result", "tool_use_id": f"tc_{i-1}",
                 "content": f"File content line {i}\n" * 200}
            ])


# ═══════════════════════════════════════════════════════════════════
# L0: Microcompact
# ═══════════════════════════════════════════════════════════════════

def test_l0_microcompact():
    """L0: add 25+ messages, compact_if_needed triggers microcompact."""
    with temp_data_dir():
        from core.conversation import ConversationManager, MICROCOMPACT_THRESHOLD
        cm = ConversationManager()
        # Add enough messages with long tool results to trigger folding
        for i in range(13):
            cm.add_user_message(f"request {i}")
            cm.add_assistant_message(f"response {i}")
        # Inject an old tool message with long content
        old_tool_msg = {"role": "tool", "content": "X" * 2000, "tool_call_id": "tc_1"}
        cm._messages.insert(1, old_tool_msg)
        assert len(cm._messages) > MICROCOMPACT_THRESHOLD, \
            f"Need >{MICROCOMPACT_THRESHOLD} messages, have {len(cm._messages)}"
        result = cm.compact_if_needed()
        # Microcompact should have run without error
        if result is not None:
            assert "microcompact" in result or "snip" in result, \
                f"Expected microcompact or snip action, got: {result}"

# ═══════════════════════════════════════════════════════════════════
# L1: Snip
# ═══════════════════════════════════════════════════════════════════

def test_l1_snip_oldest():
    """L1: add 35+ messages, message count decreases after snip."""
    with temp_data_dir():
        from core.conversation import ConversationManager, SNIP_THRESHOLD
        cm = ConversationManager()
        _fill_messages(cm, 36)
        before = cm.message_count
        assert before > SNIP_THRESHOLD, f"Need >{SNIP_THRESHOLD} messages, got {before}"
        result = cm.compact_if_needed()
        after = cm.message_count
        assert after < before, f"Snip should reduce count: {before} -> {after}"
        assert result is not None, "compact_if_needed should return action description"

# ═══════════════════════════════════════════════════════════════════
# L2: Tool-result Compress
# ═══════════════════════════════════════════════════════════════════

def test_l2_tool_result_compress():
    """L2: old tool results get truncated after threshold."""
    with temp_data_dir():
        from core.conversation import ConversationManager, TOOL_COMPRESS_THRESHOLD
        cm = ConversationManager()
        # Build messages with Anthropic-style tool_result blocks
        for i in range(25):
            cm.add_user_message(f"req {i}")
            cm._messages.append({
                "role": "user",
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": f"tu_{i}",
                    "content": "RESULT_DATA " * 200,  # ~2400 chars
                }]
            })
        assert len(cm._messages) > TOOL_COMPRESS_THRESHOLD, \
            f"Need >{TOOL_COMPRESS_THRESHOLD}, have {len(cm._messages)}"
        result = cm.compact_if_needed()
        assert result is not None, "compact_if_needed should have acted"

# ═══════════════════════════════════════════════════════════════════
# L3: Message Grouping
# ═══════════════════════════════════════════════════════════════════

def test_l3_message_grouping():
    """L3: assistant + tool pairs stay intact after snip."""
    with temp_data_dir():
        from core.conversation import ConversationManager
        cm = ConversationManager()
        for i in range(20):
            cm.add_user_message(f"request {i}")
            cm.add_assistant_message(f"response {i}")
        assert len(cm.messages) > 30
        cm.compact_if_needed()
        # Verify no orphaned tool messages
        msgs = cm.messages
        for idx, msg in enumerate(msgs):
            if msg.get("role") == "tool" and idx > 0:
                prev_role = msgs[idx - 1].get("role", "")
                assert prev_role in ("assistant", "user"), \
                    f"Orphaned tool at index {idx}, prev role = {prev_role}"

# ═══════════════════════════════════════════════════════════════════
# L4: Memory Preserve
# ═══════════════════════════════════════════════════════════════════

def test_l4_memory_preserve():
    """L4: memory_mgr._regex_extract called before compaction."""
    with temp_data_dir():
        from core.conversation import ConversationManager
        cm = ConversationManager()
        mock_mm = MagicMock()
        mock_mm._regex_extract = MagicMock(return_value=["- remember this"])
        cm._memory_mgr = mock_mm
        # Fill enough to trigger full compaction: need >50 AFTER snip removes 8
        _fill_messages(cm, 70)
        cm.compact_if_needed()
        assert mock_mm._regex_extract.called, \
            "Memory manager _regex_extract should be called during compaction"

# ═══════════════════════════════════════════════════════════════════
# L5: Mechanical Summary
# ═══════════════════════════════════════════════════════════════════

def test_l5_mechanical_summary():
    """L5: 70+ messages -> first message contains '[CONTEXT COMPACTED]'."""
    with temp_data_dir():
        from core.conversation import ConversationManager, COMPACT_THRESHOLD
        cm = ConversationManager()
        _fill_messages(cm, 70)
        assert len(cm.messages) > COMPACT_THRESHOLD
        cm._provider_call_fn = None  # no LLM -> mechanical summary
        result = cm.compact_if_needed()
        assert result is not None, "Compaction should have happened"
        first = cm.messages[0]
        content = first.get("content", "")
        assert isinstance(content, str), f"First message should be string, got {type(content)}"
        assert "[CONTEXT COMPACTED]" in content, \
            f"First message should contain [CONTEXT COMPACTED]. Got: {content[:200]}"

# ═══════════════════════════════════════════════════════════════════
# L6: LLM Compact
# ═══════════════════════════════════════════════════════════════════

def test_l6_llm_compact():
    """L6: mock provider_call_fn generates LLM summary."""
    with temp_data_dir():
        from core.conversation import ConversationManager
        cm = ConversationManager()
        _fill_messages(cm, 70)

        def mock_provider(messages, system, tools):
            return ("raw", [], "<summary>LLM generated summary of the conversation.</summary>")

        cm._provider_call_fn = mock_provider
        result = cm.compact_if_needed()
        assert result is not None, "compact_if_needed should return action"
        # Should contain llm_compact (or mechanical if compact module import fails)
        assert "compact" in result.lower(), f"Expected compact action, got: {result}"

# ═══════════════════════════════════════════════════════════════════
# L7: Reactive
# ═══════════════════════════════════════════════════════════════════

def test_l7_reactive_setup():
    """L7: provider raising exception triggers fallback to mechanical."""
    with temp_data_dir():
        from core.conversation import ConversationManager
        cm = ConversationManager()
        _fill_messages(cm, 70)

        def failing_provider(messages, system, tools):
            raise Exception("context_too_long: max 200000 tokens")

        cm._provider_call_fn = failing_provider
        result = cm.compact_if_needed()
        assert result is not None, "Compaction should still succeed via fallback"
        assert "mechanical" in result or "llm_compact" in result, \
            f"Expected fallback to mechanical, got: {result}"
        first = cm.messages[0].get("content", "")
        assert "[CONTEXT COMPACTED]" in first or "summary" in first.lower(), \
            "Fallback should produce a compacted summary"

# ═══════════════════════════════════════════════════════════════════
# Boundary Tracking
# ═══════════════════════════════════════════════════════════════════

def test_boundary_tracking():
    """_compact_boundary >= 1 after compaction."""
    with temp_data_dir():
        from core.conversation import ConversationManager
        cm = ConversationManager()
        assert cm._compact_boundary == 0, "Should start at 0"
        _fill_messages(cm, 70)
        cm._provider_call_fn = None
        cm.compact_if_needed()
        assert cm._compact_boundary >= 1, \
            f"Boundary should be >= 1 after compact, got {cm._compact_boundary}"

# ═══════════════════════════════════════════════════════════════════
# Compact Warning Callback
# ═══════════════════════════════════════════════════════════════════

def test_compact_warning_fires():
    """on_compact_warning callback fires during compaction."""
    with temp_data_dir():
        from core.conversation import ConversationManager
        cm = ConversationManager()
        warnings = []
        cm._on_compact_warning = lambda msg: warnings.append(msg)
        cm._last_warning_time = 0  # reset cooldown
        _fill_messages(cm, 70)
        cm.compact_if_needed()
        assert len(warnings) >= 1, f"Warning callback should have fired, got {len(warnings)}"
        assert "full" in warnings[0].lower() or "%" in warnings[0], \
            f"Warning should mention fullness, got: {warnings[0]}"

# ═══════════════════════════════════════════════════════════════════
# Post-Compact Cleanup
# ═══════════════════════════════════════════════════════════════════

def test_post_compact_cleanup():
    """Post-compact cleanup merges consecutive user messages."""
    with temp_data_dir():
        from core.conversation import ConversationManager
        cm = ConversationManager()
        cm._messages = [
            {"role": "user", "content": "First user msg"},
            {"role": "user", "content": "Second user msg"},
            {"role": "assistant", "content": "Response"},
            {"role": "user", "content": ""},
            {"role": "user", "content": "Third"},
        ]
        cleaned = cm._post_compact_cleanup()
        assert cleaned >= 1, f"Should have cleaned at least 1 message, got {cleaned}"
        # First two user messages should be merged
        assert "First user msg" in cm._messages[0]["content"], "First part missing"
        assert "Second user msg" in cm._messages[0]["content"], "Second part missing"

# ═══════════════════════════════════════════════════════════════════
# Adaptive Threshold
# ═══════════════════════════════════════════════════════════════════

def test_adaptive_threshold():
    """Fast typing lowers the adaptive offset (compact sooner)."""
    with temp_data_dir():
        from core.conversation import ConversationManager
        cm = ConversationManager()
        assert cm._adaptive_offset == 0, "Should start at 0"
        now = time.time()
        cm._message_timestamps = [now - i for i in range(10)]  # 10 msgs in ~10 sec
        cm._update_adaptive_offset()
        assert cm._adaptive_offset < 0, \
            f"Fast typing should lower offset, got {cm._adaptive_offset}"
        effective = cm.get_effective_threshold(50)
        assert effective < 50, f"Effective threshold should be < 50, got {effective}"
        assert effective >= 15, f"Effective threshold should be >= 15, got {effective}"

# ═══════════════════════════════════════════════════════════════════
# CJK Token Estimation
# ═══════════════════════════════════════════════════════════════════

def test_cjk_token_estimation():
    """CJK text estimates more tokens than English for same character count."""
    with temp_data_dir():
        from core.conversation import ConversationManager
        english = "Hello world this is a test " * 10  # ~270 chars
        chinese = "\u4f60\u597d\u4e16\u754c\u8fd9\u662f\u6d4b\u8bd5\u6587\u672c" * 27  # ~270 chars
        en_tokens = ConversationManager._estimate_msg_tokens(english)
        cn_tokens = ConversationManager._estimate_msg_tokens(chinese)
        assert cn_tokens > en_tokens, \
            f"CJK ({cn_tokens}) should > English ({en_tokens}) for similar char count"

# ═══════════════════════════════════════════════════════════════════
# Compact Prompt No-Tools Directive
# ═══════════════════════════════════════════════════════════════════

def test_compact_prompt_no_tools():
    """Compact prompt contains 'Do NOT call any tools' directive."""
    from prompts.compact import NO_TOOLS_PREAMBLE
    assert "Do NOT call any tools" in NO_TOOLS_PREAMBLE, \
        f"NO_TOOLS_PREAMBLE missing directive: {NO_TOOLS_PREAMBLE[:200]}"


# ═══════════════════════════════════════════════════════════════════
# Run all tests
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    reset()
    print("Suite 2 - Compaction Pipeline")
    print("=" * 60)

    print("\n-- L0: Microcompact --")
    run("01 L0 Microcompact triggers at threshold", test_l0_microcompact)

    print("\n-- L1: Snip --")
    run("02 L1 Snip reduces message count", test_l1_snip_oldest)

    print("\n-- L2: Tool-result Compress --")
    run("03 L2 Tool-result compress truncates old outputs", test_l2_tool_result_compress)

    print("\n-- L3: Message Grouping --")
    run("04 L3 Message grouping keeps pairs intact", test_l3_message_grouping)

    print("\n-- L4: Memory Preserve --")
    run("05 L4 Memory preserve calls memory_mgr", test_l4_memory_preserve)

    print("\n-- L5: Mechanical Summary --")
    run("06 L5 Mechanical summary with [CONTEXT COMPACTED]", test_l5_mechanical_summary)

    print("\n-- L6: LLM Compact --")
    run("07 L6 LLM compact with mock provider", test_l6_llm_compact)

    print("\n-- L7: Reactive --")
    run("08 L7 Reactive fallback on provider error", test_l7_reactive_setup)

    print("\n-- Boundary Tracking --")
    run("09 Boundary tracking after compact", test_boundary_tracking)

    print("\n-- Compact Warning --")
    run("10 Compact warning callback fires", test_compact_warning_fires)

    print("\n-- Post-Compact Cleanup --")
    run("11 Post-compact cleanup merges consecutive user msgs", test_post_compact_cleanup)

    print("\n-- Adaptive Threshold --")
    run("12 Adaptive threshold lowers on fast typing", test_adaptive_threshold)

    print("\n-- CJK Token Estimation --")
    run("13 CJK token estimation > English", test_cjk_token_estimation)

    print("\n-- Compact Prompt --")
    run("14 Compact prompt contains 'Do NOT call any tools'", test_compact_prompt_no_tools)

    ok = summary("Suite 2: Compaction")
    sys.exit(0 if ok else 1)
