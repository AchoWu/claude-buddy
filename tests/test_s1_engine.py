"""
Suite 1 — Engine Tests
Tests core/engine.py: error classification, retryability, SessionCost,
TransitionType, and LLMEngine instantiation/properties.
~40 tests covering error categories, cost tracking, engine basics, and edge cases.
"""

import sys, os, io, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from unittest.mock import patch, MagicMock

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
        print(f'  Suite 1 (Engine): {total}/{total} ALL TESTS PASSED')
    else:
        print(f'  Suite 1 (Engine): {PASS}/{total} PASSED, {FAIL} FAILED')
        for n, e in ERRORS:
            print(f'    X {n}: {e}')
    print(f'{"="*60}')
    return FAIL == 0

print('='*60)
print('  Suite 1: Engine Tests (~40 tests)')
print('='*60)

# ── QApp setup (LLMEngine is a QObject) ─────────────────────────
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
_qapp = QApplication.instance() or QApplication(sys.argv)

# ── Imports ─────────────────────────────────────────────────────
from core.engine import (
    ErrorCategory, categorize_error, is_retryable,
    TransitionType, SessionCost, LLMEngine,
)


# ══════════════════════════════════════════════════════════════════
# 1. Error Classification — categorize_error (tests 1-15)
# ══════════════════════════════════════════════════════════════════

def test_rate_limit_429():
    assert categorize_error(Exception("429 Too Many Requests")) == ErrorCategory.RATE_LIMIT
run("1  categorize_error: 429 → RATE_LIMIT", test_rate_limit_429)

def test_rate_limit_text():
    assert categorize_error(Exception("rate limit exceeded")) == ErrorCategory.RATE_LIMIT
run("2  categorize_error: 'rate limit' → RATE_LIMIT", test_rate_limit_text)

def test_rate_limit_too_many():
    assert categorize_error(Exception("too many requests, please slow down")) == ErrorCategory.RATE_LIMIT
run("3  categorize_error: 'too many requests' → RATE_LIMIT", test_rate_limit_too_many)

def test_context_too_long():
    assert categorize_error(Exception("context_length_exceeded")) == ErrorCategory.CONTEXT_TOO_LONG
run("4  categorize_error: context_length → CONTEXT_TOO_LONG", test_context_too_long)

def test_context_too_long_prompt():
    assert categorize_error(Exception("prompt is too long for this model")) == ErrorCategory.CONTEXT_TOO_LONG
run("5  categorize_error: 'prompt is too long' → CONTEXT_TOO_LONG", test_context_too_long_prompt)

def test_context_too_many_tokens():
    assert categorize_error(Exception("too many tokens in the request")) == ErrorCategory.CONTEXT_TOO_LONG
run("6  categorize_error: 'too many tokens' → CONTEXT_TOO_LONG", test_context_too_many_tokens)

def test_context_request_too_large():
    assert categorize_error(Exception("request too large for context")) == ErrorCategory.CONTEXT_TOO_LONG
run("7  categorize_error: 'request too large' → CONTEXT_TOO_LONG", test_context_request_too_large)

def test_context_window_keyword():
    assert categorize_error(Exception("exceeds context window limit")) == ErrorCategory.CONTEXT_TOO_LONG
run("8  categorize_error: 'context window' → CONTEXT_TOO_LONG", test_context_window_keyword)

def test_max_output_tokens():
    assert categorize_error(Exception("max_tokens limit reached")) == ErrorCategory.MAX_OUTPUT_TOKENS
run("9  categorize_error: max_tokens → MAX_OUTPUT_TOKENS", test_max_output_tokens)

def test_max_output_length_limit():
    assert categorize_error(Exception("output token length limit")) == ErrorCategory.MAX_OUTPUT_TOKENS
run("10 categorize_error: 'output token' → MAX_OUTPUT_TOKENS", test_max_output_length_limit)

def test_timeout():
    assert categorize_error(Exception("request timed out")) == ErrorCategory.TIMEOUT
