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
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QAction, QShortcut
import os
import platform
import subprocess
from .drop_area import DropArea
from .progress_widget import ProgressWidget
from .api_settings_dialog import ApiSettingsDialog
from .download_dialog import DownloadDialog
from core.video_processor import MultiprocessVideoManager
from config import OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL, OPENAI_CUSTOM_PROMPT, OPENAI_MAX_CHARS_PER_BATCH, OPENAI_MAX_ENTRIES_PER_BATCH, MAX_PROCESSES, save_config
import multiprocessing as mp


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

        # 清理多进程管理器资源
        if hasattr(self.central_widget, 'multiprocess_manager'):
            self.central_widget.multiprocess_manager.shutdown()
        
        # 清理其他资源
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
            "max_entries_per_batch": OPENAI_MAX_ENTRIES_PER_BATCH,
            "max_processes": MAX_PROCESSES
        }
        
        # 初始化多进程管理器而不是线程池
        self.init_multiprocess_manager()
        
        self.file_paths = []
        self.cache_dir = os.path.expanduser("~/Desktop/videoCache")
        self.progress_widgets = {}
        self.is_processing = False
        self.active_process_ids = set()  # 跟踪活跃的进程ID
        self.completed_processes = 0  # 跟踪已完成的进程数量
        self.total_processes = 0  # 跟踪总进程数量
        
        # 创建定时器用于检查进程状态
        self.process_timer = QTimer()
        self.process_timer.timeout.connect(self.check_process_updates)
        self.process_timer.setInterval(100)  # 每100ms检查一次
        
        # 下载对话框管理
        self.download_dialog = None
        self.model_already_loaded = False  # 跟踪模型是否已经加载过

        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
    
    def init_multiprocess_manager(self):
        """初始化多进程管理器"""
        # 确定最大进程数
        cpu_count = mp.cpu_count()
        is_apple_silicon = False
        
        if platform.system() == 'Darwin':
            try:
                result = subprocess.run(['sysctl', '-n', 'hw.optional.arm64'], 
                                      capture_output=True, text=True, timeout=5)
                is_apple_silicon = result.returncode == 0 and result.stdout.strip() == '1'
            except Exception:
                pass
        
        # 使用配置文件中的进程数设置，而不是硬编码
        # 如果配置值超出合理范围，则进行限制
        self.max_processes = min(MAX_PROCESSES, cpu_count)  # 使用配置中的设置，但不超过CPU核心数
        
        # 延迟初始化多进程管理器，避免在 macOS .app 打包环境中出现分叉炸弹
        self.multiprocess_manager = None
        
        print(f"🔧 Multiprocess settings: {self.max_processes} max processes (configured: {MAX_PROCESSES})")
        print(f"💻 System: {platform.system()} - {cpu_count} cores")
        
        if is_apple_silicon:
            print("🍎 Apple Silicon detected - using optimized multiprocessing")

    def _ensure_multiprocess_manager(self):
        """确保多进程管理器已初始化（延迟初始化）"""
        if self.multiprocess_manager is None:
            # 根据实际任务数量动态调整进程数
            from config import get_dynamic_max_processes
            task_count = len(self.video_paths) if hasattr(self, 'video_paths') and self.video_paths else len(self.file_paths) if self.file_paths else 1
            dynamic_max_processes = get_dynamic_max_processes(task_count)
            
            print(f"🔧 Initializing multiprocess manager: {task_count} tasks -> {dynamic_max_processes} processes (max configured: {self.max_processes})")
            self.multiprocess_manager = MultiprocessVideoManager(max_processes=dynamic_max_processes)

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

        self.settings_button = QPushButton("SETTING")
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

    def clear_progress_history(self):
        """清除进度历史"""
        if not self.is_processing:
            while self.progress_layout.count():
                child = self.progress_layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()
            self.progress_widgets = {}
            self.clear_button.setEnabled(False)

    def process_files(self):
        """处理视频文件 - 多进程版本"""
        if not self.file_paths:
            QMessageBox.warning(
                self, "Warning", "Select the file before processing", QMessageBox.StandardButton.Ok
            )
            return

        # 直接处理视频
        self.process_videos()

    def process_videos(self):
        """处理视频 - 多进程版本"""
        if not hasattr(self, 'video_paths') or not self.video_paths:
            # 如果没有video_paths，使用file_paths
            if not self.file_paths:
                QMessageBox.warning(
                    self, "Warning", "Select the file before processing", QMessageBox.StandardButton.Ok
                )
                return
            self.video_paths = self.file_paths

        # 清理进度显示区域
        while self.progress_layout.count():
            child = self.progress_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.progress_widgets = {}

        # 设置新的进度显示
        self.setup_progress_widgets()

        # 禁用UI控件
        self.start_button.setEnabled(False)
        self.engine_selector.setEnabled(False)
        self.settings_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.is_processing = True
        self.drop_area.setEnabled(False)
        
        # 重置计数器和跟踪器
        self.completed_processes = 0
        self.total_processes = len(self.video_paths)
        self.active_process_ids.clear()

        # 确保多进程管理器已初始化
        self._ensure_multiprocess_manager()

        # 启动所有视频处理进程
        for video_path in self.video_paths:
            try:
                process_id = self.multiprocess_manager.submit_video(
                    video_path=video_path,
                    engine=self.engine_selector.currentText(),
                    api_settings=self.api_settings,
                    cache_dir=self.cache_dir
                )
                
                self.active_process_ids.add(process_id)
                print(f"🚀 Submitted video {os.path.basename(video_path)} to process {process_id}")
                
            except Exception as e:
                self.handle_error(f"Error starting processor for {os.path.basename(video_path)}: {str(e)}")

        # 启动定时器检查进程状态
        self.process_timer.start()
    
    def check_process_updates(self):
        """检查进程更新 - 定时器回调"""
        try:
            # 如果多进程管理器未初始化，跳过检查
            if self.multiprocess_manager is None:
                return
                
            # 获取进度更新
            progress_updates = self.multiprocess_manager.get_progress_updates()
            for update in progress_updates:
                if update['type'] == 'progress':
                    self.update_file_progress(update['base_name'], update['progress'])
                    if 'elapsed_time' in update:
                        self.update_file_timer(update['base_name'], update['elapsed_time'])
                elif update['type'] == 'status':
                    self.update_file_status(update['base_name'], update['status'])
            
            # 获取处理结果
            results = self.multiprocess_manager.get_results()
            for result in results:
                process_id = result['process_id']
                video_path = result['video_path']
                base_name = os.path.basename(video_path)
                
                if process_id in self.active_process_ids:
                    self.active_process_ids.remove(process_id)
                    self.completed_processes += 1
                    
                    if result['status'] == 'success':
                        print(f"✅ Process {process_id} completed successfully: {base_name}")
                        if base_name in self.progress_widgets:
                            self.progress_widgets[base_name].update_status("Processing completed!")
                            self.progress_widgets[base_name].update_progress(100)
                    elif result['status'] == 'error':
                        error_msg = result.get('error', 'Unknown error')
                        print(f"❌ Process {process_id} failed: {base_name} - {error_msg}")
                        self.handle_error(f"Failed to process {base_name}: {error_msg}")
                    
                    # 检查是否所有进程都已完成
                    if self.completed_processes >= self.total_processes:
                        self.all_processes_completed()
            
        except Exception as e:
            print(f"Error checking process updates: {str(e)}")
    
    def all_processes_completed(self):
        """所有进程完成后的处理"""
        print("🎉 All video processing completed")
        
        # 停止定时器
        self.process_timer.stop()
        
        # 重置状态
        self.reset_ui_state_keep_progress()
        
        # 显示完成消息
        QMessageBox.information(
            self, "Processing", "All processing is complete!", QMessageBox.StandardButton.Ok
        )

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
        """处理错误 - 多进程版本"""
        print(f"❌ Error: {error_message}")
        # 注意：不需要手动管理完成计数，因为check_process_updates会处理
        # 可以选择性地显示错误对话框
        # QMessageBox.critical(self, "Processing error", error_message, QMessageBox.StandardButton.Ok)

    def handle_finished(self):
        """处理完成 - 多进程版本（保留兼容性）"""
        # 注意：在多进程版本中，完成处理由check_process_updates和all_processes_completed处理
        # 这个方法保留是为了向后兼容，但实际上不会被调用
        pass

    def open_settings(self):
        dialog = ApiSettingsDialog(self, self.api_settings)
        if dialog.exec():
            # Update the max_processes value used by the multiprocess manager
            old_max_processes = self.max_processes
            self.max_processes = self.api_settings["max_processes"]
            
            # If multiprocess manager exists and max_processes changed, reset it
            if (self.multiprocess_manager is not None and 
                old_max_processes != self.max_processes):
                print(f"🔧 Updating max_processes from {old_max_processes} to {self.max_processes}")
                # Clean up existing manager
                self.multiprocess_manager.cleanup()
                # Reset manager to None so it will be recreated with new settings
                self.multiprocess_manager = None
            
            # Save settings to config file
            save_config(
                self.api_settings["base_url"], 
                self.api_settings["api_key"],
                self.api_settings["model"],
                self.api_settings["custom_prompt"],
                self.api_settings["max_chars_per_batch"],
                self.api_settings["max_entries_per_batch"],
                self.api_settings["max_processes"]
            )

            # QMessageBox.information(
            #     self,
            #     "Save Settings",
            #     "API Settings have been updated and saved",
            #     QMessageBox.StandardButton.Ok,
            # )

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
        """重置UI状态但保留进度条 - 多进程版本"""
        self.is_processing = False
        self.drop_area.setEnabled(True)
        self.drop_area.reset_state("Drag and Drop Video Files")
        self.file_paths = []
        if hasattr(self, 'video_paths'):
            self.video_paths = []
        self.start_button.setEnabled(False)
        self.engine_selector.setEnabled(True)
        self.settings_button.setEnabled(True)
        self.clear_button.setEnabled(True)  # 重新启用清除按钮
        
        # 重置计数器
        self.completed_processes = 0
        self.total_processes = 0
        self.active_process_ids.clear()
        
    def cleanup_on_exit(self):
        """应用退出时的清理工作 - 多进程版本"""
        try:
            # 停止定时器
            if hasattr(self, 'process_timer'):
                self.process_timer.stop()
            
            # 关闭多进程管理器
            if hasattr(self, 'multiprocess_manager') and self.multiprocess_manager is not None:
                self.multiprocess_manager.shutdown()
                
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
