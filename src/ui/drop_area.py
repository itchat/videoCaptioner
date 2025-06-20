from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QDragEnterEvent, QDropEvent


class DropArea(QLabel):
    filesDropped = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setAcceptDrops(True)
        self.reset_state()

    def reset_state(self, text="Drag and Drop Video Files"):
        """Reset Dragging Region State"""
        self.setAcceptDrops(True)
        self.setText(text)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #666;
                border-radius: 5px;
                padding: 20px;
                background-color: #2c2c2c;
                color: white;
                min-height: 100px;
            }
            QLabel:hover {
                background-color: #3c3c3c;
                border-color: #888;
            }
        """)

    def setEnabled(self, enabled):
        """Enable/Disable behavior"""
        super().setEnabled(enabled)
        self.setAcceptDrops(enabled)
        if enabled:
            self.reset_state()
        else:
            self.setStyleSheet("""
                QLabel {
                    border: 2px dashed #444;
                    border-radius: 5px;
                    padding: 20px;
                    background-color: #1c1c1c;
                    color: #666;
                    min-height: 100px;
                }
            """)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            # Check if it's a video file
            urls = event.mimeData().urls()
            video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv']
            
            if any(url.toLocalFile().lower().endswith(tuple(video_extensions)) for url in urls):
                event.acceptProposedAction()
                self.setStyleSheet("""
                    QLabel {
                        border: 2px dashed #88ff88;
                        border-radius: 5px;
                        padding: 20px;
                        background-color: #3c3c3c;
                        color: white;
                        min-height: 100px;
                    }
                """)

    def dragLeaveEvent(self, event):
        self.reset_state()

    def dropEvent(self, event: QDropEvent):
        files = []
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if self.is_video_file(file_path):
                files.append(file_path)

        if files:
            self.filesDropped.emit(files)

        self.reset_state()
        event.acceptProposedAction()

    @staticmethod
    def is_video_file(file_path):
        video_extensions = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv']
        return any(file_path.lower().endswith(ext) for ext in video_extensions)