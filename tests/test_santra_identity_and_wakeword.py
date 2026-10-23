"""
test_santra_identity_and_wakeword.py - Verification suite for SANTRA Identity Migration.
Covers UI branding, default configuration, wake-word engine, sleep/wake behavior,
trailing command preservation, TTS responses, backward compatibility, and memory preservation.
"""

import unittest
from unittest.mock import MagicMock, patch
import time
import os
import json

from config import config, Config
from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.local_response_engine import LocalResponseEngine
from core.social_engine import SocialEngine
from core.wakeword import SantraWakeWordDetector, WakeWordDetectorFactory, MockWakeWordDetector
from core.jarvis_runtime import JarvisRuntime
from ui.state_machine import STATE_CONFIGS, JarvisUIState


class TestSantraIdentityMigration(unittest.TestCase):
    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.response_engine = LocalResponseEngine()
        self.social_engine = SocialEngine()

    def test_01_default_assistant_identity_is_santra(self):
        """Verify default assistant name and configuration canonical identity."""
        self.assertEqual(config.assistant_name, "Santra")
        self.assertIn("santra", [w.lower() for w in config.wake_words])
        self.assertEqual(config.wake_words[0].lower(), "santra")
        self.assertIn("SANTRA", config.ui_title)

    def test_02_ui_visual_configs_no_old_branding(self):
        """Verify UI state configurations display SANTRA in activate/wake subtexts."""
        standby_cfg = STATE_CONFIGS[JarvisUIState.STANDBY]
        self.assertIn("SANTRA", standby_cfg.subtext)
        self.assertNotIn("JARVIS", standby_cfg.subtext)

        sleep_cfg = STATE_CONFIGS[JarvisUIState.SLEEPING]
        self.assertIn("SANTRA", sleep_cfg.subtext)
        self.assertNotIn("JARVIS", sleep_cfg.subtext)

    def test_03_command_normalizer_strips_santra(self):
        """Verify CommandNormalizer strips Santra and its phonetic variants."""
        cases = [
            ("Santra open Chrome", "open chrome"),
            ("Hey Santra open Chrome", "open chrome"),
            ("Hello Santra please take a screenshot", "take screenshot"),
            ("Santra go to sleep", "go to sleep"),
            ("Sandra open notepad", "open notepad"),
            ("Santa open calculator", "open calculator"),
            # Legacy backward-compatibility
            ("Jarvis open Chrome", "open chrome"),
            ("Hey Jarvis open Chrome", "open chrome")
        ]
        for raw, expected in cases:
            res = self.normalizer.normalize(raw)
            self.assertEqual(res["normalized"], expected, f"Failed on raw: '{raw}'")

    def test_04_intent_engine_recognizes_santra_identity_and_sleep(self):
        """Verify IntentEngine parses Santra identity and sleep commands."""
        sleep_res = self.intent_engine.parse("Santra, go to sleep")
        self.assertEqual(sleep_res["intent"], "system_control")
        self.assertEqual(sleep_res["action"], "sleep_assistant")

        identity_res = self.intent_engine.parse("who are you")
        self.assertEqual(identity_res["intent"], "identity")

        help_res = self.intent_engine.parse("what can santra do")
        self.assertEqual(help_res["intent"], "help")

    def test_05_tts_and_social_engine_use_santra_identity(self):
        """Verify LocalResponseEngine and SocialEngine use Santra."""
        identity_speech = self.social_engine.get_identity_response("name")
        self.assertIn("Santra", identity_speech)

        status_speech = self.response_engine.get_template("status_check")
        self.assertTrue(any("Santra" in s for s in self.response_engine.responses["status_check"]))

    def test_06_santra_wakeword_detector_creation(self):
        """Verify WakeWordDetectorFactory instantiates SantraWakeWordDetector."""
        detector = WakeWordDetectorFactory.create_detector("santra")
        self.assertIsInstance(detector, SantraWakeWordDetector)
        self.assertTrue(detector.is_available())
        self.assertIn("santra", detector.wake_words)

    def test_07_sleep_mode_wakes_on_santra_and_preserves_command(self):
        """Verify saying 'Santra, open Chrome' while in SLEEPING mode wakes and executes."""
        with patch("core.listener.SpeechListener.start"), \
             patch("core.listener.SpeechListener.stop"), \
             patch("core.tts.tts_manager.TTSManager.play_wake_chime"):

            runtime = JarvisRuntime()
            runtime.wakeword_detector = MockWakeWordDetector()
            runtime.enter_sleep_mode(reason="test", speak=False)
            self.assertEqual(runtime.current_status, "SLEEPING")

            dispatched_commands = []
            orig_process = runtime.process_command
            def mock_process(cmd, **kwargs):
                dispatched_commands.append(cmd)
            runtime.process_command = mock_process

            # Process sleep wake utterance with trailing command
            runtime._process_command_worker("Santra, open Chrome")
            self.assertIn(runtime.current_status, ["WAKING", "STANDBY", "LISTENING"])
            self.assertIn("open Chrome", dispatched_commands)
            runtime.stop()

    def test_08_background_speech_ignored_in_sleep(self):
        """Verify normal room conversation while in SLEEPING mode does not wake."""
        with patch("core.listener.SpeechListener.start"), \
             patch("core.listener.SpeechListener.stop"):

            runtime = JarvisRuntime()
            runtime.wakeword_detector = MockWakeWordDetector()
            runtime.enter_sleep_mode(reason="test", speak=False)
            self.assertEqual(runtime.current_status, "SLEEPING")

            dispatched = []
            runtime.process_command = lambda cmd, **kw: dispatched.append(cmd)

            # Ordinary background speech without Santra
            runtime._process_command_worker("Is it raining outside today?")
            self.assertEqual(runtime.current_status, "SLEEPING")
            self.assertEqual(len(dispatched), 0)
            runtime.stop()

    def test_09_manual_wake_control_remains_functional(self):
        """Verify UI manual talk button acts as wake control when sleeping."""
        with patch("core.listener.SpeechListener.start"), \
             patch("core.listener.SpeechListener.stop"), \
             patch("core.tts.tts_manager.TTSManager.play_wake_chime"):

            runtime = JarvisRuntime()
            runtime.wakeword_detector = MockWakeWordDetector()
            runtime.enter_sleep_mode(reason="test", speak=False)
            self.assertEqual(runtime.current_status, "SLEEPING")

            # Click manual talk in UI
            runtime.trigger_manual_talk()
            self.assertIn(runtime.current_status, ["WAKING", "LISTENING", "STANDBY"])
            self.assertFalse(runtime.listener.is_sleeping())
            runtime.stop()

    def test_10_backward_compatible_config_migration(self):
        """Verify that legacy config values with 'Jarvis' migrate cleanly to Santra."""
        import tempfile
        with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".json") as f:
            legacy_data = {
                "assistant_name": "Jarvis",
                "ui_title": "JARVIS v1.1 - AI Desktop Assistant",
                "wake_words": ["jarvis", "hey jarvis"],
                "wakeword_engine": "openwakeword",
                "nvidia_api_key": "test-nv-key-preserve-me",
                "gemini_api_key": "test-gem-key-preserve-me"
            }
            json.dump(legacy_data, f)
            temp_path = f.name

        try:
            with patch.object(Config, "_apply_env_overrides"):
                cfg = Config(temp_path)
                self.assertEqual(cfg.assistant_name, "Santra")
                self.assertEqual(cfg.ui_title, "SANTRA v1.1 - AI Desktop Assistant")
                self.assertIn("santra", [w.lower() for w in cfg.wake_words])
                self.assertIn("jarvis", [w.lower() for w in cfg.wake_words])
                # Verify credentials and settings are preserved
                self.assertEqual(cfg.nvidia_api_key, "test-nv-key-preserve-me")
                self.assertEqual(cfg.gemini_api_key, "test-gem-key-preserve-me")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)


if __name__ == "__main__":
    unittest.main()
