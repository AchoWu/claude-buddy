"""UI tests for PermissionDialog / PermissionManager (ui/permission_dialog.py)."""
import sys, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

from ui.permission_dialog import PermissionManager

PASS = 0; FAIL = 0; ERRORS = []
def run(name, fn):
    global PASS, FAIL
    try: fn(); PASS += 1; print(f'  OK  {name}')
    except Exception as e: FAIL += 1; ERRORS.append((name, str(e))); print(f'  FAIL {name}: {e}')


def test_always_allowed_add_check():
    pm = PermissionManager()
    pm._always_allowed.add("Bash")
    assert "Bash" in pm._always_allowed

def test_always_denied_add_check():
    pm = PermissionManager()
    pm._always_denied.add("DangerousTool")
    assert "DangerousTool" in pm._always_denied

def test_add_allow_pattern_stores():
    pm = PermissionManager()
    pm.add_allow_pattern("Bash(git *)")
    assert "Bash(git *)" in pm._allow_patterns

def test_matches_allow_pattern_bash_git():
    pm = PermissionManager()
    pm.add_allow_pattern("Bash(git *)")
    assert pm._matches_allow_pattern("Bash", {"command": "git status"}) is True

def test_matches_allow_pattern_non_matching():
    pm = PermissionManager()
    pm.add_allow_pattern("Bash(git *)")
    assert pm._matches_allow_pattern("Bash", {"command": "rm -rf /"}) is False

def test_get_denial_count_initially_zero():
    pm = PermissionManager()
    assert pm.get_denial_count("Bash") == 0

def test_track_denial_increments():
    pm = PermissionManager()
    pm._track_denial("Bash")
    assert pm.get_denial_count("Bash") == 1
    pm._track_denial("Bash")
    assert pm.get_denial_count("Bash") == 2

def test_multiple_patterns():
    pm = PermissionManager()
    pm.add_allow_pattern("Bash(git *)")
    pm.add_allow_pattern("FileRead")
    assert pm._matches_allow_pattern("Bash", {"command": "git log"}) is True
    assert pm._matches_allow_pattern("FileRead", {"file_path": "/tmp/x"}) is True
    assert pm._matches_allow_pattern("FileWrite", {"file_path": "/tmp/x"}) is False


if __name__ == "__main__":
    print("=== test_ui_permission_dialog ===")
    run("always_allowed_add_check", test_always_allowed_add_check)
    run("always_denied_add_check", test_always_denied_add_check)
    run("add_allow_pattern_stores", test_add_allow_pattern_stores)
    run("matches_allow_pattern_bash_git", test_matches_allow_pattern_bash_git)
    run("matches_allow_pattern_non_matching", test_matches_allow_pattern_non_matching)
    run("get_denial_count_initially_zero", test_get_denial_count_initially_zero)
    run("track_denial_increments", test_track_denial_increments)
    run("multiple_patterns", test_multiple_patterns)
    print(f"\n  PASS={PASS}  FAIL={FAIL}")
    if ERRORS:
        print("  Failures:")
        for name, err in ERRORS:
            print(f"    - {name}: {err}")
    sys.exit(0 if FAIL == 0 else 1)
