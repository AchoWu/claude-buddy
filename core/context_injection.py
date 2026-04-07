"""
Context Injection — memoized dynamic context collection.
Aligned with Claude Code's context.ts patterns:
- Parallel I/O for git status, branch, project detection
- Cache for conversation duration (memoized)
- Explicit invalidation on signal

Collects:
  - Git: branch, status, recent log
  - Project: type detection (Python, Node, Rust, etc.)
  - CLAUDE.md / README project instructions
"""

import os
import subprocess
import platform
import time
from pathlib import Path
from functools import lru_cache
from typing import Any


# Cache duration: context stays fresh for this many seconds
_CACHE_TTL_SEC = 120

# Module-level cache
_context_cache: dict[str, Any] = {}
_cache_timestamp: float = 0.0


def collect_context(cwd: str | None = None, force_refresh: bool = False) -> dict[str, str]:
    """
    Collect dynamic context for system prompt injection.
    Results are cached for CACHE_TTL_SEC seconds.

    Returns dict with keys like:
      - git_branch, git_status, git_log
      - project_type, project_files
      - claude_md
    """
    global _context_cache, _cache_timestamp

    now = time.time()
    if not force_refresh and _context_cache and (now - _cache_timestamp) < _CACHE_TTL_SEC:
        return _context_cache

    effective_cwd = cwd or os.getcwd()
    ctx: dict[str, str] = {}

    # Collect all context (each collector is safe — returns empty on failure)
    _collect_git_context(effective_cwd, ctx)
    _collect_project_context(effective_cwd, ctx)
    _collect_claude_md(effective_cwd, ctx)

    _context_cache = ctx
    _cache_timestamp = now
    return ctx


def invalidate_cache():
    """Force context refresh on next call."""
    global _context_cache, _cache_timestamp
    _context_cache = {}
    _cache_timestamp = 0.0


# ── Git Context ──────────────────────────────────────────────────────

def _collect_git_context(cwd: str, ctx: dict[str, str]):
    """Collect git branch, status, and recent log."""
    try:
        # Check if we're in a git repo
        result = _run_cmd(["git", "rev-parse", "--is-inside-work-tree"], cwd=cwd)
        if result != "true":
            return

        # Branch name
        branch = _run_cmd(["git", "branch", "--show-current"], cwd=cwd)
        if branch:
            ctx["git_branch"] = branch

        # Short status (max 10 lines to save tokens)
        status = _run_cmd(["git", "status", "--short"], cwd=cwd)
        if status:
            lines = status.splitlines()
            if len(lines) > 10:
                ctx["git_status"] = "\n".join(lines[:10]) + f"\n... (+{len(lines)-10} more)"
            else:
                ctx["git_status"] = status

        # Recent log (last 3 commits, one-line format)
        log = _run_cmd(
            ["git", "log", "--oneline", "-3", "--no-decorate"],
            cwd=cwd,
        )
        if log:
            ctx["git_log"] = log

    except Exception:
        pass  # git context is best-effort


# ── Project Context ──────────────────────────────────────────────────

# Project type detection: file → type label
_PROJECT_MARKERS = {
    "package.json": "Node.js",
    "requirements.txt": "Python",
    "Pipfile": "Python (Pipenv)",
    "pyproject.toml": "Python",
    "setup.py": "Python",
    "Cargo.toml": "Rust",
    "go.mod": "Go",
    "pom.xml": "Java (Maven)",
    "build.gradle": "Java (Gradle)",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "CMakeLists.txt": "C/C++ (CMake)",
    "Makefile": "Make-based project",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "tsconfig.json": "TypeScript",
}


def _collect_project_context(cwd: str, ctx: dict[str, str]):
    """Detect project type and key files."""
    try:
        cwd_path = Path(cwd)
        detected_types = []
        key_files = []

        for marker_file, proj_type in _PROJECT_MARKERS.items():
            if (cwd_path / marker_file).exists():
                detected_types.append(proj_type)
                key_files.append(marker_file)

        if detected_types:
            ctx["project_type"] = ", ".join(detected_types[:3])
        if key_files:
            ctx["project_files"] = ", ".join(key_files[:5])

    except Exception:
        pass


