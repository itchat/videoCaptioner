from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit, QScrollArea, QSpinBox, QMessageBox
from PyQt6.QtCore import Qt
from config import OPENAI_CUSTOM_PROMPT, DEFAULT_CUSTOM_PROMPT, DEFAULT_MAX_CHARS_PER_BATCH, DEFAULT_MAX_ENTRIES_PER_BATCH


class ApiSettingsDialog(QDialog):
    def __init__(self, parent=None, api_settings=None):
        super().__init__(parent)
        self.api_settings = api_settings or {
            "base_url": "https://api.openai.com", 
            "api_key": "", 
            "model": "gpt-4.1-nano",
            "custom_prompt": OPENAI_CUSTOM_PROMPT,
            "max_chars_per_batch": DEFAULT_MAX_CHARS_PER_BATCH,
            "max_entries_per_batch": DEFAULT_MAX_ENTRIES_PER_BATCH
        }
        self.initUI()

    def initUI(self):
        self.setWindowTitle("API Setting")
        self.setFixedSize(600, 800)  # 增加高度以容纳新的批处理参数
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # 主布局
        main_layout = QVBoxLayout(self)
        
        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # 滚动内容的容器
        scroll_widget = QDialog()
        layout = QVBoxLayout(scroll_widget)

        self.title_label = QLabel("API Setting", self)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
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
            "gpt-4.1-mini",
            "gpt-4o-mini",
            "gpt-4.1-nano"
        ]
        self.model_combo.addItems(models)
        self.model_combo.setEditable(True)  # 允许用户输入自定义模型
        # 设置当前模型
        current_model = self.api_settings.get("model", "gpt-4.1-nano")
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

        # Max Chars Per Batch
        self.max_chars_label = QLabel("Max Chars Per Batch", self)
        self.max_chars_spinbox = QSpinBox(self)
        self.max_chars_spinbox.setRange(100, 20000)  # 扩大范围以支持更大的批处理
        self.max_chars_spinbox.setValue(self.api_settings.get("max_chars_per_batch", DEFAULT_MAX_CHARS_PER_BATCH))
        self.max_chars_spinbox.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)  # 移除增减按钮
        self.max_chars_spinbox.setStyleSheet(
            "QSpinBox { color: white; background-color: #333; }"
        )
        form_layout.addWidget(self.max_chars_label)
        form_layout.addWidget(self.max_chars_spinbox)

        # Max Entries Per Batch
        self.max_entries_label = QLabel("Max Entries Per Batch", self)
        self.max_entries_spinbox = QSpinBox(self)
        self.max_entries_spinbox.setRange(1, 2000)  # 扩大范围以支持更多条目
        self.max_entries_spinbox.setValue(self.api_settings.get("max_entries_per_batch", DEFAULT_MAX_ENTRIES_PER_BATCH))
        self.max_entries_spinbox.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)  # 移除增减按钮
        self.max_entries_spinbox.setStyleSheet(
            "QSpinBox { color: white; background-color: #333; }"
        )
        form_layout.addWidget(self.max_entries_label)
        form_layout.addWidget(self.max_entries_spinbox)

        # Custom Prompt
        self.prompt_label = QLabel("Custom Translation Prompt", self)
        self.prompt_text = QTextEdit(self)
        self.prompt_text.setPlainText(self.api_settings.get("custom_prompt", ""))
        self.prompt_text.setStyleSheet(
            "QTextEdit { color: white; background-color: #333; font-family: monospace; }"
        )
        self.prompt_text.setMinimumHeight(150)  # 减少最小高度
        self.prompt_text.setMaximumHeight(250)  # 减少最大高度
        form_layout.addWidget(self.prompt_label)
        form_layout.addWidget(self.prompt_text)

        # Reset to Default Button
        self.reset_prompt_button = QPushButton("RESET TO DEFAULT", self)
        self.reset_prompt_button.clicked.connect(self.reset_prompt_to_default)
        self.reset_prompt_button.setStyleSheet(
            "QPushButton { background-color: #555; color: white; padding: 5px; }"
        )
        form_layout.addWidget(self.reset_prompt_button)

        # Save Button
        self.save_button = QPushButton("SAVE", self)
        self.save_button.clicked.connect(self.save_settings)
        form_layout.addWidget(self.save_button)

        layout.addLayout(form_layout)
        
        # 设置滚动区域
        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area)
    
    def reset_prompt_to_default(self):
        """重置所有设置为默认值"""
        # 使用不会被修改的原始默认值
        from config import DEFAULT_CUSTOM_PROMPT, DEFAULT_MAX_CHARS_PER_BATCH, DEFAULT_MAX_ENTRIES_PER_BATCH
        
        # 重置 Base URL
        # self.base_url_input.setText("https://api.openai.com")
        
        # 重置 Model
        self.model_combo.setCurrentText("gpt-4.1-nano")
        
        # 重置 Prompt
        self.prompt_text.setPlainText(DEFAULT_CUSTOM_PROMPT)
        
        # 重置批处理参数
        self.max_chars_spinbox.setValue(DEFAULT_MAX_CHARS_PER_BATCH)
        self.max_entries_spinbox.setValue(DEFAULT_MAX_ENTRIES_PER_BATCH)

    def save_settings(self):
        # Get the values from the input fields
        base_url = self.base_url_input.text().strip()
        api_key = self.api_key_input.text().strip()
        model = self.model_combo.currentText().strip()
        custom_prompt = self.prompt_text.toPlainText().strip()
        max_chars_per_batch = self.max_chars_spinbox.value()
        max_entries_per_batch = self.max_entries_spinbox.value()

        # 验证必填字段
        missing_fields = []
        if not base_url:
            missing_fields.append("Base URL")
        if not api_key:
            missing_fields.append("API Key")
        if not model:
            missing_fields.append("Model")
        if not custom_prompt:
            missing_fields.append("Custom Prompt")
            
        if missing_fields:
            QMessageBox.warning(self, "Validation Error", 
                              f"Please fill in the following required fields:\n• " + "\n• ".join(missing_fields))
            return
            
        if max_chars_per_batch <= 0 or max_entries_per_batch <= 0:
            QMessageBox.warning(self, "Validation Error", 
                              "Batch parameters must be greater than zero.")
            return

        # Update the settings dictionary
        self.api_settings["base_url"] = base_url
        self.api_settings["api_key"] = api_key
        self.api_settings["model"] = model
        self.api_settings["custom_prompt"] = custom_prompt
        self.api_settings["max_chars_per_batch"] = max_chars_per_batch
        self.api_settings["max_entries_per_batch"] = max_entries_per_batch

        # Accept the dialog (close with success)
        self.accept()
