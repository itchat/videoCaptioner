from PyQt5.QtCore import QObject, pyqtSignal


class WorkerSignals(QObject):
    """ Define signals for the worker thread """
    progress = pyqtSignal(int)  # Progress signal
    result = pyqtSignal(str)    # Result signal
    error = pyqtSignal(str)     # Error signal
    file_progress = pyqtSignal(str, int)  # File processing progress signal (filename, progress)
    status = pyqtSignal(str, str)  # Status signal (filename, status information)
    finished = pyqtSignal()      # Finished signal
    started = pyqtSignal()       # Started signal

