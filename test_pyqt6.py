#!/usr/bin/env python3
"""
PyQt6 兼容性测试脚本
验证项目是否成功升级到 PyQt6
"""

import sys
import os

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

def test_pyqt6_imports():
    """测试 PyQt6 导入"""
    print("测试 PyQt6 导入...")
    
    try:
        from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
        from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
        from PyQt6.QtGui import QFont, QIcon
        print("✅ PyQt6 核心模块导入成功")
    except ImportError as e:
        print(f"❌ PyQt6 导入失败: {e}")
        return False
    
    return True

def test_project_imports():
    """测试项目模块导入"""
    print("\n测试项目模块导入...")
    
    try:
        # 测试核心模块
        from core.worker_signals import WorkerSignals
        print("✅ core.worker_signals 导入成功")
        
        from core.video_processor import VideoProcessor
        print("✅ core.video_processor 导入成功")
        
        # 测试 UI 模块
        from src.ui.drop_area import DropArea
        print("✅ src.ui.drop_area 导入成功")
        
        from src.ui.progress_widget import ProgressWidget
        print("✅ src.ui.progress_widget 导入成功")
        
        from src.ui.api_settings_dialog import ApiSettingsDialog
        print("✅ src.ui.api_settings_dialog 导入成功")
        
        from src.ui.download_dialog import DownloadDialog
        print("✅ src.ui.download_dialog 导入成功")
        
        from src.ui.main_window import MainWindow
        print("✅ src.ui.main_window 导入成功")
        
        # 测试工具模块
        from utils.theme_manager import theme_manager
        print("✅ utils.theme_manager 导入成功")
        
        from utils.log_filter import qt_log_filter
        print("✅ utils.log_filter 导入成功")
        
    except ImportError as e:
        print(f"❌ 项目模块导入失败: {e}")
        return False
    
    return True

def test_application_creation():
    """测试应用程序创建"""
    print("\n测试应用程序创建...")
    
    try:
        from PyQt6.QtWidgets import QApplication
        
        # 检查是否已经有 QApplication 实例
        if QApplication.instance() is None:
            app = QApplication(sys.argv)
        else:
            app = QApplication.instance()
        
        print("✅ QApplication 创建成功")
        
        # 测试主窗口创建
        from src.ui.main_window import MainWindow
        window = MainWindow()
        print("✅ MainWindow 创建成功")
        
        return True
    except Exception as e:
        print(f"❌ 应用程序创建失败: {e}")
        return False

def test_qt6_constants():
    """测试 Qt6 常量"""
    print("\n测试 Qt6 常量...")
    
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QMessageBox
        
        # 测试新的枚举常量
        _ = Qt.WindowType.Window
        _ = Qt.AlignmentFlag.AlignCenter
        _ = Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        _ = QMessageBox.StandardButton.Ok
        print("✅ Qt6 常量测试成功")
        return True
    except Exception as e:
        print(f"❌ Qt6 常量测试失败: {e}")
        return False

def main():
    print("=" * 50)
    print("PyQt6 升级验证测试")
    print("=" * 50)
    
    tests = [
        test_pyqt6_imports,
        test_project_imports,
        test_application_creation,
        test_qt6_constants
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
        print()
    
    print("=" * 50)
    print(f"测试结果: {passed}/{total} 通过")
    
    if passed == total:
        print("🎉 PyQt6 升级成功!")
        return True
    else:
        print("⚠️  存在问题，需要进一步检查")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
