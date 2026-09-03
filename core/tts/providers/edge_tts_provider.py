import os
import asyncio
import tempfile
import logging
from typing import Optional, List, Dict, Any
from core.tts.base_tts import BaseTTS
from config import config

logger = logging.getLogger("Jarvis.EdgeTTSProvider")

class EdgeTTSProvider(BaseTTS):
    """Cloud Neural Edge TTS Provider using edge-tts."""

    def get_name(self) -> str:
        return "EdgeTTS (Neural Cloud)"

    def synthesize_to_file(self, text: str) -> Optional[str]:
        if not text or not text.strip():
            return None

        import edge_tts
        voice = getattr(config, "tts_voice", "en-US-GuyNeural")
        rate = getattr(config, "tts_rate", "+0%")
        pitch = getattr(config, "tts_pitch", "+0Hz")
        volume = getattr(config, "tts_volume", "+0%")

        fd, temp_path = tempfile.mkstemp(suffix=".mp3", prefix="jarvis_edge_tts_")
        os.close(fd)

        logger.info(f"[EdgeTTS] Synthesizing: '{text}' (Voice: {voice}, Rate: {rate})")

        async def _run_synthesis():
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume)
            await communicate.save(temp_path)

        try:
            try:
                if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
                    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            except Exception:
                pass

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    executor.submit(asyncio.run, _run_synthesis()).result()
            else:
                asyncio.run(_run_synthesis())

            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                logger.debug(f"[EdgeTTS] Saved audio file to: {temp_path}")
                return temp_path

            logger.error("[EdgeTTS] Output file is empty.")
            return None
        except Exception as e:
            logger.error(f"[EdgeTTS] Synthesis failed: {e}", exc_info=True)
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
            return None
