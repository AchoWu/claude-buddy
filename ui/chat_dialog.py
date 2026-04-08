"""
Chat Dialog — full conversation window with translucent glass-morphism design.
"""

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QTimer, QSize, QRectF
from PyQt6.QtGui import (
    QFont, QColor, QKeyEvent, QPainter, QPainterPath,
    QLinearGradient, QBrush, QPen,
)
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QScrollArea, QLabel,
    QLineEdit, QPushButton, QFrame, QSizePolicy, QGraphicsDropShadowEffect,
)

from config import (
    BG_DARK, BG_BUBBLE, BG_INPUT, TEXT_PRIMARY, TEXT_DIM,
    CLAUDE_ORANGE, CLAUDE_ORANGE_SHIMMER, BORDER_RADIUS,
    SUCCESS_GREEN, ERROR_RED,
)

# ── Glass-morphism palette ───────────────────────────────────────────────
GLASS_BG = "rgba(30, 30, 30, 200)"       # semi-transparent dark
GLASS_HEADER = "rgba(45, 45, 45, 220)"   # slightly more opaque header
GLASS_INPUT = "rgba(20, 20, 20, 220)"    # input area
GLASS_BORDER = "rgba(255, 255, 255, 25)" # subtle white border
MSG_BG_USER = "rgba(215, 119, 87, 180)"  # Claude orange, semi-transparent
MSG_BG_ASSISTANT = "rgba(55, 55, 55, 200)"  # dark gray bubble
MSG_BG_TOOL = "rgba(40, 40, 40, 180)"    # tool call bg


class AvatarLabel(QLabel):
    """Tiny circular avatar indicator."""

    def __init__(self, letter: str, color: str, parent=None):
        super().__init__(parent)
        self.setFixedSize(28, 28)
        self._letter = letter
        self._color = QColor(color)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        # Circle
        p.setBrush(self._color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(2, 2, 24, 24)
        # Letter
        p.setPen(QColor("white"))
        font = QFont("Segoe UI", 11)
        font.setBold(True)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._letter)
        p.end()


class _MarkdownRenderer:
    """Lightweight Markdown to HTML converter for chat bubbles."""

    @staticmethod
    def to_html(md: str) -> str:
        """Convert markdown text to HTML suitable for QLabel rendering."""
        import re
        lines = md.split('\n')
        html_lines = []
        in_code_block = False
        in_list = False
        code_lang = ""

        for line in lines:
            # Fenced code block toggle
            if line.strip().startswith('```'):
                if not in_code_block:
                    in_code_block = True
                    code_lang = line.strip()[3:].strip()
                    if in_list:
                        html_lines.append('</ul>')
                        in_list = False
                    html_lines.append(
                        '<pre style="background:rgba(0,0,0,0.3);padding:8px;'
                        'border-radius:6px;font-family:Consolas,monospace;font-size:12px;">'
                    )
                else:
                    in_code_block = False
                    html_lines.append('</pre>')
                continue

            if in_code_block:
                escaped = line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                html_lines.append(escaped)
                continue

            # Headers
            m = re.match(r'^(#{1,6})\s+(.+)$', line)
            if m:
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                level = len(m.group(1))
                sizes = {1: '18px', 2: '16px', 3: '14px', 4: '13px', 5: '12px', 6: '11px'}
                size = sizes.get(level, '13px')
                html_lines.append(
                    f'<p style="font-size:{size};font-weight:bold;margin:6px 0 4px 0;">'
                    f'{_MarkdownRenderer._inline(m.group(2))}</p>'
                )
                continue

            # Unordered list
            m = re.match(r'^[\s]*[-*+]\s+(.+)$', line)
            if m:
                if not in_list:
                    html_lines.append('<ul style="margin:2px 0 2px 16px;">')
                    in_list = True
                html_lines.append(f'<li>{_MarkdownRenderer._inline(m.group(1))}</li>')
                continue

            # Ordered list
            m = re.match(r'^[\s]*(\d+)[.)]\s+(.+)$', line)
            if m:
                if in_list:
                    html_lines.append('</ul>')
                    in_list = False
                html_lines.append(f'<p style="margin:1px 0 1px 16px;">{m.group(1)}. {_MarkdownRenderer._inline(m.group(2))}</p>')
                continue

            # Close list if we hit a non-list line
            if in_list and line.strip():
                html_lines.append('</ul>')
                in_list = False

            # Blockquote
            if line.strip().startswith('>'):
                text = line.strip()[1:].strip()
                html_lines.append(
                    f'<p style="border-left:3px solid rgba(255,255,255,0.3);'
                    f'padding-left:8px;color:rgba(255,255,255,0.7);margin:2px 0;">'
                    f'{_MarkdownRenderer._inline(text)}</p>'
                )
                continue

            # Horizontal rule
            if re.match(r'^[-*_]{3,}\s*$', line.strip()):
                html_lines.append('<hr style="border:none;border-top:1px solid rgba(255,255,255,0.2);margin:6px 0;">')
                continue

            # Empty line
            if not line.strip():
                html_lines.append('<br>')
                continue

            # Normal paragraph
            html_lines.append(f'<p style="margin:2px 0;">{_MarkdownRenderer._inline(line)}</p>')

        if in_list:
            html_lines.append('</ul>')
        if in_code_block:
            html_lines.append('</pre>')

        return '\n'.join(html_lines)

    @staticmethod
    def _inline(text: str) -> str:
        """Handle inline markdown: bold, italic, code, links, strikethrough."""
        import re
        # Inline code (must be first to prevent inner processing)
        text = re.sub(
            r'`([^`]+)`',
            r'<code style="background:rgba(0,0,0,0.3);padding:1px 4px;border-radius:3px;'
            r'font-family:Consolas,monospace;font-size:12px;">\1</code>',
            text
        )
        # Bold + italic
        text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
        # Bold
        text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
        # Italic
        text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
        # Strikethrough
        text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)
        # Links
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
        return text


