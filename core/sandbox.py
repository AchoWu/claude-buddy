"""
Sandbox System — filesystem and network access control.
Aligned with Claude Code's sandbox patterns.

Provides:
  - Path-based filesystem restrictions (allowed/denied directories)
  - Command safety classification
  - Network restriction awareness
  - Integration with permission system
"""

import os
import re
from pathlib import Path
from typing import Optional
from enum import Enum


class AccessLevel(Enum):
    ALLOWED = "allowed"
    DENIED = "denied"
    ASK = "ask"  # needs user confirmation


class CommandRisk(Enum):
    SAFE = "safe"             # read-only, no side effects
    MODERATE = "moderate"     # writes to files, installs packages
    DANGEROUS = "dangerous"   # destructive, irreversible
    BLOCKED = "blocked"       # never allow


class Sandbox:
    """
    Filesystem and command sandbox.

    Config priority (highest to lowest):
      1. Explicit deny rules
      2. Explicit allow rules
      3. Default policy (ask)
    """

    # System paths that should always be denied
    SYSTEM_DENY_PATHS = [
        "/etc", "/usr/bin", "/usr/sbin", "/boot", "/sys", "/proc",
        "C:\\Windows", "C:\\Program Files", "C:\\ProgramData",
    ]

    # Sensitive file patterns
    SENSITIVE_PATTERNS = [
        r"\.env$", r"\.env\.\w+$",
        r"credentials\.\w+$", r"secrets?\.\w+$",
        r"\.pem$", r"\.key$", r"\.p12$", r"\.pfx$",
        r"id_rsa", r"id_ed25519", r"\.ssh/",
        r"\.aws/credentials", r"\.gcloud/",
        r"token\.json$", r"auth\.json$",
    ]

    # Commands classified by risk
    COMMAND_RISK = {
        # SAFE: read-only
        "safe": {
            "git status", "git log", "git diff", "git branch",
            "git show", "git blame", "git remote -v",
            "ls", "dir", "pwd", "cd", "echo", "whoami", "hostname",
            "python --version", "node --version", "pip --version",
            "npm --version", "rustc --version", "go version",
            "cat", "head", "tail", "wc", "file", "stat", "which",
        },
        # MODERATE: writes/installs
        "moderate": {
            "git add", "git commit", "git stash", "git checkout",
            "pip install", "npm install", "yarn add", "cargo build",
            "make", "cmake", "go build", "python", "node", "npx",
            "mkdir", "touch", "cp", "mv",
        },
        # DANGEROUS: destructive
        "dangerous": {
            "git reset", "git push --force", "git clean",
            "git branch -D", "git rebase",
            "rm", "rmdir", "del", "rd",
            "chmod", "chown", "sudo",
            "docker rm", "docker rmi", "docker system prune",
            "pip uninstall", "npm uninstall",
        },
        # BLOCKED: never allow
        "blocked": {
            "rm -rf /", "mkfs", "dd if=", ":(){:|:&};:",
            "format c:", "shutdown", "reboot", "halt",
            "> /dev/sda", "chmod -R 777 /",
        },
    }

    def __init__(self):
        self._allow_paths: list[str] = []
        self._deny_paths: list[str] = list(self.SYSTEM_DENY_PATHS)
        self._allow_commands: list[str] = []
        self._deny_commands: list[str] = []

    def set_workspace(self, cwd: str):
        """Set the current workspace as an allowed path."""
        resolved = str(Path(cwd).resolve())
        if resolved not in self._allow_paths:
            self._allow_paths.insert(0, resolved)

    def add_allow_path(self, path: str):
        resolved = str(Path(path).resolve())
        if resolved not in self._allow_paths:
            self._allow_paths.append(resolved)

    def add_deny_path(self, path: str):
        resolved = str(Path(path).resolve())
        if resolved not in self._deny_paths:
            self._deny_paths.append(resolved)

    # ── Filesystem Access Checks ──────────────────────────────────

    def check_path(self, file_path: str) -> AccessLevel:
        """Check if a file path is allowed, denied, or needs confirmation."""
        resolved = str(Path(file_path).resolve())

        # 1. Check explicit deny
        for deny in self._deny_paths:
            if resolved.startswith(deny) or resolved == deny:
                return AccessLevel.DENIED

        # 2. Check sensitive patterns
        for pattern in self.SENSITIVE_PATTERNS:
            if re.search(pattern, resolved, re.IGNORECASE):
                return AccessLevel.ASK

        # 3. Check explicit allow
        for allow in self._allow_paths:
            if resolved.startswith(allow) or resolved == allow:
                return AccessLevel.ALLOWED

        # 4. Default: ask
        return AccessLevel.ASK

    def is_path_allowed(self, file_path: str) -> bool:
        return self.check_path(file_path) == AccessLevel.ALLOWED

    def is_path_denied(self, file_path: str) -> bool:
        return self.check_path(file_path) == AccessLevel.DENIED

    def is_sensitive_file(self, file_path: str) -> bool:
        for pattern in self.SENSITIVE_PATTERNS:
            if re.search(pattern, str(file_path), re.IGNORECASE):
                return True
        return False

    # ── Command Risk Classification ───────────────────────────────

    def classify_command(self, command: str) -> CommandRisk:
        """Classify a shell command by risk level."""
        cmd_lower = command.lower().strip()

        # Check blocked first
        for blocked in self.COMMAND_RISK["blocked"]:
            if blocked in cmd_lower:
                return CommandRisk.BLOCKED

        # Check dangerous
        for dangerous in self.COMMAND_RISK["dangerous"]:
            if cmd_lower.startswith(dangerous) or f" {dangerous}" in f" {cmd_lower}":
                return CommandRisk.DANGEROUS

        # Check safe
        for safe in self.COMMAND_RISK["safe"]:
            if cmd_lower.startswith(safe):
                return CommandRisk.SAFE

        # Check moderate
        for moderate in self.COMMAND_RISK["moderate"]:
            if cmd_lower.startswith(moderate) or f" {moderate}" in f" {cmd_lower}":
                return CommandRisk.MODERATE

        # Default: moderate (unknown commands need caution)
        return CommandRisk.MODERATE

    def is_command_safe(self, command: str) -> bool:
        return self.classify_command(command) == CommandRisk.SAFE

    def is_command_blocked(self, command: str) -> bool:
        return self.classify_command(command) == CommandRisk.BLOCKED

    # ── Summary ───────────────────────────────────────────────────

    def get_summary(self) -> str:
        lines = ["Sandbox configuration:"]
        if self._allow_paths:
            lines.append(f"  Allowed paths: {', '.join(self._allow_paths[:5])}")
        if self._deny_paths:
            lines.append(f"  Denied paths: {len(self._deny_paths)} rules")
        return "\n".join(lines)
