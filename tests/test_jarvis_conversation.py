import unittest
from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.response_manager import ResponseManager
from modules.system.executor import CommandExecutor

class TestJarvisConversation(unittest.TestCase):
    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.response_manager = ResponseManager()
        self.executor = CommandExecutor()

    def test_jarvis_wake_word_stripping(self):
        phrases = [
            ("Jarvis open Chrome", "open chrome"),
            ("Hey Jarvis open VS Code", "open vscode"),
            ("Hello Jarvis lock my PC", "lock computer"),
            ("Namaste Jarvis take screenshot", "take screenshot"),
            ("Yo Jarvis volume up", "volume up"),
            ("Hey buddy open downloads", "open downloads")
        ]
        for raw, expected in phrases:
            with self.subTest(raw=raw):
                res = self.normalizer.normalize(raw)
                self.assertEqual(res["normalized"], expected)

    def test_greet_intent(self):
        greetings = ["Hello", "Hi Jarvis", "Namaste Jarvis", "Good Morning", "Good Night", "Yo Jarvis", "Hey buddy"]
        for g in greetings:
            with self.subTest(greeting=g):
                intent_node = self.intent_engine.parse(g)
                self.assertEqual(intent_node["intent"], "greeting")
                res = self.response_manager.greeting(g)
                self.assertTrue(len(res["spoken_text"]) > 0)

    def test_identity_intent(self):
        queries = ["Who are you?", "Who made you?", "Who built you?", "Who created you?", "Who developed you?", "Who owns you?", "Who is your developer?"]
        for q in queries:
            with self.subTest(query=q):
                intent_node = self.intent_engine.parse(q)
                self.assertEqual(intent_node["intent"], "identity")
                exec_res = self.executor.execute(intent_node)
                self.assertTrue(exec_res["success"])
                self.assertIn("Jarvis", exec_res["message"])
                self.assertIn("Active Gamer", exec_res["message"])

    def test_help_intent(self):
        queries = ["Help", "Help me", "What can you do", "Show commands", "Commands", "Capabilities"]
        for q in queries:
            with self.subTest(query=q):
                intent_node = self.intent_engine.parse(q)
                self.assertEqual(intent_node["intent"], "help")
                exec_res = self.executor.execute(intent_node)
                self.assertTrue(exec_res["success"])
                self.assertIn("Applications", exec_res["message"])
                self.assertIn("System", exec_res["message"])

    def test_about_intent(self):
        queries = ["About", "About Jarvis", "Version", "System Info"]
        for q in queries:
            with self.subTest(query=q):
                intent_node = self.intent_engine.parse(q)
                self.assertEqual(intent_node["intent"], "about")
                exec_res = self.executor.execute(intent_node)
                self.assertTrue(exec_res["success"])
                self.assertIn("Version 1.1", exec_res["message"])

    def test_web_links_intent(self):
        websites = [
            ("Open YouTube", "youtube"),
            ("Open Google", "google"),
            ("Open GitHub", "github"),
            ("Open Gmail", "gmail"),
            ("Open ChatGPT", "chatgpt"),
            ("Open Claude", "claude"),
            ("Open Gemini", "gemini"),
            ("Open Spotify", "spotify"),
            ("Open Netflix", "netflix"),
            ("Open Discord", "discord")
        ]
        for phrase, expected_target in websites:
            with self.subTest(phrase=phrase):
                intent_node = self.intent_engine.parse(phrase)
                self.assertEqual(intent_node["intent"], "open_website")
                self.assertEqual(intent_node["target"], expected_target)

    def test_fuzzy_shortcuts(self):
        shortcuts = [
            ("Chrome", "open_app", "chrome"),
            ("VS", "open_app", "vscode"),
            ("Screenshot", "screenshot", "take_screenshot"),
            ("Downloads", "file_access", "downloads"),
            ("Lock", "system_control", "lock_pc")
        ]
        for raw, expected_intent, expected_val in shortcuts:
            with self.subTest(raw=raw):
                norm = self.normalizer.normalize(raw)["normalized"]
                intent_node = self.intent_engine.parse(norm)
                self.assertEqual(intent_node["intent"], expected_intent)

if __name__ == "__main__":
    unittest.main()
