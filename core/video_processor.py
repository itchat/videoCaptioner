import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import requests.adapters
from PyQt6.QtCore import QRunnable
import os
import subprocess
from datetime import datetime
from deep_translator import GoogleTranslator
from core.worker_signals import WorkerSignals
from core.speech_recognizer import SpeechRecognizer, SubtitleFormatter
from utils.logger import VideoLogger
from utils.system_optimizer import SystemOptimizer
import threading
import re
import json
from config import OPENAI_MODEL, OPENAI_CUSTOM_PROMPT


class ContentFilteredException(Exception):
    """Exception raised when content is filtered by OpenAI safety system"""
    pass


class VideoProcessor(QRunnable):
    def __init__(self, video_path, engine, api_settings, cache_dir,
                 progress_callback=None, status_callback=None):
        super().__init__()
        self.video_path = video_path
        self.engine = engine
        self.api_settings = api_settings
        self.cache_dir = cache_dir
        self.progress_callback = progress_callback
        self.status_callback = status_callback
        self.base_name = os.path.basename(video_path)
        self.logger = VideoLogger(cache_dir)
        self.signals = WorkerSignals()
        
        # 创建复用的requests会话以提高性能
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_settings.get('api_key', '')}",
            "Content-Type": "application/json"
        })
        
        # 配置连接池以提高性能
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=3,
            pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # 语音识别器 - 使用 Parakeet MLX
        self._speech_recognizer = None
    
        # 跟踪处理状态以确保正确清理
        self._processing_complete = False
        
        # 翻译缓存以提高重复短语的处理效率
        self._translation_cache = {}
        
        # 添加持久化缓存支持
        self._cache_file = os.path.join(cache_dir, "translation_cache.json")
        self._load_translation_cache()
        
        # 添加批量优化参数
        self._batch_optimization_enabled = True
        
        # 添加API请求优化
        self._request_session_pool = {}
        
        # 计时器相关变量
        self._start_time = None
        self._timer_thread = None
        self._timer_stop_event = threading.Event()
        
        # 系统优化配置
        self.optimizer = SystemOptimizer()
        self.optimized_config = self.optimizer.get_optimized_config()
        
        # 记录系统优化信息
        self.logger.info(f"Video processor optimization - CPU cores: {self.optimized_config['system_info']['cpu_count']}")
        if self.optimized_config['system_info'].get('is_apple_silicon'):
            self.logger.info("Apple Silicon detected - using optimized video processing")
        if self.optimized_config['use_hardware_accel']:
            self.logger.info("Hardware acceleration available for video processing")

    def _start_timer(self):
        """启动计时器线程"""
        self._start_time = time.time()
        self._timer_stop_event.clear()
        self._timer_thread = threading.Thread(target=self._timer_worker, daemon=True)
        self._timer_thread.start()
        
    def _stop_timer(self):
        """停止计时器线程"""
        if self._timer_thread and self._timer_thread.is_alive():
            self._timer_stop_event.set()
            self._timer_thread.join(timeout=1.0)
    
    def _timer_worker(self):
        """计时器工作线程"""
        while not self._timer_stop_event.is_set():
            if self._start_time:
                elapsed = time.time() - self._start_time
                elapsed_str = self._format_elapsed_time(elapsed)
                self.signals.timer_update.emit(self.base_name, elapsed_str)
            time.sleep(1)  # 每秒更新一次
    
    def _format_elapsed_time(self, elapsed_seconds):
        """格式化经过的时间为 MM:SS 格式"""
        minutes = int(elapsed_seconds // 60)
        seconds = int(elapsed_seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"

    def report_progress(self, progress):
        self.signals.file_progress.emit(self.base_name, progress)
        if self.progress_callback:
            self.progress_callback(self.base_name, progress)

    def report_status(self, status):
        self.signals.status.emit(self.base_name, status)
        if self.status_callback:
            self.status_callback(self.base_name, status)

    def run(self):
        try:
            # 启动计时器
            self._start_timer()
            
            self.logger.info(f"Starting to process video: {self.base_name}")
            cache_paths = self.get_cache_paths()

            # Produce Audio (0-20%)
            self.report_status("Extracting audio...")
            self.report_progress(0)
            self.extract_audio(cache_paths['audio'])
            self.logger.info("Audio extraction completed")
            self.report_progress(20)

            # Generate Subtitle (20-40%)
            self.report_status("Recognizing speech...")
            self.generate_subtitles(cache_paths['audio'], cache_paths['srt'])
            self.logger.info("Subtitle generation complete")
            self.report_progress(40)

            # Translate Subtitle (40-70%)
            self.report_status("Translating subtitles...")
            with open(cache_paths['srt'], "r", encoding="utf-8") as f:
                lines = f.readlines()
            translated_content = self.translate_subtitles(lines)
            
            # Check if bilingual subtitles are empty before proceeding
            if not translated_content or translated_content.strip() == "":
                error_msg = "双语字幕为空，跳过视频合成任务"
                self.logger.warning(error_msg)
                self.report_status(error_msg)
                self.report_progress(100)
                self.signals.finished.emit()
                return
            
            with open(cache_paths['bilingual_srt'], "w", encoding="utf-8") as f:
                f.write(translated_content)
            self.logger.info("Subtitle translation completed")
            self.report_progress(70)

            # Composite Video (70-100%)
            self.report_status("Synthesizing video...")
            self.burn_subtitles(cache_paths['bilingual_srt'], cache_paths['output_video'])
            self.logger.info("Video synthesis completed")
            self.report_progress(100)
            self.report_status("Processing completed!")

            # Send Completion Signal
            self.signals.finished.emit()

        except Exception as e:
            error_msg = f"Processing failed: {str(e)}"
            self.logger.error(error_msg)
            self.signals.error.emit(f"Failed to process video {self.base_name} : {str(e)}")
            self.signals.status.emit(self.base_name, error_msg)
            # Send Completion Signal even if it's failed
            self.signals.finished.emit()
        finally:
            # 停止计时器
            self._stop_timer()
            
            # 确保资源被正确关闭
            try:
                # 保存翻译缓存
                self._save_translation_cache()
                
                if hasattr(self, 'session'):
                    self.session.close()
                    
                # 释放语音识别器内存
                if hasattr(self, '_speech_recognizer') and self._speech_recognizer is not None:
                    del self._speech_recognizer
                    self._speech_recognizer = None
                    
                # 清理日志处理器
                if hasattr(self, 'logger'):
                    self.logger.cleanup()
            except Exception as cleanup_error:
                print(f"Error during cleanup: {cleanup_error}")  # 使用print避免循环依赖

    def get_cache_paths(self):
        base_name = os.path.splitext(self.base_name)[0]
        return {
            'audio': os.path.join(self.cache_dir, f"{base_name}_audio.wav"),
            'srt': os.path.join(self.cache_dir, f"{base_name}_output.srt"),
            'bilingual_srt': os.path.join(self.cache_dir, f"{base_name}_bilingual.srt"),
            'output_video': os.path.join(
                os.path.dirname(self.video_path),
                f"{base_name}_subtitled_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                f"{os.path.splitext(self.video_path)[1]}"
            )
        }

    @staticmethod
    def get_ffmpeg_path():
        # Potential FFmpeg Paths
        possible_paths = [
            '/opt/homebrew/bin/ffmpeg',  # MacOS Homebrew
            '/usr/local/bin/ffmpeg',  # Linux/MacOS Path
            '/usr/bin/ffmpeg',  # Others
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None

    def check_has_audio(self):
        """检查视频文件是否包含音频流"""
        ffmpeg_path = self.get_ffmpeg_path()
        if not ffmpeg_path:
            return False
            
        try:
            cmd = [ffmpeg_path, "-i", self.video_path, "-hide_banner", "-f", "null", "-"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            # 检查stderr输出中是否有音频流信息
            stderr_output = result.stderr.lower()
            return "audio:" in stderr_output or "stream #" in stderr_output and ("audio" in stderr_output or "mp3" in stderr_output or "aac" in stderr_output or "wav" in stderr_output)
        except Exception as e:
            self.logger.warning(f"Could not check audio streams: {e}")
            return True  # 默认假设有音频，让extract_audio处理

    def extract_audio(self, audio_path):
        ffmpeg_path = self.get_ffmpeg_path()
        if not ffmpeg_path:
            raise FileNotFoundError("Could not find ffmpeg. Please install it first.")
            
        # 检查输入文件
        if not os.path.exists(self.video_path):
            raise FileNotFoundError(f"Video file not found: {self.video_path}")
        
        # 检查视频是否有音频流
        if not self.check_has_audio():
            self.logger.warning("Video file has no audio streams, creating empty audio file")
            # 创建一个短暂的静音音频文件
            try:
                cmd = [ffmpeg_path, "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "0.1", "-q:a", "0", audio_path, "-y"]
                subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
                return True
            except Exception as e:
                self.logger.error(f"Failed to create silent audio file: {e}")
                raise RuntimeError("Video has no audio and failed to create silent audio file")
            
        try:
            # 使用系统优化的硬件加速参数
            cmd = [ffmpeg_path]
            
            # 添加硬件加速（如果可用）
            if self.optimized_config['use_hardware_accel']:
                cmd.extend(["-hwaccel", "videotoolbox"])
                self.logger.info("Using VideoToolbox hardware acceleration for audio extraction")
            
            cmd.extend([
                "-i", self.video_path,
                "-q:a", "0",
                "-map", "a",
                "-ac", "1",  # 转换为单声道以减少文件大小
                "-ar", "16000",  # 降低采样率，对语音识别足够
                audio_path,
                "-y"
            ])
            
            result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
            
            self.logger.info("Audio extraction completed successfully")
            
            # 验证输出文件
            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                raise RuntimeError("Audio extraction failed: output file is empty or missing")
                
            return True
        except subprocess.TimeoutExpired:
            raise RuntimeError("Audio extraction timeout: process took too long")
        except subprocess.CalledProcessError as e:
            # 如果音频提取失败，可能是没有音频流，尝试创建静音文件
            if "no such file or directory" not in str(e.stderr).lower():
                try:
                    self.logger.warning("Audio extraction failed, attempting to create silent audio file")
                    cmd = [ffmpeg_path, "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono", "-t", "0.1", "-q:a", "0", audio_path, "-y"]
                    subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
                    return True
                except Exception:
                    pass
            
            error_msg = f"Error during audio extraction: {e.stderr}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

    def generate_subtitles(self, audio_path, srt_path):
        """使用 Parakeet MLX 生成字幕"""
        # 初始化语音识别器（如果尚未初始化）
        if self._speech_recognizer is None:
            self.logger.info("Initializing Parakeet MLX speech recognizer...")
            self.report_progress(25)
            
            try:
                # 使用默认的 Parakeet 模型，添加下载回调
                self._speech_recognizer = SpeechRecognizer(
                    model_name="mlx-community/parakeet-tdt-0.6b-v2",
                    fp32=False,  # 使用 bfloat16 精度以节省内存
                    local_attention=True,  # 使用局部注意力减少内存使用
                    local_attention_context_size=256,
                    logger=self.logger,
                    download_callback=lambda model_name: self.signals.download_started.emit(model_name),
                    progress_callback=lambda percentage, downloaded_mb, total_mb, speed_mbps: (
                        self.signals.download_progress.emit(percentage, downloaded_mb, total_mb, speed_mbps),
                        self.signals.download_completed.emit() if percentage == 100 else None
                    )[0],  # 只返回第一个结果
                    status_callback=lambda message: self.signals.download_status.emit(message)
                )
                self.logger.info("Parakeet MLX model initialized successfully")
                
            except Exception as e:
                self.logger.error(f"Failed to initialize Parakeet MLX model: {str(e)}")
                self.signals.download_error.emit(f"Failed to initialize Parakeet MLX model: {str(e)}")
                raise RuntimeError(f"Failed to initialize Parakeet MLX model: {str(e)}")
        
        self.report_progress(30)  # 模型加载完成
        
        # 使用 Parakeet MLX 进行转录
        try:
            self.logger.info(f"Starting transcription of: {audio_path}")
            
            # 检查音频文件大小，如果太小（如静音文件），直接创建空字幕
            if os.path.getsize(audio_path) < 1000:  # 小于1KB，可能是静音文件
                self.logger.info("Audio file is very small, likely silent - creating empty subtitle file")
                with open(srt_path, "w", encoding="utf-8") as f:
                    f.write("")  # 创建空字幕文件
                return
            
            # 定义进度回调函数
            def progress_callback(current_chunk, total_chunks):
                if total_chunks > 0:
                    chunk_progress = int((current_chunk / total_chunks) * 10)  # 10% 的进度范围
                    progress = 30 + chunk_progress
                    self.report_progress(min(40, progress))
            
            # 进行转录
            result = self._speech_recognizer.transcribe(
                audio_path,
                chunk_duration=120.0,  # 2分钟分块
                overlap_duration=15.0,  # 15秒重叠
                progress_callback=progress_callback
            )
            
            self.report_progress(40)  # 转录完成
            
            # 使用字幕格式化器生成 SRT 格式
            srt_content = SubtitleFormatter.to_srt(result, highlight_words=False)
            
            # 写入 SRT 文件
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
                
            # 统计生成的字幕段数
            segment_count = len(result.sentences)
            self.logger.info(f"Transcription completed, generated {segment_count} segments")
            
        except Exception as e:
            self.logger.error(f"Transcription failed: {str(e)}")
            raise RuntimeError(f"Transcription failed: {str(e)}")

    def translate_subtitles(self, lines):
        try:
            # 检查是否为空字幕文件
            if not lines or all(not line.strip() for line in lines):
                self.logger.info("Empty subtitle file detected, skipping translation")
                return ""
            
            entries = []
            current_id = None
            current_timestamp = ""
            current_text = []
            parsing_state = "id"  # 可能的状态: id, timestamp, text

            for line in lines:
                line = line.strip()
                if not line:  # 空行表示一个字幕条目结束
                    if current_id is not None and current_timestamp and current_text:
                        entries.append({
                            'id': current_id,
                            'timestamp': current_timestamp,
                            'text': '\n'.join(current_text),
                            'translated': False
                        })
                    # 重置状态为解析新条目的ID
                    current_id = None
                    current_timestamp = ""
                    current_text = []
                    parsing_state = "id"
                    continue
                
                if parsing_state == "id" and line.isdigit():
                    current_id = int(line)
                    parsing_state = "timestamp"
                elif parsing_state == "timestamp" and '-->' in line:
                    current_timestamp = line
                    parsing_state = "text"
                elif parsing_state == "text":
                    current_text.append(line)

            # 处理文件末尾可能存在的最后一个条目
            if current_id is not None and current_timestamp and current_text:
                entries.append({
                    'id': current_id,
                    'timestamp': current_timestamp,
                    'text': '\n'.join(current_text),
                    'translated': False
                })

            # Use ThreadPool for Parallel Translation with intelligent batching
            translated_entries = []
            translation_lock = threading.Lock()
            total_entries = len(entries)
            completed_count = 0
            
            if total_entries == 0:
                self.logger.warning("No valid subtitle entries found to translate")
                return ""
                
            self.logger.info(f"Starting translation of {total_entries} subtitle entries")
            
            # 使用批量翻译 - 至少需要4个段落
            if self._should_use_batch_translation(entries):
                self.logger.info("Using optimized batch translation for efficiency")
                batch_result = self._batch_translate_openai(entries)
                if batch_result:
                    translated_entries = batch_result
                    self.signals.file_progress.emit(self.base_name, 70)  # 批量完成，直接到70%
                else:
                    # 批量失败，回退到单独翻译
                    self.logger.info("Batch translation failed, using individual translation")
                    translated_entries = self._translate_individually(entries, translation_lock, total_entries)
            else:
                # 使用单独翻译（Google翻译或条目太少）
                translated_entries = self._translate_individually(entries, translation_lock, total_entries)

            # Sort by ID to Ensure Correct Subtitle Ordering
            translated_entries.sort(key=lambda x: x['id'])

            # Construct Final Subtitle Content
            translated_content = ""
            for entry in translated_entries:
                translated_content += f"{entry['id']}\n{entry['timestamp']}\n{entry['text']}\n\n"

            return translated_content

        except Exception as e:
            self.signals.error.emit(f"Translation Process Failed: {str(e)}")
            raise

    def _translate_entry(self, entry):
        """Individual Subtitle Item Translation Handling with intelligent retry logic"""
        max_attempts = 3
        base_delay = 1  # 基础延迟时间（秒）
        
        for attempt in range(1, max_attempts + 1):
            try:
                if self.engine == "OpenAI Translate":
                    return self._translate_with_openai(entry)
                else:  # Google Translation
                    return self._translate_with_google(entry)
            except ContentFilteredException as cf_e:
                # Content filtering is not retryable - return original text immediately
                self.logger.info(f"Content filtered for subtitle {entry['id']}, using original text: {entry['text'][:50]}...")
                return entry['text']  # Return original text when content is filtered
            except Exception as e:
                if attempt == max_attempts:
                    self.logger.error(f"Max attempts reached for subtitle {entry['id']}: {str(e)}")
                    raise
                
                # 根据错误类型决定延迟策略
                if "429" in str(e) or "rate limit" in str(e).lower():
                    # 速率限制错误，使用更长的延迟
                    delay = base_delay * (3 ** (attempt - 1))
                    self.logger.warning(f"Rate limit hit for subtitle {entry['id']}, waiting {delay}s before retry {attempt + 1}")
                elif "timeout" in str(e).lower() or "connection" in str(e).lower():
                    # 网络错误，使用中等延迟
                    delay = base_delay * (2 ** (attempt - 1))
                    self.logger.warning(f"Network error for subtitle {entry['id']}, retrying in {delay}s: {str(e)}")
                else:
                    # 其他错误，使用标准延迟
                    delay = base_delay * (1.5 ** (attempt - 1))
                    self.logger.warning(f"Translation attempt {attempt} failed for subtitle {entry['id']}, retrying in {delay}s: {str(e)}")
                
                time.sleep(delay)

    def _translate_with_openai(self, entry):
        """Use OpenAI for Single Subtitle Translation with session reuse and enhanced caching"""
        # 检查缓存
        cached_translation = self._get_cached_translation(entry['text'], "openai")
        if cached_translation:
            return cached_translation
        
        # 使用配置文件中的自定义prompt
        system_prompt = OPENAI_CUSTOM_PROMPT
        
        user_prompt = f"Translate to Chinese (output translation only):\n\n{entry['text']}"
            
        data = {
            "model": self.api_settings.get("model", OPENAI_MODEL),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0,  # 降低温度以获得更一致的翻译
            "max_tokens": 1000
        }

        try:
            response = self.session.post(
                f"{self.api_settings['base_url']}/v1/chat/completions",
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    # 检查响应结构
                    if 'choices' not in result or not result['choices']:
                        raise ValueError(f"Invalid API response structure: {result}")
                    
                    choice = result['choices'][0]
                    
                    # 检查是否被内容过滤器阻止
                    if choice.get('finish_reason') == 'content_filter':
                        # 如果被内容过滤器阻止，抛出特定异常
                        raise ContentFilteredException(f"Content filtered by OpenAI safety system for entry: {entry['text'][:50]}...")
                    else:
                        # 正常的响应处理
                        if 'message' not in choice or 'content' not in choice['message']:
                            raise ValueError(f"Invalid message structure in API response: {result}")
                        
                        content = choice['message']['content'].strip()
                        if not content:
                            raise ValueError("Empty response from OpenAI API")
                    
                    # 缓存结果
                    self._set_cached_translation(entry['text'], "openai", content)
                    return content
                except json.JSONDecodeError as json_err:
                    # 记录原始响应内容以便调试
                    response_text = response.text[:500]  # 限制长度避免日志过长
                    self.logger.error(f"JSON decode error. Response text: {response_text}")
                    raise requests.exceptions.RequestException(f"Invalid JSON response from OpenAI API: {str(json_err)}")
                except (KeyError, IndexError, ValueError) as struct_err:
                    # 响应结构错误
                    self.logger.error(f"API response structure error: {str(struct_err)}")
                    raise requests.exceptions.RequestException(f"Invalid API response structure: {str(struct_err)}")
            elif response.status_code == 429:  # 速率限制
                raise requests.exceptions.RequestException(f"Rate limit exceeded: {response.status_code}")
            else:
                raise requests.exceptions.RequestException(f"OpenAI API error: {response.status_code} - {response.text}")
                
        except requests.exceptions.Timeout:
            raise requests.exceptions.RequestException("OpenAI API request timeout")
        except requests.exceptions.ConnectionError:
            raise requests.exceptions.RequestException("OpenAI API connection error")

    def _translate_with_google(self, entry):
        """Translated using the Deep Translator with better error handling and enhanced caching."""
        # 检查缓存
        cached_translation = self._get_cached_translation(entry['text'], "google")
        if cached_translation:
            return cached_translation
            
        try:
            text_to_translate = entry['text'].strip()
            if not text_to_translate:
                raise ValueError("Empty text to translate")
                
            translator = GoogleTranslator(source='auto', target='zh-CN')
            translated_text = translator.translate(text_to_translate)
            
            if not translated_text:
                raise ValueError("Empty translation result from Google Translate")
            
            # 缓存结果
            self._set_cached_translation(entry['text'], "google", translated_text)
            return translated_text
        except Exception as e:
            raise Exception(f"Google Translate error: {str(e)}")

    def burn_subtitles(self, subtitle_path, output_path):
        ffmpeg_path = self.get_ffmpeg_path()
        if not ffmpeg_path:
            raise FileNotFoundError("Could not find ffmpeg. Please install it first.")
            
        # 检查输入文件
        if not os.path.exists(subtitle_path):
            raise FileNotFoundError(f"Subtitle file not found: {subtitle_path}")
        
        # 检查字幕文件是否为空或只包含空白内容
        try:
            with open(subtitle_path, 'r', encoding='utf-8') as f:
                subtitle_content = f.read().strip()
                if not subtitle_content:
                    raise ValueError(f"Subtitle file is empty: {subtitle_path}")
        except Exception as e:
            raise ValueError(f"Error reading subtitle file {subtitle_path}: {str(e)}")
            
        try:
            # 使用更高效的字幕烧录方法，包含进度更新
            cmd = [
                ffmpeg_path,
                "-hwaccel", "videotoolbox",
                "-i", self.video_path,
                "-vf", f"subtitles='{subtitle_path}':force_style='FontSize=16,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BorderStyle=4'",
                "-c:v", "h264_videotoolbox",
                "-c:a", "copy",
                "-preset", "medium",  # 更好的质量和压缩比
                "-movflags", "+faststart",  # 优化在线播放
                output_path,
                "-y"  # 覆盖已存在的文件
            ]
            
            # 使用 Popen 来监控进度
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True
            )
            
            # 监控进度 (70% -> 100%)
            progress_start = 70
            progress_range = 30
            
            stderr_output = ""
            while True:
                output = process.stderr.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    stderr_output += output
                    # 简单的进度估算，每秒增加一点进度
                    current_progress = progress_start + min(progress_range, len(stderr_output) // 100)
                    if current_progress > progress_start:
                        self.report_progress(min(99, current_progress))
            
            # 等待进程完成
            return_code = process.poll()
            if return_code != 0:
                raise subprocess.CalledProcessError(return_code, cmd, stderr=stderr_output)
                
            # 验证输出文件
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise RuntimeError("Video processing failed: output file is empty or missing")
            
            self.logger.info("Video processing completed successfully")
            return True
        except subprocess.CalledProcessError as e:
            error_msg = f"Error during FFmpeg processing: {e.stderr}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

    def _should_use_batch_translation(self, entries):
        """判断是否应该使用批量翻译，基于更智能的启发式算法"""
        if self.engine != "OpenAI Translate":
            return False
            
        if len(entries) < 3:  # 降低批量翻译门槛
            return False
            
        # 分析字幕特征
        total_chars = sum(len(entry['text']) for entry in entries)
        avg_chars = total_chars / len(entries)
        short_entries = sum(1 for entry in entries if len(entry['text']) < 120)  # 稍微增加短字幕的长度门槛
        
        # 如果大部分字幕都很短且平均长度合适，使用批量翻译
        short_ratio = short_entries / len(entries)
        
        # 更积极的判断条件 - 优先使用批量翻译
        return (
            short_ratio > 0.4 and  # 40%以上是短字幕
            avg_chars < 100 and    # 平均长度限制
            len(entries) <= 30 and # 增加批量处理的条目数
            total_chars < 2000     # 增加总字符数限制，利用更大的context window
        )
    
    def _batch_translate_openai(self, entries):
        """批量翻译短字幕以提高效率 - 动态批次大小优化"""
        # 根据条目数量和平均长度动态调整批次大小
        avg_chars = sum(len(entry['text']) for entry in entries) / len(entries)
        
        if avg_chars < 30:
            batch_size = min(8, len(entries))  # 非常短的文本，更大批次
        elif avg_chars < 60:
            batch_size = min(6, len(entries))  # 短文本，中等批次
        else:
            batch_size = min(4, len(entries))  # 较长文本，小批次
            
        all_translated_entries = []
        
        # 并行处理多个批次
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        # 将所有批次准备好
        batch_tasks = []
        for i in range(0, len(entries), batch_size):
            batch_entries = entries[i:i + batch_size]
            batch_tasks.append((i // batch_size, batch_entries))
        
        # 使用较少的线程处理批量翻译以避免API限制
        max_batch_workers = min(3, len(batch_tasks))
        
        with ThreadPoolExecutor(max_workers=max_batch_workers) as executor:
            future_to_batch = {
                executor.submit(self._process_single_batch, batch_id, batch_entries): (batch_id, batch_entries)
                for batch_id, batch_entries in batch_tasks
            }
            
            for future in as_completed(future_to_batch):
                batch_id, batch_entries = future_to_batch[future]
                try:
                    batch_result = future.result()
                    if batch_result:
                        all_translated_entries.extend(batch_result)
                    else:
                        # 如果批量翻译失败，记录但不退出
                        self.logger.warning(f"Batch {batch_id} translation failed, will use individual translation for these entries")
                        return None
                except Exception as e:
                    self.logger.warning(f"Batch {batch_id} failed with error: {str(e)}")
                    return None
        
        # 检查翻译完整性
        if len(all_translated_entries) >= len(entries) * 0.85:  # 提高成功率要求到85%
            return all_translated_entries
        else:
            self.logger.warning(f"Batch translation incomplete: {len(all_translated_entries)}/{len(entries)} entries")
            return None

    def _process_single_batch(self, batch_id, batch_entries):
        """处理单个批次的翻译"""
        # 使用JSON格式而不是%%分隔符，更可靠
        if len(batch_entries) == 1:
            # 单段落输入，直接使用文本
            batch_text = batch_entries[0]['text']
            is_single = True
        else:
            # 多段落输入，使用JSON格式
            batch_data = []
            for i, entry in enumerate(batch_entries):
                batch_data.append({
                    "id": i,
                    "text": entry['text']
                })
            batch_text = json.dumps(batch_data, ensure_ascii=False, indent=2)
            is_single = False
        
        # 使用配置文件中的自定义prompt
        system_prompt = OPENAI_CUSTOM_PROMPT
        
        if is_single:
            user_prompt = f"Translate to Chinese (output translation only):\n\n{batch_text}"
        else:
            user_prompt = f"Translate the text field of each JSON object to Chinese and return the same JSON structure with translated text:\n\n{batch_text}"
        
        data = {
            "model": self.api_settings.get("model", OPENAI_MODEL),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0,
            "max_tokens": 3000  # 增加token限制
        }

        try:
            response = self.session.post(
                f"{self.api_settings['base_url']}/v1/chat/completions",
                json=data,
                timeout=90  # 增加超时时间
            )
            
            if response.status_code == 200:
                try:
                    result = response.json()
                    if 'choices' not in result or not result['choices']:
                        raise ValueError(f"Invalid API response structure: {result}")
                    
                    choice = result['choices'][0]
                    
                    if choice.get('finish_reason') == 'content_filter':
                        raise ContentFilteredException("Batch translation content filtered by OpenAI safety system")
                    else:
                        if 'message' not in choice or 'content' not in choice['message']:
                            raise ValueError(f"Invalid message structure in API response: {result}")
                        
                        content = choice['message']['content'].strip()
                except json.JSONDecodeError as json_err:
                    response_text = response.text[:500]
                    self.logger.error(f"Batch {batch_id} JSON decode error. Response text: {response_text}")
                    raise Exception(f"Invalid JSON response from OpenAI API: {str(json_err)}")
                except (KeyError, IndexError, ValueError) as struct_err:
                    self.logger.error(f"Batch {batch_id} API response structure error: {str(struct_err)}")
                    raise Exception(f"Invalid API response structure: {str(struct_err)}")
                
                # 解析翻译结果
                if is_single:
                    translations = [content]
                else:
                    try:
                        # 尝试解析JSON响应
                        translated_data = json.loads(content)
                        if isinstance(translated_data, list):
                            translations = [item.get('text', '') for item in translated_data]
                        else:
                            raise ValueError("Expected JSON array response")
                    except (json.JSONDecodeError, ValueError):
                        # 如果JSON解析失败，回退到%%分隔符
                        if "\n%%\n" in content:
                            translations = content.split("\n%%\n")
                        elif "%%" in content:
                            translations = content.split("%%")
                        else:
                            translations = [line.strip() for line in content.split('\n') if line.strip()]
                
                # 构建结果
                batch_results = []
                for j, entry in enumerate(batch_entries):
                    if j < len(translations) and translations[j].strip():
                        batch_results.append({
                            'id': entry['id'],
                            'timestamp': entry['timestamp'],
                            'text': f"{entry['text']}\n{translations[j].strip()}"
                        })
                    else:
                        self.logger.warning(f"Translation missing for entry {entry['id']} in batch {batch_id}")
                        batch_results.append({
                            'id': entry['id'],
                            'timestamp': entry['timestamp'],
                            'text': entry['text']
                        })
                
                return batch_results
                        
            else:
                raise requests.exceptions.RequestException(f"OpenAI API error: {response.status_code}")
                
        except Exception as e:
            self.logger.warning(f"Batch {batch_id} translation failed: {str(e)}")
            return None

    def _translate_individually(self, entries, translation_lock, total_entries):
        """使用多线程进行单独翻译"""
        translated_entries = []
        completed_count = 0
        
        # 使用系统优化的线程配置
        optimal_workers = (self.optimized_config['openai_workers'] 
                         if self.engine == "OpenAI Translate" 
                         else self.optimized_config['google_workers'])
        
        self.logger.info(f"Using {optimal_workers} threads for {self.engine} translation")
        
        with ThreadPoolExecutor(max_workers=optimal_workers) as executor:
            # 创建任务
            future_to_entry = {
                executor.submit(self._translate_entry, entry): entry
                for entry in entries
            }

            # 收集翻译结果 - 使用线程安全的方式
            for future in as_completed(future_to_entry):
                entry = future_to_entry[future]
                try:
                    translated_text = future.result()
                    if translated_text:  # 确保有翻译结果
                        with translation_lock:  # 线程安全的添加
                            translated_entries.append({
                                'id': entry['id'],
                                'timestamp': entry['timestamp'],
                                'text': f"{entry['text']}\n{translated_text}"
                            })
                            completed_count += 1
                            
                            # 更新进度 - 基于实际完成数量
                            progress = 40 + completed_count / total_entries * 30
                            self.signals.file_progress.emit(self.base_name, int(progress))
                    else:
                        self.logger.warning(f"Empty translation for subtitle ID {entry['id']}")
                except Exception as e:
                    error_msg = f"Subtitle {entry['id']} translation failed: {str(e)}"
                    self.logger.error(error_msg)
                    # 只记录错误，不发送信号避免UI混乱
                    with translation_lock:
                        completed_count += 1
                        progress = 40 + completed_count / total_entries * 30
                        self.signals.file_progress.emit(self.base_name, int(progress))
                    continue
                    
        return translated_entries

    def _load_translation_cache(self):
        """加载持久化翻译缓存"""
        try:
            if os.path.exists(self._cache_file):
                with open(self._cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    # 只加载最近的缓存条目（避免缓存过大）
                    if len(cached_data) > 1000:
                        # 保留最新的1000个条目
                        sorted_items = sorted(cached_data.items(), key=lambda x: x[1].get('timestamp', 0), reverse=True)
                        self._translation_cache = dict(sorted_items[:1000])
                    else:
                        self._translation_cache = cached_data
                    self.logger.info(f"Loaded {len(self._translation_cache)} cached translations")
        except Exception as e:
            self.logger.warning(f"Failed to load translation cache: {e}")
            self._translation_cache = {}

    def _save_translation_cache(self):
        """保存翻译缓存到文件"""
        try:
            # 添加时间戳到缓存条目
            current_time = time.time()
            for key in self._translation_cache:
                if isinstance(self._translation_cache[key], str):
                    # 转换旧格式到新格式
                    self._translation_cache[key] = {
                        'translation': self._translation_cache[key],
                        'timestamp': current_time
                    }
                elif 'timestamp' not in self._translation_cache[key]:
                    self._translation_cache[key]['timestamp'] = current_time
            
            with open(self._cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._translation_cache, f, ensure_ascii=False, indent=2)
            self.logger.info(f"Saved {len(self._translation_cache)} translations to cache")
        except Exception as e:
            self.logger.warning(f"Failed to save translation cache: {e}")

    def _get_cached_translation(self, text, engine):
        """获取缓存的翻译"""
        cache_key = f"{engine}_{hash(text)}"
        if cache_key in self._translation_cache:
            cached_item = self._translation_cache[cache_key]
            if isinstance(cached_item, dict):
                return cached_item.get('translation')
            else:
                return cached_item  # 向后兼容旧格式
        return None

    def _set_cached_translation(self, text, engine, translation):
        """设置翻译缓存"""
        cache_key = f"{engine}_{hash(text)}"
        self._translation_cache[cache_key] = {
            'translation': translation,
            'timestamp': time.time()
        }


