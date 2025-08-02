import sys
import signal
import os

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from PyQt6.QtWidgets import QApplication
from src.ui.main_window import MainWindow


def main():
    # 设置环境变量抑制警告
    os.environ['PYTHONWARNINGS'] = 'ignore::UserWarning'
    
    # 修复 macOS .app 环境中 ffmpeg PATH 问题
    if hasattr(sys, 'frozen') and sys.frozen:
        # 在打包环境中，将内置 ffmpeg 添加到 PATH
        current_path = os.environ.get('PATH', '')
        
        # 检查应用包的 Contents/Frameworks 目录（ffmpeg 的实际位置）
        if sys.executable.endswith('.app/Contents/MacOS/main'):
            app_frameworks = os.path.join(os.path.dirname(sys.executable), '..', 'Frameworks')
            app_frameworks = os.path.abspath(app_frameworks)
            
            if os.path.exists(os.path.join(app_frameworks, 'ffmpeg')):
                if app_frameworks not in current_path:
                    current_path = f"{app_frameworks}:{current_path}"
                    os.environ['PATH'] = current_path
    
    # 创建QApplication并设置属性
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(True)
    
    # 只有在QApplication创建后才能导入需要Qt的模块
    from utils.theme_manager import theme_manager
    from utils.log_filter import qt_log_filter
    
    # 安装日志过滤器
    qt_log_filter.install_handler()
    
    # 设置 macOS 优化
    theme_manager.setup_macos_optimizations()
    
    # 设置字体（现在可以安全使用QFontDatabase）
    theme_manager.setup_fonts(app)
    
    # 应用主题
    theme_manager.apply_theme(app, "dark_teal.xml")
    
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
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
