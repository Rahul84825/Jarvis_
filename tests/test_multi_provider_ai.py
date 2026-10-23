"""Automated Test Suite for JARVIS Multi-Provider AI Engine & Key Management."""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.ai.provider_settings import ProviderSettingsManager, AIProviderConfig
from core.ai.provider_manager import ProviderManager
from core.ai.base_provider import BaseAIProvider


class MockFailingProvider(BaseAIProvider):
    def get_name(self) -> str:
        return "Failing Cloud AI"
    def is_available(self) -> bool:
        return True
    def generate_response(self, messages, context=None):
        raise ConnectionError("Connection refused by mock cloud server with key sk-secret12345")


class MockWorkingProvider(BaseAIProvider):
    def get_name(self) -> str:
        return "Working Fallback AI"
    def is_available(self) -> bool:
        return True
    def generate_response(self, messages, context=None):
        return "Hello from working fallback AI!"


class TestMultiProviderAI(unittest.TestCase):
    """Validates multi-provider configuration, capability matching, failover, and secrets redaction."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="jarvis_ai_test_")
        self.config_path = Path(self.test_dir) / "ai_providers.json"
        self.settings = ProviderSettingsManager(config_path=self.config_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_provider_key_masking(self):
        """Verify API keys are masked when exported for UI or logs."""
        self.settings.update_provider_key("nvidia", "nvapi-abcdef1234567890")
        summary = self.settings.list_providers_summary()
        nvidia_cfg = next(p for p in summary if p["provider_id"] == "nvidia")
        self.assertTrue(nvidia_cfg["api_key"].startswith("nvap..."))
        self.assertNotIn("abcdef1234", nvidia_cfg["api_key"])

    def test_capability_matching_for_vision(self):
        """Verify that vision requests only return providers tagged with vision capability."""
        # Configure nvidia (vision) and cerebras (text-only) with keys
        self.settings.update_provider_key("nvidia", "key-nv-test")
        self.settings.update_provider_key("cerebras", "key-cerebras-test")

        vision_eligible = self.settings.get_eligible_providers("vision")
        vision_ids = [p.provider_id for p in vision_eligible]
        self.assertIn("nvidia", vision_ids)
        self.assertNotIn("cerebras", vision_ids)

        text_eligible = self.settings.get_eligible_providers("text")
        text_ids = [p.provider_id for p in text_eligible]
        self.assertIn("nvidia", text_ids)
        self.assertIn("cerebras", text_ids)

    def test_free_tier_guard_blocks_paid_models(self):
        """Verify free_only_mode excludes paid providers."""
        self.settings.update_provider_key("openai", "sk-openai-paid")
        self.settings.update_provider_key("gemini", "key-gemini-free")

        # Free only mode disabled -> both eligible
        self.settings.set_free_only_mode(False)
        all_eligible = [p.provider_id for p in self.settings.get_eligible_providers("text")]
        self.assertIn("openai", all_eligible)
        self.assertIn("gemini", all_eligible)

        # Free only mode enabled -> openai excluded
        self.settings.set_free_only_mode(True)
        free_eligible = [p.provider_id for p in self.settings.get_eligible_providers("text")]
        self.assertNotIn("openai", free_eligible)
        self.assertIn("gemini", free_eligible)

    def test_resilient_failover_when_primary_errors(self):
        """Verify ProviderManager automatically fails over to next capable provider if primary errors."""
        mgr = ProviderManager()
        failing_prov = MockFailingProvider()
        failing_prov.api_key = "sk-secret12345"
        working_prov = MockWorkingProvider()

        # Configure candidates
        with patch.object(mgr.settings, "get_eligible_providers") as mock_eligible:
            mock_eligible.return_value = [
                AIProviderConfig(provider_id="fail", name="Failing", model="m1", enabled=True, priority=1),
                AIProviderConfig(provider_id="work", name="Working", model="m2", enabled=True, priority=2)
            ]
            mgr._providers["fail"] = failing_prov
            mgr._providers["work"] = working_prov

            messages = [{"role": "user", "content": "What is Python?"}]
            res = mgr.generate_response(messages)
            self.assertEqual(res, "Hello from working fallback AI!")


if __name__ == "__main__":
    unittest.main()
