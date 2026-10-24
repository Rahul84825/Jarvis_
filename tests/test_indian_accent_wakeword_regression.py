"""tests/test_indian_accent_wakeword_regression.py - Comprehensive Regression Suite
for SANTRA Indian Accent Adaptation, Wake-Word Intelligence & Trailing Command Preservation.

Covers the 10 core regression cases mandated by Phase 7:
1. 'Santra, open Chrome.'
2. 'Samtra, open Chrome.'
3. 'Hey Santra, search YouTube for Valorant.'
4. 'Santra, explain the code on my screen.'
5. 'Santra, go to sleep.'
6. A command spoken immediately after the name (no pause).
7. Similar-sounding words used in ordinary conversation (negative confusers).
8. Silence and background noise rejection.
9. Two consecutive wake words.
10. Low-confidence or partially spoken names.
Plus audio buffer preservation, model sharing, and sleep-wake transitions.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from config import config
from core.pronunciation_manager import PronunciationManager, pronunciation_manager
from core.command_normalizer import CommandNormalizer
from core.listener import SpeechListener
from core.wakeword import SantraWakeWordDetector, WakeWordDetectorFactory, MockWakeWordDetector
from core.jarvis_runtime import JarvisRuntime
from core.wake_word_evaluator import wake_word_evaluator


class TestIndianAccentWakeWordRegression(unittest.TestCase):
    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.pronunciation_mgr = pronunciation_manager

    # -------------------------------------------------------------
    # Case 1: Canonical 'Santra, open Chrome.'
    # -------------------------------------------------------------
    def test_case_01_canonical_santra_open_chrome(self):
        raw = "Santra, open Chrome."
        is_wake, var, conf = self.pronunciation_mgr.evaluate_candidate(raw)
        self.assertTrue(is_wake)
        self.assertEqual(var, "santra")

        norm = self.normalizer.normalize(raw)
        self.assertEqual(norm["normalized"], "open chrome")

    # -------------------------------------------------------------
    # Case 2: Indian Accent Variant 'Samtra, open Chrome.'
    # -------------------------------------------------------------
    def test_case_02_indian_accent_samtra_open_chrome(self):
        raw = "Samtra, open Chrome."
        is_wake, var, conf = self.pronunciation_mgr.evaluate_candidate(raw)
        self.assertTrue(is_wake)
        self.assertEqual(var, "samtra")

        is_addr, canon, trailing = self.pronunciation_mgr.extract_wake_and_command(raw)
        self.assertTrue(is_addr)
        self.assertEqual(canon, "Santra")
        self.assertEqual(trailing, "open Chrome.")

        norm = self.normalizer.normalize(raw)
        self.assertEqual(norm["normalized"], "open chrome")

    # -------------------------------------------------------------
    # Case 3: 'Hey Santra, search YouTube for Valorant.'
    # -------------------------------------------------------------
    def test_case_03_hey_santra_youtube_search(self):
        raw = "Hey Santra, search YouTube for Valorant."
        is_wake, var, conf = self.pronunciation_mgr.evaluate_candidate(raw)
        self.assertTrue(is_wake)

        norm = self.normalizer.normalize(raw)
        self.assertEqual(norm["normalized"], "search youtube for valorant")

    # -------------------------------------------------------------
    # Case 4: 'Santra, explain the code on my screen.' (Code preservation)
    # -------------------------------------------------------------
    def test_case_04_code_preservation_not_corrupted_to_vscode(self):
        raw = "Santra, explain the code on my screen."
        norm = self.normalizer.normalize(raw)
        # Ensure 'code' was NOT aggressively rewritten to 'vscode'
        self.assertEqual(norm["normalized"], "explain the code on my screen")
        self.assertNotIn("vscode", norm["normalized"])

        raw_variant = "Samtra, explain this code"
        norm_v = self.normalizer.normalize(raw_variant)
        self.assertEqual(norm_v["normalized"], "explain this code")
        self.assertNotIn("vscode", norm_v["normalized"])

    # -------------------------------------------------------------
    # Case 5: 'Santra, go to sleep.'
    # -------------------------------------------------------------
    def test_case_05_santra_go_to_sleep(self):
        raw = "Santra, go to sleep."
        is_wake, var, conf = self.pronunciation_mgr.evaluate_candidate(raw)
        self.assertTrue(is_wake)

        from core.intent_engine import IntentEngine
        ie = IntentEngine()
        parsed = ie.parse(raw)
        self.assertEqual(parsed["intent"], "system_control")
        self.assertEqual(parsed["action"], "sleep_assistant")

    # -------------------------------------------------------------
    # Case 6: Immediate command spoken without pause
    # -------------------------------------------------------------
    def test_case_06_immediate_command_no_pause(self):
        cases = [
            ("Santra open Chrome", "open chrome"),
            ("Samtra open Chrome", "open chrome"),
            ("Suntra take a screenshot", "take screenshot"),
            ("Santhra increase volume", "volume up")
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                is_wake, var, conf = self.pronunciation_mgr.evaluate_candidate(raw)
                self.assertTrue(is_wake, f"Failed wake evaluation for '{raw}'")
                norm = self.normalizer.normalize(raw)
                self.assertEqual(norm["normalized"], expected, f"Failed normalization for '{raw}'")

    # -------------------------------------------------------------
    # Case 7: Similar-sounding words in ordinary conversation (Rejection)
    # -------------------------------------------------------------
    def test_case_07_negative_confuser_rejection(self):
        confusers = [
            "Santa Claus is coming to town",
            "Secret Santa gift exchange",
            "Meet me at the city centre around noon",
            "He was reading Patanjali Yoga Sutra",
            "Open audio device settings in Windows",
            "Clear the garbage collector cache",
            "Charles mentioned that Travis CI build passed",
            "There is a major disadvantage to this plan",
            "Let us chant the peace mantra"
        ]
        for sentence in confusers:
            with self.subTest(sentence=sentence):
                is_wake, var, conf = self.pronunciation_mgr.evaluate_candidate(sentence)
                self.assertFalse(is_wake, f"False activation on negative confuser: '{sentence}'")

    # -------------------------------------------------------------
    # Case 8: Silence and background noise rejection
    # -------------------------------------------------------------
    def test_case_08_silence_and_background_noise(self):
        noises = [
            "",
            "   ",
            "...",
            "[ambient_room_noise]",
            "television news playing in the other room",
            "keyboard clicking sounds during typing"
        ]
        for n in noises:
            is_wake, var, conf = self.pronunciation_mgr.evaluate_candidate(n)
            self.assertFalse(is_wake, f"False trigger on noise: '{n}'")

    # -------------------------------------------------------------
    # Case 9: Two consecutive wake words
    # -------------------------------------------------------------
    def test_case_09_two_consecutive_wake_words(self):
        raw = "Santra Santra open Chrome"
        norm = self.normalizer.normalize(raw)
        self.assertEqual(norm["normalized"], "open chrome")

        raw_mixed = "Hey Santra Samtra open Chrome"
        norm_m = self.normalizer.normalize(raw_mixed)
        self.assertEqual(norm_m["normalized"], "open chrome")

    # -------------------------------------------------------------
    # Case 10: Low-confidence or partially spoken names
    # -------------------------------------------------------------
    def test_case_10_low_confidence_or_partial_rejection(self):
        # Truncated or ambiguous syllables below threshold
        partials = ["san", "tra", "sam", "trah", "sa"]
        for p in partials:
            # Low confidence candidate
            is_wake, var, conf = self.pronunciation_mgr.evaluate_candidate(p, confidence=0.30)
            self.assertFalse(is_wake, f"False trigger on low confidence partial: '{p}'")

    # -------------------------------------------------------------
    # Case 11: SpeechListener in-flight audio preservation
    # -------------------------------------------------------------
    def test_case_11_listener_preserves_audio_buffer_on_wake_trigger(self):
        listener = SpeechListener()
        listener._running = True
        # Simulate active VAD recording
        listener._recording = True
        dummy_chunk = [100, 200, 300]
        listener._audio_buffer = [dummy_chunk, dummy_chunk]
        listener._pre_roll_buffer = [dummy_chunk]

        # Trigger manual recording as would occur on wake callback
        listener.trigger_manual_recording(manual=True)

        # Buffer MUST NOT be reset back to only pre-roll
        self.assertEqual(len(listener._audio_buffer), 2, "Existing audio buffer was wiped!")
        listener._running = False

    # -------------------------------------------------------------
    # Case 12: Sleep-Mode Wake with Indian Accent Variant 'Samtra'
    # -------------------------------------------------------------
    def test_case_12_sleep_wake_with_samtra_variant(self):
        with patch("core.listener.SpeechListener.start"), \
             patch("core.listener.SpeechListener.stop"), \
             patch("core.tts.tts_manager.TTSManager.play_wake_chime"):

            runtime = JarvisRuntime()
            runtime.wakeword_detector = MockWakeWordDetector()
            runtime.enter_sleep_mode(reason="test", speak=False)
            self.assertEqual(runtime.current_status, "SLEEPING")

            dispatched_commands = []
            runtime.process_command = lambda cmd, **kw: dispatched_commands.append(cmd)

            # User speaks 'Samtra, open Chrome' while sleeping
            runtime._process_command_worker("Samtra, open Chrome")
            self.assertIn(runtime.current_status, ["WAKING", "STANDBY", "LISTENING"])
            self.assertIn("open Chrome", dispatched_commands)
            runtime.stop()

    # -------------------------------------------------------------
    # Case 13: WakeWordEvaluator Benchmark Verification
    # -------------------------------------------------------------
    def test_case_13_evaluator_metrics_satisfaction(self):
        res = wake_word_evaluator.compare_baseline_vs_improved()
        improved = res["improved"]
        self.assertEqual(improved["recall"], 1.0, "Recall must be 100% across test suite")
        self.assertEqual(improved["far"], 0.0, "False Acceptance Rate must be 0%")
        self.assertEqual(improved["frr"], 0.0, "False Rejection Rate must be 0%")
        self.assertEqual(improved["command_preservation_accuracy"], 1.0, "Command preservation must be 100%")

    # -------------------------------------------------------------
    # Case 14: Shared Faster-Whisper Model Registration
    # -------------------------------------------------------------
    def test_case_14_shared_model_registration(self):
        det = SantraWakeWordDetector()
        mock_model = MagicMock()
        det.set_shared_model(mock_model)
        self.assertIs(det._get_model(), mock_model)


if __name__ == "__main__":
    unittest.main()