class MessageBubble(QFrame):
    """A single message bubble with avatar and glass-style background."""

    def __init__(self, text: str, role: str = "assistant",
                 timestamp: float | None = None, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        is_user = role == "user"

        # Avatar
        if is_user:
            avatar = AvatarLabel("U", "#5B8DEF")
        else:
            avatar = AvatarLabel("C", CLAUDE_ORANGE)

        bg = MSG_BG_USER if is_user else MSG_BG_ASSISTANT
        if is_user:
            radius = "border-radius: 14px 4px 14px 14px;"
        else:
            radius = "border-radius: 4px 14px 14px 14px;"

        if is_user:
            # User messages: plain QLabel (no markdown needed)
            self._label = QLabel(text)
            self._label.setWordWrap(True)
            self._label.setTextFormat(Qt.TextFormat.PlainText)
            self._label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
            )
            self._label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            self._label.setMaximumWidth(460)
            self._label.setStyleSheet(f"""
                QLabel {{
                    background: {bg};
                    color: {TEXT_PRIMARY};
                    {radius}
                    padding: 10px 14px;
                    font-size: 13px;
                    line-height: 1.5;
                }}
            """)
            self._content_widget = self._label
            self._is_browser = False
        else:
            # Assistant messages: QLabel with Markdown→HTML conversion
            self._label = QLabel()
            self._label.setWordWrap(True)
            self._label.setTextFormat(Qt.TextFormat.RichText)
            self._label.setTextInteractionFlags(
                Qt.TextInteractionFlag.TextSelectableByMouse
                | Qt.TextInteractionFlag.LinksAccessibleByMouse
            )
            self._label.setOpenExternalLinks(True)
            self._label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
            self._label.setMaximumWidth(460)
            self._label.setStyleSheet(f"""
                QLabel {{
                    background: {bg};
                    color: {TEXT_PRIMARY};
                    {radius}
                    padding: 10px 14px;
                    font-size: 13px;
                    line-height: 1.5;
                }}
                QLabel a {{
                    color: {CLAUDE_ORANGE};
                }}
            """)
            if text:
                self._label.setText(_MarkdownRenderer.to_html(text))
            self._content_widget = self._label
            self._is_browser = True  # flag: uses markdown rendering
            self._raw_text = text    # store raw markdown for streaming

        # Timestamp
        time_label = QLabel(self._format_time(timestamp))
        time_label.setStyleSheet(f"""
            QLabel {{
                color: rgba(255,255,255,80);
                font-size: 10px;
                background: transparent;
                padding: 0 4px;
            }}
        """)

        bubble_col = QVBoxLayout()
        bubble_col.setContentsMargins(0, 0, 0, 0)
        bubble_col.setSpacing(2)
        bubble_col.addWidget(self._content_widget)
        if is_user:
            time_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        bubble_col.addWidget(time_label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(8)

        if is_user:
            layout.addStretch()
            layout.addLayout(bubble_col)
            layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)
        else:
            layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)
            layout.addLayout(bubble_col)
            layout.addStretch()

    def set_text(self, text: str):
        """Update the message content."""
        if self._is_browser:
            self._raw_text = text
            self._label.setText(_MarkdownRenderer.to_html(text))
        else:
            self._label.setText(text)

    def get_text(self) -> str:
        """Get the current raw text content."""
        if self._is_browser:
            return self._raw_text
        return self._label.text()

    def append_text(self, chunk: str):
        """Append text (for streaming). Accumulates raw text, renders periodically."""
        if self._is_browser:
            self._raw_text += chunk
            # During streaming: render HTML every chunk (QLabel handles height automatically)
            self._label.setText(_MarkdownRenderer.to_html(self._raw_text))
        else:
            self._label.setText(self._label.text() + chunk)

    def finalize_streaming(self, full_text: str):
        """Called when streaming ends — re-render the full text as Markdown."""
        if self._is_browser:
            self._raw_text = full_text
            self._label.setText(_MarkdownRenderer.to_html(full_text))

    @staticmethod
    def _format_time(timestamp: float | None = None) -> str:
        from datetime import datetime
        if timestamp:
            return datetime.fromtimestamp(timestamp).strftime("%H:%M")
        return datetime.now().strftime("%H:%M")


