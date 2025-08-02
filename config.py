import os
import json

# Default values
OPENAI_BASE_URL = "https://api.openai.com"  # 默认 OpenAI 平台
OPENAI_API_KEY = ""
OPENAI_MODEL = "gpt-4.1-nano"

# 批处理参数默认值
DEFAULT_MAX_CHARS_PER_BATCH = 3600
DEFAULT_MAX_ENTRIES_PER_BATCH = 10

# 当前批处理参数，会被load_config修改
OPENAI_MAX_CHARS_PER_BATCH = DEFAULT_MAX_CHARS_PER_BATCH
OPENAI_MAX_ENTRIES_PER_BATCH = DEFAULT_MAX_ENTRIES_PER_BATCH

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
    global OPENAI_MAX_CHARS_PER_BATCH, OPENAI_MAX_ENTRIES_PER_BATCH

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
        except Exception as e:
            print(f"Error loading config: {e}")


def save_config(base_url, api_key, model=None, custom_prompt=None, max_chars_per_batch=None, max_entries_per_batch=None):
    """Save configuration to file"""
    global OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL, OPENAI_CUSTOM_PROMPT
    global OPENAI_MAX_CHARS_PER_BATCH, OPENAI_MAX_ENTRIES_PER_BATCH
    
    # Create config directory if it doesn't exist
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

    # Save config
    try:
        config = {
            "base_url": base_url, 
            "api_key": api_key,
            "model": model if model is not None else "gpt-4.1-nano",
            "custom_prompt": custom_prompt if custom_prompt is not None else DEFAULT_CUSTOM_PROMPT,
            "max_chars_per_batch": max_chars_per_batch if max_chars_per_batch is not None else DEFAULT_MAX_CHARS_PER_BATCH,
            "max_entries_per_batch": max_entries_per_batch if max_entries_per_batch is not None else DEFAULT_MAX_ENTRIES_PER_BATCH
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

        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


# Load config on import
load_config()
