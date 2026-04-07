"""UI tests for NotificationQueue (ui/notification.py)."""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from PyQt6.QtCore import QPoint
from ui.notification import NotificationQueue, MAX_VISIBLE_TOASTS

PASS = 0; FAIL = 0; ERRORS = []
def run(name, fn):
    global PASS, FAIL
    try: fn(); PASS += 1; print(f'  OK  {name}')
    except Exception as e: FAIL += 1; ERRORS.append((name, str(e))); print(f'  FAIL {name}: {e}')


def test_show_creates_notification():
    nq = NotificationQueue()
    nq.set_anchor(QPoint(400, 300))
    nq.show("Hello")
    app.processEvents()
    assert len(nq._active) == 1, f"Expected 1 active, got {len(nq._active)}"

def test_max_3_active():
    nq = NotificationQueue()
    nq.set_anchor(QPoint(400, 300))
    for i in range(5):
        nq.show(f"Notification {i}")
    app.processEvents()
    assert len(nq._active) <= MAX_VISIBLE_TOASTS, \
        f"Expected <={MAX_VISIBLE_TOASTS} active, got {len(nq._active)}"
    assert len(nq._pending) == 2, f"Expected 2 pending, got {len(nq._pending)}"

def test_show_success_and_error():
    nq = NotificationQueue()
    nq.set_anchor(QPoint(400, 300))
    nq.show_success("Done!")
    nq.show_error("Oops!")
    app.processEvents()
    assert len(nq._active) == 2, f"Expected 2 active, got {len(nq._active)}"

def test_notify_task_created():
    nq = NotificationQueue()
    nq.set_anchor(QPoint(400, 300))
    nq.notify_task_created("Fix login bug")
    app.processEvents()
    assert len(nq._active) == 1

def test_set_anchor_stores_position():
    nq = NotificationQueue()
    anchor = QPoint(500, 400)
    nq.set_anchor(anchor)
    assert nq._anchor == anchor

def test_queue_overflow_goes_to_pending():
    nq = NotificationQueue()
    nq.set_anchor(QPoint(400, 300))
    for i in range(4):
        nq.show(f"Msg {i}")
    app.processEvents()
    assert len(nq._active) == MAX_VISIBLE_TOASTS
    assert len(nq._pending) == 1, f"Expected 1 pending, got {len(nq._pending)}"

def test_creation_no_crash():
    nq = NotificationQueue()
    assert nq is not None
    assert nq._active == []
    assert nq._pending == []


if __name__ == "__main__":
    print("=== test_ui_notification ===")
    run("show_creates_notification", test_show_creates_notification)
    run("max_3_active", test_max_3_active)
    run("show_success_and_error", test_show_success_and_error)
    run("notify_task_created", test_notify_task_created)
    run("set_anchor_stores_position", test_set_anchor_stores_position)
    run("queue_overflow_goes_to_pending", test_queue_overflow_goes_to_pending)
    run("creation_no_crash", test_creation_no_crash)
    print(f"\n  PASS={PASS}  FAIL={FAIL}")
    if ERRORS:
        print("  Failures:")
        for name, err in ERRORS:
            print(f"    - {name}: {err}")
    sys.exit(0 if FAIL == 0 else 1)
