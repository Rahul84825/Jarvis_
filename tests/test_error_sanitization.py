import unittest
from core.response_manager import ResponseManager

class TestErrorSanitization(unittest.TestCase):

    def setUp(self):
        self.rm = ResponseManager(speaker=None)

    def test_failure_sanitization_generic(self):
        resp = self.rm.failure("Traceback (most recent call last): Exception: Database connection lost")
        self.assertNotIn("Traceback", resp["spoken_text"])
        self.assertNotIn("Exception", resp["spoken_text"])
        self.assertEqual(resp["spoken_text"], "I couldn't complete that.")

    def test_failure_sanitization_not_found(self):
        resp = self.rm.failure("Application 'unknown_app' not found in registry")
        self.assertNotIn("registry", resp["spoken_text"])
        self.assertEqual(resp["spoken_text"], "I couldn't find that application.")

    def test_no_gemini_api_key_messages(self):
        err_msg = "Gemini API key is missing. Please configure GEMINI_API_KEY."
        resp = self.rm.failure(err_msg)
        self.assertNotIn("Gemini", resp["spoken_text"])
        self.assertNotIn("API key", resp["spoken_text"])
        self.assertEqual(resp["spoken_text"], "I couldn't complete that.")

if __name__ == "__main__":
    unittest.main()
