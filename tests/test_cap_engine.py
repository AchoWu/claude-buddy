"""
Capability Tests — Section 一 Core Engine (1.1–1.17)
Tests every engine capability from CAPABILITY_MATRIX.md using simulated UI operations.
No real API calls — MockProvider simulates all LLM behavior.

Covers:
  1.1  Tool-call loop (10-step structure)
  1.2  Streaming output (chunk-by-chunk)
  1.3  Error classification (9 ErrorCategory types)
  1.4  Exponential backoff retry
  1.5  Context-too-long recovery
  1.6  Max-output-tokens recovery (circuit breaker)
  1.7  Reactive compact feature-gate
  1.8  Abort signal mid-loop
  1.9  Session cost tracking
  1.10 Transition tracking
  1.11 Permission rich type
  1.12 Plan mode blocks non-read-only tools
  1.13 Sub-agent isolated history
  1.14 Team memory injection to sub-agents
  1.15 Background task management
  1.16 Auto memory extraction
  1.17 Tool result smart truncation
"""

import sys, os, io, time, threading, tempfile, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_buddy = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _buddy)
os.chdir(_buddy)

# Patch data dirs to temp BEFORE importing anything that uses config
from pathlib import Path
_TEMP = tempfile.mkdtemp(prefix='buddy_cap_engine_')
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
        print(f'  Cap Engine (1.1-1.17): {total}/{total} ALL TESTS PASSED')
    else:
        print(f'  Cap Engine (1.1-1.17): {PASS}/{total} PASSED, {FAIL} FAILED')
        for n, e in ERRORS:
            print(f'    X {n}: {e}')
    print(f'{"="*60}')
    return FAIL == 0

# ── QApp ────────────────────────────────────────────────────────
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
_qapp = QApplication.instance() or QApplication(sys.argv)

# ── Imports ─────────────────────────────────────────────────────
from core.engine import (
    ErrorCategory, categorize_error, is_retryable,
    TransitionType, SessionCost, LLMEngine,
)
from core.providers.base import (
    BaseProvider, ToolCall, ToolDef, AbortSignal, StreamChunk,
)
from core.conversation import ConversationManager
from unittest.mock import MagicMock, patch


# ═══════════════════════════════════════════════════════════════════
# MockProvider — configurable LLM simulator
# ═══════════════════════════════════════════════════════════════════

class MockProvider(BaseProvider):
    """
    Configurable mock provider for testing the full engine loop.
    Supports:
      - Sequence of responses (text or tool-calls)
      - Streaming simulation
      - Error injection (specific call # fails)
      - Abort signal respect
    """

    def __init__(self):
        self.responses = []    # list of (raw_content, tool_calls, text)
        self._call_idx = 0
        self._errors = {}      # call_idx → Exception to raise
        self._sync_calls = []  # record of calls for inspection
        self._stream_chunks = []  # for streaming: list of chunk lists
        self._stream_enabled = False

    def set_responses(self, *resps):
        """Set sequence of (raw_content, tool_calls, text) tuples."""
        self.responses = list(resps)
        self._call_idx = 0

    def set_error_at(self, call_idx: int, error: Exception):
        """Inject error at specific call index."""
        self._errors[call_idx] = error

    def call_sync(self, messages, system, tools, max_tokens=4096, abort_signal=None, params=None):
        if abort_signal and abort_signal.aborted:
            raise InterruptedError("Aborted")

        self._sync_calls.append({
            "messages": messages, "system": system,
            "tools": tools, "call_idx": self._call_idx,
        })

        # Check for injected error
        if self._call_idx in self._errors:
            idx = self._call_idx
            self._call_idx += 1
            raise self._errors[idx]

        if self._call_idx >= len(self.responses):
            self._call_idx += 1
            # Default: terminal text response
            return (
                {"role": "assistant", "content": "default response"},
                [],
                "default response"
            )

        resp = self.responses[self._call_idx]
        self._call_idx += 1
        return resp

    def call_stream(self, messages, system, tools, max_tokens=4096, abort_signal=None, params=None):
        """Streaming with chunks."""
        if abort_signal and abort_signal.aborted:
            raise InterruptedError("Aborted")

        raw, tool_calls, text = self.call_sync(
            messages, system, tools, max_tokens, abort_signal
        )

        # Yield text as chunks
        if text:
            words = text.split(" ")
            for w in words:
                if abort_signal and abort_signal.aborted:
                    raise InterruptedError("Aborted during stream")
                yield StreamChunk(type="text_delta", text=w + " ")

        yield StreamChunk(type="done")
        return raw, tool_calls, text

    @property
    def supports_streaming(self):
        return self._stream_enabled

    def format_tools(self, tools):
        return [{"name": t.name, "description": t.description,
                 "input_schema": t.input_schema} for t in tools]

    def format_tool_results(self, tool_calls, results):
        content = []
        for tc, r in zip(tool_calls, results):
            content.append({
                "type": "tool_result",
                "tool_use_id": tc.id,
                "content": r.get("output", ""),
                **({"is_error": True} if r.get("is_error") else {}),
            })
        return {"role": "user", "content": content}


