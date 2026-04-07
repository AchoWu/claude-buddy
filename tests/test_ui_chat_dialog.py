"""UI tests for ChatDialog (ui/chat_dialog.py)."""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from ui.chat_dialog import ChatDialog

PASS = 0; FAIL = 0; ERRORS = []
def run(name, fn):
    global PASS, FAIL
    try: fn(); PASS += 1; print(f'  OK  {name}')
    except Exception as e: FAIL += 1; ERRORS.append((name, str(e))); print(f'  FAIL {name}: {e}')


def _msg_count(dlg):
    """Count message widgets (layout count minus stretch and thinking indicator = 2)."""
    return dlg._messages_layout.count() - 2


def test_add_user_message_increases_count():
    dlg = ChatDialog()
    before = _msg_count(dlg)
    dlg.add_user_message("hello")
    assert _msg_count(dlg) == before + 1

def test_add_assistant_message_increases_count():
    dlg = ChatDialog()
    before = _msg_count(dlg)
    dlg.add_assistant_message("hi there")
    assert _msg_count(dlg) == before + 1

def test_enter_key_sends_message():
    dlg = ChatDialog()
    dlg.show()
    captured = []
    dlg.message_sent.connect(lambda t: captured.append(t))
    QTest.keyClicks(dlg._input, "test message")
    QTest.keyClick(dlg._input, Qt.Key.Key_Return)
    app.processEvents()
    assert len(captured) >= 1, f"message_sent not emitted, captured={captured}"
    assert captured[0] == "test message", f"Expected 'test message', got '{captured[0]}'"

def test_empty_input_does_not_send():
    dlg = ChatDialog()
    dlg.show()
    captured = []
    dlg.message_sent.connect(lambda t: captured.append(t))
    dlg._input.clear()
    QTest.keyClick(dlg._input, Qt.Key.Key_Return)
    app.processEvents()
    assert len(captured) == 0, f"message_sent emitted for empty input, captured={captured}"

def test_append_streaming_chunk():
    dlg = ChatDialog()
    before = _msg_count(dlg)
    dlg.append_streaming_chunk("chunk1")
    assert _msg_count(dlg) == before + 1, "Streaming bubble not created"
    dlg.append_streaming_chunk("chunk2")
    # Should still be same count (appending to existing bubble)
    assert _msg_count(dlg) == before + 1, "Extra bubble created for streaming chunk"
    assert dlg._streaming_bubble is not None

def test_set_thinking_true():
    dlg = ChatDialog()
    dlg.show()
    app.processEvents()
    dlg.set_thinking(True)
    app.processEvents()
    # ThinkingIndicator.start() calls show() and starts timer
    assert not dlg._input.isEnabled(), "Input should be disabled during thinking"
    assert dlg._thinking._timer.isActive(), "Thinking timer should be active"

def test_set_thinking_false():
    dlg = ChatDialog()
    dlg.set_thinking(True)
    dlg.set_thinking(False)
    assert not dlg._thinking.isVisible(), "Thinking indicator still visible"
    assert dlg._input.isEnabled(), "Input should be enabled after thinking"

def test_add_tool_call():
    dlg = ChatDialog()
    before = _msg_count(dlg)
    dlg.add_tool_call("Bash", "git status")
    assert _msg_count(dlg) == before + 1

def test_escape_hides_dialog():
    dlg = ChatDialog()
    dlg.show()
    app.processEvents()
    assert dlg.isVisible()
    QTest.keyClick(dlg, Qt.Key.Key_Escape)
    app.processEvents()
    assert not dlg.isVisible(), "Dialog not hidden after Escape"

def test_clear_button_emits_clear_requested():
    dlg = ChatDialog()
    dlg.show()
    captured = []
    dlg.clear_requested.connect(lambda: captured.append(True))
    # Find clearBtn
    clear_btn = dlg.findChild(type(dlg._input).__mro__[1], "clearBtn")  # QPushButton
    from PyQt6.QtWidgets import QPushButton
    clear_btn = dlg.findChild(QPushButton, "clearBtn")
    assert clear_btn is not None, "clearBtn not found"
    clear_btn.click()
    app.processEvents()
    assert len(captured) >= 1, "clear_requested not emitted"

def test_load_history_creates_bubbles():
    dlg = ChatDialog()
    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    dlg.load_history(messages)
    # Should have at least 2 message bubbles
    assert _msg_count(dlg) >= 2, f"Expected >=2 messages, got {_msg_count(dlg)}"

def test_set_status_updates_label():
    dlg = ChatDialog()
    dlg.set_status("Processing...")
    assert "Processing..." in dlg._status.text()

def test_has_shown_once_starts_false():
    dlg = ChatDialog()
    assert dlg._has_shown_once is False, f"_has_shown_once should start False"

def test_initial_size():
    dlg = ChatDialog()
    assert dlg.width() == 600, f"Expected width 600, got {dlg.width()}"
    assert dlg.height() == 720, f"Expected height 720, got {dlg.height()}"

def test_message_sent_carries_text():
    dlg = ChatDialog()
    captured = []
    dlg.message_sent.connect(lambda t: captured.append(t))
    dlg._input.setText("hello world")
    dlg._on_send()
    app.processEvents()
    assert captured == ["hello world"], f"Expected ['hello world'], got {captured}"


if __name__ == "__main__":
    print("=== test_ui_chat_dialog ===")
    run("add_user_message_increases_count", test_add_user_message_increases_count)
    run("add_assistant_message_increases_count", test_add_assistant_message_increases_count)
    run("enter_key_sends_message", test_enter_key_sends_message)
    run("empty_input_does_not_send", test_empty_input_does_not_send)
    run("append_streaming_chunk", test_append_streaming_chunk)
    run("set_thinking_true", test_set_thinking_true)
    run("set_thinking_false", test_set_thinking_false)
    run("add_tool_call", test_add_tool_call)
    run("escape_hides_dialog", test_escape_hides_dialog)
    run("clear_button_emits_clear_requested", test_clear_button_emits_clear_requested)
    run("load_history_creates_bubbles", test_load_history_creates_bubbles)
    run("set_status_updates_label", test_set_status_updates_label)
    run("has_shown_once_starts_false", test_has_shown_once_starts_false)
    run("initial_size", test_initial_size)
    run("message_sent_carries_text", test_message_sent_carries_text)
    print(f"\n  PASS={PASS}  FAIL={FAIL}")
    if ERRORS:
        print("  Failures:")
        for name, err in ERRORS:
            print(f"    - {name}: {err}")
    sys.exit(0 if FAIL == 0 else 1)
