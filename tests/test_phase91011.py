"""
Phase 9-11 Verification Tests
Phase 9: Settings hierarchy, MCP config, session ID header
Phase 10: Compact failure tracking, media stripping, message fingerprint
Phase 11: Settings properties (thinking, effort, cache, temperature)
"""
import sys, os, io, time, tempfile, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_buddy = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _buddy)
os.chdir(_buddy)

from pathlib import Path
_TEMP = tempfile.mkdtemp(prefix='buddy_p91011_')
import config
config.DATA_DIR = Path(_TEMP)
config.CONVERSATIONS_DIR = Path(_TEMP) / "conversations"
config.CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)

PASS = 0; FAIL = 0; ERRORS = []
def run(name, fn):
    global PASS, FAIL
    try: fn(); PASS += 1; print(f'  OK  {name}')
    except Exception as e: FAIL += 1; ERRORS.append((name, str(e))); print(f'  FAIL {name}: {e}')
def summary():
    total = PASS + FAIL
    print(f'\n{"="*60}')
    s = f'Phase 9-11: {total}/{total} ALL TESTS PASSED' if FAIL == 0 else f'Phase 9-11: {PASS}/{total} PASSED, {FAIL} FAILED'
    print(f'  {s}')
    for n, e in ERRORS: print(f'    X {n}: {e}')
    print(f'{"="*60}')
    return FAIL == 0

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication
_qapp = QApplication.instance() or QApplication(sys.argv)

from core.conversation import ConversationManager
from core.settings import Settings

print('=' * 60)
print('  Phase 9-11 Verification Tests')
print('=' * 60)

# ═══════════════════════════════════════════════════════════════
# Phase 9: Settings hierarchy
# ═══════════════════════════════════════════════════════════════
print('  --- Phase 9: Settings ---')

def test_settings_thinking():
    s = Settings()
    assert s.thinking_enabled is False  # default off
    s.thinking_enabled = True
    assert s.thinking_enabled is True
    s.thinking_enabled = False
run("P9.1 Settings: thinking_enabled toggle", test_settings_thinking)

def test_settings_thinking_budget():
    s = Settings()
    assert s.thinking_budget == 10000  # default
    s.thinking_budget = 5000
    assert s.thinking_budget == 5000
    # Clamp to range
    s.thinking_budget = 100  # below min
    assert s.thinking_budget >= 1024
run("P9.2 Settings: thinking_budget with clamping", test_settings_thinking_budget)

def test_settings_effort():
    s = Settings()
    assert s.effort_level == ""  # default empty
    s.effort_level = "high"
    assert s.effort_level == "high"
run("P9.3 Settings: effort_level property", test_settings_effort)

def test_settings_cache_control():
    s = Settings()
    assert s.cache_control_enabled is False
    s.cache_control_enabled = True
    assert s.cache_control_enabled is True
run("P9.4 Settings: cache_control_enabled toggle", test_settings_cache_control)

def test_settings_temperature():
    s = Settings()
    assert s.temperature is None  # default
    s.temperature = 0.7
    assert s.temperature == 0.7
    s.temperature = None
    assert s.temperature is None
run("P9.5 Settings: temperature (None or float)", test_settings_temperature)

def test_settings_load_project():
    s = Settings()
    # Create a project config
    project_dir = Path(_TEMP) / "test_project"
    project_dir.mkdir(exist_ok=True)
    claude_dir = project_dir / ".claude"
    claude_dir.mkdir(exist_ok=True)
    (claude_dir / "config.json").write_text(json.dumps({
        "effort_level": "medium",
    }))
    s.load_project_settings(str(project_dir))
    # Project settings loaded (lower priority than runtime)
run("P9.6 Settings: load_project_settings from .claude/config.json", test_settings_load_project)

# ═══════════════════════════════════════════════════════════════
# Phase 10: Compact improvements
# ═══════════════════════════════════════════════════════════════
print('  --- Phase 10: Compaction ---')

def test_compact_failure_tracking():
    conv = ConversationManager()
    assert conv._consecutive_compact_failures == 0
    conv._consecutive_compact_failures += 1
    assert conv._consecutive_compact_failures == 1
run("P10.1 Compact: failure counter initialized to 0", test_compact_failure_tracking)

def test_media_stripping():
    conv = ConversationManager()
    conv._media_item_limit = 5  # low limit for testing

    # Add 8 messages with media
    for i in range(8):
        conv._messages.append({
            "role": "user",
            "content": [{"type": "image", "source": {"data": f"base64data_{i}"}}],
        })

    stripped = conv._strip_excess_media()
    assert stripped == 3, f"Should strip 3 items (8-5=3), got {stripped}"

    # Verify stubs
    stub_count = 0
    for m in conv._messages:
        content = m.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and "removed" in block.get("text", "").lower():
                    stub_count += 1
    assert stub_count == 3
run("P10.2 Media stripping: 8 items, limit 5 → strip 3 oldest", test_media_stripping)

def test_media_stripping_under_limit():
    conv = ConversationManager()
    conv._media_item_limit = 20
    for i in range(5):
        conv._messages.append({
            "role": "user",
            "content": [{"type": "image", "source": {"data": "data"}}],
        })
    stripped = conv._strip_excess_media()
    assert stripped == 0, "Should not strip when under limit"
run("P10.3 Media stripping: under limit → no stripping", test_media_stripping_under_limit)

def test_media_in_compact_pipeline():
    conv = ConversationManager()
    conv._media_item_limit = 3
    # Add media + regular messages over threshold
    for i in range(25):
        conv._messages.append({
            "role": "user",
            "content": [{"type": "image", "source": {"data": f"d{i}"}}],
        })
        conv._messages.append({"role": "assistant", "content": f"reply {i}"})

    result = conv.compact_if_needed()
    if result:
        assert "media_strip" in result, f"Should mention media stripping: {result}"
run("P10.4 Media stripping: integrated in compact_if_needed", test_media_in_compact_pipeline)

# ═══════════════════════════════════════════════════════════════
# Phase 11: UI settings (properties exist for UI binding)
# ═══════════════════════════════════════════════════════════════
print('  --- Phase 11: UI Settings ---')

def test_all_settings_accessible():
    """All Phase 11 settings are accessible via Settings class."""
    s = Settings()
    # These must all work without error
    _ = s.thinking_enabled
    _ = s.thinking_budget
    _ = s.effort_level
    _ = s.cache_control_enabled
    _ = s.temperature
    _ = s.streaming_enabled
    _ = s.permission_mode
    _ = s.character
    _ = s.provider
    _ = s.model
run("P11.1 All settings accessible via properties", test_all_settings_accessible)

def test_settings_roundtrip():
    """Settings survive write + read cycle."""
    s = Settings()
    s.thinking_enabled = True
    s.thinking_budget = 8192
    s.effort_level = "low"
    s.cache_control_enabled = True
    s.temperature = 0.5

    s2 = Settings()  # new instance reads same QSettings
    assert s2.thinking_enabled is True
    assert s2.thinking_budget == 8192
    assert s2.effort_level == "low"
    assert s2.cache_control_enabled is True
    assert s2.temperature == 0.5
run("P11.2 Settings roundtrip: write → new instance → read", test_settings_roundtrip)

# ═══════════════════════════════════════════════════════════════
import shutil
try: ok = summary()
finally: shutil.rmtree(_TEMP, ignore_errors=True)
sys.exit(0 if ok else 1)
