"""
Worktree Tools — git worktree session management.
Aligned with Claude Code's EnterWorktreeTool / ExitWorktreeTool.
"""

import os
import subprocess
import platform
from pathlib import Path
from tools.base import BaseTool


def _run_git(args: list[str], cwd: str) -> tuple[int, str, str]:
    """Run a git command and return (returncode, stdout, stderr)."""
    is_win = platform.system() == "Windows"
    try:
        r = subprocess.run(
            ["git"] + args, capture_output=True, text=True,
            timeout=15, cwd=cwd,
            creationflags=subprocess.CREATE_NO_WINDOW if is_win else 0,
        )
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


class EnterWorktreeTool(BaseTool):
    name = "EnterWorktree"
    description = (
        "Create a git worktree for isolated development.\n\n"
        "Creates a new worktree inside .claude/worktrees/ with a new branch\n"
        "based on the current HEAD. This gives you an isolated copy of the\n"
        "repository to work on without affecting the main working directory.\n\n"
        "Use for:\n"
        "- Parallel development on a separate branch\n"
        "- Testing changes in isolation\n"
        "- Working on a fix while keeping main branch clean\n\n"
        "Parameters:\n"
        "- name: Optional name for the worktree (random if omitted)"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Optional name for the worktree",
            },
        },
    }
    is_read_only = False

    def __init__(self):
        self._original_cwd: str | None = None
        self._worktree_path: str | None = None

    def execute(self, input_data: dict) -> str:
        import uuid

        name = input_data.get("name", "").strip()
        if not name:
            name = f"wt-{uuid.uuid4().hex[:8]}"

        cwd = os.getcwd()

        # Check if in a git repo
        rc, out, err = _run_git(["rev-parse", "--is-inside-work-tree"], cwd)
        if rc != 0:
            return "Error: Not in a git repository. Worktrees require git."

        # Get repo root
        rc, repo_root, _ = _run_git(["rev-parse", "--show-toplevel"], cwd)
        if rc != 0:
            return "Error: Could not find repository root."

        # Create worktree directory
        wt_dir = Path(repo_root) / ".claude" / "worktrees"
        wt_dir.mkdir(parents=True, exist_ok=True)
        wt_path = wt_dir / name

        if wt_path.exists():
            return f"Error: Worktree '{name}' already exists at {wt_path}"

        # Create branch and worktree
        branch_name = f"claude-buddy/{name}"
        rc, out, err = _run_git(
            ["worktree", "add", "-b", branch_name, str(wt_path)], repo_root
        )
        if rc != 0:
            return f"Error creating worktree: {err}"

        self._original_cwd = cwd
        self._worktree_path = str(wt_path)

        return (
            f"Worktree created:\n"
            f"  Path: {wt_path}\n"
            f"  Branch: {branch_name}\n"
            f"  Based on: HEAD\n\n"
            f"Use ExitWorktree to leave when done."
        )


class ExitWorktreeTool(BaseTool):
    name = "ExitWorktree"
    description = (
        "Exit a worktree session and optionally clean up.\n\n"
        "Parameters:\n"
        "- action: 'keep' (leave worktree on disk) or 'remove' (delete it)\n"
        "- worktree_path: Path to the worktree to exit (optional, uses current if omitted)"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["keep", "remove"],
                "description": "'keep' leaves worktree on disk, 'remove' deletes it",
            },
            "worktree_path": {
                "type": "string",
                "description": "Path to the worktree (optional)",
            },
        },
        "required": ["action"],
    }
    is_read_only = False

    def execute(self, input_data: dict) -> str:
        action = input_data.get("action", "keep")
        wt_path = input_data.get("worktree_path", "").strip()

        if not wt_path:
            # Try to detect current worktree
            cwd = os.getcwd()
            rc, out, _ = _run_git(["rev-parse", "--show-toplevel"], cwd)
            if rc == 0 and ".claude/worktrees/" in out.replace("\\", "/"):
                wt_path = out
            else:
                return "Error: Not currently in a worktree. Provide worktree_path."

        if action == "keep":
            return f"Worktree kept at: {wt_path}\nYou can return to it later."

        if action == "remove":
            # Check for uncommitted changes
            rc, status, _ = _run_git(["status", "--porcelain"], wt_path)
            if status.strip():
                return (
                    f"Worktree has uncommitted changes:\n{status}\n"
                    f"Commit or stash changes first, or use action='keep'."
                )

            # Get repo root (parent of worktree)
            rc, repo_root, _ = _run_git(["rev-parse", "--show-toplevel"], wt_path)

            # Find the worktree's repo root (the main repo)
            rc2, main_root, _ = _run_git(
                ["worktree", "list", "--porcelain"], wt_path
            )

            # Remove worktree
            rc, out, err = _run_git(["worktree", "remove", wt_path], repo_root)
            if rc != 0:
                # Force remove
                rc, out, err = _run_git(
                    ["worktree", "remove", "--force", wt_path], repo_root
                )
                if rc != 0:
                    return f"Error removing worktree: {err}"

            return f"Worktree removed: {wt_path}"

        return f"Error: Unknown action '{action}'. Use 'keep' or 'remove'."
