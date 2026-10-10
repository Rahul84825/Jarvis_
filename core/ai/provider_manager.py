import os
import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from config import config
from core.ai.base_provider import BaseAIProvider
from core.ai.providers.local_provider import LocalAIProvider
from core.ai.providers.openrouter_provider import OpenRouterProvider
from core.ai.providers.cerebras_provider import CerebrasProvider
from core.ai.providers.gemini_provider import GeminiProvider
from core.ai.providers.openai_provider import OpenAIProvider
from core.ai.providers.ollama_provider import OllamaProvider
from core.security.privacy_guard import privacy_guard, PrivacyMode

logger = logging.getLogger("Jarvis.ProviderManager")

class ProviderManager:
    """Central AI Provider Manager.
    Manages model selection, prefix routing ('claude:', 'gpt:', 'ollama:'), availability checks,
    privacy mode enforcement (STRICT/GUARDED/RELAXED), outbound secret redaction, and audit logging.
    Reference: https://jarvis.institute/guide/#routing and https://jarvis.institute/security/
    """

    def __init__(self):
        self._providers: Dict[str, BaseAIProvider] = {
            "local": LocalAIProvider(),
            "ollama": OllamaProvider(),
            "openrouter": OpenRouterProvider(),
            "cerebras": CerebrasProvider(),
            "gemini": GeminiProvider(),
            "openai": OpenAIProvider()
        }

    @property
    def active_provider_key(self) -> str:
        # Check environment or config
        def_model = os.environ.get("JARVIS_DEFAULT_MODEL", "").lower().strip()
        if def_model:
            if "ollama" in def_model: return "ollama"
            if "gpt" in def_model or "openai" in def_model: return "openai"
            if "claude" in def_model or "openrouter" in def_model: return "openrouter"
            if "gemini" in def_model: return "gemini"
            if "cerebras" in def_model or "groq" in def_model: return "cerebras"

        return getattr(config, "ai_provider", "none").lower().strip()

    def get_provider(self, key: str) -> Optional[BaseAIProvider]:
        return self._providers.get(key.lower().strip())

    def get_active_provider(self) -> Optional[BaseAIProvider]:
        key = self.active_provider_key
        if key == "none" or not key:
            # If in STRICT mode and Ollama is online, use Ollama
            if not privacy_guard.is_cloud_allowed():
                ollama = self._providers.get("ollama")
                if ollama and ollama.is_available():
                    return ollama
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

    def extract_model_prefix(self, text: str) -> Tuple[Optional[str], str]:
        """Detects model routing prefixes (e.g., 'claude:', 'gpt:', 'ollama:', 'gemini:', 'groq:').
        Returns: (provider_key, clean_text)
        """
        if not text or not isinstance(text, str):
            return None, text

        prefix_patterns = [
            (r"^(?:claude(?:-code)?|anthropic)\s*:\s*(.+)$", "openrouter"),
            (r"^(?:gpt|openai|chatgpt)\s*:\s*(.+)$", "openai"),
            (r"^(?:gemini|google)\s*:\s*(.+)$", "gemini"),
            (r"^(?:ollama|local|llama)\s*:\s*(.+)$", "ollama"),
            (r"^(?:groq|cerebras)\s*:\s*(.+)$", "cerebras"),
        ]
        for pat, prov_key in prefix_patterns:
            m = re.match(pat, text.strip(), re.IGNORECASE)
            if m:
                return prov_key, m.group(1).strip()

        return None, text

    def generate_response(self, messages: List[Dict[str, str]], context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Routes text generation request to the selected or active AI provider with privacy guard interception."""
        if not messages:
            return None

        last_user_msg = messages[-1].get("content", "")
        forced_prov_key, clean_query = self.extract_model_prefix(last_user_msg)

        if forced_prov_key:
            # Use forced provider if available
            provider = self._providers.get(forced_prov_key)
            # Update last user message with clean query
            messages = [dict(m) for m in messages[:-1]] + [{"role": "user", "content": clean_query}]
        else:
            provider = self.get_active_provider()

        if not provider:
            logger.info("[ProviderManager] No active or requested AI provider available. Returning None for fallback.")
            return None

        is_cloud_provider = provider.get_name() not in ["LocalAIProvider", "Ollama Local"] and not isinstance(provider, (LocalAIProvider, OllamaProvider))

        # Check Privacy Mode (STRICT mode blocks cloud models)
        if is_cloud_provider and not privacy_guard.is_cloud_allowed():
            logger.warning(f"[PRIVACY_GUARD] Cloud provider '{provider.get_name()}' blocked by STRICT privacy mode.")
            privacy_guard.record_audit(provider.get_name(), "blocked_by_strict", 0, [], len(last_user_msg), status="BLOCKED")
            # Fallback to Ollama or local
            ollama = self._providers.get("ollama")
            if ollama and ollama.is_available():
                provider = ollama
            else:
                return None

        # Redact secrets from outgoing messages before cloud transmission (GUARDED mode)
        total_redacted = 0
        all_types = []
        sanitized_messages = []
        for msg in messages:
            content = msg.get("content", "")
            clean_c, red_cnt, types = privacy_guard.redact_text(content)
            total_redacted += red_cnt
            all_types.extend(types)
            sanitized_messages.append({"role": msg.get("role", "user"), "content": clean_c})

        if is_cloud_provider:
            privacy_guard.record_audit(
                provider.get_name(),
                "generate_response",
                total_redacted,
                all_types,
                sum(len(m["content"]) for m in sanitized_messages),
                status="PERMITTED"
            )

        try:
            logger.info(f"[ProviderManager] Routing request to AI Provider: {provider.get_name()} (Redactions={total_redacted})")
            res = provider.generate_response(sanitized_messages, context=context)
            if res and res.strip():
                # Inspect external model output for potential prompt-injection overrides
                clean_output = privacy_guard.sanitize_external_output(res.strip())
                return clean_output
        except Exception as e:
            logger.error(f"[ProviderManager] Error generating response from {provider.get_name()}: {e}")

        return None
