import unittest
import time
from core.tts.tts_manager import TTSManager

class TestTTSPlaybackHardening(unittest.TestCase):
    def setUp(self):
        self.tts = TTSManager()

    def test_audio_device_info_available(self):
        info = self.tts.get_audio_device_info()
        self.assertIsInstance(info, dict)
        self.assertIn("name", info)
        self.assertIn("sample_rate", info)

    def test_tts_manager_lifecycle(self):
        self.assertTrue(hasattr(self.tts, "speak"))
        self.assertTrue(hasattr(self.tts, "test_speakers"))
        self.assertTrue(hasattr(self.tts, "interrupt"))

if __name__ == "__main__":
    unittest.main()
