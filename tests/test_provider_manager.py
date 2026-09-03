import unittest
from unittest.mock import patch, MagicMock
from core.ai.provider_manager import ProviderManager
from config import config

class TestProviderManager(unittest.TestCase):

    def setUp(self):
        self.pm = ProviderManager()

    def test_default_none_provider(self):
        with patch.object(config, "ai_provider", "none"):
            self.assertIsNone(self.pm.get_active_provider())
            self.assertFalse(self.pm.is_ai_available())
            self.assertIn("None", self.pm.get_active_provider_name())

    def test_unavailable_provider_fallback(self):
        with patch.object(config, "ai_provider", "openrouter"):
            with patch.object(config, "openrouter_api_key", ""):
                self.assertIsNone(self.pm.get_active_provider())
                res = self.pm.generate_response([{"role": "user", "content": "hello"}])
                self.assertIsNone(res)

    def test_local_provider_selection(self):
        with patch.object(config, "ai_provider", "local"):
            prov = self.pm.get_active_provider()
            self.assertIsNotNone(prov)
            self.assertEqual(prov.get_name(), "Local Engine (Offline)")
            res = self.pm.generate_response([{"role": "user", "content": "who are you"}])
            self.assertIsNotNone(res)

if __name__ == "__main__":
    unittest.main()
