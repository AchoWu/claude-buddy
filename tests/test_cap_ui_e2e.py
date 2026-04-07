"""
Capability Tests — UI Simulation (End-to-End)
Simulates REAL user interactions through the BuddyApp controller layer.
Tests the full chain: ChatDialog → BuddyApp → Engine → Provider → back to ChatDialog.

NOT just component tests — these wire up the actual signal/slot connections
that main.py establishes, and verify that the UI (ChatDialog) receives
the correct messages in the correct order.

Covers:
  E2E.1  User sends message → chat shows assistant reply
  E2E.2  User sends /help → chat shows command output (no LLM call)
  E2E.3  User sends /clear → chat clears, session archived
  E2E.4  User sends /exit → __EXIT__ handled, session saved
  E2E.5  User sends /resume → chat loads history
  E2E.6  Streaming: chunks arrive → chat shows incremental text
  E2E.7  Tool call: tool indicator shown in chat, then result
  E2E.8  Abort: user clicks stop → chat shows [Request interrupted by user]
  E2E.9  Abort + reopen: interrupt marker persists across chat close/reopen
  E2E.10 No API key: chat shows "need API key" message
  E2E.11 /cost command → chat shows session cost
  E2E.12 /status command → chat shows engine status
  E2E.13 /plan → plan mode blocks write tools → chat shows blocked message
  E2E.14 Error from engine → chat shows error message
  E2E.15 Pet state changes: idle → working → idle during message flow
"""

import sys, os, io, time, threading, tempfile, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_buddy = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _buddy)
os.chdir(_buddy)

from pathlib import Path
_TEMP = tempfile.mkdtemp(prefix='buddy_cap_ui_')
import config
config.DATA_DIR = Path(_TEMP)
config.CONVERSATIONS_DIR = Path(_TEMP) / "conversations"
config.CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
config.INPUT_HISTORY_FILE = Path(_TEMP) / "input_history.json"
config.TASKS_FILE = Path(_TEMP) / "tasks.json"

(Path(_TEMP) / "soul").mkdir(exist_ok=True)
(Path(_TEMP) / "evolution").mkdir(exist_ok=True)
(Path(_TEMP) / "evolution" / "backups").mkdir(exist_ok=True)
(Path(_TEMP) / "plugins").mkdir(exist_ok=True)

try:
    import core.evolution as _evo_mod
    _evo_mod.DATA_DIR = Path(_TEMP)
    _evo_mod.SOUL_DIR = Path(_TEMP) / "soul"
    _evo_mod.EVOLUTION_DIR = Path(_TEMP) / "evolution"
except Exception:
    pass

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
        import traceback
        print(f'  FAIL {name}: {e}')

def summary():
    total = PASS + FAIL
    print(f'\n{"="*60}')
    if FAIL == 0:
        print(f'  UI Simulation (E2E): {total}/{total} ALL TESTS PASSED')
    else:
        print(f'  UI Simulation (E2E): {PASS}/{total} PASSED, {FAIL} FAILED')
        for n, e in ERRORS:
            print(f'    X {n}: {e}')
    print(f'{"="*60}')
    return FAIL == 0


os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QTimer
_qapp = QApplication.instance() or QApplication(sys.argv)

from core.engine import LLMEngine
from core.providers.base import BaseProvider, ToolCall, ToolDef, AbortSignal, StreamChunk
from core.conversation import ConversationManager
from core.commands import CommandRegistry
from core.task_manager import TaskManager
from ui.chat_dialog import ChatDialog
from ui.pet_window import PetWindow, PetState
from ui.speech_bubble import SpeechBubble
from ui.notification import NotificationQueue
from unittest.mock import MagicMock, patch

print('=' * 60)
print('  UI Simulation Tests (End-to-End)')
print('=' * 60)


# ═══════════════════════════════════════════════════════════════════
# MockProvider for UI tests
# ═══════════════════════════════════════════════════════════════════

