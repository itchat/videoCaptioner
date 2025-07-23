from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit, QScrollArea
from PyQt5.QtCore import Qt
from config import OPENAI_CUSTOM_PROMPT


class ApiSettingsDialog(QDialog):
    def __init__(self, parent=None, api_settings=None):
        super().__init__(parent)
        self.api_settings = api_settings or {
            "base_url": "", 
            "api_key": "", 
            "model": "gpt-4.1",
            "custom_prompt": OPENAI_CUSTOM_PROMPT
        }
        self.initUI()

    def initUI(self):
        self.setWindowTitle("API Setting")
        self.setFixedSize(600, 700)  # 增加尺寸以容纳自定义prompt
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        # 主布局
        main_layout = QVBoxLayout(self)
        
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # 滚动内容的容器
        scroll_widget = QDialog()
        layout = QVBoxLayout(scroll_widget)

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

        # Custom Prompt
        self.prompt_label = QLabel("Custom Translation Prompt", self)
        self.prompt_text = QTextEdit(self)
        self.prompt_text.setPlainText(self.api_settings.get("custom_prompt", ""))
        self.prompt_text.setStyleSheet(
            "QTextEdit { color: white; background-color: #333; font-family: monospace; }"
        )
        self.prompt_text.setMinimumHeight(200)
        self.prompt_text.setMaximumHeight(300)
        form_layout.addWidget(self.prompt_label)
        form_layout.addWidget(self.prompt_text)

        # Reset to Default Button
        self.reset_prompt_button = QPushButton("Reset to Default", self)
        self.reset_prompt_button.clicked.connect(self.reset_prompt_to_default)
        self.reset_prompt_button.setStyleSheet(
            "QPushButton { background-color: #555; color: white; padding: 5px; }"
        )
        form_layout.addWidget(self.reset_prompt_button)

        # Save Button
        self.save_button = QPushButton("Save", self)
        self.save_button.clicked.connect(self.save_settings)
        form_layout.addWidget(self.save_button)

        layout.addLayout(form_layout)
        
        # 设置滚动区域
        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)
    
    def reset_prompt_to_default(self):
        """重置prompt为默认值"""
        # 重新导入config以获取最新的默认prompt
        import config
        config.load_config()  # 确保获取最新的配置
        self.prompt_text.setPlainText(config.OPENAI_CUSTOM_PROMPT)

    def save_settings(self):
        # Get the values from the input fields
        base_url = self.base_url_input.text().strip()
        api_key = self.api_key_input.text().strip()
        model = self.model_combo.currentText().strip()
        custom_prompt = self.prompt_text.toPlainText().strip()

        # Update the settings dictionary
        self.api_settings["base_url"] = base_url
        self.api_settings["api_key"] = api_key
        self.api_settings["model"] = model
        self.api_settings["custom_prompt"] = custom_prompt

        # Accept the dialog (close with success)
        self.accept()
