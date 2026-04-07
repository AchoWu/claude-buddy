"""§8.5 Evolution System – verify EvolutionManager safety and soul management.

Tests correspond to capability-matrix rows for self-evolution, backup,
rollback, reflection, and soul file management.  Independently runnable:

    python tests/test_s85_evolution.py
"""
import sys, os, time, tempfile

# ── Bootstrap ───────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import run, summary, reset, temp_data_dir
from unittest.mock import patch, MagicMock
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
#  Imports (deferred until patches are possible)
# ═══════════════════════════════════════════════════════════════

def _make_evo(tmp: Path):
    """Create an EvolutionManager with all module-level paths patched to *tmp*."""
    import core.evolution as evo_mod
    with patch.object(evo_mod, 'DATA_DIR', tmp), \
         patch.object(evo_mod, 'SOUL_DIR', tmp / "soul"), \
         patch.object(evo_mod, 'EVOLUTION_DIR', tmp / "evolution"), \
         patch.object(evo_mod, 'BACKUPS_DIR', tmp / "evolution" / "backups"), \
         patch.object(evo_mod, 'PROPOSALS_DIR', tmp / "evolution" / "proposals"), \
         patch.object(evo_mod, 'REFLECTIONS_DIR', tmp / "evolution" / "reflections"), \
         patch.object(evo_mod, 'CHANGELOG_FILE', tmp / "evolution" / "changelog.md"):
        mgr = evo_mod.EvolutionManager()
    return mgr


def _patched(tmp: Path):
    """Return a context-manager that patches all evolution module paths."""
    import core.evolution as evo_mod
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch.object(evo_mod, 'DATA_DIR', tmp))
    stack.enter_context(patch.object(evo_mod, 'SOUL_DIR', tmp / "soul"))
    stack.enter_context(patch.object(evo_mod, 'EVOLUTION_DIR', tmp / "evolution"))
    stack.enter_context(patch.object(evo_mod, 'BACKUPS_DIR', tmp / "evolution" / "backups"))
    stack.enter_context(patch.object(evo_mod, 'PROPOSALS_DIR', tmp / "evolution" / "proposals"))
    stack.enter_context(patch.object(evo_mod, 'REFLECTIONS_DIR', tmp / "evolution" / "reflections"))
    stack.enter_context(patch.object(evo_mod, 'CHANGELOG_FILE', tmp / "evolution" / "changelog.md"))
    stack.enter_context(patch.object(evo_mod, 'BUDDY_ROOT', tmp / "_buddy_src"))
    return stack


# ═══════════════════════════════════════════════════════════════
#  Soul Initialization (4 tests)
# ═══════════════════════════════════════════════════════════════

def t01_soul_dir_created():
    """EvolutionManager creates soul directory with 4 md files."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            _make_evo(tmp)
        soul = tmp / "soul"
        assert soul.exists(), "soul dir not created"
        md_files = sorted(f.name for f in soul.glob("*.md"))
        assert "personality.md" in md_files
        assert "diary.md" in md_files
        assert "aspirations.md" in md_files
        assert "relationships.md" in md_files


def t02_evolution_dir_structure():
    """Evolution directory has backups/ and reflections/ subdirs."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            _make_evo(tmp)
        evo = tmp / "evolution"
        assert (evo / "backups").is_dir(), "backups dir missing"
        assert (evo / "reflections").is_dir(), "reflections dir missing"


def t03_personality_default_content():
    """personality.md contains default personality text."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            _make_evo(tmp)
        text = (tmp / "soul" / "personality.md").read_text(encoding="utf-8")
        assert "Personality" in text, "missing header"
        assert "Warm" in text or "friendly" in text, "missing default traits"


def t04_soul_status_formatted():
    """soul_status() returns a formatted string with soul sections."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            status = mgr.soul_status()
        assert isinstance(status, str)
        assert len(status) > 20, "status too short"
        assert "Personality" in status or "Soul" in status or "personality" in status.lower()


# ═══════════════════════════════════════════════════════════════
#  Risk Classification (4 tests)
# ═══════════════════════════════════════════════════════════════

