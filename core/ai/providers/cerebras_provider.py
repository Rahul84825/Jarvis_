import logging
from typing import List, Dict, Any, Optional
from core.ai.base_provider import BaseAIProvider
from config import config

logger = logging.getLogger("Jarvis.CerebrasProvider")

class CerebrasProvider(BaseAIProvider):
    """Cerebras Ultra-Fast AI Provider."""

    def __init__(self, api_key: str = None, model: str = "llama3.1-8b"):
        self.api_key = api_key or getattr(config, "cerebras_api_key", "")
        self.model = model

    def get_name(self) -> str:
        return "Cerebras Fast AI"

    def is_available(self) -> bool:
        return bool(self.api_key and len(self.api_key.strip()) > 5)

    def generate_response(self, messages: List[Dict[str, str]], context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        if not self.is_available():
            logger.debug("[Cerebras] Provider unavailable (missing API key).")
            return None

        import urllib.request
        import json

        url = "https://api.cerebras.ai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key.strip()}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "max_tokens": 150,
            "temperature": 0.7
        }

        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "").strip()
        except Exception as e:
            logger.error(f"[Cerebras] API request failed: {e}")
        return None
