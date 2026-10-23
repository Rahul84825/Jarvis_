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
            
            # Volume setting (0.0 to 1.0)
            try:
                vol = float(getattr(config, "playback_volume", 0.70))
                engine.setProperty("volume", max(0.1, min(1.0, vol)))
            except Exception:
                engine.setProperty("volume", 0.70)

            rate_str = getattr(config, "tts_rate", "+0%")
            try:
                base_rate = 165
                if "%" in rate_str:
                    pct = int(rate_str.replace("%", "").replace("+", ""))
                    engine.setProperty("rate", int(base_rate * (1 + pct / 100)))
            except Exception:
                engine.setProperty("rate", 165)

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