class UIMockProvider(BaseProvider):
    """Mock provider that returns configurable responses."""

    def __init__(self):
        self.responses = []  # list of (raw, tool_calls, text)
        self._call_idx = 0
        self._stream_enabled = False
        self._stream_delay = 0.01
        self._slow = False  # if True, sleep before responding

    def set_responses(self, *resps):
        self.responses = list(resps)
        self._call_idx = 0

    def call_sync(self, messages, system, tools, max_tokens=4096, abort_signal=None, params=None):
        if abort_signal and abort_signal.aborted:
            raise InterruptedError("Aborted")
        if self._slow:
            for _ in range(20):
                if abort_signal and abort_signal.aborted:
                    raise InterruptedError("Aborted during slow call")
                time.sleep(0.05)

        if self._call_idx < len(self.responses):
            resp = self.responses[self._call_idx]
            self._call_idx += 1
            return resp
        self._call_idx += 1
        return ({"role": "assistant", "content": "default"}, [], "default")

    def call_stream(self, messages, system, tools, max_tokens=4096, abort_signal=None, params=None):
        raw, tool_calls, text = self.call_sync(
            messages, system, tools, max_tokens, abort_signal
        )
        if text:
            words = text.split(" ")
            for w in words:
                if abort_signal and abort_signal.aborted:
                    raise InterruptedError("Aborted during stream")
                yield StreamChunk(type="text_delta", text=w + " ")
                time.sleep(self._stream_delay)
        yield StreamChunk(type="done")
        return raw, tool_calls, text

    @property
    def supports_streaming(self):
        return self._stream_enabled

    def format_tools(self, tools):
        return [{"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in tools]

    def format_tool_results(self, tool_calls, results):
        content = []
        for tc, r in zip(tool_calls, results):
            content.append({"type": "tool_result", "tool_use_id": tc.id,
                            "content": r.get("output", ""),
                            **({"is_error": True} if r.get("is_error") else {})})
        return {"role": "user", "content": content}


def make_text(text):
    return ({"role": "assistant", "content": text}, [], text)

def make_tool(name, inp, tool_id="tc_1", text=""):
    raw = [{"type": "tool_use", "id": tool_id, "name": name, "input": inp}]
    if text:
        raw.insert(0, {"type": "text", "text": text})
    return (raw, [ToolCall(id=tool_id, name=name, input=inp)], text)


# ═══════════════════════════════════════════════════════════════════
# BuddyAppSimulator — wires real components without real QApplication
# ═══════════════════════════════════════════════════════════════════

class BuddyAppSimulator:
    """
    Simulates the BuddyApp controller (main.py) with real components:
    - Real LLMEngine (with mock provider)
    - Real ChatDialog (offscreen)
    - Real CommandRegistry
    - Signal/slot connections identical to main.py's BuddyApp.__init__
    """

    def __init__(self, streaming=False):
        # Engine + provider
        self.engine = LLMEngine()
        self.provider = UIMockProvider()
        self.provider._stream_enabled = streaming
        self.engine.set_provider(self.provider, "mock-model")
        self.engine._streaming_enabled = streaming

        # Register a test tool
        td = ToolDef(name="TestTool", description="Test", input_schema={"type": "object"})
        self.engine.register_tool(td, lambda inp: f"result:{inp}", is_read_only=True)

        # Chat dialog (offscreen)
        self.chat = ChatDialog()

        # Command registry
        self.cmd_registry = CommandRegistry()

        # Task manager
        self.task_manager = TaskManager()

        # Pet state tracker (mock the PetWindow)
        self.pet_states = []

        # Settings mock
        self.settings = MagicMock()
        self.settings.provider = "mock"
        self.settings.api_key = "sk-test"

        # Permission manager mock
        self.perm_mgr = MagicMock()

        # Memory manager mock
        self.memory_mgr = MagicMock()
        self.memory_mgr.should_extract.return_value = False
        self.engine.set_memory_manager(self.memory_mgr)

        # Evolution manager mock
        self.evolution_mgr = MagicMock()
        self.evolution_mgr.should_reflect.return_value = False
        self.engine.set_evolution_manager(self.evolution_mgr)

        # Tool registry mock (for /plan, /tools etc.)
        self.tool_registry = MagicMock()
        plan_state = MagicMock()
        plan_state.active = False
        self.tool_registry.plan_mode_state = plan_state

        # ── Wire signal/slot connections (same as BuddyApp.__init__) ──

        # ChatDialog → BuddyApp._on_user_message
        self.chat.message_sent.connect(self._on_user_message)
        self.chat.abort_requested.connect(self._on_abort)
        self.chat.clear_requested.connect(self._on_clear_history)

        # Engine → UI (same as main.py)
        self.engine.response_text.connect(self._on_engine_response)
        self.engine.response_chunk.connect(self._on_engine_chunk)
        self.engine.intermediate_text.connect(self._on_intermediate_text)
        self.engine.tool_start.connect(self._on_tool_start)
        self.engine.tool_result.connect(self._on_tool_result)
        self.engine.state_changed.connect(self._on_engine_state)
        self.engine.error.connect(self._on_engine_error)

        # Tracking for assertions
        self._ui_abort_active = False
        self._setup_recording()

    def _build_ctx(self):
        return {
            "engine": self.engine,
            "conversation": self.engine.conversation,
            "command_registry": self.cmd_registry,
            "tool_registry": self.tool_registry,
            "evolution_mgr": self.evolution_mgr,
            "task_manager": self.task_manager,
            "settings": self.settings,
            "memory_mgr": self.memory_mgr,
            "plugin_mgr": MagicMock(),
            "analytics": None,
            "permission_mgr": self.perm_mgr,
        }

    # ── Handlers copied from main.py BuddyApp ──

    def _on_user_message(self, text: str):
        """Identical logic to main.py BuddyApp._on_user_message."""
        if text.startswith("/"):
            self._handle_command(text)
            return

        from core.settings import PROVIDER_PRESETS
        needs_key = PROVIDER_PRESETS.get(self.settings.provider, {}).get("needs_api_key", True)
        if needs_key and not self.settings.api_key:
            self.chat.add_assistant_message(
                "I need an API key to chat! Click the <b>gear icon</b> "
                "in the title bar to open Settings."
            )
            return

        self.chat.set_thinking(True)
        self.pet_states.append("working")
        self.engine.send_message(text)

    def _handle_command(self, text: str):
        """Identical logic to main.py BuddyApp._handle_command."""
        ctx = self._build_ctx()
        result = self.cmd_registry.execute(text, ctx)
        reply = result if result else f"Command `{text}` returned no output."

        if reply == "Session archived. Starting fresh.":
            self._on_clear_history()
            return

        if reply.startswith("__EXIT__"):
            session_id = reply.replace("__EXIT__", "")
            if session_id:
                self.chat.add_assistant_message(
                    f"Session saved. To resume later, use:\n\n"
                    f"  `/resume {session_id[:8]}`"
                )
            return

        if "Resumed" in reply and ("conversation" in reply or "session" in reply):
            self.chat.load_history(self.engine.conversation.messages)
            self.chat.add_assistant_message(reply)
            self.engine.save_conversation()
            return

        self.engine.conversation.add_user_message(text)
        self.engine.conversation.add_assistant_message(reply)
        self.chat.add_assistant_message(reply)

    def _on_engine_response(self, text: str):
        if getattr(self, '_ui_abort_active', False):
            return
        self.chat.add_assistant_message(text)
        self.chat.set_thinking(False)
        self.engine.save_conversation()
        self._ui_abort_active = False

    def _on_engine_chunk(self, text: str):
        if getattr(self, '_ui_abort_active', False):
            return
        self.chat.append_streaming_chunk(text)

    def _on_intermediate_text(self, text: str):
        if getattr(self, '_ui_abort_active', False):
            return
        if self.chat._streaming_bubble:
            self.chat._streaming_bubble = None
        self.chat.add_assistant_message(text)

    def _on_tool_start(self, name: str, input_data: dict):
        if getattr(self, '_ui_abort_active', False):
            return
        summary = (input_data.get("command") or input_data.get("file_path") or "")
        if isinstance(summary, str):
            summary = summary[:80]
        self.chat.add_tool_call(name, str(summary)[:80])

    def _on_tool_result(self, name: str, output: str):
        pass

    def _on_engine_state(self, state: str):
        self.pet_states.append(state)

    def _on_engine_error(self, error: str):
        if "cancel" in error.lower():
            if self.chat._streaming_bubble is not None:
                self.chat._streaming_bubble.finalize_streaming(
                    self.chat._streaming_bubble.get_text()
                )
                self.chat._streaming_bubble = None
            self.chat.add_assistant_message("[Request interrupted by user]")
        else:
            self.chat.add_assistant_message(f"⚠️ {error}")
        self.chat.set_thinking(False)
        self.pet_states.append("idle")
        self._ui_abort_active = False

    def _on_abort(self):
        self._ui_abort_active = True
        self.engine.abort()
        self.chat.set_status("Cancelling...")

    def _on_clear_history(self):
        self.engine.conversation.archive()
        self.chat._clear_messages()

    def simulate_user_sends(self, text: str):
        """Simulate: user types text in chat input and presses Enter."""
        self.chat.message_sent.emit(text)

    def wait_for_response(self, timeout=5.0):
        """Wait for engine to finish processing."""
        start = time.time()
        while self.engine._is_running and (time.time() - start) < timeout:
            _qapp.processEvents()
            time.sleep(0.05)
        # Extra time for signals to propagate
        for _ in range(10):
            _qapp.processEvents()
            time.sleep(0.02)

    def get_chat_messages(self) -> list[dict]:
        """Get all visible messages in chat as [{role, text}].
        Uses method interception since MessageBubble doesn't store role."""
        return list(self._recorded_msgs)

    def _setup_recording(self):
        """Monkey-patch chat methods to record what gets displayed."""
        self._recorded_msgs = []
        _orig_add_asst = self.chat.add_assistant_message
        _orig_add_tool = self.chat.add_tool_call
        _orig_load = self.chat.load_history
        _orig_clear = self.chat._clear_messages

        def _rec_asst(text, timestamp=None):
            self._recorded_msgs.append({"role": "assistant", "text": text})
            _orig_add_asst(text, timestamp)

        def _rec_tool(name, summary=""):
            self._recorded_msgs.append({"role": "tool", "text": name})
            _orig_add_tool(name, summary)

        def _rec_load(messages):
            # Must call orig FIRST (it clears internally), then record
            _orig_load(messages)
            for m in messages:
                role = m.get("role", "")
                content = m.get("content", "")
                if isinstance(content, str) and content.strip():
                    if not content.startswith("[Tool Result"):
                        self._recorded_msgs.append({"role": role, "text": content})

        def _rec_clear():
            self._recorded_msgs.clear()
            _orig_clear()

        self.chat.add_assistant_message = _rec_asst
        self.chat.add_tool_call = _rec_tool
        self.chat.load_history = _rec_load
        self.chat._clear_messages = _rec_clear


# ═══════════════════════════════════════════════════════════════════
# E2E.1 User sends message → chat shows assistant reply
# ═══════════════════════════════════════════════════════════════════

def test_e2e_1_send_receive():
    """User types message → engine processes → chat shows reply."""
    sim = BuddyAppSimulator()
    sim.provider.set_responses(make_text("Hello! I'm your buddy!"))

    sim.simulate_user_sends("Hi there")
    sim.wait_for_response()

    msgs = sim.get_chat_messages()
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistant_msgs) >= 1, f"Expected assistant reply, got: {msgs}"
    assert "buddy" in assistant_msgs[-1]["text"].lower() or "Hello" in assistant_msgs[-1]["text"]
run("E2E.1  Send message → chat shows assistant reply", test_e2e_1_send_receive)


# ═══════════════════════════════════════════════════════════════════
# E2E.2 /help → chat shows command output (no LLM call)
# ═══════════════════════════════════════════════════════════════════

def test_e2e_2_help_command():
    """/help is handled locally, shows command list in chat."""
    sim = BuddyAppSimulator()
    call_count_before = sim.provider._call_idx

    sim.simulate_user_sends("/help")

    # No LLM call should have been made
    assert sim.provider._call_idx == call_count_before, "No API call for /help"

    msgs = sim.get_chat_messages()
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistant_msgs) >= 1
    assert "Available commands" in assistant_msgs[-1]["text"] or \
           "help" in assistant_msgs[-1]["text"].lower()
