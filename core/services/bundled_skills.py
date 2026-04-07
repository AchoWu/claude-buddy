"""
Bundled Skills — CC-aligned pre-packaged skill system.
CC: loads skills from .claude/skills/ directories, provides commit/review-pr/pdf etc.
"""

import json
from pathlib import Path
from typing import Any


class SkillDefinition:
    """A single bundled skill."""
    def __init__(self, name: str, description: str, prompt: str,
                 allowed_tools: list[str] | None = None):
        self.name = name
        self.description = description
        self.prompt = prompt  # The prompt template sent to Claude
        self.allowed_tools = allowed_tools  # Optional: restrict tools for this skill


# Built-in skills (CC-aligned)
BUILTIN_SKILLS = [
    SkillDefinition(
        name="commit",
        description="Create a git commit with proper message",
        prompt=(
            "Create a git commit for the current changes. Steps:\n"
            "1. Run `git status` and `git diff --staged` to see changes\n"
            "2. If nothing staged, run `git add` for relevant files\n"
            "3. Write a concise commit message (imperative, <72 chars)\n"
            "4. Run `git commit`"
        ),
        allowed_tools=["Bash", "FileRead"],
    ),
    SkillDefinition(
        name="review-pr",
        description="Review a GitHub pull request",
        prompt=(
            "Review the current PR. Steps:\n"
            "1. Run `gh pr view --json title,body,files` to get PR info\n"
            "2. Run `gh pr diff` to see the changes\n"
            "3. Provide a thorough review with specific feedback\n"
            "4. Note any issues, suggestions, or approvals"
        ),
        allowed_tools=["Bash", "FileRead", "Grep"],
    ),
    SkillDefinition(
        name="pdf",
        description="Read and summarize a PDF file",
        prompt=(
            "Read the specified PDF file and provide a summary.\n"
            "Use FileRead with the pages parameter for large PDFs."
        ),
        allowed_tools=["FileRead"],
    ),
    SkillDefinition(
        name="test",
        description="Run tests and fix failures",
        prompt=(
            "Run the project's test suite and fix any failures. Steps:\n"
            "1. Detect test framework (pytest/jest/go test/etc)\n"
            "2. Run tests\n"
            "3. If failures, read failing test files and source code\n"
            "4. Fix the issues\n"
            "5. Re-run tests to confirm fixes"
        ),
    ),
]


class BundledSkillManager:
    """Manages bundled and user-defined skills."""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._skills_dir = data_dir / "skills"
        self._skills: dict[str, SkillDefinition] = {}
        self._load_builtins()
        self._load_user_skills()

    def _load_builtins(self):
        for skill in BUILTIN_SKILLS:
            self._skills[skill.name] = skill

    def _load_user_skills(self):
        """Scan .buddy/skills/ for user-defined skill files."""
        if not self._skills_dir.exists():
            return
        for f in self._skills_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                skill = SkillDefinition(
                    name=data["name"],
                    description=data.get("description", ""),
                    prompt=data["prompt"],
                    allowed_tools=data.get("allowed_tools"),
                )
                self._skills[skill.name] = skill
            except Exception:
                pass
        # Also scan .claude/skills/ in CWD (CC pattern)
        import os
        for skills_dir in [Path(os.getcwd()) / ".claude" / "skills",
                           Path(os.getcwd()) / ".buddy" / "skills"]:
            if skills_dir.exists():
                for f in skills_dir.glob("*.md"):
                    try:
                        content = f.read_text(encoding="utf-8")
                        skill = SkillDefinition(
                            name=f.stem,
                            description=f"Skill from {f.parent.name}/{f.name}",
                            prompt=content,
                        )
                        self._skills[skill.name] = skill
                    except Exception:
                        pass

    def get(self, name: str) -> SkillDefinition | None:
        return self._skills.get(name)

    def list_skills(self) -> list[dict]:
        return [
            {"name": s.name, "description": s.description,
             "has_tool_restrictions": s.allowed_tools is not None}
            for s in self._skills.values()
        ]

    def reload(self):
        """Reload user skills from disk."""
        self._skills.clear()
        self._load_builtins()
        self._load_user_skills()
