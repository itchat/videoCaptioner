"""
日志过滤器
用于过滤和管理应用程序的日志输出
"""

import sys
import os
import logging
from PyQt6.QtCore import qInstallMessageHandler, QtMsgType


class QtLogFilter:
    """Qt 日志过滤器"""
    
    def __init__(self):
        self.filtered_messages = [
            "qt.svg: Cannot open file",
            "qt.qpa.fonts: Populating font family aliases",
            "error messaging the mach port for IMKCFRunLoopWakeUpReliable",
            "QFontDatabase",
            "qt_material must be imported after PySide or PyQt!",
            "name 'QFontDatabase' is not defined",
        ]
        
        # 设置Qt日志过滤规则
        self.setup_qt_logging()
        
        # 设置Python警告过滤器
        self.setup_warning_filters()
    
    def setup_qt_logging(self):
        """设置Qt日志规则"""
        # 禁用一些详细的Qt日志
        os.environ['QT_LOGGING_RULES'] = ';'.join([
            'qt.svg.debug=false',
            'qt.qpa.fonts.debug=false',
            'qt.qpa.screen.debug=false',
            'qt.qpa.input.debug=false',
        ])
    
    def qt_message_handler(self, msg_type, context, message):
        """Qt 消息处理器"""
        # 过滤不需要的消息
        for filtered_msg in self.filtered_messages:
            if filtered_msg in message:
                return
        
        # 根据消息类型选择合适的日志级别
        if msg_type == QtMsgType.QtDebugMsg:
            logging.debug(f"Qt Debug: {message}")
        elif msg_type == QtMsgType.QtInfoMsg:
            logging.info(f"Qt Info: {message}")
        elif msg_type == QtMsgType.QtWarningMsg:
            # 只显示重要的警告
            if any(important in message.lower() for important in ['error', 'failed', 'critical']):
                logging.warning(f"Qt Warning: {message}")
        elif msg_type == QtMsgType.QtCriticalMsg:
            logging.error(f"Qt Critical: {message}")
        elif msg_type == QtMsgType.QtFatalMsg:
            logging.critical(f"Qt Fatal: {message}")
    
    def install_handler(self):
        """安装Qt消息处理器"""
        qInstallMessageHandler(self.qt_message_handler)
        print("✅ Qt日志过滤器已安装")
    
    def setup_warning_filters(self):
        """设置Python警告过滤器"""
        import warnings
        
        # 过滤qt_material相关的警告
        warnings.filterwarnings("ignore", message=".*qt_material must be imported.*")
        warnings.filterwarnings("ignore", message=".*QFontDatabase.*not defined.*")
        
        # 过滤其他Qt相关警告
        warnings.filterwarnings("ignore", category=DeprecationWarning, module="qt_material")


# 全局日志过滤器实例
qt_log_filter = QtLogFilter()
