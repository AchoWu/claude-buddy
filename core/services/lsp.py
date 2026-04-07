"""
LSP Manager — Language Server Protocol client for code intelligence.
Aligned with Claude Code's services/lsp/ patterns.

Provides:
  - Language server connection management
  - File change notifications (didOpen, didChange, didSave)
  - Diagnostics collection (errors, warnings)
  - Hover information and go-to-definition
  - Code completion (future)

This is an extensible scaffold. Full LSP implementation requires
a real LSP client library (e.g., pygls), but the interface is
designed to be provider-agnostic.
"""

import subprocess
import json
import os
import platform
from pathlib import Path
from typing import Any, Optional


class LSPDiagnostic:
    """A single diagnostic from a language server."""
    def __init__(self, file_path: str, line: int, col: int, message: str,
                 severity: str = "error", source: str = ""):
        self.file_path = file_path
        self.line = line
        self.col = col
        self.message = message
        self.severity = severity  # "error", "warning", "info", "hint"
        self.source = source

    def __str__(self):
        return f"{self.file_path}:{self.line}:{self.col}: {self.severity}: {self.message}"


class LSPServer:
    """Represents a connected language server."""
    def __init__(self, name: str, command: list[str], languages: list[str]):
        self.name = name
        self.command = command
        self.languages = languages
        self.process: subprocess.Popen | None = None
        self.capabilities: dict = {}

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


class LSPManager:
    """
    Manages language server connections and provides code intelligence.
    """

    # Known language servers (auto-detected)
    KNOWN_SERVERS = {
        "python": {
            "name": "pyright",
            "commands": [
                ["pyright-langserver", "--stdio"],
                ["pylsp"],
                ["python", "-m", "pylsp"],
            ],
            "languages": ["python"],
        },
        "typescript": {
            "name": "typescript-language-server",
            "commands": [
                ["typescript-language-server", "--stdio"],
                ["tsserver"],
            ],
            "languages": ["typescript", "javascript", "typescriptreact", "javascriptreact"],
        },
        "rust": {
            "name": "rust-analyzer",
            "commands": [["rust-analyzer"]],
            "languages": ["rust"],
        },
        "go": {
            "name": "gopls",
            "commands": [["gopls", "serve"]],
            "languages": ["go"],
        },
    }

    def __init__(self):
        self._servers: dict[str, LSPServer] = {}
        self._diagnostics: dict[str, list[LSPDiagnostic]] = {}  # file → diagnostics

    def detect_servers(self, cwd: str) -> list[str]:
        """Auto-detect available language servers based on project files."""
        import shutil
        cwd_path = Path(cwd)
        detected = []

        for lang, config in self.KNOWN_SERVERS.items():
            # Check if project has files of this language
            extensions = {
                "python": [".py"], "typescript": [".ts", ".tsx", ".js", ".jsx"],
                "rust": [".rs"], "go": [".go"],
            }
            has_files = any(
                list(cwd_path.glob(f"**/*{ext}"))[:1]
                for ext in extensions.get(lang, [])
            )
            if not has_files:
                continue

            # Check if any command is available
            for cmd in config["commands"]:
                if shutil.which(cmd[0]):
                    detected.append(lang)
                    break

        return detected

    def notify_file_changed(self, file_path: str):
        """Notify relevant servers that a file was changed."""
        # Stub: in full implementation, this sends didChange notification
        pass

    def notify_file_saved(self, file_path: str):
        """Notify relevant servers that a file was saved."""
        pass

    def get_diagnostics(self, file_path: str) -> list[LSPDiagnostic]:
        """Get cached diagnostics for a file."""
        return self._diagnostics.get(file_path, [])

    def get_all_diagnostics(self) -> dict[str, list[LSPDiagnostic]]:
        """Get all cached diagnostics."""
        return dict(self._diagnostics)

    def get_diagnostics_summary(self) -> str:
        """Get a human-readable summary of all diagnostics."""
        if not self._diagnostics:
            return "No diagnostics available."
        lines = ["Diagnostics:"]
        for file_path, diags in sorted(self._diagnostics.items()):
            errors = sum(1 for d in diags if d.severity == "error")
            warnings = sum(1 for d in diags if d.severity == "warning")
            if errors or warnings:
                lines.append(f"  {file_path}: {errors} errors, {warnings} warnings")
        return "\n".join(lines)

    def shutdown(self):
        """Shutdown all connected servers."""
        for server in self._servers.values():
            if server.process and server.process.poll() is None:
                try:
                    server.process.terminate()
                    server.process.wait(timeout=5)
                except Exception:
                    server.process.kill()
        self._servers.clear()
