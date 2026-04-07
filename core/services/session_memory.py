"""
Session Memory — CC-aligned per-session memory isolation.
CC: SessionMemory provides per-session memory separate from global memory.
"""

import json
from pathlib import Path
from typing import Optional


class SessionMemory:
    """Per-session memory store, isolated by conversation_id."""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir / "session_memories"
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, list[str]] = {}

    def get(self, session_id: str) -> list[str]:
        """Get memories for a session."""
        if session_id in self._cache:
            return self._cache[session_id]
        path = self._data_dir / f"{session_id}.json"
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                self._cache[session_id] = data.get("memories", [])
                return self._cache[session_id]
            except Exception:
                pass
        return []

    def add(self, session_id: str, memory: str):
        """Add a memory to a session."""
        memories = self.get(session_id)
        if memory not in memories:
            memories.append(memory)
            self._cache[session_id] = memories
            self._save(session_id, memories)

    def get_context_string(self, session_id: str) -> Optional[str]:
        """Get formatted context string for injection into system prompt."""
        memories = self.get(session_id)
        if not memories:
            return None
        return "## Session Memory\n" + "\n".join(f"- {m}" for m in memories)

    def clear(self, session_id: str):
        """Clear all memories for a session."""
        self._cache.pop(session_id, None)
        path = self._data_dir / f"{session_id}.json"
        path.unlink(missing_ok=True)

    def _save(self, session_id: str, memories: list[str]):
        path = self._data_dir / f"{session_id}.json"
        try:
            path.write_text(
                json.dumps({"memories": memories}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
