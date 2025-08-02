"""
语音识别模块 - 基于 Parakeet MLX
从 check.py 提取核心功能，去除 CLI 相关内容
"""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

from mlx.core import bfloat16, float32
from parakeet_mlx import AlignedResult, AlignedSentence, AlignedToken, from_pretrained

from utils.logger import VideoLogger


class SpeechRecognizer:
    """语音识别类，封装 Parakeet MLX 模型"""
    
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
        初始化语音识别器
        
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
        self.model_name = model_name
        self.fp32 = fp32
        self.local_attention = local_attention
        self.local_attention_context_size = local_attention_context_size
        self.logger = logger
        self.download_callback = download_callback
        self.progress_callback = progress_callback
        self.status_callback = status_callback
        self._model = None
        
    def _load_model(self):
        """加载模型"""
        if self._model is not None:
            return
            
        if self.logger:
            self.logger.info(f"Loading model: {self.model_name}")
            
        # 检查模型是否需要下载（简单方式：检查缓存目录）
        needs_download = self._check_if_model_needs_download()
        
        # 只有在需要下载时才通知UI显示下载对话框
        if needs_download and self.download_callback:
            self.download_callback(self.model_name)
            
        if needs_download and self.status_callback:
            self.status_callback("Initializing model download...")
        elif self.status_callback:
            self.status_callback("Loading cached model...")
            
        try:
            # Parakeet MLX 会自动下载模型，但没有进度回调
            # 我们提供一个简单的状态更新
            if needs_download and self.status_callback:
                self.status_callback(f"Downloading {self.model_name}...")
                
            self._model = from_pretrained(
                self.model_name, 
                dtype=bfloat16 if not self.fp32 else float32
            )
            
            if self.local_attention:
                self._model.encoder.set_attention_model(
                    "rel_pos_local_attn",
                    (self.local_attention_context_size, self.local_attention_context_size),
                )
                
            if self.logger:
                self.logger.info("Model loaded successfully")
                
            if self.status_callback:
                self.status_callback("Model loaded successfully!")
                    
            # 通知下载完成（如果是首次下载）
            if needs_download and self.progress_callback:
                self.progress_callback(100, 0, 0, 0)  # 100% 完成
                    
        except Exception as e:
            error_msg = f"Error loading model {self.model_name}: {e}"
            if self.logger:
                self.logger.error(error_msg)
            raise RuntimeError(error_msg)
    
    def _check_if_model_needs_download(self):
        """检查模型是否需要下载"""
        try:
            import os
            from huggingface_hub import hf_hub_download, try_to_load_from_cache
            
            # 检查Hugging Face缓存中是否存在模型文件
            # 这是一个简化的检查，实际的模型文件可能有多个
            try:
                # 尝试从缓存加载，如果不存在会返回None
                cached_file = try_to_load_from_cache(
                    repo_id=self.model_name,
                    filename="config.json"  # 检查配置文件
                )
                return cached_file is None
            except:
                # 如果检查失败，假设需要下载
                return True
        except ImportError:
            # 如果没有huggingface_hub，假设需要下载
            return True
    
    def transcribe(self, 
                   audio_path: str,
                   chunk_duration: Optional[float] = 120.0,
                   overlap_duration: float = 15.0,
                   progress_callback: Optional[Callable[[int, int], None]] = None) -> AlignedResult:
        """
        转录音频文件
        
        Args:
            audio_path: 音频文件路径
            chunk_duration: 分块时长（秒），None表示不分块
            overlap_duration: 重叠时长（秒）
            progress_callback: 进度回调函数 (current_chunk, total_chunks)
            
        Returns:
            AlignedResult: 转录结果
        """
        self._load_model()
        
        if self.logger:
            self.logger.info(f"Starting transcription of: {audio_path}")
            
        try:
            result = self._model.transcribe(
                audio_path,
                dtype=bfloat16 if not self.fp32 else float32,
                chunk_duration=chunk_duration,
                overlap_duration=overlap_duration,
                chunk_callback=progress_callback
            )
            
            if self.logger:
                self.logger.info(f"Transcription completed for: {audio_path}")
                
            return result
            
        except Exception as e:
            error_msg = f"Error transcribing file {audio_path}: {e}"
            if self.logger:
                self.logger.error(error_msg)
            raise RuntimeError(error_msg)


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
        srt_content = []
        entry_index = 1
        
        if highlight_words:
            for sentence in result.sentences:
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
            "duration": round(token.duration, 3),
        }

    @staticmethod
    def _aligned_sentence_to_dict(sentence: AlignedSentence) -> Dict[str, Any]:
        """将对齐的句子转换为字典"""
        return {
            "text": sentence.text,
            "start": round(sentence.start, 3),
            "end": round(sentence.end, 3),
            "duration": round(sentence.duration, 3),
            "tokens": [SubtitleFormatter._aligned_token_to_dict(token) for token in sentence.tokens],
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
        output_dict = {
            "text": result.text,
            "sentences": [
                SubtitleFormatter._aligned_sentence_to_dict(sentence) 
                for sentence in result.sentences
            ],
        }
        return json.dumps(output_dict, indent=2, ensure_ascii=False)
