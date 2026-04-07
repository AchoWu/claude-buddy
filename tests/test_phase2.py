"""
Phase 2 Verification — Engine integration of new parameters.
Tests: stop reason handling, response withholding, API key verification,
       529/ECONNRESET classification, streaming fallback.
"""
import sys, os, io, time, tempfile
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_buddy = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _buddy)
os.chdir(_buddy)

from pathlib import Path
_TEMP = tempfile.mkdtemp(prefix='buddy_p2_')
import config
config.DATA_DIR = Path(_TEMP)
config.CONVERSATIONS_DIR = Path(_TEMP) / "conversations"
config.CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
config.INPUT_HISTORY_FILE = Path(_TEMP) / "input_history.json"

PASS = 0; FAIL = 0; ERRORS = []
def run(name, fn):
    global PASS, FAIL
    try: fn(); PASS += 1; print(f'  OK  {name}')
    except Exception as e: FAIL += 1; ERRORS.append((name, str(e))); print(f'  FAIL {name}: {e}')
def summary():
    total = PASS + FAIL
    print(f'\n{"="*60}')
    s = f'Phase 2: {total}/{total} ALL TESTS PASSED' if FAIL == 0 else f'Phase 2: {PASS}/{total} PASSED, {FAIL} FAILED'
    print(f'  {s}')
    for n, e in ERRORS: print(f'    X {n}: {e}')
    print(f'{"="*60}')
    return FAIL == 0

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
_qapp = QApplication.instance() or QApplication(sys.argv)

from core.engine import LLMEngine, ErrorCategory, categorize_error, TransitionType
from core.providers.base import BaseProvider, ToolCall, ToolDef, AbortSignal, StreamChunk, LLMCallParams
from unittest.mock import MagicMock

print('=' * 60)
print('  Phase 2 Verification Tests')
print('=' * 60)

class P2MockProvider(BaseProvider):
    def __init__(self):
        self.responses = []; self._idx = 0; self._errors = {}; self._calls = []
        self._stream_fail = False
    def set_responses(self, *r): self.responses = list(r); self._idx = 0
    def set_error_at(self, i, e): self._errors[i] = e
    def call_sync(self, messages, system, tools, max_tokens=4096, abort_signal=None, params=None):
        self._calls.append({"params": params, "idx": self._idx})
        if self._idx in self._errors:
            idx = self._idx; self._idx += 1; raise self._errors[idx]
        if self._idx < len(self.responses):
            r = self.responses[self._idx]; self._idx += 1; return r
        self._idx += 1
        return ({"role": "assistant", "content": "default"}, [], "default")
    def call_stream(self, messages, system, tools, max_tokens=4096, abort_signal=None, params=None):
        if self._stream_fail:
            raise ConnectionError("Stream failed")
        raw, tc, text = self.call_sync(messages, system, tools, max_tokens, abort_signal, params)
        if text:
            for w in text.split(" "): yield StreamChunk(type="text_delta", text=w + " ")
        yield StreamChunk(type="done")
        return raw, tc, text
    @property
    def supports_streaming(self): return True
    def format_tools(self, tools): return [{"name": t.name} for t in tools]
    def format_tool_results(self, tc, r):
        return {"role": "user", "content": [{"type": "tool_result", "tool_use_id": t.id, "content": res.get("output","")} for t, res in zip(tc, r)]}

def text_r(t, stop="end_turn"):
    return ({"role": "assistant", "content": t, "_stop_reason": stop, "_usage": {"input_tokens": 100, "output_tokens": 50}}, [], t)


# ═══════════════════════════════════════════════════════════════
# Stop reason handling + response withholding
# ═══════════════════════════════════════════════════════════════

def test_stop_reason_end_turn():
    """Normal end_turn stop: text is emitted."""
    engine = LLMEngine()
    prov = P2MockProvider()
    engine.set_provider(prov, "mock")
    engine._streaming_enabled = False
    prov.set_responses(text_r("Hello!", "end_turn"))
    responses = []
    engine.response_text.connect(lambda t: responses.append(t))
    engine._conversation.add_user_message("hi")
    engine._is_running = True; engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False
    assert len(responses) == 1 and responses[0] == "Hello!"
