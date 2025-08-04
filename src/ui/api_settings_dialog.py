from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
                             QPushButton, QComboBox, QTextEdit, QSpinBox, QMessageBox, QCheckBox)
from PyQt6.QtCore import Qt
from config import (OPENAI_CUSTOM_PROMPT, DEFAULT_CUSTOM_PROMPT, DEFAULT_MAX_CHARS_PER_BATCH, 
                   DEFAULT_MAX_ENTRIES_PER_BATCH, DEFAULT_MAX_PROCESSES, OPENAI_BASE_URL, OPENAI_MODEL,
                   DEFAULT_SKIP_SUBTITLE_BURNING)


class ApiSettingsDialog(QDialog):
    def __init__(self, parent=None, api_settings=None):
        super().__init__(parent)
        self.api_settings = api_settings or {
            "base_url": OPENAI_BASE_URL, 
            "api_key": "", 
            "model": OPENAI_MODEL,
            "custom_prompt": OPENAI_CUSTOM_PROMPT,
            "max_chars_per_batch": DEFAULT_MAX_CHARS_PER_BATCH,
            "max_entries_per_batch": DEFAULT_MAX_ENTRIES_PER_BATCH,
            "max_processes": DEFAULT_MAX_PROCESSES,
            "skip_subtitle_burning": DEFAULT_SKIP_SUBTITLE_BURNING
        }
        self.initUI()

    def initUI(self):
        self.setWindowTitle("API Setting")
        # 调整为更紧凑的尺寸，因为prompt框变窄了
        self.setMinimumSize(650, 450)  # 稍微减小宽度
        self.resize(700, 480)  # 减小初始宽度
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        
        # 移除自定义背景色，让qt_material主题生效
        # 不设置任何自定义样式，完全依赖qt_material主题

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)  # 进一步减小整体间距
        main_layout.setContentsMargins(15, 15, 15, 15)  # 减小边距

        # 左右分栏布局
        content_layout = QHBoxLayout()
        content_layout.setSpacing(20)  # 稍微减小左右栏间距
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # 顶部对齐
        
        # 左栏：API连接设置 (比例调整为相等)
        left_panel = self.create_left_panel()
        content_layout.addLayout(left_panel, 1)
        
        # 右栏：批处理和系统设置 (比例调整为相等)
        right_panel = self.create_right_panel()
        content_layout.addLayout(right_panel, 1)
        
        main_layout.addLayout(content_layout)
        
        # 翻译提示文本区域
        prompt_section = self.create_prompt_section()
        main_layout.addLayout(prompt_section)
        
        # 底部按钮
        button_section = self.create_buttons()
        main_layout.addLayout(button_section)

    def create_left_panel(self):
        """创建左侧面板 - API连接设置"""
        layout = QVBoxLayout()
        layout.setSpacing(12)  # 统一间距
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # 顶部对齐
        
        # Base URL
        layout.addWidget(self.create_label("Base URL"))
        self.base_url_input = QLineEdit(self)
        self.base_url_input.setText(self.api_settings.get("base_url", ""))
        self.base_url_input.setPlaceholderText("https://api.openai.com")
        # 设置合适的高度
        self.base_url_input.setFixedHeight(32)
        layout.addWidget(self.base_url_input)
        
        layout.addSpacing(8)  # 统一间距
        
        # API Key (必填)
        api_key_label = QLabel("API Key", self)
        layout.addWidget(api_key_label)
        self.api_key_input = QLineEdit(self)
        self.api_key_input.setText(self.api_settings.get("api_key", ""))
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setPlaceholderText("Required: Enter your API key")
        # 设置合适的高度
        self.api_key_input.setFixedHeight(32)
        layout.addWidget(self.api_key_input)
        
        layout.addSpacing(8)  # 统一间距
        
        # Model
        layout.addWidget(self.create_label("Model"))
        self.model_combo = QComboBox(self)
        models = ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4.1-nano"]
        self.model_combo.addItems(models)
        self.model_combo.setEditable(True)
        
        current_model = self.api_settings.get("model", OPENAI_MODEL)
        if current_model in models:
            self.model_combo.setCurrentText(current_model)
        else:
            self.model_combo.addItem(current_model)
            self.model_combo.setCurrentText(current_model)
        
        # 设置合适的高度
        self.model_combo.setFixedHeight(32)
        layout.addWidget(self.model_combo)
        
        # 移除stretch，让布局紧凑
        return layout

    def create_right_panel(self):
        """创建右侧面板 - 批处理和系统设置"""
        layout = QVBoxLayout()
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)  # 顶部对齐
        
        # Max Chars Per Batch
        layout.addWidget(self.create_label("Max Chars Per Batch"))
        self.max_chars_spinbox = QSpinBox(self)
        self.max_chars_spinbox.setRange(100, 20000)
        self.max_chars_spinbox.setValue(self.api_settings.get("max_chars_per_batch", DEFAULT_MAX_CHARS_PER_BATCH))
        self.max_chars_spinbox.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        # 设置合适的高度
        self.max_chars_spinbox.setFixedHeight(32)
        layout.addWidget(self.max_chars_spinbox)
        
        layout.addSpacing(8)
        
        # Max Entries Per Batch
        layout.addWidget(self.create_label("Max Entries Per Batch"))
        self.max_entries_spinbox = QSpinBox(self)
        self.max_entries_spinbox.setRange(1, 2000)
        self.max_entries_spinbox.setValue(self.api_settings.get("max_entries_per_batch", DEFAULT_MAX_ENTRIES_PER_BATCH))
        self.max_entries_spinbox.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        # 设置合适的高度
        self.max_entries_spinbox.setFixedHeight(32)
        layout.addWidget(self.max_entries_spinbox)
        
        layout.addSpacing(8)  # 统一间距
        
        # Max Concurrent Processes
        layout.addWidget(self.create_label("Max Concurrent Processes"))
        self.max_processes_spinbox = QSpinBox(self)
        self.max_processes_spinbox.setRange(1, 12)
        self.max_processes_spinbox.setValue(self.api_settings.get("max_processes", DEFAULT_MAX_PROCESSES))
        self.max_processes_spinbox.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        # 设置合适的高度
        self.max_processes_spinbox.setFixedHeight(32)
        layout.addWidget(self.max_processes_spinbox)
        
        layout.addSpacing(8)  # 添加间距
        
        # Skip Subtitle Burning Checkbox
        self.skip_burning_checkbox = QCheckBox("Skip burning subtitles into video", self)
        self.skip_burning_checkbox.setChecked(self.api_settings.get("skip_subtitle_burning", DEFAULT_SKIP_SUBTITLE_BURNING))
        layout.addWidget(self.skip_burning_checkbox)
        
        # 移除stretch，让布局紧凑
        return layout

    def create_prompt_section(self):
        """创建翻译提示设置区域"""
        layout = QVBoxLayout()
        layout.setSpacing(12)  # 减小间距
        
        prompt_title = QLabel("Custom Translation Prompt", self)
        layout.addWidget(prompt_title)
        
        self.prompt_text = QTextEdit(self)
        self.prompt_text.setPlainText(self.api_settings.get("custom_prompt", ""))
        # 确保文本颜色为白色（适配深色主题）
        self.prompt_text.setStyleSheet("QTextEdit { color: white; }")
        # self.prompt_text.setFixedHeight(80)  # 减小高度
        layout.addWidget(self.prompt_text)
        
        return layout

    def create_buttons(self):
        """创建按钮区域"""
        layout = QHBoxLayout()
        layout.setSpacing(12)
        layout.setContentsMargins(0, 10, 0, 0)  # 减小顶部间距
        
        # Reset按钮
        reset_button = QPushButton("RESET TO DEFAULT", self)
        reset_button.clicked.connect(self.reset_to_default)
        reset_button.setFixedHeight(32)  # 设置按钮高度
        
        # Save按钮
        save_button = QPushButton("SAVE", self)
        save_button.clicked.connect(self.save_settings)
        save_button.setFixedHeight(32)  # 设置按钮高度
        
        layout.addWidget(reset_button)
        layout.addStretch()
        layout.addWidget(save_button)
        
        return layout

    def create_label(self, text):
        """创建普通标签"""
        label = QLabel(text, self)
        # 移除自定义样式，使用qt_material主题
        return label

    def save_settings(self):
        """保存设置 - 简化的验证逻辑"""
        # 获取输入值
        base_url = self.base_url_input.text().strip()
        api_key = self.api_key_input.text().strip()
        model = self.model_combo.currentText().strip()
        custom_prompt = self.prompt_text.toPlainText().strip()
        max_chars_per_batch = self.max_chars_spinbox.value()
        max_entries_per_batch = self.max_entries_spinbox.value()
        max_processes = self.max_processes_spinbox.value()
        skip_subtitle_burning = self.skip_burning_checkbox.isChecked()

        # 只验证 API Key 是否为空
        if not api_key:
            QMessageBox.warning(self, "Validation Error", 
                              "API Key is required and cannot be empty.\nPlease enter your API key.")
            self.api_key_input.setFocus()
            return
            
        # 检查数值参数
        if max_chars_per_batch <= 0 or max_entries_per_batch <= 0 or max_processes <= 0:
            QMessageBox.warning(self, "Validation Error", 
                              "Batch parameters must be greater than zero.")
            return

        # 空字段处理：自动恢复为默认值（无提示）
        if not base_url:
            base_url = OPENAI_BASE_URL
            self.base_url_input.setText(base_url)
            
        if not model:
            model = OPENAI_MODEL
            self.model_combo.setCurrentText(model)
            
        if not custom_prompt:
            custom_prompt = DEFAULT_CUSTOM_PROMPT
            self.prompt_text.setPlainText(custom_prompt)

        # 更新设置字典
        self.api_settings["base_url"] = base_url
        self.api_settings["api_key"] = api_key
        self.api_settings["model"] = model
        self.api_settings["custom_prompt"] = custom_prompt
        self.api_settings["max_chars_per_batch"] = max_chars_per_batch
        self.api_settings["max_entries_per_batch"] = max_entries_per_batch
        self.api_settings["max_processes"] = max_processes
        self.api_settings["skip_subtitle_burning"] = skip_subtitle_burning

        # 显示成功消息
        QMessageBox.information(self, "Settings Saved", 
                              "Settings have been saved successfully!")

        # 关闭对话框
        self.accept()

    def reset_to_default(self):
        """重置所有设置为默认值"""
        self.base_url_input.setText(OPENAI_BASE_URL)
        self.model_combo.setCurrentText(OPENAI_MODEL)
        self.prompt_text.setPlainText(DEFAULT_CUSTOM_PROMPT)
        self.max_chars_spinbox.setValue(DEFAULT_MAX_CHARS_PER_BATCH)
        self.max_entries_spinbox.setValue(DEFAULT_MAX_ENTRIES_PER_BATCH)
        self.max_processes_spinbox.setValue(DEFAULT_MAX_PROCESSES)
        self.skip_burning_checkbox.setChecked(DEFAULT_SKIP_SUBTITLE_BURNING)
