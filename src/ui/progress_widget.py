from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QProgressBar
)


class ProgressWidget(QWidget):
    def __init__(self, file_name):
        super().__init__()
        self.file_name = file_name
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        header_layout = QHBoxLayout()
        self.label = QLabel(self.file_name)
        self.percent_label = QLabel("0%")
        header_layout.addWidget(self.label)
        header_layout.addStretch()
        header_layout.addWidget(self.percent_label)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)

        # 添加计时器和状态的水平布局
        info_layout = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")
        
        self.timer_label = QLabel("00:00")
        self.timer_label.setStyleSheet("color: #4CAF50; font-size: 11px; font-weight: bold;")
        
        info_layout.addWidget(self.status_label)
        info_layout.addStretch()
        info_layout.addWidget(self.timer_label)

        layout.addLayout(header_layout)
        layout.addWidget(self.progress)
        layout.addLayout(info_layout)

        self.setStyleSheet("""
            QLabel { color: #E0E0E0; }
            QProgressBar {
                border: 1px solid #555;
                border-radius: 3px;
                background: #2D2D2D;
                height: 10px;
            }
            QProgressBar::chunk {
                background-color: #2196F3;
                border-radius: 2px;
            }
        """)

    def update_progress(self, value):
        self.progress.setValue(value)
        self.percent_label.setText(f"{value}%")

    def update_status(self, status):
        self.status_label.setText(status)
        
    def update_timer(self, elapsed_time):
        self.timer_label.setText(elapsed_time)
