"""
语音识别模块 - 基于 Parakeet MLX
支持多进程和多线程安全操作
"""
import json
import threading
import os
import math
import tempfile
import subprocess
from typing import Any, Dict, Optional, Callable
from mlx.core import bfloat16, float32
from parakeet_mlx import AlignedResult, AlignedSentence, AlignedToken, from_pretrained
from utils.logger import VideoLogger


class SpeechRecognizer:
    """语音识别类，封装 Parakeet MLX 模型 - 支持多进程和多线程安全"""
    
    # 进程级别的实例字典，每个进程都有自己的实例
    _instances = {}
    _lock = threading.Lock()
    _model_lock = threading.Lock()  # 模型访问锁
    
    def __new__(cls, *args, **kwargs):
        """进程安全的单例模式实现 - 每个进程都有自己的实例"""
        current_pid = os.getpid()
        
        if current_pid not in cls._instances:
            with cls._lock:
                if current_pid not in cls._instances:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    instance._process_id = current_pid
                    cls._instances[current_pid] = instance
                else:
                    pass  # Reusing instance for current process
        else:
            pass  # Reusing existing instance for current process
            
        return cls._instances[current_pid]
    
    def __init__(self, 
                 model_name: str = "mlx-community/parakeet-tdt-0.6b-v2",
                 fp32: bool = False,
                 local_attention: bool = False,
                 local_attention_context_size: int = 256,
                 logger: Optional[VideoLogger] = None,
                 download_callback: Optional[Callable[[str], None]] = None,
                 progress_callback: Optional[Callable[[int, float, float, float], None]] = None,
                 status_callback: Optional[Callable[[str], None]] = None):
        """
        初始化语音识别器（进程安全的单例模式）
        
        Args:
            model_name: 模型名称
            fp32: 是否使用FP32精度
            local_attention: 是否使用局部注意力机制
            local_attention_context_size: 局部注意力上下文大小
            logger: 日志记录器
            download_callback: 下载开始回调
            progress_callback: 下载进度回调 (percentage, downloaded_mb, total_mb, speed_mbps)
            status_callback: 状态更新回调
        """
        # 避免重复初始化
        if self._initialized:
            return
            
        self.model_name = model_name
        self.fp32 = fp32
        self.local_attention = local_attention
        self.local_attention_context_size = local_attention_context_size
        self.logger = logger
        self.download_callback = download_callback
        self.progress_callback = progress_callback
        self.status_callback = status_callback
        self._model = None
        self._initialized = True
        
        if self.logger:
            self.logger.info(f"SpeechRecognizer initialized for process {self._process_id}")
        
    def _load_model(self):
        """加载模型 - 进程和线程安全版本，防止多进程重复下载"""
        # 双重检查锁定模式
        if self._model is not None:
            return
            
        with self._model_lock:
            # 再次检查，防止在等待锁的过程中其他线程已经加载了模型
            if self._model is not None:
                return
                
            if self.logger:
                self.logger.info(f"Process {self._process_id}: Loading model: {self.model_name}")
                
            try:
                # 使用文件锁防止进程间重复下载（仅在支持的平台上）
                import tempfile
                try:
                    import fcntl
                    fcntl_available = True
                except ImportError:
                    fcntl_available = False
                    if self.logger:
                        self.logger.warning(f"Process {self._process_id}: fcntl not available on this platform, skipping file locking")
                
                lock_file_path = os.path.join(tempfile.gettempdir(), f"parakeet_download_{self.model_name.replace('/', '_')}.lock")
                
                if fcntl_available:
                    try:
                        # 创建进程间锁文件
                        with open(lock_file_path, 'w') as lock_file:
                            try:
                                # 尝试获取独占锁
                                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                                if self.logger:
                                    self.logger.info(f"Process {self._process_id}: Acquired download lock")
                                
                                # 再次检查模型是否需要下载（在锁内重新检查）
                                needs_download = self._check_if_model_needs_download()
                                
                                # 只有在需要下载时才通知UI显示下载对话框
                                if needs_download and self.download_callback:
                                    self.download_callback(self.model_name)
                                    
                                if needs_download and self.status_callback:
                                    self.status_callback("Initializing model download...")
                                elif self.status_callback:
                                    self.status_callback("Loading cached model...")
                                
                                # 加载模型，添加重试机制
                                max_retries = 3
                                for attempt in range(max_retries):
                                    try:
                                        if self.logger:
                                            self.logger.info(f"Process {self._process_id}: Loading model from {'cache' if not needs_download else 'download'} (attempt {attempt + 1})")
                                        self._model = from_pretrained(self.model_name)
                                        break
                                    except Exception as e:
                                        if attempt == max_retries - 1:
                                            raise e
                                        if self.logger:
                                            self.logger.warning(f"Process {self._process_id}: Model loading failed (attempt {attempt + 1}), retrying: {e}")
                                        import time
                                        time.sleep(2 ** attempt)  # 指数退避
                                
                                # 释放锁（函数结束时自动释放）
                                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                                if self.logger:
                                    self.logger.info(f"Process {self._process_id}: Released download lock")
                                
                            except IOError:
                                # 无法获取锁，说明其他进程正在下载
                                if self.logger:
                                    self.logger.info(f"Process {self._process_id}: Another process is downloading, waiting...")
                                if self.status_callback:
                                    self.status_callback("Another process is downloading the model, please wait...")
                                
                                # 阻塞等待锁（其他进程下载完成）
                                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                                if self.logger:
                                    self.logger.info(f"Process {self._process_id}: Download completed by other process, loading cached model")
                                
                                if self.status_callback:
                                    self.status_callback("Loading cached model...")
                                
                                # 直接加载已缓存的模型，添加重试机制
                                max_retries = 3
                                for attempt in range(max_retries):
                                    try:
                                        self._model = from_pretrained(self.model_name)
                                        break
                                    except Exception as e:
                                        if attempt == max_retries - 1:
                                            raise e
                                        if self.logger:
                                            self.logger.warning(f"Process {self._process_id}: Cached model loading failed (attempt {attempt + 1}), retrying: {e}")
                                        import time
                                        time.sleep(2 ** attempt)
                                
                                # 释放锁
                                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                                
                    except Exception as e:
                        if self.logger:
                            self.logger.warning(f"Process {self._process_id}: File lock failed, falling back to direct loading: {e}")
                        # 文件锁失败时的备用方案
                        needs_download = self._check_if_model_needs_download()
                        
                        if needs_download and self.download_callback:
                            self.download_callback(self.model_name)
                            
                        if needs_download and self.status_callback:
                            self.status_callback("Initializing model download...")
                        elif self.status_callback:
                            self.status_callback("Loading cached model...")
                        
                        # 添加重试机制
                        max_retries = 3
                        for attempt in range(max_retries):
                            try:
                                self._model = from_pretrained(self.model_name)
                                break
                            except Exception as e:
                                if attempt == max_retries - 1:
                                    raise e
                                if self.logger:
                                    self.logger.warning(f"Process {self._process_id}: Model loading failed (attempt {attempt + 1}), retrying: {e}")
                                import time
                                time.sleep(2 ** attempt)
                else:
                    # fcntl不可用，直接加载模型
                    if self.logger:
                        self.logger.info(f"Process {self._process_id}: Loading model directly (no file locking)")
                    needs_download = self._check_if_model_needs_download()
                    
                    if needs_download and self.download_callback:
                        self.download_callback(self.model_name)
                        
                    if needs_download and self.status_callback:
                        self.status_callback("Initializing model download...")
                    elif self.status_callback:
                        self.status_callback("Loading cached model...")
                        
                    # 添加重试机制
                    max_retries = 3
                    for attempt in range(max_retries):
                        try:
                            self._model = from_pretrained(self.model_name)
                            break
                        except Exception as e:
                            if attempt == max_retries - 1:
                                raise e
                            if self.logger:
                                self.logger.warning(f"Process {self._process_id}: Model loading failed (attempt {attempt + 1}), retrying: {e}")
                            import time
                            time.sleep(2 ** attempt)
                    
                # 配置模型参数
                try:
                    if hasattr(self._model, 'set_dtype'):
                        dtype = float32 if self.fp32 else bfloat16
                        self._model.set_dtype(dtype)
                        if self.logger:
                            self.logger.info(f"Process {self._process_id}: Model dtype set to {dtype}")
                    else:
                        if self.logger:
                            self.logger.info(f"Process {self._process_id}: Model does not support set_dtype method")
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Process {self._process_id}: Failed to set model dtype: {e}")
                
                try:
                    if self.local_attention and hasattr(self._model, 'set_local_attention'):
                        self._model.set_local_attention(
                            enabled=True,
                            context_size=self.local_attention_context_size
                        )
                        if self.logger:
                            self.logger.info(f"Process {self._process_id}: Local attention enabled with context size {self.local_attention_context_size}")
                    else:
                        if self.logger:
                            self.logger.info(f"Process {self._process_id}: Model does not support set_local_attention method")
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Process {self._process_id}: Failed to set local attention: {e}")
                    
                if self.logger:
                    self.logger.info(f"Process {self._process_id}: Model loaded successfully")
                    
                if self.status_callback:
                    self.status_callback("Model loaded successfully!")
                    
            except Exception as e:
                error_msg = f"Process {self._process_id}: Error loading model {self.model_name}: {e}"
                if self.logger:
                    self.logger.error(error_msg)
                raise RuntimeError(error_msg)
    
    def _check_if_model_needs_download(self):
        """检查模型是否需要下载 - 改进版本，检查关键模型文件"""
        try:
            import os
            from huggingface_hub import try_to_load_from_cache
            
            # 检查MLX模型的关键文件是否已缓存
            # 根据实际模型结构调整检查的文件列表
            essential_files = [
                "config.json",           # 模型配置
                "model.safetensors",     # 主要的模型权重文件
            ]
            
            # 可选文件（如果存在更好，但不是必需的）
            optional_files = [
                "tokenizer.json",        # tokenizer配置
                "preprocessor_config.json"  # 预处理器配置
            ]
            
            if self.logger:
                self.logger.info(f"Process {self._process_id}: Checking cache for model {self.model_name}")
            
            # 检查必需文件
            for filename in essential_files:
                try:
                    cached_file = try_to_load_from_cache(
                        repo_id=self.model_name,
                        filename=filename
                    )
                    if cached_file is None:
                        if self.logger:
                            self.logger.warning(f"Process {self._process_id}: Missing essential cached file: {filename}")
                        return True
                    else:
                        if self.logger:
                            self.logger.info(f"Process {self._process_id}: Found essential cached file: {filename}")
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Process {self._process_id}: Error checking {filename}: {e}")
                    return True
            
            # 检查可选文件（仅用于信息显示）
            for filename in optional_files:
                try:
                    cached_file = try_to_load_from_cache(
                        repo_id=self.model_name,
                        filename=filename
                    )
                    if cached_file is None:
                        if self.logger:
                            self.logger.info(f"Process {self._process_id}: Optional file not cached: {filename}")
                    else:
                        if self.logger:
                            self.logger.info(f"Process {self._process_id}: Found optional cached file: {filename}")
                except Exception as e:
                    if self.logger:
                        self.logger.info(f"Process {self._process_id}: Optional file check failed for {filename}: {e}")
            
            if self.logger:
                self.logger.info(f"Process {self._process_id}: All essential files found in cache, no download needed")
            return False
            
        except ImportError:
            if self.logger:
                self.logger.warning(f"Process {self._process_id}: huggingface_hub not available, assuming download needed")
            return True
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Process {self._process_id}: Cache check failed: {e}, assuming download needed")
            return True
    
    def transcribe(self, 
                   audio_path: str,
                   chunk_duration: Optional[float] = 120.0,
                   overlap_duration: float = 15.0,
                   progress_callback: Optional[Callable[[int, int], None]] = None) -> AlignedResult:
        """
        转录音频文件 - 支持分块处理和进程安全
        
        Args:
            audio_path: 音频文件路径
            chunk_duration: 分块时长（秒），None表示不分块
            overlap_duration: 重叠时长（秒）
            progress_callback: 进度回调函数 (current_chunk, total_chunks)
            
        Returns:
            AlignedResult: 转录结果
        """
        self._load_model()
        
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")
        
        if self.logger:
            self.logger.info(f"Process {self._process_id}: Starting transcription of: {audio_path}")
            
        try:
            # 使用模型锁确保同一时间只有一个转录任务在运行
            if self.logger:
                self.logger.info(f"Process {self._process_id}: Acquiring transcription lock...")
            
            with self._model_lock:
                if self.logger:
                    self.logger.info(f"Process {self._process_id}: Transcription lock acquired, starting transcription...")
                
                try:
                    # 使用原作者的方式直接调用模型的 transcribe 方法
                    dtype = float32 if self.fp32 else bfloat16
                    
                    # 先尝试直接转录，如果因为内存问题失败则降级到分块处理
                    try:
                        result = self._model.transcribe(
                            audio_path,
                            dtype=dtype,
                            chunk_duration=chunk_duration if chunk_duration else None,
                            overlap_duration=overlap_duration,
                            chunk_callback=lambda current, total: progress_callback(current, total) if progress_callback else None
                        )
                        
                        if self.logger:
                            self.logger.info(f"Process {self._process_id}: Direct transcription completed successfully")
                        return result
                        
                    except Exception as e:
                        if self.logger:
                            self.logger.error(f"Process {self._process_id}: All transcription attempts failed: {e}")
                            raise e
                        else:
                            raise e
                            
                except Exception as e:
                    if self.logger:
                        self.logger.error(f"Process {self._process_id}: All transcription attempts failed: {e}")
                        raise e
                    else:
                        raise e
            
            if self.logger:
                self.logger.info(f"Process {self._process_id}: Transcription completed for: {audio_path}")
                
            return result
            
        except Exception as e:
            error_msg = f"Process {self._process_id}: Error transcribing file {audio_path}: {e}"
            if self.logger:
                self.logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def _get_audio_duration(self, audio_path: str) -> float:
        """获取音频时长"""
        try:
            # 使用ffprobe获取音频时长
            cmd = [
                'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                '-of', 'csv=p=0', audio_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return float(result.stdout.strip())
            else:
                # 回退方案：假设时长
                file_size = os.path.getsize(audio_path)
                estimated_duration = file_size / (16000 * 2)  # 16kHz, 16-bit
                if self.logger:
                    self.logger.warning(f"Process {self._process_id}: Could not get exact duration, estimating {estimated_duration:.2f}s")
                return estimated_duration
        except Exception:
            # 默认时长
            return 60.0
    
    def _transcribe_chunk(self, audio_path: str) -> AlignedResult:
        """转录单个音频块"""
        try:
            # 使用模型处理音频 - 移除processor参数，因为新版API不支持
            result = self._model.transcribe(audio_path)
            return result
        except Exception as e:
            if self.logger:
                self.logger.error(f"Process {self._process_id}: Chunk transcription failed: {str(e)}")
            # 返回空结果而不是抛出异常 - 使用正确的构造函数参数
            return AlignedResult(text="", sentences=[])
    
    def _transcribe_with_chunks(self, 
                               audio_path: str,
                               audio_duration: float,
                               chunk_duration: float,
                               overlap_duration: float,
                               progress_callback: Optional[Callable[[int, int], None]] = None) -> AlignedResult:
        """分块转录长音频"""
        
        # 计算分块参数
        step_duration = chunk_duration - overlap_duration
        total_chunks = max(1, math.ceil((audio_duration - overlap_duration) / step_duration))
        
        if self.logger:
            self.logger.info(f"Process {self._process_id}: Processing {total_chunks} chunks (chunk: {chunk_duration}s, overlap: {overlap_duration}s)")
        
        all_sentences = []
        all_words = []
        
        for chunk_idx in range(total_chunks):
            try:
                # 计算当前块的时间范围
                start_time = chunk_idx * step_duration
                end_time = min(start_time + chunk_duration, audio_duration)
                
                if self.logger:
                    self.logger.info(f"Process {self._process_id}: Processing chunk {chunk_idx + 1}/{total_chunks} ({start_time:.1f}s - {end_time:.1f}s)")
                
                # 提取音频块
                chunk_path = self._extract_audio_chunk(audio_path, start_time, end_time)
                
                if chunk_path:
                    # 转录音频块
                    chunk_result = self._transcribe_chunk(chunk_path)
                    
                    # 调整时间戳并合并结果
                    self._merge_chunk_result(
                        chunk_result, 
                        all_sentences,
                        start_time,
                        overlap_duration if chunk_idx > 0 else 0.0
                    )
                    
                    # 清理临时文件
                    try:
                        os.unlink(chunk_path)
                    except Exception:
                        pass
                
                # 报告进度
                if progress_callback:
                    progress_callback(chunk_idx + 1, total_chunks)
                    
            except Exception as e:
                if self.logger:
                    self.logger.warning(f"Process {self._process_id}: Failed to process chunk {chunk_idx + 1}: {str(e)}")
                continue
        
        # 创建最终结果 - 使用正确的构造函数参数
        # 合并所有句子的文本
        combined_text = " ".join(sentence.text for sentence in all_sentences)
        final_result = AlignedResult(text=combined_text, sentences=all_sentences)
        if self.logger:
            self.logger.info(f"Process {self._process_id}: Transcription completed: {len(all_sentences)} sentences")
        
        return final_result
    
    def _extract_audio_chunk(self, audio_path: str, start_time: float, end_time: float) -> Optional[str]:
        """提取音频块"""
        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
                chunk_path = tmp_file.name
            
            # 使用ffmpeg提取音频块
            cmd = [
                'ffmpeg', '-y', '-i', audio_path,
                '-ss', str(start_time),
                '-t', str(end_time - start_time),
                '-ac', '1', '-ar', '16000',
                chunk_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode == 0 and os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 0:
                return chunk_path
            else:
                if self.logger:
                    self.logger.warning(f"Process {self._process_id}: Failed to extract audio chunk: {result.stderr}")
                try:
                    os.unlink(chunk_path)
                except Exception:
                    pass
                return None
                
        except Exception as e:
            if self.logger:
                self.logger.warning(f"Process {self._process_id}: Audio chunk extraction error: {str(e)}")
            return None
    
    def _merge_chunk_result(self, 
                           chunk_result: AlignedResult,
                           all_sentences: list,
                           time_offset: float,
                           overlap_duration: float):
        """合并块结果到总结果中"""
        if not chunk_result or not chunk_result.sentences:
            return
        
        # 处理句子
        for sentence in chunk_result.sentences:
            # 处理句子中的词（如果有的话）
            adjusted_tokens = []
            if hasattr(sentence, 'words') and sentence.words:
                for word in sentence.words:
                    adjusted_word = AlignedToken(
                        text=word.text,
                        start=word.start + time_offset,
                        end=word.end + time_offset,
                        id=getattr(word, 'id', 0),
                        duration=(word.end + time_offset) - (word.start + time_offset)
                    )
                    adjusted_tokens.append(adjusted_word)
            elif hasattr(sentence, 'tokens') and sentence.tokens:
                # 兼容 tokens 字段
                for token in sentence.tokens:
                    adjusted_token = AlignedToken(
                        text=token.text,
                        start=token.start + time_offset,
                        end=token.end + time_offset,
                        id=getattr(token, 'id', 0),
                        duration=(token.end + time_offset) - (token.start + time_offset)
                    )
                    adjusted_tokens.append(adjusted_token)
            
            # 调整时间戳 - 传入tokens参数
            adjusted_sentence = AlignedSentence(
                text=sentence.text,
                start=sentence.start + time_offset,
                end=sentence.end + time_offset,
                tokens=adjusted_tokens
            )
            
            # 跳过重叠部分的内容（除了第一个块）
            if time_offset == 0 or adjusted_sentence.start >= time_offset + overlap_duration:
                all_sentences.append(adjusted_sentence)

    @classmethod
    def cleanup_singleton(cls):
        """清理单例实例 - 用于应用程序退出时，支持多进程"""
        current_pid = os.getpid()
        with cls._lock:
            if current_pid in cls._instances:
                try:
                    instance = cls._instances[current_pid]
                    if hasattr(instance, '_model') and instance._model is not None:
                        # MLX 模型会自动清理，我们只需要将引用设为None
                        instance._model = None
                    # 使用实例的 logger 如果可用
                    if hasattr(instance, 'logger') and instance.logger:
                        instance.logger.info(f"Cleaned up SpeechRecognizer for process {current_pid}")
                except Exception as e:
                    # 使用实例的 logger 如果可用
                    if hasattr(instance, 'logger') and instance.logger:
                        instance.logger.error(f"Error cleaning up SpeechRecognizer for process {current_pid}: {e}")
                finally:
                    del cls._instances[current_pid]
    
    @classmethod
    def cleanup_all_instances(cls):
        """清理所有进程的实例 - 用于完全退出应用程序时"""
        with cls._lock:
            for pid, instance in list(cls._instances.items()):
                try:
                    if hasattr(instance, '_model') and instance._model is not None:
                        instance._model = None
                    # 使用实例的 logger 如果可用
                    if hasattr(instance, 'logger') and instance.logger:
                        instance.logger.info(f"Cleaned up SpeechRecognizer for process {pid}")
                except Exception as e:
                    if hasattr(instance, 'logger') and instance.logger:
                        instance.logger.error(f"Error cleaning up SpeechRecognizer for process {pid}: {e}")
            cls._instances.clear()
            # 无法使用实例logger，直接输出消息（这是最后的清理）
            pass  # All SpeechRecognizer instances cleaned up


class SubtitleFormatter:
    """字幕格式化器"""
    
    @staticmethod
    def format_timestamp(seconds: float, always_include_hours: bool = True, decimal_marker: str = ",") -> str:
        """格式化时间戳"""
        assert seconds >= 0
        milliseconds = round(seconds * 1000.0)

        hours = milliseconds // 3_600_000
        milliseconds %= 3_600_000

        minutes = milliseconds // 60_000
        milliseconds %= 60_000

        seconds = milliseconds // 1_000
        milliseconds %= 1_000

        hours_marker = f"{hours:02d}:" if always_include_hours or hours > 0 else ""
        return (
            f"{hours_marker}{minutes:02d}:{seconds:02d}{decimal_marker}{milliseconds:03d}"
        )

    @staticmethod
    def to_txt(result: AlignedResult) -> str:
        """格式化为纯文本"""
        return result.text.strip()

    @staticmethod
    def to_srt(result: AlignedResult, highlight_words: bool = False) -> str:
        """
        格式化为SRT字幕文件
        
        Args:
            result: 转录结果
            highlight_words: 是否高亮单词
            
        Returns:
            str: SRT格式字幕内容
        """
        # 处理空结果
        if not result or not result.sentences:
            return ""
            
        srt_content = []
        entry_index = 1
        
        if highlight_words:
            for sentence in result.sentences:
                # 检查句子是否有tokens属性
                if hasattr(sentence, 'tokens') and sentence.tokens:
                    for i, token in enumerate(sentence.tokens):
                        start_time = SubtitleFormatter.format_timestamp(token.start, decimal_marker=",")
                        end_time = SubtitleFormatter.format_timestamp(
                            token.end
                            if token == sentence.tokens[-1]
                            else sentence.tokens[i + 1].start,
                            decimal_marker=",",
                        )

                        text = ""
                        for j, inner_token in enumerate(sentence.tokens):
                            if i == j:
                                text += inner_token.text.replace(
                                    inner_token.text.strip(),
                                    f"<u>{inner_token.text.strip()}</u>",
                                )
                            else:
                                text += inner_token.text
                        text = text.strip()

                        srt_content.append(f"{entry_index}")
                        srt_content.append(f"{start_time} --> {end_time}")
                        srt_content.append(text)
                        srt_content.append("")
                        entry_index += 1
                else:
                    # 如果没有tokens，直接使用句子级别的时间戳
                    start_time = SubtitleFormatter.format_timestamp(sentence.start, decimal_marker=",")
                    end_time = SubtitleFormatter.format_timestamp(sentence.end, decimal_marker=",")
                    text = sentence.text.strip()

                    srt_content.append(f"{entry_index}")
                    srt_content.append(f"{start_time} --> {end_time}")
                    srt_content.append(text)
                    srt_content.append("")
                    entry_index += 1
        else:
            for sentence in result.sentences:
                start_time = SubtitleFormatter.format_timestamp(sentence.start, decimal_marker=",")
                end_time = SubtitleFormatter.format_timestamp(sentence.end, decimal_marker=",")
                text = sentence.text.strip()

                srt_content.append(f"{entry_index}")
                srt_content.append(f"{start_time} --> {end_time}")
                srt_content.append(text)
                srt_content.append("")
                entry_index += 1

        return "\n".join(srt_content)

    @staticmethod
    def to_vtt(result: AlignedResult, highlight_words: bool = False) -> str:
        """
        格式化为VTT字幕文件
        
        Args:
            result: 转录结果
            highlight_words: 是否高亮单词
            
        Returns:
            str: VTT格式字幕内容
        """
        vtt_content = ["WEBVTT", ""]
        
        if highlight_words:
            for sentence in result.sentences:
                # 检查句子是否有tokens属性
                if hasattr(sentence, 'tokens') and sentence.tokens:
                    for i, token in enumerate(sentence.tokens):
                        start_time = SubtitleFormatter.format_timestamp(token.start, decimal_marker=".")
                        end_time = SubtitleFormatter.format_timestamp(
                            token.end
                            if token == sentence.tokens[-1]
                            else sentence.tokens[i + 1].start,
                            decimal_marker=".",
                        )

                        text_line = ""
                        for j, inner_token in enumerate(sentence.tokens):
                            if i == j:
                                text_line += inner_token.text.replace(
                                    inner_token.text.strip(),
                                    f"<b>{inner_token.text.strip()}</b>",
                                )
                            else:
                                text_line += inner_token.text
                        text_line = text_line.strip()

                        vtt_content.append(f"{start_time} --> {end_time}")
                        vtt_content.append(text_line)
                        vtt_content.append("")
                else:
                    # 如果没有tokens，直接使用句子级别的时间戳
                    start_time = SubtitleFormatter.format_timestamp(sentence.start, decimal_marker=".")
                    end_time = SubtitleFormatter.format_timestamp(sentence.end, decimal_marker=".")
                    text_line = sentence.text.strip()

                    vtt_content.append(f"{start_time} --> {end_time}")
                    vtt_content.append(text_line)
                    vtt_content.append("")
        else:
            for sentence in result.sentences:
                start_time = SubtitleFormatter.format_timestamp(sentence.start, decimal_marker=".")
                end_time = SubtitleFormatter.format_timestamp(sentence.end, decimal_marker=".")
                text_line = sentence.text.strip()

                vtt_content.append(f"{start_time} --> {end_time}")
                vtt_content.append(text_line)
                vtt_content.append("")

        return "\n".join(vtt_content)

    @staticmethod
    def _aligned_token_to_dict(token: AlignedToken) -> Dict[str, Any]:
        """将对齐的token转换为字典"""
        return {
            "text": token.text,
            "start": round(token.start, 3),
            "end": round(token.end, 3),
            "duration": round(getattr(token, 'duration', token.end - token.start), 3),
        }

    @staticmethod
    def _aligned_sentence_to_dict(sentence: AlignedSentence) -> Dict[str, Any]:
        """将对齐的句子转换为字典"""
        tokens_list = []
        if hasattr(sentence, 'tokens') and sentence.tokens:
            tokens_list = [SubtitleFormatter._aligned_token_to_dict(token) for token in sentence.tokens]
        
        return {
            "text": sentence.text,
            "start": round(sentence.start, 3),
            "end": round(sentence.end, 3),
            "duration": round(getattr(sentence, 'duration', sentence.end - sentence.start), 3),
            "tokens": tokens_list,
        }

    @staticmethod
    def to_json(result: AlignedResult) -> str:
        """
        格式化为JSON
        
        Args:
            result: 转录结果
            
        Returns:
            str: JSON格式内容
        """
        # 处理空结果
        if not result:
            return json.dumps({"sentences": [], "words": []}, ensure_ascii=False, indent=2)
            
        output_dict = {
            "text": result.text if hasattr(result, 'text') else "",
            "sentences": [
                SubtitleFormatter._aligned_sentence_to_dict(sentence) 
                for sentence in (result.sentences if result.sentences else [])
            ],
        }
        return json.dumps(output_dict, indent=2, ensure_ascii=False)