run("11 categorize_error: 'timed out' → TIMEOUT", test_timeout)

def test_timeout_deadline():
    assert categorize_error(Exception("deadline exceeded")) == ErrorCategory.TIMEOUT
run("12 categorize_error: 'deadline' → TIMEOUT", test_timeout_deadline)

def test_network_error():
    assert categorize_error(Exception("connection refused")) == ErrorCategory.NETWORK_ERROR
run("13 categorize_error: 'connection' → NETWORK_ERROR", test_network_error)

def test_network_dns():
    assert categorize_error(Exception("dns resolution failed")) == ErrorCategory.NETWORK_ERROR
run("14 categorize_error: 'dns' → NETWORK_ERROR", test_network_dns)

def test_network_socket():
    assert categorize_error(Exception("socket error occurred")) == ErrorCategory.NETWORK_ERROR
run("15 categorize_error: 'socket' → NETWORK_ERROR", test_network_socket)

def test_server_error_500():
    assert categorize_error(Exception("500 Internal Server Error")) == ErrorCategory.SERVER_ERROR
run("16 categorize_error: 500 → SERVER_ERROR", test_server_error_500)

def test_server_error_502():
    assert categorize_error(Exception("502 Bad Gateway")) == ErrorCategory.SERVER_ERROR
run("17 categorize_error: 502/bad gateway → SERVER_ERROR", test_server_error_502)

def test_server_error_503():
    assert categorize_error(Exception("503 Service Unavailable")) == ErrorCategory.SERVER_ERROR
run("18 categorize_error: 503/service unavailable → SERVER_ERROR", test_server_error_503)

def test_server_error_overloaded():
    assert categorize_error(Exception("server overloaded, try again later")) == ErrorCategory.SERVER_ERROR
run("19 categorize_error: 'overloaded' → SERVER_ERROR", test_server_error_overloaded)

def test_auth_error_401():
    assert categorize_error(Exception("401 Unauthorized")) == ErrorCategory.AUTH_ERROR
run("20 categorize_error: 401 → AUTH_ERROR", test_auth_error_401)

def test_auth_error_403():
    assert categorize_error(Exception("403 Forbidden")) == ErrorCategory.AUTH_ERROR
run("21 categorize_error: 403 → AUTH_ERROR", test_auth_error_403)

def test_auth_invalid_key():
    assert categorize_error(Exception("invalid api key provided")) == ErrorCategory.AUTH_ERROR
run("22 categorize_error: 'invalid api key' → AUTH_ERROR", test_auth_invalid_key)

def test_invalid_request_400():
    assert categorize_error(Exception("400 Bad Request: invalid parameter")) == ErrorCategory.INVALID_REQUEST
run("23 categorize_error: 400/invalid → INVALID_REQUEST", test_invalid_request_400)

def test_invalid_request_malformed():
    assert categorize_error(Exception("malformed request body")) == ErrorCategory.INVALID_REQUEST
run("24 categorize_error: 'malformed' → INVALID_REQUEST", test_invalid_request_malformed)

def test_invalid_request_validation():
    assert categorize_error(Exception("validation error in field X")) == ErrorCategory.INVALID_REQUEST
run("25 categorize_error: 'validation' → INVALID_REQUEST", test_invalid_request_validation)

def test_unknown_error():
    assert categorize_error(Exception("something completely unexpected happened")) == ErrorCategory.UNKNOWN
run("26 categorize_error: unrecognized → UNKNOWN", test_unknown_error)


# ══════════════════════════════════════════════════════════════════
# 2. is_retryable (tests 27-28)
# ══════════════════════════════════════════════════════════════════

def test_retryable_categories():
    assert is_retryable(ErrorCategory.RATE_LIMIT) is True
    assert is_retryable(ErrorCategory.SERVER_ERROR) is True
    assert is_retryable(ErrorCategory.NETWORK_ERROR) is True
    assert is_retryable(ErrorCategory.TIMEOUT) is True
