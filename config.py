import os
import json
import platform
import subprocess

# Default values
OPENAI_BASE_URL = "https://api.openai.com"  # 默认 OpenAI 平台
OPENAI_API_KEY = ""
OPENAI_MODEL = "gpt-4.1-nano"

# 批处理参数默认值
DEFAULT_MAX_CHARS_PER_BATCH = 1200
DEFAULT_MAX_ENTRIES_PER_BATCH = 100

# 多进程配置默认值
def _get_default_max_processes():
    """根据系统动态获取默认最大进程数"""
    try:
        if platform.system() == 'Darwin':  # macOS
            # 检测是否是Apple Silicon
            result = subprocess.run(['sysctl', '-n', 'hw.optional.arm64'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout.strip() == '1':
                return 4  # Apple Silicon 可以处理更多并发
            else:
                return 2  # Intel Mac
        else:
            return 1  # 其他系统保守一些
    except Exception:
        return 1  # 默认值

def get_dynamic_max_processes(task_count):
    """根据实际任务数量动态调整最大进程数，避免不必要的内存分配"""
    if task_count <= 0:
        return 1
    
    # 获取配置的最大进程数作为上限
    max_allowed = MAX_PROCESSES
    
    # 根据任务数量动态调整，但不超过配置的最大值
    if task_count == 1:
        return 1  # 单任务不需要多进程
    elif task_count == 2:
        return min(2, max_allowed)
    elif task_count <= 4:
        return min(task_count, max_allowed)
    else:
        # 多任务时使用配置的最大值，但考虑内存限制
        try:
            if platform.system() == 'Darwin':  # macOS
                # 检测是否是Apple Silicon，并根据内存情况调整
                result = subprocess.run(['sysctl', '-n', 'hw.optional.arm64'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0 and result.stdout.strip() == '1':
                    # Apple Silicon - 检查内存
                    try:
                        mem_result = subprocess.run(['sysctl', '-n', 'hw.memsize'], 
                                                  capture_output=True, text=True, timeout=5)
                        if mem_result.returncode == 0:
                            mem_bytes = int(mem_result.stdout.strip())
                            mem_gb = mem_bytes / (1024**3)
                            
                            if mem_gb >= 32:  # 32GB+ 内存
                                return min(max_allowed, task_count)
                            elif mem_gb >= 16:  # 16GB+ 内存
                                return min(max_allowed, 3)
                            else:  # 16GB 以下内存
                                return min(max_allowed, 2)
                    except Exception:
                        pass
                return min(max_allowed, 2)  # Intel Mac 保守一些
            else:
                return min(max_allowed, 2)  # 其他系统保守一些
        except Exception:
            return min(max_allowed, task_count)

DEFAULT_MAX_PROCESSES = _get_default_max_processes()

# API重试配置默认值
DEFAULT_MAX_RETRIES = 3  # 最大重试次数
DEFAULT_RETRY_BASE_DELAY = 1.0  # 基础延迟时间（秒）
DEFAULT_RETRY_MAX_DELAY = 60.0  # 最大延迟时间（秒）
DEFAULT_ENABLE_GOOGLE_FALLBACK = True  # 是否启用 Google 翻译降级

# 视频处理配置默认值
DEFAULT_SKIP_SUBTITLE_BURNING = False  # 是否跳过字幕烧录到视频
DEFAULT_SKIP_TRANSLATION = False  # 是否跳过字幕翻译（只导出 _en.txt），默认勾选

# 当前API重试参数，会被load_config修改
MAX_RETRIES = DEFAULT_MAX_RETRIES
RETRY_BASE_DELAY = DEFAULT_RETRY_BASE_DELAY  
RETRY_MAX_DELAY = DEFAULT_RETRY_MAX_DELAY
ENABLE_GOOGLE_FALLBACK = DEFAULT_ENABLE_GOOGLE_FALLBACK

# 当前视频处理参数，会被load_config修改
SKIP_SUBTITLE_BURNING = DEFAULT_SKIP_SUBTITLE_BURNING
SKIP_TRANSLATION = DEFAULT_SKIP_TRANSLATION

# 当前批处理参数，会被load_config修改
OPENAI_MAX_CHARS_PER_BATCH = DEFAULT_MAX_CHARS_PER_BATCH
OPENAI_MAX_ENTRIES_PER_BATCH = DEFAULT_MAX_ENTRIES_PER_BATCH

# 当前多进程参数，会被load_config修改
MAX_PROCESSES = DEFAULT_MAX_PROCESSES

# 原始默认prompt，不会被load_config修改
DEFAULT_CUSTOM_PROMPT = """You are a professional Chinese native translator who needs to fluently translate text into Chinese.

## Translation Rules
1. Output only the translated content, without explanations or additional content (such as "Here's the translation:" or "Translation as follows:")
2. The returned translation must maintain exactly the same number of paragraphs and format as the original text
3. For content that should not be translated (such as proper nouns, code, etc.), keep the original text.
4. If input contains %%, use %% in your output, if input has no %%, don't use %% in your output

## OUTPUT FORMAT:
- **Single paragraph input** → Output translation directly (no separators, no extra text)
- **Multi-paragraph input** → Use %% as paragraph separator between translations"""

# 当前使用的prompt，会被load_config修改
OPENAI_CUSTOM_PROMPT = DEFAULT_CUSTOM_PROMPT

# Path to the config file
CONFIG_DIR = os.path.expanduser("~/Library/Application Support/videoCaptioner")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def load_config():
    """Load configuration from file"""
    global OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL, OPENAI_CUSTOM_PROMPT
    global OPENAI_MAX_CHARS_PER_BATCH, OPENAI_MAX_ENTRIES_PER_BATCH, MAX_PROCESSES
    global MAX_RETRIES, RETRY_BASE_DELAY, RETRY_MAX_DELAY, ENABLE_GOOGLE_FALLBACK
    global SKIP_SUBTITLE_BURNING, SKIP_TRANSLATION

    # Create config directory if it doesn't exist
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

    # Load config if file exists
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                OPENAI_BASE_URL = config.get("base_url", "https://api.openai.com")
                OPENAI_API_KEY = config.get("api_key", "")
                OPENAI_MODEL = config.get("model", "gpt-4.1-nano")
                OPENAI_CUSTOM_PROMPT = config.get("custom_prompt", DEFAULT_CUSTOM_PROMPT)
                OPENAI_MAX_CHARS_PER_BATCH = config.get("max_chars_per_batch", DEFAULT_MAX_CHARS_PER_BATCH)
                OPENAI_MAX_ENTRIES_PER_BATCH = config.get("max_entries_per_batch", DEFAULT_MAX_ENTRIES_PER_BATCH)
                MAX_PROCESSES = config.get("max_processes", DEFAULT_MAX_PROCESSES)
                # 新增重试配置
                MAX_RETRIES = config.get("max_retries", DEFAULT_MAX_RETRIES)
                RETRY_BASE_DELAY = config.get("retry_base_delay", DEFAULT_RETRY_BASE_DELAY)
                RETRY_MAX_DELAY = config.get("retry_max_delay", DEFAULT_RETRY_MAX_DELAY)
                ENABLE_GOOGLE_FALLBACK = config.get("enable_google_fallback", DEFAULT_ENABLE_GOOGLE_FALLBACK)
                # 新增视频处理配置
                SKIP_SUBTITLE_BURNING = config.get("skip_subtitle_burning", DEFAULT_SKIP_SUBTITLE_BURNING)
                SKIP_TRANSLATION = config.get("skip_translation", DEFAULT_SKIP_TRANSLATION)
        except Exception as e:
            print(f"Error loading config: {e}")


def save_config(base_url, api_key, model=None, custom_prompt=None, max_chars_per_batch=None, max_entries_per_batch=None, max_processes=None, max_retries=None, retry_base_delay=None, retry_max_delay=None, enable_google_fallback=None, skip_subtitle_burning=None, skip_translation=None):
    """Save configuration to file"""
    global OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL, OPENAI_CUSTOM_PROMPT
    global OPENAI_MAX_CHARS_PER_BATCH, OPENAI_MAX_ENTRIES_PER_BATCH, MAX_PROCESSES
    global MAX_RETRIES, RETRY_BASE_DELAY, RETRY_MAX_DELAY, ENABLE_GOOGLE_FALLBACK
    global SKIP_SUBTITLE_BURNING, SKIP_TRANSLATION

    # Create config directory if it doesn't exist
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

    try:
        config = {
            "base_url": base_url,
            "api_key": api_key,
            "model": model if model is not None else "gpt-4.1-nano",
            "custom_prompt": custom_prompt if custom_prompt is not None else DEFAULT_CUSTOM_PROMPT,
            "max_chars_per_batch": max_chars_per_batch if max_chars_per_batch is not None else DEFAULT_MAX_CHARS_PER_BATCH,
            "max_entries_per_batch": max_entries_per_batch if max_entries_per_batch is not None else DEFAULT_MAX_ENTRIES_PER_BATCH,
            "max_processes": max_processes if max_processes is not None else DEFAULT_MAX_PROCESSES,
            # 新增重试配置
            "max_retries": max_retries if max_retries is not None else DEFAULT_MAX_RETRIES,
            "retry_base_delay": retry_base_delay if retry_base_delay is not None else DEFAULT_RETRY_BASE_DELAY,
            "retry_max_delay": retry_max_delay if retry_max_delay is not None else DEFAULT_RETRY_MAX_DELAY,
            "enable_google_fallback": enable_google_fallback if enable_google_fallback is not None else DEFAULT_ENABLE_GOOGLE_FALLBACK,
            # 新增视频处理配置
            "skip_subtitle_burning": skip_subtitle_burning if skip_subtitle_burning is not None else DEFAULT_SKIP_SUBTITLE_BURNING,
            "skip_translation": skip_translation if skip_translation is not None else DEFAULT_SKIP_TRANSLATION,
        }

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        # Update global variables
        OPENAI_BASE_URL = base_url
        OPENAI_API_KEY = api_key
        OPENAI_MODEL = model if model is not None else "gpt-4.1-nano"
        OPENAI_CUSTOM_PROMPT = custom_prompt if custom_prompt is not None else DEFAULT_CUSTOM_PROMPT
        OPENAI_MAX_CHARS_PER_BATCH = max_chars_per_batch if max_chars_per_batch is not None else DEFAULT_MAX_CHARS_PER_BATCH
        OPENAI_MAX_ENTRIES_PER_BATCH = max_entries_per_batch if max_entries_per_batch is not None else DEFAULT_MAX_ENTRIES_PER_BATCH
        MAX_PROCESSES = max_processes if max_processes is not None else DEFAULT_MAX_PROCESSES
        # 更新重试配置
        MAX_RETRIES = max_retries if max_retries is not None else DEFAULT_MAX_RETRIES
        RETRY_BASE_DELAY = retry_base_delay if retry_base_delay is not None else DEFAULT_RETRY_BASE_DELAY
        RETRY_MAX_DELAY = retry_max_delay if retry_max_delay is not None else DEFAULT_RETRY_MAX_DELAY
        ENABLE_GOOGLE_FALLBACK = enable_google_fallback if enable_google_fallback is not None else DEFAULT_ENABLE_GOOGLE_FALLBACK
        # 更新视频处理配置
        SKIP_SUBTITLE_BURNING = skip_subtitle_burning if skip_subtitle_burning is not None else DEFAULT_SKIP_SUBTITLE_BURNING
        SKIP_TRANSLATION = skip_translation if skip_translation is not None else DEFAULT_SKIP_TRANSLATION

        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


# Load config on import
load_config()