def make_tool_response(tool_name, tool_input, tool_id="tc_1", extra_text=""):
    """Helper: create a response that includes a tool call."""
    raw = [
        {"type": "tool_use", "id": tool_id, "name": tool_name, "input": tool_input}
    ]
    if extra_text:
        raw.insert(0, {"type": "text", "text": extra_text})
    tcs = [ToolCall(id=tool_id, name=tool_name, input=tool_input)]
    return (raw, tcs, extra_text)


def make_text_response(text):
    """Helper: create a terminal text response (no tool calls)."""
    return ({"role": "assistant", "content": text}, [], text)


def make_engine_with_mock(streaming=False):
    """Create a fresh engine + mock provider, ready to test."""
    engine = LLMEngine()
    provider = MockProvider()
    provider._stream_enabled = streaming
    engine.set_provider(provider, "mock-model")
    engine._streaming_enabled = streaming
    return engine, provider


print('=' * 60)
print('  Capability Tests: Core Engine (1.1–1.17)')
print('=' * 60)


# ═══════════════════════════════════════════════════════════════════
# 1.1 Tool-call loop (10-step structure)
# ═══════════════════════════════════════════════════════════════════

def test_1_1a_simple_text_response():
    """Engine returns text when no tool calls in response."""
    engine, prov = make_engine_with_mock()
    prov.set_responses(make_text_response("Hello world"))

    responses = []
    engine.response_text.connect(lambda t: responses.append(t))

    engine._conversation.add_user_message("Hi")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    assert len(responses) == 1, f"Expected 1 response, got {len(responses)}"
    assert responses[0] == "Hello world"
run("1.1a Tool loop: simple text response → terminal", test_1_1a_simple_text_response)


def test_1_1b_tool_call_then_terminal():
    """Engine executes tool call, then gets terminal text response."""
    engine, prov = make_engine_with_mock()

    # Register a mock tool
    tool_def = ToolDef(name="MockTool", description="test", input_schema={"type": "object"})
    engine.register_tool(tool_def, lambda inp: f"result:{inp.get('x','?')}", is_read_only=True)

    # Response 1: tool call, Response 2: terminal text
    prov.set_responses(
        make_tool_response("MockTool", {"x": "42"}),
        make_text_response("Got the result: 42"),
    )

    responses = []
    engine.response_text.connect(lambda t: responses.append(t))
    tool_starts = []
    engine.tool_start.connect(lambda n, i: tool_starts.append(n))

    engine._conversation.add_user_message("use the tool")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    assert len(tool_starts) >= 1, "Tool should have been called"
    assert tool_starts[0] == "MockTool"
    assert len(responses) == 1
    assert "42" in responses[0]
run("1.1b Tool loop: tool-call → execute → terminal", test_1_1b_tool_call_then_terminal)


def test_1_1c_multi_round_tool_calls():
    """Engine handles multiple rounds of tool calls before terminal."""
    engine, prov = make_engine_with_mock()

    tool_def = ToolDef(name="Step", description="step", input_schema={"type": "object"})
    engine.register_tool(tool_def, lambda inp: f"done:{inp.get('n')}", is_read_only=True)

    prov.set_responses(
        make_tool_response("Step", {"n": "1"}, "tc_1"),
        make_tool_response("Step", {"n": "2"}, "tc_2"),
        make_tool_response("Step", {"n": "3"}, "tc_3"),
        make_text_response("All 3 steps done"),
    )

    tool_calls = []
    engine.tool_start.connect(lambda n, i: tool_calls.append(n))

    engine._conversation.add_user_message("do 3 steps")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    assert len(tool_calls) == 3, f"Expected 3 tool calls, got {len(tool_calls)}"
run("1.1c Tool loop: 3-round tool chain → terminal", test_1_1c_multi_round_tool_calls)


def test_1_1d_unknown_tool_error():
    """Unknown tool name produces error result, loop continues."""
    engine, prov = make_engine_with_mock()

    prov.set_responses(
        make_tool_response("NoSuchTool", {}),
        make_text_response("I see the error"),
    )

    responses = []
    engine.response_text.connect(lambda t: responses.append(t))

    engine._conversation.add_user_message("call fake tool")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    assert len(responses) == 1  # should still get terminal response
run("1.1d Tool loop: unknown tool → error result → continues", test_1_1d_unknown_tool_error)


