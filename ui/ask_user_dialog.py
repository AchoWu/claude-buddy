"""
AskUser Dialog — CC-aligned: clickable option chips + free-text input.

Layout:
  ┌─────────────────────────────────┐
  │  ❓ Buddy has a question        │
  │                                 │
  │  Which approach do you prefer?  │
  │                                 │
  │  ┌───────────┐ ┌───────────┐   │
  │  │ Option A  │ │ Option B  │   │
  │  └───────────┘ └───────────┘   │
  │  ┌───────────┐                  │
  │  │ Option C  │                  │
  │  └───────────┘                  │
  │                                 │
  │  ┌─────────────────────── ▶ ┐   │
  │  │  Or type your own...       │ │
  │  └────────────────────────────┘ │
  └─────────────────────────────────┘

- Click a chip → immediately submit that option
- Type text + Enter/click ▶ → submit custom text
- Multi-select: chips toggle on/off, submit button appears
"""

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QWidget, QSizePolicy, QCheckBox,
)
from PyQt6.QtGui import QFont

from config import (
    BG_DARK, BG_BUBBLE, TEXT_PRIMARY, TEXT_DIM,
    CLAUDE_ORANGE, BORDER_RADIUS,
)

# ── Colours ──────────────────────────────────────────────────
_CHIP_BG = "#3A3A3A"
_CHIP_BG_HOVER = "#484848"
_CHIP_BG_SELECTED = CLAUDE_ORANGE
_CHIP_BORDER = "#555"
_CHIP_BORDER_SELECTED = CLAUDE_ORANGE
_INPUT_BG = BG_BUBBLE


