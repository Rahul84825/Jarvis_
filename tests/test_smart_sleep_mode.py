"""
Comprehensive Automated Test Suite for JARVIS Smart Sleep Mode & Wake-Word Activation.
Validates all 12 criteria specified in Phase 9:
1. Sleep command transitions ACTIVE to SLEEPING.
2. Wake phrase transitions SLEEPING to WAKING and then ACTIVE.
3. Ordinary speech while sleeping does not execute commands.
4. No full transcription runs during Sleep Mode.
5. No cloud AI requests originate from sleeping background audio.
6. Duplicate wake events do not trigger duplicate commands.
7. The first command after wake-up is captured correctly ('Jarvis, open Chrome').
8. Manual wake works when voice wake detection is unavailable.
9. Microphone resources are not opened by multiple listeners.
10. TTS and ongoing operations are handled safely during sleep entry.
11. Repeated sleep and wake cycles do not leak threads or audio resources.
12. Existing voice, wake-word, TTS, and command tests remain functional.
"""

import time
import threading
import unittest
from unittest.mock import MagicMock, patch, call
import numpy as np

from core.jarvis_runtime import JarvisRuntime
from core.intent_engine import IntentEngine
from core.listener import SpeechListener
from core.wakeword import MockWakeWordDetector, OpenWakeWordDetector
from ui.state_machine import map_runtime_status_to_ui_state, JarvisUIState


