import os
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Base Directories
BASE_DIR = Path(__file__).parent.resolve()
LOGS_DIR = BASE_DIR / "logs"
MEMORY_DIR = BASE_DIR / "memory"

# Ensure crucial directories exist on module import
LOGS_DIR.mkdir(exist_ok=True)
MEMORY_DIR.mkdir(exist_ok=True)

class Config:
    def __init__(self, config_path: str = None):
        if config_path is None:
            self.config_path = BASE_DIR / "config.json"
        else:
            self.config_path = Path(config_path)

        # ==========================================
        # DEFAULT CONFIGURATION SETTINGS
        # ==========================================
        
        # Assistant & Identity Settings
        self.assistant_name = "Jarvis"
        self.owner_name = "Active Gamer"
        self.version = "1.1"

        # Wake Words & Engine settings
        self.wake_words = [
            "jarvis", "hey jarvis", "hello jarvis", "hi jarvis", 
            "good morning jarvis", "good evening jarvis", "good afternoon jarvis", 
            "namaste jarvis", "yo jarvis", "hey buddy", "goliya"
        ]
        self.wakeword_engine = "mock"       # Options: "mock", "openwakeword", "porcupine"
        self.wakeword_sensitivity = 0.5
        self.porcupine_api_key = ""         # Picovoice Porcupine API Key
        self.openwakeword_model_path = ""   # Custom model path (optional)
        
        # Audio Settings
        self.audio_sample_rate = 16000
        self.audio_channels = 1
        self.audio_input_device = None     # None represents default input device
        self.microphone_device = os.environ.get("MICROPHONE_DEVICE", None)
        self.debug_audio = os.environ.get("JARVIS_DEBUG_AUDIO", os.environ.get("DEBUG_AUDIO", "false")).lower() in ["true", "1", "yes"]
        self.vad_threshold = 0.015         # VAD energy threshold (float 0.0 to 1.0)
        self.silence_duration = 0.8        # Seconds of silence to wait before finalizing speech (fast 800ms response)
        self.max_duration = 5.0            # Max recording duration cap in seconds
        
        # UI Settings
        self.ui_title = "JARVIS v1.1 - AI Desktop Assistant"
        self.ui_width = 900
        self.ui_height = 650
        self.ui_theme = "dark"
        self.ui_always_on_top = True
        
        # Model Settings
        self.model_whisper_size = "small"
        self.model_tts_voice = "en-US-GuyNeural"
        
        # Database & Configuration Paths
        self.db_conversations = str(MEMORY_DIR / "conversations.db")
        self.db_tasks = str(MEMORY_DIR / "tasks.db")
        self.links_path = str(BASE_DIR / "config" / "links.json")
        
        # Logging Settings
        self.log_file = str(LOGS_DIR / "jarvis.log")
        self.log_level = "DEBUG"

        # AI Provider Settings (Options: "none", "local", "openrouter", "cerebras", "gemini", "openai")
        self.ai_provider = "none"
        self.openrouter_api_key = ""
        self.cerebras_api_key = ""
        self.openai_api_key = ""
        self.gemini_api_key = ""
        self.gemini_temperature = 0.7
        self.gemini_max_tokens = 150
        
        # Whisper model size and device
        self.whisper_model_size = "small"
        self.whisper_device = "cpu"
        
        # TTS voice, rate, pitch, volume, provider
        self.tts_provider = "edge"  # Options: "edge", "pyttsx3", "gtts"
        self.tts_voice = "en-US-GuyNeural"
        self.tts_rate = "+15%"
        self.tts_pitch = "+0Hz"
        self.tts_volume = "+0%"
        self.tts_language = "en"

        # Load from config file if exists
        self.load()
        
        # Apply environment overrides
        self._apply_env_overrides()

    def load(self):
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, val in data.items():
                        if hasattr(self, key):
                            setattr(self, key, val)
            except Exception as e:
                print(f"[Config] Error loading config.json: {e}")

    def save(self):
        try:
            # Exclude config_path to avoid circular reference in json
            data = {k: v for k, v in self.__dict__.items() if k != 'config_path'}
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"[Config] Error saving config.json: {e}")

    def _apply_env_overrides(self):
        # Load .env file if present
        env_file = BASE_DIR / ".env"
        if env_file.exists():
            try:
                with open(env_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#') and '=' in line:
                            k, v = line.split('=', 1)
                            k, v = k.strip(), v.strip()
                            if k and v and k not in os.environ:
                                os.environ[k] = v
            except Exception as e:
                print(f"[Config] Error reading .env file: {e}")

        if "JARVIS_AI_PROVIDER" in os.environ and os.environ["JARVIS_AI_PROVIDER"]:
            self.ai_provider = os.environ["JARVIS_AI_PROVIDER"]
        if "AI_PROVIDER" in os.environ and os.environ["AI_PROVIDER"]:
            self.ai_provider = os.environ["AI_PROVIDER"]
        if "OPENROUTER_API_KEY" in os.environ and os.environ["OPENROUTER_API_KEY"]:
            self.openrouter_api_key = os.environ["OPENROUTER_API_KEY"]
        if "CEREBRAS_API_KEY" in os.environ and os.environ["CEREBRAS_API_KEY"]:
            self.cerebras_api_key = os.environ["CEREBRAS_API_KEY"]
        if "OPENAI_API_KEY" in os.environ and os.environ["OPENAI_API_KEY"]:
            self.openai_api_key = os.environ["OPENAI_API_KEY"]
        if "GEMINI_API_KEY" in os.environ and os.environ["GEMINI_API_KEY"]:
            self.gemini_api_key = os.environ["GEMINI_API_KEY"]
        if "PORCUPINE_API_KEY" in os.environ and os.environ["PORCUPINE_API_KEY"]:
            self.porcupine_api_key = os.environ["PORCUPINE_API_KEY"]
        if "JARVIS_WAKEWORD_ENGINE" in os.environ and os.environ["JARVIS_WAKEWORD_ENGINE"]:
            self.wakeword_engine = os.environ["JARVIS_WAKEWORD_ENGINE"]
        if "JARVIS_WHISPER_MODEL" in os.environ and os.environ["JARVIS_WHISPER_MODEL"]:
            self.whisper_model_size = os.environ["JARVIS_WHISPER_MODEL"]
            self.model_whisper_size = os.environ["JARVIS_WHISPER_MODEL"]
        if "JARVIS_TTS_VOICE" in os.environ and os.environ["JARVIS_TTS_VOICE"]:
            self.tts_voice = os.environ["JARVIS_TTS_VOICE"]
            self.model_tts_voice = os.environ["JARVIS_TTS_VOICE"]
        if "JARVIS_LOG_LEVEL" in os.environ:
            self.log_level = os.environ["JARVIS_LOG_LEVEL"]
        if "JARVIS_UI_WIDTH" in os.environ:
            try:
                self.ui_width = int(os.environ["JARVIS_UI_WIDTH"])
            except ValueError:
                pass
        if "JARVIS_WAKE_WORDS" in os.environ:
            try:
                self.wake_words = json.loads(os.environ["JARVIS_WAKE_WORDS"])
            except Exception:
                pass
        if "JARVIS_CLAP_THRESHOLD" in os.environ:
            try:
                self.clap_threshold = float(os.environ["JARVIS_CLAP_THRESHOLD"])
            except ValueError:
                pass

    @property
    def BASE_DIR(self):
        return BASE_DIR

    @property
    def LOGS_DIR(self):
        return LOGS_DIR

    @property
    def MEMORY_DIR(self):
        return MEMORY_DIR

    def setup_logging(self):
        """Sets up a robust centralized logging system."""
        numeric_level = getattr(logging, self.log_level.upper(), logging.INFO)
        
        # Reset current logging handlers
        root_logger = logging.getLogger()
        root_logger.setLevel(numeric_level)
        root_logger.handlers.clear()
        
        # Formatter including timestamp, level, logger name, thread and message
        formatter = logging.Formatter(
            fmt='%(asctime)s - [%(levelname)s] - %(name)s - [%(threadName)s] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Rotating File Handler (Max 5 MB, Backup Count 5)
        try:
            file_handler = RotatingFileHandler(
                self.log_file,
                maxBytes=5 * 1024 * 1024,
                backupCount=5,
                encoding='utf-8'
            )
            file_handler.setFormatter(formatter)
            file_handler.setLevel(numeric_level)
            root_logger.addHandler(file_handler)
        except Exception as e:
            print(f"[Config] Failed to create rotating log file handler: {e}")
            
        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(numeric_level)
        root_logger.addHandler(console_handler)

        logging.info("Centralized logging system initialized.")
        logging.info(f"Logging Level: {self.log_level} | Destination: {self.log_file}")

# Global configuration instance used across the system
config = Config()
config.setup_logging()