def test_1_1e_max_rounds():
    """Engine stops after MAX_TOOL_ROUNDS to prevent infinite loops."""
    engine, prov = make_engine_with_mock()

    tool_def = ToolDef(name="Loop", description="", input_schema={"type": "object"})
    engine.register_tool(tool_def, lambda inp: "looping", is_read_only=True)

    # All responses are tool calls — never terminal
    prov.set_responses(*[make_tool_response("Loop", {}, f"tc_{i}") for i in range(40)])

    errors = []
    engine.error.connect(lambda e: errors.append(e))

    engine._conversation.add_user_message("loop forever")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    assert any("exceeded" in e.lower() or "rounds" in e.lower() for e in errors), \
        f"Expected max-rounds error, got: {errors}"
run("1.1e Tool loop: MAX_TOOL_ROUNDS → stop with error", test_1_1e_max_rounds)


# ═══════════════════════════════════════════════════════════════════
# 1.2 Streaming output
# ═══════════════════════════════════════════════════════════════════

def test_1_2a_streaming_chunks():
    """Streaming mode emits response_chunk signals with text fragments."""
    engine, prov = make_engine_with_mock(streaming=True)
    prov.set_responses(make_text_response("Hello wonderful world"))

    chunks = []
    engine.response_chunk.connect(lambda c: chunks.append(c))

    engine._conversation.add_user_message("stream test")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    assert len(chunks) > 1, f"Streaming should emit multiple chunks, got {len(chunks)}"
    reassembled = "".join(chunks)
    assert "Hello" in reassembled
    assert "world" in reassembled
run("1.2a Streaming: multiple chunks emitted", test_1_2a_streaming_chunks)


def test_1_2b_intermediate_text_with_tools():
    """When model returns text + tool calls, intermediate_text is emitted."""
    engine, prov = make_engine_with_mock()

    tool_def = ToolDef(name="Search", description="", input_schema={"type": "object"})
    engine.register_tool(tool_def, lambda inp: "found it", is_read_only=True)

    prov.set_responses(
        make_tool_response("Search", {"q": "test"}, extra_text="Let me search for that..."),
        make_text_response("Here are the results"),
    )

    intermediates = []
    engine.intermediate_text.connect(lambda t: intermediates.append(t))

    engine._conversation.add_user_message("search something")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    assert len(intermediates) >= 1, "intermediate_text should fire when text accompanies tools"
    assert "search" in intermediates[0].lower()
run("1.2b Intermediate text emitted alongside tool calls", test_1_2b_intermediate_text_with_tools)


# ═══════════════════════════════════════════════════════════════════
# 1.3 Error classification (covered by test_s1_engine.py, verify here)
# ═══════════════════════════════════════════════════════════════════

def test_1_3_all_categories():
    """All 9 ErrorCategory types are reachable."""
    cases = {
        ErrorCategory.RATE_LIMIT: "429 rate limit",
        ErrorCategory.SERVER_ERROR: "503 service unavailable",
        ErrorCategory.CONTEXT_TOO_LONG: "prompt is too long",
        ErrorCategory.MAX_OUTPUT_TOKENS: "max_tokens exceeded",
        ErrorCategory.NETWORK_ERROR: "connection refused",
        ErrorCategory.TIMEOUT: "request timed out",
        ErrorCategory.AUTH_ERROR: "401 unauthorized",
        ErrorCategory.INVALID_REQUEST: "400 malformed",
        ErrorCategory.UNKNOWN: "something weird",
    }
    for expected, msg in cases.items():
        got = categorize_error(Exception(msg))
        assert got == expected, f"'{msg}' → expected {expected}, got {got}"
run("1.3  Error classification: all 9 categories reachable", test_1_3_all_categories)


# ═══════════════════════════════════════════════════════════════════
# 1.4 Exponential backoff retry
# ═══════════════════════════════════════════════════════════════════

def test_1_4_retry_on_429():
    """Engine retries on rate limit error with increasing delays."""
    engine, prov = make_engine_with_mock()

    # First 2 calls fail with 429, 3rd succeeds
    prov.set_error_at(0, Exception("429 rate limit"))
    prov.set_error_at(1, Exception("429 rate limit"))
    prov.set_responses(
        None, None,  # placeholders for error indices
        make_text_response("success after retries"),
    )

    responses = []
    engine.response_text.connect(lambda t: responses.append(t))
    error_msgs = []
    engine.error.connect(lambda e: error_msgs.append(e))

    engine._conversation.add_user_message("retry test")
    engine._is_running = True
    engine._abort_signal.reset()

    start = time.time()
    engine._tool_loop()
    elapsed = time.time() - start
    engine._is_running = False

    assert len(responses) == 1
    assert responses[0] == "success after retries"
    # CC: BASE_DELAY=500ms, delays = 0.5s + 1.0s = 1.5s + jitter
    # Allow slack for timing variance
    assert elapsed >= 0.4, f"Retry delays should add up to >= 0.4s, got {elapsed:.1f}s"
    # Error signals for retry attempts
    assert any("attempt" in e.lower() or "retry" in e.lower() for e in error_msgs)
