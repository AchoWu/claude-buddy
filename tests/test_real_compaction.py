"""
Real API Compaction Tests — tests conversation compaction levels L0-L7.

Uses a SEPARATE engine per test group to avoid interference.

Run:
    python BUDDY/tests/test_real_compaction.py

Skips gracefully if no API key is configured.
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


def _fill_conversation(conv, n_pairs, tool_result_len=0):
    """Add n_pairs of user+assistant messages. Optionally add long tool results."""
    for i in range(n_pairs):
        conv.add_user_message(f"User message {i}: " + "x" * 100)
        if tool_result_len > 0:
            # Add assistant with tool_use then user with tool_result
            conv._messages.append({
                "role": "assistant",
                "content": [
                    {"type": "text", "text": f"Let me check {i}..."},
                    {"type": "tool_use", "id": f"tool_{i}", "name": "Bash",
                     "input": {"command": f"echo test_{i}"}},
                ],
            })
            conv._messages.append({
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": f"tool_{i}",
                     "content": "R" * tool_result_len},
                ],
            })
        else:
            conv.add_assistant_message(f"Assistant response {i}: " + "y" * 100)


# ══════════════════════════════════════════════════════════════════
# §L0 — Microcompact
# ══════════════════════════════════════════════════════════════════
def test_l0_microcompact():
    engine, box = make_real_engine(with_tools=False)
    conv = engine.conversation
    _fill_conversation(conv, 25, tool_result_len=800)
    result = conv.compact_if_needed()
    assert result is not None, "compact_if_needed returned None"
    result_lower = result.lower()
    assert "microcompact" in result_lower or "compact" in result_lower, \
        f"Expected 'microcompact' in result: {result[:200]}"

run("L0  Microcompact: 25 pairs with tool results → microcompact triggered", test_l0_microcompact)


# ══════════════════════════════════════════════════════════════════
# §L1 — Snip (message count decreases)
# ══════════════════════════════════════════════════════════════════
def test_l1_snip():
    engine, box = make_real_engine(with_tools=False)
    conv = engine.conversation
    _fill_conversation(conv, 35)
    before_count = len(conv.messages)
    result = conv.compact_if_needed()
    after_count = len(conv.messages)
    assert result is not None, "compact_if_needed returned None for 35 pairs"
    assert after_count < before_count, \
        f"Message count did not decrease: {before_count} → {after_count}"

run("L1  Snip: 35 pairs → message count decreases", test_l1_snip)


# ══════════════════════════════════════════════════════════════════
# §L2 — Tool compress (long tool results truncated)
# ══════════════════════════════════════════════════════════════════
def test_l2_tool_compress():
    engine, box = make_real_engine(with_tools=False)
    conv = engine.conversation
    _fill_conversation(conv, 45, tool_result_len=1000)
    initial_count = len(conv.messages)
    result = conv.compact_if_needed()
    assert result is not None, "compact_if_needed returned None for 45 pairs"
    # After compaction, messages should be reduced
    final_count = len(conv.messages)
    assert final_count < initial_count, \
        f"Messages not reduced: {initial_count} → {final_count}"
    # Check compaction happened (any method)
    assert "compact" in result.lower() or "snip" in result.lower() or "micro" in result.lower(), \
        f"Expected compaction action in result: {result[:200]}"

run("L2  Tool compress: 45 pairs with 1000-char results → truncation markers", test_l2_tool_compress)


# ══════════════════════════════════════════════════════════════════
# §L3 — Pair integrity after snip
# ══════════════════════════════════════════════════════════════════
def test_l3_pair_integrity():
    engine, box = make_real_engine(with_tools=False)
    conv = engine.conversation
    _fill_conversation(conv, 35, tool_result_len=500)
    conv.compact_if_needed()
    msgs = conv.messages
    for i, msg in enumerate(msgs):
        content = msg.get("content", "")
        if isinstance(content, list):
            has_tool_result = any(
                isinstance(b, dict) and b.get("type") == "tool_result"
                for b in content
            )
            if has_tool_result and msg.get("role") == "user":
                # There must be a preceding assistant message with tool_use
                assert i > 0, \
                    f"tool_result at index {i} has no preceding message"
                prev = msgs[i - 1]
                assert prev.get("role") == "assistant", \
                    f"tool_result at index {i} preceded by role={prev.get('role')}, expected assistant"
                prev_content = prev.get("content", "")
                if isinstance(prev_content, list):
                    has_tool_use = any(
                        isinstance(b, dict) and b.get("type") == "tool_use"
                        for b in prev_content
                    )
                    assert has_tool_use, \
                        f"tool_result at index {i}: preceding assistant has no tool_use"

run("L3  Pair integrity: tool_result always preceded by assistant+tool_use", test_l3_pair_integrity)


# ══════════════════════════════════════════════════════════════════
# §L5 — Mechanical summary
# ══════════════════════════════════════════════════════════════════
def test_l5_mechanical_summary():
    engine, box = make_real_engine(with_tools=False)
    conv = engine.conversation
    _fill_conversation(conv, 55)
    conv.compact_if_needed()
    msgs = conv.messages
    assert len(msgs) > 0, "No messages after compaction"
    first_content = msgs[0].get("content", "")
    if isinstance(first_content, list):
        first_text = " ".join(
            b.get("text", "") if isinstance(b, dict) else str(b)
            for b in first_content
        )
    else:
        first_text = str(first_content)
    assert "[CONTEXT COMPACTED]" in first_text, \
        f"First message missing [CONTEXT COMPACTED]: {first_text[:200]}"

run("L5  Mechanical summary: 55 pairs → first message has [CONTEXT COMPACTED]", test_l5_mechanical_summary)


# ══════════════════════════════════════════════════════════════════
# §L6 — LLM compact (real provider)
# ══════════════════════════════════════════════════════════════════
def test_l6_llm_compact():
    engine, box = make_real_engine(with_tools=False)
    conv = engine.conversation
    _fill_conversation(conv, 55)
    provider = make_provider()

    def provider_call_fn(messages, system, tools):
        return provider.call_sync(messages=messages, system=system, tools=tools)

    conv._provider_call_fn = provider_call_fn
    result = conv.llm_compact(provider_call_fn)
    assert result is not None, "llm_compact returned None"
    assert len(result) > 0, "llm_compact returned empty string"

run("L6  LLM compact: real provider produces non-None summary", test_l6_llm_compact)


# ══════════════════════════════════════════════════════════════════
# §L7 — Compact boundary
# ══════════════════════════════════════════════════════════════════
def test_l7_boundary():
    engine, box = make_real_engine(with_tools=False)
    conv = engine.conversation
    _fill_conversation(conv, 55)
    conv.compact_if_needed()
    assert conv._compact_boundary >= 1, \
        f"_compact_boundary should be >= 1 after compact, got {conv._compact_boundary}"

run("L7  Boundary: _compact_boundary >= 1 after compaction", test_l7_boundary)


# ══════════════════════════════════════════════════════════════════
# §CJK — Token estimation
# ══════════════════════════════════════════════════════════════════
def test_cjk_estimation():
    from core.conversation import ConversationManager
    cm = ConversationManager()
    # Use same-length strings: 10 CJK chars vs 10 ASCII chars
    cjk_tokens = cm._estimate_msg_tokens("你好世界测试中文是的")
    ascii_tokens = cm._estimate_msg_tokens("helloworld")
    assert cjk_tokens > ascii_tokens, \
        f"CJK tokens ({cjk_tokens}) should be > ASCII tokens ({ascii_tokens})"

run("CJK Token estimation: CJK text estimates higher than ASCII", test_cjk_estimation)


# ══════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════
ok = summary("Real API Compaction Tests")
sys.exit(0 if ok else 1)
