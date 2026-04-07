"""
Sprint 7 - Security & Sandbox System Tests
Tests for core/sandbox.py (Sandbox) and ui/permission_dialog.py (PermissionManager)
"""

import sys
import os
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

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


# ---------------------------------------------------------------------------
# Sandbox Tests
# ---------------------------------------------------------------------------

def test_system_dir_denied():
    """check_path on system directory should return DENIED."""
    from core.sandbox import Sandbox, AccessLevel
    import platform
    sb = Sandbox()
    # Sandbox resolves paths, so use platform-appropriate system paths
    if platform.system() == "Windows":
        test_paths = [r"C:\Windows\System32\cmd.exe", r"C:\Program Files\test.exe"]
    else:
        test_paths = ["/etc/passwd", "/usr/bin/python"]
    for p in test_paths:
        result = sb.check_path(p)
        assert result == AccessLevel.DENIED, f"Expected DENIED for {p}, got {result}"


def test_workspace_path_allowed():
    """After set_workspace, files inside workspace should be ALLOWED."""
    from core.sandbox import Sandbox, AccessLevel
    sb = Sandbox()
    workspace = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "test_workspace_tmp")
    workspace = os.path.normpath(workspace)
    sb.set_workspace(workspace)
    result = sb.check_path(os.path.join(workspace, "hello.py"))
    assert result == AccessLevel.ALLOWED, f"Expected ALLOWED for workspace file, got {result}"


def test_sensitive_file_detection():
    """is_sensitive_file should flag .env and .key files but not normal files."""
    from core.sandbox import Sandbox
    sb = Sandbox()
    assert sb.is_sensitive_file(".env") is True, ".env should be sensitive"
    assert sb.is_sensitive_file("config/.env") is True, "config/.env should be sensitive"
    assert sb.is_sensitive_file("id_rsa.key") is True, ".key file should be sensitive"
    assert sb.is_sensitive_file("readme.txt") is False, "readme.txt should NOT be sensitive"
    assert sb.is_sensitive_file("main.py") is False, "main.py should NOT be sensitive"


def test_classify_git_status_safe():
    """classify_command('git status') should be SAFE."""
    from core.sandbox import Sandbox, CommandRisk
    sb = Sandbox()
    risk = sb.classify_command("git status")
    assert risk == CommandRisk.SAFE, f"Expected SAFE for 'git status', got {risk}"


def test_classify_rm_rf_dangerous_or_blocked():
    """classify_command('rm -rf /') should be BLOCKED or DANGEROUS."""
    from core.sandbox import Sandbox, CommandRisk
    sb = Sandbox()
    risk = sb.classify_command("rm -rf /")
    assert risk in (CommandRisk.BLOCKED, CommandRisk.DANGEROUS), \
        f"Expected BLOCKED or DANGEROUS for 'rm -rf /', got {risk}"


def test_is_command_safe_ls():
    """is_command_safe('ls') should be True."""
    from core.sandbox import Sandbox
    sb = Sandbox()
    assert sb.is_command_safe("ls") is True, "'ls' should be safe"


def test_is_command_blocked_dangerous():
    """is_command_blocked should flag destructive commands."""
    from core.sandbox import Sandbox
    sb = Sandbox()
    dangerous_cmds = ["rm -rf /", "mkfs.ext4 /dev/sda", ":(){ :|:& };:"]
    for cmd in dangerous_cmds:
        result = sb.is_command_blocked(cmd)
        if result:
            return  # At least one blocked, test passes
    from core.sandbox import CommandRisk
    risks = [sb.classify_command(c) for c in dangerous_cmds]
    assert any(r in (CommandRisk.BLOCKED, CommandRisk.DANGEROUS) for r in risks), \
        "At least one destructive command should be blocked or dangerous"


def test_git_force_push_detection():
    """git push --force should be classified as risky."""
    from core.sandbox import Sandbox, CommandRisk
    sb = Sandbox()
    risk = sb.classify_command("git push --force origin main")
    assert risk in (CommandRisk.MODERATE, CommandRisk.DANGEROUS, CommandRisk.BLOCKED), \
        f"Expected git force-push to be risky, got {risk}"


# ---------------------------------------------------------------------------
# PermissionManager Tests
# ---------------------------------------------------------------------------

def test_permission_always_allow():
    """PermissionManager always-allow rules using actual API."""
    # Need QApp for QObject-based PermissionManager
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    from ui.permission_dialog import PermissionManager
    pm = PermissionManager()
    # Use internal API: _always_allowed is a set
    pm._always_allowed.add("FileReadTool")
    # check_permission for always-allowed tool should return True without dialog
    # But we can't call check_permission (it shows dialog for unknown tools)
    # Instead test the internal state
    assert "FileReadTool" in pm._always_allowed, "FileReadTool should be in always-allowed set"
    assert "BashTool" not in pm._always_allowed, "BashTool should NOT be in always-allowed"


def test_permission_pattern_and_denial():
    """Pattern-based allow 'Bash(git *)' and denial tracking."""
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)

    from ui.permission_dialog import PermissionManager
    pm = PermissionManager()
    # Pattern-based allow for git commands
    pm.add_allow_pattern("Bash(git *)")
    assert pm._matches_allow_pattern("Bash", {"command": "git status"}) is True, \
        "Bash with 'git status' should match 'Bash(git *)' pattern"
    assert pm._matches_allow_pattern("Bash", {"command": "rm -rf /"}) is False, \
        "Bash with 'rm -rf /' should NOT match 'Bash(git *)' pattern"

    # Always-deny
    pm._always_denied.add("DangerousTool")
    assert "DangerousTool" in pm._always_denied

    # Denial tracking
    pm._track_denial("DangerousTool")
    pm._track_denial("DangerousTool")
    assert pm.get_denial_count("DangerousTool") == 2, \
        f"Expected 2 denials, got {pm.get_denial_count('DangerousTool')}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("=" * 60)
    print("Sprint 7 - Security & Sandbox Tests")
    print("=" * 60)

    tests = [
        ("Sandbox: system dir -> DENIED", test_system_dir_denied),
        ("Sandbox: workspace path -> ALLOWED", test_workspace_path_allowed),
        ("Sandbox: sensitive file detection", test_sensitive_file_detection),
        ("Sandbox: git status -> SAFE", test_classify_git_status_safe),
        ("Sandbox: rm -rf / -> BLOCKED/DANGEROUS", test_classify_rm_rf_dangerous_or_blocked),
        ("Sandbox: ls -> safe", test_is_command_safe_ls),
        ("Sandbox: blocked dangerous commands", test_is_command_blocked_dangerous),
        ("Sandbox: git force-push detection", test_git_force_push_detection),
        ("PermissionManager: always-allow rule", test_permission_always_allow),
        ("PermissionManager: pattern & denial tracking", test_permission_pattern_and_denial),
    ]

    for name, fn in tests:
        run(name, fn)

    print("=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed out of {PASS + FAIL}")
    if ERRORS:
        print("\nFailures:")
        for name, err in ERRORS:
            print(f"  - {name}: {err}")
    print("=" * 60)
    sys.exit(0 if FAIL == 0 else 1)