class ToolCallBubble(QFrame):
    """Inline tool call indicator with subtle styling."""

    def __init__(self, tool_name: str, summary: str = "", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        # Icon + name + summary (truncate long summaries)
        display = summary[:30] + "..." + summary[-30:] if len(summary) > 60 else summary
        self._label = QLabel(
            f"<span style='color:{CLAUDE_ORANGE}'>&#9889;</span> "
            f"<span style='color:rgba(255,255,255,180)'><b>{tool_name}</b></span>"
            f"  <span style='color:rgba(255,255,255,90)'>{display}</span>"
        )
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setWordWrap(True)
        self._label.setMaximumWidth(420)
        self._label.setStyleSheet(f"""
            QLabel {{
                background: {MSG_BG_TOOL};
                color: {TEXT_DIM};
                border-radius: 8px;
                border-left: 2px solid {CLAUDE_ORANGE};
                padding: 6px 12px;
                font-size: 11px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(42, 2, 42, 2)  # indent to align with messages
        layout.addWidget(self._label)
        layout.addStretch()


class DiffBubble(QFrame):
    """CC-aligned: inline diff display rendered directly from tool result.
    Shows unified diff with green (+) / red (-) lines immediately after tool execution."""

    # Colors for diff syntax highlighting
    _ADD_COLOR = "#A8D08D"      # green for added lines
    _DEL_COLOR = "#E06C75"      # red for removed lines
    _HUNK_COLOR = "#61AFEF"     # blue for @@ headers
    _CTX_COLOR = "rgba(255,255,255,100)"  # dim for context lines
    _META_COLOR = "rgba(255,255,255,60)"  # dimmer for --- +++ headers

    def __init__(self, file_path: str, diff_text: str, num_add: int = 0,
                 num_del: int = 0, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: rgba(30, 30, 30, 220);
                border: 1px solid rgba(255,255,255,30);
                border-left: 2px solid {self._HUNK_COLOR};
                border-radius: 8px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 8, 10, 8)
        card_layout.setSpacing(2)

        # Header: file path + stats
        short_path = file_path
        if len(short_path) > 60:
            short_path = "..." + short_path[-57:]
        stats = ""
        if num_add:
            stats += f" <span style='color:{self._ADD_COLOR}'>+{num_add}</span>"
        if num_del:
            stats += f" <span style='color:{self._DEL_COLOR}'>-{num_del}</span>"
        header = QLabel(
            f"<span style='color:rgba(255,255,255,150); font-size:11px;'>"
            f"{short_path}</span>{stats}"
        )
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setStyleSheet("background: transparent; border: none; padding: 0 2px;")
        card_layout.addWidget(header)

        # Diff lines (syntax highlighted)
        diff_html = self._highlight_diff(diff_text)
        diff_label = QLabel(diff_html)
        diff_label.setTextFormat(Qt.TextFormat.RichText)
        diff_label.setWordWrap(True)
        diff_label.setStyleSheet(
            "background: transparent; border: none; padding: 2px 4px;"
            "font-family: Consolas, 'Courier New', monospace; font-size: 11px;"
        )
        card_layout.addWidget(diff_label)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(42, 2, 42, 2)
        outer.addWidget(card)

    def _highlight_diff(self, text: str) -> str:
        """Convert unified diff text to syntax-highlighted HTML."""
        lines = text.splitlines()
        html_lines = []
        max_lines = 40  # cap display
        for i, line in enumerate(lines):
            if i >= max_lines:
                html_lines.append(
                    f"<span style='color:{self._META_COLOR}'>"
                    f"... ({len(lines) - max_lines} more lines)</span>"
                )
                break
            escaped = (line.replace("&", "&amp;").replace("<", "&lt;")
                       .replace(">", "&gt;").replace(" ", "&nbsp;"))
            if line.startswith("+++") or line.startswith("---"):
                html_lines.append(f"<span style='color:{self._META_COLOR}'>{escaped}</span>")
            elif line.startswith("@@"):
                html_lines.append(f"<span style='color:{self._HUNK_COLOR}'>{escaped}</span>")
            elif line.startswith("+"):
                html_lines.append(f"<span style='color:{self._ADD_COLOR}'>{escaped}</span>")
            elif line.startswith("-"):
                html_lines.append(f"<span style='color:{self._DEL_COLOR}'>{escaped}</span>")
            else:
                html_lines.append(f"<span style='color:{self._CTX_COLOR}'>{escaped}</span>")
        return "<br>".join(html_lines)


class InterruptBubble(QFrame):
    """User-initiated interruption indicator — visually distinct from tool calls."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        self._label = QLabel(
            "<span style='color:rgba(220,160,80,220); font-size:13px;'>&#9632;</span>"
            "  <span style='color:rgba(220,160,80,200); font-size:11px;'>"
            "Request interrupted by user</span>"
        )
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setStyleSheet("""
            QLabel {
                background: rgba(50, 40, 30, 160);
                color: rgba(220, 160, 80, 200);
                border-radius: 10px;
                border: 1px solid rgba(220, 160, 80, 60);
                padding: 5px 16px;
                font-size: 11px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(60, 4, 60, 4)
        layout.addStretch()
        layout.addWidget(self._label)
        layout.addStretch()


class AskUserBubble(QFrame):
    """Inline interactive bubble for AskUser tool — chips + text input.
    Inserted into the message flow. Emits `answered` when user responds."""

    answered = pyqtSignal(str)  # user's answer text

    def __init__(self, question: str, options: list, multi_select: bool = False, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        # Normalize options
        self._options: list[dict] = []
        for opt in (options or []):
            if isinstance(opt, str):
                self._options.append({"label": opt})
            elif isinstance(opt, dict):
                self._options.append(opt)
        self._multi_select = multi_select
        self._chips: list[QPushButton] = []
        self._selected: set[int] = set()
        self._submitted = False

        # ── Card container ──────────────────────────────────────
        self._card = QFrame()
        self._card.setStyleSheet(f"""
            QFrame {{
                background: rgba(45, 40, 35, 200);
                border: 1px solid rgba(215, 119, 87, 100);
                border-radius: 10px;
            }}
        """)
        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(14, 12, 14, 12)
        card_layout.setSpacing(8)

        # Question label
        q_label = QLabel(f"<span style='color:{CLAUDE_ORANGE}'>&#10067;</span>  {question}")
        q_label.setTextFormat(Qt.TextFormat.RichText)
        q_label.setWordWrap(True)
        q_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; background: transparent; border: none;")
        card_layout.addWidget(q_label)

        # ── Option chips (vertical list) ────────────────────────
        if self._options:
            for idx, opt in enumerate(self._options):
                label = opt.get("label", "")
                desc = opt.get("description", "")
                chip = QPushButton(label)
                if desc:
                    chip.setToolTip(desc)
                chip.setCursor(Qt.CursorShape.PointingHandCursor)
                chip.setStyleSheet(self._chip_style(False))
                chip.clicked.connect(lambda _, i=idx: self._on_chip_click(i))
                self._chips.append(chip)
                card_layout.addWidget(chip)

        # ── Text input row ──────────────────────────────────────
        input_row = QHBoxLayout()
        input_row.setSpacing(4)
        self._text_input = QLineEdit()
        self._text_input.setPlaceholderText(
            "Or type your own..." if self._options else "Type your response..."
        )
        self._text_input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(30, 30, 30, 200);
                color: {TEXT_PRIMARY};
                border: 1px solid #555;
                border-radius: 8px;
                padding: 7px 10px;
                font-size: 12px;
            }}
            QLineEdit:focus {{
                border-color: {CLAUDE_ORANGE};
            }}
        """)
        self._text_input.returnPressed.connect(self._submit_text)
        input_row.addWidget(self._text_input)

        send_btn = QPushButton("▶")
        send_btn.setFixedSize(30, 30)
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {CLAUDE_ORANGE};
                color: white;
                border: none;
                border-radius: 15px;
                font-size: 12px;
            }}
            QPushButton:hover {{ background: #E8913A; }}
        """)
        send_btn.clicked.connect(self._submit_text)
        input_row.addWidget(send_btn)
        card_layout.addLayout(input_row)

        # ── Multi-select submit button ──────────────────────────
        if self._multi_select and self._options:
            self._submit_btn = QPushButton("Submit selected")
            self._submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._submit_btn.setEnabled(False)
            self._submit_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {CLAUDE_ORANGE}; color: white; border: none;
                    border-radius: 8px; padding: 6px 16px; font-size: 12px;
                }}
                QPushButton:hover {{ background: #E8913A; }}
                QPushButton:disabled {{ background: #555; color: #888; }}
            """)
            self._submit_btn.clicked.connect(self._submit_multi)
            card_layout.addWidget(self._submit_btn)

        # ── Outer layout ────────────────────────────────────────
        outer = QHBoxLayout(self)
        outer.setContentsMargins(42, 4, 42, 4)
        outer.addWidget(self._card)

    # ── Styles ───────────────────────────────────────────────────

    @staticmethod
    def _chip_style(selected: bool) -> str:
        if selected:
            return f"""
                QPushButton {{
                    background: {CLAUDE_ORANGE}; color: white;
                    border: 1px solid {CLAUDE_ORANGE}; border-radius: 8px;
                    padding: 7px 14px; font-size: 12px; text-align: left;
                }}
                QPushButton:hover {{ background: #E8913A; }}
            """
        return f"""
            QPushButton {{
                background: rgba(58, 58, 58, 200); color: {TEXT_PRIMARY};
                border: 1px solid #555; border-radius: 8px;
                padding: 7px 14px; font-size: 12px; text-align: left;
            }}
            QPushButton:hover {{ background: rgba(72, 72, 72, 200); border-color: {CLAUDE_ORANGE}; }}
        """

    # ── Interaction ──────────────────────────────────────────────

    def _on_chip_click(self, index: int):
        if self._submitted:
            return
        if self._multi_select:
            # Toggle
            if index in self._selected:
                self._selected.discard(index)
                self._chips[index].setStyleSheet(self._chip_style(False))
            else:
                self._selected.add(index)
                self._chips[index].setStyleSheet(self._chip_style(True))
            n = len(self._selected)
            if hasattr(self, '_submit_btn'):
                self._submit_btn.setEnabled(n > 0)
                self._submit_btn.setText(f"Submit ({n})" if n else "Submit selected")
        else:
            # Single-select: immediate submit
            answer = self._options[index].get("label", "")
            self._finish(answer)

    def _submit_text(self):
        if self._submitted:
            return
        text = self._text_input.text().strip()
        if text:
            self._finish(text)

    def _submit_multi(self):
        if self._submitted:
            return
        labels = [self._options[i].get("label", "") for i in sorted(self._selected)]
        typed = self._text_input.text().strip()
        if typed:
            labels.append(typed)
        if labels:
            self._finish(", ".join(labels))

    def _finish(self, answer: str):
        """Lock the bubble and emit answer."""
        self._submitted = True
        # Replace interactive content with static result
        # Remove all widgets from card
        card_layout = self._card.layout()
        while card_layout.count():
            item = card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                # Clear sub-layout
                sub = item.layout()
                while sub.count():
                    si = sub.takeAt(0)
                    if si.widget():
                        si.widget().deleteLater()

        # Show static result
        result_label = QLabel(
            f"<span style='color:{CLAUDE_ORANGE}'>&#10003;</span>  "
            f"<span style='color:rgba(255,255,255,180)'>{answer}</span>"
        )
        result_label.setTextFormat(Qt.TextFormat.RichText)
        result_label.setWordWrap(True)
        result_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; background: transparent; border: none;")
        card_layout.addWidget(result_label)

        self._card.setStyleSheet(f"""
            QFrame {{
                background: rgba(40, 40, 35, 160);
                border: 1px solid rgba(215, 119, 87, 60);
                border-radius: 10px;
            }}
        """)

        self.answered.emit(answer)


class ThinkingIndicator(QFrame):
    """Animated '...' thinking indicator."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        avatar = AvatarLabel("C", CLAUDE_ORANGE)

        self._dots_label = QLabel("")
        self._dots_label.setStyleSheet(f"""
            QLabel {{
                background: {MSG_BG_ASSISTANT};
                color: {CLAUDE_ORANGE};
                border-radius: 4px 14px 14px 14px;
                padding: 10px 18px;
                font-size: 18px;
                font-weight: bold;
                letter-spacing: 3px;
            }}
        """)
        self._dots_label.setFixedWidth(80)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(8)
        layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self._dots_label)
        layout.addStretch()

        self._dot_count = 0
        self._timer = QTimer(self)
        self._timer.setInterval(400)
        self._timer.timeout.connect(self._animate)

    def start(self):
        self._dot_count = 0
        self._timer.start()
        self.show()

    def stop(self):
        self._timer.stop()
        self.hide()

    def _animate(self):
        self._dot_count = (self._dot_count % 3) + 1
        self._dots_label.setText("." * self._dot_count)


class GlassContainer(QFrame):
    """Custom-painted translucent container with rounded corners and border glow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        radius = BORDER_RADIUS

        # Background fill (translucent)
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        p.fillPath(path, QColor(25, 25, 25, 200))

        # Border (subtle white glow)
        pen = QPen(QColor(255, 255, 255, 30), 1.0)
        p.setPen(pen)
        p.drawRoundedRect(rect, radius, radius)

        # Top highlight line (glass reflection effect)
        highlight_rect = QRectF(rect.x() + 20, rect.y(), rect.width() - 40, 1)
        p.setPen(Qt.PenStyle.NoPen)
        gradient = QLinearGradient(highlight_rect.left(), 0, highlight_rect.right(), 0)
        gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
        gradient.setColorAt(0.5, QColor(255, 255, 255, 40))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(gradient))
        p.drawRect(highlight_rect)

        p.end()


