"""
Notebook Edit Tool — modify Jupyter notebook (.ipynb) cells.

Aligned with Claude Code's NotebookEditTool pattern:
- Replace cell contents, insert new cells, or delete cells
- Reads the .ipynb JSON, modifies the target cell, writes back
- Validates notebook structure and cell index bounds
- Preserves notebook metadata, kernel info, and other cells untouched
"""

import json
from pathlib import Path

from tools.base import BaseTool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_notebook(path: Path) -> dict:
    """Read and minimally validate a .ipynb file."""
    text = path.read_text(encoding="utf-8")
    nb = json.loads(text)

    if not isinstance(nb, dict):
        raise ValueError("Notebook JSON root must be an object.")
    if "cells" not in nb:
        raise ValueError(
            "Notebook is missing the 'cells' key — is this a valid .ipynb file?"
        )
    if not isinstance(nb["cells"], list):
        raise ValueError("'cells' must be a JSON array.")
    return nb


def _write_notebook(path: Path, nb: dict) -> None:
    """Write notebook JSON back to disk (pretty-printed, matching Jupyter style)."""
    text = json.dumps(nb, ensure_ascii=False, indent=1, sort_keys=False)
    if not text.endswith("\n"):
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _make_cell(cell_type: str, source: str) -> dict:
    """Create a minimal nbformat-4 cell dict."""
    cell: dict = {
        "cell_type": cell_type,
        "metadata": {},
        "source": _split_source(source),
    }
    if cell_type == "code":
        cell["execution_count"] = None
        cell["outputs"] = []
    return cell


def _split_source(source: str) -> list[str]:
    """Split source into the line-list format Jupyter uses internally.

    Each line except possibly the last ends with ``\\n``.
    An empty source yields ``[]``.
    """
    if not source:
        return []
    lines = source.split("\n")
    result: list[str] = []
    for i, line in enumerate(lines):
        if i < len(lines) - 1:
            result.append(line + "\n")
        else:
            # Last line: include only if non-empty (avoids trailing empty str)
            if line:
                result.append(line)
    return result


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------