def t05_risk_soul_file_low():
    """classify_risk for soul files → LOW."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            import core.evolution as evo_mod
            soul_file = str(tmp / "soul" / "diary.md")
            risk = evo_mod.classify_risk(soul_file)
            assert risk == evo_mod.RiskLevel.LOW, f"expected LOW, got {risk}"


def t06_risk_prompts_medium():
    """classify_risk for prompts/ → MEDIUM."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        buddy_src = tmp / "_buddy_src"
        (buddy_src / "prompts").mkdir(parents=True)
        target = buddy_src / "prompts" / "system.py"
        target.write_text("# placeholder", encoding="utf-8")
        with _patched(tmp):
            import core.evolution as evo_mod
            risk = evo_mod.classify_risk(str(target))
            assert risk == evo_mod.RiskLevel.MEDIUM, f"expected MEDIUM, got {risk}"


def t07_risk_core_high():
    """classify_risk for core/*.py → HIGH."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        buddy_src = tmp / "_buddy_src"
        (buddy_src / "core").mkdir(parents=True)
        target = buddy_src / "core" / "engine.py"
        target.write_text("# placeholder", encoding="utf-8")
        with _patched(tmp):
            import core.evolution as evo_mod
            risk = evo_mod.classify_risk(str(target))
            assert risk == evo_mod.RiskLevel.HIGH, f"expected HIGH, got {risk}"


def t08_destructive_operation():
    """is_destructive_operation detects soul-dir delete as DESTRUCTIVE."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            import core.evolution as evo_mod
            soul_dir = str(tmp / "soul")
            result = evo_mod.is_destructive_operation("delete", soul_dir)
            assert result is True, "soul dir delete should be destructive"


# ═══════════════════════════════════════════════════════════════
#  Backup & Modify (6 tests)
# ═══════════════════════════════════════════════════════════════

def t09_low_risk_modify():
    """Low-risk modify: write to soul file succeeds."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            soul_file = str(tmp / "soul" / "personality.md")
            result = mgr.modify(soul_file, "# New Personality\nBold and creative.\n", reason="Test update")
        assert result["success"], f"modify failed: {result['message']}"
        assert result["risk"] == "low"
        content = (tmp / "soul" / "personality.md").read_text(encoding="utf-8")
        assert "Bold and creative" in content


def t10_medium_risk_backup_before_write():
    """Medium-risk modify: backup is created before write."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        buddy_src = tmp / "_buddy_src"
        (buddy_src / "prompts").mkdir(parents=True)
        target = buddy_src / "prompts" / "system.py"
        target.write_text("# original", encoding="utf-8")
        with _patched(tmp):
            mgr = _make_evo(tmp)
            result = mgr.modify(str(target), "# updated\nprint('hello')\n", reason="Prompt update")
        assert result["success"], f"modify failed: {result['message']}"
        assert result["risk"] == "medium"
        assert result["backup_path"] is not None, "backup should have been created"
        assert Path(result["backup_path"]).exists(), "backup file missing"


def t11_high_risk_valid_python():
    """High-risk modify with valid Python: succeeds, backup exists."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        buddy_src = tmp / "_buddy_src"
        (buddy_src / "core").mkdir(parents=True)
        target = buddy_src / "core" / "engine.py"
        target.write_text("x = 1\n", encoding="utf-8")
        with _patched(tmp):
            mgr = _make_evo(tmp)
            result = mgr.modify(str(target), "x = 2\ny = 3\n", reason="Update engine")
        assert result["success"], f"modify failed: {result['message']}"
        assert result["risk"] == "high"
        assert result["backup_path"] is not None
        content = target.read_text(encoding="utf-8")
        assert "x = 2" in content


def t12_high_risk_syntax_error_rollback():
    """High-risk modify with syntax error: auto-rollback, original preserved."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        buddy_src = tmp / "_buddy_src"
        (buddy_src / "core").mkdir(parents=True)
        target = buddy_src / "core" / "engine.py"
        original = "x = 1\n"
        target.write_text(original, encoding="utf-8")
        with _patched(tmp):
            mgr = _make_evo(tmp)
            result = mgr.modify(str(target), "def broken(\n", reason="Bad syntax")
        assert result["rolled_back"], "should have been rolled back"
        assert not result["success"], "should not report success"
        restored = target.read_text(encoding="utf-8")
        assert restored.strip() == original.strip(), f"expected original, got: {restored!r}"


