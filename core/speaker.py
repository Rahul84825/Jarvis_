import logging
from core.tts.tts_manager import TTSManager

logger = logging.getLogger("Jarvis.Speaker")

class Speaker(TTSManager):
    """Backward compatibility wrapper for TTSManager."""
    pass