# ── CLAUDE.md / Project Instructions ─────────────────────────────────

_INSTRUCTION_FILENAMES = [
    "CLAUDE.md",
    ".claude/CLAUDE.md",
    "BUDDY.md",
    ".buddy/instructions.md",
]

# Max chars per file to prevent context window bloat
_MAX_INSTRUCTION_CHARS = 8000
# Max total chars across all merged CLAUDE.md files
_MAX_TOTAL_INSTRUCTION_CHARS = 15000


def _collect_claude_md(cwd: str, ctx: dict[str, str]):
    """
    CC-aligned multi-level CLAUDE.md discovery.
    Search order (all found are merged, not first-match):
      1. CWD and parent directories (walk up to root)
      2. ~/.claude-buddy/CLAUDE.md (user global instructions)
    Each file's content is processed for @include directives.
    """
    found_parts: list[str] = []
    seen_paths: set[str] = set()

    try:
        # ── Walk CWD → root looking for instruction files ──
        current = Path(cwd).resolve()
        root = current.anchor  # e.g. "/" or "C:\\"

        while True:
            for filename in _INSTRUCTION_FILENAMES:
                filepath = current / filename
                if filepath.is_file():
                    real = str(filepath.resolve())
                    if real not in seen_paths:
                        seen_paths.add(real)
                        content = _read_instruction_file(filepath, seen_paths)
                        if content:
                            found_parts.append(content)

            parent = current.parent
            if parent == current:
                break  # reached root
            current = parent

        # ── User global: ~/.claude-buddy/CLAUDE.md ──
        from config import DATA_DIR
        global_file = DATA_DIR / "CLAUDE.md"
        if global_file.is_file():
            real = str(global_file.resolve())
            if real not in seen_paths:
                seen_paths.add(real)
                content = _read_instruction_file(global_file, seen_paths)
                if content:
                    found_parts.append(content)

    except Exception:
        pass

    if found_parts:
        merged = "\n\n---\n\n".join(found_parts)
        if len(merged) > _MAX_TOTAL_INSTRUCTION_CHARS:
            merged = merged[:_MAX_TOTAL_INSTRUCTION_CHARS] + "\n... (truncated)"
        ctx["claude_md"] = merged


def _read_instruction_file(filepath: Path, seen_paths: set[str]) -> str | None:
    """Read file content with @include directive support and circular ref prevention."""
    try:
        # Add self to seen_paths to prevent circular @include
        real = str(filepath.resolve())
        seen_paths.add(real)

        raw = filepath.read_text(encoding="utf-8", errors="replace")
        if len(raw) > _MAX_INSTRUCTION_CHARS:
            raw = raw[:_MAX_INSTRUCTION_CHARS] + "\n... (truncated)"

        # Process @include directives
        lines = raw.splitlines()
        result_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("@include "):
                include_path = stripped[9:].strip().strip('"').strip("'")
                _process_include(filepath.parent, include_path, seen_paths, result_lines)
            else:
                result_lines.append(line)

        content = "\n".join(result_lines).strip()
        return content if content else None
    except Exception:
        return None


def _process_include(base_dir: Path, include_path: str, seen_paths: set[str],
                     result_lines: list[str]):
    """Resolve and inline an @include directive. Prevents circular references."""
    try:
        target = (base_dir / include_path).resolve()
        real = str(target)
        if real in seen_paths:
            result_lines.append(f"<!-- @include {include_path}: circular reference skipped -->")
            return
        if not target.is_file():
            result_lines.append(f"<!-- @include {include_path}: file not found -->")
            return

        # Recursively process (handles nested @include + circular protection)
        content = _read_instruction_file(target, seen_paths)
        if content:
            result_lines.append(content)
    except Exception:
        result_lines.append(f"<!-- @include {include_path}: read error -->")


# ── Helpers ──────────────────────────────────────────────────────────

def _run_cmd(cmd: list[str], cwd: str, timeout: int = 5) -> str:
    """Run a command and return stdout, or empty string on failure."""
    try:
        is_windows = platform.system() == "Windows"
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            # Avoid console window on Windows
            creationflags=subprocess.CREATE_NO_WINDOW if is_windows else 0,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return ""
