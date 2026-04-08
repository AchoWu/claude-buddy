"""
File Edit Tool v2 — CC-aligned enhancements:
  - Curly quote normalization (\u201c\u201d\u2018\u2019 → straight quotes)
  - UTF-16LE auto-detection via BOM
  - Read-before-edit enforcement via FileReadState
  - Staleness detection (file changed since last read)
  - Unified diff output (CC-aligned: structuredPatch)
"""

import hashlib
import difflib
from pathlib import Path
from tools.base import BaseTool


# CC-aligned: curly quote normalization map (CC normalizes only these 4)
_QUOTE_MAP = str.maketrans({
    '\u201c': '"',  # left double curly quote → straight
    '\u201d': '"',  # right double curly quote → straight
    '\u2018': "'",  # left single curly quote → straight
    '\u2019': "'",  # right single curly quote → straight
})


def _normalize_quotes(s: str) -> str:
    """CC-aligned: normalize curly quotes to straight for matching."""
    return s.translate(_QUOTE_MAP)


def _preserve_quote_style(original: str, replacement: str) -> str:
    """
    CC-aligned: preserveQuoteStyle — if the original file content used curly quotes,
    apply the same curly quote style to the replacement text.
    CC: applyCurlyDoubleQuotes() and applyCurlySingleQuotes() in FileEditTool/utils.ts
    """
    has_curly_double = '\u201c' in original or '\u201d' in original
    has_curly_single = '\u2018' in original or '\u2019' in original

    if not has_curly_double and not has_curly_single:
        return replacement

    result = replacement
    if has_curly_double:
        # Apply curly double quotes: opening " after whitespace/start, closing elsewhere
        # Simplified heuristic: alternate open/close
        chars = list(result)
        in_double = False
        for i, c in enumerate(chars):
            if c == '"':
                chars[i] = '\u201c' if not in_double else '\u201d'
                in_double = not in_double
        result = "".join(chars)

    if has_curly_single:
        chars = list(result)
        in_single = False
        for i, c in enumerate(chars):
            if c == "'":
                chars[i] = '\u2018' if not in_single else '\u2019'
                in_single = not in_single
        result = "".join(chars)

    return result


def _detect_encoding(file_path: Path) -> str:
    """CC-aligned: detect file encoding. UTF-16LE via BOM, else UTF-8."""
    try:
        with open(file_path, "rb") as f:
            bom = f.read(2)
        if bom == b'\xff\xfe':
            return "utf-16-le"
        if bom == b'\xfe\xff':
            return "utf-16-be"
    except Exception:
        pass
    return "utf-8"


