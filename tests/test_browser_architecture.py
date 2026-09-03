import unittest
from unittest.mock import patch, MagicMock
from core.os.browser_manager import BrowserManager
from core.intent_engine import IntentEngine

class TestBrowserArchitecture(unittest.TestCase):

    def setUp(self):
        self.bm = BrowserManager()
        self.intent_engine = IntentEngine()

    def test_search_url_builder_providers(self):
        self.assertEqual(self.bm.build_search_url("google", "test"), "https://www.google.com/search?q=test")
        self.assertEqual(self.bm.build_search_url("youtube", "test"), "https://www.youtube.com/results?search_query=test")
        self.assertEqual(self.bm.build_search_url("github", "test"), "https://github.com/search?q=test")
        self.assertEqual(self.bm.build_search_url("reddit", "test"), "https://www.reddit.com/search/?q=test")
        self.assertEqual(self.bm.build_search_url("stackoverflow", "test"), "https://stackoverflow.com/search?q=test")

    def test_url_encoding_handling(self):
        url = self.bm.build_search_url("google", "React & Redux?")
        self.assertEqual(url, "https://www.google.com/search?q=React+%26+Redux%3F")

    def test_fallback_browser_resolution(self):
        with patch.object(self.bm, "is_browser_available", side_effect=lambda b: b == "default"):
            resolved, err = self.bm.resolve_target_browser("chrome")
            self.assertEqual(resolved, "default")
            self.assertIsNone(err)

    def test_disabled_fallback_behavior(self):
        with patch.object(self.bm, "is_browser_available", return_value=False):
            self.bm.browser_config["fallback_browser"] = False
            resolved, err = self.bm.resolve_target_browser("chrome")
            self.assertIsNone(resolved)
            self.assertIn("Chrome isn't installed", err)

    def test_search_convenience_methods(self):
        with patch.object(self.bm, "search", return_value={"success": True, "message": "Searching Google."}) as mock_s:
            res = self.bm.search_google("Python")
            mock_s.assert_called_with("Python", provider="google")
            self.assertTrue(res["success"])

if __name__ == "__main__":
    unittest.main()