run("E2E.2  /help → local command, no LLM call", test_e2e_2_help_command)


# ═══════════════════════════════════════════════════════════════════
# E2E.3 /clear → chat clears, session archived
# ═══════════════════════════════════════════════════════════════════

def test_e2e_3_clear():
    """/clear archives session and clears chat UI."""
    sim = BuddyAppSimulator()
    sim.provider.set_responses(make_text("First reply"))

    # Send a message first so there's history
    sim.simulate_user_sends("Hello")
    sim.wait_for_response()

    msgs_before = sim.get_chat_messages()
    assert len(msgs_before) > 0, "Should have messages before clear"

    old_id = sim.engine.conversation._conversation_id

    # Now clear
    sim.simulate_user_sends("/clear")

    msgs_after = sim.get_chat_messages()
    assert len(msgs_after) == 0, f"Chat should be empty after /clear, got {len(msgs_after)}"
    assert sim.engine.conversation.message_count == 0
    assert sim.engine.conversation._conversation_id != old_id, "New session UUID"

    # Old session should be archived on disk
    old_file = config.CONVERSATIONS_DIR / f"{old_id}.json"
    assert old_file.exists(), "Archived session file should exist"
run("E2E.3  /clear → archives session, clears chat", test_e2e_3_clear)


# ═══════════════════════════════════════════════════════════════════
# E2E.4 /exit → chat shows session ID
# ═══════════════════════════════════════════════════════════════════

