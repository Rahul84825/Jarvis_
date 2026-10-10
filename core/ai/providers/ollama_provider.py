import os
import json
import logging
import urllib.request
from typing import List, Dict, Any, Optional
from core.ai.base_provider import BaseAIProvider

logger = logging.getLogger("Jarvis.OllamaProvider")

class OllamaProvider(BaseAIProvider):
    """Local offline AI Provider interfacing with Ollama HTTP daemon.
    Reference: https://jarvis.institute/guide/#routing and https://jarvis.institute/security/
    Enables 100% on-device inference with zero external network traffic.
    """

    def __init__(self, host: str = "http://localhost:11434", default_model: str = "llama3"):
        self.host = os.environ.get("OLLAMA_HOST", host).rstrip("/")
        self.model = os.environ.get("OLLAMA_MODEL", default_model)

    def get_name(self) -> str:
        return f"Ollama Local ({self.model})"

    def is_available(self) -> bool:
        """Lightweight non-blocking ping to verify Ollama daemon is active locally."""
        try:
            req = urllib.request.Request(f"{self.host}/api/tags", headers={"User-Agent": "JARVIS-Client"})
            with urllib.request.urlopen(req, timeout=0.6) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate_response(self, messages: List[Dict[str, str]], context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Generates response using local Ollama model."""
        try:
            url = f"{self.host}/api/chat"
            payload = {
                "model": self.model,
                "messages": messages,
                "stream": False
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")

            with urllib.request.urlopen(req, timeout=30.0) as response:
                if response.status == 200:
                    res_json = json.loads(response.read().decode("utf-8"))
                    msg = res_json.get("message", {}).get("content", "")
                    return msg.strip() if msg else None
        except Exception as e:
            logger.warning(f"[Ollama] Generation failed: {e}")
        return None
