import unittest
from core.multi_command_parser import multi_command_parser, StructuredMultiAction
from core.intent_engine import intent_engine

class TestMultiActionCommands(unittest.TestCase):
    def test_multi_action_split_and_structure(self):
        # 1. "Open Chrome and search for wellmeds.in"
        res = multi_command_parser.parse_structured("open Chrome and search for wellmeds.in")
        self.assertIsInstance(res, StructuredMultiAction)
        self.assertEqual(len(res.actions), 2)
        self.assertEqual(res.actions[0]["type"], "open_app")
        self.assertEqual(res.actions[0]["target"], "chrome")
        self.assertEqual(res.actions[1]["type"], "web_search")
        self.assertEqual(res.actions[1]["query"], "wellmeds.in")

        # 2. "Open Chrome and search Google for Python"
        res2 = multi_command_parser.parse_structured("open Chrome and search Google for Python")
        self.assertEqual(len(res2.actions), 2)
        self.assertEqual(res2.actions[0]["target"], "chrome")
        self.assertEqual(res2.actions[1]["provider"], "google")
        self.assertEqual(res2.actions[1]["query"].lower(), "python")

        # 3. "Open YouTube and ChatGPT"
        res3 = multi_command_parser.parse_structured("open YouTube and ChatGPT")
        self.assertEqual(len(res3.actions), 2)
        self.assertEqual(res3.actions[0]["target"], "youtube")
        self.assertEqual(res3.actions[1]["target"], "chatgpt")

        # 4. "Open Spotify and Chrome"
        res4 = multi_command_parser.parse_structured("open Spotify and Chrome")
        self.assertEqual(len(res4.actions), 2)
        self.assertEqual(res4.actions[0]["target"], "spotify")
        self.assertEqual(res4.actions[1]["target"], "chrome")

        # 5. "Open Chrome, search for Python tutorials, and then open YouTube"
        res5 = multi_command_parser.parse_structured("open Chrome, search for Python tutorials, and then open YouTube")
        self.assertEqual(len(res5.actions), 3)

    def test_conversational_and_noise_not_split(self):
        # "okay and please" should not split into multiple commands
        res = multi_command_parser.parse_structured("okay and please")
        self.assertFalse(res.is_multi)

        res2 = multi_command_parser.parse_structured("yes and yes")
        self.assertFalse(res2.is_multi)

        res3 = multi_command_parser.parse_structured("hello jarvis")
        self.assertFalse(res3.is_multi)

    def test_intent_engine_domain_urls(self):
        # "open wellmeds.in" should resolve to open_website / open_url
        intent, target = intent_engine.classify_intent("open wellmeds.in")
        self.assertIn(intent, ["open_website", "open_url"])
        self.assertIn("wellmeds.in", target)

        # "open google.com"
        intent, target = intent_engine.classify_intent("open google.com")
        self.assertIn(intent, ["open_website", "open_url"])
        self.assertIn("google.com", target)

        # "open youtube.com"
        intent, target = intent_engine.classify_intent("open youtube.com")
        self.assertIn(intent, ["open_website", "open_url"])
        self.assertIn("youtube.com", target)

    def test_speaker_test_intent(self):
        intent, target = intent_engine.classify_intent("Jarvis, test your speakers")
        self.assertEqual(intent, "test_speakers")

        intent2, target2 = intent_engine.classify_intent("test audio output")
        self.assertEqual(intent2, "test_speakers")

if __name__ == "__main__":
    unittest.main()