class NotebookEditTool(BaseTool):
    name = "NotebookEdit"
    description = (
        "Edit a Jupyter notebook (.ipynb) cell — replace, insert, or delete.\n\n"
        "Jupyter notebooks are JSON files containing an ordered list of cells. "
        "Each cell has a type (code or markdown) and source content.\n\n"
        "Modes:\n"
        "  - replace (default): Overwrite the content (and optionally the type) of "
        "an existing cell. Clears outputs and execution_count on code cells so "
        "stale state is not preserved.\n"
        "  - insert: Add a new cell at the given index; existing cells shift down. "
        "You MUST specify cell_type when inserting.\n"
        "  - delete: Remove the cell at the given index. The new_source parameter "
        "is ignored for deletions.\n\n"
        "Parameters:\n"
        "  - notebook_path: Absolute path to the .ipynb file\n"
        "  - cell_number: 0-based cell index\n"
        "  - new_source: The new cell source (ignored for delete)\n"
        "  - cell_type: 'code' or 'markdown' (required for insert; optional for "
        "replace — defaults to the cell's existing type)\n"
        "  - edit_mode: 'replace', 'insert', or 'delete'\n\n"
        "Tips:\n"
        "  - Use FileRead to inspect the notebook before editing\n"
        "  - cell_number is 0-indexed: the first cell is 0\n"
        "  - For insert, the new cell is placed AT cell_number (before the current "
        "cell at that index). Use cell_number = total_cells to append at the end.\n"
        "  - Always use an absolute path for notebook_path"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "notebook_path": {
                "type": "string",
                "description": "Absolute path to the .ipynb file",
            },
            "cell_number": {
                "type": "integer",
                "description": "0-based index of the cell to modify",
            },
            "new_source": {
                "type": "string",
                "description": (
                    "New source content for the cell. For code cells this is "
                    "the code; for markdown cells this is the markdown text. "
                    "Ignored when edit_mode is 'delete'."
                ),
            },
            "cell_type": {
                "type": "string",
                "enum": ["code", "markdown"],
                "description": (
                    "Cell type. Required for insert mode. "
                    "For replace mode, defaults to the existing cell's type."
                ),
            },
            "edit_mode": {
                "type": "string",
                "enum": ["replace", "insert", "delete"],
                "description": "Operation to perform (default: replace)",
            },
        },
        "required": ["notebook_path", "cell_number", "new_source"],
    }
    is_read_only = False

    def execute(self, input_data: dict) -> str:
        notebook_path = Path(input_data["notebook_path"])
        cell_number: int = input_data["cell_number"]
        new_source: str = input_data.get("new_source", "")
        cell_type: str | None = input_data.get("cell_type")
        edit_mode: str = input_data.get("edit_mode", "replace")

        # --- Basic validation ---------------------------------------------------
        if notebook_path.suffix.lower() != ".ipynb":
            return (
                f"Error: File does not have .ipynb extension: {notebook_path}"
            )
        if not notebook_path.exists():
            return f"Error: Notebook not found: {notebook_path}"
        if not notebook_path.is_file():
            return f"Error: Path is not a file: {notebook_path}"
        if edit_mode not in ("replace", "insert", "delete"):
            return (
                f"Error: Invalid edit_mode '{edit_mode}'. "
                f"Must be 'replace', 'insert', or 'delete'."
            )
        if cell_number < 0:
            return f"Error: cell_number must be >= 0, got {cell_number}."

        # --- Read notebook -------------------------------------------------------
        try:
            nb = _read_notebook(notebook_path)
        except (json.JSONDecodeError, ValueError) as exc:
            return f"Error reading notebook: {exc}"
        except Exception as exc:
            return f"Error reading notebook file: {exc}"

        cells: list[dict] = nb["cells"]
        num_cells = len(cells)

        # --- Dispatch by mode ----------------------------------------------------
        if edit_mode == "replace":
            return self._replace(
                notebook_path, nb, cells, cell_number, num_cells,
                new_source, cell_type,
            )
        elif edit_mode == "insert":
            return self._insert(
                notebook_path, nb, cells, cell_number, num_cells,
                new_source, cell_type,
            )
        else:  # delete
            return self._delete(
                notebook_path, nb, cells, cell_number, num_cells,
            )

    # ----- replace ---------------------------------------------------------------
    def _replace(
        self,
        path: Path,
        nb: dict,
        cells: list[dict],
        idx: int,
        num_cells: int,
        new_source: str,
        cell_type: str | None,
    ) -> str:
        if num_cells == 0:
            return "Error: Notebook has no cells to replace."
        if idx >= num_cells:
            return (
                f"Error: cell_number {idx} is out of range. "
                f"Notebook has {num_cells} cell(s) (indices 0..{num_cells - 1})."
            )

        target = cells[idx]
        old_type = target.get("cell_type", "code")
        resolved_type = cell_type or old_type

        if resolved_type not in ("code", "markdown"):
            return (
                f"Error: Invalid cell_type '{resolved_type}'. "
                f"Must be 'code' or 'markdown'."
            )

        # Update source
        target["source"] = _split_source(new_source)
        target["cell_type"] = resolved_type

        # If the cell is (now) a code cell, reset execution state
        if resolved_type == "code":
            target["execution_count"] = None
            target["outputs"] = []
        else:
            # Markdown cells don't have execution_count/outputs
            target.pop("execution_count", None)
            target.pop("outputs", None)

        # Preserve cell id if present (nbformat >= 4.5)
        # (already in target dict — no action needed)

        try:
            _write_notebook(path, nb)
        except Exception as exc:
            return f"Error writing notebook: {exc}"

        return (
            f"Successfully replaced cell {idx} ({resolved_type}) "
            f"in {path.name}. Notebook has {num_cells} cell(s)."
        )

    # ----- insert ----------------------------------------------------------------
    def _insert(
        self,
        path: Path,
        nb: dict,
        cells: list[dict],
        idx: int,
        num_cells: int,
        new_source: str,
        cell_type: str | None,
    ) -> str:
        # For insert, valid range is [0, num_cells] (append at end allowed)
        if idx > num_cells:
            return (
                f"Error: cell_number {idx} is out of range for insert. "
                f"Notebook has {num_cells} cell(s); valid positions are "
                f"0..{num_cells}."
            )
        if not cell_type:
            return "Error: 'cell_type' is required when edit_mode is 'insert'."
        if cell_type not in ("code", "markdown"):
            return (
                f"Error: Invalid cell_type '{cell_type}'. "
                f"Must be 'code' or 'markdown'."
            )

        new_cell = _make_cell(cell_type, new_source)
        cells.insert(idx, new_cell)

        try:
            _write_notebook(path, nb)
        except Exception as exc:
            return f"Error writing notebook: {exc}"

        new_count = len(cells)
        return (
            f"Successfully inserted new {cell_type} cell at index {idx} "
            f"in {path.name}. Notebook now has {new_count} cell(s)."
        )

    # ----- delete ----------------------------------------------------------------
    def _delete(
        self,
        path: Path,
        nb: dict,
        cells: list[dict],
        idx: int,
        num_cells: int,
    ) -> str:
        if num_cells == 0:
            return "Error: Notebook has no cells to delete."
        if idx >= num_cells:
            return (
                f"Error: cell_number {idx} is out of range. "
                f"Notebook has {num_cells} cell(s) (indices 0..{num_cells - 1})."
            )

        removed = cells.pop(idx)
        removed_type = removed.get("cell_type", "unknown")

        try:
            _write_notebook(path, nb)
        except Exception as exc:
            return f"Error writing notebook: {exc}"

        new_count = len(cells)
        return (
            f"Successfully deleted {removed_type} cell at index {idx} "
            f"from {path.name}. Notebook now has {new_count} cell(s)."
        )
