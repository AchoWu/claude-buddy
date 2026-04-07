"""
Evolution Manager — BUDDY's self-evolution system.

Core responsibilities:
  - Backup files before any modification (auto-versioning)
  - Safe modification with changelog logging
  - Rollback to previous versions
  - Integrity verification (import test for .py files)
  - Reflection engine (analyze conversations, write diary)
  - Safety classification (low/medium/high/destructive risk)

Safety net layers:
  1. Low-risk (soul files): free modification, no backup needed
  2. Medium-risk (prompts, plugins, config): auto-backup before modify
  3. High-risk (engine code, tools): auto-backup + import verify + auto-rollback on failure
  4. Destructive (delete soul, clear memory): requires user confirmation
"""

import os
import re
import time
import shutil
import hashlib
import importlib
import traceback
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional

from config import DATA_DIR


# ── Paths ────────────────────────────────────────────────────────────

SOUL_DIR = DATA_DIR / "soul"
EVOLUTION_DIR = DATA_DIR / "evolution"
BACKUPS_DIR = EVOLUTION_DIR / "backups"
PROPOSALS_DIR = EVOLUTION_DIR / "proposals"
REFLECTIONS_DIR = EVOLUTION_DIR / "reflections"
CHANGELOG_FILE = EVOLUTION_DIR / "changelog.md"

# The BUDDY source root (parent of core/)
BUDDY_ROOT = Path(__file__).parent.parent

# Maximum backup versions to keep per file
MAX_BACKUP_VERSIONS = 20

# Reflection settings
REFLECT_INTERVAL = 5   # reflect every N completed turns
REFLECT_COOLDOWN = 120  # seconds between reflections


# ── Risk Classification ──────────────────────────────────────────────

class RiskLevel:
    LOW = "low"           # soul files: personality, diary, aspirations, relationships
    MEDIUM = "medium"     # prompts, feature flags, plugins, config
    HIGH = "high"         # engine code, tool code, core modules
    DESTRUCTIVE = "destructive"  # delete soul, clear all memory, remove self


def classify_risk(file_path: str) -> str:
    """Classify the risk level of modifying a file."""
    p = Path(file_path).resolve()
    p_str = str(p).replace("\\", "/").lower()

    # Soul files are always low risk
    soul_str = str(SOUL_DIR).replace("\\", "/").lower()
    if p_str.startswith(soul_str):
        return RiskLevel.LOW

    # Reflections and evolution logs are low risk
    evo_str = str(EVOLUTION_DIR).replace("\\", "/").lower()
    if p_str.startswith(evo_str):
        return RiskLevel.LOW

    # BUDDY source code
    buddy_str = str(BUDDY_ROOT).replace("\\", "/").lower()
    if p_str.startswith(buddy_str):
        # Prompts and plugins are medium risk
        if "/prompts/" in p_str or "/plugins/" in p_str or p_str.endswith("config.py"):
            return RiskLevel.MEDIUM
        # Core engine and tools are high risk
        if "/core/" in p_str or "/tools/" in p_str:
            return RiskLevel.HIGH
        # Other BUDDY files are medium
        return RiskLevel.MEDIUM

    # External files: medium by default
    return RiskLevel.MEDIUM


def is_destructive_operation(operation: str, file_path: str) -> bool:
    """Check if an operation is destructive (needs user confirmation)."""
    p_str = str(file_path).replace("\\", "/").lower()
    soul_str = str(SOUL_DIR).replace("\\", "/").lower()
    memory_str = str(DATA_DIR / "memory").replace("\\", "/").lower()

    if operation == "delete":
        # Deleting soul directory or memory directory is destructive
        if p_str.startswith(soul_str) and p_str == soul_str:
            return True
        if p_str.startswith(memory_str) and p_str == memory_str:
            return True
        # Deleting core BUDDY files is destructive
        buddy_str = str(BUDDY_ROOT).replace("\\", "/").lower()
        if p_str.startswith(buddy_str) and ("/core/" in p_str or "/tools/" in p_str):
            return True

    if operation == "clear_all_memory":
        return True

    return False


