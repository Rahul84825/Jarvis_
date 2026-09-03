import unittest
from core.command_normalizer import CommandNormalizer

class TestMultiCommandChaining(unittest.TestCase):
    def setUp(self):
        self.normalizer = CommandNormalizer()

    def test_multi_command_splitting(self):
        test_cases = [
            ("Open Chrome and VS Code", ["open chrome", "open vscode"]),
            ("Close Calculator and Volume Up", ["close calculator", "volume up"]),
            ("Open Chrome, Open GitHub and Open Downloads", ["open chrome", "open github", "open downloads"]),
            ("Take Screenshot and Open Downloads", ["take screenshot", "open downloads"]),
            ("Lock PC and turn off computer", ["lock computer", "shutdown computer"])
        ]
        for raw, expected in test_cases:
            with self.subTest(raw=raw):
                cmds = self.normalizer.split_chained_commands(raw)
                self.assertEqual(cmds, expected)

if __name__ == "__main__":
    unittest.main()
