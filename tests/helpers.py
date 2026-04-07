"""Shared test harness for BUDDY verification suite."""
import sys, os, io, tempfile
from pathlib import Path
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

# Ensure UTF-8 stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add BUDDY to path
BUDDY_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BUDDY_DIR)

# ── Test framework ──────────────────────────────────────────────
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

def summary(suite_name):
    total = PASS + FAIL
    print(f'\n{"="*60}')
    if FAIL == 0:
        print(f'  {suite_name}: {total}/{total} ALL TESTS PASSED')
    else:
        print(f'  {suite_name}: {PASS}/{total} PASSED, {FAIL} FAILED')
        for n, e in ERRORS:
            print(f'    X {n}: {e}')
    print(f'{"="*60}')
    return FAIL == 0

def reset():
    global PASS, FAIL, ERRORS
    PASS = 0
    FAIL = 0
    ERRORS = []

# ── QApp singleton ──────────────────────────────────────────────
_qapp = None
def get_qapp():
    global _qapp
    if _qapp is None:
        # Set offscreen platform if no display
        if 'QT_QPA_PLATFORM' not in os.environ:
            try:
                from PyQt6.QtWidgets import QApplication
                if QApplication.instance() is None:
                    # Try creating to see if display is available
                    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
            except Exception:
                os.environ['QT_QPA_PLATFORM'] = 'offscreen'
        from PyQt6.QtWidgets import QApplication
        _qapp = QApplication.instance() or QApplication(sys.argv)
    return _qapp

# ── Signal capture ──────────────────────────────────────────────
def capture_signal(signal):
    captured = []
    signal.connect(lambda *args: captured.append(args))
    return captured

# ── Temp data dir ───────────────────────────────────────────────
@contextmanager
def temp_data_dir():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d)
        (p / "soul").mkdir(exist_ok=True)
        (p / "evolution").mkdir(exist_ok=True)
        (p / "evolution" / "backups").mkdir(exist_ok=True)
        (p / "evolution" / "reflections").mkdir(exist_ok=True)
        (p / "conversations").mkdir(exist_ok=True)
        (p / "plugins").mkdir(exist_ok=True)
        patches = [
            patch('config.DATA_DIR', p),
            patch('config.CONVERSATIONS_DIR', p / "conversations"),
        ]
        # Try to patch evolution paths too
        try:
            patches.append(patch('core.evolution.DATA_DIR', p))
            patches.append(patch('core.evolution.SOUL_DIR', p / "soul"))
            patches.append(patch('core.evolution.EVOLUTION_DIR', p / "evolution"))
        except Exception:
            pass
        for pa in patches:
            pa.start()
        try:
            yield p
        finally:
            for pa in patches:
                try:
                    pa.stop()
                except Exception:
                    pass
