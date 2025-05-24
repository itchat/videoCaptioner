import time
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
import requests.adapters
from PyQt5.QtCore import QRunnable
import os
import subprocess
from datetime import datetime
from pywhispercpp.model import Model
from deep_translator import GoogleTranslator
from core.worker_signals import WorkerSignals
from utils.logger import VideoLogger
from utils.system_optimizer import SystemOptimizer
import threading
import re
import platform
import json


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
        
        # Whisper模型缓存 - 避免重复加载
        self._whisper_model = None
    
        # 跟踪处理状态以确保正确清理
        self._processing_complete = False
        
        # 翻译缓存以提高重复短语的处理效率
        self._translation_cache = {}
        
        # 系统优化配置
        self.optimizer = SystemOptimizer()
        self.optimized_config = self.optimizer.get_optimized_config()
        
        # 记录系统优化信息
        self.logger.info(f"Video processor optimization - CPU cores: {self.optimized_config['system_info']['cpu_count']}")
        if self.optimized_config['system_info'].get('is_apple_silicon'):
            self.logger.info("Apple Silicon detected - using optimized video processing")
        if self.optimized_config['use_hardware_accel']:
            self.logger.info("Hardware acceleration available for video processing")

    def get_whisper_model_path(self):
        """获取 Whisper 模型文件路径，优先使用本地文件，否则下载到用户目录"""
        # 检测是否在打包环境中运行
        is_bundled = getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')
        
        # 定义模型下载URL
        model_url = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin"
        
        # 优先使用用户目录（特别是在打包环境中）
        user_model_dir = os.path.expanduser("~/.whisper_models")
        user_model_path = os.path.join(user_model_dir, "ggml-large-v3-turbo.bin")
        
        if os.path.exists(user_model_path):
            self.logger.info(f"Found user model: {user_model_path}")
            # Validate existing model file
            if self._validate_model_file(user_model_path):
                return user_model_path
            else:
                self.logger.warning("Existing user model file is corrupted, will re-download")
                try:
                    os.remove(user_model_path)
                    self.logger.info("Removed corrupted user model file")
                except Exception as e:
                    self.logger.error(f"Failed to remove corrupted file: {e}")
        
        # 在非打包环境下，检查应用内部模型路径
        if not is_bundled:
            app_model_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), 
                "models"
            )
            app_model_path = os.path.join(app_model_dir, "ggml-large-v3-turbo.bin")
            
            if os.path.exists(app_model_path):
                self.logger.info(f"Found app model: {app_model_path}")
                # Validate existing app model file
                if self._validate_model_file(app_model_path):
                    return app_model_path
                else:
                    self.logger.warning("Existing app model file is corrupted, will download to user directory")
        
        # 下载模型到用户目录（适用于所有环境）
        try:
            os.makedirs(user_model_dir, exist_ok=True)
            
            # 发送下载开始信号
            self.signals.download_started.emit("Whisper large-v3-turbo")
            self.signals.download_status.emit("Initializing model download...")
            
            # 下载模型到用户目录
            self.logger.info("Downloading Whisper large-v3-turbo model to user directory...")
            self.report_status("Downloading Whisper model (first time only)...")
            
            import time
            start_time = time.time()
            
            response = requests.get(model_url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            last_time = start_time
            last_downloaded = 0
            
            self.signals.download_status.emit(f"Downloading from {model_url}")
            
            with open(user_model_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        # 计算并发送下载进度
                        if total_size > 0:
                            progress = min(100, int((downloaded / total_size) * 100))
                            downloaded_mb = downloaded / (1024 * 1024)
                            total_mb = total_size / (1024 * 1024)
                            
                            # 计算下载速度（每秒更新一次）
                            current_time = time.time()
                            if current_time - last_time >= 1.0:
                                speed_bytes_per_sec = (downloaded - last_downloaded) / (current_time - last_time)
                                speed_mbps = speed_bytes_per_sec / (1024 * 1024)
                                
                                # 发送下载进度信号
                                self.signals.download_progress.emit(progress, downloaded_mb, total_mb, speed_mbps)
                                
                                last_time = current_time
                                last_downloaded = downloaded
                            
                            # 更新文件处理进度（限制在20%以内）
                            file_progress = min(20, progress // 5)
                            self.report_progress(file_progress)
            
            self.logger.info(f"Model downloaded to: {user_model_path}")
            
            # Validate downloaded model file
            if not self._validate_model_file(user_model_path):
                self.logger.error("Downloaded model file failed validation")
                # Remove corrupted file
                try:
                    os.remove(user_model_path)
                    self.logger.info("Removed corrupted model file")
                except Exception as remove_error:
                    self.logger.error(f"Failed to remove corrupted file: {remove_error}")
                
                self.signals.download_error.emit("Downloaded model file is corrupted. Please try again.")
                raise RuntimeError("Downloaded model file failed validation")
            
            self.signals.download_completed.emit()
            self.signals.download_status.emit("Model download completed successfully!")
            return user_model_path
            
        except Exception as e:
            self.logger.error(f"Failed to download model: {str(e)}")
            self.signals.download_error.emit(f"Failed to download Whisper model: {str(e)}")
            raise RuntimeError(f"Failed to download Whisper model: {str(e)}")

    def _validate_model_file(self, model_path):
        """Validate the integrity of the downloaded Whisper model file"""
        try:
            # Check if file exists
            if not os.path.exists(model_path):
                self.logger.error(f"Model file does not exist: {model_path}")
                return False
            
            # Check file size (Whisper large-v3-turbo should be around 1.5GB)
            file_size = os.path.getsize(model_path)
            min_size = 1.4 * 1024 * 1024 * 1024  # 1.4 GB minimum
            max_size = 2.0 * 1024 * 1024 * 1024  # 2.0 GB maximum
            
            if file_size < min_size:
                self.logger.error(f"Model file too small: {file_size / (1024**3):.2f} GB")
                return False
            
            if file_size > max_size:
                self.logger.error(f"Model file too large: {file_size / (1024**3):.2f} GB")
                return False
            
            # Check file header (GGML models start with specific magic bytes)
            with open(model_path, 'rb') as f:
                header = f.read(8)
                
                # GGML files can start with 'ggml', 'GGML', or 'lmgg' (little-endian)
                valid_headers = [b'ggml', b'GGML', b'lmgg', b'GMGL']
                if not any(header.startswith(h) for h in valid_headers):
                    self.logger.error(f"Invalid model file header: {header[:4]}")
                    return False
            
            # Additional check: ensure file is not truncated
            # Try to read from the end of the file
            with open(model_path, 'rb') as f:
                f.seek(-1024, 2)  # Seek to last 1KB
                end_data = f.read(1024)
                if len(end_data) != 1024:
                    self.logger.error("Model file appears to be truncated")
                    return False
            
            self.logger.info(f"Model file validation passed: {file_size / (1024**3):.2f} GB")
            return True
            
        except Exception as e:
            self.logger.error(f"Model file validation failed: {str(e)}")
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
            # 确保资源被正确关闭
            try:
                if hasattr(self, 'session'):
                    self.session.close()
                    
                # 释放Whisper模型内存
                if hasattr(self, '_whisper_model') and self._whisper_model is not None:
                    del self._whisper_model
                    self._whisper_model = None
                    
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

    def extract_audio(self, audio_path):
        ffmpeg_path = self.get_ffmpeg_path()
        if not ffmpeg_path:
            raise FileNotFoundError("Could not find ffmpeg. Please install it first.")
            
        # 检查输入文件
        if not os.path.exists(self.video_path):
            raise FileNotFoundError(f"Video file not found: {self.video_path}")
            
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
            error_msg = f"Error during audio extraction: {e.stderr}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

    def generate_subtitles(self, audio_path, srt_path):
        # 使用缓存的 Whisper 模型提高效率
        if self._whisper_model is None:
            self.logger.info("Loading Whisper large-v3-turbo model with whisper.cpp...")
            self.report_progress(25)  # 更细粒度的进度反馈
            
            try:
                # 获取模型路径
                model_path = self.get_whisper_model_path()
                
                # 初始化模型并检查硬件加速选项
                self.logger.info("Initializing Whisper model with hardware acceleration options")
                
                try:
                    # 使用系统优化的线程配置
                    n_threads = self.optimized_config['whisper_threads']
                    
                    self.logger.info(f"Using optimized {n_threads} threads for Whisper processing")
                    self._whisper_model = Model(
                        model_path,
                        n_threads=n_threads,
                        print_realtime=False,
                        print_progress=False
                    )
                    
                    self.logger.info("Whisper model initialized with system-optimized threading")
                    
                except Exception as model_error:
                    # 如果带参数初始化失败，回退到默认初始化
                    self.logger.warning(f"Failed to initialize with optimization parameters: {model_error}")
                    self.logger.info("Falling back to default initialization")
                    self._whisper_model = Model(model_path)
                    
                self.logger.info("Whisper model loaded successfully")
                    
            except Exception as e:
                self.logger.error(f"Failed to load Whisper model: {str(e)}")
                raise RuntimeError(f"Failed to load Whisper model: {str(e)}")
            
        self.report_progress(30)  # 模型加载完成
        
        # 使用 pywhispercpp 进行转录
        try:
            self.logger.info(f"Starting transcription of: {audio_path}")
            
            # pywhispercpp 转录 - 直接返回 Segment 对象列表
            segments = self._whisper_model.transcribe(audio_path)
            
            self.report_progress(35)  # 转录开始
            
            # 将结果写入 SRT 文件
            with open(srt_path, "w", encoding="utf-8") as f:
                segment_count = 0
                
                for i, segment in enumerate(segments):
                    # pywhispercpp 的时间戳是毫秒，需要转换为秒
                    start_time = segment.t0 / 1000.0  # 转换为秒
                    end_time = segment.t1 / 1000.0    # 转换为秒
                    text = segment.text.strip()
                    
                    if text:  # 只写入非空文本
                        start = self.format_time(start_time)
                        end = self.format_time(end_time)
                        f.write(f"{i + 1}\n{start} --> {end}\n{text}\n\n")
                        segment_count += 1
                        
                    # 更新进度 (35% -> 40%)
                    if i % 10 == 0 and len(segments) > 0:
                        progress = 35 + min(5, (i / len(segments)) * 5)
                        self.report_progress(int(progress))
                        
            self.logger.info(f"Transcription completed, generated {segment_count} segments")
            
        except Exception as e:
            self.logger.error(f"Transcription failed: {str(e)}")
            raise RuntimeError(f"Transcription failed: {str(e)}")

    @staticmethod
    def format_time(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:06.3f}".replace(".", ",")

    def translate_subtitles(self, lines):
        try:
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
            
            # 尝试批量翻译短字幕
            if self._should_use_batch_translation(entries):
                self.logger.info("Using batch translation for efficiency")
                batch_result = self._batch_translate_openai(entries)
                if batch_result:
                    translated_entries = batch_result
                    self.signals.file_progress.emit(self.base_name, 70)  # 批量完成，直接到70%
                else:
                    # 批量失败，回退到单独翻译
                    self.logger.info("Batch translation failed, using individual translation")
                    translated_entries = self._translate_individually(entries, translation_lock, total_entries)
            else:
                # 使用单独翻译
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
        """Use OpenAI for Single Subtitle Translation with session reuse and caching"""
        # 检查缓存
        cache_key = f"openai_{hash(entry['text'])}"
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]
            
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": """你是一位资深的专业翻译专家，精通中英文互译，遵循翻译的"信、达、雅"三大原则：

**翻译原则：**
- 信（忠实）：准确传达原文意思，不遗漏、不添加
- 达（通顺）：译文流畅自然，符合中文表达习惯  
- 雅（优美）：语言得体，用词恰当，具有良好的可读性

**翻译策略：**
1. **专业术语**：采用直译，保持准确性
2. **习语俚语**：采用意译，转换为对应的中文表达
3. **文化背景**：结合中文语境，适当调整表达方式
4. **语言风格**：保持原文的正式/非正式程度
5. **句式结构**：优先使用中文的自然表达方式

**输出要求：**
- 只输出中文翻译结果，不包含英文原文
- 不添加任何解释或多余信息
- 确保译文自然流畅，适合字幕阅读

请将以下英文字幕翻译成中文："""},
                {"role": "user", "content": f"""{entry['text']}"""}
            ],
            "temperature": 0.3,  # 降低温度以获得更一致的翻译
            "max_tokens": 1000
        }

        try:
            response = self.session.post(
                f"{self.api_settings['base_url']}/v1/chat/completions",
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content'].strip()
                if not content:
                    raise ValueError("Empty response from OpenAI API")
                
                # 缓存结果
                self._translation_cache[cache_key] = content
                return content
            elif response.status_code == 429:  # 速率限制
                raise requests.exceptions.RequestException(f"Rate limit exceeded: {response.status_code}")
            else:
                raise requests.exceptions.RequestException(f"OpenAI API error: {response.status_code} - {response.text}")
                
        except requests.exceptions.Timeout:
            raise requests.exceptions.RequestException("OpenAI API request timeout")
        except requests.exceptions.ConnectionError:
            raise requests.exceptions.RequestException("OpenAI API connection error")
        except json.JSONDecodeError:
            raise requests.exceptions.RequestException("Invalid JSON response from OpenAI API")

    def _translate_with_google(self, entry):
        """Translated using the Deep Translator with better error handling and caching."""
        # 检查缓存
        cache_key = f"google_{hash(entry['text'])}"
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]
            
        try:
            text_to_translate = entry['text'].strip()
            if not text_to_translate:
                raise ValueError("Empty text to translate")
                
            translator = GoogleTranslator(source='auto', target='zh-CN')
            translated_text = translator.translate(text_to_translate)
            
            if not translated_text:
                raise ValueError("Empty translation result from Google Translate")
            
            # 缓存结果
            self._translation_cache[cache_key] = translated_text
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
            
        if len(entries) < 3:  # 太少的条目不值得批量处理
            return False
            
        # 分析字幕特征
        total_chars = sum(len(entry['text']) for entry in entries)
        avg_chars = total_chars / len(entries)
        short_entries = sum(1 for entry in entries if len(entry['text']) < 80)
        
        # 如果大部分字幕都很短且平均长度合适，使用批量翻译
        short_ratio = short_entries / len(entries)
        
        # 更智能的判断条件
        return (
            short_ratio > 0.6 and  # 60%以上是短字幕
            avg_chars < 60 and     # 平均长度不超过60字符
            len(entries) <= 15 and # 不要批量处理太多条目
            total_chars < 800      # 总字符数不要太多，避免API限制
        )
    
    def _batch_translate_openai(self, entries):
        """批量翻译短字幕以提高效率"""
        # 使用简单的分隔符避免AI混淆
        batch_lines = []
        for entry in entries:
            batch_lines.append(f"ID:{entry['id']}|{entry['text']}")
        
        batch_text = "\n".join(batch_lines)
        
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": """你是一位资深的专业翻译专家，精通中英文互译，遵循翻译的"信、达、雅"三大原则。

**翻译原则：**
- 信（忠实）：准确传达原文意思，不遗漏、不添加
- 达（通顺）：译文流畅自然，符合中文表达习惯  
- 雅（优美）：语言得体，用词恰当，具有良好的可读性

**翻译策略：**
1. **专业术语**：采用直译，保持准确性
2. **习语俚语**：采用意译，转换为对应的中文表达
3. **文化背景**：结合中文语境，适当调整表达方式
4. **上下文连贯**：考虑字幕间的逻辑关系，保持表达一致性

**严格格式要求：**
输入格式：ID:数字|英文内容
输出格式：ID:数字|中文翻译

请逐行翻译，保持完全相同的ID号，只翻译竖线后的内容。
示例：
输入：ID:1|Hello world
输出：ID:1|你好世界

请确保每行输出都严格按照 "ID:数字|中文翻译" 的格式，不要有任何额外的文字。"""},
                {"role": "user", "content": batch_text}
            ],
            "temperature": 0.2,
            "max_tokens": 4000
        }

        try:
            response = self.session.post(
                f"{self.api_settings['base_url']}/v1/chat/completions",
                json=data,
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content'].strip()
                
                # 解析批量翻译结果 - 改进的解析逻辑
                translated_entries = []
                lines = content.split('\n')
                
                for line in lines:
                    line = line.strip()
                    if not line or not '|' in line:
                        continue
                        
                    # 尝试多种可能的格式
                    if line.startswith('ID:'):
                        try:
                            # 标准格式：ID:数字|翻译
                            id_part, translation = line.split('|', 1)
                            entry_id = int(id_part.replace('ID:', '').strip())
                        except (ValueError, IndexError):
                            continue
                    elif ':' in line and '|' in line:
                        try:
                            # 备用格式：数字|翻译 或 数字:翻译
                            parts = line.split('|', 1)
                            if len(parts) == 2:
                                id_str = parts[0].strip()
                                translation = parts[1]
                                # 提取数字
                                match = re.search(r'\d+', id_str)
                                if match:
                                    entry_id = int(match.group())
                                else:
                                    continue
                            else:
                                continue
                        except (ValueError, IndexError):
                            continue
                    else:
                        continue
                    
                    # 找到对应的原始条目并创建双语字幕
                    original_entry = next((e for e in entries if e['id'] == entry_id), None)
                    if original_entry and translation.strip():
                        translated_entries.append({
                            'id': entry_id,
                            'timestamp': original_entry['timestamp'],
                            'text': f"{original_entry['text']}\n{translation.strip()}"  # 双语格式
                        })
                
                # 检查翻译完整性
                if len(translated_entries) >= len(entries) * 0.7:  # 至少成功70%
                    return translated_entries
                else:
                    self.logger.warning(f"Batch translation incomplete: {len(translated_entries)}/{len(entries)} entries")
                    return None
                    
            else:
                raise requests.exceptions.RequestException(f"OpenAI API error: {response.status_code}")
                
        except Exception as e:
            self.logger.warning(f"Batch translation failed, falling back to individual: {str(e)}")
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


