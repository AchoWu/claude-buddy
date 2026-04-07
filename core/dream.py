"""
Dream / Proactive Memory Consolidation — CC-aligned.
CC: src/services/autoDream/autoDream.ts

Gates:
  1. Time: hours since last dream >= 24
  2. Sessions: session count since last dream >= 5
When triggered, spawns a subagent to consolidate recent conversation summaries
into MEMORY.md.
"""

import json
import time
import threading
from pathlib import Path
from typing import Callable, Any


# CC: autoDream defaults
MIN_HOURS_BETWEEN_DREAMS = 24
MIN_SESSIONS_BEFORE_DREAM = 5


class DreamManager:
    """CC-aligned proactive memory consolidation manager."""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._state_path = data_dir / "dream_state.json"
        self._lock_path = data_dir / ".dream.lock"
        self._state = self._load_state()

    def should_dream(self) -> bool:
        """CC: check both gates — time AND sessions."""
        now = time.time()
        last = self._state.get("last_dream_at", 0)
        sessions = self._state.get("sessions_since_dream", 0)

        hours_since = (now - last) / 3600
        return hours_since >= MIN_HOURS_BETWEEN_DREAMS and sessions >= MIN_SESSIONS_BEFORE_DREAM

    def record_session(self):
        """Increment session counter (called on each session start/message)."""
        self._state["sessions_since_dream"] = self._state.get("sessions_since_dream", 0) + 1
        self._save_state()

    def dream(
        self,
        recent_summaries: list[str],
        provider_call_fn: Callable | None = None,
        memory_path: Path | None = None,
    ) -> str | None:
        """
        CC-aligned: run memory consolidation.
        Reads recent summaries, generates updated MEMORY.md content.
        """
        # File lock to prevent concurrent dreams
        if not self._acquire_lock():
            return None

        try:
            if not provider_call_fn:
                return None

            memory_path = memory_path or (self._data_dir / "MEMORY.md")

            # Read existing memory
            existing = ""
            if memory_path.exists():
                existing = memory_path.read_text(encoding="utf-8")

            # Build consolidation prompt
            summaries_text = "\n---\n".join(recent_summaries[-10:])  # last 10
            prompt = (
                "You are consolidating conversation memories. "
                "Review the recent session summaries below and update the memory file.\n\n"
                f"## Current MEMORY.md:\n{existing or '(empty)'}\n\n"
                f"## Recent session summaries:\n{summaries_text}\n\n"
                "Instructions:\n"
                "- Add new facts, preferences, project context discovered in recent sessions\n"
                "- Remove outdated information\n"
                "- Keep it concise (under 500 words)\n"
                "- Output the complete updated MEMORY.md content"
            )

            try:
                _, _, result = provider_call_fn(
                    messages=[{"role": "user", "content": prompt}],
                    system="You are a memory consolidation agent. Output only the updated MEMORY.md content.",
                    tools=[],
                )
                if result and len(result.strip()) > 20:
                    memory_path.write_text(result.strip(), encoding="utf-8")
                    self._state["last_dream_at"] = time.time()
                    self._state["sessions_since_dream"] = 0
                    self._save_state()
                    return result.strip()
            except Exception:
                pass
            return None
        finally:
            self._release_lock()

    def dream_async(self, recent_summaries: list[str],
                    provider_call_fn: Callable | None = None,
                    callback: Callable[[str | None], None] | None = None):
        """Fire-and-forget async dream."""
        def _run():
            result = self.dream(recent_summaries, provider_call_fn)
            if callback:
                try:
                    callback(result)
                except Exception:
                    pass
        t = threading.Thread(target=_run, daemon=True)
        t.start()

    def _load_state(self) -> dict:
        if self._state_path.exists():
            try:
                return json.loads(self._state_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"last_dream_at": 0, "sessions_since_dream": 0}

    def _save_state(self):
        self._data_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._state_path.write_text(
                json.dumps(self._state, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def _acquire_lock(self) -> bool:
        """Simple file-based lock."""
        try:
            self._data_dir.mkdir(parents=True, exist_ok=True)
            if self._lock_path.exists():
                # Check if lock is stale (>1 hour)
                if time.time() - self._lock_path.stat().st_mtime > 3600:
                    self._lock_path.unlink(missing_ok=True)
                else:
                    return False
            self._lock_path.write_text(str(time.time()), encoding="utf-8")
            return True
        except Exception:
            return False

    def _release_lock(self):
        try:
            self._lock_path.unlink(missing_ok=True)
        except Exception:
            pass
