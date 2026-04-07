"""
Sprint 8 - File Read Tracking Tests
Tests for core/conversation.py (FileReadState)
"""

import sys
import os
import io
import time
import tempfile

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
# FileReadState Tests
# ---------------------------------------------------------------------------

def test_record_then_has_read():
    """record_read then has_read should return True."""
    from core.conversation import FileReadState
    frs = FileReadState()
    frs.record_read("/project/main.py")
    assert frs.has_read("/project/main.py") is True, \
        "has_read should be True after record_read"


def test_has_read_unread_file():
    """has_read on a file never recorded should return False."""
    from core.conversation import FileReadState
    frs = FileReadState()
    assert frs.has_read("/project/unknown.py") is False, \
        "has_read should be False for unread file"


def test_is_stale_after_modification():
    """Read a real file, modify it externally, is_stale should return True."""
    from core.conversation import FileReadState
    frs = FileReadState()

    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("original content")
        tmp_path = f.name

    try:
        # Record the read with the current mtime
        mtime = os.path.getmtime(tmp_path)
        frs.record_read(tmp_path, mtime=mtime)

        # File should NOT be stale yet
        assert frs.is_stale(tmp_path) is False, \
            "File should not be stale immediately after reading"

        # Simulate external modification by bumping mtime
        time.sleep(0.05)
        with open(tmp_path, 'w') as f:
            f.write("modified content")

        # Now file should be stale
        assert frs.is_stale(tmp_path) is True, \
            "File should be stale after external modification"
    finally:
        os.unlink(tmp_path)


def test_lru_eviction():
    """With max_entries=100, recording 101 files should evict the first."""
    from core.conversation import FileReadState
    frs = FileReadState(max_entries=100)

    # Record 101 file reads
    for i in range(101):
        frs.record_read(f"/project/file_{i}.py")

    # The first file (file_0) should have been evicted
    assert frs.has_read("/project/file_0.py") is False, \
        "file_0 should be evicted after 101 entries (max=100)"
    # The last file should still be present
    assert frs.has_read("/project/file_100.py") is True, \
        "file_100 should still be tracked"


def test_clear_removes_all():
    """clear() should remove all tracked entries."""
    from core.conversation import FileReadState
    frs = FileReadState()
    frs.record_read("/a.py")
    frs.record_read("/b.py")
    frs.record_read("/c.py")
    frs.clear()
    assert frs.has_read("/a.py") is False, "has_read should be False after clear"
    assert frs.has_read("/b.py") is False, "has_read should be False after clear"
    assert frs.has_read("/c.py") is False, "has_read should be False after clear"


def test_read_files_property():
    """read_files should return list of all recorded file paths (resolved)."""
    from core.conversation import FileReadState
    from pathlib import Path
    frs = FileReadState()
    # Use absolute paths since FileReadState resolves paths
    paths = [str(Path("/x.py").resolve()), str(Path("/y.py").resolve()), str(Path("/z.py").resolve())]
    for p in paths:
        frs.record_read(p)
    files = frs.read_files
    assert isinstance(files, list), f"read_files should return a list, got {type(files)}"
    assert len(files) == 3, f"Expected 3 files, got {len(files)}: {files}"
    for p in paths:
        assert p in files, f"{p} should be in read_files, got: {files}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    print("=" * 60)
    print("Sprint 8 - File Read Tracking Tests")
    print("=" * 60)

    tests = [
        ("FileReadState: record then has_read", test_record_then_has_read),
        ("FileReadState: unread file -> False", test_has_read_unread_file),
        ("FileReadState: stale after modification", test_is_stale_after_modification),
        ("FileReadState: LRU eviction at max_entries", test_lru_eviction),
        ("FileReadState: clear removes all", test_clear_removes_all),
        ("FileReadState: read_files property", test_read_files_property),
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
