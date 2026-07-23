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
        
        # Wake Words & Engine settings
        self.wake_words = ["jarvis", "hey jarvis", "hello jarvis"]
        self.wakeword_engine = "mock"       # Options: "mock", "openwakeword", "porcupine"
        self.wakeword_sensitivity = 0.5
        self.porcupine_api_key = ""         # Picovoice Porcupine API Key
        self.openwakeword_model_path = ""   # Custom model path (optional)
        
        # Audio Settings
        self.audio_sample_rate = 16000
        self.audio_channels = 1
        self.audio_input_device = None     # None represents default input device
        self.vad_threshold = 0.05          # VAD energy threshold (float 0.0 to 1.0)
        self.clap_threshold = 0.6          # Peak amplitude threshold (float 0.0 to 1.0)
        self.clap_duration_limit = 0.15     # Max duration in seconds to count as a clap (to ignore speech)
        self.double_clap_max_gap = 0.6     # Max time in seconds between two claps for a double-clap
        self.double_clap_min_gap = 0.15    # Min time in seconds between two claps to filter bouncing
        
        # UI Settings
        self.ui_title = "JARVIS v1.0 - Foundation"
        self.ui_width = 900
        self.ui_height = 650
        self.ui_theme = "dark"
        self.ui_always_on_top = True
        
        # Model Settings
        self.model_whisper_size = "small"
        self.model_tts_voice = "en-US-GuyNeural"
        
        # Database Paths
        self.db_conversations = str(MEMORY_DIR / "conversations.db")
        self.db_tasks = str(MEMORY_DIR / "tasks.db")
        
        # Logging Settings
        self.log_file = str(LOGS_DIR / "jarvis.log")
        self.log_level = "DEBUG"

        # Gemini API settings
        self.gemini_api_key = ""
        self.gemini_temperature = 0.7
        self.gemini_max_tokens = 150
        
        # Whisper model size and device
        self.whisper_model_size = "small"
        self.whisper_device = "cpu"
        
        # TTS voice and rate
        self.tts_voice = "en-US-GuyNeural"
        self.tts_rate = "+0%"

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
