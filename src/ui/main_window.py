from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QScrollArea,
    QMessageBox,
    QShortcut,
    QAction,
    QApplication,
)
from PyQt5.QtCore import Qt, QThreadPool
from PyQt5.QtGui import QKeySequence
import os
from .drop_area import DropArea
from .progress_widget import ProgressWidget
from src.ui.api_settings_dialog import ApiSettingsDialog
from core.video_processor import VideoProcessor
from config import OPENAI_BASE_URL, OPENAI_API_KEY, save_config


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.central_widget = SubtitleProcessor()
        self.setCentralWidget(self.central_widget)
        self.init_window()

    def init_window(self):
        # self.setWindowTitle("videoCaptioner")
        self.setMinimumSize(350, 350)  # 设置最小窗口大小
        # self.resize(400, 400)  # 设置默认窗口大小

        # Set the window icon
        self.setWindowFlags(Qt.Window)

        # Create menu bar with quit action for macOS
        self.create_menu_actions()

        # Add Command+Q shortcut for macOS
        self.quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        self.quit_shortcut.activated.connect(self.close)

        # Add Command+Q shortcut specifically for macOS
        self.quit_shortcut_mac = QShortcut(QKeySequence("Meta+Q"), self)
        self.quit_shortcut_mac.activated.connect(self.close)

    def create_menu_actions(self):
        # Create File menu with Quit action
        file_menu = self.menuBar().addMenu("File")

        # Create Quit action
        quit_action = QAction("Quit", self)
        quit_action.setShortcut(QKeySequence("Meta+Q"))
        quit_action.triggered.connect(QApplication.quit)
        file_menu.addAction(quit_action)

    def closeEvent(self, event):
        if self.central_widget.is_processing:
            reply = QMessageBox.question(
                self,
                "Are you sure to quit?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
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
        self.api_settings = {"base_url": OPENAI_BASE_URL, "api_key": OPENAI_API_KEY}
        self.thread_pool = QThreadPool()
        self.video_paths = []
        self.cache_dir = os.path.expanduser("~/Desktop/videoCache")
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
        self.engine_selector.addItems(["Google Translate", "OpenAI Translate"])
        self.engine_selector.setStyleSheet(
            "QComboBox { color: white; border: 1px solid #444; }"
        )
        engine_layout.addWidget(self.engine_selector)
        main_layout.addLayout(engine_layout)

    def setup_buttons(self, main_layout):
        button_layout = QHBoxLayout()
        self.start_button = QPushButton("Start Processing")
        self.start_button.clicked.connect(self.process_videos)
        self.start_button.setEnabled(False)

        self.settings_button = QPushButton("Setting API")
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
                "Processing",
                "Wait for the current task to complete before adding a new file",
                QMessageBox.Ok,
            )

    def setup_progress_widgets(self):
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
        if not self.video_paths:
            QMessageBox.warning(
                self, "Warning", "Select the file before processing", QMessageBox.Ok
            )
            return

        # Cleaning progress display area
        while self.progress_layout.count():
            child = self.progress_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.progress_widgets = {}

        # Set a new progress display
        self.setup_progress_widgets()

        self.start_button.setEnabled(False)
        self.engine_selector.setEnabled(False)
        self.settings_button.setEnabled(False)
        self.is_processing = True
        self.drop_area.setEnabled(False)

        for video_path in self.video_paths:
            try:
                processor = VideoProcessor(
                    video_path=video_path,
                    engine=self.engine_selector.currentText(),
                    api_settings=self.api_settings,
                    cache_dir=self.cache_dir,
                )

                processor.signals.file_progress.connect(self.update_file_progress)
                processor.signals.status.connect(self.update_file_status)
                processor.signals.error.connect(self.handle_error)
                processor.signals.finished.connect(self.handle_finished)

                self.thread_pool.start(processor)

            except Exception as e:
                self.handle_error(f"Error starting processor: {str(e)}")

    def update_file_progress(self, file_name, progress):
        if file_name in self.progress_widgets:
            self.progress_widgets[file_name].update_progress(progress)

    def update_file_status(self, file_name, status):
        if file_name in self.progress_widgets:
            self.progress_widgets[file_name].update_status(status)

    def handle_error(self, error_message):
        QMessageBox.critical(self, "Processing error", error_message, QMessageBox.Ok)

    def handle_finished(self):
        # Check that all tasks have been completed
        if self.thread_pool.activeThreadCount() == 0:
            self.reset_ui_state()

            QMessageBox.information(
                self, "Processing", "All video processing is complete!", QMessageBox.Ok
            )

    def open_settings(self):
        dialog = ApiSettingsDialog(self, self.api_settings)
        if dialog.exec_():
            # Save settings to config file
            save_config(self.api_settings["base_url"], self.api_settings["api_key"])

            QMessageBox.information(
                self,
                "Save Settings",
                "API Settings have been updated and saved",
                QMessageBox.Ok,
            )

    def reset_ui_state(self):
        self.is_processing = False
        self.drop_area.setEnabled(True)
        self.drop_area.reset_state()
        self.video_paths = []
        self.start_button.setEnabled(False)
        self.engine_selector.setEnabled(True)
        self.settings_button.setEnabled(True)

        # 清理进度显示区域
        while self.progress_layout.count():
            child = self.progress_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.progress_widgets = {}
