import unittest
from core.intent_engine import IntentEngine

class TestIntentEngine(unittest.TestCase):
    def setUp(self):
        self.engine = IntentEngine()

    def test_empty_input(self):
        """Verifies that empty or whitespace-only input returns unknown intent."""
        res1 = self.engine.parse("")
        self.assertEqual(res1["intent"], "unknown")

        res2 = self.engine.parse("   ")
        self.assertEqual(res2["intent"], "unknown")

    def test_system_control_shutdown(self):
        """Verifies parsing of shutdown-related phrases."""
        phrases = ["shutdown the pc", "shutdown computer", "turn off pc", "turn off computer"]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "system_control")
                self.assertEqual(res["action"], "shutdown_pc")

    def test_system_control_restart(self):
        """Verifies parsing of restart-related phrases."""
        phrases = ["restart the pc", "restart computer", "reboot pc", "reboot computer"]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "system_control")
                self.assertEqual(res["action"], "restart_pc")

    def test_system_control_lock(self):
        """Verifies parsing of lock-related phrases."""
        phrases = ["lock the pc", "lock computer", "lock screen", "lock system", "Lock my PC", "Please lock my computer"]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "system_control")
                self.assertEqual(res["action"], "lock_pc")

    def test_open_app(self):
        """Verifies parsing of 'open <app>' intent."""
        test_cases = [
            ("Open Chrome", "chrome"),
            ("Launch Notepad", "notepad"),
            ("run firefox", "firefox"),
            ("start paint.exe", "paint.exe"),
            ("Could you launch Chrome", "chrome"),
            ("Open Visual Studio Code", "vscode")
        ]
        for phrase, expected in test_cases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "open_app")
                self.assertEqual(res["target"], expected)

    def test_questions(self):
        """Verifies parsing of queries starting with question words or ending with question marks."""
        phrases = [
            "What is the weather today?",
            "who is the president of France",
            "how to build an assistant",
            "when is dinner",
            "where are my keys",
            "why is the sky blue",
            "which way to go"
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertIn(res["intent"], ["question", "conversation"])

    def test_conversation(self):
        """Verifies parsing of conversational greetings and pleasantries."""
        phrases = [
            "hello", "hi", "hey", "good morning", "good afternoon",
            "good evening", "thanks", "thank you", "bye", "goodbye",
            "how are you", "what's up"
        ]
    def test_conversation(self):
        """Verifies parsing of conversational greetings and pleasantries."""
        phrases = [
            "hello", "hi", "hey", "good morning", "good afternoon",
            "good evening", "thanks", "thank you", "bye", "goodbye",
            "how are you", "what's up"
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertIn(res["intent"], ["conversation", "greeting"])

    def test_fallback_routing(self):
        """Verifies that unrecognized phrasings fallback gracefully to conversation."""
        res = self.engine.parse("random query that does not match anything")
        self.assertEqual(res["intent"], "conversation")

    def test_phonetic_aliases_and_fillers(self):
        """Verifies parsing with leading punctuation, phonetic aliases, and filler words."""
        res1 = self.engine.parse("open note pad")
        self.assertEqual(res1["intent"], "open_app")
        self.assertEqual(res1["target"], "notepad")

        res2 = self.engine.parse("open room")
        self.assertEqual(res2["intent"], "open_app")
        self.assertEqual(res2["target"], "chrome")

        res3 = self.engine.parse("and Jarvis, open note pad")
        self.assertEqual(res3["intent"], "open_app")
        self.assertEqual(res3["target"], "notepad")

        res5 = self.engine.parse("open downloads folder")
        self.assertEqual(res5["intent"], "file_access")
        self.assertEqual(res5["action"], "open_folder")
        self.assertEqual(res5["target"], "downloads")

        res6 = self.engine.parse("Jarvis, open you tube")
        self.assertEqual(res6["intent"], "open_website")
        self.assertEqual(res6["target"], "youtube")

        res7 = self.engine.parse("open vs code")
        self.assertEqual(res7["intent"], "open_app")
        self.assertEqual(res7["target"], "vscode")

        res8 = self.engine.parse("open krone")
        self.assertEqual(res8["intent"], "open_app")
        self.assertEqual(res8["target"], "chrome")

if __name__ == "__main__":
    unittest.main()
