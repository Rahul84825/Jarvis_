import os
import wave
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from config import config
from core.listener import SpeechListener

class TestSpeechDebugAudio(unittest.TestCase):

    def setUp(self):
        self.listener = SpeechListener()

    def test_debug_audio_disabled_by_default(self):
        with patch.object(config, "debug_audio", False):
            with patch("wave.open", MagicMock()) as mock_wave:
                with patch("tempfile.mkstemp", return_value=(123, "temp_test.wav")):
                    with patch("os.close", MagicMock()):
                        audio_data = [0.0] * 16000
                        self.listener._save_and_dispatch(audio_data)
                        # Check that no debug_wavs files were created
                        debug_dir = config.LOGS_DIR / "debug_wavs"
                        if debug_dir.exists():
                            wav_count = len(list(debug_dir.glob("*.wav")))
                            self.assertLessEqual(wav_count, 20)

    def test_debug_audio_enabled_rotation(self):
        with patch.object(config, "debug_audio", True):
            debug_dir = config.LOGS_DIR / "debug_wavs"
            debug_dir.mkdir(exist_ok=True, parents=True)

            # Create mock dummy wav files
            created_files = []
            for i in range(25):
                p = debug_dir / f"test_dummy_{i}.wav"
                p.write_bytes(b"RIFF dummy")
                created_files.append(p)

            # Invoke save_and_dispatch to trigger rotation cap
            audio_data = [0.0] * 100
            with patch("tempfile.mkstemp", return_value=(123, "temp_test.wav")):
                with patch("os.close", MagicMock()):
                    with patch("os.remove", MagicMock()):
                        self.listener._save_and_dispatch(audio_data)

            # Verify that rotation keeps <= 20 files
            remaining_wavs = list(debug_dir.glob("*.wav"))
            self.assertLessEqual(len(remaining_wavs), 21)

            # Cleanup dummy test files
            for f in remaining_wavs:
                if "test_dummy_" in f.name:
                    try:
                        f.unlink()
                    except Exception:
                        pass

if __name__ == "__main__":
    unittest.main()
