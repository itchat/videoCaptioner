from PyQt6.QtCore import QObject, pyqtSignal


class WorkerSignals(QObject):
    """ Define signals for the worker thread """
    progress = pyqtSignal(int)  # Progress signal
    result = pyqtSignal(str)    # Result signal
    error = pyqtSignal(str)     # Error signal
    file_progress = pyqtSignal(str, int)  # File processing progress signal (filename, progress)
    status = pyqtSignal(str, str)  # Status signal (filename, status information)
    finished = pyqtSignal()      # Finished signal
    started = pyqtSignal()       # Started signal
    
    # 新增模型下载相关信号
    download_started = pyqtSignal(str)  # 下载开始信号 (model_name)
    download_progress = pyqtSignal(int, float, float, float)  # 下载进度信号 (percentage, downloaded_mb, total_mb, speed_mbps)
    download_status = pyqtSignal(str)  # 下载状态信号 (status_message)
    download_completed = pyqtSignal()  # 下载完成信号
    download_error = pyqtSignal(str)  # 下载错误信号 (error_message)
    
    # 计时器相关信号
    timer_update = pyqtSignal(str, str)  # 计时器更新信号 (filename, elapsed_time)

