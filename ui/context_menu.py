"""
Context Menu — right-click menu for the pet.
"""

from PyQt6.QtWidgets import QMenu
from PyQt6.QtGui import QAction
from PyQt6.QtCore import QPoint, pyqtSignal, QObject


class PetContextMenu(QObject):
    """Right-click context menu for the desktop pet."""

    chat_requested = pyqtSignal()
    task_panel_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    sleep_requested = pyqtSignal()
    wake_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

    def show_at(self, pos: QPoint):
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background: #373737;
                border: 1px solid #555;
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
                border-radius: 4px;
                color: white;
            }
            QMenu::item:selected {
                background: #D77757;
            }
            QMenu::separator {
                height: 1px;
                background: #555;
                margin: 4px 8px;
            }
        """)

        chat_action = menu.addAction("Chat...")
        chat_action.triggered.connect(self.chat_requested.emit)

        tasks_action = menu.addAction("Tasks...")
        tasks_action.triggered.connect(self.task_panel_requested.emit)

        menu.addSeparator()

        sleep_action = menu.addAction("Sleep")
        sleep_action.triggered.connect(self.sleep_requested.emit)

        wake_action = menu.addAction("Wake Up")
        wake_action.triggered.connect(self.wake_requested.emit)

        menu.addSeparator()

        settings_action = menu.addAction("Settings...")
        settings_action.triggered.connect(self.settings_requested.emit)

        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_requested.emit)

        menu.exec(pos)