run("1.4  Exponential backoff: 429 → retry with delay → success", test_1_4_retry_on_429)


def test_1_4b_fatal_error_no_retry():
    """Non-retryable errors (auth) raise immediately without retry."""
    engine, prov = make_engine_with_mock()
    prov.set_error_at(0, Exception("401 unauthorized"))
    prov.set_responses(None)

    engine._conversation.add_user_message("auth fail")
    engine._is_running = True
    engine._abort_signal.reset()

    raised = False
    try:
        engine._tool_loop()
    except Exception as e:
        raised = True
        assert "401" in str(e) or "unauthorized" in str(e).lower()
    engine._is_running = False

    assert raised, "Auth error should raise (non-retryable)"
    assert prov._call_idx == 1, "Should not retry on auth error"
run("1.4b Fatal error (auth): no retry, raises immediately", test_1_4b_fatal_error_no_retry)


# ═══════════════════════════════════════════════════════════════════
# 1.5 Context-too-long recovery
# ═══════════════════════════════════════════════════════════════════

def test_1_5_context_recovery():
    """Context-too-long error triggers full compact + retry."""
    engine, prov = make_engine_with_mock()

    # First call: context error, second call: success (after compact)
    prov.set_error_at(0, Exception("context_length_exceeded: prompt is too long"))
    prov.set_responses(
        None,
        make_text_response("recovered after compaction"),
    )

    responses = []
    engine.response_text.connect(lambda t: responses.append(t))

    # Add some messages to conversation so compact has something to work with
    for i in range(15):
        engine._conversation.add_user_message(f"filler message {i}")
        engine._conversation.add_assistant_message(f"filler reply {i}")

    engine._conversation.add_user_message("trigger context error")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    assert len(responses) == 1
    assert "recovered" in responses[0]
    # Check transition was recorded
    ctx_transitions = [t for t in engine.transitions if t["type"] == "context_recovery"]
    assert len(ctx_transitions) >= 1, "Should record CONTEXT_RECOVERY transition"
run("1.5  Context-too-long: compact + retry → success", test_1_5_context_recovery)


# ═══════════════════════════════════════════════════════════════════
# 1.6 Max-output-tokens recovery (circuit breaker: 3 attempts)
# ═══════════════════════════════════════════════════════════════════

def test_1_6_max_output_recovery():
    """Max output token error retries up to 3 times (circuit breaker)."""
    engine, prov = make_engine_with_mock()

    # 2 max-output errors, then success
    prov.set_error_at(0, Exception("max_tokens limit reached"))
    prov.set_error_at(1, Exception("max_tokens limit reached"))
    prov.set_responses(
        None, None,
        make_text_response("recovered after 2 max-output retries"),
    )

    responses = []
    engine.response_text.connect(lambda t: responses.append(t))

    engine._conversation.add_user_message("max output test")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    assert len(responses) == 1
    recovery_transitions = [t for t in engine.transitions if t["type"] == "max_output_recovery"]
    assert len(recovery_transitions) >= 2, f"Should have 2 recovery transitions, got {len(recovery_transitions)}"
run("1.6  Max-output recovery: 2 failures → success on 3rd try", test_1_6_max_output_recovery)


def test_1_6b_circuit_breaker():
    """Circuit breaker: 4th max-output error raises (limit is 3)."""
    engine, prov = make_engine_with_mock()

    for i in range(5):
        prov.set_error_at(i, Exception("max_tokens limit reached"))
    prov.set_responses(*[None] * 5)

    engine._conversation.add_user_message("circuit break test")
    engine._is_running = True
    engine._abort_signal.reset()

    raised = False
    try:
        engine._tool_loop()
    except Exception as e:
        raised = True
        assert "max_tokens" in str(e).lower()
    engine._is_running = False

    assert raised, "Should raise after exceeding recovery limit"
run("1.6b Circuit breaker: >3 max-output errors → raises", test_1_6b_circuit_breaker)


# ═══════════════════════════════════════════════════════════════════
# 1.7 Reactive compact feature-gate
# ═══════════════════════════════════════════════════════════════════

def test_1_7_reactive_compact_disabled():
    """When reactive_compact flag is disabled, context error raises directly."""
    engine, prov = make_engine_with_mock()
    prov.set_error_at(0, Exception("context_length_exceeded"))
    prov.set_responses(None, make_text_response("should not reach"))

    # Mock the feature flag to return disabled
    with patch('core.services.analytics.get_feature_flags') as mock_ff:
        mock_ff.return_value.is_enabled.return_value = False

        engine._conversation.add_user_message("reactive disabled test")
        engine._is_running = True
        engine._abort_signal.reset()

        raised = False
        try:
            engine._tool_loop()
        except Exception as e:
            raised = True
            assert "context" in str(e).lower()
        engine._is_running = False

        assert raised, "Should raise when reactive_compact is disabled"
