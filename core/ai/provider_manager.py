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
from core.ai.providers.nvidia_provider import NvidiaNemotronProvider
from core.security.privacy_guard import privacy_guard, PrivacyMode

from core.ai.provider_settings import provider_settings_manager

logger = logging.getLogger("Jarvis.ProviderManager")

class ProviderManager:
    """Central AI Provider Manager.
    Manages model selection, prefix routing ('claude:', 'gpt:', 'ollama:', 'nvidia:', 'nemotron:'),
    5-tier capability routing, resilient multi-provider failover, privacy mode enforcement,
    outbound secret redaction, and audit logging.
    """

    def __init__(self):
        self._providers: Dict[str, BaseAIProvider] = {
            "local": LocalAIProvider(),
            "ollama": OllamaProvider(),
            "openrouter": OpenRouterProvider(),
            "cerebras": CerebrasProvider(),
            "gemini": GeminiProvider(),
            "openai": OpenAIProvider(),
            "nvidia": NvidiaNemotronProvider()
        }
        self.settings = provider_settings_manager
        self._sync_with_settings()

    def _sync_with_settings(self):
        """Synchronizes provider instances with current settings and credentials."""
        for pid, prov in self._providers.items():
            cfg = self.settings.get_provider_config(pid)
            if cfg:
                if hasattr(prov, "api_key") and cfg.api_key:
                    prov.api_key = cfg.api_key
                if hasattr(prov, "model") and cfg.model:
                    prov.model = cfg.model
                if hasattr(prov, "base_url") and cfg.base_url:
                    prov.base_url = cfg.base_url
                if hasattr(prov, "timeout") and cfg.timeout_sec:
                    prov.timeout = cfg.timeout_sec

    @property
    def active_provider_key(self) -> str:
        self._sync_with_settings()
        def_model = os.environ.get("JARVIS_DEFAULT_MODEL", "").lower().strip()
        if def_model:
            if "ollama" in def_model: return "ollama"
            if "nemotron" in def_model or "nvidia" in def_model: return "nvidia"
            if "gpt" in def_model or "openai" in def_model: return "openai"
            if "claude" in def_model or "openrouter" in def_model: return "openrouter"
            if "gemini" in def_model: return "gemini"
            if "cerebras" in def_model or "groq" in def_model: return "cerebras"

        prov_cfg = getattr(config, "ai_provider", "").lower().strip()
        if prov_cfg and prov_cfg not in ["default", "auto"]:
            if prov_cfg in ["nvidia", "nemotron"]:
                return "nvidia"
            return prov_cfg

        # Check eligible providers in priority order
        eligible = self.settings.get_eligible_providers("text")
        if eligible:
            return eligible[0].provider_id

        if getattr(config, "nvidia_api_key", None) or os.environ.get("NVIDIA_API_KEY"):
            return "nvidia"
        return "none"

    def get_provider(self, key: str) -> Optional[BaseAIProvider]:
        self._sync_with_settings()
        return self._providers.get(key.lower().strip())

    def get_active_provider(self) -> Optional[BaseAIProvider]:
        key = self.active_provider_key
        if key == "none" or not key:
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

    def is_vision_capable(self, provider_key: Optional[str] = None) -> bool:
        """Checks if active provider or specified provider explicitly supports visual understanding."""
        key = provider_key or self.active_provider_key
        cfg = self.settings.get_provider_config(key)
        if cfg and "vision" in getattr(cfg, "capabilities", []) and getattr(cfg, "enabled", True):
            return True
        return False

    def extract_model_prefix(self, text: str) -> Tuple[Optional[str], str]:
        """Detects model routing prefixes (e.g., 'claude:', 'gpt:', 'ollama:', 'gemini:', 'groq:', 'ask nemotron to...').
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
            (r"^(?:ask\s+)?(?:nvidia|nemotron)(?:\s*:\s*|\s*,\s*|\s+model\s+to\s+|\s+ai\s+to\s+|\s+to\s+|\s+about\s+|\s+explain\s+)(.+)$", "nvidia"),
            (r"^(?:nvidia|nemotron)\s*:\s*(.+)$", "nvidia"),
        ]
        for pat, prov_key in prefix_patterns:
            m = re.match(pat, text.strip(), re.IGNORECASE)
            if m:
                return prov_key, m.group(1).strip()

        return None, text

    def generate_response(self, messages: List[Dict[str, str]], context: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """Routes generation request to the best eligible AI provider with capability matching,
        multimodal formatting, and resilient fallback failover.
        """
        if not messages:
            return None

        self._sync_with_settings()
        last_user_msg = messages[-1].get("content", "")
        forced_prov_key, clean_query = self.extract_model_prefix(last_user_msg)

        ctx = context or {}
        req_capability = "vision" if ctx.get("requires_vision") else "text"
        image_b64 = ctx.get("image_base64")

        # 1. Determine candidate providers
        candidates: List[Tuple[str, BaseAIProvider]] = []
        seen_keys = set()

        if forced_prov_key and forced_prov_key in self._providers:
            prov = self._providers[forced_prov_key]
            if prov.is_available():
                candidates.append((forced_prov_key, prov))
                seen_keys.add(forced_prov_key)
            # Update last user message with clean query
            messages = [dict(m) for m in messages[:-1]] + [{"role": "user", "content": clean_query}]

        # Include eligible configured providers from settings manager for priority routing & failover
        eligible_cfgs = self.settings.get_eligible_providers(req_capability)
        if eligible_cfgs:
            explicit_prov_cfg = getattr(config, "ai_provider", "").lower().strip()
            if explicit_prov_cfg in ["nvidia", "nemotron"]:
                explicit_prov_key = "nvidia"
            else:
                explicit_prov_key = explicit_prov_cfg

            sorted_cfgs = list(eligible_cfgs)
            if explicit_prov_key and explicit_prov_key not in ["default", "auto", "none"]:
                sorted_cfgs.sort(key=lambda c: 0 if c.provider_id == explicit_prov_key else 1)

            for cfg in sorted_cfgs:
                pid = cfg.provider_id
                if pid not in seen_keys and pid in self._providers:
                    p = self._providers[pid]
                    if p.is_available():
                        candidates.append((pid, p))
                        seen_keys.add(pid)
        else:
            # Fallback to active provider if settings list is unconfigured or empty
            act = self.get_active_provider()
            if act and act.is_available() and self.active_provider_key not in seen_keys:
                candidates.append((self.active_provider_key, act))

        if not candidates:
            logger.info(f"[ProviderManager] No eligible AI provider available for capability '{req_capability}'.")
            return None

        # 1B. Check Multi-Layer AI Cache (Section 2 & 6)
        query_to_cache = clean_query if forced_prov_key else last_user_msg
        if isinstance(query_to_cache, str) and query_to_cache.strip() and not ctx.get("force_fresh"):
            try:
                from core.ai.caching import nemotron_cache
                target_prov_key = candidates[0][0]
                target_prov_obj = candidates[0][1]
                target_model = getattr(target_prov_obj, "model", "default")
                lookup_res = nemotron_cache.lookup(query_to_cache, provider=target_prov_key, model=target_model, context=ctx)
                if lookup_res.hit and lookup_res.response:
                    logger.info(f"[CACHE_HIT] Resolved request via {lookup_res.source_label} in {lookup_res.latency_ms:.2f}ms (0 outbound API calls)")
                    return lookup_res.response
            except Exception as ce:
                logger.debug(f"[CACHE_LOOKUP_ERROR] Cache lookup failed gracefully: {ce}")

        # 2. Iterate through candidates with failover
        for prov_key, provider in candidates:
            is_cloud_provider = provider.get_name() not in ["LocalAIProvider", "Ollama Local"] and not isinstance(provider, (LocalAIProvider, OllamaProvider))

            # Strict privacy check
            if is_cloud_provider and not privacy_guard.is_cloud_allowed():
                logger.warning(f"[PRIVACY_GUARD] Cloud provider '{provider.get_name()}' blocked by STRICT privacy mode.")
                privacy_guard.record_audit(provider.get_name(), "blocked_by_strict", 0, [], len(last_user_msg), status="BLOCKED")
                continue

            # Redact secrets from outgoing text
            total_redacted = 0
            all_types = []
            sanitized_messages = []
            for msg in messages:
                content = msg.get("content", "")
                if isinstance(content, str):
                    clean_c, red_cnt, types = privacy_guard.redact_text(content)
                    total_redacted += red_cnt
                    all_types.extend(types)
                    sanitized_messages.append({"role": msg.get("role", "user"), "content": clean_c})
                else:
                    sanitized_messages.append(msg)

            # If vision is required and provider supports it, wrap content in multimodal format
            call_messages = sanitized_messages
            prov_cfg = self.settings.get_provider_config(prov_key)
            prov_supports_vision = ("vision" in getattr(prov_cfg, "capabilities", [])) if prov_cfg else False

            if req_capability == "vision" and image_b64 and prov_supports_vision:
                call_messages = []
                for msg in sanitized_messages:
                    if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                        content_items = [
                            {"type": "text", "text": msg["content"]},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
                        ]
                        call_messages.append({"role": "user", "content": content_items})
                    else:
                        call_messages.append(msg)

            if is_cloud_provider:
                privacy_guard.record_audit(
                    provider.get_name(),
                    "generate_response",
                    total_redacted,
                    all_types,
                    sum(len(str(m.get("content", ""))) for m in sanitized_messages),
                    status="PERMITTED"
                )

            try:
                logger.info(f"[ProviderManager] Routing request to AI Provider: {provider.get_name()} (Capability: {req_capability})")

                # Single-Flight Request Coalescing (Section 8)
                from core.ai.caching import nemotron_cache, CacheLayer
                prov_model = getattr(provider, "model", "default")
                flight_key = nemotron_cache.generate_cache_key(query_to_cache, provider=prov_key, model=prov_model, context=ctx)

                def _execute_provider():
                    return provider.generate_response(call_messages, context=context)

                res, was_coalesced = nemotron_cache.coalesce_and_execute(flight_key, _execute_provider)

                if res and res.strip():
                    clean_output = privacy_guard.sanitize_external_output(res.strip())

                    # Store in cache if newly generated and eligible
                    if not was_coalesced:
                        try:
                            layer = CacheLayer.TASK_RESULT if ctx.get("file_path") else CacheLayer.EXACT
                            nemotron_cache.store_response(
                                query=query_to_cache,
                                response=clean_output,
                                provider=prov_key,
                                model=prov_model,
                                layer=layer,
                                context=ctx
                            )
                        except Exception as ce:
                            logger.debug(f"Failed to cache response: {ce}")

                    return clean_output
                else:
                    logger.warning(f"[ProviderManager] Provider {provider.get_name()} returned empty response. Attempting failover.")
            except Exception as e:
                # Sanitize error to avoid logging secrets
                err_clean = str(e)
                if hasattr(provider, "api_key") and provider.api_key and len(provider.api_key) > 5:
                    err_clean = err_clean.replace(provider.api_key, "[REDACTED_KEY]")
                logger.warning(f"[ProviderManager] Error from {provider.get_name()}: {err_clean}. Attempting failover.")

        logger.error("[ProviderManager] All candidate AI providers failed or were unavailable.")
        return None
