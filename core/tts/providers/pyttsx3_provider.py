import os
import tempfile
import logging
from typing import Optional
from core.tts.base_tts import BaseTTS
from config import config

logger = logging.getLogger("Jarvis.Pyttsx3Provider")

class Pyttsx3Provider(BaseTTS):
    """Local Offline pyttsx3 Provider (SAPI5 / eSpeak / NSSS)."""

    def get_name(self) -> str:
        return "pyttsx3 (Offline Local)"

    def is_available(self) -> bool:
        try:
            import pyttsx3
            return True
        except ImportError:
            return False

    def synthesize_to_file(self, text: str) -> Optional[str]:
        if not text or not text.strip():
            return None

        fd, temp_path = tempfile.mkstemp(suffix=".wav", prefix="jarvis_pyttsx3_")
        os.close(fd)

        logger.info(f"[pyttsx3] Synthesizing offline: '{text}'")
        try:
            import pyttsx3
            engine = pyttsx3.init()
            rate_str = getattr(config, "tts_rate", "+15%")
            try:
                base_rate = 200
                if "%" in rate_str:
                    pct = int(rate_str.replace("%", "").replace("+", ""))
                    engine.setProperty("rate", int(base_rate * (1 + pct / 100)))
            except Exception:
                engine.setProperty("rate", 220)

            engine.save_to_file(text, temp_path)
            engine.runAndWait()

            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                logger.debug(f"[pyttsx3] Saved audio file to: {temp_path}")
                return temp_path
            return None
        except Exception as e:
            logger.error(f"[pyttsx3] Synthesis failed: {e}", exc_info=True)
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            return None
