"""
MCP Server Approval — CC-aligned user approval for new MCP servers.
CC: mcpServerApproval service prompts user before connecting to unknown servers.
"""

import json
from pathlib import Path
from typing import Callable, Optional


class McpServerApproval:
    """Track approval status of MCP servers."""

    def __init__(self, data_dir: Path):
        self._data_dir = data_dir
        self._approvals_path = data_dir / "mcp_approvals.json"
        self._approvals: dict[str, bool] = self._load()

    def is_approved(self, server_name: str) -> Optional[bool]:
        """Check if server is approved. None = not yet decided."""
        return self._approvals.get(server_name)

    def approve(self, server_name: str):
        """Mark server as approved."""
        self._approvals[server_name] = True
        self._save()

    def deny(self, server_name: str):
        """Mark server as denied."""
        self._approvals[server_name] = False
        self._save()

    def revoke(self, server_name: str):
        """Remove approval decision (will prompt again)."""
        self._approvals.pop(server_name, None)
        self._save()

    def check_and_prompt(
        self,
        server_name: str,
        server_config: dict,
        prompt_fn: Callable[[str, dict], bool] | None = None,
    ) -> bool:
        """
        CC-aligned: check approval, prompt user if unknown.
        Returns True if approved, False if denied.
        """
        status = self.is_approved(server_name)
        if status is True:
            return True
        if status is False:
            return False

        # Unknown — prompt user
        if prompt_fn:
            command = server_config.get("command", "?")
            args = server_config.get("args", [])
            desc = f"MCP server '{server_name}' wants to connect.\n"
            desc += f"  Command: {command} {' '.join(str(a) for a in args)}\n"
            desc += "Allow this server?"
            approved = prompt_fn(server_name, {"description": desc})
            if approved:
                self.approve(server_name)
            else:
                self.deny(server_name)
            return approved

        # No prompt function — deny by default (safe)
        return False

    def list_approvals(self) -> dict[str, bool]:
        return dict(self._approvals)

    def _load(self) -> dict[str, bool]:
        if self._approvals_path.exists():
            try:
                return json.loads(self._approvals_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save(self):
        self._data_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._approvals_path.write_text(
                json.dumps(self._approvals, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
