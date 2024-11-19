import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from PyQt5.QtCore import QRunnable
import os
import subprocess
from faster_whisper import WhisperModel
from deep_translator import GoogleTranslator
from core.worker_signals import WorkerSignals
from utils.logger import VideoLogger


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

    def report_progress(self, progress):
        """报告进度"""
        self.signals.file_progress.emit(self.base_name, progress)
        if self.progress_callback:
            self.progress_callback(self.base_name, progress)

    def report_status(self, status):
        """报告状态"""
        self.signals.status.emit(self.base_name, status)
        if self.status_callback:
            self.status_callback(self.base_name, status)

    def run(self):
        try:
            self.logger.info(f"开始处理视频: {self.base_name}")
            cache_paths = self.get_cache_paths()

            # 提取音频 (0-20%)
            self.report_status("正在提取音频...")
            self.report_progress(0)
            self.extract_audio(cache_paths['audio'])
            self.logger.info("音频提取完成")
            self.report_progress(20)

            # 生成字幕 (20-40%)
            self.report_status("正在识别语音...")
            self.generate_subtitles(cache_paths['audio'], cache_paths['srt'])
            self.logger.info("字幕生成完成")
            self.report_progress(40)

            # 翻译字幕 (40-70%)
            self.report_status("正在翻译字幕...")
            with open(cache_paths['srt'], "r", encoding="utf-8") as f:
                lines = f.readlines()
            translated_content = self.translate_subtitles(lines)
            with open(cache_paths['bilingual_srt'], "w", encoding="utf-8") as f:
                f.write(translated_content)
            self.logger.info("字幕翻译完成")
            self.report_progress(70)

            # 合成视频 (70-100%)
            self.report_status("正在合成视频...")
            self.burn_subtitles(cache_paths['bilingual_srt'], cache_paths['output_video'])
            self.logger.info("视频合成完成")
            self.report_progress(100)
            self.report_status("处理完成!")

            # 发送完成信号
            self.signals.finished.emit()

        except Exception as e:
            error_msg = f"处理失败: {str(e)}"
            self.logger.error(error_msg)
            self.signals.error.emit(f"处理视频 {self.base_name} 时发生错误: {str(e)}")
            self.signals.status.emit(self.base_name, error_msg)
            # 发生错误时也要发送完成信号
            self.signals.finished.emit()

    def get_cache_paths(self):
        base_name = os.path.splitext(self.base_name)[0]
        return {
            'audio': os.path.join(self.cache_dir, f"{base_name}_audio.wav"),
            'srt': os.path.join(self.cache_dir, f"{base_name}_output.srt"),
            'bilingual_srt': os.path.join(self.cache_dir, f"{base_name}_bilingual.srt"),
            'output_video': os.path.join(os.path.dirname(self.video_path),
                                         f"{base_name}_subtitled{os.path.splitext(self.video_path)[1]}")
        }

    @staticmethod
    def get_ffmpeg_path():
        # 可能的 FFmpeg 路径
        possible_paths = [
            '/opt/homebrew/bin/ffmpeg',  # MacOS Homebrew
            '/usr/local/bin/ffmpeg',  # 常见 Linux/MacOS 路径
            '/usr/bin/ffmpeg',  # 另一个常见路径
        ]

        for path in possible_paths:
            if os.path.exists(path):
                return path
        return None

    def extract_audio(self, audio_path):
        ffmpeg_path = self.get_ffmpeg_path()
        if not ffmpeg_path:
            raise FileNotFoundError("Could not find ffmpeg. Please install it first.")
        subprocess.run([
            ffmpeg_path,
            "-hwaccel", "videotoolbox",
            "-i", self.video_path,
            "-q:a", "0",
            "-map", "a",
            audio_path,
            "-y"
        ])

    def generate_subtitles(self, audio_path, srt_path):
        model = WhisperModel("base")
        segments, _ = model.transcribe(audio_path)

        with open(srt_path, "w", encoding="utf-8") as f:
            for i, segment in enumerate(segments):
                start = self.format_time(segment.start)
                end = self.format_time(segment.end)
                f.write(f"{i + 1}\n{start} --> {end}\n{segment.text}\n\n")

    @staticmethod
    def format_time(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = seconds % 60
        return f"{hours:02}:{minutes:02}:{seconds:06.3f}".replace(".", ",")

    def translate_subtitles(self, lines):
        try:
            # 将普通字幕行转换为结构化数据
            entries = []
            current_id = 1
            current_timestamp = ""
            current_text = []

            for line in lines:
                line = line.strip()
                if not line:
                    if current_text:
                        entries.append({
                            'id': current_id,
                            'timestamp': current_timestamp,
                            'text': '\n'.join(current_text),
                            'translated': False
                        })
                        current_text = []
                    continue
                if line.isdigit():
                    current_id = int(line)
                elif '-->' in line:
                    current_timestamp = line
                else:
                    current_text.append(line)

            if current_text:
                entries.append({
                    'id': current_id,
                    'timestamp': current_timestamp,
                    'text': '\n'.join(current_text),
                    'translated': False
                })

            # 使用线程池进行并行翻译
            translated_entries = []
            with ThreadPoolExecutor(max_workers=10) as executor:
                future_to_entry = {
                    executor.submit(self._translate_entry, entry): entry
                    for entry in entries
                }

                # 收集翻译结果
                for future in as_completed(future_to_entry):
                    entry = future_to_entry[future]
                    try:
                        translated_text = future.result()
                        translated_entries.append({
                            'id': entry['id'],
                            'timestamp': entry['timestamp'],
                            'text': f"{entry['text']}\n{translated_text}"
                        })

                        # 更新进度
                        progress = 40 + len(translated_entries) / len(entries) * 30
                        self.signals.file_progress.emit(self.base_name, int(progress))
                    except Exception as e:
                        self.signals.error.emit(f"字幕 {entry['id']} 翻译失败: {str(e)}")
                        raise

            # 按ID排序确保字幕顺序正确
            translated_entries.sort(key=lambda x: x['id'])

            # 构建最终的字幕内容
            translated_content = ""
            for entry in translated_entries:
                translated_content += f"{entry['id']}\n{entry['timestamp']}\n{entry['text']}\n\n"

            return translated_content

        except Exception as e:
            self.signals.error.emit(f"翻译过程出错: {str(e)}")
            raise

    def _translate_entry(self, entry):
        """单个字幕条目的翻译处理"""
        max_attempts = 3
        attempt = 1
        while attempt <= max_attempts:
            try:
                if self.engine == "OpenAI 翻译":
                    return self._translate_with_openai(entry)
                else:  # Google翻译
                    return self._translate_with_google(entry)
            except Exception as e:
                if attempt == max_attempts:
                    raise
                attempt += 1
                time.sleep(1)

    def _translate_with_openai(self, entry):
        """使用OpenAI进行单条字幕翻译"""
        headers = {
            "Authorization": f"Bearer {self.api_settings['api_key']}",
            "Content-Type": "application/json"
        }

        data = {
            "model": "gpt-3.5-turbo",
            "messages": [
                {"role": "system", "content": """You are a professional, authentic translation engine. 
Translate the following English subtitle to Chinese:
1. Only return the Chinese translation, no English text
2. Maintain the natural and accurate translation
Return the translated text directly without any explanations or additional information."""},
                {"role": "user", "content": f"""{entry['text']}"""}
            ],
            "temperature": 0.7
        }

        response = requests.post(
            f"{self.api_settings['base_url']}/v1/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content'].strip()
        else:
            raise Exception(f"OpenAI API 返回错误: {response.status_code}")

    @staticmethod
    def _translate_with_google(entry):
        """使用 Deep Translator 的 Google Translate 接口翻译"""
        translated_text = GoogleTranslator(source='auto', target='zh-CN').translate(entry['text'].strip())
        print(translated_text)
        return translated_text

    def burn_subtitles(self, subtitle_path, output_path):
        ffmpeg_path = self.get_ffmpeg_path()
        subprocess.run([
            ffmpeg_path,
            "-hwaccel", "videotoolbox",
            "-i", self.video_path,
            "-vf", f"subtitles='{subtitle_path}'",
            "-c:v", "h264_videotoolbox",
            "-c:a", "copy",
            output_path
        ])


