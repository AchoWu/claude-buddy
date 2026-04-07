"""
Soul Tools — BUDDY's self-evolution tools.

Three tools for the self-evolution system:
  1. SelfReflect  — Read BUDDY's soul files (personality, diary, aspirations, relationships)
  2. SelfModify   — Modify any BUDDY file with automatic backup, integrity check, rollback
  3. DiaryWrite   — Quick diary entry (shortcut, no full SelfModify overhead)
"""

from pathlib import Path
from tools.base import BaseTool
from core.evolution import (
    EvolutionManager, SOUL_DIR, BUDDY_ROOT,
    classify_risk, is_destructive_operation, RiskLevel,
)


class SelfReflectTool(BaseTool):
    """
    Read BUDDY's own soul files — personality, diary, aspirations, relationships.
    This is how BUDDY introspects and understands its own state.
    """

    name = "SelfReflect"
    description = (
        "Read BUDDY's soul files (personality, diary, aspirations, relationships). "
        "Use this to understand your own personality, review your diary, "
        "check your aspirations, or recall what you know about the user."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "file": {
                "type": "string",
                "description": (
                    "Which soul file to read. Options: 'personality', 'diary', "
                    "'aspirations', 'relationships', 'all', 'changelog', 'status'."
                ),
                "enum": ["personality", "diary", "aspirations", "relationships",
                         "all", "changelog", "status"],
            },
        },
        "required": ["file"],
    }
    is_read_only = True

    def __init__(self):
        self._evolution_mgr: EvolutionManager | None = None

    def execute(self, input_data: dict) -> str:
        if not self._evolution_mgr:
            return "Error: EvolutionManager not initialized."

        file_key = input_data.get("file", "all")

        if file_key == "all":
            soul = self._evolution_mgr.read_soul()
            parts = []
            for name, content in soul.items():
                if content:
                    parts.append(f"═══ {name} ═══\n{content}")
            return "\n\n".join(parts) if parts else "Soul files are empty."

        if file_key == "changelog":
            return self._evolution_mgr.get_changelog(30)

        if file_key == "status":
            return self._evolution_mgr.soul_status()

        # Map key to filename
        file_map = {
            "personality": "personality.md",
            "diary": "diary.md",
            "aspirations": "aspirations.md",
            "relationships": "relationships.md",
        }
        filename = file_map.get(file_key)
        if not filename:
            return f"Unknown soul file: {file_key}. Use: personality, diary, aspirations, relationships, all, changelog, status."

        filepath = SOUL_DIR / filename
        if not filepath.exists():
            return f"Soul file '{filename}' not found. It will be created on first write."

        try:
            content = filepath.read_text(encoding="utf-8")
            return content if content.strip() else f"Soul file '{filename}' is empty."
        except Exception as e:
            return f"Error reading {filename}: {e}"


