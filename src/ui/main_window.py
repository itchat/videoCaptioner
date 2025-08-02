from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QComboBox,
    QScrollArea,
    QMessageBox,
    QApplication,
)
from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtGui import QKeySequence, QAction, QShortcut
import os
import platform
import subprocess
from .drop_area import DropArea
from .progress_widget import ProgressWidget
from .api_settings_dialog import ApiSettingsDialog
from .download_dialog import DownloadDialog
from core.video_processor import VideoProcessor
from config import OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL, OPENAI_CUSTOM_PROMPT, OPENAI_MAX_CHARS_PER_BATCH, OPENAI_MAX_ENTRIES_PER_BATCH, save_config


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
        self.setWindowFlags(Qt.WindowType.Window)

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
                "Are you sure you want to quit?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return

        # 清理资源
        self.central_widget.cleanup_on_exit()
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
            "base_url": OPENAI_BASE_URL, 
            "api_key": OPENAI_API_KEY,
            "model": OPENAI_MODEL,
            "custom_prompt": OPENAI_CUSTOM_PROMPT,
            "max_chars_per_batch": OPENAI_MAX_CHARS_PER_BATCH,
            "max_entries_per_batch": OPENAI_MAX_ENTRIES_PER_BATCH
        }
        
        # 优化的线程池配置以避免语音识别并发问题
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
        
        # 对于语音识别任务，限制并发数以避免 MLX 模型冲突
        # Apple Silicon 设备建议最多2个并发，其他设备建议1个
        is_apple_silicon = False
        if platform.system() == 'Darwin':
            try:
                result = subprocess.run(['sysctl', '-n', 'hw.optional.arm64'], 
                                      capture_output=True, text=True, timeout=5)
                is_apple_silicon = result.returncode == 0 and result.stdout.strip() == '1'
            except Exception:
                pass
        
        # 保守的线程池设置：优先稳定性而不是并发性能
        if is_apple_silicon:
            optimal_pool_size = 2  # Apple Silicon 最多2个并发
        else:
            optimal_pool_size = 1  # 其他平台限制为1个以确保稳定性
        
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(optimal_pool_size)
        
        print(f"🔧 Thread pool size: {optimal_pool_size} threads (optimized for speech recognition)")
        print(f"💻 System: {platform.system()} - {cpu_count} cores")
        
        if is_apple_silicon:
            print("🍎 Apple Silicon detected - using optimized concurrency")
        
        self.file_paths = []  # 改名为更通用的file_paths
        self.cache_dir = os.path.expanduser("~/Desktop/videoCache")
        self.progress_widgets = {}
        self.is_processing = False
        self.active_processors = []  # 跟踪活跃的处理器
        self.completed_processors = 0  # 跟踪已完成的处理器数量
        self.total_processors = 0  # 跟踪总处理器数量
        
        # 下载对话框管理
        self.download_dialog = None
        self.model_already_loaded = False  # 跟踪模型是否已经加载过

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

        self.clear_button = QPushButton("Clear History")
        self.clear_button.clicked.connect(self.clear_progress_history)
        self.clear_button.setEnabled(False)  # 初始状态下禁用

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.settings_button)
        button_layout.addWidget(self.clear_button)
        main_layout.addLayout(button_layout)

    def on_files_dropped(self, files):
        if not self.is_processing:
            # 只处理视频文件
            video_files = []
            invalid_files = []
            
            for file_path in files:
                if self.drop_area.is_video_file(file_path):
                    video_files.append(file_path)
                else:
                    invalid_files.append(file_path)
            
            # 显示无效文件警告
            if invalid_files:
                invalid_names = [os.path.basename(f) for f in invalid_files]
                QMessageBox.warning(
                    self,
                    "Invalid File Type",
                    f"The following files are not supported video files and will be ignored:\n" + 
                    "\n".join(invalid_names),
                    QMessageBox.StandardButton.Ok,
                )
            
            self.file_paths = video_files
            
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
                QMessageBox.StandardButton.Ok,
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
        
        # 如果有进度条，启用清除按钮
        if self.progress_widgets:
            self.clear_button.setEnabled(True)

    def process_files(self):
        """处理视频文件"""
        if not self.file_paths:
            QMessageBox.warning(
                self, "Warning", "Select the file before processing", QMessageBox.StandardButton.Ok
            )
            return

        # 只处理视频文件
        self.video_paths = self.file_paths
        self.process_videos()

    def process_videos(self):
        if not self.video_paths:
            QMessageBox.warning(
                self, "Warning", "Select the file before processing", QMessageBox.StandardButton.Ok
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
        self.clear_button.setEnabled(False)  # 处理时禁用清除按钮
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
                processor.signals.timer_update.connect(self.update_file_timer)
                
                # 连接下载相关信号
                processor.signals.download_started.connect(self.show_download_dialog)
                processor.signals.download_progress.connect(self.update_download_progress)
                processor.signals.download_status.connect(self.update_download_status)
                processor.signals.download_completed.connect(self.download_completed)
                processor.signals.download_error.connect(self.download_error)

                self.thread_pool.start(processor)

            except Exception as e:
                self.handle_error(f"Error starting processor: {str(e)}")

    def update_file_progress(self, file_name, progress):
        if file_name in self.progress_widgets:
            self.progress_widgets[file_name].update_progress(progress)

    def update_file_status(self, file_name, status):
        if file_name in self.progress_widgets:
            self.progress_widgets[file_name].update_status(status)

    def update_file_timer(self, file_name, elapsed_time):
        if file_name in self.progress_widgets:
            self.progress_widgets[file_name].update_timer(elapsed_time)

    def handle_error(self, error_message):
        # 增加已完成的处理器计数（包括错误的情况）
        self.completed_processors += 1
        
        QMessageBox.critical(self, "Processing error", error_message, QMessageBox.StandardButton.Ok)
        
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
                        
            self.active_processors.clear()
            # 重置计数器
            self.completed_processors = 0
            self.total_processors = 0
            
            # 重置UI状态，但保留进度条
            self.reset_ui_state_keep_progress()

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
                        
            self.active_processors.clear()
            # 重置计数器
            self.completed_processors = 0
            self.total_processors = 0
            
            # 重置UI状态，但保留进度条
            self.reset_ui_state_keep_progress()

            QMessageBox.information(
                self, "Processing", "All processing is complete!", QMessageBox.StandardButton.Ok
            )

    def open_settings(self):
        dialog = ApiSettingsDialog(self, self.api_settings)
        if dialog.exec():
            # Save settings to config file
            save_config(
                self.api_settings["base_url"], 
                self.api_settings["api_key"],
                self.api_settings["model"],
                self.api_settings["custom_prompt"],
                self.api_settings["max_chars_per_batch"],
                self.api_settings["max_entries_per_batch"]
            )

            QMessageBox.information(
                self,
                "Save Settings",
                "API Settings have been updated and saved",
                QMessageBox.StandardButton.Ok,
            )

    def reset_ui_state(self):
        self.is_processing = False
        self.drop_area.setEnabled(True)
        # 重置拖拽区域为视频文件提示文本
        self.drop_area.reset_state("Drag and Drop Video Files")
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

    def reset_ui_state_keep_progress(self):
        """重置UI状态但保留进度条"""
        self.is_processing = False
        self.drop_area.setEnabled(True)
        # 重置拖拽区域为视频文件提示文本
        self.drop_area.reset_state("Drag and Drop Video Files")
        self.file_paths = []  # 重置通用文件路径
        # 为了兼容性，也重置video_paths（如果存在的话）
        if hasattr(self, 'video_paths'):
            self.video_paths = []
        self.start_button.setEnabled(False)
        self.engine_selector.setEnabled(True)
        self.settings_button.setEnabled(True)
        
        # 清理处理器列表
        self.active_processors.clear()
        
        # 不清理进度显示区域，保留进度条
        # 启用清除历史按钮，让用户可以手动清除
        if self.progress_widgets:
            self.clear_button.setEnabled(True)
        
    def clear_progress_history(self):
        """清除历史进度条"""
        if not self.is_processing:  # 只在没有处理任务时允许清除
            # 清理进度显示区域
            while self.progress_layout.count():
                child = self.progress_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            self.progress_widgets = {}
            self.clear_button.setEnabled(False)  # 清除后禁用按钮
        
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
            
            # 等待线程池完成
            if hasattr(self, 'thread_pool'):
                self.thread_pool.waitForDone(5000)  # 最多等待5秒
            
            # 清理单例模式的语音识别器
            try:
                from core.speech_recognizer import SpeechRecognizer
                SpeechRecognizer.cleanup_singleton()
            except Exception as e:
                print(f"Error cleaning up SpeechRecognizer: {e}")
                
        except Exception as e:
            print(f"Cleanup error: {e}")  # 使用print避免日志问题

    def show_download_dialog(self, model_name):
        """显示下载进度对话框"""
        # 如果模型已经加载过，就不显示下载对话框
        if self.model_already_loaded:
            return
            
        if self.download_dialog is None:
            self.download_dialog = DownloadDialog(self)
        
        self.download_dialog.show()
        self.download_dialog.raise_()
        self.download_dialog.activateWindow()
        self.download_dialog.add_log(f"Starting download of {model_name} model")
    
    def update_download_progress(self, percentage, downloaded_mb, total_mb, speed_mbps):
        """更新下载进度"""
        if self.model_already_loaded:
            return
        if self.download_dialog:
            self.download_dialog.update_progress(percentage, downloaded_mb, total_mb, speed_mbps)
    
    def update_download_status(self, message):
        """更新下载状态"""
        if self.model_already_loaded:
            return
        if self.download_dialog:
            self.download_dialog.update_status(message)
    
    def download_completed(self):
        """下载完成处理"""
        self.model_already_loaded = True  # 标记模型已经加载完成
        if self.download_dialog:
            self.download_dialog.set_completed()
    
    def download_error(self, error_message):
        """下载错误处理"""
        if self.download_dialog:
            self.download_dialog.set_error(error_message)
        else:
            # 如果对话框不存在，显示错误消息框
            QMessageBox.critical(
                self, 
                "Download Error", 
                f"Failed to download speech recognition model:\n{error_message}", 
                QMessageBox.StandardButton.Ok
            )
