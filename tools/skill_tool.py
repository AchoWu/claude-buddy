"""
Skill Tool — invoke dynamic skills (slash commands available to the model).
Aligned with Claude Code's SkillTool.
"""

import os
import json
from pathlib import Path
from tools.base import BaseTool
from config import DATA_DIR


SKILLS_DIR = DATA_DIR / "skills"
SKILLS_DIR.mkdir(parents=True, exist_ok=True)


class SkillTool(BaseTool):
    name = "Skill"
    description = (
        "Invoke a registered skill (slash command) by name.\n\n"
        "Skills are pre-defined action sequences that automate common tasks.\n"
        "They are loaded from ~/.claude-buddy/skills/ directory.\n\n"
        "Use this when the user asks for a slash command like /commit or /review.\n\n"
        "Parameters:\n"
        "- skill: The skill name (e.g., 'commit', 'review-pr')\n"
        "- args: Optional arguments for the skill"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "skill": {
                "type": "string",
                "description": "The skill name to invoke",
            },
            "args": {
                "type": "string",
                "description": "Optional arguments for the skill",
                "default": "",
            },
        },
        "required": ["skill"],
    }
    is_read_only = False

    def __init__(self):
        self._command_registry = None  # injected by ToolRegistry

    def execute(self, input_data: dict) -> str:
        skill_name = input_data.get("skill", "").strip()
        args = input_data.get("args", "").strip()

        if not skill_name:
            return "Error: skill name is required."

        # 1. Check command registry first
        if self._command_registry:
            cmd = self._command_registry.get(skill_name)
            if cmd:
                return self._command_registry.execute(f"/{skill_name} {args}".strip())

        # 2. Check skills directory for skill files
        skill_file = SKILLS_DIR / f"{skill_name}.json"
        if skill_file.exists():
            return self._load_and_run_skill(skill_file, args)

        skill_file_md = SKILLS_DIR / f"{skill_name}.md"
        if skill_file_md.exists():
            return self._load_prompt_skill(skill_file_md, args)

        # 3. List available skills
        available = self._list_available()
        return (
            f"Skill '{skill_name}' not found.\n"
            f"Available skills: {available or '(none)'}\n"
            f"Add skills to {SKILLS_DIR}/"
        )

    def _load_and_run_skill(self, skill_file: Path, args: str) -> str:
        """Load a JSON skill definition and return its prompt."""
        try:
            with open(skill_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            prompt = data.get("prompt", "")
            if args:
                prompt = prompt.replace("{{args}}", args)
            return f"[Skill loaded: {skill_file.stem}]\n\n{prompt}"
        except Exception as e:
            return f"Error loading skill: {e}"

    def _load_prompt_skill(self, skill_file: Path, args: str) -> str:
        """Load a markdown skill (prompt template)."""
        try:
            content = skill_file.read_text(encoding="utf-8")
            if args:
                content = content.replace("{{args}}", args)
            return f"[Skill loaded: {skill_file.stem}]\n\n{content}"
        except Exception as e:
            return f"Error loading skill: {e}"

    def _list_available(self) -> str:
        """List available skills from directory + command registry."""
        skills = set()

        # From skills directory
        if SKILLS_DIR.exists():
            for f in SKILLS_DIR.iterdir():
                if f.suffix in (".json", ".md"):
                    skills.add(f.stem)

        # From command registry
        if self._command_registry:
            for name, _ in self._command_registry.list_commands():
                skills.add(name.lstrip("/"))

        return ", ".join(sorted(skills)) if skills else ""