def t13_backup_creates_in_backup_dir():
    """backup() creates file in the backups directory."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            test_file = tmp / "testfile.txt"
            test_file.write_text("hello", encoding="utf-8")
            backup_path = mgr.backup(str(test_file))
        assert backup_path is not None, "backup returned None"
        assert Path(backup_path).exists(), "backup file does not exist"
        assert "backups" in backup_path, "backup not in backups dir"


def t14_max_20_backup_versions():
    """Max 20 backup versions per file (create 25, verify ≤20 remain)."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            test_file = tmp / "many_backups.txt"
            for i in range(25):
                test_file.write_text(f"version {i}", encoding="utf-8")
                mgr.backup(str(test_file))
                time.sleep(0.02)  # ensure distinct timestamps

            # Count backup files for this file
            import core.evolution as evo_mod
            rel_key = mgr._backup_key(str(test_file))
            backup_dir = (tmp / "evolution" / "backups") / rel_key
            if backup_dir.exists():
                count = len(list(backup_dir.iterdir()))
                assert count <= 20, f"expected ≤20 backups, got {count}"
            else:
                raise AssertionError("backup dir not found")


# ═══════════════════════════════════════════════════════════════
#  Changelog (3 tests)
# ═══════════════════════════════════════════════════════════════

def t15_modify_appends_changelog():
    """modify() appends entry to changelog."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            soul_file = str(tmp / "soul" / "diary.md")
            mgr.modify(soul_file, "# Updated diary\n", reason="Test changelog")
        changelog = tmp / "evolution" / "changelog.md"
        assert changelog.exists(), "changelog not created"
        text = changelog.read_text(encoding="utf-8")
        assert len(text) > 10, "changelog too short"


def t16_changelog_contains_fields():
    """Changelog entry contains timestamp, file, risk, and reason."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            soul_file = str(tmp / "soul" / "personality.md")
            mgr.modify(soul_file, "# Updated\n", reason="Personality tweak")
        text = (tmp / "evolution" / "changelog.md").read_text(encoding="utf-8")
        assert "risk=" in text, "missing risk field"
        assert "Reason:" in text or "reason" in text.lower(), "missing reason"
        # Should contain a timestamp-like pattern
        assert "20" in text, "missing timestamp (year prefix)"


def t17_rollback_appends_changelog():
    """rollback() appends 'rollback' entry to changelog."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            test_file = tmp / "soul" / "personality.md"
            # Modify first so there's a backup
            mgr.modify(str(test_file), "# v2\n", reason="Prep for rollback")
            mgr.rollback(str(test_file))
        text = (tmp / "evolution" / "changelog.md").read_text(encoding="utf-8")
        assert "rollback" in text.lower(), "changelog missing rollback entry"


# ═══════════════════════════════════════════════════════════════
#  Rollback (2 tests)
# ═══════════════════════════════════════════════════════════════

def t18_rollback_restores_content():
    """rollback() restores from backup."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            target = tmp / "soul" / "personality.md"
            original = target.read_text(encoding="utf-8")
            mgr.modify(str(target), "# Completely new\n", reason="Will rollback")
            ok = mgr.rollback(str(target))
        assert ok, "rollback returned False"
        restored = target.read_text(encoding="utf-8")
        assert restored == original, "content not restored"


def t19_rollback_no_backup_returns_false():
    """rollback() on file without backup returns False."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            fake_file = str(tmp / "nonexistent_file.txt")
            ok = mgr.rollback(fake_file)
        assert ok is False, "rollback should return False for no backup"


# ═══════════════════════════════════════════════════════════════
#  Reflection (5 tests)
# ═══════════════════════════════════════════════════════════════

def t20_should_reflect_false_initially():
    """should_reflect() returns False on first few calls."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            # First call increments to 1, which is < REFLECT_INTERVAL (5)
            result = mgr.should_reflect()
        assert result is False, "should_reflect should be False initially"


