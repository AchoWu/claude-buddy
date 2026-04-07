"""
Analytics + Feature Flags — local usage tracking and runtime configuration.
Aligned with Claude Code's services/analytics/ patterns.

Analytics: local-only usage telemetry (never uploaded).
  - API call counts, tool usage frequency, error rates
  - Session duration, compaction events
  - Daily JSON files in ~/.claude-buddy/analytics/

Feature Flags: JSON-driven runtime configuration.
  - Load from ~/.claude-buddy/features.json
  - Control experimental features without code changes
  - Type-safe access with defaults
"""

import json
import time
import os
from pathlib import Path
from datetime import date, datetime
from typing import Any
from collections import Counter

from config import DATA_DIR


# ═══════════════════════════════════════════════════════════════════
# Feature Flags
# ═══════════════════════════════════════════════════════════════════

FEATURES_FILE = DATA_DIR / "features.json"

# Defaults: used when key is missing from features.json
_DEFAULT_FLAGS = {
    "streaming_enabled": True,
    "bridge_enabled": False,
    "auto_memory_extract": True,
    "llm_compact_enabled": True,
    "reactive_compact": True,
    "plugin_system_enabled": True,
    "team_memory_enabled": True,
    "compact_warning_enabled": True,
    "max_tool_rounds": 30,
    "context_window_override": 0,     # 0 = use provider default
    "prompt_version": "v4",
}


