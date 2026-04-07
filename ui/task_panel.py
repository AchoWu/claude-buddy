"""
Task Panel — displays task list in a side panel.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea,
)

from config import (
    BG_DARK, BG_BUBBLE, TEXT_PRIMARY, TEXT_DIM,
    CLAUDE_ORANGE, SUCCESS_GREEN, BORDER_RADIUS, WARNING_AMBER,
)


class TaskItem(QFrame):
    """Single task row."""

    def __init__(self, task_data: dict, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)

        status = task_data.get("status", "pending")
        icon = {"pending": "⬜", "in_progress": "🔄", "completed": "✅"}.get(status, "⬜")
        color = {"pending": TEXT_DIM, "in_progress": WARNING_AMBER, "completed": SUCCESS_GREEN}.get(status, TEXT_DIM)

        self.setStyleSheet(f"""
            QFrame {{
                background: {BG_BUBBLE};
                border-radius: 6px;
                border-left: 3px solid {color};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)

        label = QLabel(f"{icon}  <b>#{task_data.get('id', '?')}</b>  {task_data.get('subject', '')}")
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 12px; background: transparent;")
        label.setWordWrap(True)
        layout.addWidget(label, 1)

        status_label = QLabel(status)
        status_label.setStyleSheet(f"color: {color}; font-size: 11px; background: transparent;")
        layout.addWidget(status_label)


class TaskPanel(QWidget):
    """Side panel showing all tasks."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(350, 450)

        # Container
        container = QFrame(self)
        container.setStyleSheet(f"""
            QFrame {{
                background: {BG_DARK};
                border-radius: {BORDER_RADIUS}px;
                border: 1px solid #444;
            }}
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # Header
        header = QHBoxLayout()
        title = QLabel(f"<b style='color:{CLAUDE_ORANGE}'>Tasks</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton("X")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(28, 28)
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)
        layout.addLayout(header)

        # Task list scroll area
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setStyleSheet(f"QScrollArea {{ background: {BG_DARK}; border: none; }}")

        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(4)
        self._list_layout.addStretch()

        self._scroll.setWidget(self._list_widget)
        layout.addWidget(self._scroll, 1)

        # Empty state
        self._empty_label = QLabel(f"<span style='color:{TEXT_DIM}'>No tasks yet.</span>")
        self._empty_label.setTextFormat(Qt.TextFormat.RichText)
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._empty_label)

    def refresh(self, tasks: list[dict]):
        """Refresh the task list."""
        # Clear existing items (except the stretch)
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._empty_label.setVisible(len(tasks) == 0)

        for task in tasks:
            item = TaskItem(task)
            self._list_layout.insertWidget(self._list_layout.count() - 1, item)

    def show_near(self, anchor):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        x = anchor.x() + 140
        y = anchor.y() - self.height() // 2
        if screen:
            geo = screen.availableGeometry()
            if x + self.width() > geo.right():
                x = anchor.x() - self.width() - 16
            y = max(geo.top() + 10, min(y, geo.bottom() - self.height() - 10))
        self.move(x, y)
        self.show()
        self.raise_()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        super().keyPressEvent(event)