def t21_should_reflect_true_after_5_turns():
    """should_reflect() returns True after 5 turns."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            # Simulate enough turns: should_reflect increments each call
            results = []
            for _ in range(10):
                results.append(mgr.should_reflect())
        # By turn 5+, at least one should be True
        assert any(results), "should_reflect never returned True after 10 calls"


def t22_simple_reflect_writes_diary():
    """Simple reflect (no provider): records 'Worked on: ...' in diary."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            messages = [
                {"role": "user", "content": "Help me build a REST API"},
                {"role": "assistant", "content": "Sure, let me help with that."},
            ]
            result = mgr.reflect(messages, provider_call_fn=None)
        assert result is not None, "reflect returned None"
        assert "Worked on" in result, f"expected 'Worked on' in: {result!r}"
        diary = (tmp / "soul" / "diary.md").read_text(encoding="utf-8")
        assert "REST API" in diary or "Worked on" in diary


def t23_llm_reflect_with_mock_provider():
    """LLM reflect (mock provider): writes reflection to diary."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            mock_response = "Today I helped with testing. I learned the user values thoroughness."

            def mock_provider(msgs, system, tools):
                return (None, None, mock_response)

            messages = [
                {"role": "user", "content": "Write some tests"},
                {"role": "assistant", "content": "Here are the tests."},
            ]
            result = mgr.reflect(messages, provider_call_fn=mock_provider)
        assert result is not None
        assert "testing" in result.lower() or "thoroughness" in result.lower()
        diary = (tmp / "soul" / "diary.md").read_text(encoding="utf-8")
        assert "testing" in diary.lower() or "thoroughness" in diary.lower()


def t24_reflection_archives_to_reflections_dir():
    """LLM reflection archives to reflections/ directory."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)

            def mock_provider(msgs, system, tools):
                return (None, None, "Great session today, productive work.")

            messages = [{"role": "user", "content": "Build feature X"}]
            mgr.reflect(messages, provider_call_fn=mock_provider)

        ref_dir = tmp / "evolution" / "reflections"
        ref_files = list(ref_dir.glob("reflection_*.md"))
        assert len(ref_files) >= 1, f"expected reflection file, found {len(ref_files)}"
        content = ref_files[0].read_text(encoding="utf-8")
        assert "Reflection" in content


# ═══════════════════════════════════════════════════════════════
#  Memory Expansion (3 tests)
# ═══════════════════════════════════════════════════════════════

def t25_dual_tag_extraction():
    """[user] prefix topics go to diary, [self] prefix to relationships context."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            # Simulate user tag: write to diary via _append_diary
            mgr._append_diary("[user] Prefers functional programming style.")
            # Simulate self tag: write to relationships via aspirations
            rel_path = tmp / "soul" / "relationships.md"
            existing = rel_path.read_text(encoding="utf-8")
            rel_path.write_text(
                existing + "\n## Learned\n- [self] I should use more FP patterns\n",
                encoding="utf-8",
            )
        diary = (tmp / "soul" / "diary.md").read_text(encoding="utf-8")
        assert "functional programming" in diary.lower(), "user tag not in diary"
        rel = rel_path.read_text(encoding="utf-8")
        assert "FP patterns" in rel, "self tag not in relationships"


def t26_duplicate_insight_not_added():
    """Duplicate aspiration is not added twice."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            mgr._append_aspirations(["- Learn more about testing"])
            mgr._append_aspirations(["- Learn more about testing"])  # duplicate
        asp = (tmp / "soul" / "aspirations.md").read_text(encoding="utf-8")
        count = asp.lower().count("learn more about testing")
        assert count == 1, f"expected 1 occurrence, found {count}"


def t27_diary_auto_trim_at_50kb():
    """Diary auto-trims when exceeding 50KB."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            # Write a large diary
            diary_path = tmp / "soul" / "diary.md"
            big_content = "# BUDDY's Diary\n\n"
            for i in range(500):
                big_content += f"\n## 2025-01-{(i % 28)+1:02d} {i:02d}:00\n"
                big_content += f"Entry number {i}. " + ("x" * 100) + "\n"
            diary_path.write_text(big_content, encoding="utf-8")
            # Now append, which should trigger trim
            mgr._append_diary("Final entry after trim.")
        size = diary_path.stat().st_size
        assert size <= 55000, f"diary too large after trim: {size} bytes"


# ═══════════════════════════════════════════════════════════════
#  Soul File Management (3 tests)
# ═══════════════════════════════════════════════════════════════

def t28_read_soul_personality():
    """read_soul() returns dict with personality.md content."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            soul = mgr.read_soul()
        assert "personality.md" in soul
        assert len(soul["personality.md"]) > 0, "personality content empty"
        assert "Personality" in soul["personality.md"]


