import unittest
from unittest.mock import MagicMock, patch
from core.intent_engine import IntentEngine
from core.os.browser_manager import BrowserManager
from core.local_response_engine import LocalResponseEngine
from modules.system.executor import CommandExecutor

class TestChromeTabAndWindow(unittest.TestCase):
    """Unit tests for Chrome New Tab and Chrome New Independent Window command understanding and execution."""

    def setUp(self):
        self.engine = IntentEngine()
        self.response_engine = LocalResponseEngine()
        self.executor = CommandExecutor()

    # =========================================================================
    # 1. OPEN_NEW_CHROME_TAB POSITIVE VARIATIONS
    # =========================================================================
    def test_open_new_chrome_tab_variations(self):
        variations = [
            "Open a new tab",
            "Open a new Chrome tab",
            "Open another tab",
            "Create a new tab",
            "Start a new tab",
            "Can you open a new tab?",
            "Could you open a new tab for me?",
            "Jarvis, open a new tab",
            "Hey Jarvis, open another Chrome tab",
            "Please open a fresh tab",
            "Give me a new tab",
            "I need a new tab",
            "Make a new tab in Chrome",
            "Open one more tab",
            "Open another browser tab",
            "New Chrome tab",
            "Chrome, new tab",
            "Hey Jarvis, could you please open a new tab for me?",
            "Jarvis, can you make another tab in Chrome?",
            "Would you open a new Chrome tab?"
        ]
        for phrase in variations:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "open_new_chrome_tab")
                self.assertEqual(res["target"], "chrome")
                self.assertGreaterEqual(res["confidence"], 0.95)

    # =========================================================================
    # 2. OPEN_NEW_CHROME_WINDOW POSITIVE VARIATIONS
    # =========================================================================
    def test_open_new_chrome_window_variations(self):
        variations = [
            "Open a new Chrome",
            "Open another Chrome",
            "Open another Chrome window",
            "Open a new Chrome window",
            "Launch another Chrome",
            "Start another Chrome window",
            "Create a new Chrome window",
            "Open Chrome in another window",
            "Can you open another Chrome window?",
            "Could you launch a new Chrome window?",
            "Jarvis, open another Chrome",
            "Hey Jarvis, start a new Chrome window",
            "I want another Chrome window",
            "Give me a fresh Chrome window",
            "Open a separate Chrome window",
            "Start a separate Chrome",
            "Launch a second Chrome window"
        ]
        for phrase in variations:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "open_new_chrome_window")
                self.assertEqual(res["target"], "chrome")
                self.assertGreaterEqual(res["confidence"], 0.95)

    # =========================================================================
    # 3. DISAMBIGUATION: TAB vs WINDOW vs APP OPEN vs APP CLOSE
    # =========================================================================
    def test_disambiguation(self):
        cases = [
            ("Open a new tab", "open_new_chrome_tab", "chrome"),
            ("Open another tab in Chrome", "open_new_chrome_tab", "chrome"),
            ("Open another Chrome", "open_new_chrome_window", "chrome"),
            ("Open a new Chrome window", "open_new_chrome_window", "chrome"),
            ("Open Chrome", "open_app", "chrome"),
            ("Close Chrome", "close_app", "chrome"),
            ("Launch Chrome", "open_app", "chrome"),
            ("Shut down Chrome", "close_app", "chrome")
        ]
        for phrase, expected_intent, expected_target in cases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], expected_intent)
                self.assertEqual(res["target"], expected_target)

    # =========================================================================
    # 4. NEGATIVE TESTS: INFORMATIONAL QUESTIONS MUST NOT TRIGGER ACTIONS
    # =========================================================================
    def test_informational_questions(self):
        questions = [
            "How do I open another Chrome?",
            "What is Chrome?",
            "Why should I use Chrome?",
            "Tell me about Chrome windows.",
            "How do Chrome tabs work?",
            "Can you explain how to create a new Chrome window?"
        ]
        for q in questions:
            with self.subTest(question=q):
                res = self.engine.parse(q)
                self.assertIn(res["intent"], ["question", "conversation"])
                self.assertNotIn(res["intent"], ["open_new_chrome_tab", "open_new_chrome_window", "open_app", "close_app"])

    # =========================================================================
    # 5. RESPONSE GENERATION
    # =========================================================================
    def test_responses(self):
        tab_node = {"intent": "open_new_chrome_tab", "target": "chrome"}
        tab_resp = self.response_engine.format_intent_response(tab_node)
        self.assertIn("Opening a new tab.", tab_resp)

        win_node = {"intent": "open_new_chrome_window", "target": "chrome"}
        win_resp = self.response_engine.format_intent_response(win_node)
        self.assertIn("Opening another Chrome window.", win_resp)

    # =========================================================================
    # 6. EXECUTOR ROUTING
    # =========================================================================
    def test_executor_routes_to_browser_manager(self):
        with patch.object(self.executor.browser_mgr, "open_new_chrome_tab", return_value={"success": True, "message": "Opening a new tab."}) as mock_tab:
            res = self.executor.execute({"intent": "open_new_chrome_tab", "target": "chrome"})
            self.assertTrue(res["success"])
            self.assertEqual(res["message"], "Opening a new tab.")
            mock_tab.assert_called_once()

        with patch.object(self.executor.browser_mgr, "open_new_chrome_window", return_value={"success": True, "message": "Opening another Chrome window."}) as mock_win:
            res = self.executor.execute({"intent": "open_new_chrome_window", "target": "chrome"})
            self.assertTrue(res["success"])
            self.assertEqual(res["message"], "Opening another Chrome window.")
            mock_win.assert_called_once()

if __name__ == "__main__":
    unittest.main()
