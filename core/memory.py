"""
Memory System v4 — CC-aligned with exact taxonomy + MEMORY.md index.

CC architecture (from src/memdir/, src/services/extractMemories/):
  - MEMORY.md as index: "- [Title](file.md) — one-line hook" (≤200 lines, ≤25KB)
  - Topic files with frontmatter: name, description, type
  - Four categories: user, feedback, project, reference
  - Semantic file naming: user_expertise.md, feedback_testing.md
  - Project memory: ~/.claude/projects/{sanitized-git-root}/memory/

BUDDY additions (not in CC):
  - Self-insight extraction → soul/relationships.md
  - Regex fallback when LLM unavailable
"""

import os
import re
import time
import hashlib
from pathlib import Path
from typing import Any, Callable, Optional

from config import DATA_DIR


MEMORY_DIR = DATA_DIR / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

PROJECT_MEMORIES_DIR = "projects"
MEMORY_INDEX = "MEMORY.md"

# CC-aligned limits
MAX_MEMORY_SIZE = 25000      # bytes for MEMORY.md index
MAX_MEMORY_LINES = 200       # lines for MEMORY.md index
MAX_EXTRACT_MESSAGES = 10    # recent messages to analyze

# CC four-category taxonomy (from src/memdir/memoryTypes.ts)
MEMORY_CATEGORIES = ("user", "feedback", "project", "reference")


# ── Frontmatter ──────────────────────────────────────────────────────

def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML-like frontmatter from markdown file.
    Returns (metadata_dict, body_text)."""
    if not content.startswith("---"):
        return {}, content
    end = content.find("\n---", 3)
    if end == -1:
        return {}, content
    fm_block = content[3:end].strip()
    body = content[end + 4:].strip()
    meta = {}
    for line in fm_block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val.startswith("[") and val.endswith("]"):
                items = [v.strip().strip('"').strip("'") for v in val[1:-1].split(",") if v.strip()]
                meta[key] = items
            else:
                meta[key] = val
    return meta, body


def _make_frontmatter(name: str, description: str, category: str) -> str:
    """Generate CC-aligned frontmatter for a memory topic file.
    CC schema: name, description, type (mandatory)."""
    return (
        f"---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        f"type: {category}\n"
        f"---"
    )


def _slugify(text: str) -> str:
    """Convert text to a safe filename slug. CC: semantic snake_case naming."""
    # Take first few meaningful words
    words = re.sub(r'[^a-zA-Z0-9\s]', '', text.lower()).split()
    slug = "_".join(words[:4])
    if not slug:
        slug = hashlib.md5(text.encode()).hexdigest()[:8]
    # Ensure uniqueness with short hash suffix
    h = hashlib.md5(text.encode()).hexdigest()[:4]
    return f"{slug}_{h}"


# ── LLM Extraction Prompt (CC four-category) ──────────────────────────

EXTRACT_SYSTEM_PROMPT = """\
CRITICAL: Respond with TEXT ONLY. Do NOT call any tools.

You are a memory extraction assistant. Your job is to identify information
from the conversation that should be remembered for future sessions.

