"""UI tests for SpeechBubble (ui/speech_bubble.py)."""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from PyQt6.QtCore import QPoint
from ui.speech_bubble import SpeechBubble

PASS = 0; FAIL = 0; ERRORS = []
def run(name, fn):
    global PASS, FAIL
    try: fn(); PASS += 1; print(f'  OK  {name}')
    except Exception as e: FAIL += 1; ERRORS.append((name, str(e))); print(f'  FAIL {name}: {e}')


def test_show_message_makes_visible():
    bubble = SpeechBubble()
    bubble.show_message("Hello!", QPoint(400, 300))
    app.processEvents()
    assert bubble.isVisible(), "Bubble not visible after show_message"

def test_show_message_sets_label_text():
    bubble = SpeechBubble()
    bubble.show_message("Test text", QPoint(400, 300))
    app.processEvents()
    assert "Test text" in bubble._label.text(), f"Label text: '{bubble._label.text()}'"

def test_follow_anchor_changes_position():
    bubble = SpeechBubble()
    bubble.show_message("Hello", QPoint(400, 300))
    app.processEvents()
    pos1 = bubble.pos()
    bubble.follow_anchor(QPoint(600, 500))
    app.processEvents()
    pos2 = bubble.pos()
    assert pos1 != pos2, f"Position did not change: {pos1} == {pos2}"

def test_initially_hidden():
    bubble = SpeechBubble()
    assert not bubble.isVisible(), "Bubble should start hidden"

def test_show_message_positions_near_anchor():
    bubble = SpeechBubble()
    anchor = QPoint(500, 400)
    bubble.show_message("Positioned text", anchor)
    app.processEvents()
    # Bubble should be somewhere near the anchor (above it)
    bpos = bubble.pos()
    # Y should be less than anchor Y (bubble is above)
    assert bpos.y() < anchor.y(), f"Bubble y={bpos.y()} not above anchor y={anchor.y()}"

def test_paint_event_no_crash():
    bubble = SpeechBubble()
    bubble.show_message("Paint test", QPoint(300, 300))
    app.processEvents()
    bubble.repaint()
    app.processEvents()
    # No crash means pass


if __name__ == "__main__":
    print("=== test_ui_speech_bubble ===")
    run("show_message_makes_visible", test_show_message_makes_visible)
    run("show_message_sets_label_text", test_show_message_sets_label_text)
    run("follow_anchor_changes_position", test_follow_anchor_changes_position)
    run("initially_hidden", test_initially_hidden)
    run("show_message_positions_near_anchor", test_show_message_positions_near_anchor)
    run("paint_event_no_crash", test_paint_event_no_crash)
    print(f"\n  PASS={PASS}  FAIL={FAIL}")
    if ERRORS:
        print("  Failures:")
        for name, err in ERRORS:
            print(f"    - {name}: {err}")
    sys.exit(0 if FAIL == 0 else 1)