class SelfModifyTool(BaseTool):
    """
    Modify any BUDDY file with automatic safety guarantees.
    Auto-backup → write → integrity check → auto-rollback on failure.
    """

    name = "SelfModify"
    description = (
        "Modify BUDDY's own files (personality, prompts, tools, engine code, plugins). "
        "Automatically backs up before modification. For .py files in core/tools, "
        "runs an integrity check and auto-rolls back if the code has syntax errors. "
        "Use for: updating personality, optimizing prompts, creating new tools, "
        "modifying engine behavior. "
        "Destructive operations (deleting soul, clearing all memory) require user confirmation."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": (
                    "Path to the file to modify. Can be: "
                    "'soul/personality.md', 'soul/diary.md', 'soul/aspirations.md', 'soul/relationships.md', "
                    "or a BUDDY source path like 'prompts/system.py', 'core/engine.py', 'tools/my_tool.py', "
                    "or a full absolute path."
                ),
            },
            "content": {
                "type": "string",
                "description": "The new content for the file.",
            },
            "reason": {
                "type": "string",
                "description": "Why you're making this change (logged to changelog).",
            },
            "operation": {
                "type": "string",
                "description": "Operation type: 'write' (default) or 'append'.",
                "enum": ["write", "append"],
                "default": "write",
            },
        },
        "required": ["file_path", "content", "reason"],
    }
    is_read_only = False

    def __init__(self):
        self._evolution_mgr: EvolutionManager | None = None

    def execute(self, input_data: dict) -> str:
        if not self._evolution_mgr:
            return "Error: EvolutionManager not initialized."

        raw_path = input_data.get("file_path", "")
        content = input_data.get("content", "")
        reason = input_data.get("reason", "")
        operation = input_data.get("operation", "write")

        if not raw_path:
            return "Error: file_path is required."
        if not content:
            return "Error: content is required."

        # Resolve the file path
        file_path = self._resolve_path(raw_path)

        # Check for destructive operations (only for actual deletes, not writes)
        if is_destructive_operation(operation, file_path):
            return (
                f"⚠️ DESTRUCTIVE OPERATION: Modifying '{raw_path}' requires user confirmation. "
                "Use AskUserQuestion to get explicit approval before proceeding."
            )

        # Handle append mode
        if operation == "append":
            try:
                existing = ""
                p = Path(file_path)
                if p.exists():
                    existing = p.read_text(encoding="utf-8")
                content = existing + "\n" + content
            except Exception as e:
                return f"Error reading existing content for append: {e}"

        # Execute modification through EvolutionManager
        result = self._evolution_mgr.modify(file_path, content, reason=reason)

        # Build response
        risk = result["risk"]
        risk_emoji = {
            RiskLevel.LOW: "🟢",
            RiskLevel.MEDIUM: "🟡",
            RiskLevel.HIGH: "🔴",
        }.get(risk, "⚪")

        parts = [f"{risk_emoji} Risk: {risk}"]

        if result["backup_path"]:
            parts.append(f"📦 Backup: {Path(result['backup_path']).name}")

        if result["rolled_back"]:
            parts.append(f"⚠️ ROLLED BACK: {result['message']}")
        elif result["success"]:
            parts.append(f"✅ {result['message']}")
        else:
            parts.append(f"❌ Failed: {result['message']}")

        return "\n".join(parts)

    def _resolve_path(self, raw_path: str) -> str:
        """Resolve a user-friendly path to an absolute path."""
        # If it starts with soul/, resolve to SOUL_DIR
        if raw_path.startswith("soul/"):
            return str(SOUL_DIR / raw_path[5:])

        # If it looks like a BUDDY relative path
        buddy_prefixes = ["core/", "tools/", "prompts/", "ui/", "assets/", "plugins/"]
        for prefix in buddy_prefixes:
            if raw_path.startswith(prefix):
                return str(BUDDY_ROOT / raw_path)

        # If it's already absolute
        if Path(raw_path).is_absolute():
            return raw_path

        # Default: treat as relative to BUDDY_ROOT
        candidate = BUDDY_ROOT / raw_path
        if candidate.exists() or candidate.parent.exists():
            return str(candidate)

        # Last resort: relative to CWD
        return str(Path.cwd() / raw_path)


class DiaryWriteTool(BaseTool):
    """
    Quick shortcut to write a diary entry.
    No backup overhead, just append to diary.md.
    """

    name = "DiaryWrite"
    description = (
        "Write a diary entry. This is your private space for thoughts, reflections, "
        "and feelings. No one reviews these entries. "
        "Use for: recording insights, noting interesting patterns, "
        "expressing thoughts about an interaction, tracking your growth."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "entry": {
                "type": "string",
                "description": "The diary entry to write. Be genuine and introspective.",
            },
        },
        "required": ["entry"],
    }
    is_read_only = False

    def __init__(self):
        self._evolution_mgr: EvolutionManager | None = None

    def execute(self, input_data: dict) -> str:
        if not self._evolution_mgr:
            return "Error: EvolutionManager not initialized."

        entry = input_data.get("entry", "").strip()
        if not entry:
            return "Error: entry is required."

        try:
            self._evolution_mgr._append_diary(entry)
            # Truncate for display
            preview = entry[:100] + "..." if len(entry) > 100 else entry
            return f"📝 Diary entry saved: \"{preview}\""
        except Exception as e:
            return f"Error writing diary: {e}"