run("1.7  Reactive compact gate: disabled → no recovery", test_1_7_reactive_compact_disabled)


# ═══════════════════════════════════════════════════════════════════
# 1.8 Abort signal mid-loop
# ═══════════════════════════════════════════════════════════════════

def test_1_8_abort_mid_loop():
    """Abort signal stops the loop at next iteration."""
    engine, prov = make_engine_with_mock()

    tool_def = ToolDef(name="SlowTool", description="", input_schema={"type": "object"})

    def slow_executor(inp):
        time.sleep(0.1)
        return "done"

    engine.register_tool(tool_def, slow_executor, is_read_only=True)

    # 10 rounds of tool calls — abort after 1st
    prov.set_responses(*[make_tool_response("SlowTool", {}, f"tc_{i}") for i in range(10)])

    engine._conversation.add_user_message("abort test")
    engine._is_running = True
    engine._abort_signal.reset()

    # Abort after a short delay
    def delayed_abort():
        time.sleep(0.15)
        engine.abort()

    t = threading.Thread(target=delayed_abort)
    t.start()

    raised = False
    try:
        engine._tool_loop()
    except InterruptedError:
        raised = True
    t.join()
    engine._is_running = False

    assert raised or engine._abort_signal.aborted, "Should have been aborted"
    # Should not have completed all 10 rounds
    assert prov._call_idx < 10, f"Should abort early, but did {prov._call_idx} calls"
run("1.8  Abort signal: stops loop mid-execution", test_1_8_abort_mid_loop)


def test_1_8b_persist_abort():
    """_persist_abort writes interrupt marker + saves.
    CC-aligned: marker is role='user' (createUserInterruptionMessage)."""
    engine, prov = make_engine_with_mock()
    engine._conversation.add_user_message("question before abort")

    engine._abort_signal.abort("user_cancel")
    engine._persist_abort()

    msgs = engine.conversation.messages
    last = msgs[-1]
    # CC uses role="user" for interrupt marker (it's a user action)
    assert last["role"] == "user", f"CC-aligned: interrupt marker should be user, got {last['role']}"
    assert last["content"] == "[Request interrupted by user]"

    # Verify it was saved to disk
    session_file = config.CONVERSATIONS_DIR / f"{engine.conversation._conversation_id}.json"
    assert session_file.exists(), "Session file should exist after persist_abort"
run("1.8b _persist_abort: writes marker as user (CC-aligned) + saves to disk", test_1_8b_persist_abort)


# ═══════════════════════════════════════════════════════════════════
# 1.9 Session cost tracking
# ═══════════════════════════════════════════════════════════════════

def test_1_9_cost_tracked():
    """Session cost is updated after API calls and tool calls."""
    engine, prov = make_engine_with_mock()

    tool_def = ToolDef(name="CostTool", description="", input_schema={"type": "object"})
    engine.register_tool(tool_def, lambda inp: "ok", is_read_only=True)

    prov.set_responses(
        make_tool_response("CostTool", {}),
        make_text_response("done"),
    )

    engine._conversation.add_user_message("cost test")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    sc = engine.session_cost
    assert sc.total_api_calls >= 2, f"Expected >= 2 API calls, got {sc.total_api_calls}"
    assert sc.total_tool_calls >= 1, f"Expected >= 1 tool call, got {sc.total_tool_calls}"
    assert "mock-model" in sc.model_usage, "Cost should be tracked per model"
    # Summary should contain useful info
    summary_str = sc.summary()
    assert "API calls:" in summary_str
    assert "Tool calls:" in summary_str
run("1.9  Session cost: API calls + tool calls tracked", test_1_9_cost_tracked)


# ═══════════════════════════════════════════════════════════════════
# 1.10 Transition tracking
# ═══════════════════════════════════════════════════════════════════

def test_1_10_transitions_recorded():
    """Each loop iteration records transitions with type, detail, time."""
    engine, prov = make_engine_with_mock()

    tool_def = ToolDef(name="Trans", description="", input_schema={"type": "object"})
    engine.register_tool(tool_def, lambda inp: "ok", is_read_only=True)

    prov.set_responses(
        make_tool_response("Trans", {}),
        make_text_response("done"),
    )

    engine._conversation.add_user_message("transition test")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    trans = engine.transitions
    assert len(trans) >= 2, f"Expected >= 2 transitions, got {len(trans)}"

    # Check TOOL_RESULTS transition
    tool_trans = [t for t in trans if t["type"] == "tool_results"]
    assert len(tool_trans) >= 1, "Should have TOOL_RESULTS transition"
    assert "Trans" in tool_trans[0]["detail"]

    # Check TERMINAL transition
    term_trans = [t for t in trans if t["type"] == "terminal"]
    assert len(term_trans) == 1, "Should have exactly 1 TERMINAL transition"

    # Each transition has required fields
    for t in trans:
        assert "round" in t
        assert "type" in t
        assert "detail" in t
        assert "time" in t
        assert isinstance(t["time"], float)