run("27 is_retryable: True for RATE_LIMIT/SERVER/NETWORK/TIMEOUT", test_retryable_categories)

def test_non_retryable_categories():
    assert is_retryable(ErrorCategory.AUTH_ERROR) is False
    assert is_retryable(ErrorCategory.INVALID_REQUEST) is False
    assert is_retryable(ErrorCategory.CONTEXT_TOO_LONG) is False
    assert is_retryable(ErrorCategory.MAX_OUTPUT_TOKENS) is False
    assert is_retryable(ErrorCategory.UNKNOWN) is False
run("28 is_retryable: False for AUTH/INVALID/CONTEXT/MAX_OUTPUT/UNKNOWN", test_non_retryable_categories)


# ══════════════════════════════════════════════════════════════════
# 3. SessionCost (tests 29-34)
# ══════════════════════════════════════════════════════════════════

def test_session_cost_init_zeros():
    sc = SessionCost()
    assert sc.total_input_tokens == 0
    assert sc.total_output_tokens == 0
    assert sc.total_api_calls == 0
    assert sc.total_tool_calls == 0
    assert sc.model_usage == {}
run("29 SessionCost initializes to zeros", test_session_cost_init_zeros)

def test_session_cost_add_call():
    sc = SessionCost()
    sc.add_call("claude-sonnet", input_tokens=100, output_tokens=50)
    assert sc.total_input_tokens == 100
    assert sc.total_output_tokens == 50
    assert sc.total_api_calls == 1
    assert "claude-sonnet" in sc.model_usage
    assert sc.model_usage["claude-sonnet"]["input"] == 100
    assert sc.model_usage["claude-sonnet"]["output"] == 50
    assert sc.model_usage["claude-sonnet"]["calls"] == 1
run("30 SessionCost.add_call tracks tokens per model", test_session_cost_add_call)

def test_session_cost_accumulation():
    sc = SessionCost()
    sc.add_call("model-a", input_tokens=100, output_tokens=50)
    sc.add_call("model-a", input_tokens=200, output_tokens=100)
    sc.add_call("model-b", input_tokens=300, output_tokens=150)
    assert sc.total_input_tokens == 600
    assert sc.total_output_tokens == 300
    assert sc.total_api_calls == 3
    assert sc.model_usage["model-a"]["calls"] == 2
    assert sc.model_usage["model-a"]["input"] == 300
    assert sc.model_usage["model-a"]["output"] == 150
    assert sc.model_usage["model-b"]["calls"] == 1
    assert sc.model_usage["model-b"]["input"] == 300
    assert sc.model_usage["model-b"]["output"] == 150
run("31 SessionCost accumulates across multiple calls and models", test_session_cost_accumulation)

def test_session_cost_tool_calls():
    sc = SessionCost()
    sc.add_tool_call()
    sc.add_tool_call()
    sc.add_tool_call()
    assert sc.total_tool_calls == 3
run("32 SessionCost.add_tool_call increments counter", test_session_cost_tool_calls)

def test_session_cost_summary():
    sc = SessionCost()
    sc.add_call("test-model", input_tokens=500, output_tokens=200)
    sc.add_tool_call()
    s = sc.summary()
    assert "API calls: 1" in s
    assert "Tool calls: 1" in s
    assert "500" in s
    assert "200" in s
    assert "test-model" in s
run("33 SessionCost.summary() returns formatted string", test_session_cost_summary)

def test_session_cost_summary_empty():
    sc = SessionCost()
    s = sc.summary()
    assert "API calls: 0" in s
    assert "Tool calls: 0" in s
run("34 SessionCost.summary() works with zero usage", test_session_cost_summary_empty)


# ══════════════════════════════════════════════════════════════════
# 4. TransitionType (test 35)
# ══════════════════════════════════════════════════════════════════

