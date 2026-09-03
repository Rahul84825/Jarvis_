import unittest
from unittest.mock import patch, MagicMock
from core.os.browser_manager import BrowserManager
from core.intent_engine import IntentEngine
from core.command_normalizer import CommandNormalizer

class TestBrowserManager(unittest.TestCase):

    def setUp(self):
        self.bm = BrowserManager()
        self.intent_engine = IntentEngine()
        self.normalizer = CommandNormalizer()

    def test_build_search_url_google(self):
        url = self.bm.build_search_url("google", "Python decorators")
        self.assertEqual(url, "https://www.google.com/search?q=Python+decorators")

    def test_build_search_url_youtube(self):
        url = self.bm.build_search_url("youtube", "CodeWithHarry Python")
        self.assertEqual(url, "https://www.youtube.com/results?search_query=CodeWithHarry+Python")

    def test_build_search_url_github(self):
        url = self.bm.build_search_url("github", "jarvis assistant")
        self.assertEqual(url, "https://github.com/search?q=jarvis+assistant")

    def test_build_search_url_encoding_special_chars(self):
        url = self.bm.build_search_url("google", "C++ & Java?")
        self.assertEqual(url, "https://www.google.com/search?q=C%2B%2B+%26+Java%3F")

    def test_build_search_url_non_english(self):
        url = self.bm.build_search_url("google", "नमस्ते जावास्क्रिप्ट")
        self.assertIn("https://www.google.com/search?q=", url)

    def test_intent_parsing_google_search(self):
        node = self.intent_engine.parse("Search Google for Python tutorials")
        self.assertEqual(node["intent"], "web_search")
        self.assertEqual(node["provider"], "google")
        self.assertEqual(node["target"], "python tutorials")

    def test_intent_parsing_youtube_search(self):
        node = self.intent_engine.parse("Search YouTube for CodeWithHarry")
        self.assertEqual(node["intent"], "web_search")
        self.assertEqual(node["provider"], "youtube")
        self.assertEqual(node["target"], "codewithharry")

    def test_intent_parsing_chrome_alias_search(self):
        node = self.intent_engine.parse("Search Chrome for React tutorials")
        self.assertEqual(node["intent"], "web_search")
        self.assertEqual(node["provider"], "google")
        self.assertEqual(node["target"], "react tutorials")

    def test_intent_parsing_find_on_youtube(self):
        node = self.intent_engine.parse("Find Python tutorials on YouTube")
        self.assertEqual(node["intent"], "web_search")
        self.assertEqual(node["provider"], "youtube")
        self.assertEqual(node["target"], "python tutorials")

    def test_multi_command_clause_splitting(self):
        from core.multi_command_parser import multi_command_parser
        sub_cmds = multi_command_parser.parse("Open Chrome and search Google for Python")
        self.assertEqual(len(sub_cmds), 2)
        self.assertIn("open chrome", sub_cmds[0].lower())
        self.assertIn("search google for python", sub_cmds[1].lower())

    @patch("core.platform.platform_manager.platform_manager.open_browser", return_value=True)
    def test_search_execution(self, mock_open):
        res = self.bm.search("Python decorators", provider="google")
        self.assertTrue(res["success"])
        self.assertEqual(res["operation"], "web_search")
        self.assertIn("Searching Google.", res["message"])

if __name__ == "__main__":
    unittest.main()
