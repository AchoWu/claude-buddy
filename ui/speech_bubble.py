"""
Speech Bubble — floating tooltip-like bubble above the pet.
Follows the pet when dragged.
"""

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PyQt6.QtGui import QPainter, QColor, QPainterPath
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QGraphicsOpacityEffect

from config import (
    BG_BUBBLE, TEXT_PRIMARY, BORDER_RADIUS,
    BUBBLE_SHOW_SEC, BUBBLE_FADE_SEC,
)


class SpeechBubble(QWidget):
    """Semi-transparent speech bubble that appears above the pet and follows it."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMaximumWidth(320)

        # Content label
        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setStyleSheet(f"""
            QLabel {{
                color: {TEXT_PRIMARY};
                background: {BG_BUBBLE};
                border-radius: {BORDER_RADIUS}px;
                padding: 12px 16px;
                font-size: 13px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 16)  # extra bottom for arrow
        layout.addWidget(self._label)

        # Opacity effect for fade-out
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

        # Current anchor (pet's top-center global position)
        self._anchor = QPoint(0, 0)

        # Timers
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._start_fade)

        self._fade_anim: QPropertyAnimation | None = None

    def show_message(self, text: str, anchor: QPoint, duration_sec: float = BUBBLE_SHOW_SEC):
        """
        Show bubble with text, anchored above the given point.
        anchor: global position of the pet's top-center.
        """
        self._anchor = anchor
        self._label.setText(text)
        self._label.adjustSize()
        self.adjustSize()

        self._reposition()

        # Reset opacity
        self._opacity.setOpacity(1.0)
        self.show()
        self.raise_()

        # Schedule hide
        fade_start = max(0, duration_sec - BUBBLE_FADE_SEC)
        self._hide_timer.start(int(fade_start * 1000))

    def follow_anchor(self, anchor: QPoint):
        """Reposition bubble when the pet moves. Called from pet_moved signal."""
        self._anchor = anchor
        if self.isVisible():
            self._reposition()

    def _reposition(self):
        """Place the bubble centered above the anchor point."""
        x = self._anchor.x() - self.width() // 2
        y = self._anchor.y() - self.height() - 8
        self.move(x, y)

    def _start_fade(self):
        self._fade_anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._fade_anim.setDuration(int(BUBBLE_FADE_SEC * 1000))
        self._fade_anim.setStartValue(1.0)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._fade_anim.finished.connect(self.hide)
        self._fade_anim.start()

    def paintEvent(self, event):
        """Draw the triangle arrow at bottom-center pointing down."""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(BG_BUBBLE))
        painter.setPen(Qt.PenStyle.NoPen)

        # Triangle arrow
        cx = self.width() // 2
        bottom = self.height()
        path = QPainterPath()
        path.moveTo(cx - 8, bottom - 16)
        path.lineTo(cx, bottom - 4)
        path.lineTo(cx + 8, bottom - 16)
        path.closeSubpath()
        painter.drawPath(path)
        painter.end()
