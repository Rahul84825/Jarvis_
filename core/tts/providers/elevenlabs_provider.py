import os
import json
import logging
import urllib.request
import urllib.error
import tempfile
from pathlib import Path
from typing import Optional, List, Dict, Any
from core.tts.base_tts import BaseTTS

logger = logging.getLogger("Jarvis.TTS.ElevenLabs")

DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"  # George / British Voice


class ElevenLabsProvider(BaseTTS):
    """ElevenLabs Cloud TTS Provider with graceful degradation when API key is missing."""

    def __init__(self, api_key: str = None, voice_id: str = DEFAULT_VOICE_ID):
        self.voice_id = voice_id
        self.api_key = api_key or self._discover_api_key()

    def _discover_api_key(self) -> str:
        """Discovers ElevenLabs API key from env or ~/.claude.json."""
        if os.getenv("ELEVENLABS_API_KEY"):
            return os.getenv("ELEVENLABS_API_KEY").strip()

        # Check ~/.claude.json elevenlabs MCP entry
        claude_json = Path.home() / ".claude.json"
        if claude_json.exists():
            try:
                with open(claude_json, "r", encoding="utf-8") as f:
                    data = json.load(f)
                key = data.get("mcpServers", {}).get("elevenlabs", {}).get("env", {}).get("ELEVENLABS_API_KEY")
                if key:
                    return str(key).strip()
            except Exception:
                pass
        return ""

    def get_name(self) -> str:
        return "ElevenLabs"

    def is_available(self) -> bool:
        return bool(self.api_key)

    def synthesize_to_file(self, text: str) -> Optional[str]:
        """Synthesizes text to an MP3 file via ElevenLabs API and returns the file path."""
        if not self.is_available():
            raise RuntimeError("ElevenLabs API key not configured.")

        tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
        output_path = tmp.name
        tmp.close()

        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        payload = {
            "text": text,
            "model_id": "eleven_turbo_v2_5",
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.75
            }
        }
        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key,
            "User-Agent": "Jarvis-Desktop/2.0"
        }

        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10.0) as resp:
                if resp.status == 200:
                    with open(output_path, "wb") as f:
                        f.write(resp.read())
                    return output_path
                else:
                    raise RuntimeError(f"ElevenLabs API returned status code {resp.status}")
        except Exception as e:
            logger.warning(f"ElevenLabs synthesis failed: {e}")
            raise

    def get_voices(self) -> List[Dict[str, Any]]:
        return [{"id": self.voice_id, "name": "George (British)"}]
