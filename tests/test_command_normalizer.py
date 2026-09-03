import unittest
from core.command_normalizer import CommandNormalizer

class TestCommandNormalizer(unittest.TestCase):
    def setUp(self):
        self.normalizer = CommandNormalizer()

    def test_polite_phrases_and_wake_words(self):
        test_cases = [
            ("Jarvis please open Chrome", "open chrome"),
            ("Could you launch Chrome", "open chrome"),
            ("Please lock my PC", "lock computer"),
            ("Please lock my computer", "lock computer"),
            ("Could you please lock the computer", "lock computer"),
            ("Can you turn off the computer", "shutdown computer"),
            ("Jarvis Jarvis sleep my computer", "sleep computer"),
            ("Take a picture of my screen", "take screenshot"),
            ("Open Visual Studio Code", "open vscode"),
            ("Please bring up VS Code", "open vscode")
        ]
        for raw, expected in test_cases:
            with self.subTest(raw=raw):
                res = self.normalizer.normalize(raw)
                self.assertEqual(res["normalized"], expected)

    def test_synonym_mappings(self):
        test_cases = [
            ("increase volume", "volume up"),
            ("make it louder", "volume up"),
            ("decrease volume", "volume down"),
            ("make it quieter", "volume down"),
            ("mute sound", "mute"),
            ("unmute audio", "unmute"),
            ("launch google chrome", "open chrome"),
            ("run notepad", "open notepad")
        ]
        for raw, expected in test_cases:
            with self.subTest(raw=raw):
                res = self.normalizer.normalize(raw)
                self.assertEqual(res["normalized"], expected)

if __name__ == "__main__":
    unittest.main()
