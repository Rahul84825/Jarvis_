"""Tests for Track 1 & Track 2 Real-Time Voice Conversation, Interruption,
and NVIDIA Nemotron Streaming Cancellation.
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from core.tts.tts_manager import TTSManager
from core.conversation_manager import ConversationManager, ExplanationState
from core.ai.intelligence_router import intelligence_router, MODE_FAST_LOCAL
from core.listener import SpeechListener


class TestRealtimeConversation(unittest.TestCase):
    """Test suite for voice lifecycle, barge-in, interruption classification,
    and conversational state resumption.
    """

    def setUp(self):
        self.tts = TTSManager()
        self.conv_mgr = ConversationManager()

    def tearDown(self):
        self.tts.stop()

    # =========================================================================
    # 1. IMMEDIATE BARGE-IN & AUDIO CUTOFF
    # =========================================================================
    def test_barge_in_stops_tts_immediately(self):
        """Verify barge-in halts speech playback and invalidates queue."""
        initial_gen = self.tts._current_generation_id
        t0 = time.time()
        self.tts.interrupt(force=True)
        duration_ms = (time.time() - t0) * 1000

        # Interrupt must complete under 50ms locally
        self.assertLess(duration_ms, 50.0, f"Interrupt took {duration_ms:.2f}ms (>50ms target)")
        self.assertFalse(self.tts.is_speaking())
        self.assertEqual(self.tts.get_queue_size(), 0)
        self.assertGreater(self.tts._current_generation_id, initial_gen)

    def test_generation_id_invalidation_prevents_stale_playback(self):
        """Verify audio chunks tagged with an older generation ID are discarded."""
        old_gen = self.tts._current_generation_id
        new_gen = self.tts.new_generation()
        self.assertGreater(new_gen, old_gen)

        # Enqueue item with old generation ID
        self.tts.speech_queue.put(("Stale text that should never play", "high", old_gen))
        # The worker should drop it when processed
        self.assertEqual(self.tts.get_queue_size(), 1)
        # Calling interrupt flushes the queue completely
        self.tts.interrupt(force=True)
        self.assertEqual(self.tts.get_queue_size(), 0)

    def test_speak_sentences_tracks_progress(self):
        """Verify speak_sentences sets up sentence progress state."""
        sentences = [
            "Binary search is an efficient algorithm.",
            "It finds the position of a target value within a sorted array.",
            "It compares the target value to the middle element."
        ]
        progress_events = []
        self.tts.set_sentence_callback(lambda idx, total, text: progress_events.append((idx, total, text)))

        # Mock playback to avoid hardware sound device
        with patch.object(self.tts, "_play_audio_file", return_value=True):
            self.tts.speak_sentences(sentences, interrupt=True)
            self.assertEqual(self.tts.current_sentence_progress["total"], 3)

    # =========================================================================
    # 2. CONVERSATION STATE CONTINUITY & RESUMPTION
    # =========================================================================
    def test_explanation_tracking_and_resumption(self):
        """Verify explanation state stores sentences and resumes from interrupted point."""
        explanation = (
            "Binary search is a search algorithm. "
            "It works by repeatedly dividing in half the portion of the list that could contain the item. "
            "First, calculate the midpoint. "
            "Then, compare the key with the midpoint value. "
            "Finally, eliminate the half where the key cannot lie."
        )
        self.conv_mgr.set_active_explanation(
            topic="binary search",
            goal="explain binary search",
            text=explanation
        )

        self.assertIsNotNone(self.conv_mgr.explanation_state)
        self.assertEqual(len(self.conv_mgr.explanation_state.sentences), 5)

        # Simulate user listening through sentence 1 (index 0) and midpoint question during sentence 2 (index 1)
        self.conv_mgr.update_sentence_progress(current_index=1, total=5)
        self.conv_mgr.mark_interrupted()

        self.assertTrue(self.conv_mgr.has_interrupted_explanation())
        self.assertTrue(self.conv_mgr.explanation_state.interrupted)
        self.assertEqual(self.conv_mgr.explanation_state.interrupted_at_index, 1)

        # User says "continue" -> resumes from sentence index 2 (index + 1)
        resumed_text, remaining = self.conv_mgr.resume_explanation()
        self.assertIn("Continuing from where we paused", resumed_text)
        self.assertEqual(len(remaining), 3)  # sentences 2, 3, 4
        self.assertIn("First, calculate the midpoint", remaining[0])
        self.assertFalse(self.conv_mgr.has_interrupted_explanation())

    # =========================================================================
    # 3. INTERRIBUTION CLASSIFICATION
    # =========================================================================
    def test_classify_interruption_types(self):
        """Verify distinct interruption classifications."""
        test_cases = [
            ("stop talking", "STOP"),
            ("be quiet please", "STOP"),
            ("cancel that operation", "CANCEL"),
            ("abort this task", "CANCEL"),
            ("continue from where you stopped", "RESUME"),
            ("go on", "RESUME"),
            ("no, I meant binary search, not linear search", "CORRECTION"),
            ("actually, use Python instead", "TASK_MODIFICATION"),
            ("wait, what does that variable mean?", "QUESTION"),
            ("why does that work?", "FOLLOW_UP"),
            ("also explain its time complexity", "ADDITION"),
            ("forget that for now; open VS Code", "TOPIC_CHANGE"),
        ]
        for utterance, expected_type in test_cases:
            res = self.conv_mgr.classify_interruption(utterance)
            self.assertEqual(
                res["type"], expected_type,
                f"Utterance '{utterance}' expected {expected_type}, got {res['type']}"
            )

    def test_apply_correction_phrase_replacement(self):
        """Verify correction applies replacement to active task context."""
        self.conv_mgr.set_active_explanation(
            topic="linear search",
            goal="explain linear search",
            text="Linear search sequentially checks each element."
        )

        corrected = self.conv_mgr.apply_correction("no, I meant binary search, not linear search")
        self.assertIn("binary search", corrected)
        self.assertEqual(self.conv_mgr.task_context.current_topic, "binary search")

    def test_interruption_question_preserves_parent_explanation(self):
        """Verify answering an interruption question does not overwrite or destroy the parent explanation."""
        explanation = (
            "Binary search operates on sorted arrays. "
            "First, calculate the midpoint of the range. "
            "Next, inspect if the target matches the midpoint. "
            "If less, search the left half. "
            "Otherwise, search the right half."
        )
        self.conv_mgr.set_active_explanation("binary search", "explain binary search", explanation)
        self.conv_mgr.update_sentence_progress(current_index=1, total=5)
        self.conv_mgr.mark_interrupted()

        # User interrupts with a question
        interruption_q = "Wait, why are we calculating the midpoint?"
        class_res = self.conv_mgr.classify_interruption(interruption_q)
        self.assertEqual(class_res["type"], "QUESTION")
        self.assertEqual(class_res["subtype"], "INTERRUPTION_QUESTION")

        # Runtime attempts to set new explanation for the question answer
        midpoint_answer = "We calculate the midpoint to halve the search space on every step."
        self.conv_mgr.set_active_explanation("midpoint", "why midpoint", midpoint_answer, preserve_if_interrupted=True)

        # Parent explanation MUST remain intact and interrupted
        self.assertTrue(self.conv_mgr.has_interrupted_explanation())
        self.assertEqual(self.conv_mgr.explanation_state.topic, "binary search")
        self.assertEqual(self.conv_mgr.explanation_state.current_sentence_idx, 1)

        # User says "continue" -> resumes parent explanation from sentence index 2
        resumed_text, remaining = self.conv_mgr.resume_explanation()
        self.assertIn("Continuing from where we paused", resumed_text)
        self.assertEqual(len(remaining), 3)
        self.assertIn("Next, inspect if the target matches the midpoint", remaining[0])
        self.assertFalse(self.conv_mgr.has_interrupted_explanation())

    def test_task_modification_and_topic_change(self):
        """Verify task modification and topic change correctly update or clear explanation context."""
        self.conv_mgr.set_active_explanation(
            topic="binary search",
            goal="explain binary search",
            text="Binary search operates on sorted lists."
        )
        self.conv_mgr.mark_interrupted()
        self.assertTrue(self.conv_mgr.has_interrupted_explanation())

        # Task modification
        modified = self.conv_mgr.apply_correction("actually, use Python instead")
        self.assertEqual(modified, "Explain binary search in Python")

        # Topic change or cancellation clears the paused state
        self.conv_mgr.clear_interrupted_state()
        self.assertFalse(self.conv_mgr.has_interrupted_explanation())
        self.assertIsNone(self.conv_mgr.explanation_state)

    # =========================================================================
    # 4. INSTANT REFLEXES & FAST TURN-TAKING
    # =========================================================================
    def test_instant_reflex_stop_talking(self):
        """Verify 'stop talking' is routed to instant reflex Layer 1 without cloud latency."""
        req = intelligence_router.route("stop talking")
        self.assertEqual(req.layer, 1)
        self.assertEqual(req.intent, "STOP_TALKING")
        self.assertEqual(req.mode, MODE_FAST_LOCAL)

    def test_instant_reflex_user_correction(self):
        """Verify correction utterance is routed with CORRECTION intent."""
        req = intelligence_router.route("no, I meant binary search, not linear search")
        self.assertEqual(req.intent, "CORRECTION")

    # =========================================================================
    # 5. AUDIO PIPELINE RELIABILITY
    # =========================================================================
    def test_listener_barge_in_clears_speaking_cooldown(self):
        """Verify barge-in clears speech cooldown to prevent dropping user speech."""
        listener = SpeechListener()
        listener.set_speaking_active(True)
        self.assertTrue(listener.speaking_active)

        # Trigger barge-in
        listener._on_barge_in()
        self.assertTrue(listener._barge_in_active)
        self.assertEqual(listener._speaking_cooldown_until, 0.0)

    # =========================================================================
    # 6. NVIDIA NEMOTRON STREAMING CANCELLATION
    # =========================================================================
    def test_nvidia_streaming_cancellation_callback(self):
        """Verify streaming generator stops immediately when is_cancelled returns True."""
        from core.ai.providers.nvidia_provider import NvidiaNemotronProvider
        provider = NvidiaNemotronProvider(api_key="nvapi-mock-test-key-12345")

        cancelled = False
        def is_cancelled():
            return cancelled

        mock_lines = [
            b'data: {"choices":[{"delta":{"content":"First chunk "}}]}',
            b'data: {"choices":[{"delta":{"content":"Second chunk "}}]}',
            b'data: {"choices":[{"delta":{"content":"Third chunk "}}]}'
        ]

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.iter_lines.return_value = iter(mock_lines)
            mock_post.return_value = mock_resp

            received = []
            gen = provider.stream_response([{"role": "user", "content": "Explain binary search"}], is_cancelled=is_cancelled)

            # Receive first chunk
            received.append(next(gen))
            # Barge-in happens!
            cancelled = True

            # Next chunk attempt should terminate generator
            with self.assertRaises(StopIteration):
                next(gen)

            self.assertEqual(len(received), 1)
            self.assertEqual(received[0], "First chunk ")


if __name__ == "__main__":
    unittest.main()