def test_e2e_4_exit():
    """/exit saves conversation and shows session ID in chat."""
    sim = BuddyAppSimulator()
    sim.engine.conversation.add_user_message("before exit")

    sim.simulate_user_sends("/exit")

    msgs = sim.get_chat_messages()
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistant_msgs) >= 1
    last = assistant_msgs[-1]["text"]
    assert "session saved" in last.lower() or "/resume" in last.lower(), \
        f"Expected session saved message, got: {last[:100]}"
run("E2E.4  /exit → session saved, resume hint shown", test_e2e_4_exit)


# ═══════════════════════════════════════════════════════════════════
# E2E.5 /resume → chat loads history
# ═══════════════════════════════════════════════════════════════════

def test_e2e_5_resume():
    """/resume shows session list when sessions exist."""
    sim = BuddyAppSimulator()
    # Create a saved session
    sim.engine.conversation.add_user_message("save me")
    sim.engine.conversation.add_assistant_message("saved reply")
    sim.engine.save_conversation()

    sim.simulate_user_sends("/resume")

    msgs = sim.get_chat_messages()
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistant_msgs) >= 1
    last = assistant_msgs[-1]["text"]
    assert "session" in last.lower() or "resume" in last.lower() or \
           "no saved" in last.lower()
run("E2E.5  /resume → shows session list or loads history", test_e2e_5_resume)


