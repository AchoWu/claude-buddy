"""UI tests for SettingsDialog (ui/settings_dialog.py)."""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLineEdit, QComboBox
from core.settings import Settings
from ui.settings_dialog import SettingsDialog

PASS = 0; FAIL = 0; ERRORS = []
def run(name, fn):
    global PASS, FAIL
    try: fn(); PASS += 1; print(f'  OK  {name}')
    except Exception as e: FAIL += 1; ERRORS.append((name, str(e))); print(f'  FAIL {name}: {e}')


def _make_dialog():
    settings = Settings()
    return SettingsDialog(settings)


def test_dialog_creates_without_crash():
    dlg = _make_dialog()
    assert dlg is not None

def test_has_provider_combo():
    dlg = _make_dialog()
    assert dlg._provider_combo is not None
    assert isinstance(dlg._provider_combo, QComboBox)
    assert dlg._provider_combo.count() > 0

def test_has_api_key_input():
    dlg = _make_dialog()
    assert dlg._api_key_input is not None
    assert isinstance(dlg._api_key_input, QLineEdit)

def test_api_key_is_password_mode():
    dlg = _make_dialog()
    assert dlg._api_key_input.echoMode() == QLineEdit.EchoMode.Password

def test_settings_changed_signal_exists():
    dlg = _make_dialog()
    # Verify the signal exists by connecting a dummy slot
    captured = []
    dlg.settings_changed.connect(lambda: captured.append(True))
    # Signal should be connectable without error

def test_has_permission_combo():
    dlg = _make_dialog()
    assert dlg._perm_combo is not None
    assert isinstance(dlg._perm_combo, QComboBox)
    assert dlg._perm_combo.count() >= 3  # default, auto, bypass

def test_dialog_is_frameless():
    dlg = _make_dialog()
    flags = dlg.windowFlags()
    assert flags & Qt.WindowType.FramelessWindowHint, "Missing FramelessWindowHint"


if __name__ == "__main__":
    print("=== test_ui_settings_dialog ===")
    run("dialog_creates_without_crash", test_dialog_creates_without_crash)
    run("has_provider_combo", test_has_provider_combo)
    run("has_api_key_input", test_has_api_key_input)
    run("api_key_is_password_mode", test_api_key_is_password_mode)
    run("settings_changed_signal_exists", test_settings_changed_signal_exists)
    run("has_permission_combo", test_has_permission_combo)
    run("dialog_is_frameless", test_dialog_is_frameless)
    print(f"\n  PASS={PASS}  FAIL={FAIL}")
    if ERRORS:
        print("  Failures:")
        for name, err in ERRORS:
            print(f"    - {name}: {err}")
    sys.exit(0 if FAIL == 0 else 1)
