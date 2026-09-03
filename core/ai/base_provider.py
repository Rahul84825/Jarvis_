from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Generator

class BaseAIProvider(ABC):
    """Abstract Base Class for all AI Providers.
    Decouples Jarvis runtime logic from cloud LLM API specifics.
    """

    @abstractmethod
    def get_name(self) -> str:
        """Returns provider human-readable display name."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if provider has required credentials and is enabled."""
        pass

    @abstractmethod
    def generate_response(self, messages: List[Dict[str, str]], context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Generates a text completion response for a given list of role-based messages."""
        pass

    def stream_response(self, messages: List[Dict[str, str]], context: Optional[Dict[str, Any]] = None) -> Generator[str, None, None]:
        """Streams text chunks for a given list of role-based messages."""
        res = self.generate_response(messages, context=context)
        if res:
            yield res

    def health_check(self) -> bool:
        """Performs a lightweight sanity test to check provider connectivity."""
        return self.is_available()
