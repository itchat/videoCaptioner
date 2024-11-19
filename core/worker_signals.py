from PyQt5.QtCore import QObject, pyqtSignal


class WorkerSignals(QObject):
    """
    定义工作线程的信号
    """
    progress = pyqtSignal(int)  # 进度信号
    result = pyqtSignal(str)  # 结果信号
    error = pyqtSignal(str)  # 错误信号
    file_progress = pyqtSignal(str, int)  # 文件处理进度信号 (文件名, 进度)
    status = pyqtSignal(str, str)  # 状态信号 (文件名, 状态信息)
    finished = pyqtSignal()  # 完成信号
    started = pyqtSignal()  # 开始信号
