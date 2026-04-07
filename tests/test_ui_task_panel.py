"""UI tests for TaskPanel (ui/task_panel.py)."""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from ui.task_panel import TaskPanel

PASS = 0; FAIL = 0; ERRORS = []
def run(name, fn):
    global PASS, FAIL
    try: fn(); PASS += 1; print(f'  OK  {name}')
    except Exception as e: FAIL += 1; ERRORS.append((name, str(e))); print(f'  FAIL {name}: {e}')


def test_empty_state_shows_no_tasks():
    panel = TaskPanel()
    panel.show()
    app.processEvents()
    panel.refresh([])
    app.processEvents()
    # After refresh with empty list, empty_label should not be hidden
    assert not panel._empty_label.isHidden(), "Empty label should be visible when no tasks"

def test_refresh_with_tasks_populates():
    panel = TaskPanel()
    tasks = [
        {"id": "1", "subject": "Fix bug", "status": "pending"},
        {"id": "2", "subject": "Write tests", "status": "in_progress"},
    ]
    panel.refresh(tasks)
    app.processEvents()
    assert not panel._empty_label.isVisible(), "Empty label should be hidden when tasks exist"
    # list_layout has task items + stretch
    assert panel._list_layout.count() > 1, "Tasks not added to layout"

def test_task_status_badges():
    panel = TaskPanel()
    tasks = [
        {"id": "1", "subject": "Done task", "status": "completed"},
        {"id": "2", "subject": "Working", "status": "in_progress"},
    ]
    panel.refresh(tasks)
    app.processEvents()
    # Count should be tasks + stretch = 3
    assert panel._list_layout.count() >= 3, f"Expected >=3 items, got {panel._list_layout.count()}"

def test_creation_no_crash():
    panel = TaskPanel()
    assert panel is not None

def test_escape_hides():
    panel = TaskPanel()
    panel.show()
    app.processEvents()
    assert panel.isVisible()
    QTest.keyClick(panel, Qt.Key.Key_Escape)
    app.processEvents()
    assert not panel.isVisible(), "TaskPanel not hidden after Escape"


if __name__ == "__main__":
    print("=== test_ui_task_panel ===")
    run("empty_state_shows_no_tasks", test_empty_state_shows_no_tasks)
    run("refresh_with_tasks_populates", test_refresh_with_tasks_populates)
    run("task_status_badges", test_task_status_badges)
    run("creation_no_crash", test_creation_no_crash)
    run("escape_hides", test_escape_hides)
    print(f"\n  PASS={PASS}  FAIL={FAIL}")
    if ERRORS:
        print("  Failures:")
        for name, err in ERRORS:
            print(f"    - {name}: {err}")
    sys.exit(0 if FAIL == 0 else 1)