class _OptionChip(QPushButton):
    """A clickable option chip with label + optional description tooltip."""

    def __init__(self, label: str, description: str = "", parent=None):
        super().__init__(parent)
        self.label_text = label
        self.setText(label)
        if description:
            self.setToolTip(description)
        self.setCheckable(False)  # single-select: click = instant submit
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self._selected = False
        self._apply_style()

    def _apply_style(self):
        bg = _CHIP_BG_SELECTED if self._selected else _CHIP_BG
        border = _CHIP_BORDER_SELECTED if self._selected else _CHIP_BORDER
        text_color = "#fff" if self._selected else TEXT_PRIMARY
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg};
                color: {text_color};
                border: 1px solid {border};
                border-radius: 8px;
                padding: 8px 16px;
                font-size: 13px;
                text-align: left;
            }}
            QPushButton:hover {{
                background: {_CHIP_BG_SELECTED if self._selected else _CHIP_BG_HOVER};
                border-color: {CLAUDE_ORANGE};
            }}
        """)

    def set_selected(self, selected: bool):
        self._selected = selected
        self._apply_style()


class AskUserDialog(QDialog):
    """CC-aligned AskUser dialog: option chips + text input."""

    def __init__(self, question: str, options: list[dict],
                 multi_select: bool = False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Buddy needs your input")
        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setMinimumWidth(420)
        self.setMaximumWidth(560)
        self.setStyleSheet(f"""
            QDialog {{
                background: {BG_DARK};
                border: 1px solid {CLAUDE_ORANGE};
                border-radius: {BORDER_RADIUS}px;
            }}
        """)

        self._answer = ""
        # Normalize options
        raw = options or []
        self._options: list[dict] = []
        for opt in raw:
            if isinstance(opt, str):
                self._options.append({"label": opt})
            elif isinstance(opt, dict):
                self._options.append(opt)
        self._multi_select = multi_select
        self._chips: list[_OptionChip] = []
        self._selected_indices: set[int] = set()

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(18, 16, 18, 14)

        # ── Header ──────────────────────────────────────────────
        header = QLabel(f"❓ <b style='color:{CLAUDE_ORANGE}'>Buddy has a question</b>")
        header.setTextFormat(Qt.TextFormat.RichText)
        header.setStyleSheet(f"font-size: 14px; color: {TEXT_PRIMARY}; padding-bottom: 2px;")
        layout.addWidget(header)

        # ── Question ────────────────────────────────────────────
        q_label = QLabel(question)
        q_label.setWordWrap(True)
        q_label.setStyleSheet(f"""
            color: {TEXT_PRIMARY};
            font-size: 13px;
            padding: 4px 0 6px 0;
            line-height: 1.5;
        """)
        layout.addWidget(q_label)

        # ── Option chips (flow layout) ──────────────────────────
        if self._options:
            if multi_select:
                hint = QLabel("Select one or more options:")
            else:
                hint = QLabel("Click an option, or type below:")
            hint.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; padding: 0;")
            layout.addWidget(hint)

            chips_container = self._build_flow_chips()
            layout.addWidget(chips_container)

            # Show descriptions under chips if any option has one
            has_descs = any(opt.get("description") for opt in self._options)
            if has_descs:
                for opt in self._options:
                    desc = opt.get("description", "")
                    if desc:
                        d = QLabel(f"  • <b>{opt['label']}</b> — {desc}")
                        d.setTextFormat(Qt.TextFormat.RichText)
                        d.setWordWrap(True)
                        d.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px; padding: 0 4px;")
                        layout.addWidget(d)

        # ── Separator ───────────────────────────────────────────
        if self._options:
            sep = QFrame()
            sep.setFrameShape(QFrame.Shape.HLine)
            sep.setStyleSheet(f"background: #444; max-height: 1px; margin: 4px 0;")
            layout.addWidget(sep)

        # ── Text input row ──────────────────────────────────────
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self._text_input = QLineEdit()
        self._text_input.setPlaceholderText(
            "Or type your own answer..." if self._options else "Type your response..."
        )
        self._text_input.setStyleSheet(f"""
            QLineEdit {{
                background: {_INPUT_BG};
                color: {TEXT_PRIMARY};
                border: 1px solid #555;
                border-radius: 8px;
                padding: 9px 12px;
                font-size: 13px;
            }}
            QLineEdit:focus {{
                border-color: {CLAUDE_ORANGE};
            }}
        """)
        self._text_input.returnPressed.connect(self._submit_text)
        # Typing clears chip selection
        self._text_input.textChanged.connect(self._on_text_changed)
        input_row.addWidget(self._text_input)

        send_btn = QPushButton("▶")
        send_btn.setFixedSize(36, 36)
        send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        send_btn.setStyleSheet(f"""
            QPushButton {{
                background: {CLAUDE_ORANGE};
                color: white;
                border: none;
                border-radius: 18px;
                font-size: 14px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: #E8913A;
            }}
        """)
        send_btn.clicked.connect(self._submit_text)
        input_row.addWidget(send_btn)
        layout.addLayout(input_row)

        # ── Multi-select submit button ──────────────────────────
        if self._multi_select and self._options:
            self._submit_btn = QPushButton("Submit selected")
            self._submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._submit_btn.setEnabled(False)
            self._submit_btn.setStyleSheet(f"""
                QPushButton {{
                    background: {CLAUDE_ORANGE};
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 8px 20px;
                    font-size: 13px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background: #E8913A;
                }}
                QPushButton:disabled {{
                    background: #555;
                    color: #888;
                }}
            """)
            self._submit_btn.clicked.connect(self._submit_multi)
            layout.addWidget(self._submit_btn, alignment=Qt.AlignmentFlag.AlignRight)

        # Auto-focus text input if no options
        if not self._options:
            self._text_input.setFocus()

    # ── Flow layout for chips ────────────────────────────────────

    def _build_flow_chips(self) -> QWidget:
        """Build a vertical list of option chips."""
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(0, 4, 0, 4)
        outer.setSpacing(6)

        for idx, opt in enumerate(self._options):
            label = opt.get("label", "")
            desc = opt.get("description", "")

            chip = _OptionChip(label, desc)
            chip.setProperty("chip_index", idx)

            if self._multi_select:
                chip.clicked.connect(lambda checked, i=idx: self._toggle_chip(i))
            else:
                chip.clicked.connect(lambda checked, i=idx: self._select_chip(i))

            self._chips.append(chip)
            outer.addWidget(chip)

        return container

    # ── Chip interaction ─────────────────────────────────────────

    def _select_chip(self, index: int):
        """Single-select: click chip → immediately submit."""
        self._answer = self._options[index].get("label", "")
        self.accept()

    def _toggle_chip(self, index: int):
        """Multi-select: toggle chip on/off."""
        if index in self._selected_indices:
            self._selected_indices.discard(index)
            self._chips[index].set_selected(False)
        else:
            self._selected_indices.add(index)
            self._chips[index].set_selected(True)

        # Update submit button
        if hasattr(self, '_submit_btn'):
            n = len(self._selected_indices)
            self._submit_btn.setEnabled(n > 0)
            self._submit_btn.setText(f"Submit ({n} selected)" if n else "Submit selected")

    def _on_text_changed(self, text: str):
        """User started typing → clear chip selection (single-select only)."""
        if not self._multi_select and text.strip():
            self._selected_indices.clear()
            for chip in self._chips:
                chip.set_selected(False)

    # ── Submit ───────────────────────────────────────────────────

    def _submit_text(self):
        """Submit free-text input."""
        text = self._text_input.text().strip()
        if text:
            self._answer = text
            self.accept()

    def _submit_multi(self):
        """Submit multi-select: join selected chip labels."""
        labels = []
        for idx in sorted(self._selected_indices):
            labels.append(self._options[idx].get("label", ""))
        # Also include typed text if any
        typed = self._text_input.text().strip()
        if typed:
            labels.append(typed)
        if labels:
            self._answer = ", ".join(labels)
            self.accept()

    def get_answer(self) -> str:
        return self._answer
