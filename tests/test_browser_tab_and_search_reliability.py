"""Regression and reliability tests for search responses, targeted browser tab control,
and TTS amplitude callback handling.
"""

import unittest
from unittest.mock import MagicMock, patch

from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.os.browser_manager import BrowserManager
from core.os.cdp_client import CDPClient
from core.response_registry import response_registry, CommandOutcome
from modules.system.executor import CommandExecutor


class TestBrowserTabAndSearchReliability(unittest.TestCase):

    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.browser_mgr = BrowserManager()
        self.executor = CommandExecutor()

    # -------------------------------------------------------------
    # 1. TTS Amplitude Callback Without TypeError
    # -------------------------------------------------------------
    def test_tts_amplitude_callback_no_typeerror(self):
        """Verifies that TTSManager._trigger_callback accepts amplitude arguments cleanly."""
        from core.tts.tts_manager import TTSManager
        tts = TTSManager()
        received_amps = []

        def amp_cb(val):
            received_amps.append(val)

        # Trigger amplitude callback with 30ms chunk value and 0.0 stop value
        tts._trigger_callback(amp_cb, 0.45)
        tts._trigger_callback(amp_cb, 0.0)

        self.assertEqual(received_amps, [0.45, 0.0])

    # -------------------------------------------------------------
    # 2. Targeted Tab Close Intent Parsing
    # -------------------------------------------------------------
    def test_close_named_tab_intent_parsing(self):
        """Verifies 'close the Python tutorials tab' routes to browser_tab_control, NOT close_app."""
        phrase = "Jarvis, close the Python tutorials tab"
        norm = self.normalizer.normalize(phrase)["normalized"]
        node = self.intent_engine.parse(norm, raw_text=phrase)

        self.assertEqual(node["intent"], "browser_tab_control")
        self.assertEqual(node["action"], "close_tab")
        self.assertEqual(node["tab_target"].lower(), "python tutorials")

    def test_switch_named_tab_intent_parsing(self):
        """Verifies 'switch to the GitHub tab' routes to browser_tab_control switch_tab."""
        phrase = "Jarvis, switch to the GitHub tab"
        norm = self.normalizer.normalize(phrase)["normalized"]
        node = self.intent_engine.parse(norm, raw_text=phrase)

        self.assertEqual(node["intent"], "browser_tab_control")
        self.assertEqual(node["action"], "switch_tab")
        self.assertEqual(node["tab_target"].lower(), "github")

    def test_list_open_tabs_intent_parsing(self):
        """Verifies 'list open tabs' routes to browser_tab_control list_tabs."""
        phrase = "Jarvis, list open tabs"
        norm = self.normalizer.normalize(phrase)["normalized"]
        node = self.intent_engine.parse(norm, raw_text=phrase)

        self.assertEqual(node["intent"], "browser_tab_control")
        self.assertEqual(node["action"], "list_tabs")

    def test_close_active_tab_intent_parsing(self):
        """Verifies 'close tab' routes to active tab close."""
        phrase = "Jarvis, close tab"
        norm = self.normalizer.normalize(phrase)["normalized"]
        node = self.intent_engine.parse(norm, raw_text=phrase)

        self.assertEqual(node["intent"], "browser_tab_control")
        self.assertEqual(node["action"], "close_tab")
        self.assertEqual(node["tab_target"], "active")

    # -------------------------------------------------------------
    # 3. Targeted Tab Resolution via CDP
    # -------------------------------------------------------------
    @patch.object(CDPClient, "is_available", return_value=True)
    @patch.object(CDPClient, "list_tabs")
    @patch.object(CDPClient, "close_tab", return_value=True)
    def test_targeted_tab_close_success(self, mock_close, mock_list, mock_avail):
        """Verifies matching and closing a specific tab via CDP."""
        mock_list.return_value = [
            {"id": "tab1", "title": "Google Search", "url": "https://google.com"},
            {"id": "tab2", "title": "Python Tutorials - YouTube", "url": "https://youtube.com/watch"},
            {"id": "tab3", "title": "GitHub Dashboard", "url": "https://github.com"}
        ]

        res = self.browser_mgr.close_tab(target="Python Tutorials")
        self.assertTrue(res["success"])
        self.assertIn("Closed the 'Python Tutorials - YouTube' tab", res["message"])
        mock_close.assert_called_once_with("tab2")

    @patch.object(CDPClient, "is_available", return_value=True)
    @patch.object(CDPClient, "list_tabs")
    def test_targeted_tab_close_ambiguous(self, mock_list, mock_avail):
        """Verifies ambiguous tab matches report clarification prompt."""
        mock_list.return_value = [
            {"id": "tab1", "title": "Python 3 Documentation", "url": "https://docs.python.org"},
            {"id": "tab2", "title": "Python Tutorials - YouTube", "url": "https://youtube.com"},
        ]

        res = self.browser_mgr.close_tab(target="Python")
        self.assertFalse(res["success"])
        self.assertTrue(res.get("ambiguous", False))
        self.assertIn("Multiple tabs matched", res["message"])

    @patch.object(CDPClient, "is_available", return_value=True)
    @patch.object(CDPClient, "list_tabs")
    def test_targeted_tab_close_no_match(self, mock_list, mock_avail):
        """Verifies when no tab matches, truthful failure is returned."""
        mock_list.return_value = [
            {"id": "tab1", "title": "Google Search", "url": "https://google.com"}
        ]

        res = self.browser_mgr.close_tab(target="Nonexistent Tab XYZ")
        self.assertFalse(res["success"])
        self.assertIn("No tab matching 'Nonexistent Tab XYZ' was found", res["message"])

    @patch.object(CDPClient, "is_available", return_value=False)
    def test_targeted_tab_close_cdp_offline_safety(self, mock_avail):
        """Verifies that when CDP is offline, JARVIS does NOT close the active tab blindly."""
        res = self.browser_mgr.close_tab(target="Python Tutorials")
        self.assertFalse(res["success"])
        self.assertTrue(res.get("cdp_required", False))
        self.assertIn("--remote-debugging-port=9222", res["message"])

    # -------------------------------------------------------------
    # 4. Truthful Search Outcome Semantics
    # -------------------------------------------------------------
    @patch("core.platform.platform_manager.PlatformManager.open_browser", return_value=True)
    def test_search_outcome_semantics_youtube(self, mock_open):
        """Verifies search outcome truthfully states search results were opened."""
        res = self.browser_mgr.search("Python tutorials", provider="youtube")
        self.assertTrue(res["success"])
        self.assertIn("I opened YouTube search results for 'Python tutorials'.", res["message"])

        intent_node = {
            "intent": "web_search",
            "action": "search",
            "provider": "youtube",
            "query": "Python tutorials",
            "target": "Python tutorials"
        }
        spoken = response_registry.get_success_response(intent_node, res)
        self.assertIn("I opened YouTube search results for 'Python tutorials'.", spoken)

    @patch("core.platform.platform_manager.PlatformManager.open_browser", return_value=True)
    def test_search_outcome_semantics_google(self, mock_open):
        """Verifies Google search outcome truthfully states search results were opened."""
        res = self.browser_mgr.search("today's weather", provider="google")
        self.assertTrue(res["success"])
        self.assertIn("I opened Google search results for 'today's weather'.", res["message"])


if __name__ == "__main__":
    unittest.main()