def test_transition_types_exist():
    expected = ["COMPACTION", "TOKEN_COMPACTION", "CONTEXT_RECOVERY",
                "MAX_OUTPUT_RECOVERY", "TOOL_RESULTS", "TERMINAL",
                "MAX_ROUNDS", "ABORTED", "ERROR"]
    for name in expected:
        assert hasattr(TransitionType, name), f"Missing TransitionType.{name}"
    assert len(TransitionType) == 9, f"Expected 9 members, got {len(TransitionType)}"
run("35 TransitionType has all 9 expected members", test_transition_types_exist)

def test_transition_type_values():
    """Each TransitionType should have a string value."""
    for tt in TransitionType:
        assert isinstance(tt.value, str), f"{tt.name}.value should be str"
        assert len(tt.value) > 0, f"{tt.name}.value should not be empty"
run("36 TransitionType members have non-empty string values", test_transition_type_values)


# ══════════════════════════════════════════════════════════════════
# 5. LLMEngine instantiation and properties (tests 37-50)
# ══════════════════════════════════════════════════════════════════

def test_engine_instantiation():
    engine = LLMEngine()
    assert engine is not None
run("37 LLMEngine can be instantiated", test_engine_instantiation)

def test_engine_has_conversation():
    engine = LLMEngine()
    conv = engine.conversation
    assert conv is not None
    assert hasattr(conv, 'messages')
run("38 LLMEngine.conversation property exists", test_engine_has_conversation)

def test_engine_has_session_cost():
    engine = LLMEngine()
    sc = engine.session_cost
    assert isinstance(sc, SessionCost)
    assert sc.total_api_calls == 0
run("39 LLMEngine.session_cost is a SessionCost with zeros", test_engine_has_session_cost)

def test_engine_transitions_empty():
    engine = LLMEngine()
    assert engine.transitions == []
    assert isinstance(engine.transitions, list)
run("40 LLMEngine.transitions starts as empty list", test_engine_transitions_empty)

def test_engine_set_provider():
    engine = LLMEngine()
    mock_provider = MagicMock()
    engine.set_provider(mock_provider, model="test-model")
    assert engine._provider is mock_provider
    assert engine._provider_model == "test-model"
run("41 set_provider stores provider and model", test_engine_set_provider)

def test_engine_set_provider_no_model():
    engine = LLMEngine()
    mock_provider = MagicMock()
    engine.set_provider(mock_provider)
    assert engine._provider is mock_provider
    assert engine._provider_model == ""
run("42 set_provider without model uses empty string", test_engine_set_provider_no_model)

def test_engine_clear_conversation():
    engine = LLMEngine()
    engine.conversation.add_user_message("hello")
    assert engine.conversation.message_count > 0
    engine.clear_conversation()
    assert engine.conversation.message_count == 0
run("43 clear_conversation resets messages to zero", test_engine_clear_conversation)

def test_engine_set_plan_mode():
    engine = LLMEngine()
    mock_state = MagicMock()
    engine.set_plan_mode_state(mock_state)
    assert engine._plan_mode_state is mock_state
run("44 set_plan_mode_state stores state", test_engine_set_plan_mode)

def test_engine_set_memory():
    engine = LLMEngine()
    engine.set_memory("User likes Python.")
    assert engine._memory_content == "User likes Python."
    engine.set_memory(None)
    assert engine._memory_content is None
run("45 set_memory stores and clears content", test_engine_set_memory)

def test_engine_set_memory_manager():
    engine = LLMEngine()
    mgr = MagicMock()
    engine.set_memory_manager(mgr)
    assert engine._memory_mgr is mgr
run("46 set_memory_manager injects manager", test_engine_set_memory_manager)

def test_engine_set_team_memory():
    engine = LLMEngine()
    store = MagicMock()
    engine.set_team_memory(store)
    assert engine._team_memory is store
run("47 set_team_memory injects store", test_engine_set_team_memory)

def test_engine_set_evolution_manager():
    engine = LLMEngine()
    mgr = MagicMock()
    engine.set_evolution_manager(mgr)
    assert engine._evolution_mgr is mgr
