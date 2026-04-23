"""
Settings Dialog — configure API provider, model, and behavior.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QLineEdit, QComboBox, QFormLayout, QCheckBox,
)

from config import (
    BG_DARK, BG_BUBBLE, BG_INPUT, TEXT_PRIMARY, TEXT_DIM,
    CLAUDE_ORANGE, BORDER_RADIUS, ERROR_RED, CHARACTERS_DIR,
)
from core.settings import Settings, PROVIDER_PRESETS


class SettingsDialog(QWidget):
    """Settings panel for API configuration and pet behavior."""

    settings_changed = pyqtSignal()  # emitted when user saves

    def __init__(self, settings: Settings, parent=None):
        super().__init__(parent)
        self._settings = settings

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(440, 580)

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
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel(f"<b style='color:{CLAUDE_ORANGE}'>Settings</b>")
        title.setTextFormat(Qt.TextFormat.RichText)
        title.setStyleSheet("font-size: 15px;")
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton("X")
        close_btn.setObjectName("closeBtn")
        close_btn.setFixedSize(32, 32)
        close_btn.clicked.connect(self.hide)
        header.addWidget(close_btn)
        layout.addLayout(header)

        # Form
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        label_style = f"color: {TEXT_DIM}; font-size: 12px;"

        # Provider dropdown
        self._provider_combo = QComboBox()
        self._provider_combo.setStyleSheet(f"""
            QComboBox {{
                background: {BG_INPUT};
                color: {TEXT_PRIMARY};
                border: 1px solid #555;
                border-radius: 6px;
                padding: 6px 10px;
            }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background: {BG_BUBBLE};
                color: {TEXT_PRIMARY};
                selection-background-color: {CLAUDE_ORANGE};
            }}
        """)
        for key, preset in PROVIDER_PRESETS.items():
            self._provider_combo.addItem(preset["label"], key)

        self._provider_combo.currentIndexChanged.connect(self._on_provider_changed)

        provider_label = QLabel("Provider")
        provider_label.setStyleSheet(label_style)
        form.addRow(provider_label, self._provider_combo)

        # API Key
        self._api_key_input = QLineEdit()
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setPlaceholderText("sk-...")

        api_label = QLabel("API Key")
        api_label.setStyleSheet(label_style)
        form.addRow(api_label, self._api_key_input)

        # Base URL
        self._base_url_input = QLineEdit()
        self._base_url_input.setPlaceholderText("https://api.example.com/v1")

        url_label = QLabel("Base URL")
        url_label.setStyleSheet(label_style)
        form.addRow(url_label, self._base_url_input)

        # Model
        self._model_input = QLineEdit()
        self._model_input.setPlaceholderText("Model name")

        model_label = QLabel("Model")
        model_label.setStyleSheet(label_style)
        form.addRow(model_label, self._model_input)

        # Permission mode
        self._perm_combo = QComboBox()
        self._perm_combo.setStyleSheet(self._provider_combo.styleSheet())
        self._perm_combo.addItem("Default (Ask)", "default")
        self._perm_combo.addItem("Auto (Smart approve)", "auto")
        self._perm_combo.addItem("Bypass (No prompts)", "bypass")

        perm_label = QLabel("Permissions")
        perm_label.setStyleSheet(label_style)
        form.addRow(perm_label, self._perm_combo)

        # Streaming toggle
        self._streaming_check = QCheckBox("Enable Streaming")
        self._streaming_check.setStyleSheet(f"""
            QCheckBox {{
                color: {TEXT_PRIMARY};
                font-size: 12px;
                spacing: 8px;
            }}
            QCheckBox::indicator {{
                width: 16px; height: 16px;
                border: 1px solid #555;
                border-radius: 3px;
                background: {BG_INPUT};
            }}
            QCheckBox::indicator:checked {{
                background: {CLAUDE_ORANGE};
                border-color: {CLAUDE_ORANGE};
            }}
        """)
        streaming_label = QLabel("Streaming")
        streaming_label.setStyleSheet(label_style)
        form.addRow(streaming_label, self._streaming_check)

        # Thinking / Reasoning toggle (unified: Anthropic thinking + OpenAI/OpenRouter reasoning)
        self._thinking_check = QCheckBox("Enable Thinking / Reasoning")
        self._thinking_check.setStyleSheet(self._streaming_check.styleSheet())
        self._thinking_check.setToolTip(
            "Enables extended reasoning on supported providers:\n"
            "- Anthropic: sends thinking parameter\n"
            "- OpenAI / OpenRouter: sends reasoning parameter"
        )
        thinking_label = QLabel("Thinking")
        thinking_label.setStyleSheet(label_style)
        form.addRow(thinking_label, self._thinking_check)

        # Character selector
        self._char_combo = QComboBox()
        self._char_combo.setStyleSheet(self._provider_combo.styleSheet())
        # Discover available characters from filesystem
        if CHARACTERS_DIR.exists():
            for d in sorted(CHARACTERS_DIR.iterdir()):
                if d.is_dir() and (d / "idle_0.png").exists():
                    display_name = d.name.replace("_", " ").title()
                    self._char_combo.addItem(display_name, d.name)
        if self._char_combo.count() == 0:
            self._char_combo.addItem("Default", "buddy")

        char_label = QLabel("Character")
        char_label.setStyleSheet(label_style)
        form.addRow(char_label, self._char_combo)

        layout.addLayout(form)
        layout.addStretch()

        # Save button
        save_btn = QPushButton("Save Settings")
        save_btn.setFixedHeight(36)
        save_btn.clicked.connect(self._on_save)
        layout.addWidget(save_btn)

        # Load current settings
        self._load_settings()

        # Drag support
        self._drag_pos = None

    def _load_settings(self):
        # Set provider combo
        provider = self._settings.provider
        for i in range(self._provider_combo.count()):
            if self._provider_combo.itemData(i) == provider:
                self._provider_combo.setCurrentIndex(i)
                break

        self._api_key_input.setText(self._settings.api_key)
        self._base_url_input.setText(self._settings.base_url)
        self._model_input.setText(self._settings.model)

        perm = self._settings.permission_mode
        for i in range(self._perm_combo.count()):
            if self._perm_combo.itemData(i) == perm:
                self._perm_combo.setCurrentIndex(i)
                break

        self._streaming_check.setChecked(self._settings.streaming_enabled)
        self._thinking_check.setChecked(self._settings.thinking_enabled)

        # Set character combo
        char = self._settings.character
        for i in range(self._char_combo.count()):
            if self._char_combo.itemData(i) == char:
                self._char_combo.setCurrentIndex(i)
                break

    def _on_provider_changed(self, index: int):
        key = self._provider_combo.itemData(index)
        preset = PROVIDER_PRESETS.get(key, {})

        if preset.get("base_url"):
            self._base_url_input.setText(preset["base_url"])
        else:
            self._base_url_input.clear()

        if preset.get("default_model"):
            self._model_input.setText(preset["default_model"])
        else:
            self._model_input.clear()

        needs_key = preset.get("needs_api_key", True)
        needs_url = preset.get("needs_base_url", False)

        self._api_key_input.setEnabled(needs_key)
        self._base_url_input.setEnabled(needs_url)
        self._model_input.setEnabled(True)
        self._api_key_input.setPlaceholderText("sk-..." if needs_key else "(not needed)")
        self._model_input.setPlaceholderText("model name")

    def _on_save(self):
        self._settings.provider = self._provider_combo.currentData()
        self._settings.api_key = self._api_key_input.text().strip()
        self._settings.base_url = self._base_url_input.text().strip()
        self._settings.model = self._model_input.text().strip()
        self._settings.permission_mode = self._perm_combo.currentData()
        self._settings.streaming_enabled = self._streaming_check.isChecked()
        self._settings.thinking_enabled = self._thinking_check.isChecked()
        self._settings.character = self._char_combo.currentData()

        self.settings_changed.emit()
        self.hide()

    def show_centered(self):
        from PyQt6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geo = screen.availableGeometry()
            x = (geo.width() - self.width()) // 2
            y = (geo.height() - self.height()) // 2
            self.move(x, y)
        self.show()
        self.raise_()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.pos()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
        super().keyPressEvent(event)