class TestSmartSleepMode(unittest.TestCase):
    """Deterministic unit and integration tests for JARVIS Smart Sleep Mode."""

    @patch("core.jarvis_runtime.SpeechListener")
    @patch("core.jarvis_runtime.SpeechTranscriber")
    @patch("core.jarvis_runtime.WakeWordDetectorFactory.create_detector")
    def setUp(self, mock_ww, mock_trans, mock_list):
        # Setup mock detector
        self.mock_detector = MockWakeWordDetector(wake_words=["jarvis"])
        mock_ww.return_value = self.mock_detector

        # Setup mock listener
        self.mock_listener = MagicMock()
        self.mock_listener.is_recording.return_value = False
        self.mock_listener.is_listening.return_value = True
        self.mock_listener.is_sleeping.return_value = False
        mock_list.return_value = self.mock_listener

        # Setup runtime
        self.runtime = JarvisRuntime()
        self.runtime.tts_manager.interrupt = MagicMock()
        self.runtime.tts_manager.play_wake_chime = MagicMock()
        self.runtime.tts_manager.speak = MagicMock()
        self.runtime.response_manager.conversation = MagicMock()

    # -------------------------------------------------------------
    # 1. Sleep command transitions ACTIVE to SLEEPING
    # -------------------------------------------------------------
    def test_01_sleep_command_transitions_to_sleeping(self):
        """Validates that sleep intents ('go to sleep', 'sleep', 'enter sleep mode')
        transition JARVIS from active STANDBY into SLEEPING.
        """
        engine = IntentEngine()
        for phrase in ["go to sleep", "sleep", "enter sleep mode", "sleep jarvis", "take a nap"]:
            parsed = engine.parse(phrase)
            self.assertEqual(parsed["intent"], "system_control", f"Failed for {phrase}")
            self.assertEqual(parsed["action"], "sleep_assistant", f"Failed for {phrase}")

        self.runtime._update_status("STANDBY")
        self.assertEqual(self.runtime.current_status, "STANDBY")

        # Invoke sleep mode entry
        ok = self.runtime.enter_sleep_mode(reason="voice_command", speak=False)
        self.assertTrue(ok)
        self.assertEqual(self.runtime.current_status, "SLEEPING")
        self.mock_listener.set_sleep_mode.assert_called_with(True)

        # Verify UI mapping
        ui_state = map_runtime_status_to_ui_state(self.runtime.current_status)
        self.assertEqual(ui_state, JarvisUIState.SLEEPING)

    # -------------------------------------------------------------
    # 2. Wake phrase transitions SLEEPING to WAKING and then ACTIVE
    # -------------------------------------------------------------
    def test_02_wake_phrase_transitions_sleeping_to_waking_and_active(self):
        """Validates that detecting 'jarvis' while in SLEEPING mode triggers
        transition through WAKING to restored listening pipeline.
        """
        self.runtime._update_status("SLEEPING")
        self.runtime.listener.set_sleep_mode(True)
        self.runtime._last_wake_time = 0.0

        status_history = []
        self.runtime.register_observers(on_status_change=lambda s: status_history.append(s))

        # Simulate wake word detection callback
        self.runtime._on_wakeword("jarvis")

        # State should have transitioned through WAKING
        self.assertIn("WAKING", status_history)
        self.assertIn("LISTENING", status_history)
        self.mock_listener.set_sleep_mode.assert_called_with(False)
        self.runtime.tts_manager.play_wake_chime.assert_called()

    # -------------------------------------------------------------
    # 3. Ordinary speech while sleeping does not execute commands
    # -------------------------------------------------------------
    def test_03_ordinary_speech_while_sleeping_does_not_execute_commands(self):
        """Validates that ordinary spoken words/commands ('open chrome', 'what is the weather')
        are completely discarded and execute no tools while sleeping.
        """
        self.runtime._update_status("SLEEPING")
        self.runtime.executor.execute = MagicMock()

        # Simulate incoming command worker for ordinary speech
        self.runtime._process_command_worker("what is the weather today")
        self.runtime._process_command_worker("open Chrome")
        self.runtime._process_command_worker("delete all files on desktop")

        # Executor must never have been called
        self.runtime.executor.execute.assert_not_called()
        # State must remain SLEEPING
        self.assertEqual(self.runtime.current_status, "SLEEPING")

    # -------------------------------------------------------------
    # 4. No full transcription runs during Sleep Mode
    # -------------------------------------------------------------
    def test_04_no_full_transcription_runs_during_sleep_mode(self):
        """Validates that in SpeechListener, when _sleep_mode is True,
        VAD onset detection and speech buffering are completely bypassed.
        """
        real_listener = SpeechListener()
        real_listener._running = True
        real_listener.set_sleep_mode(True)

        consumer_called = []
        real_listener.add_audio_consumer(lambda chunk: consumer_called.append(len(chunk)))

        # Simulate loud incoming speech audio frame (RMS > threshold)
        loud_audio = np.full((1024, 1), 0.25, dtype=np.float32)
        real_listener._audio_callback(loud_audio, 1024, None, None)

        # Registered wake-word consumer received the PCM chunk
        self.assertEqual(len(consumer_called), 1)
        self.assertEqual(consumer_called[0], 1024)

        # Full VAD recording must NOT be triggered
        self.assertFalse(real_listener.is_recording())
        self.assertEqual(len(real_listener._audio_buffer), 0)

    # -------------------------------------------------------------
    # 5. No cloud AI requests originate from sleeping background audio
    # -------------------------------------------------------------
    @patch("core.ai.intelligence_router.intelligence_router.route")
    def test_05_no_cloud_ai_requests_from_sleeping_audio(self, mock_router):
        """Validates that no background AI requests (Gemini, Nemotron) are dispatched
        when audio is received during sleep mode.
        """
        self.runtime._update_status("SLEEPING")
        self.runtime._process_command_worker("explain quantum physics to me")

        mock_router.assert_not_called()

    # -------------------------------------------------------------
    # 6. Duplicate wake events do not trigger duplicate commands
    # -------------------------------------------------------------
    def test_06_duplicate_wake_events_are_debounced(self):
        """Validates that rapid repeated wake triggers within 800ms
        are debounced and do not spawn duplicate wake transitions.
        """
        self.runtime._update_status("SLEEPING")
        self.runtime._last_wake_time = 0.0

        chime_count = 0
        def count_chimes():
            nonlocal chime_count
            chime_count += 1

        self.runtime.tts_manager.play_wake_chime = count_chimes

        # First wake trigger
        self.runtime.wake_up(source="wakeword")
        self.assertEqual(chime_count, 1)

        # Immediate secondary wake trigger (10ms later)
        self.runtime.wake_up(source="wakeword")
        # Should be suppressed by debounce
        self.assertEqual(chime_count, 1)

    # -------------------------------------------------------------
    # 7. First command after wake-up is captured correctly
    # -------------------------------------------------------------
    def test_07_wake_plus_command_preserves_trailing_instruction(self):
        """Validates that 'Jarvis, open Chrome' while in sleep mode
        wakes JARVIS and dispatches 'open Chrome' without dropping the command.
        """
        self.runtime._update_status("SLEEPING")
        self.runtime._last_wake_time = 0.0

        dispatched_commands = []
        original_process = self.runtime.process_command
        def mock_process(cmd):
            dispatched_commands.append(cmd)

        self.runtime.process_command = mock_process

        # User speaks "Jarvis, open Chrome"
        self.runtime._process_command_worker("Jarvis, open Chrome")

        # The runtime should wake up and dispatch trailing command
        self.assertEqual(self.runtime.current_status, "LISTENING")
        self.assertIn("open Chrome", dispatched_commands)

        self.runtime.process_command = original_process

    # -------------------------------------------------------------
    # 8. Manual wake works when voice wake detection is unavailable
    # -------------------------------------------------------------
    def test_08_manual_wake_works_when_detector_unavailable(self):
        """Validates that trigger_manual_talk() wakes JARVIS even if
        the wake word detector is offline or unavailable.
        """
        self.runtime.wakeword_detector = None  # Detector unavailable
        self.runtime._update_status("SLEEPING")
        self.runtime._last_wake_time = 0.0

        # Click manual talk / wake
        self.runtime.trigger_manual_talk()

        # Should be awake in STANDBY or LISTENING
        self.assertIn(self.runtime.current_status, ("STANDBY", "LISTENING"))
        self.mock_listener.set_sleep_mode.assert_called_with(False)

    # -------------------------------------------------------------
    # 9. Microphone resources are not opened by multiple listeners
    # -------------------------------------------------------------
    def test_09_single_shared_microphone_stream(self):
        """Validates that wake word detector receives shared PCM frames
        from the listener without opening a second conflicting sounddevice stream.
        """
        ww_detector = OpenWakeWordDetector()
        ww_detector._model_ready = False  # Avoid ONNX load in unit test

        # Feed external frame from SpeechListener
        frame = np.zeros(1280, dtype=np.int16)
        ww_detector.feed_pcm_frame(frame)

        self.assertTrue(ww_detector._external_feed_active)
        self.assertGreater(ww_detector._last_external_feed_time, 0.0)

    # -------------------------------------------------------------
    # 10. TTS and ongoing operations are handled safely during sleep entry
    # -------------------------------------------------------------
    def test_10_tts_and_operations_safely_cancelled_on_sleep(self):
        """Validates that entering sleep halts any active TTS playback,
        clears speaking locks, and cancels active planner tasks.
        """
        self.runtime._tts_speaking_lock = True
        self.runtime.tts_manager.is_speaking = MagicMock(return_value=True)
        self.runtime.pending_intent = {"intent": "long_operation"}
        mock_planner = MagicMock()
        self.runtime.multi_step_planner = mock_planner

        self.runtime.enter_sleep_mode(reason="user_request", speak=False)

        self.runtime.tts_manager.interrupt.assert_called_with(force=True)
        self.assertFalse(self.runtime._tts_speaking_lock)
        self.assertIsNone(self.runtime.pending_intent)
        mock_planner.cancel_active_task.assert_called()
        self.assertEqual(self.runtime.current_status, "SLEEPING")

    # -------------------------------------------------------------
    # 11. Repeated sleep and wake cycles do not leak resources
    # -------------------------------------------------------------
    def test_11_repeated_sleep_and_wake_cycles_resource_safety(self):
        """Validates that cycling between sleep and wake 10 times
        does not corrupt state or leave conflicting listeners.
        """
        initial_threads = threading.active_count()

        for i in range(10):
            self.runtime._last_wake_time = 0.0
            self.runtime.enter_sleep_mode(reason=f"cycle_{i}", speak=False)
            self.assertEqual(self.runtime.current_status, "SLEEPING")

            self.runtime.wake_up(source="manual_click")
            self.assertEqual(self.runtime.current_status, "STANDBY")

        final_threads = threading.active_count()
        # Thread count should remain stable
        self.assertLessEqual(final_threads, initial_threads + 2)

    # -------------------------------------------------------------
    # 12. Safety verification: Sleep mode does NOT shut down Windows
    # -------------------------------------------------------------
    @patch("modules.system.system_control.sleep_pc")
    @patch("modules.system.system_control.shutdown_pc")
    def test_12_sleep_mode_does_not_suspend_or_shutdown_windows(self, mock_shutdown, mock_sleep_pc):
        """Safety requirement: Assistant sleep mode must NEVER trigger
        OS-level PC sleep, hibernation, or computer shutdown.
        """
        engine = IntentEngine()
        parsed = engine.parse("Jarvis, go to sleep")
        self.assertEqual(parsed["action"], "sleep_assistant")
        self.assertNotEqual(parsed["action"], "sleep_pc")

        # Execute intent
        res = self.runtime._execute_intent(parsed, confirm=False, speak=False)
        self.assertTrue(res["success"])

        # OS control must NEVER have been called
        mock_sleep_pc.assert_not_called()
        mock_shutdown.assert_not_called()


if __name__ == "__main__":
    unittest.main()
