import time
import requests
import requests.adapters
from PyQt6.QtCore import QRunnable
import os
import subprocess
import sys
from datetime import datetime
from deep_translator import GoogleTranslator
from core.worker_signals import WorkerSignals
from core.speech_recognizer import SpeechRecognizer, SubtitleFormatter
from utils.logger import VideoLogger
import threading
import json
import platform
import multiprocessing as mp
import queue
from typing import Dict, Any, Optional, List
from config import OPENAI_MODEL, OPENAI_CUSTOM_PROMPT, OPENAI_MAX_CHARS_PER_BATCH, OPENAI_MAX_ENTRIES_PER_BATCH, MAX_PROCESSES


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
        
        # 语音识别器 - 使用单例模式的 Parakeet MLX
        # 注意：不在这里初始化，而是在需要时获取单例实例
    
        # 跟踪处理状态以确保正确清理
        self._processing_complete = False
        
        # 计时器相关变量
        self._start_time = None
        self._timer_thread = None
        self._timer_stop_event = threading.Event()
        
        # 简化的系统检测
        self.use_hardware_accel = self._check_hardware_acceleration()
        self.is_apple_silicon = self._is_apple_silicon()
        
        # 记录系统信息
        self.logger.info(f"Video processor - Platform: {platform.system()}")
        if self.is_apple_silicon:
            self.logger.info("Apple Silicon detected - using optimized video processing")
        
        if self.use_hardware_accel:
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

    def _is_apple_silicon(self) -> bool:
        """检测是否是Apple Silicon"""
        if platform.system() != 'Darwin':
            return False
        try:
            result = subprocess.run(['sysctl', '-n', 'hw.optional.arm64'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0 and result.stdout.strip() == '1'
        except Exception:
            return False

    def _check_hardware_acceleration(self) -> bool:
        """检查VideoToolbox硬件加速支持"""
        if platform.system() != 'Darwin':
            return False
        try:
            ffmpeg_path = self.get_ffmpeg_path()
            if not ffmpeg_path:
                return False
            result = subprocess.run([ffmpeg_path, '-version'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0 and 'videotoolbox' in result.stdout.lower()
        except Exception:
            return False

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

            # Produce Audio (0-10%)
            self.report_status("Extracting audio...")
            self.report_progress(0)
            self.extract_audio(cache_paths['audio'])
            self.logger.info("Audio extraction completed")
            self.report_progress(10)

            # Generate Subtitle (10-70%)
            self.report_status("Recognizing speech...")
            self.generate_subtitles(cache_paths['audio'], cache_paths['srt'])
            self.logger.info("Subtitle generation complete")
            self.report_progress(70)

            # Translate Subtitle (70-80%)
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
            self.report_progress(80)

            # Composite Video (80-100%)
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
                if hasattr(self, 'session'):
                    self.session.close()
                    
                # 注意：不再需要释放语音识别器内存，因为使用单例模式
                # MLX 模型会在应用程序退出时自动清理
                    
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
        """
        获取 ffmpeg 路径
        - 打包环境：使用内置的 ffmpeg
        - 开发环境：使用系统安装的 ffmpeg
        """
        # 检测是否在 PyInstaller 打包环境中
        if getattr(sys, 'frozen', False):
            if platform.system() == 'Darwin':  # macOS
                # 在 macOS .app 包中，检查 Contents/Frameworks 目录
                if '.app/Contents/MacOS' in sys.executable:
                    app_frameworks = os.path.join(os.path.dirname(sys.executable), '..', 'Frameworks')
                    ffmpeg_path = os.path.join(os.path.abspath(app_frameworks), 'ffmpeg')
                    if os.path.exists(ffmpeg_path):
                        return ffmpeg_path
                
                # 也检查可执行文件同目录
                bundle_dir = os.path.dirname(sys.executable)
                ffmpeg_path = os.path.join(bundle_dir, 'ffmpeg')
                if os.path.exists(ffmpeg_path):
                    return ffmpeg_path
            else:
                # 其他平台的 PyInstaller 环境
                bundle_dir = os.path.dirname(sys.executable)
                ffmpeg_path = os.path.join(bundle_dir, 'ffmpeg')
                if os.path.exists(ffmpeg_path):
                    return ffmpeg_path
        
        # 开发环境 - 使用系统安装的 ffmpeg
        possible_paths = [
            '/opt/homebrew/bin/ffmpeg',  # MacOS Homebrew
            '/usr/local/bin/ffmpeg',     # Linux/MacOS Path
            '/usr/bin/ffmpeg',           # Others
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
                
        # 如果都找不到，返回 None
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
            error_msg = "Could not find ffmpeg."
            if getattr(sys, 'frozen', False):
                error_msg += " Application may not be properly installed or ffmpeg not bundled correctly."
                error_msg += f" Searched in: {sys.executable} directory"
            else:
                error_msg += " Please install it first (e.g., brew install ffmpeg)."
            self.logger.error(error_msg)
            raise FileNotFoundError(error_msg)
            
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
            if self.use_hardware_accel:
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
        """使用 Parakeet MLX 生成字幕 - 使用单例模式"""
        # 获取单例语音识别器
        try:
            self.logger.info("Getting Parakeet MLX speech recognizer instance...")
            self.report_progress(12)  # 10% + 2% for initialization
            
            # 获取单例实例，只有第一次调用时会触发下载回调
            speech_recognizer = SpeechRecognizer(
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
            self.logger.info("Parakeet MLX model instance obtained successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to get Parakeet MLX model instance: {str(e)}")
            self.signals.download_error.emit(f"Failed to get Parakeet MLX model instance: {str(e)}")
            raise RuntimeError(f"Failed to get Parakeet MLX model instance: {str(e)}")
        
        self.report_progress(20)  # 模型实例获取完成，占用10%->20%的进度
        
        # 使用 Parakeet MLX 进行转录
        try:
            self.logger.info(f"Starting transcription of: {audio_path}")
            
            # 检查音频文件大小，如果太小（如静音文件），直接创建空字幕
            if os.path.getsize(audio_path) < 1000:  # 小于1KB，可能是静音文件
                self.logger.info("Audio file is very small, likely silent - creating empty subtitle file")
                with open(srt_path, "w", encoding="utf-8") as f:
                    f.write("")  # 创建空字幕文件
                return
            
            # 定义进度回调函数 - 语音识别占用20%-70%的进度空间（50%的进度空间）
            def progress_callback(current_chunk, total_chunks):
                if total_chunks > 0:
                    # 语音识别进度：20% + (current_chunk/total_chunks) * 50%
                    recognition_progress = (current_chunk / total_chunks) * 50
                    progress = 20 + recognition_progress
                    self.report_progress(min(70, int(progress)))
            
            # 进行转录 - 现在是线程安全的
            result = speech_recognizer.transcribe(
                audio_path,
                chunk_duration=120.0,  # 2分钟分块
                overlap_duration=15.0,  # 15秒重叠
                progress_callback=progress_callback
            )
            
            self.report_progress(70)  # 转录完成，确保达到70%
            
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
                            'text': '\n'.join(current_text)
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
                    'text': '\n'.join(current_text)
                })

            total_entries = len(entries)
            if total_entries == 0:
                self.logger.warning("No valid subtitle entries found to translate")
                return ""
                
            self.logger.info(f"Starting batch translation of {total_entries} subtitle entries")
            
            # 批量翻译所有字幕 (70% -> 80%)
            self.report_progress(72)
            translated_entries = self._batch_translate_all(entries)
            self.report_progress(80)

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

    def _batch_translate_all(self, entries):
        """批量翻译所有字幕条目"""
        if self.engine == "OpenAI Translate":
            return self._batch_translate_with_openai(entries)
        else:  # Google Translation
            return self._batch_translate_with_google(entries)
    
    """
    外部调用
    ↓
    _batch_translate_with_openai (调度器)
    ↓
    ├─ 内容少 → _translate_openai_batch (单次处理)
    └─ 内容多 → _translate_openai_multiple_batches (分批管理)
                    ↓
                    循环调用 → _translate_openai_batch (具体执行)
    """

    def _batch_translate_with_openai(self, entries):
        """使用OpenAI API批量翻译所有字幕 - 使用段落分隔符方案"""
        try:
            # 从配置文件获取批处理参数
            max_chars_per_batch = self.api_settings.get("max_chars_per_batch", OPENAI_MAX_CHARS_PER_BATCH)
            max_entries_per_batch = self.api_settings.get("max_entries_per_batch", OPENAI_MAX_ENTRIES_PER_BATCH)
            
            total_chars = sum(len(entry['text']) for entry in entries)
            
            if total_chars <= max_chars_per_batch and len(entries) <= max_entries_per_batch:
                # 内容较少，使用单一批量请求
                self.logger.info(f"Content size {total_chars} chars, {len(entries)} entries - using single batch request")
                return self._translate_openai_batch(entries)
            else:
                # 内容过多，需要分批处理
                self.logger.info(f"Content size {total_chars} chars, {len(entries)} entries - using multiple batch processing")
                return self._translate_openai_multiple_batches(entries, max_chars_per_batch, max_entries_per_batch)
                
        except Exception as e:
            self.logger.error(f"OpenAI batch translation failed: {str(e)}")
            raise
    
    def _translate_openai_batch(self, entries):
        """OpenAI单批次翻译 - 使用段落分隔符方案"""
        # 构建翻译文本 - 使用 %% 分隔符
        if len(entries) == 1:
            # 单段落，直接翻译
            text_to_translate = entries[0]['text']
        else:
            # 多段落，使用 %% 分隔
            texts = [entry['text'] for entry in entries]
            text_to_translate = '\n%%\n'.join(texts)
        
        # 使用配置文件中的自定义prompt
        system_prompt = OPENAI_CUSTOM_PROMPT

        user_prompt = f"Translate to Chinese (output translation only):\n\n{text_to_translate}"
        
        data = {
            "model": self.api_settings.get("model", OPENAI_MODEL),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0,
            "max_tokens": 8000  # 适中的token限制
        }

        response = self.session.post(
            f"{self.api_settings['base_url']}/v1/chat/completions",
            json=data,
            timeout=300
        )
        
        if response.status_code == 200:
            result = response.json()
            if 'choices' not in result or not result['choices']:
                raise ValueError(f"Invalid API response structure: {result}")
            
            choice = result['choices'][0]
            
            if choice.get('finish_reason') == 'content_filter':
                raise ContentFilteredException("Batch translation content filtered by OpenAI safety system")
            
            if 'message' not in choice or 'content' not in choice['message']:
                raise ValueError(f"Invalid message structure in API response: {result}")
            
            translated_content = choice['message']['content'].strip()
            
            # 解析翻译结果
            if len(entries) == 1:
                # 单段落
                translated_texts = [translated_content]
            else:
                # 多段落，按 %% 分割
                if '\n%%\n' in translated_content:
                    translated_texts = translated_content.split('\n%%\n')
                elif '%%' in translated_content:
                    translated_texts = translated_content.split('%%')
                else:
                    # 如果没有找到分隔符，可能是单个翻译结果，按行数分割
                    lines = translated_content.split('\n')
                    if len(lines) >= len(entries):
                        translated_texts = lines[:len(entries)]
                    else:
                        translated_texts = [translated_content]  # 使用整个翻译作为第一个结果
            
            # 确保翻译结果数量匹配
            while len(translated_texts) < len(entries):
                translated_texts.append(entries[len(translated_texts)]['text'])  # 使用原文填充
            translated_texts = translated_texts[:len(entries)]  # 截断多余的结果
            
            # 构建最终结果
            translated_entries = []
            for i, entry in enumerate(entries):
                translated_text = translated_texts[i].strip() if i < len(translated_texts) else entry['text']
                if not translated_text:
                    translated_text = entry['text']  # 如果翻译为空，使用原文
                
                translated_entries.append({
                    'id': entry['id'],
                    'timestamp': entry['timestamp'],
                    'text': f"{entry['text']}\n{translated_text}"
                })
            
            self.logger.info(f"Successfully translated {len(translated_entries)} entries via OpenAI paragraph batch")
            return translated_entries
                
        else:
            raise requests.exceptions.RequestException(f"OpenAI API error: {response.status_code} - {response.text}")
    
    def _translate_openai_multiple_batches(self, entries, max_chars=None, max_entries=None):
        """OpenAI多批次翻译 - 使用段落分隔符方案"""
        # 使用传入的参数或默认配置值
        if max_chars is None:
            max_chars = OPENAI_MAX_CHARS_PER_BATCH
        if max_entries is None:
            max_entries = OPENAI_MAX_ENTRIES_PER_BATCH
            
        all_translated = []
        batches = []
        current_batch = []
        current_chars = 0
        
        # 构建批次
        for entry in entries:
            entry_length = len(entry['text'])
            
            # 检查是否需要新批次
            if (len(current_batch) >= max_entries or 
                current_chars + entry_length > max_chars) and current_batch:
                batches.append(current_batch)
                current_batch = []
                current_chars = 0
            
            current_batch.append(entry)
            current_chars += entry_length
        
        # 添加最后一个批次
        if current_batch:
            batches.append(current_batch)
        
        self.logger.info(f"Split into {len(batches)} batches for OpenAI paragraph translation")
        
        # 逐批次翻译
        for i, batch in enumerate(batches):
            try:
                self.logger.info(f"Translating batch {i+1}/{len(batches)} with {len(batch)} entries")
                
                # 使用单批次翻译函数
                translated_batch = self._translate_openai_batch(batch)
                all_translated.extend(translated_batch)
                
                # 发出进度信号 - 使用正确的进度报告方法
                progress = 72 + int((i + 1) / len(batches) * 8)
                self.report_progress(min(80, progress))
                
                # 批次间适当延迟，避免API限制
                if i < len(batches) - 1:
                    time.sleep(0.1)
                    
            except Exception as e:
                self.logger.error(f"Failed to translate batch {i+1}: {str(e)}")
                # 如果批次翻译失败，保留原文
                failed_batch = []
                for entry in batch:
                    failed_batch.append({
                        'id': entry['id'],
                        'timestamp': entry['timestamp'],
                        'text': entry['text']  # 保持原文
                    })
                all_translated.extend(failed_batch)
        
        self.logger.info(f"Completed OpenAI paragraph translation: {len(all_translated)} entries")
        return all_translated
    
    def _batch_translate_with_google(self, entries):
        """使用Google Translate批量翻译所有字幕，支持分批处理大文本"""
        try:
            separator = "\n---SUBTITLE_SEPARATOR---\n"
            max_chars = 4500  # 留一些余量，避免超过5000字符限制
            translated_entries = []
            
            # 分批处理字幕条目
            current_batch = []
            current_length = 0
            batch_count = 0
            
            # 先计算总批次数以便显示进度
            total_batches = 1
            temp_length = 0
            for entry in entries:
                entry_length = len(entry['text']) + len(separator)
                if temp_length + entry_length > max_chars and temp_length > 0:
                    total_batches += 1
                    temp_length = entry_length
                else:
                    temp_length += entry_length
            
            for entry in entries:
                entry_text = entry['text']
                entry_length = len(entry_text) + len(separator)
                
                # 如果添加当前条目会超过限制，先处理当前批次
                if current_length + entry_length > max_chars and current_batch:
                    batch_count += 1
                    self.logger.info(f"Processing Google Translate batch {batch_count}/{total_batches} ({len(current_batch)} entries, {current_length} chars)")
                    
                    # 更新进度 (72% -> 80% 的范围内)
                    progress = 72 + int((batch_count / total_batches) * 8)
                    self.report_progress(min(80, progress))
                    
                    batch_results = self._translate_google_batch(current_batch, separator)
                    translated_entries.extend(batch_results)
                    
                    # 重置批次
                    current_batch = []
                    current_length = 0
                
                current_batch.append(entry)
                current_length += entry_length
            
            # 处理最后一批
            if current_batch:
                batch_count += 1
                self.logger.info(f"Processing final Google Translate batch {batch_count}/{total_batches} ({len(current_batch)} entries, {current_length} chars)")
                batch_results = self._translate_google_batch(current_batch, separator)
                translated_entries.extend(batch_results)
            
            self.logger.info(f"Successfully translated {len(translated_entries)} entries via Google Translate in {batch_count} batches")
            return translated_entries
            
        except Exception as e:
            self.logger.error(f"Google Translate batch translation failed: {str(e)}")
            raise
    
    def _translate_google_batch(self, entries, separator):
        """翻译一个批次的字幕条目"""
        # 提取所有需要翻译的文本
        texts_to_translate = [entry['text'] for entry in entries]
        
        # 使用分隔符将所有文本合并成一个大字符串
        combined_text = separator.join(texts_to_translate)
        
        # 使用Deep Translator进行批量翻译
        translator = GoogleTranslator(source='auto', target='zh-CN')
        translated_combined = translator.translate(combined_text)
        
        if not translated_combined:
            raise ValueError("Empty response from Google Translate")
        
        # 分割翻译结果
        translated_texts = translated_combined.split(separator)
        
        # 确保翻译结果数量匹配
        if len(translated_texts) != len(entries):
            self.logger.warning(f"Translation count mismatch: expected {len(entries)}, got {len(translated_texts)}")
            # 填充缺失的翻译
            while len(translated_texts) < len(entries):
                translated_texts.append("")
            translated_texts = translated_texts[:len(entries)]
        
        # 构建翻译结果
        batch_results = []
        for i, entry in enumerate(entries):
            translated_text = translated_texts[i].strip() if i < len(translated_texts) else ""
            if not translated_text:
                translated_text = entry['text']  # 如果翻译失败，使用原文
            
            batch_results.append({
                'id': entry['id'],
                'timestamp': entry['timestamp'],
                'text': f"{entry['text']}\n{translated_text}"
            })
        
        return batch_results

    def burn_subtitles(self, subtitle_path, output_path):
        ffmpeg_path = self.get_ffmpeg_path()
        if not ffmpeg_path:
            error_msg = "Could not find ffmpeg."
            if getattr(sys, 'frozen', False):
                error_msg += " Application may not be properly installed or ffmpeg not bundled correctly."
                error_msg += f" Searched in: {sys.executable} directory and Contents/MacOS"
            else:
                error_msg += " Please install it first (e.g., brew install ffmpeg)."
            self.logger.error(error_msg)
            raise FileNotFoundError(error_msg)
            
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
            # 优化的硬件加速字幕烧录命令，更激进的压缩
            cmd = [
                ffmpeg_path,
                "-hwaccel", "videotoolbox",
                "-i", self.video_path,
                "-vf", f"subtitles='{subtitle_path}':force_style='FontSize=16,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,BorderStyle=4'",
                "-c:v", "h264_videotoolbox",
                "-b:v", "0",  # 使用变动比特率模式
                "-q:v", "52", # VideoToolbox质量参数调整为55，更激进的压缩
                "-c:a", "copy",
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
            
            # 监控进度 (80% -> 100%)
            progress_start = 80
            progress_range = 20
            
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


# ===== 多进程支持函数 =====

def process_video_worker(
    video_path: str,
    engine: str,
    api_settings: Dict[str, Any],
    cache_dir: str,
    progress_queue: mp.Queue,
    result_queue: mp.Queue,
    process_id: int
):
    """
    多进程视频处理工作函数
    
    Args:
        video_path: 视频文件路径
        engine: 翻译引擎
        api_settings: API设置
        cache_dir: 缓存目录
        progress_queue: 进度报告队列
        result_queue: 结果队列
        process_id: 进程ID
    """
    try:
        # 创建处理器实例（不继承QRunnable，直接使用核心功能）
        processor = VideoProcessorForMultiprocess(
            video_path=video_path,
            engine=engine,
            api_settings=api_settings,
            cache_dir=cache_dir,
            progress_queue=progress_queue,
            process_id=process_id
        )
        
        # 执行处理
        result = processor.process()
        
        # 发送成功结果
        result_queue.put({
            'process_id': process_id,
            'video_path': video_path,
            'status': 'success',
            'result': result
        })
        
    except Exception as e:
        # 发送错误结果
        result_queue.put({
            'process_id': process_id,
            'video_path': video_path,
            'status': 'error',
            'error': str(e)
        })


class VideoProcessorForMultiprocess:
    """简化的视频处理器，专门用于多进程环境"""
    
    def __init__(self, video_path: str, engine: str, api_settings: Dict[str, Any], 
                 cache_dir: str, progress_queue: mp.Queue, process_id: int):
        self.video_path = video_path
        self.engine = engine
        self.api_settings = api_settings
        self.cache_dir = cache_dir
        self.progress_queue = progress_queue
        self.process_id = process_id
        self.base_name = os.path.basename(video_path)
        
        # 创建日志器实例
        self.logger = VideoLogger(cache_dir)
        
        # 创建独立的requests会话
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.api_settings.get('api_key', '')}",
            "Content-Type": "application/json"
        })
        
        # 配置连接池
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=5,
            pool_maxsize=10,
            max_retries=3,
            pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        # 继承原有的系统检测逻辑
        self.use_hardware_accel = VideoProcessor._check_hardware_acceleration(self)
        self.is_apple_silicon = VideoProcessor._is_apple_silicon(self)
        
        # 开始时间
        self.start_time = time.time()
    
    def report_progress(self, progress: int):
        """报告进度"""
        try:
            elapsed = time.time() - self.start_time
            elapsed_str = self._format_elapsed_time(elapsed)
            
            self.progress_queue.put({
                'type': 'progress',
                'process_id': self.process_id,
                'video_path': self.video_path,
                'base_name': self.base_name,
                'progress': progress,
                'elapsed_time': elapsed_str
            }, block=False)
        except queue.Full:
            pass  # 忽略队列满的情况，避免阻塞
    
    def report_status(self, status: str):
        """报告状态"""
        try:
            self.progress_queue.put({
                'type': 'status',
                'process_id': self.process_id,
                'video_path': self.video_path,
                'base_name': self.base_name,
                'status': status
            }, block=False)
        except queue.Full:
            pass
    
    def _format_elapsed_time(self, elapsed_seconds: float) -> str:
        """格式化经过的时间为 MM:SS 格式"""
        minutes = int(elapsed_seconds // 60)
        seconds = int(elapsed_seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"
    
    def process(self) -> Dict[str, Any]:
        """主处理流程 - 复用原有VideoProcessor的方法"""
        try:
            print(f"🎬 Process {self.process_id}: Starting to process {self.base_name}")
            
            # 使用原有的get_cache_paths逻辑
            cache_paths = self.get_cache_paths()
            
            # 音频提取 (0-10%)
            self.report_status("Extracting audio...")
            self.report_progress(0)
            self.extract_audio(cache_paths['audio'])
            self.report_progress(10)
            
            # 语音识别 (10-70%)
            self.report_status("Recognizing speech...")
            self.generate_subtitles(cache_paths['audio'], cache_paths['srt'])
            self.report_progress(70)
            
            # 字幕翻译 (70-80%)
            self.report_status("Translating subtitles...")
            with open(cache_paths['srt'], "r", encoding="utf-8") as f:
                lines = f.readlines()
            translated_content = self.translate_subtitles(lines)
            
            if not translated_content or translated_content.strip() == "":
                self.report_status("Empty bilingual subtitles, skipping video synthesis")
                self.report_progress(100)
                return {'status': 'skipped', 'reason': 'empty_subtitles'}
            
            with open(cache_paths['bilingual_srt'], "w", encoding="utf-8") as f:
                f.write(translated_content)
            self.report_progress(80)
            
            # 视频合成 (80-100%)
            self.report_status("Synthesizing video...")
            self.burn_subtitles(cache_paths['bilingual_srt'], cache_paths['output_video'])
            self.report_progress(100)
            self.report_status("Processing completed!")
            
            return {
                'status': 'completed',
                'output_path': cache_paths['output_video'],
                'cache_paths': cache_paths
            }
            
        except Exception as e:
            error_msg = f"Processing failed: {str(e)}"
            self.report_status(error_msg)
            raise RuntimeError(error_msg)
        finally:
            # 清理资源
            try:
                if hasattr(self, 'session'):
                    self.session.close()
                    
                # 清理日志处理器
                if hasattr(self, 'logger'):
                    self.logger.cleanup()
            except Exception:
                pass
    
    # 以下方法直接复用VideoProcessor的方法，避免重复代码
    def get_cache_paths(self):
        return VideoProcessor.get_cache_paths(self)
    
    def get_ffmpeg_path(self):
        return VideoProcessor.get_ffmpeg_path()
    
    def check_has_audio(self):
        return VideoProcessor.check_has_audio(self)
    
    def extract_audio(self, audio_path):
        return VideoProcessor.extract_audio(self, audio_path)
    
    def generate_subtitles(self, audio_path, srt_path):
        """生成字幕 - 在子进程中创建独立的语音识别器"""
        try:
            # 在子进程中导入和初始化语音识别器
            from core.speech_recognizer import SpeechRecognizer, SubtitleFormatter
            
            print(f"🎙️ Process {self.process_id}: Initializing speech recognizer...")
            
            # 创建进程专用的语音识别器
            speech_recognizer = SpeechRecognizer(
                model_name="mlx-community/parakeet-tdt-0.6b-v2",
                fp32=False,
                local_attention=True,
                local_attention_context_size=256
            )
            
            self.report_progress(20)
            
            # 检查音频文件大小
            if os.path.getsize(audio_path) < 1000:
                print(f"🎙️ Process {self.process_id}: Audio file is very small, creating empty subtitle")
                with open(srt_path, "w", encoding="utf-8") as f:
                    f.write("")
                return
            
            # 进度回调函数
            def progress_callback(current_chunk, total_chunks):
                if total_chunks > 0:
                    recognition_progress = (current_chunk / total_chunks) * 50
                    progress = 20 + recognition_progress
                    self.report_progress(min(70, int(progress)))
            
            # 转录
            result = speech_recognizer.transcribe(
                audio_path,
                chunk_duration=120.0,
                overlap_duration=15.0,
                progress_callback=progress_callback
            )
            
            self.report_progress(70)
            
            # 生成SRT格式
            srt_content = SubtitleFormatter.to_srt(result, highlight_words=False)
            
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt_content)
            
            segment_count = len(result.sentences)
            print(f"🎙️ Process {self.process_id}: Transcription completed, {segment_count} segments")
            
        except Exception as e:
            print(f"🎙️ Process {self.process_id}: Transcription failed: {str(e)}")
            raise RuntimeError(f"Transcription failed: {str(e)}")
    
    def translate_subtitles(self, lines):
        """翻译字幕 - 多进程版本，不使用signals"""
        try:
            # 检查是否为空字幕文件
            if not lines or all(not line.strip() for line in lines):
                print(f"🎙️ Process {self.process_id}: Empty subtitle file detected, skipping translation")
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
                            'text': '\n'.join(current_text)
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
                    'text': '\n'.join(current_text)
                })

            total_entries = len(entries)
            if total_entries == 0:
                print(f"⚠️ Process {self.process_id}: No valid subtitle entries found to translate")
                return ""
                
            print(f"🎙️ Process {self.process_id}: Starting batch translation of {total_entries} subtitle entries")
            
            # 批量翻译所有字幕 (70% -> 80%)
            self.report_progress(72)
            
            # 使用自己的翻译方法而不是父类的
            if self.engine == "OpenAI Translate":
                translated_entries = self._batch_translate_with_openai_multiprocess(entries)
            else:  # Google Translation
                translated_entries = self._batch_translate_with_google_multiprocess(entries)
            
            self.report_progress(80)

            # Sort by ID to Ensure Correct Subtitle Ordering
            translated_entries.sort(key=lambda x: x['id'])

            # Construct Final Subtitle Content
            translated_content = ""
            for entry in translated_entries:
                translated_content += f"{entry['id']}\n{entry['timestamp']}\n{entry['text']}\n\n"

            return translated_content

        except Exception as e:
            error_msg = f"Translation Process Failed: {str(e)}"
            print(f"❌ Process {self.process_id}: {error_msg}")
            raise RuntimeError(error_msg)
    
    def _batch_translate_with_openai_multiprocess(self, entries):
        """多进程版本的OpenAI翻译"""
        try:
            from config import OPENAI_MODEL, OPENAI_CUSTOM_PROMPT, OPENAI_MAX_CHARS_PER_BATCH, OPENAI_MAX_ENTRIES_PER_BATCH
        except ImportError:
            # 如果导入失败，使用默认值
            OPENAI_MAX_CHARS_PER_BATCH = 8000
            OPENAI_MAX_ENTRIES_PER_BATCH = 50
            OPENAI_MODEL = "gpt-3.5-turbo"
            OPENAI_CUSTOM_PROMPT = "You are a professional translator. Translate the following text to Chinese, maintaining the original meaning and tone."
        
        try:
            # 从配置文件获取批处理参数
            max_chars_per_batch = self.api_settings.get("max_chars_per_batch", OPENAI_MAX_CHARS_PER_BATCH)
            max_entries_per_batch = self.api_settings.get("max_entries_per_batch", OPENAI_MAX_ENTRIES_PER_BATCH)
            
            total_chars = sum(len(entry['text']) for entry in entries)
            
            if total_chars <= max_chars_per_batch and len(entries) <= max_entries_per_batch:
                # 内容较少，使用单一批量请求
                print(f"🎙️ Process {self.process_id}: Content size {total_chars} chars, {len(entries)} entries - using single batch request")
                return self._translate_openai_batch_multiprocess(entries)
            else:
                # 内容过多，需要分批处理
                print(f"🎙️ Process {self.process_id}: Content size {total_chars} chars, {len(entries)} entries - using multiple batch processing")
                return self._translate_openai_multiple_batches_multiprocess(entries, max_chars_per_batch, max_entries_per_batch)
                
        except Exception as e:
            print(f"❌ Process {self.process_id}: OpenAI batch translation failed: {str(e)}")
            raise
    
    def _translate_openai_batch_multiprocess(self, entries):
        """多进程版本的OpenAI单批次翻译"""
        try:
            from config import OPENAI_MODEL, OPENAI_CUSTOM_PROMPT
        except ImportError:
            OPENAI_MODEL = "gpt-3.5-turbo"
            OPENAI_CUSTOM_PROMPT = "You are a professional translator. Translate the following text to Chinese, maintaining the original meaning and tone."
        
        # 构建翻译文本 - 使用 %% 分隔符
        if len(entries) == 1:
            # 单段落，直接翻译
            text_to_translate = entries[0]['text']
        else:
            # 多段落，使用 %% 分隔
            texts = [entry['text'] for entry in entries]
            text_to_translate = '\n%%\n'.join(texts)
        
        # 使用配置文件中的自定义prompt
        system_prompt = OPENAI_CUSTOM_PROMPT
        user_prompt = f"Translate to Chinese (output translation only):\n\n{text_to_translate}"
        
        data = {
            "model": self.api_settings.get("model", OPENAI_MODEL),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0,
            "max_tokens": 8000  # 适中的token限制
        }

        response = self.session.post(
            f"{self.api_settings['base_url']}/v1/chat/completions",
            json=data,
            timeout=300
        )
        
        if response.status_code == 200:
            result = response.json()
            if 'choices' not in result or not result['choices']:
                raise ValueError(f"Invalid API response structure: {result}")
            
            choice = result['choices'][0]
            
            if choice.get('finish_reason') == 'content_filter':
                raise Exception("Batch translation content filtered by OpenAI safety system")
            
            if 'message' not in choice or 'content' not in choice['message']:
                raise ValueError(f"Invalid message structure in API response: {result}")
            
            translated_content = choice['message']['content'].strip()
            
            # 解析翻译结果
            if len(entries) == 1:
                # 单段落
                translated_texts = [translated_content]
            else:
                # 多段落，按 %% 分割
                if '\n%%\n' in translated_content:
                    translated_texts = translated_content.split('\n%%\n')
                elif '%%' in translated_content:
                    translated_texts = translated_content.split('%%')
                else:
                    # 如果没有找到分隔符，可能是单个翻译结果，按行数分割
                    lines = translated_content.split('\n')
                    if len(lines) >= len(entries):
                        translated_texts = lines[:len(entries)]
                    else:
                        translated_texts = [translated_content]  # 使用整个翻译作为第一个结果
            
            # 确保翻译结果数量匹配
            while len(translated_texts) < len(entries):
                translated_texts.append(entries[len(translated_texts)]['text'])  # 使用原文填充
            translated_texts = translated_texts[:len(entries)]  # 截断多余的结果
            
            # 构建最终结果
            translated_entries = []
            for i, entry in enumerate(entries):
                translated_text = translated_texts[i].strip() if i < len(translated_texts) else entry['text']
                if not translated_text:
                    translated_text = entry['text']  # 如果翻译为空，使用原文
                
                translated_entries.append({
                    'id': entry['id'],
                    'timestamp': entry['timestamp'],
                    'text': f"{entry['text']}\n{translated_text}"
                })
            
            print(f"🎙️ Process {self.process_id}: Successfully translated {len(translated_entries)} entries via OpenAI")
            return translated_entries
                
        else:
            raise Exception(f"OpenAI API error: {response.status_code} - {response.text}")
    
    def _translate_openai_multiple_batches_multiprocess(self, entries, max_chars, max_entries):
        """多进程版本的OpenAI多批次翻译"""
        all_translated = []
        batches = []
        current_batch = []
        current_chars = 0
        
        # 构建批次
        for entry in entries:
            entry_length = len(entry['text'])
            
            # 检查是否需要新批次
            if (len(current_batch) >= max_entries or 
                current_chars + entry_length > max_chars) and current_batch:
                batches.append(current_batch)
                current_batch = []
                current_chars = 0
            
            current_batch.append(entry)
            current_chars += entry_length
        
        # 添加最后一个批次
        if current_batch:
            batches.append(current_batch)
        
        print(f"🎙️ Process {self.process_id}: Split into {len(batches)} batches for OpenAI translation")
        
        # 逐批次翻译
        for i, batch in enumerate(batches):
            try:
                print(f"🎙️ Process {self.process_id}: Translating batch {i+1}/{len(batches)} with {len(batch)} entries")
                
                # 使用单批次翻译函数
                translated_batch = self._translate_openai_batch_multiprocess(batch)
                all_translated.extend(translated_batch)
                
                # 发出进度信号
                progress = 72 + int((i + 1) / len(batches) * 8)
                self.report_progress(min(80, progress))
                
                # 批次间适当延迟，避免API限制
                if i < len(batches) - 1:
                    time.sleep(0.1)
                    
            except Exception as e:
                print(f"❌ Process {self.process_id}: Failed to translate batch {i+1}: {str(e)}")
                # 如果批次翻译失败，保留原文
                failed_batch = []
                for entry in batch:
                    failed_batch.append({
                        'id': entry['id'],
                        'timestamp': entry['timestamp'],
                        'text': entry['text']  # 保持原文
                    })
                all_translated.extend(failed_batch)
        
        print(f"🎙️ Process {self.process_id}: Completed OpenAI translation: {len(all_translated)} entries")
        return all_translated
    
    def _batch_translate_with_google_multiprocess(self, entries):
        """多进程版本的Google翻译"""
        try:
            separator = "\n---SUBTITLE_SEPARATOR---\n"
            max_chars = 4500  # 留一些余量，避免超过5000字符限制
            translated_entries = []
            
            # 分批处理字幕条目
            current_batch = []
            current_length = 0
            batch_count = 0
            
            # 先计算总批次数以便显示进度
            total_batches = 1
            temp_length = 0
            for entry in entries:
                entry_length = len(entry['text']) + len(separator)
                if temp_length + entry_length > max_chars and temp_length > 0:
                    total_batches += 1
                    temp_length = entry_length
                else:
                    temp_length += entry_length
            
            for entry in entries:
                entry_text = entry['text']
                entry_length = len(entry_text) + len(separator)
                
                # 如果添加当前条目会超过限制，先处理当前批次
                if current_length + entry_length > max_chars and current_batch:
                    batch_count += 1
                    print(f"🎙️ Process {self.process_id}: Processing Google Translate batch {batch_count}/{total_batches} ({len(current_batch)} entries, {current_length} chars)")
                    
                    # 更新进度 (72% -> 80% 的范围内)
                    progress = 72 + int((batch_count / total_batches) * 8)
                    self.report_progress(min(80, progress))
                    
                    batch_results = self._translate_google_batch_multiprocess(current_batch, separator)
                    translated_entries.extend(batch_results)
                    
                    # 重置批次
                    current_batch = []
                    current_length = 0
                
                current_batch.append(entry)
                current_length += entry_length
            
            # 处理最后一批
            if current_batch:
                batch_count += 1
                print(f"🎙️ Process {self.process_id}: Processing final Google Translate batch {batch_count}/{total_batches} ({len(current_batch)} entries, {current_length} chars)")
                batch_results = self._translate_google_batch_multiprocess(current_batch, separator)
                translated_entries.extend(batch_results)
            
            print(f"🎙️ Process {self.process_id}: Successfully translated {len(translated_entries)} entries via Google Translate in {batch_count} batches")
            return translated_entries
            
        except Exception as e:
            print(f"❌ Process {self.process_id}: Google Translate batch translation failed: {str(e)}")
            raise
    
    def _translate_google_batch_multiprocess(self, entries, separator):
        """多进程版本的Google批次翻译"""
        # 提取所有需要翻译的文本
        texts_to_translate = [entry['text'] for entry in entries]
        
        # 使用分隔符将所有文本合并成一个大字符串
        combined_text = separator.join(texts_to_translate)
        
        # 使用Deep Translator进行批量翻译
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source='auto', target='zh-CN')
        translated_combined = translator.translate(combined_text)
        
        if not translated_combined:
            raise ValueError("Empty response from Google Translate")
        
        # 分割翻译结果
        translated_texts = translated_combined.split(separator)
        
        # 确保翻译结果数量匹配
        if len(translated_texts) != len(entries):
            print(f"⚠️ Process {self.process_id}: Translation count mismatch: expected {len(entries)}, got {len(translated_texts)}")
            # 填充缺失的翻译
            while len(translated_texts) < len(entries):
                translated_texts.append("")
            translated_texts = translated_texts[:len(entries)]
        
        # 构建翻译结果
        batch_results = []
        for i, entry in enumerate(entries):
            translated_text = translated_texts[i].strip() if i < len(translated_texts) else ""
            if not translated_text:
                translated_text = entry['text']  # 如果翻译失败，使用原文
            
            batch_results.append({
                'id': entry['id'],
                'timestamp': entry['timestamp'],
                'text': f"{entry['text']}\n{translated_text}"
            })
        
        return batch_results
    
    def burn_subtitles(self, subtitle_path, output_path):
        return VideoProcessor.burn_subtitles(self, subtitle_path, output_path)


