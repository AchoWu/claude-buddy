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
        "Launch a new agent to handle complex, multi-step tasks autonomously.\n\n"
        "The Agent tool launches sub-agents that autonomously handle complex tasks. "
        "Each agent operates in a fresh, isolated conversation with access to the same tools.\n\n"
        "## When to use\n"
        "- Open-ended codebase exploration: searching across many files, understanding architecture\n"
        "- Complex multi-step research requiring many tool calls (5+)\n"
        "- Parallel exploration of alternative approaches — launch multiple agents in one message\n"
        "- Tasks where intermediate tool output would clutter the main conversation\n"
        "- Gathering information from multiple sources before synthesizing\n"
        "- When you are doing an open-ended search that may require multiple rounds of "
        "globbing and grepping, use an Agent instead of doing it yourself\n\n"
        "## When NOT to use\n"
        "- If you want to read a specific file path, use FileRead directly\n"
        "- If you are searching for a specific class/function definition, use Grep directly\n"
        "- If you are searching code within 2-3 specific files, use FileRead directly\n"
        "- Simple single-step operations — just call the tool directly\n"
        "- When the result needs to immediately feed into your current reasoning "
        "with full parent context (sub-agents start fresh)\n\n"
        "## Usage notes\n"
        "- Always include a short description (3-5 words) summarizing what the agent will do\n"
        "- Launch multiple agents concurrently whenever possible — use a single message "
        "with multiple Agent tool calls for parallel exploration\n"
        "- The agent's final text answer is returned to you. It is NOT visible to the user. "
        "You must send a text message summarizing the result.\n"
        "- Clearly tell the agent whether you expect it to write code or just do research\n"
        "- Brief the agent like a smart colleague who just walked into the room — "
        "it hasn't seen this conversation, doesn't know what you've tried\n"
        "- Include file paths, line numbers, constraints explicitly in the prompt\n"
        "- Terse command-style prompts produce shallow, generic work\n\n"
        "**Never delegate understanding.** Don't write 'based on your findings, fix the bug'. "
        "Write prompts that prove you understood: include file paths, what specifically to change.\n\n"
        "## Options\n"
        "- model: override model (sonnet/opus/haiku). Default: same as parent.\n"
        "- isolation: 'worktree' to run in a temporary git worktree.\n"
        "- run_in_background: true to run async, you'll be notified when done."
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
