import unittest
from unittest.mock import patch, MagicMock
import numpy as np
from core.listener import SpeechListener

class TestMicDiagnostics(unittest.TestCase):

    def setUp(self):
        self.listener = SpeechListener()

    def test_get_available_microphones(self):
        with patch("sounddevice.query_devices", return_value=[{"name": "Mic 1", "max_input_channels": 2, "default_samplerate": 16000}]):
            mics = SpeechListener.get_available_microphones()
            self.assertEqual(len(mics), 1)
            self.assertEqual(mics[0]["name"], "Mic 1")

    def test_run_microphone_diagnostics_mock(self):
        dummy_rec = np.ones((32000, 1), dtype="float32") * 0.05
        with patch("sounddevice.rec", return_value=dummy_rec):
            with patch("sounddevice.wait", MagicMock()):
                with patch("sounddevice.query_devices", return_value={"name": "Test Mic"}):
                    res = self.listener.run_microphone_diagnostics(duration=0.1)
                    self.assertIn("spoken_summary", res)
                    self.assertIn("signal_quality", res)
                    self.assertEqual(res["sample_rate"], 16000)

if __name__ == "__main__":
    unittest.main()
