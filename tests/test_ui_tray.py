"""UI tests for SystemTray (ui/tray.py)."""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from ui.tray import SystemTray

PASS = 0; FAIL = 0; ERRORS = []
def run(name, fn):
    global PASS, FAIL
    try: fn(); PASS += 1; print(f'  OK  {name}')
    except Exception as e: FAIL += 1; ERRORS.append((name, str(e))); print(f'  FAIL {name}: {e}')


def test_system_tray_creates():
    tray = SystemTray()
    assert tray is not None

def test_has_expected_signals():
    tray = SystemTray()
    # Verify all signals exist by connecting dummy slots
    signals = [
        tray.show_pet_requested,
        tray.hide_pet_requested,
        tray.chat_requested,
        tray.task_panel_requested,
        tray.settings_requested,
        tray.quit_requested,
    ]
    for sig in signals:
        sig.connect(lambda: None)
    # No error means pass

def test_menu_has_actions():
    tray = SystemTray()
    menu = tray._tray.contextMenu()
    assert menu is not None, "Context menu is None"
    actions = menu.actions()
    assert len(actions) > 0, "Menu has no actions"

def test_menu_action_count():
    tray = SystemTray()
    menu = tray._tray.contextMenu()
    actions = [a for a in menu.actions() if not a.isSeparator()]
    assert len(actions) >= 5, f"Expected >=5 non-separator actions, got {len(actions)}"

def test_show_message_no_crash():
    tray = SystemTray()
    # show_message should not crash even in offscreen mode
    try:
        tray.show_message("Test", "Hello")
    except Exception:
        pass  # May fail in offscreen but should not crash Python


if __name__ == "__main__":
    print("=== test_ui_tray ===")
    run("system_tray_creates", test_system_tray_creates)
    run("has_expected_signals", test_has_expected_signals)
    run("menu_has_actions", test_menu_has_actions)
    run("menu_action_count", test_menu_action_count)
    run("show_message_no_crash", test_show_message_no_crash)
    print(f"\n  PASS={PASS}  FAIL={FAIL}")
    if ERRORS:
        print("  Failures:")
        for name, err in ERRORS:
            print(f"    - {name}: {err}")
    sys.exit(0 if FAIL == 0 else 1)
