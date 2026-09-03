import unittest
from core.local_response_engine import LocalResponseEngine

class TestMultiCommandConcatenation(unittest.TestCase):

    def setUp(self):
        self.engine = LocalResponseEngine()

    def test_single_command_summary(self):
        sub_results = [{"success": True, "message": "Calculator closed."}]
        summary = self.engine.format_multi_command_response(sub_results)
        self.assertEqual(summary, "Calculator closed.")

    def test_two_command_summary(self):
        sub_results = [
            {"success": True, "message": "Closing Calculator."},
            {"success": True, "message": "Volume increased."}
        ]
        summary = self.engine.format_multi_command_response(sub_results)
        self.assertEqual(summary, "Done. Closing Calculator., and Volume increased.")

    def test_three_command_summary(self):
        sub_results = [
            {"success": True, "message": "Closing Calculator."},
            {"success": True, "message": "Volume increased."},
            {"success": True, "message": "Opening Chrome."}
        ]
        summary = self.engine.format_multi_command_response(sub_results)
        self.assertIn("Done.", summary)
        self.assertIn("Closing Calculator.", summary)
        self.assertIn("Volume increased.", summary)
        self.assertIn("Opening Chrome.", summary)

    def test_empty_multi_command_summary(self):
        summary = self.engine.format_multi_command_response([])
        self.assertEqual(summary, "Done.")

if __name__ == "__main__":
    unittest.main()