class MultiprocessVideoManager:
    """多进程视频处理管理器"""
    
    def __init__(self, max_processes: Optional[int] = None):
        self.processes = []
        self.active_processes = {}  # 跟踪活动进程 {process_id: process_info}
        self.pending_tasks = []  # 等待处理的任务队列
        self.progress_queue = mp.Queue()
        self.result_queue = mp.Queue()
        self.is_processing = False
        self.next_process_id = 0
        
        # 使用配置文件中的进程数，或者传入的参数
        if max_processes is not None:
            self.max_processes = max_processes
        else:
            # 从config导入进程数配置
            self.max_processes = MAX_PROCESSES
        
        print(f"🔧 MultiprocessVideoManager initialized with max_processes={self.max_processes}")
    
    def _is_apple_silicon(self) -> bool:
        """检测是否是Apple Silicon"""
        if platform.system() != 'Darwin':
            return False
        try:
            result = subprocess.run(['sysctl', '-n', 'hw.optional.arm64'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0 and result.stdout.strip() == '1'
        except Exception:
            return False
    
    def start_processing(self, video_tasks: list):
        """
        开始多进程处理
        
        Args:
            video_tasks: 视频任务列表，每个任务包含 (video_path, engine, api_settings, cache_dir)
        """
        if self.is_processing:
            raise RuntimeError("已有处理任务在进行中")
        
        self.is_processing = True
        self.processes = []
    
    def submit_video(self, video_path: str, engine: str, api_settings: Dict[str, Any], cache_dir: str) -> int:
        """
        提交单个视频进行处理
        
        Args:
            video_path: 视频文件路径
            engine: 翻译引擎
            api_settings: API设置
            cache_dir: 缓存目录
            
        Returns:
            int: 进程ID（任务ID）
        """
        if not self.is_processing:
            self.is_processing = True
        
        # 创建任务信息
        task_info = {
            'task_id': self.next_process_id,
            'video_path': video_path,
            'engine': engine,
            'api_settings': api_settings,
            'cache_dir': cache_dir,
            'status': 'pending'  # pending, running, completed, failed
        }
        
        self.next_process_id += 1
        
        # 将任务添加到待处理队列
        self.pending_tasks.append(task_info)
        print(f"📝 Added task {task_info['task_id']} for {os.path.basename(video_path)} to queue")
        
        # 尝试启动新任务
        self._try_start_next_tasks()
        
        return task_info['task_id']
    
    def _try_start_next_tasks(self):
        """尝试启动下一个任务（如果有空闲进程槽位）"""
        # 清理已完成的进程
        self._cleanup_finished_processes()
        
        # 检查是否有空闲槽位和待处理任务
        while len(self.active_processes) < self.max_processes and self.pending_tasks:
            task_info = self.pending_tasks.pop(0)  # 取出第一个任务
            self._start_task(task_info)
    
    def _start_task(self, task_info: Dict[str, Any]):
        """启动单个任务"""
        process_id = task_info['task_id']
        
        # 创建并启动进程
        process = mp.Process(
            target=process_video_worker,
            args=(
                task_info['video_path'],
                task_info['engine'],
                task_info['api_settings'],
                task_info['cache_dir'],
                self.progress_queue,
                self.result_queue,
                process_id
            )
        )
        process.start()
        
        # 更新任务状态
        task_info['status'] = 'running'
        task_info['process'] = process
        task_info['completed'] = False
        
        # 保存进程信息
        self.processes.append(task_info)
        self.active_processes[process_id] = task_info
        
        print(f"🚀 Started process {process_id} for {os.path.basename(task_info['video_path'])} (active: {len(self.active_processes)}/{self.max_processes}, pending: {len(self.pending_tasks)})")
    
    def _cleanup_finished_processes(self):
        """清理已完成的进程并启动新任务"""
        finished_process_ids = []
        
        for process_id, proc_info in self.active_processes.items():
            if not proc_info['process'].is_alive():
                finished_process_ids.append(process_id)
                # 确保进程正确结束
                proc_info['process'].join(timeout=1)
                proc_info['completed'] = True
                proc_info['status'] = 'completed'
                print(f"🧹 Cleaned up finished process {process_id} for {os.path.basename(proc_info['video_path'])}")
        
        # 从活动进程字典中移除已完成的进程
        for process_id in finished_process_ids:
            if process_id in self.active_processes:
                del self.active_processes[process_id]
    
    def get_progress_updates(self) -> list:
        """获取所有进度更新"""
        # 首先清理已完成的进程并尝试启动新任务
        self._cleanup_finished_processes()
        self._try_start_next_tasks()
        
        updates = []
        while True:
            try:
                update = self.progress_queue.get_nowait()
                updates.append(update)
            except queue.Empty:
                break
        return updates
    
    def get_results(self) -> list:
        """获取所有完成的结果"""
        results = []
        while True:
            try:
                result = self.result_queue.get_nowait()
                results.append(result)
            except queue.Empty:
                break
        return results
    
    def is_all_complete(self) -> bool:
        """检查所有任务是否完成（包括队列中的）"""
        if not self.processes and not self.pending_tasks:
            return True
        
        # 清理已完成的进程并尝试启动新任务
        self._cleanup_finished_processes()
        self._try_start_next_tasks()
        
        # 检查是否还有活动进程或待处理任务
        return len(self.active_processes) == 0 and len(self.pending_tasks) == 0
    
    def process_videos(self, video_paths: List[str], engine: str, api_settings: Dict[str, Any], cache_dir: str) -> List[int]:
        """
        批量处理视频文件
        
        Args:
            video_paths: 视频文件路径列表
            engine: 翻译引擎
            api_settings: API设置
            cache_dir: 缓存目录
            
        Returns:
            List[int]: 任务ID列表
        """
        if not video_paths:
            return []
        
        task_ids = []
        print(f"📋 Submitting {len(video_paths)} videos for processing (max concurrent: {self.max_processes})")
        
        for video_path in video_paths:
            if os.path.exists(video_path):
                task_id = self.submit_video(video_path, engine, api_settings, cache_dir)
                task_ids.append(task_id)
                print(f"   Added: {os.path.basename(video_path)} (Task ID: {task_id})")
            else:
                print(f"⚠️ Video file not found: {video_path}")
        
        print(f"📊 Queue Status: {len(self.active_processes)} running, {len(self.pending_tasks)} pending")
        return task_ids
    
    def get_active_process_count(self) -> int:
        """获取当前活动进程数量"""
        self._cleanup_finished_processes()
        return len(self.active_processes)
    
    def get_total_process_count(self) -> int:
        """获取总进程数量（包括已完成的）"""
        return len(self.processes)
    
    def stop_all(self):
        """停止所有进程"""
        print("🛑 Stopping all processes...")
        
        # 停止所有活动进程
        for process_id, proc_info in self.active_processes.items():
            if proc_info['process'].is_alive():
                print(f"🛑 Terminating process {process_id}")
                proc_info['process'].terminate()
                proc_info['process'].join(timeout=5)
                if proc_info['process'].is_alive():
                    print(f"🛑 Force killing process {process_id}")
                    proc_info['process'].kill()
                proc_info['completed'] = True
        
        # 清空活动进程字典和待处理任务
        self.active_processes.clear()
        self.pending_tasks.clear()
        self.is_processing = False
        print(f"🛑 All processes stopped. Cleared {len(self.pending_tasks)} pending tasks.")
    
    def cleanup(self):
        """清理资源"""
        print("🧹 Cleaning up multiprocess manager...")
        
        self.stop_all()
        
        # 清空队列
        while not self.progress_queue.empty():
            try:
                self.progress_queue.get_nowait()
            except queue.Empty:
                break
        
        while not self.result_queue.empty():
            try:
                self.result_queue.get_nowait()
            except queue.Empty:
                break
        
        print("🧹 Multiprocess manager cleanup completed")




