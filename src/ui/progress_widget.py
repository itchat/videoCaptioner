from PyQt5.QtWidgets import (
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

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 11px;")

        layout.addLayout(header_layout)
        layout.addWidget(self.progress)
        layout.addWidget(self.status_label)

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
