"""UI integration tests — cross-component interactions."""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from PyQt6.QtCore import Qt, QPoint
from PyQt6.QtTest import QTest
from ui.pet_window import PetWindow, PetState
from ui.chat_dialog import ChatDialog
from ui.speech_bubble import SpeechBubble

PASS = 0; FAIL = 0; ERRORS = []
def run(name, fn):
    global PASS, FAIL
    try: fn(); PASS += 1; print(f'  OK  {name}')
    except Exception as e: FAIL += 1; ERRORS.append((name, str(e))); print(f'  FAIL {name}: {e}')


def test_pet_click_signal_fires():
    pet = PetWindow()
    pet.show()
    captured = []
    pet.clicked.connect(lambda: captured.append(True))
    QTest.mouseClick(pet, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert len(captured) >= 1, "PetWindow clicked signal did not fire"

def test_pet_double_click_signal_fires():
    pet = PetWindow()
    pet.show()
    captured = []
    pet.double_clicked.connect(lambda: captured.append(True))
    QTest.mouseDClick(pet, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert len(captured) >= 1, "PetWindow double_clicked signal did not fire"

def test_chat_dialog_add_messages_count():
    dlg = ChatDialog()
    count_base = dlg._messages_layout.count() - 2
    dlg.add_user_message("Hello")
    dlg.add_assistant_message("Hi!")
    dlg.add_user_message("How are you?")
    app.processEvents()
    count_after = dlg._messages_layout.count() - 2
    assert count_after == count_base + 3, f"Expected {count_base + 3} msgs, got {count_after}"

def test_speech_bubble_show_hide_cycle():
    bubble = SpeechBubble()
    assert not bubble.isVisible()
    bubble.show_message("Hello!", QPoint(300, 300))
    app.processEvents()
    assert bubble.isVisible()
    bubble.hide()
    app.processEvents()
    assert not bubble.isVisible()

def test_pet_state_changes_cycle():
    pet = PetWindow()
    states = [PetState.IDLE, PetState.TALKING, PetState.WORKING,
              PetState.SLEEPING, PetState.WALKING, PetState.CELEBRATING]
    for state in states:
        pet.set_pet_state(state)
        assert pet.pet_state == state, f"State mismatch: expected {state}, got {pet.pet_state}"
    # Return to idle
    pet.set_pet_state(PetState.IDLE)
    assert pet.pet_state == PetState.IDLE

def test_chat_streaming_finalize_flow():
    dlg = ChatDialog()
    base = dlg._messages_layout.count() - 2
    # Start streaming
    dlg.append_streaming_chunk("Hello ")
    assert dlg._streaming_bubble is not None
    count_mid = dlg._messages_layout.count() - 2
    assert count_mid == base + 1
    # More chunks
    dlg.append_streaming_chunk("world!")
    assert dlg._streaming_bubble._label.text() == "Hello world!"
    # Finalize by calling add_assistant_message (which uses existing streaming bubble)
    dlg.add_assistant_message("Hello world!")
    assert dlg._streaming_bubble is None, "Streaming bubble should be cleared after finalize"
    count_final = dlg._messages_layout.count() - 2
    assert count_final == base + 1, "Should still be 1 message after finalize"


if __name__ == "__main__":
    print("=== test_ui_integration ===")
    run("pet_click_signal_fires", test_pet_click_signal_fires)
    run("pet_double_click_signal_fires", test_pet_double_click_signal_fires)
    run("chat_dialog_add_messages_count", test_chat_dialog_add_messages_count)
    run("speech_bubble_show_hide_cycle", test_speech_bubble_show_hide_cycle)
    run("pet_state_changes_cycle", test_pet_state_changes_cycle)
    run("chat_streaming_finalize_flow", test_chat_streaming_finalize_flow)
    print(f"\n  PASS={PASS}  FAIL={FAIL}")
    if ERRORS:
        print("  Failures:")
        for name, err in ERRORS:
            print(f"    - {name}: {err}")
    sys.exit(0 if FAIL == 0 else 1)
