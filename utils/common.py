import os
import shutil
import hashlib
from pathlib import Path

def ensure_directory_exists(directory):
    """If the directory does not exist, please create it."""
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)

def get_safe_filename(filename):
    """Getting a Safe File Name"""
    return "".join([c for c in filename if c.isalpha() or c.isdigit() or c in (' ','-','_')]).rstrip()

def get_file_hash(filepath, chunk_size=8192):
    """计算文件的MD5哈希值，用于缓存键生成"""
    hash_md5 = hashlib.md5()
    try:
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(chunk_size), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except (IOError, OSError):
        return None

def get_video_info(video_path):
    """获取视频基本信息"""
    try:
        file_size = os.path.getsize(video_path)
        file_name = os.path.basename(video_path)
        file_ext = os.path.splitext(video_path)[1].lower()
        
        return {
            'name': file_name,
            'size': file_size,
            'extension': file_ext,
            'size_mb': round(file_size / (1024 * 1024), 2)
        }
    except (IOError, OSError):
        return None

def cleanup_temp_files(cache_dir, keep_recent=5):
    """清理临时文件，保留最近的几个"""
    try:
        if not os.path.exists(cache_dir):
            return
        
        # 获取所有临时文件
        temp_files = []
        for file_path in Path(cache_dir).glob("*_audio.wav"):
            temp_files.append((file_path, file_path.stat().st_mtime))
        
        # 按修改时间排序，删除旧文件
        temp_files.sort(key=lambda x: x[1], reverse=True)
        for file_path, _ in temp_files[keep_recent:]:
            try:
                os.remove(file_path)
                # 同时删除相关的srt文件
                base_name = file_path.stem.replace('_audio', '')
                for pattern in ['_output.srt', '_bilingual.srt']:
                    related_file = file_path.parent / f"{base_name}{pattern}"
                    if related_file.exists():
                        os.remove(related_file)
            except OSError:
                continue
                
    except Exception:
        pass  # 静默失败，不影响主要功能

def validate_video_file(video_path):
    """验证视频文件是否有效"""
    if not os.path.exists(video_path):
        return False, "文件不存在"
    
    # 检查文件大小
    file_size = os.path.getsize(video_path)
    if file_size == 0:
        return False, "文件为空"
    
    if file_size > 2 * 1024 * 1024 * 1024:  # 2GB
        return False, "文件过大（超过2GB）"
    
    # 检查文件扩展名
    valid_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.m4v', '.webm'}
    file_ext = os.path.splitext(video_path)[1].lower()
    if file_ext not in valid_extensions:
        return False, f"不支持的文件格式: {file_ext}"
    
    return True, "文件有效"

def format_duration(seconds):
    """格式化时长显示"""
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}分{secs}秒"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}小时{minutes}分钟"