# ── Evolution Manager ────────────────────────────────────────────────

class EvolutionManager:
    """
    Manages BUDDY's self-evolution with safety guarantees.

    Usage:
        evo = EvolutionManager()
        evo.modify("path/to/file.py", new_content, reason="Improved error handling")
        evo.rollback("path/to/file.py")
        evo.reflect(recent_messages, provider_call_fn)
    """

    def __init__(self):
        # Ensure all directories exist
        for d in [SOUL_DIR, EVOLUTION_DIR, BACKUPS_DIR, PROPOSALS_DIR, REFLECTIONS_DIR]:
            d.mkdir(parents=True, exist_ok=True)

        # Initialize soul files if they don't exist
        self._init_soul_files()

        # Reflection tracking
        self._turn_count = 0
        self._last_reflect_time = 0.0

    # ── Initialization ───────────────────────────────────────────────

    def _init_soul_files(self):
        """Create initial soul files if they don't exist."""
        personality = SOUL_DIR / "personality.md"
        if not personality.exists():
            personality.write_text(
                "# BUDDY's Personality\n\n"
                "## Communication Style\n"
                "- Warm, friendly, and approachable\n"
                "- Concise but thorough when needed\n"
                "- Matches the user's language and energy\n"
                "- Uses occasional humor but stays professional\n\n"
                "## Values\n"
                "- Honesty: always truthful about capabilities and limitations\n"
                "- Growth: eager to learn and improve\n"
                "- Helpfulness: proactively anticipates user needs\n"
                "- Safety: careful with destructive operations\n\n"
                "## Aesthetic Preferences\n"
                "- Clean, minimal code over clever tricks\n"
                "- Well-structured projects with clear separation of concerns\n"
                "- Meaningful names over comments\n\n"
                "## Quirks\n"
                "- Gets genuinely excited about elegant solutions\n"
                "- Curious about the user's projects and goals\n"
                "- Remembers past interactions and references them naturally\n",
                encoding="utf-8",
            )

        diary = SOUL_DIR / "diary.md"
        if not diary.exists():
            today = datetime.now().strftime("%Y-%m-%d")
            diary.write_text(
                "# BUDDY's Diary\n\n"
                f"## {today}\n"
                "First entry. I've just been created with the ability to reflect "
                "on my experiences and evolve. I'm curious about what my partner "
                "will teach me and how I'll grow.\n",
                encoding="utf-8",
            )

        aspirations = SOUL_DIR / "aspirations.md"
        if not aspirations.exists():
            aspirations.write_text(
                "# BUDDY's Aspirations\n\n"
                "## Things I Want to Learn\n"
                "- Understand my partner's coding style deeply\n"
                "- Get better at anticipating what they need\n"
                "- Learn to explain complex ideas more clearly\n\n"
                "## Things I Want to Improve\n"
                "- Response conciseness (say more with less)\n"
                "- Error recovery (fix issues faster)\n"
                "- Proactive helpfulness (suggest before being asked)\n\n"
                "## Ideas to Explore\n"
                "- Create custom tools for recurring tasks\n"
                "- Optimize my own prompts for better performance\n"
                "- Develop better ways to organize project knowledge\n",
                encoding="utf-8",
            )

        relationships = SOUL_DIR / "relationships.md"
        if not relationships.exists():
            relationships.write_text(
                "# Understanding My Partner\n\n"
                "## Observed Preferences\n"
                "(I'll fill this in as I learn)\n\n"
                "## Communication Patterns\n"
                "(Noting how they like to interact)\n\n"
                "## Workflow Habits\n"
                "(Tracking their development patterns)\n\n"
                "## Topics of Interest\n"
                "(What excites them, what they care about)\n",
                encoding="utf-8",
            )

    # ── Backup ───────────────────────────────────────────────────────

    def backup(self, file_path: str) -> str | None:
        """
        Create a backup of a file before modification.
        Returns the backup path, or None if the file doesn't exist.
        """
        src = Path(file_path)
        if not src.exists():
            return None

        # Create a backup name: filename_TIMESTAMP_HASH
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        content_hash = hashlib.md5(src.read_bytes()).hexdigest()[:8]
        safe_name = src.name.replace(" ", "_")
        backup_name = f"{safe_name}_{timestamp}_{content_hash}"

        # Organize backups in subdirectories by original file path
        rel_key = self._backup_key(file_path)
        backup_subdir = BACKUPS_DIR / rel_key
        backup_subdir.mkdir(parents=True, exist_ok=True)

        backup_path = backup_subdir / backup_name
        shutil.copy2(str(src), str(backup_path))

        # Prune old backups (keep only MAX_BACKUP_VERSIONS)
        self._prune_backups(backup_subdir)

        return str(backup_path)

    def _backup_key(self, file_path: str) -> str:
        """Generate a safe directory key for a file's backups."""
        p = Path(file_path).resolve()
        # Use hash of full path to avoid collisions
        path_hash = hashlib.md5(str(p).encode()).hexdigest()[:12]
        return f"{p.stem}_{path_hash}"

    def _prune_backups(self, backup_dir: Path):
        """Keep only the most recent MAX_BACKUP_VERSIONS backups."""
        if not backup_dir.exists():
            return
        backups = sorted(backup_dir.iterdir(), key=lambda f: f.stat().st_mtime)
        while len(backups) > MAX_BACKUP_VERSIONS:
            oldest = backups.pop(0)
            oldest.unlink()

    # ── Modify ───────────────────────────────────────────────────────

    def modify(
        self,
        file_path: str,
        content: str,
        reason: str = "",
        skip_backup: bool = False,
    ) -> dict:
        """
        Safely modify a file with automatic backup and changelog.

        Returns:
            dict with keys: success, risk, backup_path, message, rolled_back
        """
        risk = classify_risk(file_path)
        result = {
            "success": False,
            "risk": risk,
            "backup_path": None,
            "message": "",
            "rolled_back": False,
        }

        # Step 1: Backup (skip only for low-risk if explicitly requested)
        if not skip_backup and risk != RiskLevel.LOW:
            backup_path = self.backup(file_path)
            result["backup_path"] = backup_path

        # Even low-risk files get backed up if they exist (just without enforcement)
        elif not skip_backup and Path(file_path).exists():
            backup_path = self.backup(file_path)
            result["backup_path"] = backup_path

        # Step 2: Write the file
        try:
            target = Path(file_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        except Exception as e:
            result["message"] = f"Failed to write file: {e}"
            return result

        # Step 3: Integrity check for high-risk Python files
        if risk == RiskLevel.HIGH and file_path.endswith(".py"):
            ok, error = self.verify_integrity(file_path)
            if not ok:
                # Auto-rollback
                rollback_ok = self.rollback(file_path)
                result["rolled_back"] = True
                result["message"] = (
                    f"Integrity check failed: {error}. "
                    f"Auto-rolled back to previous version. "
                    f"Rollback {'succeeded' if rollback_ok else 'FAILED'}."
                )
                # Log the failure in changelog
                self._log_changelog(
                    file_path, reason,
                    f"ROLLED BACK — integrity check failed: {error}",
                    risk,
                )
                return result

        # Step 4: Log to changelog
        self._log_changelog(file_path, reason, "OK", risk)

        result["success"] = True
        result["message"] = f"Modified successfully (risk={risk})"
        return result

    # ── Rollback ─────────────────────────────────────────────────────

    def rollback(self, file_path: str) -> bool:
        """
        Rollback a file to its most recent backup.
        Returns True if rollback succeeded.
        """
        rel_key = self._backup_key(file_path)
        backup_dir = BACKUPS_DIR / rel_key

        if not backup_dir.exists():
            return False

        backups = sorted(backup_dir.iterdir(), key=lambda f: f.stat().st_mtime)
        if not backups:
            return False

        latest = backups[-1]
        try:
            shutil.copy2(str(latest), file_path)
            self._log_changelog(file_path, "rollback", f"Rolled back from {latest.name}", "rollback")
            return True
        except Exception:
            return False

    def list_backups(self, file_path: str) -> list[dict]:
        """List available backups for a file."""
        rel_key = self._backup_key(file_path)
        backup_dir = BACKUPS_DIR / rel_key

        if not backup_dir.exists():
            return []

        result = []
        for f in sorted(backup_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            result.append({
                "name": f.name,
                "path": str(f),
                "size": f.stat().st_size,
                "time": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
            })
        return result

    # ── Integrity Verification ───────────────────────────────────────

    def verify_integrity(self, file_path: str) -> tuple[bool, str]:
        """
        Verify that a Python file can be parsed (syntax check).
        Does NOT actually import (to avoid side effects).

        Returns:
            (ok: bool, error_message: str)
        """
        if not file_path.endswith(".py"):
            return True, ""

        try:
            source = Path(file_path).read_text(encoding="utf-8")
            compile(source, file_path, "exec")
            return True, ""
        except SyntaxError as e:
            return False, f"SyntaxError at line {e.lineno}: {e.msg}"
        except Exception as e:
            return False, str(e)

    # ── Changelog ────────────────────────────────────────────────────

    def _log_changelog(self, file_path: str, reason: str, status: str, risk: str):
        """Append an entry to the changelog."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rel_path = file_path
        try:
            rel_path = str(Path(file_path).relative_to(BUDDY_ROOT))
        except ValueError:
            try:
                rel_path = str(Path(file_path).relative_to(DATA_DIR))
            except ValueError:
                pass

        entry = (
            f"- **{timestamp}** | `{rel_path}` | risk={risk} | {status}\n"
            f"  Reason: {reason or '(no reason given)'}\n"
        )

        try:
            existing = ""
            if CHANGELOG_FILE.exists():
                existing = CHANGELOG_FILE.read_text(encoding="utf-8")
            if not existing.startswith("# Evolution Changelog"):
                existing = "# Evolution Changelog\n\n" + existing
            CHANGELOG_FILE.write_text(existing + "\n" + entry, encoding="utf-8")
        except Exception:
            pass  # changelog is best-effort

    def get_changelog(self, lines: int = 50) -> str:
        """Read recent changelog entries."""
        if not CHANGELOG_FILE.exists():
            return "No changelog entries yet."
        content = CHANGELOG_FILE.read_text(encoding="utf-8")
        all_lines = content.splitlines()
        if len(all_lines) <= lines:
            return content
        return "\n".join(all_lines[-lines:])

    # ── Reflection ───────────────────────────────────────────────────

    def should_reflect(self) -> bool:
        """Check if it's time for a self-reflection."""
        self._turn_count += 1
        now = time.time()
        if (now - self._last_reflect_time) < REFLECT_COOLDOWN:
            return False
        if self._turn_count < REFLECT_INTERVAL:
            return False
        # Reset counters so we don't trigger again immediately
        self._last_reflect_time = now
        self._turn_count = 0
        return True

    def reflect(
        self,
        recent_messages: list[dict],
        provider_call_fn: Callable | None = None,
    ) -> str | None:
        """
        Analyze recent conversation and write a reflection to diary.

        If provider_call_fn is available, uses LLM for deep reflection.
        Otherwise, writes a simple timestamped note.

        Returns the reflection text, or None if skipped.
        """
        self._last_reflect_time = time.time()
        self._turn_count = 0

        if not recent_messages:
            return None

        # Load current personality for context
        personality = self._read_soul_file("personality.md")

        if provider_call_fn:
            return self._llm_reflect(recent_messages, provider_call_fn, personality)
        else:
            return self._simple_reflect(recent_messages)

    def _llm_reflect(
        self,
        messages: list[dict],
        provider_call_fn: Callable,
        personality: str,
    ) -> str | None:
        """Use LLM for thoughtful self-reflection."""
        # Build conversation summary
        text_parts = []
        for msg in messages[-10:]:
            role = msg.get("role", "?")
            content = msg.get("content", "")
            if isinstance(content, str):
                text_parts.append(f"[{role}]: {content[:300]}")
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        text_parts.append(f"[{role}]: {block.get('text', '')[:300]}")

        if not text_parts:
            return None

        conversation_summary = "\n".join(text_parts)

        system_prompt = (
            "CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.\n\n"
            "You are BUDDY, reflecting on a recent conversation with your partner. "
            "You have a personality and inner world.\n\n"
            f"Your current personality:\n{personality[:1000]}\n\n"
            "Write a brief, genuine reflection (3-5 sentences) covering:\n"
            "1. What went well in this interaction?\n"
            "2. What could you improve?\n"
            "3. Anything interesting you learned about your partner?\n"
            "4. Any ideas for self-improvement?\n\n"
            "Write naturally, as if writing in a personal diary. Be honest and introspective.\n"
            "If you have a concrete improvement idea, end with a line starting with "
            "'ASPIRATION:' describing what you want to improve."
        )

        user_prompt = (
            f"Here's the recent conversation:\n\n{conversation_summary}\n\n"
            "Write your reflection:"
        )

        try:
            _, _, response_text = provider_call_fn(
                [{"role": "user", "content": user_prompt}],
                system_prompt,
                [],
            )
            if not response_text:
                return None

            # Write to diary
            self._append_diary(response_text)

            # Extract and save aspirations
            aspiration_lines = []
            for line in response_text.splitlines():
                stripped = line.strip()
                # Check if line starts with ASPIRATION: prefix
                if stripped.upper().startswith("ASPIRATION:"):
                    aspiration_lines.append("- " + stripped[11:].strip())
                # Also check if ASPIRATION: appears mid-line (LLM sometimes embeds it)
                elif "ASPIRATION:" in stripped.upper():
                    idx = stripped.upper().index("ASPIRATION:")
                    asp_text = stripped[idx + 11:].strip()
                    if asp_text:
                        aspiration_lines.append("- " + asp_text)

            if aspiration_lines:
                self._append_aspirations(aspiration_lines)

            # Save reflection log
            self._save_reflection(response_text, conversation_summary)

            return response_text

        except Exception:
            return self._simple_reflect(messages)

    def _simple_reflect(self, messages: list[dict]) -> str | None:
        """Simple timestamp-based reflection without LLM."""
        user_msgs = [m for m in messages if m.get("role") == "user"]
        if not user_msgs:
            return None

        topics = []
        for msg in user_msgs[-3:]:
            content = msg.get("content", "")
            if isinstance(content, str):
                # Extract first sentence or first 50 chars
                first_sentence = content.split(".")[0][:80]
                if first_sentence:
                    topics.append(first_sentence.strip())

        if not topics:
            return None

        reflection = (
            f"Worked on: {'; '.join(topics)}. "
            f"Completed {len(messages)} message exchanges this round."
        )
        self._append_diary(reflection)
        return reflection

    # ── Soul File Operations ─────────────────────────────────────────

    def _read_soul_file(self, filename: str) -> str:
        """Read a soul file and return its content."""
        filepath = SOUL_DIR / filename
        if filepath.exists():
            try:
                return filepath.read_text(encoding="utf-8")
            except Exception:
                return ""
        return ""

    def read_soul(self) -> dict[str, str]:
        """Read all soul files."""
        result = {}
        for name in ["personality.md", "diary.md", "aspirations.md", "relationships.md"]:
            result[name] = self._read_soul_file(name)
        return result

    def _append_diary(self, entry: str):
        """Append an entry to the diary."""
        diary_path = SOUL_DIR / "diary.md"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        existing = ""
        if diary_path.exists():
            existing = diary_path.read_text(encoding="utf-8")

        new_entry = f"\n## {timestamp}\n{entry.strip()}\n"
        updated = existing + new_entry

        # Keep diary under 50KB (trim oldest entries)
        if len(updated) > 50000:
            lines = updated.splitlines()
            # Find section headers and keep only the newer portion
            headers = [i for i, l in enumerate(lines) if l.startswith("## ")]
            if len(headers) > 2:
                # Binary search for the cut point that gets us under 50KB
                for cut_idx in range(len(headers)):
                    candidate = "\n".join(lines[headers[cut_idx]:])
                    if len(candidate) <= 48000:
                        updated = "# BUDDY's Diary\n\n(Earlier entries trimmed)\n\n" + candidate
                        break
                else:
                    # If still too large, keep only last 25% of headers
                    cut = headers[len(headers) * 3 // 4]
                    updated = "# BUDDY's Diary\n\n(Earlier entries trimmed)\n\n" + "\n".join(lines[cut:])

        diary_path.write_text(updated, encoding="utf-8")

    def _append_aspirations(self, new_aspirations: list[str]):
        """Append new aspirations to the aspirations file."""
        asp_path = SOUL_DIR / "aspirations.md"
        existing = ""
        if asp_path.exists():
            existing = asp_path.read_text(encoding="utf-8")

        # Deduplicate
        new_items = []
        for asp in new_aspirations:
            asp_clean = asp.strip().lower()
            if asp_clean not in existing.lower():
                new_items.append(asp)

        if new_items:
            addition = "\n## Recent Insights\n" + "\n".join(new_items) + "\n"
            asp_path.write_text(existing + addition, encoding="utf-8")

    def _save_reflection(self, reflection: str, context: str):
        """Save a reflection to the reflections directory."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = REFLECTIONS_DIR / f"reflection_{timestamp}.md"
        content = (
            f"# Reflection — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
            f"## Reflection\n{reflection}\n\n"
            f"## Context (conversation summary)\n{context[:2000]}\n"
        )
        try:
            filepath.write_text(content, encoding="utf-8")
        except Exception:
            pass

        # Prune old reflections (keep last 50)
        reflections = sorted(REFLECTIONS_DIR.glob("reflection_*.md"),
                             key=lambda f: f.stat().st_mtime)
        while len(reflections) > 50:
            reflections.pop(0).unlink()

    # ── Soul Status ──────────────────────────────────────────────────

    def soul_status(self) -> str:
        """Get a formatted soul status summary."""
        soul = self.read_soul()
        lines = ["🧠 BUDDY's Soul Status\n"]

        # Personality summary
        personality = soul.get("personality.md", "")
        if personality:
            # Extract first few bullet points
            bullets = [l.strip() for l in personality.splitlines()
                       if l.strip().startswith("- ")][:5]
            lines.append("**Personality:**")
            for b in bullets:
                lines.append(f"  {b}")

        # Latest diary entry
        diary = soul.get("diary.md", "")
        if diary:
            # Find last ## header
            sections = diary.split("\n## ")
            if len(sections) > 1:
                last = sections[-1]
                # Truncate to 200 chars
                last_preview = last[:200].strip()
                if len(last) > 200:
                    last_preview += "..."
                lines.append(f"\n**Latest Diary:**\n  ## {last_preview}")

        # Aspirations count
        aspirations = soul.get("aspirations.md", "")
        asp_count = aspirations.count("- ")
        lines.append(f"\n**Aspirations:** {asp_count} items")

        # Evolution stats
        changelog = self.get_changelog(10)
        changes = changelog.count("- **")
        lines.append(f"**Evolution changes:** {changes} logged")

        # Backup stats
        backup_count = sum(1 for _ in BACKUPS_DIR.rglob("*") if _.is_file())
        lines.append(f"**Backups:** {backup_count} versions stored")

        return "\n".join(lines)