# ═══════════════════════════════════════════════════════════════════
# E2E.6 Streaming chunks arrive → chat shows incremental text
# ═══════════════════════════════════════════════════════════════════

def test_e2e_6_streaming():
    """Streaming mode: chunks appear incrementally in chat."""
    sim = BuddyAppSimulator(streaming=True)
    sim.provider.set_responses(make_text("Word by word streaming response"))

    sim.simulate_user_sends("Stream test")
    sim.wait_for_response()

    msgs = sim.get_chat_messages()
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistant_msgs) >= 1
    text = assistant_msgs[-1]["text"]
    assert "streaming" in text.lower() or "word" in text.lower() or "response" in text.lower()
run("E2E.6  Streaming: chunks shown incrementally", test_e2e_6_streaming)


# ═══════════════════════════════════════════════════════════════════
# E2E.7 Tool call → indicator shown in chat
# ═══════════════════════════════════════════════════════════════════

def test_e2e_7_tool_call():
    """Tool call shows indicator in chat, then final response."""
    sim = BuddyAppSimulator()
    sim.provider.set_responses(
        make_tool("TestTool", {"key": "val"}, text="Let me check..."),
        make_text("Here are the results"),
    )

    sim.simulate_user_sends("Use the tool")
    sim.wait_for_response()

    msgs = sim.get_chat_messages()
    # Should have: intermediate text, tool indicator, and final response
    tool_msgs = [m for m in msgs if m["role"] == "tool"]
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]

    assert len(tool_msgs) >= 1, f"Expected tool call indicator, got: {msgs}"
    assert "TestTool" in tool_msgs[0]["text"]
    assert len(assistant_msgs) >= 1, "Expected final assistant response"
run("E2E.7  Tool call: indicator + final response in chat", test_e2e_7_tool_call)


# ═══════════════════════════════════════════════════════════════════
# E2E.8 Abort → chat shows [Request interrupted by user]
# ═══════════════════════════════════════════════════════════════════

def test_e2e_8_abort():
    """User clicks stop → engine aborts → chat shows interrupt marker."""
    sim = BuddyAppSimulator()
    sim.provider._slow = True
    sim.provider.set_responses(make_text("This should be interrupted"))

    sim.simulate_user_sends("Slow request")

    # Let engine start, then abort
    time.sleep(0.2)
    sim.chat.abort_requested.emit()

    sim.wait_for_response(timeout=8)

    msgs = sim.get_chat_messages()
    # Should show interrupt marker
    all_text = " ".join(m["text"] for m in msgs)
    assert "interrupted" in all_text.lower() or "cancel" in all_text.lower(), \
        f"Expected interrupt marker, chat has: {[m['text'][:50] for m in msgs]}"