run("48 set_evolution_manager injects manager", test_engine_set_evolution_manager)

def test_engine_context_window_default():
    engine = LLMEngine()
    assert engine._context_window == LLMEngine.DEFAULT_CONTEXT_WINDOW
    assert engine._context_window == 32000
run("49 engine default context window is 32000", test_engine_context_window_default)

def test_engine_set_context_window():
    engine = LLMEngine()
    engine.set_context_window(128000)
    assert engine._context_window == 128000
run("50 set_context_window changes window size", test_engine_set_context_window)

def test_engine_register_tool():
    engine = LLMEngine()
    tool_def = MagicMock()
    tool_def.name = "TestTool"
    executor = MagicMock()
    engine.register_tool(tool_def, executor, is_read_only=True)
    assert "TestTool" in engine._tool_executors
    assert engine._tool_read_only["TestTool"] is True
    assert tool_def in engine._tools
run("51 register_tool adds tool to engine", test_engine_register_tool)

def test_engine_register_multiple_tools():
    engine = LLMEngine()
    for name in ["ToolA", "ToolB", "ToolC"]:
        td = MagicMock()
        td.name = name
        engine.register_tool(td, MagicMock(), is_read_only=(name == "ToolA"))
    assert len(engine._tools) == 3
    assert len(engine._tool_executors) == 3
    assert engine._tool_read_only["ToolA"] is True
    assert engine._tool_read_only["ToolB"] is False
run("52 register_tool handles multiple tools with read-only flags", test_engine_register_multiple_tools)

def test_engine_not_running_initially():
    engine = LLMEngine()
    assert engine._is_running is False
    assert engine._abort_signal.aborted is False
run("53 engine is not running initially", test_engine_not_running_initially)

def test_engine_abort():
    engine = LLMEngine()
    engine.abort()
    assert engine._abort_signal.aborted is True
run("54 abort() sets abort signal", test_engine_abort)

def test_engine_get_cost_summary():
    engine = LLMEngine()
    s = engine.get_cost_summary()
    assert isinstance(s, str)
    assert "API calls: 0" in s
run("55 get_cost_summary returns formatted string", test_engine_get_cost_summary)

def test_engine_background_task_start():
    engine = LLMEngine()
    executor = MagicMock(return_value="done")
    task_id = engine.start_background_task(executor, {"key": "val"})
    assert task_id is not None
    assert isinstance(task_id, str)
    task = engine.get_background_task(task_id)
    assert task is not None
    assert task["status"] in ("running", "completed")
run("56 start_background_task returns a valid task_id", test_engine_background_task_start)

def test_engine_background_task_nonexistent():
    engine = LLMEngine()
    task = engine.get_background_task("999")
    assert task is None
run("57 get_background_task returns None for unknown id", test_engine_background_task_nonexistent)

def test_engine_send_message_no_provider():
    """send_message with no provider should emit error, not crash."""
    engine = LLMEngine()
    errors = []
    engine.error.connect(lambda msg: errors.append(msg))
    engine.send_message("hello")
    assert len(errors) == 1
    assert "provider" in errors[0].lower() or "configured" in errors[0].lower()
run("58 send_message without provider emits error signal", test_engine_send_message_no_provider)

def test_engine_set_permission_callback():
    engine = LLMEngine()
    cb = MagicMock(return_value=True)
    engine.set_permission_callback(cb)
    assert engine._permission_callback is cb
run("59 set_permission_callback stores callback", test_engine_set_permission_callback)


# ══════════════════════════════════════════════════════════════════
# 6. Error classification edge cases (tests 60-66)
# ══════════════════════════════════════════════════════════════════

def test_error_empty_message():
    assert categorize_error(Exception("")) == ErrorCategory.UNKNOWN
run("60 categorize_error: empty message → UNKNOWN", test_error_empty_message)

def test_error_multiple_keywords_first_wins():
    """When multiple keywords match, the first check in code order wins."""
    e = Exception("rate limit 429 too many requests")
    assert categorize_error(e) == ErrorCategory.RATE_LIMIT
