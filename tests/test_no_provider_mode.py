import unittest
from unittest.mock import patch
from core.conversation_manager import ConversationManager
from config import config

class TestNoProviderMode(unittest.TestCase):

    def setUp(self):
        self.cm = ConversationManager()

    def test_no_provider_fallback_response(self):
        with patch.object(config, "ai_provider", "none"):
            res = self.cm.process_query("What is quantum computing?")
            self.assertFalse(res["ai_available"])
            self.assertEqual(res["source"], "Local Fallback")
            self.assertEqual(res["text"], "I'm currently limited to my local capabilities for that question.")

    def test_no_provider_zero_api_messages(self):
        with patch.object(config, "ai_provider", "none"):
            res = self.cm.process_query("Explain recursion")
            self.assertNotIn("API key", res["text"])
            self.assertNotIn("Gemini", res["text"])
            self.assertNotIn("OpenRouter", res["text"])

if __name__ == "__main__":
    unittest.main()