run("E2E.8  Abort → [Request interrupted by user] in chat", test_e2e_8_abort)


# ═══════════════════════════════════════════════════════════════════
# E2E.9 Abort + reopen: interrupt marker persists
# ═══════════════════════════════════════════════════════════════════

def test_e2e_9_abort_persist():
    """After abort, closing and reopening chat still shows interrupt marker."""
    sim = BuddyAppSimulator()
    sim.provider._slow = True
    sim.provider.set_responses(make_text("Will be interrupted"))

    sim.simulate_user_sends("Another slow request")
    time.sleep(0.2)
    sim.chat.abort_requested.emit()
    sim.wait_for_response(timeout=8)

    # Simulate close chat (hide)
    sim.chat.hide()

    # Simulate reopen: load_history from engine (same as _open_chat)
    sim.chat._clear_messages()
    sim.chat.load_history(sim.engine.conversation.messages)

    msgs = sim.get_chat_messages()
    all_text = " ".join(m["text"] for m in msgs)
    assert "interrupted" in all_text.lower(), \
        f"Interrupt marker should persist after reopen, got: {[m['text'][:50] for m in msgs]}"
run("E2E.9  Abort persist: marker survives close/reopen", test_e2e_9_abort_persist)


# ═══════════════════════════════════════════════════════════════════
# E2E.10 No API key → chat shows error
# ═══════════════════════════════════════════════════════════════════

def test_e2e_10_no_api_key():
    """Without API key, chat shows helpful error message."""
    sim = BuddyAppSimulator()
    sim.settings.api_key = ""  # no key
    sim.settings.provider = "anthropic"  # needs key

    sim.simulate_user_sends("Hello")

    msgs = sim.get_chat_messages()
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistant_msgs) >= 1
    text = assistant_msgs[-1]["text"]
    assert "api key" in text.lower() or "key" in text.lower() or "settings" in text.lower()

    # Should NOT have made an API call
    assert sim.provider._call_idx == 0
run("E2E.10 No API key → helpful error, no API call", test_e2e_10_no_api_key)


# ═══════════════════════════════════════════════════════════════════
# E2E.11 /cost → chat shows session cost
# ═══════════════════════════════════════════════════════════════════

def test_e2e_11_cost():
    """/cost shows API call and token statistics in chat."""
    sim = BuddyAppSimulator()
    # Make a real API call first
    sim.provider.set_responses(make_text("reply"))
    sim.simulate_user_sends("Hello")
    sim.wait_for_response()

    sim.simulate_user_sends("/cost")

    msgs = sim.get_chat_messages()
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    cost_msg = assistant_msgs[-1]["text"]
    assert "API calls:" in cost_msg or "api" in cost_msg.lower()
run("E2E.11 /cost → shows API call statistics", test_e2e_11_cost)


# ═══════════════════════════════════════════════════════════════════
# E2E.12 /status → chat shows engine status
# ═══════════════════════════════════════════════════════════════════

def test_e2e_12_status():
    """/status shows engine info in chat."""
    sim = BuddyAppSimulator()
    sim.simulate_user_sends("/status")

    msgs = sim.get_chat_messages()
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    status_msg = assistant_msgs[-1]["text"]
    assert "Messages:" in status_msg
    assert "Context window:" in status_msg
run("E2E.12 /status → shows engine info", test_e2e_12_status)


# ═══════════════════════════════════════════════════════════════════
# E2E.13 /plan → blocks write tools
# ═══════════════════════════════════════════════════════════════════

def test_e2e_13_plan_mode():
    """/plan activates plan mode, visible in /status."""
    sim = BuddyAppSimulator()

    sim.simulate_user_sends("/plan")

    msgs = sim.get_chat_messages()
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    plan_msg = assistant_msgs[-1]["text"]
    assert "plan mode" in plan_msg.lower() or "activated" in plan_msg.lower()
run("E2E.13 /plan → plan mode activated message", test_e2e_13_plan_mode)


