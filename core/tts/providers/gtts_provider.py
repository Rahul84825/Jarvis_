import os
import tempfile
import logging
from typing import Optional
from core.tts.base_tts import BaseTTS

logger = logging.getLogger("Jarvis.GTTSProvider")

class GTTSProvider(BaseTTS):
    """gTTS Google Translate TTS Provider Fallback."""

    def get_name(self) -> str:
        return "gTTS (Google Web Fallback)"

    def synthesize_to_file(self, text: str) -> Optional[str]:
        if not text or not text.strip():
            return None

        fd, temp_path = tempfile.mkstemp(suffix=".mp3", prefix="jarvis_gtts_")
        os.close(fd)

        logger.info(f"[gTTS] Synthesizing: '{text}'")
        try:
            from gtts import gTTS
            tts = gTTS(text=text, lang="en")
            tts.save(temp_path)

            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                logger.debug(f"[gTTS] Saved audio file to: {temp_path}")
                return temp_path
            return None
        except Exception as e:
            logger.error(f"[gTTS] Synthesis failed: {e}", exc_info=True)
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            return None
