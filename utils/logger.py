import logging
import os
from datetime import datetime


class VideoLogger:
    def __init__(self, cache_dir):
        self.cache_dir = cache_dir
        self.log_dir = os.path.join(cache_dir, 'logs')
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        # 创建日志文件，使用时间格式
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = os.path.join(self.log_dir, f'process_{timestamp}.log')

        # 获取logger
        self.logger = logging.getLogger(f'VideoProcessor_{timestamp}')
        self.logger.setLevel(logging.INFO)
        
        # 确保没有重复的handlers
        if not self.logger.handlers:
            # 文件Handler
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
            file_handler.setLevel(logging.INFO)

            formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)

            self.logger.addHandler(file_handler)

    def info(self, message):
        self.logger.info(message)

    def error(self, message):
        self.logger.error(message)

    def warning(self, message):
        self.logger.warning(message)
    
    def cleanup(self):
        """正确关闭日志处理器以避免资源泄漏"""
        for handler in self.logger.handlers[:]:
            handler.close()
            self.logger.removeHandler(handler)
