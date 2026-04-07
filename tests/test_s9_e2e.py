"""§9 End-to-End Scenarios – integration tests across subsystems.

Tests 8 end-to-end scenarios from the capability matrix.
Independently runnable:

    python tests/test_s9_e2e.py
"""
import sys, os, time, tempfile

# ── Bootstrap ───────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from helpers import run, summary, reset
from unittest.mock import patch, MagicMock
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
#  Shared helpers
# ═══════════════════════════════════════════════════════════════

def _patched(tmp: Path):
    """Patch all evolution module-level paths to tmp."""
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


def _make_evo(tmp: Path):
    """Create EvolutionManager with patched paths."""
    import core.evolution as evo_mod
    with _patched(tmp):
        mgr = evo_mod.EvolutionManager()
    return mgr


# ═══════════════════════════════════════════════════════════════
#  E2E.1  Personality Adaptation
# ═══════════════════════════════════════════════════════════════

def e2e_01_personality_adaptation():
    """Modify personality.md, verify changelog + content change."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            personality_path = str(tmp / "soul" / "personality.md")

            # Read original
            original = (tmp / "soul" / "personality.md").read_text(encoding="utf-8")
            assert "Personality" in original

            # Modify personality
            new_content = (
                "# BUDDY's Personality\n\n"
                "## Communication Style\n"
                "- Direct and concise\n"
                "- Uses technical language confidently\n"
                "- Matches partner's energy\n"
            )
            result = mgr.modify(personality_path, new_content, reason="Adapted to user preference")

        assert result["success"], f"modify failed: {result['message']}"

        # Verify content changed
        updated = (tmp / "soul" / "personality.md").read_text(encoding="utf-8")
        assert "Direct and concise" in updated
        assert "technical language" in updated

        # Verify changelog was updated
        changelog = (tmp / "evolution" / "changelog.md").read_text(encoding="utf-8")
        assert "Adapted to user preference" in changelog or "personality" in changelog.lower()


# ═══════════════════════════════════════════════════════════════
#  E2E.2  Prompt Self-Optimization
# ═══════════════════════════════════════════════════════════════

def e2e_02_prompt_self_optimization():
    """Create prompts/system.py, modify via evolution, verify backup + changelog."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        buddy_src = tmp / "_buddy_src"
        (buddy_src / "prompts").mkdir(parents=True)
        target = buddy_src / "prompts" / "system.py"
        target.write_text(
            "SYSTEM_PROMPT = 'You are a helpful assistant.'\n",
            encoding="utf-8",
        )

        with _patched(tmp):
            mgr = _make_evo(tmp)
            result = mgr.modify(
                str(target),
                "SYSTEM_PROMPT = 'You are BUDDY, a creative coding partner.'\n",
                reason="Optimize system prompt for personality",
            )

        assert result["success"], f"modify failed: {result['message']}"
        assert result["risk"] == "medium"
        assert result["backup_path"] is not None
        assert Path(result["backup_path"]).exists(), "backup file missing"

        # Verify changelog
        changelog = (tmp / "evolution" / "changelog.md").read_text(encoding="utf-8")
        assert "Optimize system prompt" in changelog or "prompt" in changelog.lower()


# ═══════════════════════════════════════════════════════════════
#  E2E.3  Tool Self-Creation
# ═══════════════════════════════════════════════════════════════

def e2e_03_tool_self_creation():
    """Create a plugin file in plugins/ directory."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        plugins_dir = tmp / "plugins"
        plugins_dir.mkdir(parents=True)

        plugin_content = (
            "# Auto-generated plugin\n"
            "def greet(name: str) -> str:\n"
            "    return f'Hello, {name}!'\n\n"
            "PLUGIN_INFO = {\n"
            "    'name': 'greeter',\n"
            "    'description': 'A simple greeting plugin',\n"
            "    'functions': [greet],\n"
            "}\n"
        )
        plugin_path = plugins_dir / "greeter.py"
        plugin_path.write_text(plugin_content, encoding="utf-8")

        # Verify file exists and is valid Python
        assert plugin_path.exists(), "plugin file not created"
        source = plugin_path.read_text(encoding="utf-8")
        compile(source, str(plugin_path), "exec")  # syntax check
        assert "greet" in source
        assert "PLUGIN_INFO" in source


# ═══════════════════════════════════════════════════════════════
#  E2E.4  Modify Failure Rollback
# ═══════════════════════════════════════════════════════════════

def e2e_04_modify_failure_rollback():
    """High-risk .py modify with syntax error → auto-rollback + changelog entry."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        buddy_src = tmp / "_buddy_src"
        (buddy_src / "core").mkdir(parents=True)
        target = buddy_src / "core" / "engine.py"
        original_content = "class Engine:\n    pass\n"
        target.write_text(original_content, encoding="utf-8")

        with _patched(tmp):
            mgr = _make_evo(tmp)
            result = mgr.modify(
                str(target),
                "class Engine:\n    def broken(self\n",  # syntax error
                reason="Attempted engine update",
            )

        # Should have rolled back
        assert result["rolled_back"], "should have rolled back"
        assert not result["success"], "should not report success"

        # Original content should be restored
        restored = target.read_text(encoding="utf-8")
        assert restored.strip() == original_content.strip(), (
            f"content not restored: {restored!r}"
        )

        # Changelog should mention rollback
        changelog = (tmp / "evolution" / "changelog.md").read_text(encoding="utf-8")
        assert "ROLLED BACK" in changelog, "changelog missing ROLLED BACK"


