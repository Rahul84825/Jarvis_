import logging
from typing import List, Dict, Any, Optional
from core.ai.base_provider import BaseAIProvider
from core.llm import GeminiClient
from config import config

logger = logging.getLogger("Jarvis.GeminiProvider")

class GeminiProvider(BaseAIProvider):
    """Google Gemini AI Provider wrapping GeminiClient into BaseAIProvider interface."""

    def __init__(self, api_key: str = None):
        key = api_key or getattr(config, "gemini_api_key", "")
        self.client = GeminiClient(api_key=key)

    def get_name(self) -> str:
        return "Google Gemini Cloud AI"

    def is_available(self) -> bool:
        return self.client.is_available()

    def generate_response(self, messages: List[Dict[str, str]], context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        if not self.is_available():
            logger.debug("[GeminiProvider] Provider unavailable (missing API key).")
            return None

        # Extract latest user message
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m.get("content", "")
                break

        if not user_msg:
            return None

        # Build Gemini history format
        gemini_history = []
        for m in messages[:-1]:
            role = "user" if m.get("role") == "user" else "model"
            gemini_history.append({"role": role, "parts": [m.get("content", "")]})

        try:
            return self.client.generate_response(user_msg, conversation_history=gemini_history)
        except Exception as e:
            logger.error(f"[GeminiProvider] API generation failed: {e}")
            return None
