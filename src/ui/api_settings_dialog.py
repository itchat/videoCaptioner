from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel,
    QLineEdit, QPushButton
)
from PyQt5.QtCore import Qt


class ApiSettingsDialog(QDialog):
    def __init__(self, parent=None, api_settings=None):
        super().__init__(parent)
        self.api_settings = api_settings or {"base_url": "", "api_key": ""}
        self.initUI()

    def initUI(self):
        self.setWindowTitle("API Setting")
        self.setFixedSize(420, 280)

        layout = QVBoxLayout(self)

        self.title_label = QLabel("API Setting", self)
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)

        form_layout = QVBoxLayout()
        form_layout.setSpacing(15)

        # Base URL
        self.base_url_label = QLabel("Base URL", self)
        self.base_url_input = QLineEdit(self)
        # Set your default base_url here
        self.base_url_input.setText(self.api_settings.get("base_url", ""))
        self.base_url_input.setPlaceholderText("Type in Base URL")
        self.base_url_input.setStyleSheet("QLineEdit { color: white; }")
        form_layout.addWidget(self.base_url_label)
        form_layout.addWidget(self.base_url_input)

        self.api_key_label = QLabel("API Key", self)
        self.api_key_input = QLineEdit(self)
        self.api_key_input.setText(
        # Set your default api_key here
        self.api_settings.get("api_key", ""))
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("Type in API Key")
        self.api_key_input.setStyleSheet("QLineEdit { color: white; }")
        form_layout.addWidget(self.api_key_label)
        form_layout.addWidget(self.api_key_input)

        # Save Button
        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.save_settings)
        form_layout.addWidget(self.save_button)

        layout.addLayout(form_layout)

    def save_settings(self):
        self.api_settings["base_url"] = self.base_url_input.text()
        self.api_settings["api_key"] = self.api_key_input.text()
        self.accept()
