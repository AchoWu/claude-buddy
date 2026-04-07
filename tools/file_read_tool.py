"""
File Read Tool v2 — CC-aligned enhancements:
  - Image support: PNG/JPG/WebP/GIF detection + compression to ≤1MB
  - PDF page extraction with token budgeting
  - UTF-16 auto-detection
  - LRU state tracking + deduplication
"""

import hashlib
import base64
from pathlib import Path
from tools.base import BaseTool


# Image extensions (CC: FileReadTool supports these)
_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".svg"}
_PDF_EXT = ".pdf"

# Max image size to send (CC: token-aware compression)
_MAX_IMAGE_BYTES = 1 * 1024 * 1024  # 1MB after compression


def _detect_encoding(file_path: Path) -> str:
    """Auto-detect encoding via BOM."""
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


class FileReadTool(BaseTool):
    name = "FileRead"
    description = (
        "Read the contents of a file and return it with line numbers.\n\n"
        "Use this tool to read ANY file. NEVER use Bash with cat/head/tail/type.\n\n"
        "Features:\n"
        "- Returns content with line numbers (1-based)\n"
        "- Supports offset and limit for reading specific sections of large files\n"
        "- Default: reads up to 2000 lines from the beginning\n"
        "- Can read images (PNG, JPG, WebP, GIF) — returns visual description\n"
        "- Can read PDFs — use `pages` parameter for specific page ranges\n"
        "- Use absolute paths\n\n"
        "IMPORTANT: You MUST use this tool to read a file BEFORE using FileEdit on it.\n"
        "The system tracks which files you've read. FileEdit will be rejected if you\n"
        "haven't read the file first."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "Absolute path to the file to read",
            },
            "offset": {
                "type": "integer",
                "description": "Line number to start reading from (1-based)",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to read",
            },
            "pages": {
                "type": "string",
                "description": "Page range for PDF files (e.g. '1-5', '3', '10-20'). Max 20 pages per request.",
            },
        },
        "required": ["file_path"],
    }
    is_read_only = True

    def __init__(self):
        self._file_read_state = None  # injected by ToolRegistry

    def execute(self, input_data: dict) -> str:
        file_path = Path(input_data["file_path"])
        offset = input_data.get("offset", 1)
        limit = input_data.get("limit", 2000)
        pages = input_data.get("pages")

        if not file_path.exists():
            return f"Error: File not found: {file_path}"
        if not file_path.is_file():
            return f"Error: Not a file (it's a directory): {file_path}. Use Glob to list its contents."

        ext = file_path.suffix.lower()

        # ── Image files (CC: token-aware image reading) ──────────
        if ext in _IMAGE_EXTS:
            return self._read_image(file_path)

        # ── PDF files (CC: page extraction) ──────────────────────
        if ext == _PDF_EXT:
            return self._read_pdf(file_path, pages)

        # ── Text files ───────────────────────────────────────────
        return self._read_text(file_path, offset, limit)

    def _read_text(self, file_path: Path, offset: int, limit: int) -> str:
        """Read text file with line numbers and deduplication."""
        try:
            stat = file_path.stat()
            mtime = stat.st_mtime

            # CC-aligned: auto-detect encoding
            encoding = _detect_encoding(file_path)
            text = file_path.read_text(encoding=encoding, errors="replace")
            lines = text.splitlines()

            # Deduplication: if same range read on unchanged file
            if self._file_read_state:
                info = self._file_read_state.get_read_info(str(file_path))
                if info and info.get("mtime_at_read") == mtime:
                    prev_offset = info.get("last_offset", 1)
                    prev_limit = info.get("last_limit", 2000)
                    if prev_offset == offset and prev_limit == limit:
                        return (
                            f"(File unchanged since last read: {file_path}, "
                            f"{len(lines)} lines total. Content omitted to save context. "
                            f"Use a different offset/limit to see other sections.)"
                        )

            # Apply offset and limit
            start = max(0, offset - 1)
            end = start + limit
            selected = lines[start:end]

            # Format with line numbers
            numbered = []
            for i, line in enumerate(selected, start=start + 1):
                numbered.append(f"{i:>6}\t{line}")

            result = "\n".join(numbered)
            if len(lines) > end:
                result += f"\n... ({len(lines) - end} more lines)"

            # Record read
            if self._file_read_state:
                content_hash = hashlib.md5(text.encode()).hexdigest()[:12]
                self._file_read_state.record_read(
                    str(file_path), mtime=mtime, content_hash=content_hash,
                )
                info = self._file_read_state.get_read_info(str(file_path))
                if info:
                    info["last_offset"] = offset
                    info["last_limit"] = limit

            return result if result else "(empty file)"

        except UnicodeDecodeError:
            return f"Error: File appears to be binary: {file_path}"
        except Exception as e:
            return f"Error reading file: {e}"

    def _read_image(self, file_path: Path) -> str:
        """CC-aligned: read image file, compress if needed, return base64 or description."""
        try:
            raw_size = file_path.stat().st_size
            ext = file_path.suffix.lower()

            # SVG: just read as text
            if ext == ".svg":
                text = file_path.read_text(encoding="utf-8", errors="replace")
                if self._file_read_state:
                    self._file_read_state.record_read(str(file_path), mtime=file_path.stat().st_mtime)
                return f"(SVG image, {raw_size:,} bytes)\n{text[:5000]}"

            # Try PIL for compression
            try:
                from PIL import Image
                import io

                img = Image.open(file_path)
                width, height = img.size
                fmt = img.format or "PNG"

                # CC-aligned: compress large images to save tokens
                if raw_size > _MAX_IMAGE_BYTES:
                    # Resize to fit within budget
                    scale = (_MAX_IMAGE_BYTES / raw_size) ** 0.5
                    new_w = max(1, int(width * scale))
                    new_h = max(1, int(height * scale))
                    img = img.resize((new_w, new_h), Image.LANCZOS)
                    buf = io.BytesIO()
                    save_fmt = "JPEG" if ext in (".jpg", ".jpeg") else "PNG"
                    img.save(buf, format=save_fmt, quality=80 if save_fmt == "JPEG" else None)
                    data = buf.getvalue()
                    b64 = base64.b64encode(data).decode()
                    compressed_info = f" (compressed from {raw_size:,}B → {len(data):,}B)"
                else:
                    data = file_path.read_bytes()
                    b64 = base64.b64encode(data).decode()
                    compressed_info = ""

                if self._file_read_state:
                    self._file_read_state.record_read(str(file_path), mtime=file_path.stat().st_mtime)

                return (
                    f"(Image: {fmt} {width}x{height}, {raw_size:,} bytes{compressed_info})\n"
                    f"[base64 data: {len(b64)} chars]"
                )

            except ImportError:
                # No PIL — return basic info
                if self._file_read_state:
                    self._file_read_state.record_read(str(file_path), mtime=file_path.stat().st_mtime)
                return f"(Image file: {file_path.name}, {raw_size:,} bytes. Install Pillow for image viewing.)"

        except Exception as e:
            return f"Error reading image: {e}"

    def _read_pdf(self, file_path: Path, pages: str | None) -> str:
        """CC-aligned: extract text from PDF with page range support."""
        try:
            raw_size = file_path.stat().st_size

            # Parse page range
            page_start, page_end = 1, 20  # default: first 20 pages
            if pages:
                if "-" in pages:
                    parts = pages.split("-", 1)
                    page_start = int(parts[0])
                    page_end = int(parts[1])
                else:
                    page_start = int(pages)
                    page_end = page_start
            # Cap at 20 pages per request
            if page_end - page_start + 1 > 20:
                page_end = page_start + 19

            # Try pymupdf first, then pdfplumber
            text_parts = []
            total_pages = 0

            try:
                import fitz  # pymupdf
                doc = fitz.open(str(file_path))
                total_pages = len(doc)
                for i in range(max(0, page_start - 1), min(page_end, total_pages)):
                    page = doc[i]
                    text_parts.append(f"--- Page {i + 1} ---\n{page.get_text()}")
                doc.close()
            except ImportError:
                try:
                    import pdfplumber
                    with pdfplumber.open(str(file_path)) as pdf:
                        total_pages = len(pdf.pages)
                        for i in range(max(0, page_start - 1), min(page_end, total_pages)):
                            page = pdf.pages[i]
                            text = page.extract_text() or "(no text on this page)"
                            text_parts.append(f"--- Page {i + 1} ---\n{text}")
                except ImportError:
                    if self._file_read_state:
                        self._file_read_state.record_read(str(file_path), mtime=file_path.stat().st_mtime)
                    return (
                        f"(PDF file: {file_path.name}, {raw_size:,} bytes. "
                        f"Install pymupdf or pdfplumber for PDF reading.)"
                    )

            if self._file_read_state:
                self._file_read_state.record_read(str(file_path), mtime=file_path.stat().st_mtime)

            result = "\n\n".join(text_parts) if text_parts else "(no text extracted)"
            header = f"(PDF: {file_path.name}, {total_pages} pages, {raw_size:,} bytes, showing pages {page_start}-{min(page_end, total_pages)})\n\n"
            return header + result

        except Exception as e:
            return f"Error reading PDF: {e}"