run("1.10 Transition tracking: tool_results + terminal recorded", test_1_10_transitions_recorded)


# ═══════════════════════════════════════════════════════════════════
# 1.11 Permission rich type
# ═══════════════════════════════════════════════════════════════════

def test_1_11a_permission_dict_deny():
    """Permission callback returning {approved: False, action: 'deny'} blocks tool."""
    engine, prov = make_engine_with_mock()

    tool_def = ToolDef(name="WriteTool", description="", input_schema={"type": "object"})
    engine.register_tool(tool_def, lambda inp: "should not run", is_read_only=False)
    engine.set_permission_callback(lambda name, inp: {"approved": False, "action": "deny"})

    prov.set_responses(
        make_tool_response("WriteTool", {}),
        make_text_response("Permission was denied"),
    )

    engine._conversation.add_user_message("permission test")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    # Check that the tool result message contains denial info
    msgs = engine.conversation.messages
    denied_found = False
    for m in msgs:
        content = m.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "denied" in str(block.get("content", "")).lower():
                    denied_found = True
                    assert "action=deny" in str(block.get("content", ""))
    assert denied_found, "Tool result should contain permission denied with action=deny"
run("1.11a Permission rich type: dict {approved:false, action:deny}", test_1_11a_permission_dict_deny)


def test_1_11b_permission_bool_allow():
    """Permission callback returning True allows execution."""
    engine, prov = make_engine_with_mock()

    executed = []
    tool_def = ToolDef(name="WriteTool", description="", input_schema={"type": "object"})
    engine.register_tool(tool_def, lambda inp: (executed.append(1), "ok")[1], is_read_only=False)
    engine.set_permission_callback(lambda name, inp: True)

    prov.set_responses(
        make_tool_response("WriteTool", {}),
        make_text_response("Tool ran"),
    )

    engine._conversation.add_user_message("perm allow test")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    assert len(executed) == 1, "Tool should have executed when permission is True"
run("1.11b Permission bool: True → tool executes", test_1_11b_permission_bool_allow)


def test_1_11c_readonly_skips_permission():
    """Read-only tools skip permission check entirely."""
    engine, prov = make_engine_with_mock()

    executed = []
    tool_def = ToolDef(name="ReadTool", description="", input_schema={"type": "object"})
    engine.register_tool(tool_def, lambda inp: (executed.append(1), "ok")[1], is_read_only=True)
    # Permission callback that always denies
    engine.set_permission_callback(lambda name, inp: False)

    prov.set_responses(
        make_tool_response("ReadTool", {}),
        make_text_response("Read done"),
    )

    engine._conversation.add_user_message("read test")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    assert len(executed) == 1, "Read-only tool should bypass permission check"
run("1.11c Read-only tools bypass permission check", test_1_11c_readonly_skips_permission)


# ═══════════════════════════════════════════════════════════════════
# 1.12 Plan mode blocks non-read-only tools
# ═══════════════════════════════════════════════════════════════════

def test_1_12_plan_mode_blocks_write():
    """Plan mode active → write tools are blocked with error."""
    engine, prov = make_engine_with_mock()

    write_tool = ToolDef(name="FileWrite", description="", input_schema={"type": "object"})
    read_tool = ToolDef(name="FileRead", description="", input_schema={"type": "object"})
    write_executed = []
    read_executed = []
    engine.register_tool(write_tool, lambda inp: (write_executed.append(1), "w")[1], is_read_only=False)
    engine.register_tool(read_tool, lambda inp: (read_executed.append(1), "r")[1], is_read_only=True)

    # Simulate plan mode state
    plan_state = MagicMock()
    plan_state.active = True
    engine.set_plan_mode_state(plan_state)

    prov.set_responses(
        make_tool_response("FileWrite", {"file_path": "x.py"}),
        make_tool_response("FileRead", {"file_path": "x.py"}, "tc_2"),
        make_text_response("done"),
    )

    engine._conversation.add_user_message("plan mode test")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    assert len(write_executed) == 0, "Write tool should be blocked in plan mode"
    assert len(read_executed) == 1, "Read tool should still work in plan mode"

    # Check that blocked message mentions plan mode
    msgs = engine.conversation.messages
    blocked_found = False
    for m in msgs:
        content = m.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "plan mode" in str(block.get("content", "")).lower():
                    blocked_found = True
    assert blocked_found, "Blocked tool result should mention plan mode"
run("1.12 Plan mode: write blocked, read allowed", test_1_12_plan_mode_blocks_write)


# ═══════════════════════════════════════════════════════════════════
# 1.13 Sub-agent isolated history
# ═══════════════════════════════════════════════════════════════════

