from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QProgressBar, QPushButton, QTextEdit
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class DownloadDialog(QDialog):
    """模型下载进度对话框"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Downloading Parakeet MLX Model")
        self.setFixedSize(1000, 500)  # 增大窗口尺寸
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.WindowCloseButtonHint)
        self.setModal(False)  # 设置为非模态，用户可以关闭
        
        self.init_ui()
        
        # 设置样式
        self.setStyleSheet("""
            QDialog {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QLabel {
                color: #ffffff;
                font-size: 12px;
            }
            QProgressBar {
                border: 1px solid #555;
                border-radius: 5px;
                background: #2D2D2D;
                height: 20px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #4CAF50;
                border-radius: 4px;
            }
            QPushButton {
                background-color: #404040;
                color: white;
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px 16px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #505050;
            }
            QPushButton:pressed {
                background-color: #353535;
            }
            QTextEdit {
                background-color: #1e1e1e;
                color: #cccccc;
                border: 1px solid #444;
                border-radius: 5px;
                font-family: "Consolas", "Monaco", "Courier New", monospace;
                font-size: 10px;
            }
        """)
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 标题
        title_label = QLabel("Downloading Parakeet MLX Model")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # 描述
        desc_label = QLabel("First-time setup: Downloading Parakeet MLX model...\nThis may take a few minutes depending on your internet connection.")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("color: #cccccc; font-size: 11px;")
        layout.addWidget(desc_label)
        
        # 进度条区域
        progress_layout = QVBoxLayout()
        
        # 进度标签
        self.progress_label = QLabel("Initializing download...")
        progress_layout.addWidget(self.progress_label)
        
        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        progress_layout.addWidget(self.progress_bar)
        
        # 速度和大小信息
        info_layout = QHBoxLayout()
        self.speed_label = QLabel("Speed: --")
        self.size_label = QLabel("Size: --")
        info_layout.addWidget(self.speed_label)
        info_layout.addStretch()
        info_layout.addWidget(self.size_label)
        progress_layout.addLayout(info_layout)
        
        layout.addLayout(progress_layout)
        
        # 日志区域
        log_label = QLabel("Download Log:")
        layout.addWidget(log_label)
        
        self.log_text = QTextEdit()
        self.log_text.setMaximumHeight(100)
        self.log_text.setReadOnly(True)
        layout.addWidget(self.log_text)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)
        button_layout.addWidget(self.close_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def update_progress(self, value, downloaded_mb=0, total_mb=0, speed_mbps=0):
        """更新下载进度"""
        self.progress_bar.setValue(value)
        
        # 更新进度标签
        if value == 0:
            self.progress_label.setText("Initializing download...")
        elif value == 100:
            self.progress_label.setText("Download completed!")
        else:
            self.progress_label.setText(f"Downloading... {value}%")
        
        # 更新速度和大小信息
        if total_mb > 0:
            self.size_label.setText(f"Size: {downloaded_mb:.1f}/{total_mb:.1f} MB")
        
        if speed_mbps > 0:
            self.speed_label.setText(f"Speed: {speed_mbps:.1f} MB/s")
        elif value > 0:
            self.speed_label.setText("Speed: Calculating...")
    
    def update_status(self, message):
        """更新状态信息"""
        self.progress_label.setText(message)
        self.add_log(message)
    
    def add_log(self, message):
        """添加日志信息"""
        self.log_text.append(f"[{self.get_timestamp()}] {message}")
        # 自动滚动到底部
        scrollbar = self.log_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
    
    def get_timestamp(self):
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().strftime("%H:%M:%S")
    
    def set_completed(self):
        """设置下载完成状态"""
        self.progress_bar.setValue(100)
        self.progress_label.setText("Download completed successfully!")
        self.add_log("Model download completed successfully")
        self.close_button.setText("Close")
    
    def set_error(self, error_message):
        """设置错误状态"""
        self.progress_label.setText(f"Download failed: {error_message}")
        self.add_log(f"Error: {error_message}")
        self.progress_bar.setStyleSheet("""
            QProgressBar::chunk {
                background-color: #f44336;
            }
        """)
        self.close_button.setText("Close")
    
    def closeEvent(self, event):
        """重写关闭事件"""
        # 用户可以随时关闭对话框，下载会在后台继续
        self.add_log("Dialog closed by user (download continues in background)")
        event.accept()
