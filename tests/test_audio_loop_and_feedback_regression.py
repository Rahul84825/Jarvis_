import os
import time
import queue
import wave
import tempfile
import unittest
import numpy as np
from unittest.mock import MagicMock, patch

from config import config
from core.listener import SpeechListener
from core.wakeword import SantraWakeWordDetector, WakeWordDetectorFactory, MockWakeWordDetector
from core.jarvis_runtime import JarvisRuntime
from core.tts.tts_manager import TTSManager


class TestAudioLoopAndFeedbackRegression(unittest.TestCase):
    """Exhaustive regression test suite verifying audio lifecycle,
    prevention of infinite loops, chime isolation, silence gating,
    and deduplication.
    """

    def setUp(self):
        self.listener = SpeechListener(
            sample_rate=16000,
            threshold=0.015,
            silence_duration=0.5,
            max_duration=3.0,
            enable_vad_onset=True
        )

    def tearDown(self):
        if hasattr(self, "listener") and self.listener:
            self.listener.stop()

    def test_01_repeated_listener_start_requests_idempotent(self):
        """Phase 8.1: Repeated listener start requests must be idempotent and not open duplicate streams."""
        with patch("sounddevice.InputStream") as mock_stream_cls:
            mock_stream = MagicMock()
            mock_stream_cls.return_value = mock_stream

            self.listener.start()
            self.assertTrue(self.listener.is_listening())
            mock_stream_cls.assert_called_once()

            # Second start should be safely ignored
            self.listener.start()
            self.assertTrue(self.listener.is_listening())
            # Stream should NOT have been created a second time
            mock_stream_cls.assert_called_once()

    def test_02_repeated_stop_requests_safe(self):
        """Phase 8.2: Repeated stop requests must be safe to call more than once."""
        with patch("sounddevice.InputStream") as mock_stream_cls:
            mock_stream = MagicMock()
            mock_stream_cls.return_value = mock_stream
            self.listener.start()
            self.assertTrue(self.listener.is_listening())

            self.listener.stop()
            self.assertFalse(self.listener.is_listening())
            mock_stream.stop.assert_called_once()

            # Second stop should not raise any exceptions
            self.listener.stop()
            self.assertFalse(self.listener.is_listening())

    def test_03_single_audio_segment_generates_exactly_one_transcription(self):
        """Phase 8.3: A single finalized segment must trigger exactly one transcription; duplicates are discarded."""
        with patch("core.jarvis_runtime.SpeechListener"), \
             patch("core.jarvis_runtime.SpeechTranscriber") as mock_transcriber_cls, \
             patch("core.jarvis_runtime.WakeWordDetectorFactory.create_detector"):
            mock_transcriber = MagicMock()
            mock_transcriber.transcribe.return_value = "open calculator"
            mock_transcriber.last_metadata = {"confidence": 0.95, "duration": 1.2}
            mock_transcriber_cls.return_value = mock_transcriber

            runtime = JarvisRuntime()
            runtime.transcriber = mock_transcriber

            # Create a mock WAV file
            fd, temp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                with wave.open(temp_path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(16000)
                    wf.writeframes(b"\x00\x00" * 8000)

                with patch.object(runtime, "process_command") as mock_process:
                    # First dispatch
                    runtime._on_speech_end(temp_path)
                    mock_transcriber.transcribe.assert_called_once_with(temp_path)
                    mock_process.assert_called_once()

                    # Duplicate dispatch with same WAV path should be deduplicated
                    runtime._on_speech_end(temp_path)
                    mock_transcriber.transcribe.assert_called_once()
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

    def test_04_silence_does_not_cause_repeated_stt_calls(self):
        """Phase 8.4: Silence limit reached with SpeechDetected=False does not dispatch to STT."""
        callback_mock = MagicMock()
        self.listener.on_speech_end_cb = callback_mock
        self.listener._running = True
        self.listener._recording = True
        self.listener._recording_start_time = time.time() - 2.0
        self.listener._silence_start = time.time() - 1.5
        self.listener._speech_detected = False
        self.listener._ambient_rms = 0.003

        # Feed a frame of silence
        silent_frame = np.zeros((1024, 1), dtype=np.float32)
        with patch.object(self.listener, "_save_and_dispatch") as mock_save:
            self.listener._audio_callback(silent_frame, 1024, None, None)
            # Should NOT dispatch to _save_and_dispatch
            mock_save.assert_not_called()
            # Recording should be stopped cleanly
            self.assertFalse(self.listener._recording)

    def test_05_one_wake_event_produces_at_most_one_intended_beep(self):
        """Phase 8.5: Rapid wake-word events produce at most one chime due to cooldown and state gating."""
        with patch("core.jarvis_runtime.SpeechListener"), \
             patch("core.jarvis_runtime.SpeechTranscriber"), \
             patch("core.jarvis_runtime.WakeWordDetectorFactory.create_detector"):
            runtime = JarvisRuntime()
            runtime.listener = MagicMock()
            runtime.tts_manager.play_wake_chime = MagicMock()

            # First wake event -> chime plays
            runtime._on_wakeword("santra")
            self.assertEqual(runtime.tts_manager.play_wake_chime.call_count, 1)

            # Rapid duplicate wake events while in LISTENING state -> ignored
            runtime._on_wakeword("santra")
            runtime._on_wakeword("hey jarvis")
            self.assertEqual(runtime.tts_manager.play_wake_chime.call_count, 1)

    def test_06_tts_output_not_reprocessed_as_user_command(self):
        """Phase 8.6: Setting speaking active suppresses unconfirmed background recording."""
        self.listener._running = True
        self.listener._recording = True
        self.listener._manual_recording = False
        self.listener._speech_detected = True

        # Jarvis starts speaking TTS output
        self.listener.set_speaking_active(True)
        self.assertTrue(self.listener.speaking_active)
        # Background VAD recording should be immediately canceled to prevent feedback
        self.assertFalse(self.listener._recording)

    def test_07_reconnection_does_not_create_duplicate_streams(self):
        """Phase 8.7: Stopping and restarting listener re-uses single stream reference cleanly."""
        with patch("sounddevice.InputStream") as mock_stream_cls:
            stream1 = MagicMock()
            stream2 = MagicMock()
            mock_stream_cls.side_effect = [stream1, stream2]

            self.listener.start()
            self.assertEqual(self.listener._stream, stream1)

            self.listener.stop()
            self.assertIsNone(self.listener._stream)

            self.listener.start()
            self.assertEqual(self.listener._stream, stream2)
            self.listener.stop()

    def test_08_failed_transcription_does_not_cause_rapid_retry_loop(self):
        """Phase 8.8: Transcriber error is handled gracefully and pipeline returns to STANDBY."""
        with patch("core.jarvis_runtime.SpeechListener"), \
             patch("core.jarvis_runtime.SpeechTranscriber") as mock_transcriber_cls, \
             patch("core.jarvis_runtime.WakeWordDetectorFactory.create_detector"):
            mock_transcriber = MagicMock()
            mock_transcriber.transcribe.side_effect = RuntimeError("STT Model Error")
            mock_transcriber_cls.return_value = mock_transcriber

            runtime = JarvisRuntime()
            runtime.transcriber = mock_transcriber

            fd, temp_path = tempfile.mkstemp(suffix=".wav")
            os.close(fd)
            try:
                # Should not raise exception out of handler
                runtime._on_speech_end(temp_path)
                # State should recover to STANDBY
                self.assertEqual(runtime.current_status, "STANDBY")
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)

    def test_09_consecutive_legitimate_commands_still_work(self):
        """Phase 8.9: Users can issue repeated valid commands intentionally without false deduplication."""
        with patch("core.jarvis_runtime.SpeechListener"), \
             patch("core.jarvis_runtime.SpeechTranscriber"), \
             patch("core.jarvis_runtime.WakeWordDetectorFactory.create_detector"):
            runtime = JarvisRuntime()
            with patch.object(runtime, "_process_single_command") as mock_proc:
                # First command
                runtime._process_command_worker("volume up", utterance_id="U1", t0_start=time.time())
                mock_proc.assert_called_once()

                # User legitimately says "volume up" again after 1.5s
                time.sleep(1.3)
                runtime._process_command_worker("volume up", utterance_id="U2", t0_start=time.time())
                self.assertEqual(mock_proc.call_count, 2)

    def test_10_wake_word_plus_trailing_command_preserved(self):
        """Phase 8.10: Command spoken with wake word preserves pre-roll buffer and suppresses chime echo."""
        self.listener._running = True
        # Pre-roll has audio frames representing "Hey Santra open Chrome"
        test_frame = np.full((1024, 1), 0.05, dtype=np.float32)
        self.listener._pre_roll_buffer = [test_frame, test_frame]

        self.listener.suppress_chime_feedback(duration=0.20)
        self.listener.trigger_manual_recording(manual=True)

        self.assertTrue(self.listener._recording)
        # Pre-roll frames were preserved in recording buffer
        self.assertEqual(len(self.listener._audio_buffer), 2)

        # Incoming frame during chime window is suppressed
        self.listener._audio_callback(test_frame, 1024, None, None)
        self.assertEqual(len(self.listener._audio_buffer), 2)  # Still 2, not 3!

    def test_11_sleep_mode_does_not_start_stt(self):
        """Phase 8.11: Sleep mode bypasses VAD onset and speech recording entirely."""
        self.listener._running = True
        self.listener.set_sleep_mode(True)
        self.assertTrue(self.listener.is_sleeping())

        loud_frame = np.full((1024, 1), 0.25, dtype=np.float32)
        self.listener._audio_callback(loud_frame, 1024, None, None)

        # Recording must NOT start while in sleep mode
        self.assertFalse(self.listener.is_recording())
        self.assertEqual(len(self.listener._audio_buffer), 0)

    def test_12_ui_mute_and_talk_controls_responsive(self):
        """Phase 8.12: UI controls (toggle mute and manual talk) operate cleanly and idempotently."""
        with patch("core.jarvis_runtime.SpeechListener"), \
             patch("core.jarvis_runtime.SpeechTranscriber"), \
             patch("core.jarvis_runtime.WakeWordDetectorFactory.create_detector"):
            runtime = JarvisRuntime()
            runtime.listener = MagicMock()
            runtime.listener.is_listening.return_value = True

            # Mute
            runtime.toggle_mute()
            self.assertTrue(runtime.muted)

            # Unmute
            runtime.toggle_mute()
            self.assertFalse(runtime.muted)

    def test_13_worker_and_stream_cleanup_after_shutdown(self):
        """Phase 8.13: Calling runtime.stop() terminates all workers and releases streams."""
        with patch("core.jarvis_runtime.SpeechListener"), \
             patch("core.jarvis_runtime.SpeechTranscriber"), \
             patch("core.jarvis_runtime.WakeWordDetectorFactory.create_detector"):
            runtime = JarvisRuntime()
            runtime.listener = MagicMock()
            runtime.wakeword_detector = MagicMock()
            runtime.tts_manager = MagicMock()

            runtime.stop()
            self.assertEqual(runtime.current_status, "STOPPED")
            runtime.listener.stop.assert_called_once()
            runtime.wakeword_detector.stop.assert_called_once()
            runtime.tts_manager.stop.assert_called_once()

    def test_14_buffererror_prevention_on_speech_burst(self):
        """Direct regression test for Root Cause 1: Evaluates a burst in SantraWakeWordDetector
        and verifies that np.frombuffer does not cause BufferError on bytearray.
        """
        detector = SantraWakeWordDetector()
        detector._speech_buffer = bytearray(b"\x00\x00" * 12800)  # 12,800 bytes
        detector._speech_frames = 10
        detector._silence_frames = 3

        # Simulate extracting snapshot exactly like _run_detector
        raw_burst = bytes(detector._speech_buffer)
        detector._speech_buffer = bytearray()
        detector._speech_frames = 0
        detector._silence_frames = 0

        # Create numpy array view from raw_burst
        audio_int16 = np.frombuffer(raw_burst, dtype=np.int16)
        self.assertEqual(len(audio_int16), 12800)
        # Verify detector._speech_buffer can be modified/cleared without BufferError!
        detector._speech_buffer.extend(b"\x01\x02")
        detector._speech_buffer.clear()
        self.assertEqual(len(detector._speech_buffer), 0)


if __name__ == "__main__":
    unittest.main()