run("P2.1 Stop reason end_turn: text emitted normally", test_stop_reason_end_turn)


def test_stop_reason_max_tokens_withhold():
    """max_tokens stop: partial text is NOT emitted, escalation + retry happens."""
    engine = LLMEngine()
    prov = P2MockProvider()
    engine.set_provider(prov, "mock")
    engine._streaming_enabled = False
    # First response: max_tokens (truncated), second: complete
    prov.set_responses(
        text_r("Partial text that was cut off...", "max_tokens"),
        text_r("Complete response after escalation", "end_turn"),
    )
    responses = []
    engine.response_text.connect(lambda t: responses.append(t))
    engine._conversation.add_user_message("write something long")
    engine._is_running = True; engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False
    # Should NOT have emitted the partial text
    assert len(responses) == 1, f"Expected 1 response (the complete one), got {len(responses)}"
    assert "Complete" in responses[0], f"Should get complete response, got: {responses[0][:50]}"
    # Should have recovery transition
    recovery = [t for t in engine.transitions if t["type"] == "max_output_recovery"]
    assert len(recovery) >= 1, "Should have max_output_recovery transition"
    assert "withhold" in recovery[0]["detail"].lower(), f"Should mention withholding: {recovery[0]['detail']}"
run("P2.2 Stop max_tokens: withhold partial, escalate, emit complete", test_stop_reason_max_tokens_withhold)


# ═══════════════════════════════════════════════════════════════
# Partial response preserved in messages
# ═══════════════════════════════════════════════════════════════

def test_partial_preserved():
    """Partial assistant response is kept in messages for continuation context."""
    engine = LLMEngine()
    prov = P2MockProvider()
    engine.set_provider(prov, "mock")
    engine._streaming_enabled = False
    prov.set_responses(
        text_r("Part 1 of the answer...", "max_tokens"),
        text_r("Part 2 completing the answer.", "end_turn"),
    )
    engine._conversation.add_user_message("explain something")
    engine._is_running = True; engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False
    msgs = engine.conversation.messages
    # Partial response should be in messages (for continuation context)
    has_partial = any("Part 1" in str(m.get("content", "")) for m in msgs)
    assert has_partial, "Partial response should be preserved in messages for context"
    # Continuation prompt should also be there
    has_continuation = any("Resume directly" in str(m.get("content", "")) for m in msgs)
    assert has_continuation, "Continuation prompt should be in messages"
run("P2.3 Partial response preserved in messages for continuation", test_partial_preserved)


# ═══════════════════════════════════════════════════════════════
# Streaming fallback
# ═══════════════════════════════════════════════════════════════

def test_streaming_fallback():
    """When streaming fails, engine falls back to sync call."""
    engine = LLMEngine()
    prov = P2MockProvider()
    prov._stream_fail = True  # force streaming to fail
    engine.set_provider(prov, "mock")
    engine._streaming_enabled = True
    prov.set_responses(text_r("Fallback response"))
    responses = []
    engine.response_text.connect(lambda t: responses.append(t))
    engine._conversation.add_user_message("test fallback")
    engine._is_running = True; engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False
    assert len(responses) == 1, f"Fallback should work, got {len(responses)} responses"
    assert "Fallback" in responses[0]
run("P2.4 Streaming fallback: stream fails → sync succeeds", test_streaming_fallback)


# ═══════════════════════════════════════════════════════════════
# API key verification
# ═══════════════════════════════════════════════════════════════

def test_verify_api_key_no_provider():
    """verify_api_key with no provider returns failure."""
    engine = LLMEngine()
    ok, msg = engine.verify_api_key()
    assert ok is False
    assert "provider" in msg.lower()
run("P2.5 verify_api_key: no provider → failure", test_verify_api_key_no_provider)


