import logging
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

logger = logging.getLogger("Jarvis.BaseTTS")

class BaseTTS(ABC):
    """Abstract Base Class for TTS Engine Providers."""

    @abstractmethod
    def get_name(self) -> str:
        """Returns provider name string."""
        pass

    @abstractmethod
    def synthesize_to_file(self, text: str) -> Optional[str]:
        """Synthesizes text to a temporary audio file (MP3/WAV) and returns its absolute path."""
        pass

    def get_voices(self) -> List[Dict[str, Any]]:
        """Returns list of supported voice metadata dictionaries."""
        return []
