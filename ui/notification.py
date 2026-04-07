"""
Notification — toast notification queue with stacking support.
Multiple notifications display stacked vertically above the pet.
"""

from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PyQt6.QtWidgets import QWidget, QLabel, QVBoxLayout, QGraphicsOpacityEffect

from config import (
    BG_BUBBLE, TEXT_PRIMARY, CLAUDE_ORANGE, SUCCESS_GREEN,
    ERROR_RED, BORDER_RADIUS, NOTIFICATION_SHOW_SEC,
)

# Import notification templates
from prompts.templates import (
    TASK_COMPLETED_TEMPLATE, TASK_CREATED_TEMPLATE,
    TOOL_EXECUTING_TEMPLATE, ERROR_TEMPLATE,
)

MAX_VISIBLE_TOASTS = 3
TOAST_STACK_GAP = 8  # px between stacked toasts


class ToastNotification(QWidget):
    """Single toast notification card with auto-dismiss and fade animation."""

    def __init__(self, on_dismissed=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMaximumWidth(300)

        self._on_dismissed = on_dismissed  # callback when toast is done

        self._label = QLabel(self)
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setStyleSheet(f"""
            QLabel {{
                background: {BG_BUBBLE};
                color: {TEXT_PRIMARY};
                border-radius: 8px;
                border-left: 3px solid {CLAUDE_ORANGE};
                padding: 10px 14px;
                font-size: 12px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)

        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

        self._fade_timer = QTimer(self)
        self._fade_timer.setSingleShot(True)
        self._fade_timer.timeout.connect(self._fade_out)

        self._anim: QPropertyAnimation | None = None

    def show_at(self, text: str, pos: QPoint, color: str = CLAUDE_ORANGE,
                duration_sec: float = NOTIFICATION_SHOW_SEC):
        self._label.setText(text)
        self._label.setStyleSheet(f"""
            QLabel {{
                background: {BG_BUBBLE};
                color: {TEXT_PRIMARY};
                border-radius: 8px;
                border-left: 3px solid {color};
                padding: 10px 14px;
                font-size: 12px;
            }}
        """)
        self._label.adjustSize()
        self.adjustSize()

        x = pos.x() - self.width() // 2
        y = pos.y() - self.height() - 8
        self.move(x, y)

        self._opacity.setOpacity(1.0)
        self.show()
        self.raise_()

        fade_start = max(0, duration_sec - 2)
        self._fade_timer.start(int(fade_start * 1000))

    def _fade_out(self):
        self._anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._anim.setDuration(2000)
        self._anim.setStartValue(1.0)
        self._anim.setEndValue(0.0)
        self._anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        self._anim.finished.connect(self._on_fade_done)
        self._anim.start()

    def _on_fade_done(self):
        self.hide()
        self.deleteLater()
        if self._on_dismissed:
            self._on_dismissed(self)


class NotificationQueue:
    """
    Queue of toast notifications with stacking support.
    Shows up to MAX_VISIBLE_TOASTS simultaneously, stacked vertically.
    New notifications push older ones up.
    """

    def __init__(self):
        self._active: list[ToastNotification] = []
        self._pending: list[tuple[str, str]] = []  # (text, color)
        self._anchor = QPoint(0, 0)

    def set_anchor(self, anchor: QPoint):
        self._anchor = anchor

    def show(self, text: str, color: str = CLAUDE_ORANGE):
        """Show a notification. If at max, queue it."""
        if len(self._active) >= MAX_VISIBLE_TOASTS:
            self._pending.append((text, color))
            return
        self._show_toast(text, color)

    def show_success(self, text: str):
        self.show(text, SUCCESS_GREEN)

    def show_error(self, text: str):
        self.show(text, ERROR_RED)

    # ── Convenience methods using templates ──────────────────────────

    def notify_task_created(self, subject: str):
        self.show(TASK_CREATED_TEMPLATE.format(subject=subject), CLAUDE_ORANGE)

    def notify_task_completed(self, subject: str):
        self.show_success(TASK_COMPLETED_TEMPLATE.format(subject=subject))

    def notify_tool_executing(self, tool_name: str):
        self.show(TOOL_EXECUTING_TEMPLATE.format(tool_name=tool_name), CLAUDE_ORANGE)

    def notify_error(self, message: str):
        self.show_error(ERROR_TEMPLATE.format(message=message[:100]))

    # ── Internal ─────────────────────────────────────────────────────

    def _show_toast(self, text: str, color: str):
        toast = ToastNotification(on_dismissed=self._on_toast_dismissed)
        self._active.append(toast)
        self._reposition_all()

        # Position this toast at its slot
        slot_index = len(self._active) - 1
        pos = self._slot_position(slot_index, toast)
        toast.show_at(text, pos, color)

    def _on_toast_dismissed(self, toast: ToastNotification):
        """A toast finished its fade — remove and show next pending."""
        if toast in self._active:
            self._active.remove(toast)
        self._reposition_all()

        # Show next pending notification
        if self._pending and len(self._active) < MAX_VISIBLE_TOASTS:
            text, color = self._pending.pop(0)
            self._show_toast(text, color)

    def _reposition_all(self):
        """Reposition all active toasts so they stack correctly."""
        y_offset = 0
        for i, toast in enumerate(reversed(self._active)):
            x = self._anchor.x() - toast.width() // 2
            y = self._anchor.y() - y_offset - toast.height() - 8
            toast.move(x, y)
            y_offset += toast.height() + TOAST_STACK_GAP

    def _slot_position(self, index: int, toast: ToastNotification) -> QPoint:
        """Calculate position for a toast at the given stack index."""
        y_offset = 0
        for i in range(index):
            if i < len(self._active):
                y_offset += self._active[i].height() + TOAST_STACK_GAP
        return QPoint(
            self._anchor.x(),
            self._anchor.y() - y_offset,
        )
