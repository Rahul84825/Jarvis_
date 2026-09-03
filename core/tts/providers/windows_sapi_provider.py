import os
import tempfile
import logging
from typing import Optional, List, Dict
from core.tts.base_tts import BaseTTS
from config import config

logger = logging.getLogger("Jarvis.WindowsSAPIProvider")

class WindowsSAPIProvider(BaseTTS):
    """Native Windows SAPI5 COM TTS Provider.
    Works 100% offline with zero external package dependencies on Windows.
    Uses Microsoft David, Microsoft Zira, or other installed SAPI voices.
    """

    def __init__(self):
        self._available = False
        self._voice_names: List[str] = []
        self._check_availability()

    def _check_availability(self):
        try:
            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            voices = speaker.GetVoices()
            self._voice_names = [voices.Item(i).GetDescription() for i in range(voices.Count)]
            self._available = True
            logger.info(f"Windows SAPI initialized successfully with {len(self._voice_names)} voices: {self._voice_names}")
        except Exception as e:
            logger.warning(f"Windows SAPI not available: {e}")
            self._available = False

    def get_name(self) -> str:
        return "Windows SAPI (Native Offline)"

    def is_available(self) -> bool:
        return self._available

    def get_available_voices(self) -> List[str]:
        return self._voice_names

    def synthesize_to_file(self, text: str) -> Optional[str]:
        if not text or not text.strip():
            return None

        if not self._available:
            self._check_availability()
            if not self._available:
                logger.error("[WindowsSAPI] SAPI COM is unavailable on this machine.")
                return None

        fd, temp_path = tempfile.mkstemp(suffix=".wav", prefix="jarvis_sapi_")
        os.close(fd)

        logger.info(f"[WindowsSAPI] Synthesizing offline: '{text}'")
        try:
            import win32com.client
            import pythoncom
            pythoncom.CoInitialize()

            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            stream = win32com.client.Dispatch("SAPI.SpFileStream")

            # Desired voice selection
            preferred_voice = getattr(config, "sapi_voice", "David").lower()
            voices = speaker.GetVoices()
            for i in range(voices.Count):
                desc = voices.Item(i).GetDescription().lower()
                if preferred_voice in desc:
                    speaker.Voice = voices.Item(i)
                    break

            # Rate mapping: SAPI rate is from -10 to +10 (0 is normal)
            rate_str = getattr(config, "tts_rate", "+0%")
            try:
                if "%" in rate_str:
                    pct = int(rate_str.replace("%", "").replace("+", ""))
                    # Map percentage (-50% to +50%) to SAPI scale (-5 to +5)
                    sapi_rate = max(-10, min(10, int(pct / 10)))
                    speaker.Rate = sapi_rate
            except Exception:
                speaker.Rate = 0

            # Open stream for writing (3 = SSFMCreateForWrite)
            stream.Open(temp_path, 3, False)
            speaker.AudioOutputStream = stream
            speaker.Speak(text)
            stream.Close()

            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                logger.debug(f"[WindowsSAPI] Saved audio file to: {temp_path}")
                return temp_path

            logger.error("[WindowsSAPI] SAPI output WAV is empty.")
            return None

        except Exception as e:
            logger.error(f"[WindowsSAPI] Synthesis failed: {e}", exc_info=True)
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            return None
        finally:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass
