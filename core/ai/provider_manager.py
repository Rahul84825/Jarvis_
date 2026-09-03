import logging
from typing import Dict, List, Optional, Any
from config import config
from core.ai.base_provider import BaseAIProvider
from core.ai.providers.local_provider import LocalAIProvider
from core.ai.providers.openrouter_provider import OpenRouterProvider
from core.ai.providers.cerebras_provider import CerebrasProvider
from core.ai.providers.gemini_provider import GeminiProvider
from core.ai.providers.openai_provider import OpenAIProvider
from core.ai.providers.nvidia_provider import NVIDIAProvider

logger = logging.getLogger("Jarvis.ProviderManager")

class ProviderManager:
    """Central AI Provider Manager.
    Manages selection, availability checks, health monitoring, and graceful fallbacks across AI providers.
    Guarantees Jarvis core operates normally when AI_PROVIDER='none' or when keys are unconfigured.
    """

    def __init__(self):
        self._providers: Dict[str, BaseAIProvider] = {
            "local": LocalAIProvider(),
            "openrouter": OpenRouterProvider(),
            "cerebras": CerebrasProvider(),
            "gemini": GeminiProvider(),
            "openai": OpenAIProvider(),
            "nvidia": NVIDIAProvider()
        }

    @property
    def active_provider_key(self) -> str:
        return getattr(config, "ai_provider", "none").lower().strip()

    def get_active_provider(self) -> Optional[BaseAIProvider]:
        key = self.active_provider_key
        if key == "none" or not key:
            return None

        provider = self._providers.get(key)
        if provider and provider.is_available():
            return provider

        logger.debug(f"[ProviderManager] Selected provider '{key}' is unconfigured or unavailable.")
        return None

    def get_active_provider_name(self) -> str:
        provider = self.get_active_provider()
        if provider:
            return provider.get_name()
        if self.active_provider_key == "none":
            return "None (Local Core)"
        return f"{self.active_provider_key.title()} (Unavailable)"

    def is_ai_available(self) -> bool:
        provider = self.get_active_provider()
        return provider is not None and provider.is_available()

    def generate_response(self, messages: List[Dict[str, str]], context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Routes text generation request to the active AI provider.
        Returns None gracefully if no provider is configured or available.
        """
        provider = self.get_active_provider()
        if not provider:
            logger.info("[ProviderManager] No active AI provider available. Returning None for fallback.")
            return None

        try:
            logger.info(f"[ProviderManager] Routing request to AI Provider: {provider.get_name()}")
            res = provider.generate_response(messages, context=context)
            if res and res.strip():
                return res.strip()
        except Exception as e:
            logger.error(f"[ProviderManager] Error generating response from {provider.get_name()}: {e}")

        return None
