from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox
from PyQt5.QtCore import Qt


class ApiSettingsDialog(QDialog):
    def __init__(self, parent=None, api_settings=None):
        super().__init__(parent)
        self.api_settings = api_settings or {"base_url": "", "api_key": "", "model": "gpt-4.1"}
        self.initUI()

    def initUI(self):
        self.setWindowTitle("API Setting")
        self.setFixedSize(420, 350)  # 增加高度以容纳模型选择
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

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
        self.base_url_input.setStyleSheet(
            "QLineEdit { color: white; background-color: #333; }"
        )
        self.base_url_input.setFocus()
        form_layout.addWidget(self.base_url_label)
        form_layout.addWidget(self.base_url_input)

        self.api_key_label = QLabel("API Key", self)
        self.api_key_input = QLineEdit(self)
        # Set your default api_key here
        self.api_key_input.setText(self.api_settings.get("api_key", ""))
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("Type in API Key")
        self.api_key_input.setStyleSheet(
            "QLineEdit { color: white; background-color: #333; }"
        )
        form_layout.addWidget(self.api_key_label)
        form_layout.addWidget(self.api_key_input)

        # Model selection
        self.model_label = QLabel("Model", self)
        self.model_combo = QComboBox(self)
        # 添加常用的 GPT 模型选项
        models = [
            "gpt-4.1",
            "gpt-4o",
            "gpt-4o-mini", 
            "gpt-4-turbo",
            "gpt-4",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-16k"
        ]
        self.model_combo.addItems(models)
        self.model_combo.setEditable(True)  # 允许用户输入自定义模型
        # 设置当前模型
        current_model = self.api_settings.get("model", "gpt-4.1")
        if current_model in models:
            self.model_combo.setCurrentText(current_model)
        else:
            # 如果是自定义模型，添加到列表并选中
            self.model_combo.addItem(current_model)
            self.model_combo.setCurrentText(current_model)
        
        self.model_combo.setStyleSheet(
            "QComboBox { color: white; background-color: #333; }"
            "QComboBox::drop-down { background-color: #333; }"
            "QComboBox::down-arrow { color: white; }"
        )
        form_layout.addWidget(self.model_label)
        form_layout.addWidget(self.model_combo)

        # Save Button
        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.save_settings)
        form_layout.addWidget(self.save_button)

        layout.addLayout(form_layout)

    def save_settings(self):
        # Get the values from the input fields
        base_url = self.base_url_input.text().strip()
        api_key = self.api_key_input.text().strip()
        model = self.model_combo.currentText().strip()

        # Update the settings dictionary
        self.api_settings["base_url"] = base_url
        self.api_settings["api_key"] = api_key
        self.api_settings["model"] = model

        # Accept the dialog (close with success)
        self.accept()