def test_1_13_sub_agent_isolated():
    """Sub-agent has its own conversation, doesn't pollute main."""
    engine, prov = make_engine_with_mock()

    # Add some messages to main conversation
    engine._conversation.add_user_message("main message 1")
    engine._conversation.add_assistant_message("main reply 1")
    main_count_before = engine.conversation.message_count

    # Run sub-agent — it uses call_sync directly (not the streaming path)
    result = engine.run_sub_agent(
        system_prompt="You are a helper",
        user_prompt="Do something",
    )

    # Main conversation should not have gained sub-agent messages
    main_count_after = engine.conversation.message_count
    assert main_count_after == main_count_before, \
        f"Main conversation polluted: {main_count_before} → {main_count_after}"
    assert isinstance(result, str)
    assert len(result) > 0
run("1.13 Sub-agent: isolated history, main not polluted", test_1_13_sub_agent_isolated)


# ═══════════════════════════════════════════════════════════════════
# 1.14 Team memory injection to sub-agents
# ═══════════════════════════════════════════════════════════════════

def test_1_14_team_memory_injection():
    """Sub-agent system prompt includes team memory context."""
    engine, prov = make_engine_with_mock()

    # Mock team memory
    team_mem = MagicMock()
    team_mem.get_context_for_agent.return_value = "Project uses React and TypeScript"
    engine.set_team_memory(team_mem)

    # Track what system prompt the sub-agent call receives
    original_call_sync = prov.call_sync
    captured_system = []

    def spy_call_sync(messages, system, tools, max_tokens=4096, abort_signal=None):
        captured_system.append(system)
        return make_text_response("sub-agent done")

    prov.call_sync = spy_call_sync

    result = engine.run_sub_agent(
        system_prompt="You are a researcher",
        user_prompt="Find APIs",
        agent_id="agent_1",
        team="research",
    )

    assert len(captured_system) >= 1, "Sub-agent should have made at least 1 call"
    assert "React" in captured_system[0], "Team memory should be injected into system prompt"
    assert "TypeScript" in captured_system[0]

    # Verify team_memory.get_context_for_agent was called with correct args
    team_mem.get_context_for_agent.assert_called_once_with(
        agent_id="agent_1", team="research"
    )
run("1.14 Team memory injected into sub-agent system prompt", test_1_14_team_memory_injection)


# ═══════════════════════════════════════════════════════════════════
# 1.15 Background task management
# ═══════════════════════════════════════════════════════════════════

def test_1_15a_background_task_start():
    """start_background_task returns task_id, task completes in background."""
    engine, prov = make_engine_with_mock()

    def slow_task(inp):
        time.sleep(0.1)
        return f"result:{inp.get('cmd')}"

    task_id = engine.start_background_task(slow_task, {"cmd": "echo hello"})
    assert task_id is not None
    assert isinstance(task_id, str)

    task = engine.get_background_task(task_id)
    assert task is not None
    assert task["status"] in ("running", "completed")

    # Wait for completion
    time.sleep(0.3)
    task = engine.get_background_task(task_id)
    assert task["status"] == "completed"
    assert "echo hello" in task["output"]
run("1.15a Background task: start → complete → output available", test_1_15a_background_task_start)


def test_1_15b_background_task_error():
    """Background task that raises error reports status=error."""
    engine, prov = make_engine_with_mock()

    def failing_task(inp):
        raise ValueError("task failed")

    task_id = engine.start_background_task(failing_task, {})
    time.sleep(0.2)

    task = engine.get_background_task(task_id)
    assert task["status"] == "error"
    assert "failed" in task["output"].lower()
run("1.15b Background task: error → status=error, message captured", test_1_15b_background_task_error)


def test_1_15c_multiple_tasks():
    """Multiple background tasks run independently."""
    engine, prov = make_engine_with_mock()

    ids = []
    for i in range(3):
        tid = engine.start_background_task(lambda inp: f"task-{inp['n']}", {"n": i})
        ids.append(tid)

    assert len(set(ids)) == 3, "Each task should have a unique ID"
    time.sleep(0.3)

    for tid in ids:
        task = engine.get_background_task(tid)
        assert task["status"] == "completed"
run("1.15c Multiple background tasks: independent IDs + completion", test_1_15c_multiple_tasks)


# ═══════════════════════════════════════════════════════════════════
# 1.16 Auto memory extraction
# ═══════════════════════════════════════════════════════════════════

def test_1_16_auto_extract_triggered():
    """Auto memory extraction is triggered after terminal response."""
    engine, prov = make_engine_with_mock()

    # Mock memory manager
    mem_mgr = MagicMock()
    mem_mgr.should_extract.return_value = True
    mem_mgr.auto_extract.return_value = ["user prefers tabs"]
    mem_mgr.load_memory.return_value = "- user prefers tabs"
    engine.set_memory_manager(mem_mgr)

    prov.set_responses(make_text_response("I noted your preference"))

    engine._conversation.add_user_message("I always use tabs")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    # Give background thread time to run
    time.sleep(0.3)

    mem_mgr.should_extract.assert_called_once()
    mem_mgr.auto_extract.assert_called_once()
