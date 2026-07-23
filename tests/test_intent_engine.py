import unittest
from core.intent_engine import IntentEngine

class TestIntentEngine(unittest.TestCase):
    def setUp(self):
        self.engine = IntentEngine()

    def test_empty_input(self):
        """Verifies that empty or whitespace-only input returns unknown intent."""
        res1 = self.engine.parse("")
        self.assertEqual(res1["intent"], "unknown")
        self.assertEqual(res1["query"], "")

        res2 = self.engine.parse("   ")
        self.assertEqual(res2["intent"], "unknown")
        self.assertEqual(res2["query"], "")


    def test_system_action_shutdown(self):
        """Verifies parsing of shutdown-related phrases into system actions."""
        phrases = ["shutdown the pc", "shutdown computer", "turn off pc", "turn off computer"]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "system_action")
                self.assertEqual(res["action"], "shutdown")

    def test_system_action_restart(self):
        """Verifies parsing of restart-related phrases."""
        phrases = ["restart the pc", "restart computer", "reboot pc", "reboot computer"]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "system_action")
                self.assertEqual(res["action"], "restart")

    def test_system_action_lock(self):
        """Verifies parsing of lock-related phrases."""
        phrases = ["lock the pc", "lock computer", "lock screen", "lock system"]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "system_action")
                self.assertEqual(res["action"], "lock")

    def test_open_app(self):
        """Verifies parsing of 'open <app>' intent."""
        test_cases = [
            ("Open Chrome", "chrome"),
            ("Launch Notepad", "notepad"),
            ("run firefox", "firefox"),
            ("start paint.exe", "paint.exe"),
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
            "which way to go",
            "tell me a story",
            "show me the files",
            "can you help me",
            "could you do this",
            "is there any milk left",
            "Do you know the way?"
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                res = self.engine.parse(phrase)
                self.assertEqual(res["intent"], "question")
                self.assertEqual(res["query"], phrase)

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
                self.assertEqual(res["intent"], "conversation")
                self.assertEqual(res["query"], phrase)

    def test_fallback_routing(self):
        """Verifies that unrecognized phrasings fallback gracefully to conversation."""
        res = self.engine.parse("random query that does not match anything")
        self.assertEqual(res["intent"], "conversation")
        self.assertEqual(res["query"], "random query that does not match anything")

    def test_phonetic_aliases_and_fillers(self):
        """Verifies parsing with leading punctuation, phonetic aliases, and filler words."""
        res1 = self.engine.parse("open note pad")
        self.assertEqual(res1["intent"], "open_app")
        self.assertEqual(res1["target"], "notepad")

        res2 = self.engine.parse("open-cru")
        self.assertEqual(res2["intent"], "open_app")
        self.assertEqual(res2["target"], "chrome")

        res3 = self.engine.parse("and Jarvis, open note pad")
        self.assertEqual(res3["intent"], "open_app")
        self.assertEqual(res3["target"], "notepad")

        res4 = self.engine.parse(", open room")
        self.assertEqual(res4["intent"], "open_app")
        self.assertEqual(res4["target"], "chrome")

        res5 = self.engine.parse("open downloads folder")
        self.assertEqual(res5["intent"], "file_access")
        self.assertEqual(res5["action"], "open_folder")
        self.assertEqual(res5["target"], "downloads")

if __name__ == "__main__":
    unittest.main()
