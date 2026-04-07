"""
System Tray Icon — QSystemTrayIcon with menu for the pet.
"""

from PyQt6.QtWidgets import QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtCore import pyqtSignal, QObject

from config import SPRITES_DIR, CLAUDE_ORANGE, APP_NAME, CHARACTERS_DIR, DEFAULT_CHARACTER


def _create_tray_icon(character: str = DEFAULT_CHARACTER) -> QIcon:
    """Load tray icon from the current character's idle sprite, or generate a fallback."""
    # Try character's idle_0.png first (matches the desktop pet)
    char_icon = CHARACTERS_DIR / character / "idle_0.png"
    if char_icon.exists():
        return QIcon(str(char_icon))
    # Fallback: old top-level icon.png
    icon_path = SPRITES_DIR / "icon.png"
    if icon_path.exists():
        return QIcon(str(icon_path))
    # Last resort: orange circle
    px = QPixmap(32, 32)
    px.fill(QColor(0, 0, 0, 0))
    p = QPainter(px)
    p.setBrush(QColor(CLAUDE_ORANGE))
    p.setPen(QColor(0, 0, 0, 0))
    p.drawEllipse(2, 2, 28, 28)
    p.end()
    return QIcon(px)


class SystemTray(QObject):
    """System tray icon with context menu."""

    show_pet_requested = pyqtSignal()
    hide_pet_requested = pyqtSignal()
    chat_requested = pyqtSignal()
    task_panel_requested = pyqtSignal()
    settings_requested = pyqtSignal()
    quit_requested = pyqtSignal()

    def __init__(self, character: str = DEFAULT_CHARACTER, parent=None):
        super().__init__(parent)
        self._character = character

        self._tray = QSystemTrayIcon(parent)
        self._tray.setIcon(_create_tray_icon(character))
        self._tray.setToolTip(APP_NAME)

        # Build menu
        menu = QMenu()
        menu.setStyleSheet("""
            QMenu {
                background: #373737;
                border: 1px solid #555;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 24px 6px 12px;
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

        show_action = menu.addAction("Show Pet")
        show_action.triggered.connect(self.show_pet_requested.emit)

        hide_action = menu.addAction("Hide Pet")
        hide_action.triggered.connect(self.hide_pet_requested.emit)

        menu.addSeparator()

        chat_action = menu.addAction("Chat...")
        chat_action.triggered.connect(self.chat_requested.emit)

        tasks_action = menu.addAction("Tasks...")
        tasks_action.triggered.connect(self.task_panel_requested.emit)

        menu.addSeparator()

        settings_action = menu.addAction("Settings...")
        settings_action.triggered.connect(self.settings_requested.emit)

        menu.addSeparator()

        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_requested.emit)

        self._tray.setContextMenu(menu)

        # Double-click tray icon → show pet
        self._tray.activated.connect(self._on_activated)

    def show(self):
        self._tray.show()

    def show_message(self, title: str, message: str):
        self._tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 5000)

    def set_character(self, character: str):
        """Update tray icon to match the current character."""
        self._character = character
        self._tray.setIcon(_create_tray_icon(character))

    def _on_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.show_pet_requested.emit()
