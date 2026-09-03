import unittest
from core.local_response_engine import LocalResponseEngine

class TestResponseBrevity(unittest.TestCase):

    def setUp(self):
        self.engine = LocalResponseEngine()

    def test_open_chrome_brevity(self):
        node = {"intent": "open_app", "target": "chrome"}
        resp = self.engine.format_intent_response(node)
        self.assertLessEqual(len(resp.split()), 3)

    def test_open_vscode_brevity(self):
        node = {"intent": "open_app", "target": "vscode"}
        resp = self.engine.format_intent_response(node)
        self.assertLessEqual(len(resp.split()), 4)

    def test_screenshot_brevity(self):
        node = {"intent": "screenshot", "action": "take_screenshot"}
        resp = self.engine.format_intent_response(node)
        self.assertLessEqual(len(resp.split()), 3)

    def test_volume_up_brevity(self):
        node = {"intent": "system_control", "action": "volume_up"}
        resp = self.engine.format_intent_response(node)
        self.assertLessEqual(len(resp.split()), 2)

    def test_volume_down_brevity(self):
        node = {"intent": "system_control", "action": "volume_down"}
        resp = self.engine.format_intent_response(node)
        self.assertLessEqual(len(resp.split()), 2)

    def test_mute_brevity(self):
        node = {"intent": "system_control", "action": "mute"}
        resp = self.engine.format_intent_response(node)
        self.assertEqual(resp, "Muted.")

    def test_unmute_brevity(self):
        node = {"intent": "system_control", "action": "unmute"}
        resp = self.engine.format_intent_response(node)
        self.assertEqual(resp, "Unmuted.")

    def test_lock_pc_brevity(self):
        node = {"intent": "system_control", "action": "lock_pc"}
        resp = self.engine.format_intent_response(node)
        self.assertLessEqual(len(resp.split()), 3)

if __name__ == "__main__":
    unittest.main()
