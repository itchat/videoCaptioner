import os

def ensure_directory_exists(directory):
    """确保目录存在，如果不存在则创建"""
    if not os.path.exists(directory):
        os.makedirs(directory)

def get_safe_filename(filename):
    """获取安全的文件名"""
    return "".join([c for c in filename if c.isalpha() or c.isdigit() or c in (' ','-','_')]).rstrip()