class ChatDialog(QWidget):
    """Full conversation dialog with translucent glass-morphism design."""

    message_sent = pyqtSignal(str)   # user typed a message
    abort_requested = pyqtSignal()   # user clicked stop during thinking
    open_settings = pyqtSignal()     # user clicked settings button
    clear_requested = pyqtSignal()   # user clicked clear history button
    ask_user_answered = pyqtSignal(str)  # user answered an AskUser bubble

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumSize(420, 500)
        self.resize(600, 720)

        # ── Resize state ────────────────────────────────────────────
        self._resize_edge = None      # which edge is being dragged
        self._resize_margin = 6       # px from edge to trigger resize cursor
        self.setMouseTracking(True)   # track mouse for cursor changes

        # Drop shadow around the entire dialog
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 120))
        shadow.setOffset(0, 4)

        # Glass container
        self._container = GlassContainer(self)
        self._container.setGraphicsEffect(shadow)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)  # shadow margin
        main_layout.addWidget(self._container)

        container_layout = QVBoxLayout(self._container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # ── Title bar ────────────────────────────────────────────────
        title_bar = QFrame()
        title_bar.setFixedHeight(44)
        title_bar.setStyleSheet(f"""
            QFrame {{
                background: {GLASS_HEADER};
                border-top-left-radius: {BORDER_RADIUS}px;
                border-top-right-radius: {BORDER_RADIUS}px;
                border-bottom: 1px solid rgba(255,255,255,15);
            }}
        """)
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(16, 0, 12, 0)

        # Orange dot + title
        dot_label = QLabel(f"<span style='color:{CLAUDE_ORANGE}; font-size:22px;'>&#9679;</span>")
        dot_label.setTextFormat(Qt.TextFormat.RichText)
        dot_label.setFixedWidth(24)
        dot_label.setStyleSheet("background: transparent;")
        title_layout.addWidget(dot_label)

        title_label = QLabel(f"<b style='color:rgba(255,255,255,220); font-size:14px;'>Claude Buddy</b>")
        title_label.setTextFormat(Qt.TextFormat.RichText)
        title_label.setStyleSheet("background: transparent;")
        title_layout.addWidget(title_label)

        title_layout.addStretch()

        # Settings button in title bar
        settings_btn = QPushButton("S")
        settings_btn.setObjectName("settingsBtn")
        settings_btn.setFixedSize(32, 32)
        settings_btn.setToolTip("Settings (API Key)")
        settings_btn.clicked.connect(self.open_settings.emit)
        title_layout.addWidget(settings_btn)

        # Clear history button (trash icon drawn via QPixmap)
        clear_btn = QPushButton()
        clear_btn.setObjectName("clearBtn")
        clear_btn.setFixedSize(32, 32)
        clear_btn.setToolTip("Clear conversation history")
        clear_btn.setIcon(self._make_trash_icon())
        clear_btn.setIconSize(QSize(16, 16))
        clear_btn.setStyleSheet(f"""
            QPushButton {{
                background: rgba(255,255,255,15);
                border: 1px solid rgba(255,255,255,20);
                border-radius: 6px;
            }}
            QPushButton:hover {{
                background: rgba(255,100,100,40);
                border-color: {ERROR_RED};
            }}
        """)
        clear_btn.clicked.connect(self._on_clear)
        title_layout.addWidget(clear_btn)

        # Minimize button
        min_btn = QPushButton("-")
        min_btn.setObjectName("miniBtn")
        min_btn.setFixedSize(32, 32)
        min_btn.clicked.connect(self.hide)
        title_layout.addWidget(min_btn)

        # Close button
        close_btn = QPushButton("X")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(32, 32)
        close_btn.clicked.connect(self.hide)
        title_layout.addWidget(close_btn)

        container_layout.addWidget(title_bar)

        # ── Drag support ─────────────────────────────────────────────
        self._drag_pos = None
        self._anchor = QPoint(0, 0)
        self._has_shown_once = False  # First show → center on screen
        title_bar.mousePressEvent = self._title_mouse_press
        title_bar.mouseMoveEvent = self._title_mouse_move
        title_bar.mouseReleaseEvent = lambda e: setattr(self, '_drag_pos', None)

        # ── Message area ─────────────────────────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{
                background: transparent;
                border: none;
            }}
            QScrollArea > QWidget > QWidget {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: transparent;
                width: 6px;
                margin: 4px 1px;
            }}
            QScrollBar::handle:vertical {{
                background: rgba(255,255,255,40);
                border-radius: 3px;
                min-height: 30px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: rgba(255,255,255,70);
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
                background: transparent;
            }}
        """)

        self._messages_widget = QWidget()
        self._messages_widget.setStyleSheet("background: transparent;")
        self._messages_layout = QVBoxLayout(self._messages_widget)
        self._messages_layout.setContentsMargins(4, 12, 4, 12)
        self._messages_layout.setSpacing(4)
        self._messages_layout.addStretch()

        self._scroll.setWidget(self._messages_widget)
        container_layout.addWidget(self._scroll, 1)

        # ── Thinking indicator ───────────────────────────────────────
        self._thinking = ThinkingIndicator()
        self._thinking.hide()
        self._messages_layout.addWidget(self._thinking)

        # ── Status bar ───────────────────────────────────────────────
        status_bar = QHBoxLayout()
        status_bar.setContentsMargins(12, 0, 12, 0)
        status_bar.setSpacing(6)

        self._status = QLabel(f"<span style='color:rgba(255,255,255,80)'>Ready</span>")
        self._status.setTextFormat(Qt.TextFormat.RichText)
        self._status.setStyleSheet("font-size: 10px; background: transparent;")
        status_bar.addWidget(self._status)

        status_bar.addStretch()

        self._plan_badge = QLabel("PLAN MODE")
        self._plan_badge.setStyleSheet("""
            QLabel {
                background: rgba(100, 160, 255, 50);
                color: rgba(100, 160, 255, 220);
                border: 1px solid rgba(100, 160, 255, 80);
                border-radius: 6px;
                padding: 1px 8px;
                font-size: 9px;
                font-weight: bold;
            }
        """)
        self._plan_badge.hide()
        status_bar.addWidget(self._plan_badge)

        container_layout.addLayout(status_bar)

        # ── Input area ───────────────────────────────────────────────
        input_frame = QFrame()
        input_frame.setStyleSheet(f"""
            QFrame {{
                background: {GLASS_INPUT};
                border-bottom-left-radius: {BORDER_RADIUS}px;
                border-bottom-right-radius: {BORDER_RADIUS}px;
                border-top: 1px solid rgba(255,255,255,10);
            }}
        """)
        input_layout = QHBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 10, 12, 12)
        input_layout.setSpacing(8)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Ask Claude Buddy anything...")
        self._input.setStyleSheet(f"""
            QLineEdit {{
                background: rgba(255,255,255,8);
                border: 1px solid rgba(255,255,255,20);
                border-radius: 18px;
                padding: 8px 16px;
                color: {TEXT_PRIMARY};
                font-size: 13px;
                selection-background-color: {CLAUDE_ORANGE};
            }}
            QLineEdit:focus {{
                border: 1px solid rgba(215,119,87,120);
            }}
            QLineEdit::placeholder {{
                color: rgba(255,255,255,40);
            }}
        """)
        self._input.setFixedHeight(36)
        self._input.returnPressed.connect(self._on_send)
        input_layout.addWidget(self._input)

        self._send_btn = QPushButton(">")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setFixedSize(36, 36)
        self._send_btn.clicked.connect(self._on_send_or_abort)
        input_layout.addWidget(self._send_btn)

        self._is_thinking = False

        container_layout.addWidget(input_frame)

    # ── Streaming state ───────────────────────────────────────────────
        self._streaming_bubble: MessageBubble | None = None

    # ── Input history (↑/↓ like shell, persisted to disk) ──────────────
        self._input_history: list[str] = []    # oldest first
        self._history_index = -1               # -1 = not browsing
        self._saved_input = ""                 # stash current input when browsing
        self._input.installEventFilter(self)
        self._load_input_history()

    # ── Public API ───────────────────────────────────────────────────
    def load_history(self, messages: list[dict]):
        """Load conversation history into the chat UI. Called on open."""
        self._loading_history = True  # suppress per-message auto-scroll
        self._clear_messages()

        if not messages:
            return

        import re
        has_any = False
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            ts = msg.get("timestamp")

            # Skip system/tool role messages
            if role in ("system", "tool"):
                continue

            # Extract text from various content formats
            if isinstance(content, dict):
                content = content.get("content", str(content))
            if isinstance(content, list):
                parts = []
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
                content = "\n".join(parts) if parts else ""

            if not isinstance(content, str) or not content.strip():
                continue

            text = content.strip()

            # Skip tool result messages
            if text.startswith("[Tool Result"):
                continue

            if role == "user":
                # Use _display field if available (e.g., "/init" instead of raw prompt)
                display = msg.get("_display", "")
                show_text = display if display else text
                if show_text == "[Request interrupted by user]":
                    self.add_interrupt_message()
                    has_any = True
                    continue
                self.add_user_message(show_text, timestamp=ts)
                has_any = True
            elif role == "assistant":
                # Split into text parts and tool_call parts, render each appropriately
                # Find all <tool_call> blocks
                tool_call_pattern = re.compile(r'<tool_call>\s*(\{.*?\})\s*</tool_call>', re.DOTALL)
                parts = tool_call_pattern.split(text)
                # parts = [text_before, json1, text_between, json2, text_after, ...]
                for i, part in enumerate(parts):
                    part = part.strip()
                    if not part:
                        continue
                    if i % 2 == 1:
                        # This is a JSON tool call block
                        try:
                            import json
                            data = json.loads(part)
                            name = data.get("name", "Tool")
                            args = data.get("arguments", {})
                            summary = str(args.get("command", args.get("file_path", args.get("query", ""))))
                            self.add_tool_call(name, summary)
                        except (json.JSONDecodeError, AttributeError):
                            pass
                    else:
                        # Normal text — render as assistant message
                        if part:
                            self.add_assistant_message(part, timestamp=ts)

        # Done loading — scroll to bottom once, then re-enable auto-scroll
        self._loading_history = False
        self._scroll_to_bottom()

    def add_user_message(self, text: str, timestamp: float | None = None):
        bubble = MessageBubble(text, role="user", timestamp=timestamp)
        self._insert_message(bubble)

    def add_assistant_message(self, text: str, timestamp: float | None = None):
        # If we were streaming, finalize that bubble instead of creating new one
        if self._streaming_bubble is not None:
            self._streaming_bubble.finalize_streaming(text)
            self._streaming_bubble = None
            self._scroll_to_bottom()
            return
        bubble = MessageBubble(text, role="assistant", timestamp=timestamp)
        self._insert_message(bubble)

    def append_streaming_chunk(self, chunk: str):
        """Append a text chunk to the current streaming bubble (real-time display)."""
        if self._streaming_bubble is None:
            # Create a new streaming bubble
            self._streaming_bubble = MessageBubble("", role="assistant")
            self._insert_message(self._streaming_bubble)
        # Append text to the existing bubble
        self._streaming_bubble.append_text(chunk)
        self._scroll_to_bottom()

    def add_tool_call(self, tool_name: str, summary: str = ""):
        bubble = ToolCallBubble(tool_name, summary)
        self._insert_message(bubble)

    def add_diff_result(self, file_path: str, diff_text: str):
        """CC-aligned: show diff inline immediately after FileEdit/FileWrite."""
        # Count additions and deletions
        num_add = sum(1 for l in diff_text.splitlines() if l.startswith("+") and not l.startswith("+++"))
        num_del = sum(1 for l in diff_text.splitlines() if l.startswith("-") and not l.startswith("---"))
        bubble = DiffBubble(file_path, diff_text, num_add, num_del)
        self._insert_message(bubble)

    def add_interrupt_message(self):
        """Show a styled interruption indicator (distinct from tool calls)."""
        bubble = InterruptBubble()
        self._insert_message(bubble)

    def add_ask_user(self, question: str, options: list, multi_select: bool):
        """Insert an interactive AskUser bubble into the message flow."""
        bubble = AskUserBubble(question, options, multi_select)
        bubble.answered.connect(self.ask_user_answered.emit)
        self._insert_message(bubble)
        self._scroll_to_bottom()

    def set_plan_mode(self, active: bool):
        """Show or hide the plan mode badge."""
        if active:
            self._plan_badge.show()
        else:
            self._plan_badge.hide()

    def set_status(self, text: str):
        self._status.setText(f"<span style='color:rgba(255,255,255,80)'>{text}</span>")

    def set_thinking(self, thinking: bool):
        self._is_thinking = thinking
        if thinking:
            self._input.setEnabled(False)
            self._thinking.start()
            self.set_status("Thinking...")
            # Send button → Stop button
            self._send_btn.setText("■")
            self._send_btn.setToolTip("Stop generation")
            self._send_btn.setStyleSheet(f"""
                QPushButton {{
                    background: rgba(255,80,80,180);
                    color: white;
                    border: none;
                    border-radius: 18px;
                    font-size: 16px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: rgba(255,60,60,220);
                }}
            """)
            self._scroll_to_bottom()
        else:
            self._thinking.stop()
            self._input.setEnabled(True)
            self._send_btn.setEnabled(True)
            self._input.setFocus()
            self.set_status("Ready")
            # Stop button → Send button: restore default style explicitly
            self._send_btn.setText(">")
            self._send_btn.setToolTip("Send message")
            self._send_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {CLAUDE_ORANGE};
                    color: white;
                    border: none;
                    border-radius: 18px;
                    font-size: 18px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: {CLAUDE_ORANGE_SHIMMER};
                }}
            """)
            # Force immediate visual refresh
            self._send_btn.style().unpolish(self._send_btn)
            self._send_btn.style().polish(self._send_btn)
            self._send_btn.repaint()
            QApplication.processEvents()

    def show_near(self, anchor: QPoint):
        """Show the dialog. First time: screen center. After that: last position."""
        if not self._has_shown_once:
            self._has_shown_once = True
            self._center_on_screen()
        self.show()
        self.raise_()
        self._input.setFocus()

    def follow_anchor(self, anchor: QPoint):
        """No-op: chat dialog does not follow the pet."""
        pass

    def _position_near_anchor(self):
        """Place the dialog to the left of the pet, or right if no room."""
        anchor = self._anchor
        x = anchor.x() - self.width() - 16
        y = anchor.y() - self.height() // 2
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            if x < geo.left():
                x = anchor.x() + 140
            if y < geo.top():
                y = geo.top() + 10
            if y + self.height() > geo.bottom():
                y = geo.bottom() - self.height() - 10
        self.move(x, y)

    def _center_on_screen(self):
        """Place the dialog at the center of the primary screen."""
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = geo.x() + (geo.width() - self.width()) // 2
            y = geo.y() + (geo.height() - self.height()) // 2
            self.move(x, y)

    # ── Private ──────────────────────────────────────────────────────
    def _add_welcome(self):
        """Add initial welcome message."""
        welcome = MessageBubble(
            "Hi! I'm Claude Buddy, your desktop companion. "
            "Ask me anything or let me help with your code!",
            role="assistant",
        )
        self._insert_message(welcome)

    @staticmethod
    def _make_trash_icon():
        """Draw a simple trash can icon as QIcon."""
        from PyQt6.QtGui import QPixmap, QPainter, QPen, QIcon
        px = QPixmap(16, 16)
        px.fill(QColor(0, 0, 0, 0))
        p = QPainter(px)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(200, 200, 200))
        pen.setWidthF(1.4)
        p.setPen(pen)
        # Lid
        p.drawLine(3, 4, 13, 4)
        p.drawLine(6, 4, 6, 2)
        p.drawLine(6, 2, 10, 2)
        p.drawLine(10, 2, 10, 4)
        # Body
        p.drawLine(4, 4, 4, 13)
        p.drawLine(4, 13, 12, 13)
        p.drawLine(12, 13, 12, 4)
        # Inner lines
        p.drawLine(7, 6, 7, 11)
        p.drawLine(9, 6, 9, 11)
        p.end()
        return QIcon(px)

    def _clear_messages(self):
        """Remove all message bubbles from the UI (keep thinking + stretch)."""
        # The layout has: [msg0, msg1, ..., thinking_indicator, stretch]
        # Remove everything except the last 2 items
        while self._messages_layout.count() > 2:
            item = self._messages_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()
        self._streaming_bubble = None

    def _on_clear(self):
        """User clicked clear button — clear UI and emit signal."""
        self._clear_messages()
        self.clear_requested.emit()

    def _insert_message(self, widget):
        # Insert before the stretch (and before thinking indicator)
        idx = self._messages_layout.count() - 2  # before thinking + stretch
        if idx < 0:
            idx = 0
        self._messages_layout.insertWidget(idx, widget)
        self._scroll_to_bottom()

    def save_checkpoint(self):
        """Save the current message count so we can rollback on abort."""
        # Message widgets = layout count minus 2 (thinking indicator + stretch)
        self._checkpoint = max(0, self._messages_layout.count() - 2)

    def rollback_to_checkpoint(self):
        """Remove all message widgets added after the last checkpoint."""
        target = getattr(self, '_checkpoint', None)
        if target is None:
            return
        # Current message count (excluding thinking + stretch)
        current = self._messages_layout.count() - 2
        while current > target:
            item = self._messages_layout.takeAt(target)
            if item and item.widget():
                item.widget().deleteLater()
            current = self._messages_layout.count() - 2
        self._streaming_bubble = None

    def _on_send_or_abort(self):
        if self._is_thinking:
            self.abort_requested.emit()
        else:
            self._on_send()

    def _on_send(self):
        text = self._input.text().strip()
        if not text:
            return
        # Record to input history + persist
        if not self._input_history or self._input_history[-1] != text:
            self._input_history.append(text)
            self._save_input_history()
        self._history_index = -1
        self._saved_input = ""

        self._input.clear()
        self.add_user_message(text)
        self.message_sent.emit(text)

    def _load_input_history(self):
        """Load input history from disk on startup."""
        try:
            from config import INPUT_HISTORY_FILE
            if INPUT_HISTORY_FILE.exists():
                import json
                with open(INPUT_HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    self._input_history = data[-500:]  # keep last 500
        except Exception:
            pass

    def _save_input_history(self):
        """Persist input history to disk."""
        try:
            from config import INPUT_HISTORY_FILE
            import json
            # Keep last 500 entries
            to_save = self._input_history[-500:]
            with open(INPUT_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(to_save, f, ensure_ascii=False)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        """Intercept ↑/↓ on the input box for shell-like history navigation."""
        if obj is self._input and event.type() == event.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Up:
                self._history_navigate(-1)
                return True   # consumed
            elif key == Qt.Key.Key_Down:
                self._history_navigate(+1)
                return True
        return super().eventFilter(obj, event)

    def _history_navigate(self, direction: int):
        """Navigate input history. direction: -1 = older, +1 = newer."""
        if not self._input_history:
            return

        if self._history_index == -1:
            # Entering history mode: save current input
            self._saved_input = self._input.text()
            if direction == -1:
                self._history_index = len(self._input_history) - 1
            else:
                return  # already at newest, nothing to do
        else:
            new_index = self._history_index + direction
            if new_index < 0:
                # Already at oldest entry
                return
            if new_index >= len(self._input_history):
                # Past newest → restore saved input
                self._history_index = -1
                self._input.setText(self._saved_input)
                return
            self._history_index = new_index

        self._input.setText(self._input_history[self._history_index])

    def _scroll_to_bottom(self):
        if getattr(self, '_loading_history', False):
            return  # suppress during load_history to avoid scroll spam
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))

    def _title_mouse_press(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()

    def _title_mouse_move(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            pass  # user dragged dialog freely

    def mousePressEvent(self, event):
        """Start drag or edge resize."""
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._detect_edge(event.pos())
            if edge:
                self._resize_edge = edge
                self._drag_pos = event.globalPosition().toPoint()
            else:
                self._drag_pos = event.globalPosition().toPoint() - self.pos()
                self._resize_edge = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Handle drag move or edge resize, and update cursor shape."""
        if self._resize_edge and self._drag_pos:
            # Resizing
            delta = event.globalPosition().toPoint() - self._drag_pos
            self._drag_pos = event.globalPosition().toPoint()
            self._apply_resize(delta)
            pass
        elif self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            # Dragging
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            pass
        else:
            # Hover — update cursor
            edge = self._detect_edge(event.pos())
            if edge in ("left", "right"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif edge in ("top", "bottom"):
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            elif edge in ("top-left", "bottom-right"):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif edge in ("top-right", "bottom-left"):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        self._resize_edge = None
        super().mouseReleaseEvent(event)

    def _detect_edge(self, pos) -> str | None:
        """Detect which edge/corner the mouse is near."""
        m = self._resize_margin
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()

        on_left = x < m
        on_right = x > w - m
        on_top = y < m
        on_bottom = y > h - m

        if on_top and on_left:
            return "top-left"
        if on_top and on_right:
            return "top-right"
        if on_bottom and on_left:
            return "bottom-left"
        if on_bottom and on_right:
            return "bottom-right"
        if on_left:
            return "left"
        if on_right:
            return "right"
        if on_top:
            return "top"
        if on_bottom:
            return "bottom"
        return None

    def _apply_resize(self, delta):
        """Resize the window by the given delta based on the active edge."""
        geo = self.geometry()
        min_w, min_h = self.minimumWidth(), self.minimumHeight()

        if "right" in self._resize_edge:
            geo.setRight(max(geo.left() + min_w, geo.right() + delta.x()))
        if "bottom" in self._resize_edge:
            geo.setBottom(max(geo.top() + min_h, geo.bottom() + delta.y()))
        if "left" in self._resize_edge:
            new_left = min(geo.right() - min_w, geo.left() + delta.x())
            geo.setLeft(new_left)
        if "top" in self._resize_edge:
            new_top = min(geo.bottom() - min_h, geo.top() + delta.y())
            geo.setTop(new_top)

        self.setGeometry(geo)

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        else:
            super().keyPressEvent(event)
