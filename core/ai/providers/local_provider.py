import logging
from typing import List, Dict, Any, Optional
from core.ai.base_provider import BaseAIProvider
from core.local_response_engine import LocalResponseEngine

logger = logging.getLogger("Jarvis.LocalAIProvider")

class LocalAIProvider(BaseAIProvider):
    """Local AI Provider using local template engine (100% offline, zero API requirement)."""

    def __init__(self):
        self.engine = LocalResponseEngine()

    def get_name(self) -> str:
        return "Local Engine (Offline)"

    def is_available(self) -> bool:
        return True

    def generate_response(self, messages: List[Dict[str, str]], context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        if not messages:
            return self.engine.get_template("greeting")
        last_msg = messages[-1].get("content", "").lower()
        if "help" in last_msg:
            return self.engine.get_help_response()
        if "who are you" in last_msg or "who made you" in last_msg:
            return self.engine.get_identity_response()
        return self.engine.get_template("unknown")