Extract memories into these four categories (from CC's memoryTypes.ts):

## [user] — User role, goals, expertise, preferences, communication style
## [feedback] — Guidance on how to approach work; user corrections ("don't mock DB, use real DB")
## [project] — Project goals, architecture decisions, deadlines, team structure
## [reference] — Pointers to external systems (Jira, Slack, Grafana URLs, etc.)

Also extract self-insights about BUDDY's performance:
## [self] — Things BUDDY did well/poorly, patterns in user interaction

Rules:
- Output each memory as: - [category] title: description
  e.g. "- [user] Language preference: User prefers Chinese for all communication"
  e.g. "- [feedback] Testing policy: Always use real DB, never mock in integration tests"
- Be concise: one line per memory, title + description separated by colon
- Only extract DURABLE facts (not task-specific details)
- If nothing worth remembering, output exactly: NONE
- Do NOT extract: temporary task progress, file contents, error messages
- Update existing memories rather than creating duplicates
- Convert relative dates to absolute dates when possible
"""

EXTRACT_USER_TEMPLATE = """\
Review these recent conversation messages and extract any durable memories:

{messages_text}

Output memories as bullet points (or NONE if nothing to save):"""


class MemoryManager:
    """
    CC-aligned memory manager with four-category taxonomy.

    Storage structure (mirrors CC's ~/.claude/projects/...):
      ~/.claude-buddy/memory/
        MEMORY.md                    # Index: "- [Title](file.md) — hook"
        user_expertise_a1b2.md       # Semantic naming
        feedback_testing_c3d4.md
        project_roadmap_e5f6.md
        reference_jira_7890.md
        projects/
          <name>_<hash>/memory/
            MEMORY.md
            ...
    """

    def __init__(self, memory_dir: Path | None = None):
        self._dir = memory_dir or MEMORY_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._project_base = self._dir / PROJECT_MEMORIES_DIR
        self._project_base.mkdir(parents=True, exist_ok=True)
        self._last_extract_time = 0.0
        self._extract_cooldown = 60.0
        self._extract_turn_count = 0
        self._extract_interval = 3
        # Migrate legacy formats → CC v4
        self._migrate_legacy()

    # ── Load ─────────────────────────────────────────────────────────

    def load_memory(self, project_path: str | None = None) -> str | None:
        """Load memory: MEMORY.md index + all topic file bodies.
        Merges general + project-specific if project_path given."""
        parts = []

        general_content = self._load_memory_dir(self._dir)
        if general_content:
            parts.append("## General Memory\n" + general_content)

        if project_path:
            proj_dir = self._project_memory_dir(project_path)
            proj_content = self._load_memory_dir(proj_dir)
            if proj_content:
                parts.append(f"## Project Memory ({Path(project_path).name})\n" + proj_content)

        if not parts:
            return None
        combined = "\n\n".join(parts)
        if len(combined) > MAX_MEMORY_SIZE:
            combined = combined[:MAX_MEMORY_SIZE] + "\n... (memory truncated)"
        return combined

    def _load_memory_dir(self, mem_dir: Path) -> str | None:
        """Load MEMORY.md index + all topic file bodies from a directory."""
        if not mem_dir.exists():
            return None

        parts = []

        # Read MEMORY.md index
        index_file = mem_dir / MEMORY_INDEX
        if index_file.is_file():
            content = self._read_file(index_file)
            if content:
                parts.append(content)

        # Read all topic files (any .md that isn't MEMORY.md or .migrated)
        for f in sorted(mem_dir.glob("*.md")):
            if f.name == MEMORY_INDEX:
                continue
            content = self._read_file(f)
            if content:
                _, body = _parse_frontmatter(content)
                if body.strip():
                    parts.append(body.strip())

        if not parts:
            return None
        return "\n\n".join(parts)

    # ── Save ─────────────────────────────────────────────────────────

    def save_memory(self, content: str, project_path: str | None = None,
                    category: str = "user", name: str = "",
                    description: str = ""):
        """Save a memory entry to a topic file and update MEMORY.md index.
        CC-aligned: semantic filename, frontmatter with name/description/type."""
        if category not in MEMORY_CATEGORIES:
            category = "user"

        mem_dir = self._project_memory_dir(project_path) if project_path else self._dir
        mem_dir.mkdir(parents=True, exist_ok=True)

        clean = content.strip()
        if not clean:
            return

        # Check for duplicate
        existing = self._load_memory_dir(mem_dir) or ""
        if clean.lower() in existing.lower():
            return

        # Auto-generate name/description if not provided
        if not name:
            name = clean[:60].replace("\n", " ")
        if not description:
            description = clean[:120].replace("\n", " ")

        # CC-aligned: semantic filename
        slug = _slugify(clean)
        topic_file = mem_dir / f"{slug}.md"
        fm = _make_frontmatter(name, description, category)
        topic_file.write_text(f"{fm}\n\n{clean}\n", encoding="utf-8")

        # Update MEMORY.md index: "- [Title](file.md) — hook"
        self._update_index(mem_dir, name, description, topic_file.name)

    def _update_index(self, mem_dir: Path, title: str, hook: str,
                      filename: str):
        """Append a pointer to MEMORY.md index. CC format:
        - [Title](file.md) — one-line hook"""
        index_file = mem_dir / MEMORY_INDEX
        existing = self._read_file(index_file) or ""

        # CC exact format
        hook_short = hook[:120].replace("\n", " ")
        entry = f"- [{title}]({filename}) — {hook_short}"

        if filename in existing:
            return  # already indexed

        updated = existing + "\n" + entry + "\n" if existing else entry + "\n"

        # Enforce CC limits
        lines = updated.splitlines()
        if len(lines) > MAX_MEMORY_LINES:
            lines = lines[-MAX_MEMORY_LINES:]
            updated = "\n".join(lines) + "\n"
        if len(updated.encode("utf-8")) > MAX_MEMORY_SIZE:
            # Truncate and add warning (CC: truncateEntrypointContent)
            while len(updated.encode("utf-8")) > MAX_MEMORY_SIZE - 200:
                lines = updated.splitlines()
                if len(lines) <= 1:
                    break
                lines = lines[1:]  # drop oldest
                updated = "\n".join(lines) + "\n"
            updated += f"\n> WARNING: MEMORY.md exceeded {MAX_MEMORY_SIZE} bytes, oldest entries removed.\n"

        self._write_file(index_file, updated)

    def clear_memory(self, project_path: str | None = None):
        """Clear all memory files in the target directory."""
        mem_dir = self._project_memory_dir(project_path) if project_path else self._dir
        if not mem_dir.exists():
            return
        for f in mem_dir.glob("*.md"):
            try:
                f.unlink()
            except Exception:
                pass

    # ── Auto-Extraction ──────────────────────────────────────────────

    def should_extract(self) -> bool:
        self._extract_turn_count += 1
        now = time.time()
        if (now - self._last_extract_time) < self._extract_cooldown:
            return False
        if self._extract_turn_count < self._extract_interval:
            return False
        self._last_extract_time = now
        self._extract_turn_count = 0
        return True

    def auto_extract(
        self,
        recent_messages: list[dict],
        provider_call_fn: Callable | None = None,
        project_path: str | None = None,
    ) -> list[str]:
        """Extract memories using CC four-category taxonomy."""
        self._last_extract_time = time.time()
        self._extract_turn_count = 0

        msgs = recent_messages[-MAX_EXTRACT_MESSAGES:]
        if not msgs:
            return []

        if provider_call_fn:
            llm_memories = self._llm_extract(msgs, provider_call_fn)
            if llm_memories is not None:
                self._save_extracted(llm_memories, project_path)
                return [m["content"] for m in llm_memories]

        regex_memories = self._regex_extract(msgs)
        self._save_extracted(
            [{"category": "user", "name": m[:40], "content": m} for m in regex_memories],
            project_path,
        )
        return regex_memories

    def _llm_extract(
        self,
        messages: list[dict],
        provider_call_fn: Callable,
    ) -> list[dict] | None:
        """Use LLM to extract memories.
        Returns list of {category, name, description, content} or None."""
        try:
            text_parts = []
            for msg in messages:
                role = msg.get("role", "?")
                content = msg.get("content", "")
                if isinstance(content, str):
                    text_parts.append(f"[{role}]: {content[:500]}")
                elif isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(f"[{role}]: {block.get('text', '')[:500]}")
            if not text_parts:
                return []

            messages_text = "\n\n".join(text_parts)
            user_prompt = EXTRACT_USER_TEMPLATE.format(messages_text=messages_text)

            _, _, response_text = provider_call_fn(
                [{"role": "user", "content": user_prompt}],
                EXTRACT_SYSTEM_PROMPT,
                [],
            )

            if not response_text or "NONE" in response_text.strip().upper():
                return []

            # Parse: - [category] title: description
            results = []
            self_insights = []
            cat_pattern = re.compile(r"^[-*]\s*\[(\w+)\]\s*(.+)$")
            for line in response_text.splitlines():
                m = cat_pattern.match(line.strip())
                if m:
                    cat = m.group(1).lower()
                    text = m.group(2).strip()
                    # Split "title: description" if colon present
                    if ": " in text:
                        name, _, desc = text.partition(": ")
                    else:
                        name = text[:40]
                        desc = text

                    if cat == "self":
                        self_insights.append(text)
                    elif cat in MEMORY_CATEGORIES:
                        results.append({
                            "category": cat,
                            "name": name.strip(),
                            "description": desc.strip(),
                            "content": text,
                        })
                    else:
                        results.append({
                            "category": "user",
                            "name": name.strip(),
                            "description": desc.strip(),
                            "content": text,
                        })

            if self_insights:
                self._save_self_insights(self_insights)

            return results[:10]

        except Exception:
            return None

    def _regex_extract(self, messages: list[dict]) -> list[str]:
        """Fast regex-based extraction (fallback)."""
        memories = []
        patterns = [
            r"(?:always|never|prefer|remember|note that|keep in mind|from now on|whenever)\s+(.{10,120})",
            r"(?:i (?:like|prefer|want|need)|please (?:always|never))\s+(.{10,120})",
            r"(?:my (?:preference|style|convention) is)\s+(.{10,120})",
            r"(?:don't|do not|stop)\s+(.{10,80})",
            r"(?:use|switch to|change to)\s+(\w+)\s+(?:instead|from now|always)",
        ]
        for msg in messages:
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue
            for pattern in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches:
                    clean = match.strip().rstrip(".,;!?")
                    if len(clean) > 15:
                        memories.append(clean)
        return memories[:10]

    # For backwards compatibility
    def extract_memories(self, conversation_messages: list[dict]) -> list[str]:
        return self._regex_extract(conversation_messages)

    def _save_extracted(self, memories: list[dict], project_path: str | None):
        """Save extracted memories with CC-aligned fields."""
        if not memories:
            return
        for mem in memories:
            self.save_memory(
                mem.get("content", ""),
                project_path=project_path,
                category=mem.get("category", "user"),
                name=mem.get("name", ""),
                description=mem.get("description", ""),
            )

    # ── Self-Insight Storage ─────────────────────────────────────────

    def _save_self_insights(self, insights: list[str]):
        """Save BUDDY's self-insights to the relationships.md soul file."""
        try:
            from core.evolution import SOUL_DIR
            relationships_file = SOUL_DIR / "relationships.md"
            if not relationships_file.exists():
                return
            existing = relationships_file.read_text(encoding="utf-8")
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d")

            new_entries = []
            for insight in insights[:5]:
                clean = insight.strip()
                if clean and clean.lower() not in existing.lower():
                    new_entries.append(f"- {clean}")

            if new_entries:
                addition = f"\n## Insights ({timestamp})\n" + "\n".join(new_entries) + "\n"
                updated = existing + addition
                if len(updated) > 25000:
                    lines = updated.splitlines()
                    updated = "\n".join(lines[-200:])
                relationships_file.write_text(updated, encoding="utf-8")
        except Exception:
            pass

    # ── Legacy Migration ─────────────────────────────────────────────

    # Map old categories to CC categories
    _LEGACY_CAT_MAP = {
        "knowledge": "reference",
        "context": "project",
        "techniques": "feedback",
        "preferences": "user",
    }

    def _migrate_legacy(self):
        """Migrate old formats (v2 general.md, v3 category_hash.md) → CC v4.
        Runs once per format found."""
        # v2: general.md (flat bullet list)
        self._migrate_v2_general()
        # v3: knowledge_hash.md / preferences_hash.md etc.
        self._migrate_v3_category_files()

    def _migrate_v2_general(self):
        """Migrate v2 general.md → v4 topic files."""
        legacy = self._dir / "general.md"
        if not legacy.is_file():
            return
        try:
            content = legacy.read_text(encoding="utf-8").strip()
            if not content:
                legacy.unlink()
                return
            for line in content.splitlines():
                line = line.strip().lstrip("- ").strip()
                if len(line) > 5:
                    lower = line.lower()
                    cat = "user"
                    if any(w in lower for w in ("project", "architecture", "interested")):
                        cat = "project"
                    elif any(w in lower for w in ("pattern", "technique", "debug")):
                        cat = "feedback"
                    elif any(w in lower for w in ("jira", "slack", "url", "link")):
                        cat = "reference"
                    self.save_memory(line, category=cat, name=line[:40])
            legacy.rename(self._dir / "general.md.migrated")
        except Exception:
            pass

    def _migrate_v3_category_files(self):
        """Migrate v3 files (knowledge_hash.md, preferences_hash.md) → v4."""
        old_cats = ("knowledge", "context", "techniques", "preferences")
        # Collect files to migrate first
        to_migrate = []
        for old_cat in old_cats:
            for f in list(self._dir.glob(f"{old_cat}_*.md")):
                try:
                    content = f.read_text(encoding="utf-8")
                    meta, body = _parse_frontmatter(content)
                    body = body.strip()
                    if not body:
                        f.unlink()
                        continue
                    new_cat = self._LEGACY_CAT_MAP.get(old_cat, "user")
                    to_migrate.append((f, new_cat, meta, body))
                except Exception:
                    pass

        if not to_migrate:
            return

        # Rename all old files first (so dedup check doesn't see them)
        for f, _, _, _ in to_migrate:
            try:
                f.rename(f.with_suffix(".md.migrated"))
            except Exception:
                pass

        # Clear stale index
        idx = self._dir / MEMORY_INDEX
        if idx.is_file():
            idx.unlink()

        # Now save as new v4 files
        for _, new_cat, meta, body in to_migrate:
            self.save_memory(
                body, category=new_cat,
                name=meta.get("name", body[:40]),
                description=meta.get("description", body[:80]),
            )

    def _rebuild_index(self, mem_dir: Path):
        """Rebuild MEMORY.md from current topic files."""
        entries = []
        for f in sorted(mem_dir.glob("*.md")):
            if f.name == MEMORY_INDEX:
                continue
            content = self._read_file(f)
            if not content:
                continue
            meta, body = _parse_frontmatter(content)
            name = meta.get("name", body[:40].replace("\n", " "))
            desc = meta.get("description", body[:80].replace("\n", " "))
            entries.append(f"- [{name}]({f.name}) — {desc[:120]}")
        if entries:
            self._write_file(mem_dir / MEMORY_INDEX, "\n".join(entries) + "\n")
        else:
            # No entries, clean index
            idx = mem_dir / MEMORY_INDEX
            if idx.exists():
                idx.unlink()

    # ── Helpers ───────────────────────────────────────────────────────

    def _project_memory_dir(self, project_path: str | None) -> Path:
        if not project_path:
            return self._dir
        path_hash = hashlib.md5(project_path.encode()).hexdigest()[:12]
        name = Path(project_path).name
        proj_dir = self._project_base / f"{name}_{path_hash}" / "memory"
        proj_dir.mkdir(parents=True, exist_ok=True)
        return proj_dir

    @staticmethod
    def _read_file(filepath: Path) -> str | None:
        if not filepath.exists():
            return None
        try:
            content = filepath.read_text(encoding="utf-8").strip()
            return content if content else None
        except Exception:
            return None

    @staticmethod
    def _write_file(filepath: Path, content: str):
        try:
            filepath.parent.mkdir(parents=True, exist_ok=True)
            filepath.write_text(content, encoding="utf-8")
        except Exception:
            pass
