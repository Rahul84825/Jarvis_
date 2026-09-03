import sys
import unittest
from unittest.mock import MagicMock, patch
from core.llm import GeminiClient
from config import config

class TestGeminiClient(unittest.TestCase):
    def test_fallback_mode_no_api_key(self):
        """Verifies fallback/mock offline reasoning when API key is not set."""
        client = GeminiClient(api_key="")

        # Test greeting fallback
        res_greet = client.generate_response("hello jarvis")
        self.assertIn("hello", res_greet.lower())

        # Test generic fallback
        res_other = client.generate_response("what is the weather?")
        self.assertIn("offline mode", res_other.lower())
        self.assertNotIn("api key is missing", res_other.lower())

    @patch('google.generativeai.GenerativeModel')
    @patch('google.generativeai.configure')
    def test_successful_response(self, mock_configure, mock_model_class):
        """Verifies normal response generation using the mocked Gemini API."""
        mock_model = MagicMock()
        mock_chat = MagicMock()
        mock_response = MagicMock()

        mock_response.text = " This is a voice-optimized response from Gemini. "
        mock_chat.send_message.return_value = mock_response
        mock_model.start_chat.return_value = mock_chat
        mock_model_class.return_value = mock_model

        client = GeminiClient(api_key="dummy_api_key")
        res = client.generate_response("Hi there", history_context=[])

        mock_configure.assert_called_once_with(api_key="dummy_api_key")
        mock_model.start_chat.assert_called_once_with(history=[])
        mock_chat.send_message.assert_called_once_with("Hi there")
        self.assertEqual(res, "This is a voice-optimized response from Gemini.")

    @patch('google.generativeai.GenerativeModel')
    @patch('google.generativeai.configure')
    @patch('time.sleep')
    def test_retry_on_failure(self, mock_sleep, mock_configure, mock_model_class):
        """Verifies that the retry logic triggers upon API errors and succeeds eventually."""
        mock_model = MagicMock()
        mock_chat = MagicMock()
        mock_response = MagicMock()

        mock_response.text = "Success after error."
        mock_chat.send_message.side_effect = [Exception("API Timeout"), mock_response]
        mock_model.start_chat.return_value = mock_chat
        mock_model_class.return_value = mock_model

        client = GeminiClient(api_key="dummy_key")
        res = client.generate_response("Try again")

        self.assertEqual(res, "Success after error.")
        self.assertEqual(mock_chat.send_message.call_count, 2)
        mock_sleep.assert_called_once_with(1.0)

    @patch('google.generativeai.GenerativeModel')
    @patch('google.generativeai.configure')
    @patch('time.sleep')
    def test_all_retries_fail(self, mock_sleep, mock_configure, mock_model_class):
        """Verifies that client returns clean offline error message if all retries fail."""
        mock_model = MagicMock()
        mock_chat = MagicMock()

        mock_chat.send_message.side_effect = Exception("API Outage")
        mock_model.start_chat.return_value = mock_chat
        mock_model_class.return_value = mock_model

        client = GeminiClient(api_key="dummy_key")
        res = client.generate_response("Force failure")

        self.assertIn("offline mode", res.lower())
        self.assertNotIn("api key", res.lower())
        self.assertEqual(mock_chat.send_message.call_count, 3)

if __name__ == "__main__":
    unittest.main()
