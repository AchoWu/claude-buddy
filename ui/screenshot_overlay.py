"""
Screenshot Overlay — full-screen transparent overlay for region selection.

User drags to select a rectangle, ESC to cancel.
Similar to Windows Snipping Tool / Win+Shift+S experience.
"""

from PyQt6.QtCore import Qt, QRect, QPoint, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QMouseEvent, QKeyEvent, QFont
from PyQt6.QtWidgets import QWidget, QApplication

from config import CLAUDE_ORANGE


class ScreenshotOverlay(QWidget):
    """Full-screen semi-transparent overlay for drawing a selection rectangle."""

    region_selected = pyqtSignal(QRect)   # user completed selection
    cancelled = pyqtSignal()               # user pressed ESC or right-clicked

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)

        self._start_pos: QPoint | None = None
        self._current_pos: QPoint | None = None
        self._selecting = False

    def start_selection(self):
        """Show overlay full-screen and wait for user to draw a region."""
        # Cover the entire virtual desktop (all screens)
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.virtualGeometry()
            self.setGeometry(geo)

        self._start_pos = None
        self._current_pos = None
        self._selecting = False

        self.showFullScreen()
        self.raise_()
        self.activateWindow()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Semi-transparent dark overlay covering entire screen
        painter.fillRect(self.rect(), QColor(0, 0, 0, 120))

        if self._start_pos and self._current_pos:
            rect = QRect(self._start_pos, self._current_pos).normalized()

            # Clear the selected area (make it bright/transparent)
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_Clear
            )
            painter.fillRect(rect, QColor(0, 0, 0, 0))

            # Switch back to normal mode for drawing border
            painter.setCompositionMode(
                QPainter.CompositionMode.CompositionMode_SourceOver
            )

            # Draw selection border (Claude orange)
            pen = QPen(QColor(CLAUDE_ORANGE), 2, Qt.PenStyle.SolidLine)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

            # Show dimensions label
            dims_text = f"{rect.width()} × {rect.height()}"
            font = QFont("Segoe UI", 11)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))

            # Position label below selection or above if near bottom
            label_x = rect.right() - 80
            label_y = rect.bottom() + 20
            if label_y > self.height() - 30:
                label_y = rect.top() - 10

            painter.drawText(QPoint(label_x, label_y), dims_text)

        else:
            # Show hint text when no selection started
            painter.setPen(QColor(255, 255, 255, 200))
            font = QFont("Segoe UI", 14)
            painter.setFont(font)
            hint = "拖拽选择截屏区域  |  ESC 取消"
            text_rect = painter.fontMetrics().boundingRect(hint)
            x = (self.width() - text_rect.width()) // 2
            y = self.height() // 2
            painter.drawText(QPoint(x, y), hint)

        painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._start_pos = event.position().toPoint()
            self._current_pos = self._start_pos
            self._selecting = True
            self.update()
        elif event.button() == Qt.MouseButton.RightButton:
            # Right-click cancels
            self._cancel()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._selecting:
            self._current_pos = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._selecting:
            self._selecting = False
            end_pos = event.position().toPoint()
            rect = QRect(self._start_pos, end_pos).normalized()
            self.hide()

            # Only emit if selection is meaningful (> 10x10 pixels)
            if rect.width() > 10 and rect.height() > 10:
                # Convert to global coordinates for screen capture
                global_rect = QRect(
                    self.mapToGlobal(rect.topLeft()),
                    rect.size(),
                )
                self.region_selected.emit(global_rect)
            else:
                self.cancelled.emit()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Escape:
            self._cancel()

    def _cancel(self):
        """Hide overlay and emit cancelled signal."""
        self._selecting = False
        self._start_pos = None
        self._current_pos = None
        self.hide()
        self.cancelled.emit()
