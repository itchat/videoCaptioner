import os
import json

# Default values
OPENAI_BASE_URL = ""
OPENAI_API_KEY = ""
OPENAI_MODEL = "gpt-4.1"
OPENAI_CUSTOM_PROMPT = """你是一位资深的专业翻译专家，精通中英文互译，遵循翻译的"信、达、雅"三大原则：

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

请将以下英文字幕翻译成中文："""

# Path to the config file
CONFIG_DIR = os.path.expanduser("~/Library/Application Support/videoCaptioner")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def load_config():
    """Load configuration from file"""
    global OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL, OPENAI_CUSTOM_PROMPT

    # Create config directory if it doesn't exist
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

    # Load config if file exists
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                OPENAI_BASE_URL = config.get("base_url", "")
                OPENAI_API_KEY = config.get("api_key", "")
                OPENAI_MODEL = config.get("model", "gpt-4.1")
                OPENAI_CUSTOM_PROMPT = config.get("custom_prompt", OPENAI_CUSTOM_PROMPT)
        except Exception as e:
            print(f"Error loading config: {e}")


def save_config(base_url, api_key, model=None, custom_prompt=None):
    """Save configuration to file"""
    global OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL, OPENAI_CUSTOM_PROMPT
    
    # Create config directory if it doesn't exist
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

    # Save config
    try:
        config = {
            "base_url": base_url, 
            "api_key": api_key,
            "model": model if model is not None else "gpt-4.1",
            "custom_prompt": custom_prompt if custom_prompt is not None else OPENAI_CUSTOM_PROMPT
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

        # Update global variables
        OPENAI_BASE_URL = base_url
        OPENAI_API_KEY = api_key
        OPENAI_MODEL = model if model is not None else "gpt-4.1"
        OPENAI_CUSTOM_PROMPT = custom_prompt if custom_prompt is not None else OPENAI_CUSTOM_PROMPT

        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


# Load config on import
load_config()