def test_verify_api_key_success():
    """verify_api_key with working provider returns success."""
    engine = LLMEngine()
    prov = P2MockProvider()
    prov.set_responses(text_r("OK"))
    engine.set_provider(prov, "mock")
    ok, msg = engine.verify_api_key()
    assert ok is True
    assert "valid" in msg.lower()
run("P2.6 verify_api_key: working provider → success", test_verify_api_key_success)


def test_verify_api_key_auth_fail():
    """verify_api_key with auth error returns specific message."""
    engine = LLMEngine()
    prov = P2MockProvider()
    prov.set_error_at(0, Exception("401 unauthorized"))
    prov.set_responses(None)
    engine.set_provider(prov, "mock")
    ok, msg = engine.verify_api_key()
    assert ok is False
    assert "invalid" in msg.lower() or "api key" in msg.lower()
run("P2.7 verify_api_key: auth error → invalid key message", test_verify_api_key_auth_fail)


# ═══════════════════════════════════════════════════════════════
# 529 / ECONNRESET classification
# ═══════════════════════════════════════════════════════════════

def test_529_classification():
    """529 Transient Capacity Error → OVERLOADED (separate from 429, retryable)."""
    assert categorize_error(Exception("529 Transient Capacity")) == ErrorCategory.OVERLOADED
run("P2.8 Error 529 → OVERLOADED (separate from 429)", test_529_classification)

def test_econnreset_classification():
    """ECONNRESET → NETWORK_ERROR (retryable)."""
    assert categorize_error(Exception("ECONNRESET: connection reset")) == ErrorCategory.NETWORK_ERROR
run("P2.9 Error ECONNRESET → NETWORK_ERROR", test_econnreset_classification)

def test_epipe_classification():
    """EPIPE/broken pipe → NETWORK_ERROR (retryable)."""
    assert categorize_error(Exception("broken pipe")) == ErrorCategory.NETWORK_ERROR
run("P2.10 Error broken pipe → NETWORK_ERROR", test_epipe_classification)


# ═══════════════════════════════════════════════════════════════
# LLMCallParams built correctly
# ═══════════════════════════════════════════════════════════════

def test_params_passed_to_provider():
    """Engine builds LLMCallParams and passes to provider."""
    engine = LLMEngine()
    prov = P2MockProvider()
    engine.set_provider(prov, "mock")
    engine._streaming_enabled = False
    engine._thinking_config = {"type": "enabled", "budget_tokens": 5000}
    engine._effort_level = "high"
    engine._cache_control_enabled = True
    prov.set_responses(text_r("ok"))
    engine._conversation.add_user_message("test")
    engine._is_running = True; engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False
    # Check that params were passed
    assert len(prov._calls) >= 1
    params = prov._calls[0]["params"]
    assert params is not None, "LLMCallParams should be passed"
    assert params.thinking == {"type": "enabled", "budget_tokens": 5000}
    assert params.effort == "high"
    assert params.cache_control is True
    # Temperature should be None when thinking is enabled
    assert params.temperature is None, "Temperature must be None when thinking enabled"
run("P2.11 LLMCallParams: thinking+effort+cache passed, temp=None with thinking", test_params_passed_to_provider)


def test_params_temperature_without_thinking():
    """When thinking is off, temperature is passed through."""
    engine = LLMEngine()
    prov = P2MockProvider()
    engine.set_provider(prov, "mock")
    engine._streaming_enabled = False
    engine._thinking_config = None  # no thinking
    engine._temperature = 0.7
    prov.set_responses(text_r("ok"))
    engine._conversation.add_user_message("test")
    engine._is_running = True; engine._abort_signal.reset()
    engine._tool_loop()
    engine._is_running = False
    params = prov._calls[0]["params"]
    assert params.temperature == 0.7, f"Temperature should be 0.7, got {params.temperature}"
    assert params.thinking is None
run("P2.12 LLMCallParams: temperature passed when thinking is off", test_params_temperature_without_thinking)


# ═══════════════════════════════════════════════════════════════
import shutil
try: ok = summary()
finally: shutil.rmtree(_TEMP, ignore_errors=True)
sys.exit(0 if ok else 1)
