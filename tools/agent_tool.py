"""
Agent Tool v2 — CC-aligned enhancements:
  - model override parameter (sonnet/opus/haiku)
  - worktree isolation mode
  - Parent context injection (via engine.run_sub_agent)
"""

from __future__ import annotations

import traceback
from typing import Any, Optional

from tools.base import BaseTool


class AgentTool(BaseTool):
    """Spawn a sub-agent that runs a task in an isolated conversation context.

    CC-aligned features:
    - model: override the model used by the sub-agent
    - isolation: "worktree" creates a temporary git worktree for the sub-agent
    - Parent context injection via engine.run_sub_agent (last 20 messages)
    """

    name = "Agent"
    description = (
        "Spawn a sub-agent to handle a complex task in an isolated context.\n\n"
        "## When to use\n"
        "- Complex multi-step research that requires several tool calls\n"
        "- Parallel exploration of alternative approaches or solutions\n"
        "- Tasks where intermediate reasoning would clutter the main conversation\n"
        "- Gathering information from multiple sources before synthesizing\n\n"
        "## When NOT to use\n"
        "- Simple single-step operations (just call the tool directly)\n"
        "- When the result needs to immediately feed into the current reasoning\n"
        "  with full context — the sub-agent does NOT see the parent conversation\n"
        "- Trivial file reads, greps, or one-off shell commands\n\n"
        "The sub-agent returns its final text answer.  It has access to the\n"
        "same tools but operates in a fresh, isolated conversation.\n\n"
        "Options:\n"
        "- model: override model (sonnet/opus/haiku). Default: same as parent.\n"
        "- isolation: 'worktree' to run in a temporary git worktree."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": (
                    "A short label (3-5 words) summarising what the sub-agent "
                    "will do. Shown in progress indicators."
                ),
            },
            "prompt": {
                "type": "string",
                "description": (
                    "The full task description / question for the sub-agent. "
                    "Be specific — the sub-agent has NO access to the parent "
                    "conversation history."
                ),
            },
            "model": {
                "type": "string",
                "enum": ["sonnet", "opus", "haiku"],
                "description": (
                    "Optional model override. 'sonnet' for balance, 'opus' for "
                    "complex reasoning, 'haiku' for fast/cheap tasks. "
                    "Default: same model as parent."
                ),
            },
            "isolation": {
                "type": "string",
                "enum": ["worktree"],
                "description": (
                    "Set to 'worktree' to run the sub-agent in a temporary "
                    "git worktree, giving it an isolated copy of the repository."
                ),
            },
            "run_in_background": {
                "type": "boolean",
                "description": "Run in background and return task_id immediately.",
                "default": False,
            },
        },
        "required": ["description", "prompt"],
    }
    is_read_only = True  # launching is non-destructive; sub-agent has own perms

    # Injected by ToolRegistry
    _engine: Optional[Any] = None

    def execute(self, input_data: dict) -> str:
        if self._engine is None:
            return (
                "Error: AgentTool has no engine reference. "
                "The query engine must be injected as `_engine` before use."
            )

        description: str = input_data.get("description", "sub-agent task")
        prompt: str = input_data.get("prompt", "")
        model_override: str = input_data.get("model", "")
        isolation: str = input_data.get("isolation", "")
        run_bg: bool = input_data.get("run_in_background", False)

        if not prompt.strip():
            return "Error: prompt must be a non-empty string."

        # Build system prompt
        system_prompt = (
            "You are a sub-agent spawned to handle a focused task.\n"
            f"Task label: {description}\n\n"
            "Instructions:\n"
            "- Complete the task described in the user message below.\n"
            "- Use the available tools as needed.\n"
            "- When finished, reply with a concise summary of your findings or "
            "the result of the task.\n"
            "- Do NOT ask follow-up questions — make reasonable assumptions.\n"
            "- Keep your final answer focused and relevant."
        )

        # CC-aligned: worktree isolation
        original_cwd = None
        worktree_path = None
        if isolation == "worktree":
            worktree_path, original_cwd = self._setup_worktree(description)
            if worktree_path:
                system_prompt += (
                    f"\n\nYou are running in an isolated git worktree: {worktree_path}\n"
                    "Do NOT cd to the original repository root."
                )

        try:
            # CC-aligned: background execution
            if run_bg and hasattr(self._engine, 'start_background_task'):
                def _bg_agent(inp):
                    return self._engine.run_sub_agent(
                        system_prompt=system_prompt,
                        user_prompt=prompt,
                        agent_id=f"agent_{description[:20]}",
                        model_override=model_override or None,
                    )
                task_id = self._engine.start_background_task(_bg_agent, {})
                return f"Sub-agent started in background. Task ID: {task_id}"

            result = self._engine.run_sub_agent(
                system_prompt=system_prompt,
                user_prompt=prompt,
                agent_id=f"agent_{description[:20]}",
                model_override=model_override or None,
            )
            return result if result else "(sub-agent returned empty response)"

        except Exception as exc:
            tb = traceback.format_exc()
            return f"Error running sub-agent: {exc}\n{tb}"
        finally:
            # Cleanup worktree
            if worktree_path and original_cwd:
                self._cleanup_worktree(worktree_path, original_cwd)

    def _setup_worktree(self, name: str) -> tuple[str | None, str | None]:
        """CC-aligned: create a temporary git worktree."""
        import subprocess, os, tempfile
        try:
            # Check if we're in a git repo
            subprocess.run(["git", "rev-parse", "--git-dir"],
                           capture_output=True, check=True, timeout=5)

            original_cwd = os.getcwd()
            safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name[:30])
            worktree_dir = os.path.join(
                os.path.expanduser("~"), ".claude-buddy", "worktrees", safe_name
            )
            os.makedirs(os.path.dirname(worktree_dir), exist_ok=True)

            # Create worktree with new branch
            branch_name = f"buddy-agent-{safe_name}"
            subprocess.run(
                ["git", "worktree", "add", "-b", branch_name, worktree_dir, "HEAD"],
                capture_output=True, check=True, timeout=30,
            )
            os.chdir(worktree_dir)
            return worktree_dir, original_cwd

        except Exception:
            return None, None

    def _cleanup_worktree(self, worktree_path: str, original_cwd: str):
        """Remove temporary worktree."""
        import subprocess, os, shutil
        try:
            os.chdir(original_cwd)
            subprocess.run(
                ["git", "worktree", "remove", "--force", worktree_path],
                capture_output=True, timeout=10,
            )
        except Exception:
            # Fallback: just delete the directory
            try:
                shutil.rmtree(worktree_path, ignore_errors=True)
            except Exception:
                pass
