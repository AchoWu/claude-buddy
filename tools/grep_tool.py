"""
Grep Tool v2 — content search with output modes, context lines, pagination.
Aligned with Claude Code's GrepTool: 3 output modes, -A/-B/-C context,
head_limit+offset pagination, line numbers flag, multiline mode.
"""

import re
import subprocess
import shutil
from pathlib import Path
from tools.base import BaseTool


class GrepTool(BaseTool):
    name = "Grep"
    description = (
        "Search for a regex pattern in file contents.\n\n"
        "Use this tool to search inside files. NEVER use Bash with grep/rg/findstr.\n\n"
        "Features:\n"
        "- 3 output modes: 'content' (matching lines), 'files_with_matches' (file paths only), 'count' (match counts)\n"
        "- Context lines: -A (after), -B (before), -C (both) for surrounding context\n"
        "- Pagination: head_limit + offset for large result sets\n"
        "- Supports regex patterns (e.g., 'def\\s+\\w+', 'import.*os')\n"
        "- Supports glob filtering to narrow file types (e.g., glob='*.py')\n"
        "- Case-insensitive search with case_insensitive=true\n"
        "- Uses ripgrep (rg) if available, otherwise Python fallback\n\n"
        "Default: returns up to 250 matching lines with file:line: content format.\n\n"
        "REMINDER: NEVER use Bash (grep, rg, findstr) to search file content. Always use Grep."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for",
            },
            "path": {
                "type": "string",
                "description": "File or directory to search in (default: current directory)",
            },
            "glob": {
                "type": "string",
                "description": "Glob pattern to filter files (e.g., '*.py')",
            },
            "case_insensitive": {
                "type": "boolean",
                "description": "Case insensitive search (default: false)",
                "default": False,
            },
            "output_mode": {
                "type": "string",
                "enum": ["content", "files_with_matches", "count"],
                "description": (
                    "Output mode: 'content' shows matching lines (default), "
                    "'files_with_matches' shows only file paths, "
                    "'count' shows match counts per file"
                ),
            },
            "context_before": {
                "type": "integer",
                "description": "Number of lines to show before each match (-B)",
            },
            "context_after": {
                "type": "integer",
                "description": "Number of lines to show after each match (-A)",
            },
            "context": {
                "type": "integer",
                "description": "Number of lines to show before AND after each match (-C)",
            },
            "head_limit": {
                "type": "integer",
                "description": "Limit output to first N results (0 = unlimited, default: 250)",
                "default": 250,
            },
            "offset": {
                "type": "integer",
                "description": "Skip first N results before applying head_limit (default: 0)",
                "default": 0,
            },
        },
        "required": ["pattern"],
    }
    is_read_only = True

    def execute(self, input_data: dict) -> str:
        pattern = input_data["pattern"]
        search_path = Path(input_data.get("path", ".")).resolve()
        glob_filter = input_data.get("glob")
        ci = input_data.get("case_insensitive", False)
        output_mode = input_data.get("output_mode", "content")
        ctx_before = input_data.get("context_before", 0)
        ctx_after = input_data.get("context_after", 0)
        ctx_both = input_data.get("context", 0)
        head_limit = input_data.get("head_limit", 250)
        offset = input_data.get("offset", 0)

        # -C overrides -A/-B
        if ctx_both > 0:
            ctx_before = ctx_both
            ctx_after = ctx_both

        rg = shutil.which("rg")
        if rg:
            return self._rg_search(
                rg, pattern, search_path, glob_filter, ci,
                output_mode, ctx_before, ctx_after, head_limit, offset,
            )
        return self._python_search(
            pattern, search_path, glob_filter, ci,
            output_mode, ctx_before, ctx_after, head_limit, offset,
        )

    def _rg_search(
        self, rg: str, pattern: str, path: Path, glob_filter: str | None,
        ci: bool, mode: str, ctx_b: int, ctx_a: int, limit: int, offset: int,
    ) -> str:
        cmd = [rg, "--no-heading", "--color=never"]

        if mode == "files_with_matches":
            cmd.append("--files-with-matches")
        elif mode == "count":
            cmd.append("--count")
        else:
            cmd.append("--line-number")
            if ctx_b > 0:
                cmd.extend(["-B", str(ctx_b)])
            if ctx_a > 0:
                cmd.extend(["-A", str(ctx_a)])

        if ci:
            cmd.append("-i")
        if glob_filter:
            cmd.extend(["--glob", glob_filter])

        # Use a generous limit and paginate ourselves
        fetch_limit = (offset + limit + 50) if limit > 0 else 10000
        if mode == "content":
            cmd.extend([f"--max-count={fetch_limit}"])

        cmd.extend([pattern, str(path)])

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.stdout:
                return self._paginate(result.stdout.strip(), offset, limit)
            if result.returncode == 1:
                return "No matches found."
            return result.stderr.strip() or "No matches found."
        except subprocess.TimeoutExpired:
            return "Error: search timed out after 30s. Try a more specific pattern or path."
        except Exception as e:
            return f"Error: {e}"

    def _python_search(
        self, pattern: str, path: Path, glob_filter: str | None,
        ci: bool, mode: str, ctx_b: int, ctx_a: int, limit: int, offset: int,
    ) -> str:
        flags = re.IGNORECASE if ci else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            return f"Invalid regex: {e}"

        if path.is_file():
            files = [path]
        else:
            glob_pat = glob_filter or "**/*"
            files = sorted(
                (f for f in path.glob(glob_pat) if f.is_file()),
                key=lambda p: p.stat().st_mtime if p.exists() else 0,
                reverse=True,
            )

        results: list[str] = []
        max_collect = (offset + limit + 50) if limit > 0 else 10000

        for file in files:
            if len(results) >= max_collect:
                break
            try:
                text = file.read_text(encoding="utf-8", errors="ignore")
                lines = text.splitlines()

                if mode == "files_with_matches":
                    if any(regex.search(line) for line in lines):
                        results.append(str(file))
                elif mode == "count":
                    count = sum(1 for line in lines if regex.search(line))
                    if count > 0:
                        results.append(f"{file}:{count}")
                else:  # content
                    for i, line in enumerate(lines):
                        if regex.search(line):
                            # Context lines
                            if ctx_b > 0 or ctx_a > 0:
                                start = max(0, i - ctx_b)
                                end = min(len(lines), i + ctx_a + 1)
                                for j in range(start, end):
                                    sep = ":" if j == i else "-"
                                    results.append(f"{file}{sep}{j+1}{sep} {lines[j].rstrip()}")
                                results.append("--")  # separator
                            else:
                                results.append(f"{file}:{i+1}: {line.rstrip()}")

                            if len(results) >= max_collect:
                                break
            except Exception:
                continue

        if not results:
            return "No matches found."

        output = "\n".join(results)
        return self._paginate(output, offset, limit)

    @staticmethod
    def _paginate(output: str, offset: int, limit: int) -> str:
        """Apply offset and limit to output lines."""
        if offset <= 0 and limit <= 0:
            return output
        lines = output.splitlines()
        total = len(lines)
        if offset > 0:
            lines = lines[offset:]
        if limit > 0:
            lines = lines[:limit]
        result = "\n".join(lines)
        if offset > 0 or (limit > 0 and total > offset + limit):
            result += f"\n[Showing {len(lines)} of {total} results (offset={offset}, limit={limit})]"
        return result
