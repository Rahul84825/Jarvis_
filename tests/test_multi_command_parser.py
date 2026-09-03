import unittest
from core.multi_command_parser import multi_command_parser

class TestMultiCommandParser(unittest.TestCase):

    def test_single_command_returns_list(self):
        res = multi_command_parser.parse("Open Chrome")
        self.assertEqual(res, ["Open Chrome"])

    def test_split_by_and(self):
        res = multi_command_parser.parse("Close Calculator and volume up.")
        self.assertEqual(res, ["Close Calculator", "volume up."])

    def test_verb_propagation(self):
        res = multi_command_parser.parse("Open Chrome and VS Code.")
        self.assertEqual(res, ["Open Chrome", "open VS Code."])

    def test_split_by_then_and_also(self):
        res = multi_command_parser.parse("Open Chrome, then open GitHub and increase volume.")
        self.assertEqual(res, ["Open Chrome", "open GitHub", "increase volume."])

    def test_screenshot_and_downloads(self):
        res = multi_command_parser.parse("Take a screenshot and open Downloads.")
        self.assertEqual(res, ["Take a screenshot", "open Downloads."])

    def test_multi_verb_sequence(self):
        res = multi_command_parser.parse("Close Spotify, open Chrome and increase the volume.")
        self.assertEqual(res, ["Close Spotify", "open Chrome", "increase the volume."])

if __name__ == "__main__":
    unittest.main()
