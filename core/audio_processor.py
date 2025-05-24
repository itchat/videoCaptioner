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
import re
import platform
import shutil


class AudioProcessor(QRunnable):
    def __init__(self, audio_path, engine, api_settings, cache_dir,
                 progress_callback=None, status_callback=None):
        super().__init__()
        self.audio_path = audio_path
        self.engine = engine
        self.api_settings = api_settings
        self.cache_dir = cache_dir
        self.progress_callback = progress_callback
        self.status_callback = status_callback
        self.base_name = os.path.basename(audio_path)
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
        
        # 翻译缓存以提高重复短语的处理效率
        self._translation_cache = {}
        
        # 系统优化配置
        self.optimizer = SystemOptimizer()
        self.optimized_config = self.optimizer.get_optimized_config()
        
        # 记录系统优化信息
        self.logger.info(f"System optimization - CPU cores: {self.optimized_config['system_info']['cpu_count']}")
        if self.optimized_config['system_info'].get('is_apple_silicon'):
            self.logger.info("Apple Silicon detected - using optimized ML processing")
        self.logger.info(f"Configured thread limits - Whisper: {self.optimized_config['whisper_threads']}, "
                        f"OpenAI: {self.optimized_config['openai_workers']}, "
                        f"Google: {self.optimized_config['google_workers']}")

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
                
                # GGML files typically start with 'ggml' or 'GGML' magic bytes
                if not (header.startswith(b'ggml') or header.startswith(b'GGML')):
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
            self.logger.info(f"Starting to process audio: {self.base_name}")
            cache_paths = self.get_cache_paths()

            # 如果是非wav格式，先转换为wav
            if not self.audio_path.lower().endswith('.wav'):
                self.report_status("Converting audio format...")
                self.report_progress(0)
                self.convert_audio_to_wav(cache_paths['audio'])
                self.report_progress(20)
            else:
                # 直接复制wav文件
                shutil.copy2(self.audio_path, cache_paths['audio'])
                self.report_progress(20)

            # Generate Transcript (20-60%)
            self.report_status("Transcribing audio...")
            self.generate_transcript(cache_paths['audio'], cache_paths['transcript'])
            self.logger.info("Transcript generation complete")
            self.report_progress(60)

            # Translate Transcript (60-80%)
            self.report_status("Translating transcript...")
            with open(cache_paths['transcript'], "r", encoding="utf-8") as f:
                content = f.read()
            
            self.logger.info(f"Original transcript content length: {len(content)}")
            self.logger.info(f"First 200 chars: {content[:200]}")
            
            translated_content = self.translate_transcript(content)
            
            self.logger.info(f"Translated content length: {len(translated_content)}")
            self.logger.info(f"First 200 chars of translated: {translated_content[:200]}")
            
            with open(cache_paths['bilingual_transcript'], "w", encoding="utf-8") as f:
                f.write(translated_content)
            self.logger.info("Transcript translation completed")
            self.report_progress(80)

            # Generate PDF (80-100%)
            self.report_status("Generating PDF...")
            self.generate_podcast_pdf(cache_paths['bilingual_transcript'], cache_paths['output_pdf'])
            self.logger.info("PDF generation completed")
            self.report_progress(100)
            self.report_status("Processing completed!")

            # Send Completion Signal
            self.signals.finished.emit()

        except Exception as e:
            error_msg = f"Processing failed: {str(e)}"
            self.logger.error(error_msg)
            self.signals.error.emit(f"Failed to process audio {self.base_name} : {str(e)}")
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
                print(f"Error during cleanup: {cleanup_error}")

    def get_cache_paths(self):
        base_name = os.path.splitext(self.base_name)[0]
        return {
            'audio': os.path.join(self.cache_dir, f"{base_name}_audio.wav"),
            'transcript': os.path.join(self.cache_dir, f"{base_name}_transcript.txt"),
            'bilingual_transcript': os.path.join(self.cache_dir, f"{base_name}_bilingual.txt"),
            'output_pdf': os.path.join(
                os.path.dirname(self.audio_path),
                f"{base_name}_podcast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
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

    def convert_audio_to_wav(self, output_path):
        ffmpeg_path = self.get_ffmpeg_path()
        if not ffmpeg_path:
            raise FileNotFoundError("Could not find ffmpeg. Please install it first.")
            
        # 检查输入文件
        if not os.path.exists(self.audio_path):
            raise FileNotFoundError(f"Audio file not found: {self.audio_path}")
            
        try:
            # 优化FFmpeg参数
            result = subprocess.run([
                ffmpeg_path,
                "-i", self.audio_path,
                "-acodec", "pcm_s16le",
                "-ac", "1",  # 单声道
                "-ar", "16000",  # 16kHz采样率，对语音识别足够
                output_path,
                "-y"
            ], capture_output=True, text=True, check=True, timeout=300)
            
            self.logger.info("Audio conversion completed successfully")
            
            # 验证输出文件
            if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
                raise RuntimeError("Audio conversion failed: output file is empty or missing")
                
            return True
        except subprocess.TimeoutExpired:
            raise RuntimeError("Audio conversion timeout: process took too long")
        except subprocess.CalledProcessError as e:
            error_msg = f"Error during audio conversion: {e.stderr}"
            self.logger.error(error_msg)
            raise RuntimeError(error_msg)

    def generate_transcript(self, audio_path, transcript_path):
        # 使用缓存的 Whisper 模型提高效率
        if self._whisper_model is None:
            self.logger.info("Loading Whisper large-v3-turbo model with whisper.cpp...")
            self.report_progress(25)
            
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
            
        self.report_progress(30)
        
        # 使用 pywhispercpp 进行转录
        try:
            self.logger.info(f"Starting transcription of: {audio_path}")
            
            # pywhispercpp 转录 - 直接返回 Segment 对象列表
            segments = self._whisper_model.transcribe(audio_path)
            
            self.report_progress(40)
            
            # 生成更适合翻译的段落格式 - 按句子结构分段
            with open(transcript_path, "w", encoding="utf-8") as f:
                current_paragraph = []
                sentence_count = 0
                total_segments = len(segments)
                
                for i, segment in enumerate(segments):
                    # pywhispercpp 的 Segment 对象有 text 属性
                    text = segment.text.strip()
                    if text:
                        current_paragraph.append(text)
                        
                        # 检查是否包含句子结束标点
                        has_sentence_ending = any(punct in text for punct in '.!?。！？')
                        if has_sentence_ending:
                            sentence_count += 1
                        
                        # 当达到20个完整句子时，或者遇到明显的段落分隔时结束段落
                        should_end_paragraph = (
                            sentence_count >= 20 or  # 20个句子一段，减少PDF间距
                            len(current_paragraph) >= 50 or  # 防止段落过长
                            (has_sentence_ending and len(" ".join(current_paragraph)) > 800)  # 超过800字符且有句号
                        )
                        
                        if should_end_paragraph:
                            paragraph_text = " ".join(current_paragraph)
                            # 清理文本，确保句子结构完整
                            paragraph_text = self.clean_paragraph_text(paragraph_text)
                            f.write(f"{paragraph_text}\n\n")
                            
                            current_paragraph = []
                            sentence_count = 0
                            
                        # 更新进度 (40% -> 60%)
                        if i % 20 == 0:
                            progress = 40 + min(20, (i / max(1, total_segments)) * 20)
                            self.report_progress(int(progress))
                
                # 处理最后一个段落
                if current_paragraph:
                    paragraph_text = " ".join(current_paragraph)
                    paragraph_text = self.clean_paragraph_text(paragraph_text)
                    f.write(f"{paragraph_text}\n\n")
                    
            self.logger.info("Transcription completed successfully")
                    
        except Exception as e:
            self.logger.error(f"Transcription failed: {str(e)}")
            raise RuntimeError(f"Transcription failed: {str(e)}")

    def clean_paragraph_text(self, text):
        """清理和格式化段落文本，确保翻译友好的句子结构"""
        # 去除多余空格
        text = re.sub(r'\s+', ' ', text)
        
        # 修复常见的句子连接问题
        text = re.sub(r'([a-z])\s+([A-Z])', r'\1. \2', text)  # 在小写字母后大写字母前加句号
        text = re.sub(r'([.!?])\s*([a-z])', r'\1 \2', text)  # 标点后确保有空格
        
        # 清理多余的标点
        text = re.sub(r'[.]{2,}', '.', text)  # 多个句号变成一个
        text = re.sub(r'[,]{2,}', ',', text)  # 多个逗号变成一个
        
        # 确保句子结尾有标点
        text = text.strip()
        if text and text[-1] not in '.!?。！？':
            # 检查最后几个词，如果是完整句子就加句号
            words = text.split()
            if len(words) >= 3:  # 至少3个词才算完整句子
                text += '.'
            
        return text

    def translate_transcript(self, content):
        """翻译整个转录内容"""
        try:
            # 将内容分段处理，避免API限制
            paragraphs = [p.strip() for p in content.split('\n\n') if p.strip()]
            
            if not paragraphs:
                return ""
            
            translated_paragraphs = []
            total_paragraphs = len(paragraphs)
            
            # 使用多线程处理，但使用系统优化的并发数
            optimal_workers = (self.optimized_config['openai_workers'] 
                             if self.engine == "OpenAI Translate" 
                             else self.optimized_config['google_workers'])
            
            self.logger.info(f"Using {optimal_workers} threads for {self.engine} translation")
            
            with ThreadPoolExecutor(max_workers=optimal_workers) as executor:
                future_to_paragraph = {
                    executor.submit(self._translate_paragraph, paragraph, i): (paragraph, i)
                    for i, paragraph in enumerate(paragraphs)
                }
                
                results = {}
                for future in as_completed(future_to_paragraph):
                    paragraph, index = future_to_paragraph[future]
                    try:
                        translated_paragraph = future.result()
                        if translated_paragraph:
                            results[index] = {
                                'original': paragraph,
                                'translated': translated_paragraph
                            }
                        
                        # 更新进度 (60% -> 80%)
                        progress = 60 + (len(results) / total_paragraphs) * 20
                        self.report_progress(int(progress))
                        
                    except Exception as e:
                        self.logger.error(f"Failed to translate paragraph {index}: {str(e)}")
                        results[index] = {
                            'original': paragraph,
                            'translated': f"[翻译失败: {paragraph[:50]}...]"
                        }
            
            # 构建双语内容
            bilingual_content = ""
            for i in range(total_paragraphs):
                if i in results:
                    bilingual_content += f"【原文】\n{results[i]['original']}\n\n"
                    bilingual_content += f"【中文】\n{results[i]['translated']}\n\n"
                    bilingual_content += "---\n\n"
                
            return bilingual_content
            
        except Exception as e:
            self.logger.error(f"Translation failed: {str(e)}")
            raise

    def _translate_paragraph(self, paragraph, index):
        """翻译单个段落"""
        max_attempts = 3
        base_delay = 1
        
        for attempt in range(1, max_attempts + 1):
            try:
                if self.engine == "OpenAI Translate":
                    result = self._translate_paragraph_openai(paragraph)
                else:
                    result = self._translate_paragraph_google(paragraph)
                
                # 验证翻译结果
                if not result or result.strip() == paragraph.strip():
                    raise ValueError(f"Translation failed or returned original text")
                
                self.logger.info(f"Successfully translated paragraph {index} using {self.engine}")
                return result
                
            except Exception as e:
                if attempt == max_attempts:
                    self.logger.error(f"Max attempts reached for paragraph {index}: {str(e)}")
                    # 返回原文而不是抛出异常，避免整个处理失败
                    return f"[翻译失败] {paragraph}"
                
                delay = base_delay * (2 ** (attempt - 1))
                self.logger.warning(f"Translation attempt {attempt} failed for paragraph {index}, retrying in {delay}s: {str(e)}")
                time.sleep(delay)

    def _translate_paragraph_openai(self, paragraph):
        """使用OpenAI翻译段落"""
        # 检查缓存
        cache_key = f"openai_para_{hash(paragraph)}"
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]
            
        data = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": """你是一位资深的专业翻译专家，专门从事音频转录内容的中英文互译，遵循翻译的"信、达、雅"三大原则：

**翻译原则：**
- 信（忠实）：准确传达原文意思，保持内容完整性
- 达（通顺）：译文流畅自然，符合中文阅读习惯，适合podcast风格
- 雅（优美）：语言得体，用词恰当，具有良好的可读性

**针对音频转录的特殊要求：**
1. **口语化处理**：将口语表达转换为书面语，但保持自然亲切的语调
2. **段落整理**：合理断句，形成清晰的段落结构
3. **语境连贯**：确保翻译后的中文逻辑清晰，易于理解
4. **专业术语**：准确翻译专业概念，必要时提供简要解释
5. **语调保持**：保持原文的情感色彩和表达风格

**输出要求：**
- 只输出中文翻译结果，不包含英文原文
- 确保译文适合作为podcast文档阅读
- 语言流畅自然，避免机器翻译痕迹

请将以下音频转录内容翻译成中文："""},
                {"role": "user", "content": paragraph}
            ],
            "temperature": 0.3,
            "max_tokens": 2000
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
                if not content:
                    raise ValueError("Empty response from OpenAI API")
                
                # 缓存结果
                self._translation_cache[cache_key] = content
                return content
            else:
                raise requests.exceptions.RequestException(f"OpenAI API error: {response.status_code}")
                
        except Exception as e:
            raise requests.exceptions.RequestException(f"OpenAI translation error: {str(e)}")

    def _translate_paragraph_google(self, paragraph):
        """使用Google翻译段落"""
        # 检查缓存
        cache_key = f"google_para_{hash(paragraph)}"
        if cache_key in self._translation_cache:
            return self._translation_cache[cache_key]
        
        # 预处理文本：清理和规范化
        cleaned_paragraph = self._preprocess_for_translation(paragraph)
        self.logger.info(f"Starting Google translation for text: {cleaned_paragraph[:50]}...")
            
        try:
            # 如果段落太长，分块处理
            max_length = 3500  # 保守的字符限制，留出缓冲
            if len(cleaned_paragraph) > max_length:
                self.logger.info(f"Text too long ({len(cleaned_paragraph)} chars), splitting into chunks")
                # 按句子分割，保持句子完整性
                sentences = re.split(r'(?<=[.!?。！？])\s+', cleaned_paragraph)
                translated_sentences = []
                
                current_chunk = ""
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                        
                    # 检查加入这个句子后是否超长
                    test_chunk = current_chunk + " " + sentence if current_chunk else sentence
                    
                    if len(test_chunk) < max_length:
                        current_chunk = test_chunk
                    else:
                        # 翻译当前chunk
                        if current_chunk:
                            translated_chunk = self._do_google_translate(current_chunk)
                            if translated_chunk:
                                translated_sentences.append(translated_chunk)
                        
                        # 开始新的chunk
                        current_chunk = sentence
                
                # 翻译最后一个chunk
                if current_chunk:
                    translated_chunk = self._do_google_translate(current_chunk)
                    if translated_chunk:
                        translated_sentences.append(translated_chunk)
                
                result = "".join(translated_sentences)
            else:
                result = self._do_google_translate(cleaned_paragraph)
            
            if not result or not result.strip():
                raise ValueError("Empty translation result from Google Translate")
            
            # 验证翻译质量
            if self._is_translation_valid(paragraph, result):
                self.logger.info(f"Google translation successful: {result[:50]}...")
                # 缓存结果
                self._translation_cache[cache_key] = result
                return result
            else:
                raise ValueError("Translation quality check failed")
            
        except Exception as e:
            self.logger.error(f"Google Translate error: {str(e)}")
            raise Exception(f"Google Translate error: {str(e)}")

    def _preprocess_for_translation(self, text):
        """预处理文本以提高翻译质量"""
        # 移除多余的空白字符
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 修复常见的转录错误
        text = re.sub(r'\b(um|uh|er|ah)\b', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s+', ' ', text).strip()
        
        # 确保句子有适当的标点
        if text and text[-1] not in '.!?。！？':
            text += '.'
        
        return text

    def _do_google_translate(self, text):
        """执行实际的Google翻译，带重试机制"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                translator = GoogleTranslator(source='auto', target='zh-CN')
                result = translator.translate(text)
                
                if result and result.strip():
                    return result
                else:
                    raise ValueError("Empty result from translator")
                    
            except Exception as e:
                if attempt == max_retries - 1:
                    raise e
                self.logger.warning(f"Google translate attempt {attempt + 1} failed: {str(e)}")
                time.sleep(1 * (attempt + 1))  # 递增延迟
        
        return None

    def _is_translation_valid(self, original, translated):
        """验证翻译结果是否有效"""
        if not translated or not translated.strip():
            return False
        
        # 检查是否返回了原文（翻译失败的常见情况）
        if translated.strip() == original.strip():
            return False
        
        # 检查是否包含中文字符
        has_chinese = any('\u4e00' <= char <= '\u9fff' for char in translated)
        if not has_chinese:
            return False
        
        # 检查长度是否合理（翻译后通常长度会改变）
        length_ratio = len(translated) / len(original) if original else 0
        if length_ratio < 0.3 or length_ratio > 3:  # 长度变化过大可能有问题
            self.logger.warning(f"Translation length ratio suspicious: {length_ratio}")
        
        return True

    def generate_podcast_pdf(self, bilingual_transcript_path, output_pdf_path):
        """使用统一的PDF生成器生成双语PDF文档"""
        try:
            from core.pdf_generator import PodcastPDFGenerator
            
            # 读取双语内容并转换为PDF生成器所需的格式
            with open(bilingual_transcript_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            self.logger.info(f"Reading bilingual content, length: {len(content)}")
            self.logger.info(f"First 300 chars: {content[:300]}")
            
            # 解析内容为条目列表
            transcript_entries = []
            sections = content.split('---')
            
            self.logger.info(f"Found {len(sections)} sections in bilingual content")
            
            for i, section in enumerate(sections):
                section = section.strip()
                if not section:
                    continue
                    
                self.logger.info(f"Processing section {i}: {section[:100]}...")
                
                lines = section.split('\n')
                original_text = ""
                chinese_text = ""
                
                current_mode = None
                for line in lines:
                    line = line.strip()
                    if line == "【原文】":
                        current_mode = "original"
                        self.logger.info("Found original text marker")
                    elif line == "【中文】":
                        current_mode = "chinese"
                        self.logger.info("Found Chinese text marker")
                    elif line and current_mode == "original":
                        original_text += line + " "
                    elif line and current_mode == "chinese":
                        chinese_text += line + " "
                
                if original_text and chinese_text:
                    self.logger.info(f"Entry {len(transcript_entries)}: Original={original_text[:50]}..., Chinese={chinese_text[:50]}...")
                    transcript_entries.append({
                        'original': original_text.strip(),
                        'translation': chinese_text.strip()
                    })
                elif original_text:
                    self.logger.warning(f"Found original text but no Chinese translation for section {i}")
                else:
                    self.logger.warning(f"No valid content found in section {i}")
            
            self.logger.info(f"Total transcript entries created: {len(transcript_entries)}")
            
            # 使用统一的PDF生成器
            output_dir = os.path.dirname(output_pdf_path)
            original_filename = os.path.basename(self.audio_path)
            
            generator = PodcastPDFGenerator(output_dir)
            generated_pdf_path = generator.generate_pdf(
                transcript_entries, 
                original_filename, 
                self.engine
            )
            
            self.logger.info(f"PDF generated successfully: {generated_pdf_path}")
            
        except Exception as e:
            self.logger.error(f"PDF generation failed: {str(e)}")
            raise
