import logging
import os
from datetime import datetime


class VideoLogger:
    def __init__(self, cache_dir):
        self.cache_dir = cache_dir
        self.log_dir = os.path.join(cache_dir, 'logs')
        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir)

        # Creating log file by using time format
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_file = os.path.join(self.log_dir, f'process_{timestamp}.log')

        self.logger = logging.getLogger('VideoProcessor')
        self.logger.setLevel(logging.INFO)

        # File Handler
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