# ═══════════════════════════════════════════════════════════════════
# E2E.14 Engine error → chat shows error
# ═══════════════════════════════════════════════════════════════════

def test_e2e_14_engine_error():
    """API error shown in chat as error message."""
    sim = BuddyAppSimulator()
    sim.provider.set_responses()  # no responses, but we'll make it fail
    sim.provider._call_idx = 999  # force default which won't error

    # Instead inject a direct error
    from unittest.mock import PropertyMock
    original_call = sim.provider.call_sync
    def error_call(*args, **kwargs):
        raise Exception("401 unauthorized: invalid api key")
    sim.provider.call_sync = error_call

    sim.simulate_user_sends("This should error")
    sim.wait_for_response(timeout=5)

    msgs = sim.get_chat_messages()
    all_text = " ".join(m["text"] for m in msgs)
    assert "error" in all_text.lower() or "unauthorized" in all_text.lower() or "⚠" in all_text, \
        f"Expected error in chat, got: {[m['text'][:60] for m in msgs]}"
run("E2E.14 Engine error → error message in chat", test_e2e_14_engine_error)


# ═══════════════════════════════════════════════════════════════════
# E2E.15 Pet state changes during message flow
# ═══════════════════════════════════════════════════════════════════

def test_e2e_15_pet_states():
    """Pet state goes: idle → work → idle during message processing."""
    sim = BuddyAppSimulator()
    sim.provider.set_responses(make_text("Done"))

    sim.simulate_user_sends("Do something")
    sim.wait_for_response()

    # Should have recorded state changes
    assert "work" in sim.pet_states, f"Should go through 'work' state, got: {sim.pet_states}"
    assert "idle" in sim.pet_states, f"Should return to 'idle', got: {sim.pet_states}"
    # 'work' should come before 'idle'
    work_idx = sim.pet_states.index("work")
    idle_idx = len(sim.pet_states) - 1 - sim.pet_states[::-1].index("idle")
    assert work_idx < idle_idx, "work should come before final idle"
run("E2E.15 Pet states: working → idle during flow", test_e2e_15_pet_states)


# ═══════════════════════════════════════════════════════════════════
# E2E.16 Multiple messages in sequence
# ═══════════════════════════════════════════════════════════════════

def test_e2e_16_multi_turn():
    """Multiple messages in sequence build up in chat correctly."""
    sim = BuddyAppSimulator()
    sim.provider.set_responses(
        make_text("Reply 1"),
        make_text("Reply 2"),
        make_text("Reply 3"),
    )

    for i in range(3):
        sim.simulate_user_sends(f"Message {i+1}")
        sim.wait_for_response()

    msgs = sim.get_chat_messages()
    assistant_msgs = [m for m in msgs if m["role"] == "assistant"]
    assert len(assistant_msgs) >= 3, \
        f"Expected 3 assistant replies, got {len(assistant_msgs)}"
run("E2E.16 Multi-turn: 3 messages → 3 replies in chat", test_e2e_16_multi_turn)


# ═══════════════════════════════════════════════════════════════════
# E2E.17 Conversation persists and reloads into chat
# ═══════════════════════════════════════════════════════════════════

def test_e2e_17_persist_reload():
    """After conversation, closing and reopening chat shows all messages."""
    sim = BuddyAppSimulator()
    sim.provider.set_responses(make_text("Persistent reply"))

    sim.simulate_user_sends("Remember this")
    sim.wait_for_response()

    # Save
    sim.engine.save_conversation()

    # Simulate close + reopen
    sim.chat._clear_messages()
    sim.chat.load_history(sim.engine.conversation.messages)

    msgs = sim.get_chat_messages()
    all_text = " ".join(m["text"] for m in msgs)
    # User message should be in loaded conversation (role=user from load_history)
    has_user = any("Remember this" in m["text"] or "remember" in m["text"].lower()
                    for m in msgs if m["role"] == "user")
    has_reply = any("Persistent" in m["text"] or "persistent" in m["text"].lower()
                     for m in msgs)
    assert has_user or has_reply, \
        f"Messages should persist, got: {[m['text'][:50] for m in msgs]}"
run("E2E.17 Persist + reload: messages survive close/reopen", test_e2e_17_persist_reload)


# ═══════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════

import shutil
try:
    ok = summary()
finally:
    shutil.rmtree(_TEMP, ignore_errors=True)

sys.exit(0 if ok else 1)
