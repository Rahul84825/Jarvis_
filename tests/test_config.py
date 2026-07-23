import os
import json
import unittest
import tempfile
from pathlib import Path
from config import Config

class TestConfig(unittest.TestCase):
    def setUp(self):
        # Create a temporary config JSON path
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self.temp_file.close()
        self.temp_path = Path(self.temp_file.name)

    def tearDown(self):
        # Cleanup temporary files
        if self.temp_path.exists():
            try:
                os.remove(self.temp_path)
            except OSError:
                pass

    def test_default_values(self):
        """Verifies that default config values are loaded correctly."""
        cfg = Config(config_path=str(self.temp_path))
        self.assertEqual(cfg.wake_words, ["jarvis", "hey jarvis", "hello jarvis"])
        self.assertEqual(cfg.audio_sample_rate, 16000)
        self.assertEqual(cfg.ui_title, "JARVIS v1.0 - Foundation")
        self.assertEqual(cfg.log_level, "DEBUG")

    def test_save_and_load(self):
        """Verifies that saving config settings to file and reloading works correctly."""
        cfg = Config(config_path=str(self.temp_path))
        cfg.log_level = "WARNING"
        cfg.ui_width = 1200
        cfg.wake_words = ["jarvis", "computer"]
        cfg.save()

        # Instantiate new config object pointing to same file
        new_cfg = Config(config_path=str(self.temp_path))
        self.assertEqual(new_cfg.log_level, "WARNING")
        self.assertEqual(new_cfg.ui_width, 1200)
        self.assertEqual(new_cfg.wake_words, ["jarvis", "computer"])

    def test_env_overrides(self):
        """Verifies that environment variables successfully override config values."""
        os.environ["JARVIS_LOG_LEVEL"] = "ERROR"
        os.environ["JARVIS_UI_WIDTH"] = "1500"
        os.environ["JARVIS_WAKE_WORDS"] = '["test_wake", "hey_test"]'
        os.environ["JARVIS_CLAP_THRESHOLD"] = "0.45"
        
        try:
            cfg = Config(config_path=str(self.temp_path))
            self.assertEqual(cfg.log_level, "ERROR")
            self.assertEqual(cfg.ui_width, 1500)
            self.assertEqual(cfg.wake_words, ["test_wake", "hey_test"])
            self.assertEqual(cfg.clap_threshold, 0.45)
        finally:
            # Clean up env variables
            del os.environ["JARVIS_LOG_LEVEL"]
            del os.environ["JARVIS_UI_WIDTH"]
            del os.environ["JARVIS_WAKE_WORDS"]
            del os.environ["JARVIS_CLAP_THRESHOLD"]

if __name__ == "__main__":
    unittest.main()
