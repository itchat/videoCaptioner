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
    QLabel,
)
from PyQt5.QtCore import Qt, QThreadPool
from PyQt5.QtGui import QKeySequence
import os
from .drop_area import DropArea
from .progress_widget import ProgressWidget
from .api_settings_dialog import ApiSettingsDialog
from core.video_processor import VideoProcessor
from core.audio_processor import AudioProcessor
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
        # 设置合理的线程池大小，避免过多并发
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(min(4, QThreadPool.globalInstance().maxThreadCount()))
        
        self.file_paths = []  # 改名为更通用的file_paths
        self.cache_dir = os.path.expanduser("~/Desktop/videoCache")
        self.progress_widgets = {}
        self.is_processing = False
        self.active_processors = []  # 跟踪活跃的处理器
        self.completed_processors = 0  # 跟踪已完成的处理器数量
        self.total_processors = 0  # 跟踪总处理器数量

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
        self.start_button.clicked.connect(self.process_files)
        self.start_button.setEnabled(False)

        self.settings_button = QPushButton("Setting API")
        self.settings_button.clicked.connect(self.open_settings)

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.settings_button)
        main_layout.addLayout(button_layout)

    def on_files_dropped(self, files):
        if not self.is_processing:
            # 分离视频和音频文件
            video_files = []
            audio_files = []
            invalid_files = []
            
            for file_path in files:
                if self.drop_area.is_video_file(file_path):
                    video_files.append(file_path)
                elif self.drop_area.is_audio_file(file_path):
                    audio_files.append(file_path)
                else:
                    invalid_files.append(file_path)
            
            # 显示无效文件警告
            if invalid_files:
                invalid_names = [os.path.basename(f) for f in invalid_files]
                QMessageBox.warning(
                    self,
                    "Invalid File Type",
                    f"The following files are not supported media files and will be ignored:\n" + 
                    "\n".join(invalid_names),
                    QMessageBox.Ok,
                )
            
            # 混合文件类型警告
            if video_files and audio_files:
                QMessageBox.warning(
                    self,
                    "Mixed File Types",
                    "You have selected both video and audio files. Please process one type at a time.\n"
                    "Only video files will be processed this time.",
                    QMessageBox.Ok,
                )
                # 优先处理视频文件
                self.file_paths = video_files
            elif video_files:
                self.file_paths = video_files
            elif audio_files:
                self.file_paths = audio_files
            else:
                self.file_paths = []
            
            if self.file_paths:
                self.setup_progress_widgets()
                self.start_button.setEnabled(True)
            else:
                self.start_button.setEnabled(False)
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
        for file_path in self.file_paths:
            base_name = os.path.basename(file_path)
            progress_widget = ProgressWidget(base_name)
            self.progress_widgets[base_name] = progress_widget
            self.progress_layout.addWidget(progress_widget)

    def process_files(self):
        """统一的文件处理入口，根据文件类型自动判断处理模式"""
        if not self.file_paths:
            QMessageBox.warning(
                self, "Warning", "Select the file before processing", QMessageBox.Ok
            )
            return

        # 自动检测文件类型
        has_video = any(self.drop_area.is_video_file(f) for f in self.file_paths)
        has_audio = any(self.drop_area.is_audio_file(f) for f in self.file_paths)
        
        if has_video:
            # 视频处理模式
            self.video_paths = self.file_paths
            self.process_videos()
        elif has_audio:
            # 音频处理模式  
            self.process_audios()
        else:
            QMessageBox.warning(
                self, "Warning", "No valid media files found", QMessageBox.Ok
            )

    def process_audios(self):
        """新增的音频处理方法"""
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
        
        # 重置计数器
        self.completed_processors = 0
        self.total_processors = len(self.file_paths)
        self.active_processors.clear()

        for audio_path in self.file_paths:
            try:
                processor = AudioProcessor(
                    audio_path=audio_path,
                    engine=self.engine_selector.currentText(),
                    api_settings=self.api_settings,
                    cache_dir=self.cache_dir,
                )

                # 跟踪处理器
                self.active_processors.append(processor)
                
                processor.signals.file_progress.connect(self.update_file_progress)
                processor.signals.status.connect(self.update_file_status)
                processor.signals.error.connect(self.handle_error)
                processor.signals.finished.connect(self.handle_finished)

                self.thread_pool.start(processor)

            except Exception as e:
                self.handle_error(f"Error starting processor: {str(e)}")

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
        
        # 重置计数器
        self.completed_processors = 0
        self.total_processors = len(self.video_paths)
        self.active_processors.clear()

        for video_path in self.video_paths:
            try:
                processor = VideoProcessor(
                    video_path=video_path,
                    engine=self.engine_selector.currentText(),
                    api_settings=self.api_settings,
                    cache_dir=self.cache_dir,
                )

                # 跟踪处理器
                self.active_processors.append(processor)
                
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
        # 增加已完成的处理器计数（包括错误的情况）
        self.completed_processors += 1
        
        QMessageBox.critical(self, "Processing error", error_message, QMessageBox.Ok)
        
        # 检查是否所有任务都已完成（包括错误的）
        if self.completed_processors >= self.total_processors:
            # 清理处理器列表并释放资源
            for processor in self.active_processors:
                # 确保每个处理器的资源被正确清理
                if hasattr(processor, 'session'):
                    try:
                        processor.session.close()
                    except:
                        pass
                if hasattr(processor, 'logger'):
                    try:
                        processor.logger.cleanup()
                    except:
                        pass
                if hasattr(processor, '_whisper_model') and processor._whisper_model is not None:
                    try:
                        del processor._whisper_model
                        processor._whisper_model = None
                    except:
                        pass
                        
            self.active_processors.clear()
            # 重置计数器
            self.completed_processors = 0
            self.total_processors = 0
            
            # 重置UI状态
            self.reset_ui_state()

    def handle_finished(self):
        # 增加已完成的处理器计数
        self.completed_processors += 1
        
        # 检查是否所有任务都已完成
        if self.completed_processors >= self.total_processors:
            # 清理处理器列表并释放资源
            for processor in self.active_processors:
                # 确保每个处理器的资源被正确清理
                if hasattr(processor, 'session'):
                    try:
                        processor.session.close()
                    except:
                        pass
                if hasattr(processor, 'logger'):
                    try:
                        processor.logger.cleanup()
                    except:
                        pass
                if hasattr(processor, '_whisper_model') and processor._whisper_model is not None:
                    try:
                        del processor._whisper_model
                        processor._whisper_model = None
                    except:
                        pass
                        
            self.active_processors.clear()
            # 重置计数器
            self.completed_processors = 0
            self.total_processors = 0
            
            # 重置UI状态
            self.reset_ui_state()

            QMessageBox.information(
                self, "Processing", "All processing is complete!", QMessageBox.Ok
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
        # 重置拖拽区域为通用提示文本
        self.drop_area.reset_state("Drag and Drop Video or Audio Files")
        self.file_paths = []  # 重置通用文件路径
        # 为了兼容性，也重置video_paths（如果存在的话）
        if hasattr(self, 'video_paths'):
            self.video_paths = []
        self.start_button.setEnabled(False)
        self.engine_selector.setEnabled(True)
        self.settings_button.setEnabled(True)
        
        # 清理处理器列表
        self.active_processors.clear()

        # 清理进度显示区域
        while self.progress_layout.count():
            child = self.progress_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.progress_widgets = {}
        
    def cleanup_on_exit(self):
        """应用退出时的清理工作"""
        try:
            # 强制清理所有活跃的处理器
            for processor in self.active_processors:
                if hasattr(processor, 'session'):
                    try:
                        processor.session.close()
                    except:
                        pass
                if hasattr(processor, 'logger'):
                    try:
                        processor.logger.cleanup()
                    except:
                        pass
                if hasattr(processor, '_whisper_model') and processor._whisper_model is not None:
                    try:
                        del processor._whisper_model
                        processor._whisper_model = None
                    except:
                        pass
            
            # 等待线程池完成
            if hasattr(self, 'thread_pool'):
                self.thread_pool.waitForDone(5000)  # 最多等待5秒
                
        except Exception as e:
            print(f"Cleanup error: {e}")  # 使用print避免日志问题