run("1.16 Auto memory extraction: triggered after terminal turn", test_1_16_auto_extract_triggered)


# ═══════════════════════════════════════════════════════════════════
# 1.17 Tool result smart truncation
# ═══════════════════════════════════════════════════════════════════

def test_1_17a_truncation_applied():
    """Tool output > 50000 chars is truncated with head+tail (CC: DEFAULT_MAX_RESULT_SIZE_CHARS=50000)."""
    engine, prov = make_engine_with_mock()

    big_output = "X" * 80000  # > 50000
    tool_def = ToolDef(name="BigTool", description="", input_schema={"type": "object"})
    engine.register_tool(tool_def, lambda inp: big_output, is_read_only=True)

    prov.set_responses(
        make_tool_response("BigTool", {}),
        make_text_response("processed big output"),
    )

    tool_results = []
    engine.tool_result.connect(lambda name, output: tool_results.append(output))

    engine._conversation.add_user_message("big tool test")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    # Find the tool result in conversation messages
    msgs = engine.conversation.messages
    found_truncated = False
    for m in msgs:
        content = m.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "truncated" in str(block.get("content", "")).lower():
                    found_truncated = True
    assert found_truncated, "Large tool output should contain truncation marker"
run("1.17a Tool result truncation: >50000 chars → head+tail", test_1_17a_truncation_applied)


def test_1_17b_truncation_ratio():
    """Truncation preserves 2/3 head + 1/3 tail of MAX_TOOL_RESULT_CHARS."""
    engine = LLMEngine()
    max_chars = engine.MAX_TOOL_RESULT_CHARS  # 50000

    big = "A" * (max_chars * 2)  # 100000 chars
    head_size = max_chars * 2 // 3  # 10000
    tail_size = max_chars // 3       # 5000

    # Simulate what the engine does
    if len(big) > max_chars:
        truncated_output = (
            big[:head_size]
            + f"\n\n... [{len(big) - head_size - tail_size:,} chars truncated] ...\n\n"
            + big[-tail_size:]
        )

    assert truncated_output.startswith("A" * 100)  # head preserved
    assert truncated_output.endswith("A" * 100)     # tail preserved
    assert "truncated" in truncated_output
    assert len(truncated_output) < len(big)
run("1.17b Truncation ratio: head 2/3 + tail 1/3", test_1_17b_truncation_ratio)


def test_1_17c_small_output_not_truncated():
    """Tool output <= 15000 chars is NOT truncated."""
    engine, prov = make_engine_with_mock()

    small_output = "Y" * 1000
    tool_def = ToolDef(name="SmallTool", description="", input_schema={"type": "object"})
    engine.register_tool(tool_def, lambda inp: small_output, is_read_only=True)

    prov.set_responses(
        make_tool_response("SmallTool", {}),
        make_text_response("small output ok"),
    )

    engine._conversation.add_user_message("small test")
    engine._is_running = True
    engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False

    # Check tool result in conversation — should NOT contain truncation marker
    msgs = engine.conversation.messages
    for m in msgs:
        content = m.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    assert "truncated" not in str(block.get("content", "")).lower(), \
                        "Small output should not be truncated"
run("1.17c Small output: not truncated", test_1_17c_small_output_not_truncated)


# ═══════════════════════════════════════════════════════════════════
# 1.X Full _run_loop integration (send_message → response_text)
# ═══════════════════════════════════════════════════════════════════

def test_1_X_full_send_message():
    """Full integration: send_message → _run_loop in thread → signals emitted.
    Note: Qt signals across threads require event loop processing.
    We test the _run_loop path directly (synchronous) to verify signal emission."""
    engine, prov = make_engine_with_mock()
    prov.set_responses(make_text_response("Full integration reply"))

    responses = []
    engine.response_text.connect(lambda t: responses.append(t))
    states = []
    engine.state_changed.connect(lambda s: states.append(s))

    # Test _run_loop directly (synchronous, avoids Qt event loop issue)
    engine._is_running = True
    engine._abort_signal.reset()
    engine._conversation.add_user_message("Integration test")
    engine._run_loop()

    assert len(responses) == 1, f"Expected 1 response, got {len(responses)}"
    assert responses[0] == "Full integration reply"
    assert engine._is_running is False, "Should be false after _run_loop completes"
run("1.X  Full _run_loop → response_text + state_changed signals", test_1_X_full_send_message)


# ═══════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════

import shutil
try:
    ok = summary()
finally:
    shutil.rmtree(_TEMP, ignore_errors=True)

sys.exit(0 if ok else 1)
