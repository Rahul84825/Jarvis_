import json
import unittest
from pathlib import Path

class TestSpeechCommandsJson(unittest.TestCase):

    def setUp(self):
        self.json_path = Path(__file__).parent / "speech_commands.json"

    def test_speech_commands_file_exists_and_valid(self):
        self.assertTrue(self.json_path.exists())
        with open(self.json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.assertIn("test_commands", data)
        commands = data["test_commands"]
        self.assertGreater(len(commands), 15)

        for cmd in commands:
            self.assertIn("phrase", cmd)
            self.assertIn("expected_intent", cmd)
            self.assertIn("category", cmd)

if __name__ == "__main__":
    unittest.main()
