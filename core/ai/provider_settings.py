"""Secure Multi-Provider AI Settings and Capability Manager for JARVIS.

Manages provider registration, API keys, models, priorities, capability matching,
connectivity testing, and privacy/cost controls (free-tier guard).
"""

import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger("Jarvis.ProviderSettings")

PROVIDERS_CONFIG_PATH = Path(__file__).parent.parent.parent / "config" / "ai_providers.json"


@dataclass
class AIProviderConfig:
    """Configuration for a specific AI model provider."""
    provider_id: str
    name: str
    model: str
    api_key: str = ""
    base_url: str = ""
    enabled: bool = True
    priority: int = 10  # Lower number = higher priority
    capabilities: List[str] = field(default_factory=lambda: ["text"])  # text, vision, code, tool_calling
    is_free_tier: bool = False
    timeout_sec: float = 25.0
    max_retries: int = 2
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self, mask_key: bool = True) -> Dict[str, Any]:
        d = asdict(self)
        if mask_key and self.api_key:
            k = self.api_key.strip()
            if len(k) > 8:
                d["api_key"] = f"{k[:4]}...{k[-4:]}"
            else:
                d["api_key"] = "********"
        return d


class ProviderSettingsManager:
    """Manages AI provider credentials, models, and priority-based routing."""

    DEFAULT_PROVIDERS = [
        AIProviderConfig(
            provider_id="nvidia",
            name="NVIDIA Nemotron",
            model="nvidia/nemotron-3.5-super-vl-120b-a12b",
            base_url="https://integrate.api.nvidia.com/v1",
            priority=1,
            capabilities=["text", "vision", "code", "tool_calling"],
            is_free_tier=True,
            timeout_sec=30.0
        ),
        AIProviderConfig(
            provider_id="gemini",
            name="Google Gemini",
            model="gemini-1.5-flash",
            base_url="https://generativelanguage.googleapis.com",
            priority=2,
            capabilities=["text", "vision", "code", "tool_calling"],
            is_free_tier=True,
            timeout_sec=20.0
        ),
        AIProviderConfig(
            provider_id="openai",
            name="OpenAI",
            model="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            priority=3,
            capabilities=["text", "vision", "code", "tool_calling"],
            is_free_tier=False,
            timeout_sec=25.0
        ),
        AIProviderConfig(
            provider_id="cerebras",
            name="Cerebras / Groq",
            model="llama3.1-8b",
            base_url="https://api.cerebras.ai/v1",
            priority=4,
            capabilities=["text", "code"],
            is_free_tier=True,
            timeout_sec=10.0
        ),
        AIProviderConfig(
            provider_id="ollama",
            name="Ollama Local",
            model="llama3.2",
            base_url="http://localhost:11434",
            priority=5,
            capabilities=["text", "code"],
            is_free_tier=True,
            timeout_sec=30.0
        )
    ]

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or PROVIDERS_CONFIG_PATH
        self.providers: Dict[str, AIProviderConfig] = {}
        self.free_only_mode: bool = False
        self._load_configuration()

    def _load_configuration(self):
        """Loads provider configuration merging defaults, disk file, and environment variables."""
        # 1. Initialize defaults
        for prov in self.DEFAULT_PROVIDERS:
            self.providers[prov.provider_id] = AIProviderConfig(**asdict(prov))

        # 2. Load from disk file if exists
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.free_only_mode = data.get("free_only_mode", False)
                    for item in data.get("providers", []):
                        pid = item.get("provider_id")
                        if pid:
                            if pid in self.providers:
                                # Update fields
                                for k, v in item.items():
                                    if hasattr(self.providers[pid], k):
                                        setattr(self.providers[pid], k, v)
                            else:
                                self.providers[pid] = AIProviderConfig(**item)
            except Exception as e:
                logger.error(f"Error loading AI providers config: {e}")

        # 3. Read environment variable overrides (highest precedence for keys)
        env_map = {
            "nvidia": "NVIDIA_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "cerebras": "CEREBRAS_API_KEY",
            "openrouter": "OPENROUTER_API_KEY"
        }
        for pid, env_var in env_map.items():
            val = os.environ.get(env_var, "").strip()
            if val and pid in self.providers:
                self.providers[pid].api_key = val

    def save_configuration(self):
        """Persists provider configurations (with plain keys for local use)."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "free_only_mode": self.free_only_mode,
            "providers": [asdict(p) for p in self.providers.values()]
        }
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info("Saved AI providers configuration.")
        except Exception as e:
            logger.error(f"Failed to save AI providers configuration: {e}")

    def get_provider_config(self, provider_id: str) -> Optional[AIProviderConfig]:
        return self.providers.get(provider_id.lower().strip())

    def update_provider_key(self, provider_id: str, api_key: str):
        """Updates and stores an API key securely."""
        pid = provider_id.lower().strip()
        if pid in self.providers:
            self.providers[pid].api_key = api_key.strip()
            self.save_configuration()
            logger.info(f"Updated API key for provider '{pid}'.")

    def update_provider_model(self, provider_id: str, model: str):
        pid = provider_id.lower().strip()
        if pid in self.providers:
            self.providers[pid].model = model.strip()
            self.save_configuration()

    def set_provider_enabled(self, provider_id: str, enabled: bool):
        pid = provider_id.lower().strip()
        if pid in self.providers:
            self.providers[pid].enabled = enabled
            self.save_configuration()

    def set_provider_priority(self, provider_id: str, priority: int):
        pid = provider_id.lower().strip()
        if pid in self.providers:
            self.providers[pid].priority = priority
            self.save_configuration()

    def set_free_only_mode(self, free_only: bool):
        self.free_only_mode = free_only
        self.save_configuration()

    def get_eligible_providers(
        self,
        required_capability: str = "text"
    ) -> List[AIProviderConfig]:
        """Returns sorted list of enabled, configured providers matching capability and cost limits."""
        eligible = []
        for prov in self.providers.values():
            if not prov.enabled:
                continue
            # Must have key (unless ollama)
            if prov.provider_id != "ollama" and not prov.api_key:
                continue
            # Cost guard
            if self.free_only_mode and not prov.is_free_tier:
                continue
            # Capability match
            if required_capability not in prov.capabilities:
                continue
            eligible.append(prov)

        # Sort by priority ascending (1 = highest)
        eligible.sort(key=lambda p: p.priority)
        return eligible

    def list_providers_summary(self) -> List[Dict[str, Any]]:
        """Returns safe summary for UI and telemetry with masked keys."""
        return [p.to_dict(mask_key=True) for p in sorted(self.providers.values(), key=lambda x: x.priority)]


# Global singleton instance
provider_settings_manager = ProviderSettingsManager()
