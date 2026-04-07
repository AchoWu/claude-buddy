"""
Glob Tool — file pattern search using pathlib.
"""

from pathlib import Path
from tools.base import BaseTool


class GlobTool(BaseTool):
    name = "Glob"
    description = (
        "Search for files matching a glob pattern.\n\n"
        "Use this tool to find files. NEVER use Bash with find/ls/dir.\n\n"
        "Examples:\n"
        "- '**/*.py' — all Python files recursively\n"
        "- 'src/**/*.ts' — all TypeScript files under src/\n"
        "- '*.json' — JSON files in current directory only\n"
        "- '**/test_*.py' — all test files\n\n"
        "Features:\n"
        "- Returns matching file paths sorted by modification time (newest first)\n"
        "- Supports an optional path parameter to search in a specific directory\n"
        "- Returns up to 200 results\n\n"
        "REMINDER: NEVER use Bash (find, ls, dir) to search for files. Always use Glob."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Glob pattern to match files (e.g., '**/*.py')",
            },
            "path": {
                "type": "string",
                "description": "Directory to search in (default: current directory)",
            },
        },
        "required": ["pattern"],
    }
    is_read_only = True

    def execute(self, input_data: dict) -> str:
        pattern = input_data["pattern"]
        search_dir = Path(input_data.get("path", ".")).resolve()

        if not search_dir.exists():
            return f"Error: Directory not found: {search_dir}"

        try:
            matches = sorted(
                search_dir.glob(pattern),
                key=lambda p: p.stat().st_mtime if p.exists() else 0,
                reverse=True,
            )

            if not matches:
                return f"No files matching '{pattern}' in {search_dir}"

            # Limit output
            MAX_RESULTS = 200
            lines = [str(p) for p in matches[:MAX_RESULTS]]
            result = "\n".join(lines)

            if len(matches) > MAX_RESULTS:
                result += f"\n... and {len(matches) - MAX_RESULTS} more files"

            return result

        except Exception as e:
            return f"Error: {e}"
