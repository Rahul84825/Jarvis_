import unittest
from core.ai.base_provider import BaseAIProvider
from core.ai.providers.local_provider import LocalAIProvider
from core.ai.providers.openrouter_provider import OpenRouterProvider
from core.ai.providers.cerebras_provider import CerebrasProvider
from core.ai.providers.gemini_provider import GeminiProvider
from core.ai.providers.openai_provider import OpenAIProvider

class TestAIProviderInterface(unittest.TestCase):

    def test_local_provider_interface(self):
        p = LocalAIProvider()
        self.assertTrue(isinstance(p, BaseAIProvider))
        self.assertEqual(p.get_name(), "Local Engine (Offline)")
        self.assertTrue(p.is_available())
        res = p.generate_response([{"role": "user", "content": "hello"}])
        self.assertIsNotNone(res)

    def test_openrouter_provider_interface(self):
        p = OpenRouterProvider(api_key="")
        self.assertTrue(isinstance(p, BaseAIProvider))
        self.assertEqual(p.get_name(), "OpenRouter Cloud AI")
        self.assertFalse(p.is_available())
        self.assertIsNone(p.generate_response([{"role": "user", "content": "test"}]))

    def test_cerebras_provider_interface(self):
        p = CerebrasProvider(api_key="")
        self.assertTrue(isinstance(p, BaseAIProvider))
        self.assertEqual(p.get_name(), "Cerebras Fast AI")
        self.assertFalse(p.is_available())
        self.assertIsNone(p.generate_response([{"role": "user", "content": "test"}]))

    def test_gemini_provider_interface(self):
        p = GeminiProvider(api_key="")
        self.assertTrue(isinstance(p, BaseAIProvider))
        self.assertEqual(p.get_name(), "Google Gemini Cloud AI")

    def test_openai_provider_interface(self):
        p = OpenAIProvider(api_key="")
        self.assertTrue(isinstance(p, BaseAIProvider))
        self.assertEqual(p.get_name(), "OpenAI Cloud AI")
        self.assertFalse(p.is_available())

if __name__ == "__main__":
    unittest.main()
