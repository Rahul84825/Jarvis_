import unittest
from unittest.mock import patch
from core.llm import GeminiClient

class TestOfflineFallback(unittest.TestCase):

    def setUp(self):
        self.client = GeminiClient(api_key="")

    def test_zero_api_key_error_in_response(self):
        forbidden_phrases = [
            "gemini api key is missing",
            "please configure your api key",
            "gemini api is not configured",
            "api key required",
            "configure config.py",
            "gemini unavailable"
        ]
        res1 = self.client.generate_response("Explain quantum computing.")
        res2 = self.client.generate_response("Who are you?")
        res3 = self.client.generate_response("Hello!")

        for phrase in forbidden_phrases:
            self.assertNotIn(phrase, res1.lower())
            self.assertNotIn(phrase, res2.lower())
            self.assertNotIn(phrase, res3.lower())

    def test_natural_reasoning_offline_message(self):
        res = self.client.generate_response("Explain quantum computing.")
        self.assertIn("currently operating in offline mode", res.lower())

    def test_identity_offline_message(self):
        res = self.client.generate_response("Who are you?")
        self.assertIn("goliya", res.lower())
        self.assertIn("assistant", res.lower())

    def test_greetings_offline_message(self):
        res = self.client.generate_response("Good morning")
        self.assertIn("hello", res.lower())

if __name__ == "__main__":
    unittest.main()
