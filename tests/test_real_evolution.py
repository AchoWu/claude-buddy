"""
Real API tests for the evolution system (~10 tests).
Tests soul init, risk classification, modify/rollback, reflection, etc.
All file operations use temp directories to avoid polluting the real soul.
"""

import sys, os, io, time, tempfile
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from tests.real_api_helpers import (
    get_app, skip_no_api, make_real_engine, make_provider,
    run, summary, reset_counters, SignalBox,
)

app = get_app()
skip_no_api()

# ── Setup ─────────────────────────────────────────────────────────
from pathlib import Path
from unittest.mock import patch
import core.evolution as evo_mod


def with_temp_soul(fn):
    """Run fn with isolated soul/evolution directories."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        old_soul = evo_mod.SOUL_DIR
        old_evo = evo_mod.EVOLUTION_DIR
        old_bk = evo_mod.BACKUPS_DIR
        old_pr = evo_mod.PROPOSALS_DIR
        old_rf = evo_mod.REFLECTIONS_DIR
        old_cl = evo_mod.CHANGELOG_FILE
        try:
            evo_mod.SOUL_DIR = td / "soul"
            evo_mod.EVOLUTION_DIR = td / "evolution"
            evo_mod.BACKUPS_DIR = td / "evolution" / "backups"
            evo_mod.PROPOSALS_DIR = td / "evolution" / "proposals"
            evo_mod.REFLECTIONS_DIR = td / "evolution" / "reflections"
            evo_mod.CHANGELOG_FILE = evo_mod.EVOLUTION_DIR / "changelog.md"
            fn(td)
        finally:
            evo_mod.SOUL_DIR = old_soul
            evo_mod.EVOLUTION_DIR = old_evo
            evo_mod.BACKUPS_DIR = old_bk
            evo_mod.PROPOSALS_DIR = old_pr
            evo_mod.REFLECTIONS_DIR = old_rf
            evo_mod.CHANGELOG_FILE = old_cl


# ── Tests ─────────────────────────────────────────────────────────

def test_soul_init():
    """EvolutionManager() creates all four soul files."""
    def _inner(td):
        from core.evolution import EvolutionManager
        evo = EvolutionManager()
        soul = evo_mod.SOUL_DIR
        assert (soul / "personality.md").exists(), "personality.md not created"
        assert (soul / "diary.md").exists(), "diary.md not created"
        assert (soul / "aspirations.md").exists(), "aspirations.md not created"
        assert (soul / "relationships.md").exists(), "relationships.md not created"
    with_temp_soul(_inner)


def test_risk_classify():
    """Risk classification for different file paths."""
    def _inner(td):
        from core.evolution import classify_risk, EvolutionManager
        evo = EvolutionManager()  # ensure dirs exist

        # Soul files → low
        soul_path = str(evo_mod.SOUL_DIR / "diary.md")
        assert classify_risk(soul_path) == "low", f"soul file should be low risk"

        # Core engine code → high
        core_path = str(evo_mod.BUDDY_ROOT / "core" / "engine.py")
        assert classify_risk(core_path) == "high", f"core file should be high risk"

        # Prompts → medium
        prompt_path = str(evo_mod.BUDDY_ROOT / "prompts" / "system.py")
        assert classify_risk(prompt_path) == "medium", f"prompts file should be medium risk"
    with_temp_soul(_inner)


def test_low_risk_modify():
    """Low-risk modification of personality.md succeeds."""
    def _inner(td):
        from core.evolution import EvolutionManager
        evo = EvolutionManager()
        personality_path = str(evo_mod.SOUL_DIR / "personality.md")
        result = evo.modify(personality_path, "New personality content\n", reason="test")
        assert result["success"] is True, f"modify failed: {result['message']}"
        assert result["risk"] == "low", f"expected low risk, got {result['risk']}"
        content = (evo_mod.SOUL_DIR / "personality.md").read_text(encoding="utf-8")
        assert "New personality" in content, "content not written"
    with_temp_soul(_inner)


def test_high_risk_rollback():
    """High-risk .py file with syntax error gets auto-rolled back."""
    def _inner(td):
        from core.evolution import EvolutionManager
        evo = EvolutionManager()
        # Create a valid .py file first so there's something to back up
        dummy_path = str(evo_mod.BUDDY_ROOT / "core" / "test_dummy_evo.py")
        try:
            Path(dummy_path).parent.mkdir(parents=True, exist_ok=True)
            Path(dummy_path).write_text("# valid\ndef f(): pass\n", encoding="utf-8")
            # Now modify with syntax error
            result = evo.modify(dummy_path, "def f(\n", reason="test bad syntax")
            assert result["rolled_back"] is True or result["success"] is False, \
                f"Expected rollback or failure, got: {result}"
        finally:
            # Clean up
            if Path(dummy_path).exists():
                Path(dummy_path).unlink()
    with_temp_soul(_inner)


def test_changelog():
    """After a modify, changelog.md has new content."""
    def _inner(td):
        from core.evolution import EvolutionManager
        evo = EvolutionManager()
        personality_path = str(evo_mod.SOUL_DIR / "personality.md")
        evo.modify(personality_path, "changelog test content\n", reason="changelog test")
        changelog = evo_mod.CHANGELOG_FILE
        assert changelog.exists(), "changelog.md not created"
        content = changelog.read_text(encoding="utf-8")
        assert "changelog test" in content, f"reason not in changelog: {content[:300]}"
    with_temp_soul(_inner)


def test_reflection_trigger():
    """should_reflect() returns False before threshold, True at threshold."""
    def _inner(td):
        from core.evolution import EvolutionManager
        evo = EvolutionManager()
        evo._turn_count = 3
        evo._last_reflect_time = 0
        # At turn_count=3, calling should_reflect increments to 4 which is < 5
        result4 = evo.should_reflect()
        assert result4 is False, f"Expected False at turn 4, got {result4}"
        # Now turn_count is 4, calling again increments to 5 which is >= 5
        result5 = evo.should_reflect()
        assert result5 is True, f"Expected True at turn 5, got {result5}"
    with_temp_soul(_inner)


def test_llm_reflection():
    """Reflection with real LLM API writes to diary.md."""
    def _inner(td):
        from core.evolution import EvolutionManager
        evo = EvolutionManager()

        initial_diary = (evo_mod.SOUL_DIR / "diary.md").read_text(encoding="utf-8")

        provider = make_provider()
        def provider_call_fn(messages, system, tools):
            return provider.call_sync(messages=messages, system=system, tools=tools)

        test_messages = [
            {"role": "user", "content": "Help me fix a bug in my login page"},
            {"role": "assistant", "content": "I'll help! Let me look at the code."},
            {"role": "user", "content": "Thanks, the error is on line 42"},
            {"role": "assistant", "content": "Found it - you have a typo in the variable name."},
            {"role": "user", "content": "Perfect, that fixed it!"},
        ]
        result = evo.reflect(test_messages, provider_call_fn)
        assert result is not None, "reflect returned None"
        updated_diary = (evo_mod.SOUL_DIR / "diary.md").read_text(encoding="utf-8")
        assert updated_diary != initial_diary, "diary.md was not updated after LLM reflection"
    with_temp_soul(_inner)


def test_simple_reflection():
    """Reflection without LLM writes a simple entry to diary.md."""
    def _inner(td):
        from core.evolution import EvolutionManager
        evo = EvolutionManager()

        initial_diary = (evo_mod.SOUL_DIR / "diary.md").read_text(encoding="utf-8")

        test_messages = [
            {"role": "user", "content": "Help me fix a bug in my login page"},
            {"role": "assistant", "content": "I'll help! Let me look at the code."},
        ]
        result = evo.reflect(test_messages, None)
        assert result is not None, "simple reflect returned None"
        assert "Worked on" in result, f"Expected 'Worked on' in result: {result[:200]}"
        updated_diary = (evo_mod.SOUL_DIR / "diary.md").read_text(encoding="utf-8")
        assert updated_diary != initial_diary, "diary.md was not updated after simple reflection"
    with_temp_soul(_inner)


def test_backup_limit():
    """Modifying the same file 25 times keeps only 20 backups."""
    def _inner(td):
        from core.evolution import EvolutionManager
        evo = EvolutionManager()
        personality_path = str(evo_mod.SOUL_DIR / "personality.md")

        for i in range(25):
            evo.modify(personality_path, f"Version {i}\n", reason=f"iteration {i}")

        # Find backup dir for this file
        rel_key = evo._backup_key(personality_path)
        backup_dir = evo_mod.BACKUPS_DIR / rel_key
        assert backup_dir.exists(), "backup dir not created"
        backups = list(backup_dir.iterdir())
        assert len(backups) <= 20, f"Expected <= 20 backups, got {len(backups)}"
    with_temp_soul(_inner)


def test_soul_status():
    """soul_status() returns a non-empty string with personality info."""
    def _inner(td):
        from core.evolution import EvolutionManager
        evo = EvolutionManager()
        status = evo.soul_status()
        assert isinstance(status, str), "soul_status did not return a string"
        assert len(status) > 0, "soul_status returned empty string"
        assert "Personality" in status or "personality" in status or "Soul" in status, \
            f"soul_status missing personality info: {status[:300]}"
    with_temp_soul(_inner)


# ── Run ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    reset_counters()
    print("\n" + "=" * 60)
    print("  TEST SUITE: Real Evolution")
    print("=" * 60 + "\n")

    run("EVO.1  Soul init",           test_soul_init)
    run("EVO.2  Risk classify",       test_risk_classify)
    run("EVO.3  Low-risk modify",     test_low_risk_modify)
    run("EVO.4  High-risk rollback",  test_high_risk_rollback)
    run("EVO.5  Changelog",           test_changelog)
    run("EVO.6  Reflection trigger",  test_reflection_trigger)
    run("EVO.7  LLM reflection",      test_llm_reflection)
    run("EVO.8  Simple reflection",   test_simple_reflection)
    run("EVO.9  Backup limit",        test_backup_limit)
    run("EVO.10 Soul status",         test_soul_status)

    ok = summary("Real Evolution")
    sys.exit(0 if ok else 1)
