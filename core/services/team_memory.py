"""
Team Memory Sync — shared memory between agents.
Aligned with Claude Code's services/teamMemorySync/ patterns.

Provides:
  - TeamMemoryStore: shared key-value store accessible by all agents in a team
  - Memory scoping: session-scoped (default), project-scoped, global
  - Parent→child memory propagation: sub-agent inherits relevant parent memories
  - Child→parent merge: sub-agent's new memories merge back after completion
  - Conflict resolution: last-write-wins with timestamp tracking

Usage:
  store = TeamMemoryStore()

  # Parent agent saves a memory
  store.set("project_stack", "React + TypeScript + Postgres", scope="project")

  # Spawn sub-agent with relevant memories
  child_memories = store.get_context_for_agent(agent_id="agent_2", team="research")

  # Sub-agent discovers something and saves it
  store.set("api_endpoint", "https://api.example.com/v2", agent_id="agent_2")

  # After sub-agent completes, merge back to parent
  new_entries = store.get_new_entries_by(agent_id="agent_2")
"""

import time
import json
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, field

from config import DATA_DIR


TEAM_MEMORY_DIR = DATA_DIR / "team_memory"
TEAM_MEMORY_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class MemoryEntry:
    """A single memory entry in the team store."""
    key: str
    value: str
    scope: str = "session"        # "session", "project", "global"
    agent_id: str = "main"        # which agent created this
    team: str = ""                # team name (empty = all teams)
    timestamp: float = field(default_factory=time.time)
    merged: bool = False          # True if merged back from sub-agent

    def to_dict(self) -> dict:
        return {
            "key": self.key, "value": self.value,
            "scope": self.scope, "agent_id": self.agent_id,
            "team": self.team, "timestamp": self.timestamp,
            "merged": self.merged,
        }

    @staticmethod
    def from_dict(d: dict) -> "MemoryEntry":
        return MemoryEntry(
            key=d["key"], value=d["value"],
            scope=d.get("scope", "session"),
            agent_id=d.get("agent_id", "main"),
            team=d.get("team", ""),
            timestamp=d.get("timestamp", time.time()),
            merged=d.get("merged", False),
        )


class TeamMemoryStore:
    """
    Shared memory store for multi-agent coordination.
    All agents read/write the same store; entries are tagged by agent_id.
    """

    def __init__(self, persist_dir: Path | None = None):
        self._entries: dict[str, MemoryEntry] = {}  # key → entry
        self._persist_dir = persist_dir or TEAM_MEMORY_DIR

    # ── Read/Write ────────────────────────────────────────────────

    def set(self, key: str, value: str, scope: str = "session",
            agent_id: str = "main", team: str = ""):
        """Set a memory entry. Overwrites if key exists (last-write-wins)."""
        self._entries[key] = MemoryEntry(
            key=key, value=value, scope=scope,
            agent_id=agent_id, team=team,
        )

    def get(self, key: str) -> str | None:
        """Get a memory value by key."""
        entry = self._entries.get(key)
        return entry.value if entry else None

    def delete(self, key: str) -> bool:
        return self._entries.pop(key, None) is not None

    def has(self, key: str) -> bool:
        return key in self._entries

    def all_entries(self) -> list[MemoryEntry]:
        return list(self._entries.values())

    # ── Agent Context ─────────────────────────────────────────────

    def get_context_for_agent(self, agent_id: str = "", team: str = "") -> str:
        """
        Build a memory context string for a sub-agent.
        Includes: all global + project entries, plus team-specific entries.
        """
        relevant = []
        for entry in self._entries.values():
            # Global and project scope: always include
            if entry.scope in ("global", "project"):
                relevant.append(entry)
            # Session scope: include if same team or no team restriction
            elif entry.scope == "session":
                if not entry.team or entry.team == team:
                    relevant.append(entry)

        if not relevant:
            return ""

        lines = ["## Shared Team Memory"]
        for e in sorted(relevant, key=lambda x: x.timestamp):
            source = f" (from {e.agent_id})" if e.agent_id != "main" else ""
            lines.append(f"- **{e.key}**: {e.value}{source}")
        return "\n".join(lines)

    def get_new_entries_by(self, agent_id: str) -> list[MemoryEntry]:
        """Get all entries created by a specific agent (for merge-back)."""
        return [e for e in self._entries.values() if e.agent_id == agent_id]

    def merge_from_agent(self, agent_id: str, target_agent: str = "main"):
        """
        Merge memories from a sub-agent back to the parent.
        Marks merged entries so they aren't double-merged.
        """
        for entry in self._entries.values():
            if entry.agent_id == agent_id and not entry.merged:
                entry.merged = True
                # Entries are already in the shared store, so "merging"
                # just means marking them as acknowledged by parent.

    # ── Team Filtering ────────────────────────────────────────────

    def get_team_entries(self, team: str) -> list[MemoryEntry]:
        """Get all entries for a specific team."""
        return [e for e in self._entries.values()
                if e.team == team or not e.team]

    def clear_team(self, team: str):
        """Remove all entries for a team."""
        to_remove = [k for k, e in self._entries.items() if e.team == team]
        for k in to_remove:
            del self._entries[k]

    def clear_agent(self, agent_id: str):
        """Remove all entries created by a specific agent."""
        to_remove = [k for k, e in self._entries.items() if e.agent_id == agent_id]
        for k in to_remove:
            del self._entries[k]

    # ── Format ────────────────────────────────────────────────────

    def format_summary(self) -> str:
        """Human-readable summary of all entries."""
        if not self._entries:
            return "Team memory is empty."
        lines = [f"Team Memory ({len(self._entries)} entries):"]
        for e in sorted(self._entries.values(), key=lambda x: x.timestamp):
            merged = " [merged]" if e.merged else ""
            lines.append(f"  [{e.scope}] {e.key} = {e.value[:80]} (by {e.agent_id}){merged}")
        return "\n".join(lines)

    # ── Persistence ───────────────────────────────────────────────

    def save(self, name: str = "default"):
        """Persist team memory to disk."""
        try:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            path = self._persist_dir / f"{name}.json"
            data = [e.to_dict() for e in self._entries.values()]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load(self, name: str = "default") -> bool:
        """Load team memory from disk."""
        path = self._persist_dir / f"{name}.json"
        if not path.exists():
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self._entries.clear()
            for d in data:
                entry = MemoryEntry.from_dict(d)
                self._entries[entry.key] = entry
            return True
        except Exception:
            return False

    def clear(self):
        self._entries.clear()