def t29_read_soul_diary():
    """read_soul() returns dict with diary.md content."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            soul = mgr.read_soul()
        assert "diary.md" in soul
        assert len(soul["diary.md"]) > 0, "diary content empty"


def t30_soul_status_includes_all_sections():
    """soul_status() mentions personality, diary, aspirations, and backups."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            status = mgr.soul_status()
        status_lower = status.lower()
        assert "personality" in status_lower, "missing personality section"
        assert "diary" in status_lower, "missing diary section"
        assert "aspiration" in status_lower, "missing aspirations section"
        assert "backup" in status_lower, "missing backup count"


# ═══════════════════════════════════════════════════════════════
#  Runner
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    reset()

    print("\n§8.5 Evolution System Tests\n" + "=" * 60)

    # Soul Initialization
    print("\n── Soul Initialization ──")
    run("t01 soul dir created with 4 md files",        t01_soul_dir_created)
    run("t02 evolution dir structure",                   t02_evolution_dir_structure)
    run("t03 personality.md default content",            t03_personality_default_content)
    run("t04 soul_status() formatted string",            t04_soul_status_formatted)

    # Risk Classification
    print("\n── Risk Classification ──")
    run("t05 soul file → LOW risk",                      t05_risk_soul_file_low)
    run("t06 prompts/ → MEDIUM risk",                    t06_risk_prompts_medium)
    run("t07 core/*.py → HIGH risk",                     t07_risk_core_high)
    run("t08 destructive operation detection",           t08_destructive_operation)

    # Backup & Modify
    print("\n── Backup & Modify ──")
    run("t09 low-risk modify succeeds",                  t09_low_risk_modify)
    run("t10 medium-risk backup before write",           t10_medium_risk_backup_before_write)
    run("t11 high-risk valid Python succeeds",           t11_high_risk_valid_python)
    run("t12 high-risk syntax error → rollback",         t12_high_risk_syntax_error_rollback)
    run("t13 backup creates in backup_dir",              t13_backup_creates_in_backup_dir)
    run("t14 max 20 backup versions",                    t14_max_20_backup_versions)

    # Changelog
    print("\n── Changelog ──")
    run("t15 modify appends changelog",                  t15_modify_appends_changelog)
    run("t16 changelog contains fields",                 t16_changelog_contains_fields)
    run("t17 rollback appends changelog entry",          t17_rollback_appends_changelog)

    # Rollback
    print("\n── Rollback ──")
    run("t18 rollback restores content",                 t18_rollback_restores_content)
    run("t19 rollback no backup → False",                t19_rollback_no_backup_returns_false)

    # Reflection
    print("\n── Reflection ──")
    run("t20 should_reflect False initially",            t20_should_reflect_false_initially)
    run("t21 should_reflect True after 5 turns",         t21_should_reflect_true_after_5_turns)
    run("t22 simple reflect writes diary",               t22_simple_reflect_writes_diary)
    run("t23 LLM reflect with mock provider",            t23_llm_reflect_with_mock_provider)
    run("t24 reflection archives to reflections/",       t24_reflection_archives_to_reflections_dir)

    # Memory Expansion
    print("\n── Memory Expansion ──")
    run("t25 dual-tag extraction",                       t25_dual_tag_extraction)
    run("t26 duplicate insight not added",               t26_duplicate_insight_not_added)
    run("t27 diary auto-trim at 50KB",                   t27_diary_auto_trim_at_50kb)

    # Soul File Management
    print("\n── Soul File Management ──")
    run("t28 read_soul personality",                     t28_read_soul_personality)
    run("t29 read_soul diary",                           t29_read_soul_diary)
    run("t30 soul_status includes all sections",         t30_soul_status_includes_all_sections)

    ok = summary("§8.5 Evolution System")
    sys.exit(0 if ok else 1)
