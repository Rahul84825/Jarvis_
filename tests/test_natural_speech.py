import unittest
from core.response_manager import ResponseManager

class TestNaturalSpeech(unittest.TestCase):

    def setUp(self):
        self.rm = ResponseManager(speaker=None)

    def test_wake_responses_natural(self):
        res = self.rm.wake_response(speak=False)
        self.assertIn(res["spoken_text"], self.rm.wake_responses)

    def test_greeting_responses(self):
        res_am = self.rm.greeting("good morning", speak=False)
        self.assertIn("Good morning", res_am["spoken_text"])

        res_namaste = self.rm.greeting("namaste", speak=False)
        self.assertIn("Namaste", res_namaste["spoken_text"])

    def test_success_responses(self):
        res_app = self.rm.success("Launched Chrome successfully.", speak=False)
        self.assertIn("Chrome", res_app["spoken_text"])

        res_ss = self.rm.success("Screenshot saved.", speak=False)
        self.assertEqual(res_ss["spoken_text"], "Done. Screenshot saved.")

    def test_failure_responses(self):
        res_fail_gen = self.rm.failure("Failed to launch target.", speak=False)
        self.assertEqual(res_fail_gen["spoken_text"], "I couldn't complete that.")

        res_fail_unk = self.rm.failure("Unknown application target.", speak=False)
        self.assertEqual(res_fail_unk["spoken_text"], "I'm not sure what you meant.")

if __name__ == "__main__":
    unittest.main()
