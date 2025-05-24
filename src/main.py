import sys
import signal
import os

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from PyQt5.QtWidgets import QApplication
from qt_material import apply_stylesheet
from src.ui.main_window import MainWindow


def main():
    # 设置环境变量来防止额外窗口
    os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'
    os.environ['QT_SCALE_FACTOR'] = '1'
    os.environ['QT_MAC_WANTS_LAYER'] = '1'
    
    # 创建QApplication并设置属性
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    
    apply_stylesheet(app, theme="dark_teal.xml")
    window = MainWindow()
    
    # 确保应用退出时正确清理资源
    def signal_handler(sig, frame):
        if hasattr(window.central_widget, 'cleanup_on_exit'):
            window.central_widget.cleanup_on_exit()
        app.quit()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # 连接应用退出信号到清理函数
    app.aboutToQuit.connect(lambda: window.central_widget.cleanup_on_exit() if hasattr(window.central_widget, 'cleanup_on_exit') else None)
    
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