class FeatureFlags:
    """
    Runtime feature flags loaded from a JSON config file.
    Falls back to defaults for missing keys.
    """

    def __init__(self, config_path: Path | None = None):
        self._path = config_path or FEATURES_FILE
        self._flags: dict[str, Any] = dict(_DEFAULT_FLAGS)
        self._load()

    def _load(self):
        """Load flags from disk, merging with defaults."""
        if not self._path.exists():
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                user_flags = json.load(f)
            if isinstance(user_flags, dict):
                self._flags.update(user_flags)
        except Exception:
            pass

    def reload(self):
        """Re-read from disk (for hot-reload)."""
        self._flags = dict(_DEFAULT_FLAGS)
        self._load()

    def is_enabled(self, key: str) -> bool:
        """Check if a boolean flag is enabled."""
        val = self._flags.get(key, False)
        return bool(val)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a flag value with optional default."""
        return self._flags.get(key, default)

    def get_int(self, key: str, default: int = 0) -> int:
        """Get an integer flag."""
        try:
            return int(self._flags.get(key, default))
        except (ValueError, TypeError):
            return default

    def set(self, key: str, value: Any):
        """Set a flag and persist to disk."""
        self._flags[key] = value
        self._save()

    def _save(self):
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._flags, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def all_flags(self) -> dict[str, Any]:
        return dict(self._flags)

    def format_status(self) -> str:
        lines = ["Feature flags:"]
        for k, v in sorted(self._flags.items()):
            if isinstance(v, bool):
                icon = "[ON]" if v else "[OFF]"
            else:
                icon = f"= {v}"
            lines.append(f"  {k:30s} {icon}")
        return "\n".join(lines)


# Module-level singleton
_feature_flags: FeatureFlags | None = None

def get_feature_flags() -> FeatureFlags:
    global _feature_flags
    if _feature_flags is None:
        _feature_flags = FeatureFlags()
    return _feature_flags


# ═══════════════════════════════════════════════════════════════════
# Analytics (Local-Only Telemetry)
# ═══════════════════════════════════════════════════════════════════

ANALYTICS_DIR = DATA_DIR / "analytics"
ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)


class Analytics:
    """
    Local-only usage analytics. All data stays on disk.

    Tracks:
      - API calls (count, input/output tokens)
      - Tool usage (per-tool call counts)
      - Errors (count, types)
      - Session info (start time, duration)
      - Compaction events
    """

    def __init__(self, analytics_dir: Path | None = None):
        self._dir = analytics_dir or ANALYTICS_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._session_start = time.time()
        self._today = date.today().isoformat()

        # In-memory counters (flushed to disk periodically)
        self._api_calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._tool_calls: Counter = Counter()
        self._errors: Counter = Counter()  # error_type → count
        self._compactions = 0
        self._commands: Counter = Counter()

    # ── Recording ─────────────────────────────────────────────────

    def record_api_call(self, model: str = "", input_tokens: int = 0, output_tokens: int = 0):
        self._api_calls += 1
        self._input_tokens += input_tokens
        self._output_tokens += output_tokens

    def record_tool_call(self, tool_name: str):
        self._tool_calls[tool_name] += 1

    def record_error(self, error_type: str):
        self._errors[error_type] += 1

    def record_compaction(self):
        self._compactions += 1

    def record_command(self, command: str):
        self._commands[command] += 1

    # ── Queries ───────────────────────────────────────────────────

    @property
    def session_duration_minutes(self) -> float:
        return (time.time() - self._session_start) / 60

    @property
    def total_api_calls(self) -> int:
        return self._api_calls

    @property
    def total_tool_calls(self) -> int:
        return sum(self._tool_calls.values())

    @property
    def total_errors(self) -> int:
        return sum(self._errors.values())

    @property
    def error_rate(self) -> float:
        total = self._api_calls + self.total_tool_calls
        if total == 0:
            return 0.0
        return self.total_errors / total

    def top_tools(self, n: int = 5) -> list[tuple[str, int]]:
        return self._tool_calls.most_common(n)

    def format_report(self, title: str = "Usage Statistics") -> str:
        """Format a human-readable statistics report."""
        duration = self.session_duration_minutes

        lines = [
            f"{title} (session: {duration:.0f} min):",
            "",
            f"  API calls:     {self._api_calls}",
            f"  Input tokens:  ~{self._input_tokens:,}",
            f"  Output tokens: ~{self._output_tokens:,}",
            "",
            f"  Tool calls:    {self.total_tool_calls}",
        ]

        top = self.top_tools(8)
        if top:
            tool_str = ", ".join(f"{name} ({count})" for name, count in top)
            lines.append(f"  Top tools:     {tool_str}")

        lines.extend([
            "",
            f"  Errors:        {self.total_errors} ({self.error_rate:.1%} rate)",
        ])

        if self._errors:
            for err_type, count in self._errors.most_common(3):
                lines.append(f"    {err_type}: {count}")

        lines.extend([
            "",
            f"  Compactions:   {self._compactions}",
        ])

        if self._commands:
            cmd_str = ", ".join(f"{c} ({n})" for c, n in self._commands.most_common(5))
            lines.append(f"  Commands:      {cmd_str}")

        return "\n".join(lines)

    # ── Persistence ───────────────────────────────────────────────

    def flush(self):
        """Write current stats to today's JSON file (append/merge)."""
        today = date.today().isoformat()
        path = self._dir / f"{today}.json"

        # Load existing data for today
        existing = {}
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}

        # Merge counters
        data = {
            "date": today,
            "api_calls": existing.get("api_calls", 0) + self._api_calls,
            "input_tokens": existing.get("input_tokens", 0) + self._input_tokens,
            "output_tokens": existing.get("output_tokens", 0) + self._output_tokens,
            "tool_calls": self._merge_counters(
                existing.get("tool_calls", {}), dict(self._tool_calls)
            ),
            "errors": self._merge_counters(
                existing.get("errors", {}), dict(self._errors)
            ),
            "compactions": existing.get("compactions", 0) + self._compactions,
            "commands": self._merge_counters(
                existing.get("commands", {}), dict(self._commands)
            ),
            "session_minutes": existing.get("session_minutes", 0) + self.session_duration_minutes,
            "last_flush": time.time(),
        }

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

        # Reset counters after flush
        self._api_calls = 0
        self._input_tokens = 0
        self._output_tokens = 0
        self._tool_calls.clear()
        self._errors.clear()
        self._compactions = 0
        self._commands.clear()

    def load_report(self, days: int = 7) -> str:
        """Load and format a report for the last N days."""
        total_api = 0
        total_input = 0
        total_output = 0
        total_tools: Counter = Counter()
        total_errors: Counter = Counter()
        total_compactions = 0
        total_minutes = 0.0
        total_commands: Counter = Counter()

        today = date.today()
        for i in range(days):
            from datetime import timedelta
            day = (today - timedelta(days=i)).isoformat()
            path = self._dir / f"{day}.json"
            if not path.exists():
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                total_api += data.get("api_calls", 0)
                total_input += data.get("input_tokens", 0)
                total_output += data.get("output_tokens", 0)
                total_tools.update(data.get("tool_calls", {}))
                total_errors.update(data.get("errors", {}))
                total_compactions += data.get("compactions", 0)
                total_minutes += data.get("session_minutes", 0)
                total_commands.update(data.get("commands", {}))
            except Exception:
                continue

        if total_api == 0 and not total_tools:
            return f"No analytics data for the last {days} days."

        lines = [
            f"Usage Report (last {days} days):",
            "",
            f"  API calls:     {total_api}",
            f"  Input tokens:  ~{total_input:,}",
            f"  Output tokens: ~{total_output:,}",
            f"  Total time:    {total_minutes:.0f} min",
            "",
            f"  Tool calls:    {sum(total_tools.values())}",
        ]
        top = total_tools.most_common(8)
        if top:
            lines.append(f"  Top tools:     {', '.join(f'{n} ({c})' for n, c in top)}")

        err_total = sum(total_errors.values())
        lines.append(f"\n  Errors:        {err_total}")
        lines.append(f"  Compactions:   {total_compactions}")

        return "\n".join(lines)

    @staticmethod
    def _merge_counters(existing: dict, new: dict) -> dict:
        merged = dict(existing)
        for k, v in new.items():
            merged[k] = merged.get(k, 0) + v
        return merged


# Module-level singleton
_analytics: Analytics | None = None

def get_analytics() -> Analytics:
    global _analytics
    if _analytics is None:
        _analytics = Analytics()
    return _analytics