def _generate_diff(old_content: str, new_content: str, file_path: str,
                   context_lines: int = 3) -> str:
    """Generate a unified diff string (CC-aligned: structuredPatch).
    Shows added/removed lines with @@ hunk headers."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        n=context_lines,
    )
    result = "".join(diff)
    if not result:
        return ""
    # Cap diff output to avoid flooding context
    lines = result.splitlines()
    if len(lines) > 60:
        lines = lines[:55] + [f"... ({len(lines) - 55} more lines)"]
    return "\n".join(lines)


class FileEditTool(BaseTool):
    name = "FileEdit"
    description = (
        "Edit a file by replacing an exact string with a new string.\n\n"
        "CRITICAL: You MUST read the file with FileRead BEFORE using this tool.\n"
        "The system tracks which files you've read and will reject edits on unread files.\n\n"
        "Rules:\n"
        "1. old_string must match the file content EXACTLY (including whitespace and indentation)\n"
        "2. If old_string appears multiple times, the edit will fail — provide more context to make it unique, or use replace_all=true\n"
        "3. Use replace_all=true to replace ALL occurrences (e.g., renaming a variable)\n\n"
        "Steps to edit a file:\n"
        "1. FileRead the file first\n"
        "2. Copy the exact text from FileRead output (after the line number prefix)\n"
        "3. Use that as old_string\n"
        "4. Provide new_string as the replacement\n\n"
        "IMPORTANT: After a successful edit, the tool result contains a unified diff.\n"
        "REMINDER: ALWAYS FileRead before FileEdit. NEVER guess the file contents."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to edit",
            },
            "old_string": {
                "type": "string",
                "description": "The exact string to find and replace",
            },
            "new_string": {
                "type": "string",
                "description": "The replacement string",
            },
            "replace_all": {
                "type": "boolean",
                "description": "Replace all occurrences (default: false)",
                "default": False,
            },
        },
        "required": ["file_path", "old_string", "new_string"],
    }
    is_read_only = False

    def __init__(self):
        self._file_read_state = None  # injected by ToolRegistry

    def execute(self, input_data: dict) -> str:
        file_path = Path(input_data["file_path"])
        old_string = input_data["old_string"]
        new_string = input_data["new_string"]
        replace_all = input_data.get("replace_all", False)

        if not file_path.exists():
            return f"Error: File not found: {file_path}. Use Glob to find the correct path."

        # ── Read-before-edit enforcement (Claude Code pattern) ────────
        if self._file_read_state:
            if not self._file_read_state.has_read(str(file_path)):
                return (
                    f"Error: You must read {file_path} with FileRead before editing it. "
                    f"This prevents blind edits. Please use FileRead first, then retry FileEdit."
                )

            # Staleness check: file may have changed since we read it
            if self._file_read_state.is_stale(str(file_path)):
                return (
                    f"Warning: {file_path} has been modified since you last read it "
                    f"(by the user or a linter). "
                    f"Please re-read it with FileRead to see the current content, then retry."
                )

        try:
            # CC-aligned: auto-detect encoding (UTF-16LE via BOM)
            encoding = _detect_encoding(file_path)
            content = file_path.read_text(encoding=encoding)

            # Try exact match first
            if old_string in content:
                return self._do_replace(file_path, content, old_string, new_string,
                                        replace_all, encoding)

            # CC-aligned: try with curly quote normalization
            # CC: findActualString() normalizes BOTH file + search, finds position
            # in normalized content, extracts actual substring from original file
            normalized_old = _normalize_quotes(old_string)
            normalized_content = _normalize_quotes(content)

            if normalized_old in normalized_content:
                # Match found after normalizing both sides
                # Find the actual string in original content at the normalized position
                pos = normalized_content.find(normalized_old)
                if pos >= 0:
                    actual_old = content[pos:pos + len(old_string)]
                    # CC: preserveQuoteStyle — apply file's curly style to new_string
                    styled_new = _preserve_quote_style(actual_old, new_string)
                    return self._do_replace(file_path, content, actual_old, styled_new,
                                            replace_all, encoding)

            # Not found — show helpful error
            lines = content.splitlines()
            snippet_lines = lines[:20] if len(lines) > 20 else lines
            snippet = "\n".join(f"  {i+1}: {l}" for i, l in enumerate(snippet_lines))
            return (
                f"Error: old_string not found in {file_path}. "
                f"The file may have different content than expected. "
                f"Re-read with FileRead to see the actual content.\n"
                f"First {len(snippet_lines)} lines of file:\n{snippet}"
            )

        except Exception as e:
            return f"Error editing file: {e}"

    def _do_replace(self, file_path: Path, content: str, old_string: str,
                    new_string: str, replace_all: bool, encoding: str) -> str:
        """Perform the actual replacement, save, and return a diff."""
        count = content.count(old_string)
        if count > 1 and not replace_all:
            return (
                f"Error: old_string found {count} times in {file_path}. "
                f"Options:\n"
                f"1. Add more surrounding context to old_string to make it unique\n"
                f"2. Use replace_all=true to replace ALL {count} occurrences"
            )

        if replace_all:
            new_content = content.replace(old_string, new_string)
            replacements = count
        else:
            new_content = content.replace(old_string, new_string, 1)
            replacements = 1

        file_path.write_text(new_content, encoding=encoding)

        # Update file-read state with new mtime
        if self._file_read_state:
            new_mtime = file_path.stat().st_mtime
            new_hash = hashlib.md5(new_content.encode()).hexdigest()[:12]
            self._file_read_state.record_read(
                str(file_path), mtime=new_mtime, content_hash=new_hash
            )

        # Generate diff for display (CC-aligned: structuredPatch)
        diff = _generate_diff(content, new_content, str(file_path))
        return (
            f"Successfully replaced {replacements} occurrence(s) in {file_path}\n"
            f"{diff}"
        )
