import os
import json

# Default values
OPENAI_BASE_URL = ""
OPENAI_API_KEY = ""

# Path to the config file
CONFIG_DIR = os.path.expanduser("~/Library/Application Support/videoCaptioner")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")


def load_config():
    """Load configuration from file"""
    global OPENAI_BASE_URL, OPENAI_API_KEY

    # Create config directory if it doesn't exist
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

    # Load config if file exists
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                OPENAI_BASE_URL = config.get("base_url", "")
                OPENAI_API_KEY = config.get("api_key", "")
        except Exception as e:
            print(f"Error loading config: {e}")


def save_config(base_url, api_key):
    """Save configuration to file"""
    # Create config directory if it doesn't exist
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

    # Save config
    try:
        config = {"base_url": base_url, "api_key": api_key}
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f)

        # Update global variables
        global OPENAI_BASE_URL, OPENAI_API_KEY
        OPENAI_BASE_URL = base_url
        OPENAI_API_KEY = api_key

        return True
    except Exception as e:
        print(f"Error saving config: {e}")
        return False


# Load config on import
load_config()