run("61 categorize_error: multiple keywords → first match wins", test_error_multiple_keywords_first_wins)

def test_error_case_insensitive():
    """Error messages are lowercased before matching."""
    assert categorize_error(Exception("RATE LIMIT EXCEEDED")) == ErrorCategory.RATE_LIMIT
    assert categorize_error(Exception("Connection Refused")) == ErrorCategory.NETWORK_ERROR
    assert categorize_error(Exception("UNAUTHORIZED")) == ErrorCategory.AUTH_ERROR
run("62 categorize_error: matching is case-insensitive", test_error_case_insensitive)

def test_error_with_traceback_text():
    """Errors containing stack trace info still categorize correctly."""
    e = Exception("Traceback: ... connection refused at line 42 ...")
    assert categorize_error(e) == ErrorCategory.NETWORK_ERROR
run("63 categorize_error: error with traceback text still categorizes", test_error_with_traceback_text)

def test_error_very_long_message():
    """Very long error messages don't cause issues."""
    msg = "x" * 10000 + " rate limit " + "y" * 10000
    assert categorize_error(Exception(msg)) == ErrorCategory.RATE_LIMIT
run("64 categorize_error: very long message still matches keywords", test_error_very_long_message)

def test_error_all_categories_covered():
    """Ensure all ErrorCategory members can be returned by categorize_error."""
    test_cases = {
        ErrorCategory.RATE_LIMIT: "429",
        ErrorCategory.SERVER_ERROR: "500",
        ErrorCategory.CONTEXT_TOO_LONG: "context_length",
        ErrorCategory.MAX_OUTPUT_TOKENS: "max_tokens",
        ErrorCategory.NETWORK_ERROR: "connection",
        ErrorCategory.TIMEOUT: "timeout",
        ErrorCategory.AUTH_ERROR: "unauthorized",
        ErrorCategory.INVALID_REQUEST: "400 invalid",
        ErrorCategory.UNKNOWN: "xyzzy gibberish",
    }
    for expected_cat, msg in test_cases.items():
        result = categorize_error(Exception(msg))
        assert result == expected_cat, f"Expected {expected_cat} for '{msg}', got {result}"
run("65 categorize_error: all 9 categories are reachable", test_error_all_categories_covered)

def test_tool_result_truncation_constant():
    """Verify the truncation threshold is reasonable."""
    assert LLMEngine.MAX_TOOL_RESULT_CHARS > 1000
    assert LLMEngine.MAX_TOOL_RESULT_CHARS <= 100000
run("66 MAX_TOOL_RESULT_CHARS is within reasonable range", test_tool_result_truncation_constant)

def test_engine_class_constants():
    """Verify key class constants are defined."""
    assert LLMEngine.MAX_RETRIES >= 1
    assert LLMEngine.RETRY_BASE_DELAY > 0
    assert LLMEngine.RETRY_MAX_DELAY >= LLMEngine.RETRY_BASE_DELAY
    assert LLMEngine.MAX_OUTPUT_TOKEN_RECOVERY_LIMIT >= 1
    assert LLMEngine.MAX_REACTIVE_COMPACT_ATTEMPTS >= 1
    assert LLMEngine.OUTPUT_RESERVE > 0
    assert LLMEngine.COMPACTION_BUFFER > 0
run("67 engine class constants are defined with reasonable values", test_engine_class_constants)

def test_short_error_truncation():
    """_short_error truncates long messages."""
    short = LLMEngine._short_error(Exception("hello"))
    assert short == "hello"
    long_msg = "x" * 300
    truncated = LLMEngine._short_error(Exception(long_msg))
    assert len(truncated) <= 160  # 150 + "..."
    assert truncated.endswith("...")
run("68 _short_error truncates messages over 150 chars", test_short_error_truncation)


# ══════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════

ok = summary()
sys.exit(0 if ok else 1)
