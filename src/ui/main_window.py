from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QComboBox, QScrollArea, QMessageBox
)
from PyQt5.QtCore import Qt, QThreadPool
# from PyQt5.QtGui import QIcon
import os
from .drop_area import DropArea
from .progress_widget import ProgressWidget
from api_settings_dialog import ApiSettingsDialog
from core.video_processor import VideoProcessor


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.central_widget = SubtitleProcessor()
        self.setCentralWidget(self.central_widget)
        self.init_window()

    def init_window(self):
        self.setWindowTitle("视频字幕自动化处理")
        self.setFixedSize(400, 600)

        # 设置窗口标志
        self.setWindowFlags(Qt.Window)

        # # 设置应用图标（会显示在 Dock 中）
        # icon_path = os.path.join(os.path.dirname(__file__), '..', '..', 'icon.icns')
        # if os.path.exists(icon_path):
        #     self.setWindowIcon(QIcon(icon_path))

    def closeEvent(self, event):
        """处理窗口关闭事件"""
        if self.central_widget.is_processing:
            reply = QMessageBox.question(
                self,
                "确认退出",
                "正在处理视频，确定要退出吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()
                return

        self.central_widget.reset_ui_state()
        event.accept()


class SubtitleProcessor(QWidget):
    def __init__(self):
        super().__init__()
        self.init_settings()
        self.init_ui()

    def init_settings(self):
        # Set default display info here
        self.api_settings = {
            "base_url": "",
            "api_key": ""
        }
        self.thread_pool = QThreadPool()
        self.video_paths = []
        self.cache_dir = os.path.expanduser("/Users/ronin/Desktop/videoCache")
        self.progress_widgets = {}
        self.is_processing = False

        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)

    def init_ui(self):
        main_layout = QVBoxLayout()

        # Drop Area
        self.drop_area = DropArea()
        self.drop_area.filesDropped.connect(self.on_files_dropped)
        main_layout.addWidget(self.drop_area)

        # Progress Area
        self.setup_progress_area(main_layout)

        # Engine Selection
        self.setup_engine_selection(main_layout)

        # Buttons
        self.setup_buttons(main_layout)

        self.setLayout(main_layout)

    def setup_progress_area(self, main_layout):
        self.progress_area = QScrollArea()
        self.progress_area.setWidgetResizable(True)
        self.progress_container = QWidget()
        self.progress_layout = QVBoxLayout(self.progress_container)
        self.progress_area.setWidget(self.progress_container)
        main_layout.addWidget(self.progress_area)

    def setup_engine_selection(self, main_layout):
        engine_layout = QHBoxLayout()
        self.engine_selector = QComboBox()
        self.engine_selector.addItems(["Google 翻译", "OpenAI 翻译"])
        self.engine_selector.setStyleSheet(
            "QComboBox { color: white; border: 1px solid #444; }")
        engine_layout.addWidget(self.engine_selector)
        main_layout.addLayout(engine_layout)

    def setup_buttons(self, main_layout):
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("开始处理")
        self.start_button.clicked.connect(self.process_videos)
        self.start_button.setEnabled(False)

        self.settings_button = QPushButton("设置 API")
        self.settings_button.clicked.connect(self.open_settings)

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.settings_button)
        main_layout.addLayout(button_layout)

    def on_files_dropped(self, files):
        if not self.is_processing:
            self.video_paths = files
            self.setup_progress_widgets()
            self.start_button.setEnabled(bool(files))
        else:
            QMessageBox.warning(
                self,
                "处理中",
                "请等待当前任务完成后再添加新文件",
                QMessageBox.Ok
            )

    def setup_progress_widgets(self):
        """设置进度显示部件"""
        while self.progress_layout.count():
            child = self.progress_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.progress_widgets = {}
        for video_path in self.video_paths:
            base_name = os.path.basename(video_path)
            progress_widget = ProgressWidget(base_name)
            self.progress_widgets[base_name] = progress_widget
            self.progress_layout.addWidget(progress_widget)

    def process_videos(self):
        """开始处理视频文件"""
        if not self.video_paths:
            QMessageBox.warning(self, "警告", "请先选择要处理的视频文件", QMessageBox.Ok)
            return

        # 清理之前的进度显示
        while self.progress_layout.count():
            child = self.progress_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.progress_widgets = {}

        # 设置新的进度显示
        self.setup_progress_widgets()

        self.start_button.setEnabled(False)
        self.is_processing = True
        self.drop_area.setEnabled(False)

        for video_path in self.video_paths:
            try:
                processor = VideoProcessor(
                    video_path=video_path,
                    engine=self.engine_selector.currentText(),
                    api_settings=self.api_settings,
                    cache_dir=self.cache_dir
                )

                processor.signals.file_progress.connect(self.update_file_progress)
                processor.signals.status.connect(self.update_file_status)
                processor.signals.error.connect(self.handle_error)
                processor.signals.finished.connect(self.handle_finished)

                self.thread_pool.start(processor)

            except Exception as e:
                self.handle_error(f"启动处理器时出错: {str(e)}")

    def update_file_progress(self, file_name, progress):
        """更新文件处理进度"""
        if file_name in self.progress_widgets:
            self.progress_widgets[file_name].update_progress(progress)

    def update_file_status(self, file_name, status):
        """更新文件处理状态"""
        if file_name in self.progress_widgets:
            self.progress_widgets[file_name].update_status(status)

    def handle_error(self, error_message):
        """处理错误信息"""
        # print(f"Error: {error_message}")
        QMessageBox.critical(
            self,
            "处理错误",
            error_message,
            QMessageBox.Ok
        )

    def handle_finished(self):
        """处理完成回调"""
        # 检查是否所有任务都完成了
        if self.thread_pool.activeThreadCount() == 0:
            self.is_processing = False
            self.drop_area.setEnabled(True)
            self.drop_area.setAcceptDrops(True)  # 明确重新启用拖放
            self.video_paths = []
            self.start_button.setEnabled(False)

            # 清理进度显示区域
            while self.progress_layout.count():
                child = self.progress_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            self.progress_widgets = {}

            QMessageBox.information(
                self,
                "处理完成",
                "所有视频处理已完成！",
                QMessageBox.Ok
            )

    def open_settings(self):
        """打开设置对话框"""
        dialog = ApiSettingsDialog(self, self.api_settings)
        if dialog.exec_():
            QMessageBox.information(
                self,
                "设置保存",
                "API设置已更新",
                QMessageBox.Ok
            )

    def reset_ui_state(self):
        """重置UI状态"""
        self.is_processing = False
        self.drop_area.setEnabled(True)
        self.drop_area.reset_state()
        self.video_paths = []
        self.start_button.setEnabled(False)
        self.progress_widgets = {}
