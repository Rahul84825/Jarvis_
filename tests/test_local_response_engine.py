import unittest
from core.local_response_engine import LocalResponseEngine
from config import config

class TestLocalResponseEngine(unittest.TestCase):

    def setUp(self):
        self.engine = LocalResponseEngine()

    def test_wake_response_brevity(self):
        resp = self.engine.get_wake_response()
        self.assertIn(resp, ["Yes?", "I'm listening.", "Go ahead."])
        self.assertLessEqual(len(resp.split()), 3)

    def test_identity_formatting(self):
        resp = self.engine.get_identity_response()
        self.assertIn(getattr(config, "assistant_name", "Jarvis"), resp)

    def test_help_response(self):
        resp = self.engine.get_help_response()
        self.assertIn("open applications", resp.lower())
        self.assertLessEqual(len(resp.split()), 30)

    def test_intent_formatting_open_app(self):
        node = {"intent": "open_app", "target": "chrome"}
        resp = self.engine.format_intent_response(node)
        self.assertIn("Chrome", resp)

    def test_intent_formatting_screenshot(self):
        node = {"intent": "screenshot", "action": "take_screenshot"}
        resp = self.engine.format_intent_response(node)
        self.assertIn("screenshot", resp.lower())

    def test_intent_formatting_volume_up(self):
        node = {"intent": "system_control", "action": "volume_up"}
        resp = self.engine.format_intent_response(node)
        self.assertEqual(resp, "Volume increased.")

    def test_intent_formatting_volume_down(self):
        node = {"intent": "system_control", "action": "volume_down"}
        resp = self.engine.format_intent_response(node)
        self.assertEqual(resp, "Volume decreased.")

    def test_intent_formatting_mute(self):
        node = {"intent": "system_control", "action": "mute"}
        resp = self.engine.format_intent_response(node)
        self.assertEqual(resp, "Muted.")

    def test_intent_formatting_unmute(self):
        node = {"intent": "system_control", "action": "unmute"}
        resp = self.engine.format_intent_response(node)
        self.assertEqual(resp, "Unmuted.")

    def test_intent_formatting_lock_pc(self):
        node = {"intent": "system_control", "action": "lock_pc"}
        resp = self.engine.format_intent_response(node)
        self.assertEqual(resp, "Locking the computer.")

    def test_intent_formatting_open_website(self):
        node = {"intent": "open_website", "target": "youtube"}
        resp = self.engine.format_intent_response(node)
        self.assertIn("YouTube", resp)

    def test_intent_formatting_file_access(self):
        node = {"intent": "file_access", "target": "downloads"}
        resp = self.engine.format_intent_response(node)
        self.assertIn("Downloads", resp)

    def test_greeting_namaste(self):
        node = {"intent": "greeting", "raw": "Namaste Jarvis"}
        resp = self.engine.format_intent_response(node)
        self.assertIn("Namaste", resp)

    def test_thank_you_response(self):
        node = {"intent": "thank_you"}
        resp = self.engine.format_intent_response(node)
        self.assertIn(resp, ["You're welcome.", "Anytime.", "Happy to help."])

    def test_goodbye_response(self):
        node = {"intent": "goodbye"}
        resp = self.engine.format_intent_response(node)
        self.assertIn(resp, ["Goodbye.", "See you later."])

    def test_unknown_query_fallback(self):
        node = {"intent": "unknown"}
        resp = self.engine.format_intent_response(node)
        self.assertIn("I'm not sure how to help with that yet", resp)

if __name__ == "__main__":
    unittest.main()
