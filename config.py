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
        self.assistant_name = "Santra"
        self.full_name = "Santra AI Desktop Assistant"
        self.creator_name = ""  # Configurable; if unset, system reports not configured
        self.project_purpose = "A native desktop AI assistant engineered for local computer control, system automation, and intelligent interaction."
        self.personality_tone = "normal"  # Options: "normal", "professional", "funny", "dramatic"
        self.response_length = "normal"   # Options: "concise", "normal", "detailed"
        self.humor_enabled = True         # Boolean humor preference
        self.owner_name = "Active Gamer"
        self.version = "1.1"

        # Wake Words & Engine settings
        self.wake_words = [
            "santra", "hey santra", "hello santra", "hi santra", 
            "good morning santra", "good evening santra", "good afternoon santra", 
            "namaste santra", "yo santra", "hey buddy", "jarvis", "hey jarvis", "goliya"
        ]
        self.wakeword_engine = "santra"   # Options: "santra", "openwakeword", "porcupine", "mock"
        self.wakeword_sensitivity = 0.5
        self.porcupine_api_key = ""         # Picovoice Porcupine API Key
        self.openwakeword_model_path = ""   # Custom model path (optional)
        
        # Audio Settings
        self.audio_sample_rate = 16000
        self.audio_channels = 1
        self.audio_input_device = None     # None represents default input device
        self.audio_output_device = None    # None represents system default output device
        self.microphone_device = os.environ.get("MICROPHONE_DEVICE", None)
        self.debug_audio = os.environ.get("JARVIS_DEBUG_AUDIO", os.environ.get("DEBUG_AUDIO", "false")).lower() in ["true", "1", "yes"]
        self.vad_threshold = 0.015         # VAD energy threshold (float 0.0 to 1.0)
        self.silence_duration = 0.8        # Seconds of silence to wait before finalizing speech (fast 800ms response)
        self.max_duration = 5.0            # Max recording duration cap in seconds
        
        # UI Settings
        self.ui_title = "SANTRA v1.1 - AI Desktop Assistant"
        self.ui_width = 900
        self.ui_height = 650
        self.ui_theme = "dark"
        self.ui_always_on_top = True
        
        # Model Settings
        self.model_whisper_size = "small"
        self.model_tts_voice = "en-GB-RyanNeural"
        
        # Database & Configuration Paths
        self.db_conversations = str(MEMORY_DIR / "conversations.db")
        self.db_tasks = str(MEMORY_DIR / "tasks.db")
        self.persistent_memory_enabled = True
        self.links_path = str(BASE_DIR / "config" / "links.json")
        
        # Logging Settings
        self.log_file = str(LOGS_DIR / "jarvis.log")
        self.log_level = "DEBUG"

        # AI Provider Settings (Options: "none", "local", "openrouter", "cerebras", "gemini", "openai", "nvidia")
        self.ai_provider = "none"
        self.openrouter_api_key = ""
        self.cerebras_api_key = ""
        self.openai_api_key = ""
        self.gemini_api_key = ""
        self.gemini_temperature = 0.7
        self.gemini_max_tokens = 150

        # NVIDIA Nemotron Settings
        self.nvidia_api_key = ""
        self.nvidia_base_url = "https://integrate.api.nvidia.com/v1"
        self.nvidia_model = "nvidia/nemotron-3.5-super-vl-120b-a12b"
        self.nvidia_temperature = 0.6
        self.nvidia_max_tokens = 2048
        self.nvidia_timeout_sec = 25.0
        self.nvidia_max_retries = 3
        
        # Whisper model size, beam size, and device
        self.whisper_model_size = "base"
        self.whisper_beam_size = 1
        self.whisper_device = "cpu"
        
        # TTS voice, rate, pitch, volume, provider, cloud timeout, and cache
        self.tts_provider = "edge"  # Options: "edge", "sapi", "windows", "pyttsx3", "gtts"
        self.tts_voice = "en-GB-RyanNeural"
        self.tts_rate = "+0%"
        self.tts_pitch = "-2Hz"
        self.tts_volume = "-20%"
        self.tts_language = "en"
        self.tts_cloud_timeout_ms = 6500
        self.tts_cache_enabled = True
        self.playback_volume = 0.70
        self.sapi_volume = 70
        self.sapi_voice = "Zira"

        # Observability & Tracing Settings
        self.tracing_enabled = True
        self.whisper_threads = 4

        # Load from config file if exists
        self.load()
        
        # Apply environment overrides
        self._apply_env_overrides()

    def load(self):
        if self.config_path.exists() and self.config_path.stat().st_size > 0:
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for key, val in data.items():
                        if hasattr(self, key):
                            setattr(self, key, val)
                # Backward-compatibility migration: Ensure Santra is canonical
                if getattr(self, "assistant_name", "").lower() in ("jarvis", "goliya", ""):
                    self.assistant_name = "Santra"
                    self.full_name = "Santra AI Desktop Assistant"
                if not getattr(self, "ui_title", "") or "jarvis" in self.ui_title.lower():
                    self.ui_title = "SANTRA v1.1 - AI Desktop Assistant"
                current_words = [w.lower() for w in getattr(self, "wake_words", [])]
                if "santra" not in current_words:
                    santra_phrases = ["santra", "hey santra", "hello santra", "hi santra"]
                    self.wake_words = santra_phrases + [w for w in getattr(self, "wake_words", []) if w not in santra_phrases]
                if getattr(self, "wakeword_engine", "") == "openwakeword" and not getattr(self, "openwakeword_model_path", ""):
                    # Default to native santra engine when model path not set
                    self.wakeword_engine = "santra"
            except Exception as e:
                print(f"[Config] Error loading config.json: {e}")

    def save(self):
        try:
            # Exclude config_path to avoid circular reference in json
            # Sanitize credentials so API keys never get persisted into tracked config.json
            sensitive_keys = {
                'nvidia_api_key', 'openai_api_key', 'gemini_api_key',
                'openrouter_api_key', 'cerebras_api_key', 'porcupine_api_key'
            }
            data = {}
            for k, v in self.__dict__.items():
                if k == 'config_path':
                    continue
                if k in sensitive_keys:
                    data[k] = ""
                else:
                    data[k] = v
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
        if "NVIDIA_API_KEY" in os.environ and os.environ["NVIDIA_API_KEY"]:
            self.nvidia_api_key = os.environ["NVIDIA_API_KEY"]
            if self.ai_provider == "none":
                self.ai_provider = "nvidia"
        elif "JARVIS_NVIDIA_API_KEY" in os.environ and os.environ["JARVIS_NVIDIA_API_KEY"]:
            self.nvidia_api_key = os.environ["JARVIS_NVIDIA_API_KEY"]
            if self.ai_provider == "none":
                self.ai_provider = "nvidia"
        if "NVIDIA_BASE_URL" in os.environ and os.environ["NVIDIA_BASE_URL"]:
            self.nvidia_base_url = os.environ["NVIDIA_BASE_URL"]
        if "NVIDIA_MODEL" in os.environ and os.environ["NVIDIA_MODEL"]:
            self.nvidia_model = os.environ["NVIDIA_MODEL"]
        if "NVIDIA_TIMEOUT_SEC" in os.environ and os.environ["NVIDIA_TIMEOUT_SEC"]:
            try:
                self.nvidia_timeout_sec = float(os.environ["NVIDIA_TIMEOUT_SEC"])
            except ValueError:
                pass
        if "NVIDIA_MAX_RETRIES" in os.environ and os.environ["NVIDIA_MAX_RETRIES"]:
            try:
                self.nvidia_max_retries = int(os.environ["NVIDIA_MAX_RETRIES"])
            except ValueError:
                pass
        if "PORCUPINE_API_KEY" in os.environ and os.environ["PORCUPINE_API_KEY"]:
            self.porcupine_api_key = os.environ["PORCUPINE_API_KEY"]
        if "JARVIS_WAKEWORD_ENGINE" in os.environ and os.environ["JARVIS_WAKEWORD_ENGINE"]:
            self.wakeword_engine = os.environ["JARVIS_WAKEWORD_ENGINE"]
        if "JARVIS_WHISPER_MODEL" in os.environ and os.environ["JARVIS_WHISPER_MODEL"]:
            self.whisper_model_size = os.environ["JARVIS_WHISPER_MODEL"]
            self.model_whisper_size = os.environ["JARVIS_WHISPER_MODEL"]
        elif "WHISPER_MODEL" in os.environ and os.environ["WHISPER_MODEL"]:
            self.whisper_model_size = os.environ["WHISPER_MODEL"]
            self.model_whisper_size = os.environ["WHISPER_MODEL"]
            
        if "JARVIS_WHISPER_BEAM_SIZE" in os.environ:
            try:
                self.whisper_beam_size = int(os.environ["JARVIS_WHISPER_BEAM_SIZE"])
            except ValueError:
                pass
        elif "WHISPER_BEAM_SIZE" in os.environ:
            try:
                self.whisper_beam_size = int(os.environ["WHISPER_BEAM_SIZE"])
            except ValueError:
                pass

        if "JARVIS_SILENCE_DURATION" in os.environ:
            try:
                self.silence_duration = float(os.environ["JARVIS_SILENCE_DURATION"])
            except ValueError:
                pass
        elif "SILENCE_DURATION" in os.environ:
            try:
                self.silence_duration = float(os.environ["SILENCE_DURATION"])
            except ValueError:
                pass

        if "JARVIS_TTS_PROVIDER" in os.environ and os.environ["JARVIS_TTS_PROVIDER"]:
            self.tts_provider = os.environ["JARVIS_TTS_PROVIDER"]
        elif "TTS_PROVIDER" in os.environ and os.environ["TTS_PROVIDER"]:
            self.tts_provider = os.environ["TTS_PROVIDER"]

        if "JARVIS_TTS_CLOUD_TIMEOUT_MS" in os.environ:
            try:
                self.tts_cloud_timeout_ms = int(os.environ["JARVIS_TTS_CLOUD_TIMEOUT_MS"])
            except ValueError:
                pass
        elif "TTS_CLOUD_TIMEOUT_MS" in os.environ:
            try:
                self.tts_cloud_timeout_ms = int(os.environ["TTS_CLOUD_TIMEOUT_MS"])
            except ValueError:
                pass

        if "JARVIS_TTS_CACHE_ENABLED" in os.environ:
            self.tts_cache_enabled = os.environ["JARVIS_TTS_CACHE_ENABLED"].lower() in ["true", "1", "yes"]
        elif "TTS_CACHE_ENABLED" in os.environ:
            self.tts_cache_enabled = os.environ["TTS_CACHE_ENABLED"].lower() in ["true", "1", "yes"]

        if "JARVIS_TTS_VOICE" in os.environ and os.environ["JARVIS_TTS_VOICE"]:
            self.tts_voice = os.environ["JARVIS_TTS_VOICE"]
            self.model_tts_voice = os.environ["JARVIS_TTS_VOICE"]
        if "JARVIS_TTS_PITCH" in os.environ and os.environ["JARVIS_TTS_PITCH"]:
            self.tts_pitch = os.environ["JARVIS_TTS_PITCH"]
        if "JARVIS_TTS_RATE" in os.environ and os.environ["JARVIS_TTS_RATE"]:
            self.tts_rate = os.environ["JARVIS_TTS_RATE"]
        if "JARVIS_TTS_VOLUME" in os.environ and os.environ["JARVIS_TTS_VOLUME"]:
            self.tts_volume = os.environ["JARVIS_TTS_VOLUME"]
        if "JARVIS_PLAYBACK_VOLUME" in os.environ:
            try:
                self.playback_volume = float(os.environ["JARVIS_PLAYBACK_VOLUME"])
            except ValueError:
                pass
        if "JARVIS_LOG_LEVEL" in os.environ:
            self.log_level = os.environ["JARVIS_LOG_LEVEL"]
        if "AUDIO_OUTPUT_DEVICE" in os.environ:
            self.audio_output_device = os.environ["AUDIO_OUTPUT_DEVICE"]
        elif "JARVIS_AUDIO_OUTPUT_DEVICE" in os.environ:
            self.audio_output_device = os.environ["JARVIS_AUDIO_OUTPUT_DEVICE"]
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
        if "JARVIS_PERSISTENT_MEMORY" in os.environ:
            self.persistent_memory_enabled = os.environ["JARVIS_PERSISTENT_MEMORY"].lower() in ["true", "1", "yes"]

        if "JARVIS_CREATOR_NAME" in os.environ and os.environ["JARVIS_CREATOR_NAME"]:
            self.creator_name = os.environ["JARVIS_CREATOR_NAME"]
        elif "CREATOR_NAME" in os.environ and os.environ["CREATOR_NAME"]:
            self.creator_name = os.environ["CREATOR_NAME"]

        if "JARVIS_PERSONALITY_TONE" in os.environ and os.environ["JARVIS_PERSONALITY_TONE"]:
            self.personality_tone = os.environ["JARVIS_PERSONALITY_TONE"].lower()
        if "JARVIS_RESPONSE_LENGTH" in os.environ and os.environ["JARVIS_RESPONSE_LENGTH"]:
            self.response_length = os.environ["JARVIS_RESPONSE_LENGTH"].lower()
        if "JARVIS_HUMOR_ENABLED" in os.environ:
            self.humor_enabled = os.environ["JARVIS_HUMOR_ENABLED"].lower() in ["true", "1", "yes"]

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
