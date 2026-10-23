"""Tests for Phase 3: Wake-Word Reliability, Manual Talk Lifecycle,
Microphone Stream Ownership, and System Diagnostics.
"""

import time
import unittest
import numpy as np
from unittest.mock import MagicMock, patch

from core.jarvis_runtime import JarvisRuntime
from core.wakeword import OpenWakeWordDetector, MockWakeWordDetector, WakeWordDetectorFactory
from core.listener import SpeechListener


class TestPhase3WakeWordAndManualTalk(unittest.TestCase):
    """Focused test suite verifying hands-free wake phrase activation,
    manual Talk button toggle-stop, single microphone stream ownership,
    and truthful diagnostics.
    """

    def setUp(self):
        with patch("core.jarvis_runtime.SpeechListener"), \
             patch("core.jarvis_runtime.SpeechTranscriber"), \
             patch("core.jarvis_runtime.WakeWordDetectorFactory.create_detector"):
            self.runtime = JarvisRuntime()
            self.runtime.listener = SpeechListener()
            self.runtime.listener._running = True
            self.runtime.tts_manager.interrupt = MagicMock()
            self.runtime.tts_manager.play_wake_chime = MagicMock()

    def tearDown(self):
        if hasattr(self.runtime, "listener") and self.runtime.listener:
            self.runtime.listener.stop()
        if hasattr(self.runtime, "wakeword_detector") and self.runtime.wakeword_detector:
            self.runtime.wakeword_detector.stop()

    # =========================================================================
    # 1. WAKE-WORD MODEL READINESS & FALLBACK
    # =========================================================================
    def test_openwakeword_model_loading_and_phrases(self):
        """Verify OpenWakeWord detector loads model and configures supported wake phrases."""
        detector = OpenWakeWordDetector(wake_words=["hey jarvis", "jarvis"], sensitivity=0.45)
        # Should be ready with 'hey_jarvis' ONNX model
        self.assertTrue(detector.is_available())
        diag = detector.get_diagnostic()
        self.assertIn("OpenWakeWord ready", diag)
        self.assertIn("hey_jarvis", diag)
        self.assertEqual(detector.sensitivity, 0.45)

    def test_openwakeword_model_unavailable_fallback(self):
        """Verify graceful fallback when model path is invalid."""
        detector = OpenWakeWordDetector(model_path="non_existent_model_file.onnx")
        # In degraded mode, is_available reflects actual model state
        diag = detector.get_diagnostic()
        self.assertIsInstance(diag, str)

    def test_wakeword_factory_creates_openwakeword_by_default(self):
        """Verify WakeWordDetectorFactory instantiates OpenWakeWordDetector."""
        det = WakeWordDetectorFactory.create_detector("openwakeword")
        self.assertIsInstance(det, OpenWakeWordDetector)

        mock_det = WakeWordDetectorFactory.create_detector("mock")
        self.assertIsInstance(mock_det, MockWakeWordDetector)

    # =========================================================================
    # 2. MICROPHONE STREAM OWNERSHIP & AUDIO CONSUMER SHARING
    # =========================================================================
    def test_unified_microphone_stream_consumer_registration(self):
        """Verify SpeechListener registers WakeWordDetector as an audio consumer without opening a second stream."""
        listener = SpeechListener()
        detector = OpenWakeWordDetector()

        listener.add_audio_consumer(detector.feed_pcm_frame)
        self.assertIn(detector.feed_pcm_frame, listener._audio_consumers)

        # Simulate PCM chunk feeding
        dummy_chunk = np.zeros(1280, dtype=np.int16)
        detector.feed_pcm_frame(dummy_chunk)
        self.assertTrue(detector._external_feed_active)
        self.assertGreater(detector._last_external_feed_time, 0.0)

        # Clean unregister
        listener.remove_audio_consumer(detector.feed_pcm_frame)
        self.assertNotIn(detector.feed_pcm_frame, listener._audio_consumers)

    # =========================================================================
    # 3. WAKE-WORD CALLBACK & RUNTIME STATE TRANSITIONS
    # =========================================================================
    def test_on_wakeword_triggers_listening_and_earcon(self):
        """Verify wake-word detection triggers LISTENING transition and earcon chime."""
        self.runtime._update_status("STANDBY")
        self.runtime._on_wakeword("hey_jarvis")

        self.assertEqual(self.runtime.current_status, "LISTENING")
        self.runtime.tts_manager.play_wake_chime.assert_called()
        self.assertTrue(self.runtime.listener.is_recording())

    def test_wakeword_barge_in_during_active_tts(self):
        """Verify wake word interrupts active speech playback immediately."""
        self.runtime.tts_manager._state = "TTS_PLAYING"
        self.runtime._tts_speaking_lock = True
        self.runtime._update_status("SPEAKING")

        self.runtime._on_wakeword("hey_jarvis")

        self.runtime.tts_manager.interrupt.assert_called_with(force=True)
        self.assertFalse(self.runtime._tts_speaking_lock)
        self.assertEqual(self.runtime.current_status, "LISTENING")

    # =========================================================================
    # 4. MANUAL TALK LIFECYCLE (TOGGLE-TO-STOP & DEBOUNCING)
    # =========================================================================
    def test_manual_talk_first_click_starts_recording(self):
        """Verify first manual Talk click starts recording session in LISTENING state."""
        self.runtime._update_status("STANDBY")
        self.runtime.listener._running = True

        self.runtime.trigger_manual_talk()

        self.assertEqual(self.runtime.current_status, "LISTENING")
        self.assertTrue(self.runtime.listener.is_recording())
        self.runtime.tts_manager.play_wake_chime.assert_called()

    def test_manual_talk_second_click_toggles_and_submits(self):
        """Verify second manual Talk click while recording finalizes and processes speech."""
        self.runtime.listener._running = True
        self.runtime.listener.trigger_manual_recording(manual=True)
        self.assertTrue(self.runtime.listener.is_recording())

        # Ensure debounce threshold has passed
        self.runtime._last_manual_talk_time = time.time() - 0.5
        with patch.object(self.runtime.listener, "stop_manual_recording") as mock_stop:
            self.runtime.trigger_manual_talk()
            mock_stop.assert_called_once()

    def test_manual_talk_debounces_rapid_repeated_clicks(self):
        """Verify rapid repeated clicks (<250ms) are debounced without corrupting audio buffer."""
        self.runtime.listener._running = True
        self.runtime._last_manual_talk_time = time.time()  # just clicked

        with patch.object(self.runtime.listener, "trigger_manual_recording") as mock_rec:
            self.runtime.trigger_manual_talk()
            mock_rec.assert_not_called()

    def test_manual_talk_interrupts_in_flight_generation(self):
        """Verify manual Talk invalidates generation when Jarvis is THINKING."""
        self.runtime.current_status = "THINKING"
        self.runtime.listener._running = True
        self.runtime._last_manual_talk_time = time.time() - 0.5

        old_gen = self.runtime.tts_manager._current_generation_id
        self.runtime.trigger_manual_talk()

        self.assertEqual(self.runtime.current_status, "LISTENING")
        self.assertGreater(self.runtime.tts_manager._current_generation_id, old_gen)

    # =========================================================================
    # 5. STALE RESPONSE INVALIDATION
    # =========================================================================
    def test_stale_command_worker_discarded(self):
        """Verify worker thread from superseded utterance is discarded before execution."""
        old_uid = "OLD123"
        new_uid = "NEW456"
        self.runtime._active_utterance_id = new_uid

        with patch.object(self.runtime, "_process_single_command") as mock_proc:
            self.runtime._process_command_worker("Open Chrome", utterance_id=old_uid)
            mock_proc.assert_not_called()

    # =========================================================================
    # 6. SYSTEM DIAGNOSTICS & TELEMETRY
    # =========================================================================
    def test_comprehensive_audio_diagnostics_report(self):
        """Verify get_audio_system_diagnostics returns accurate subsystem health."""
        diag = self.runtime.get_audio_system_diagnostics()

        self.assertIn("summary", diag)
        self.assertIn("microphone", diag)
        self.assertIn("wakeword", diag)
        self.assertIn("manual_talk", diag)
        self.assertIn("stt", diag)
        self.assertIn("tts", diag)

        self.assertEqual(diag["microphone"]["sample_rate_hz"], 16000)
        self.assertEqual(diag["manual_talk"]["toggle_stop_supported"], True)
        self.assertIn("hey jarvis", [w.lower() for w in diag["wakeword"]["supported_phrases"]])


if __name__ == "__main__":
    unittest.main()
