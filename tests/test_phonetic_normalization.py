import unittest
from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine

class TestPhoneticNormalization(unittest.TestCase):

    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()

    def test_indian_english_phonetic_replacements(self):
        self.assertEqual(self.normalizer.normalize("open crome")["normalized"], "open chrome")
        self.assertEqual(self.normalizer.normalize("open krone")["normalized"], "open chrome")
        self.assertEqual(self.normalizer.normalize("open vieskund")["normalized"], "open vscode")
        self.assertEqual(self.normalizer.normalize("open utube")["normalized"], "open youtube")
        self.assertEqual(self.normalizer.normalize("open calcilator")["normalized"], "open calculator")

    def test_test_microphone_intent(self):
        res = self.intent_engine.parse("Jarvis test my microphone")
        self.assertEqual(res["intent"], "test_microphone")

        res2 = self.intent_engine.parse("check microphone")
        self.assertEqual(res2["intent"], "test_microphone")

if __name__ == "__main__":
    unittest.main()