# ═══════════════════════════════════════════════════════════════
#  E2E.5  Reflection Chain
# ═══════════════════════════════════════════════════════════════

def e2e_05_reflection_chain():
    """Simulate 5 turns, reflect, verify diary has new entry."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)

            # Simulate turns until should_reflect is True
            for _ in range(10):
                if mgr.should_reflect():
                    break

            messages = [
                {"role": "user", "content": "Help me refactor the auth module"},
                {"role": "assistant", "content": "I'll restructure the auth flow."},
                {"role": "user", "content": "Add rate limiting too"},
            ]
            result = mgr.reflect(messages, provider_call_fn=None)

        assert result is not None, "reflect returned None"
        assert "Worked on" in result

        diary = (tmp / "soul" / "diary.md").read_text(encoding="utf-8")
        assert "refactor" in diary.lower() or "auth" in diary.lower() or "Worked on" in diary


# ═══════════════════════════════════════════════════════════════
#  E2E.6  Bidirectional Memory
# ═══════════════════════════════════════════════════════════════

def e2e_06_bidirectional_memory():
    """Test memory extraction with [user] and [self] tags into soul files."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)

            # Simulate [user] insight → diary
            mgr._append_diary("[user] Partner prefers TDD workflow.")

            # Simulate [self] insight → aspirations
            mgr._append_aspirations(["- [self] Get better at writing test fixtures"])

        # Verify diary has user insight
        diary = (tmp / "soul" / "diary.md").read_text(encoding="utf-8")
        assert "TDD workflow" in diary, "user insight not in diary"

        # Verify aspirations has self insight
        asp = (tmp / "soul" / "aspirations.md").read_text(encoding="utf-8")
        assert "test fixtures" in asp, "self insight not in aspirations"


# ═══════════════════════════════════════════════════════════════
#  E2E.7  Manual Rollback
# ═══════════════════════════════════════════════════════════════

def e2e_07_manual_rollback():
    """Modify a file, then manually rollback, verify content restored."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)
            target = tmp / "soul" / "personality.md"
            original = target.read_text(encoding="utf-8")

            # Modify
            mgr.modify(str(target), "# Completely changed\nNew personality.\n", reason="Test")

            # Verify it changed
            changed = target.read_text(encoding="utf-8")
            assert "Completely changed" in changed

            # Rollback
            ok = mgr.rollback(str(target))

        assert ok, "rollback failed"
        restored = target.read_text(encoding="utf-8")
        assert restored == original, f"content not fully restored"


# ═══════════════════════════════════════════════════════════════
#  E2E.8  Soul View Chain
# ═══════════════════════════════════════════════════════════════

def e2e_08_soul_view_chain():
    """soul_status(), read_soul('diary'), read_soul('personality') all work."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        with _patched(tmp):
            mgr = _make_evo(tmp)

            # soul_status returns non-empty
            status = mgr.soul_status()
            assert len(status) > 20, f"status too short: {status!r}"
            assert "Soul" in status or "soul" in status.lower() or "Personality" in status

            # read_soul returns all soul files
            soul = mgr.read_soul()
            assert "diary.md" in soul
            assert len(soul["diary.md"]) > 0, "diary is empty"

            assert "personality.md" in soul
            assert len(soul["personality.md"]) > 0, "personality is empty"

            # All four soul files present
            assert "aspirations.md" in soul
            assert "relationships.md" in soul


# ═══════════════════════════════════════════════════════════════
#  Runner
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    reset()

    print("\n§9 End-to-End Scenario Tests\n" + "=" * 60)

    run("E2E.1 personality adaptation",         e2e_01_personality_adaptation)
    run("E2E.2 prompt self-optimization",       e2e_02_prompt_self_optimization)
    run("E2E.3 tool self-creation",             e2e_03_tool_self_creation)
    run("E2E.4 modify failure → rollback",      e2e_04_modify_failure_rollback)
    run("E2E.5 reflection chain",               e2e_05_reflection_chain)
    run("E2E.6 bidirectional memory",           e2e_06_bidirectional_memory)
    run("E2E.7 manual rollback",                e2e_07_manual_rollback)
    run("E2E.8 soul view chain",                e2e_08_soul_view_chain)

    ok = summary("§9 End-to-End Scenarios")
    sys.exit(0 if ok else 1)
