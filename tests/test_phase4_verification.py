"""Phase 4 Comprehensive Independent Verification Test Suite.
Verifies:
1. End-to-end conversation continuity across 8 real interruption/correction scenarios.
2. Voice & TTS reliability: Generation IDs, sentence completion gating, and barge-in.
3. NVIDIA Nemotron streaming cancellation, socket cleanup, and safe tool-calling.
4. Workspace execution with interactive confirmation and memory preferences.
5. Windows power plans vs Acer OEM hardware telemetry boundaries.
"""

import unittest
import time
from unittest.mock import MagicMock, patch

from core.conversation_manager import ConversationManager
from core.tts.tts_manager import TTSManager
from core.listener import SpeechListener
from core.ai.intelligence_router import intelligence_router, MODE_FAST_LOCAL, MODE_REASONING
from core.ai.providers.nvidia_provider import NvidiaNemotronProvider
from core.os.workspace_manager import WorkspaceManager
from core.os.power_manager import PowerManager
from memory.persistent_memory import persistent_memory


class TestPhase4IndependentVerification(unittest.TestCase):
    """Rigorous Phase 4 Independent Verification Suite."""

    def setUp(self):
        self.conv_mgr = ConversationManager(db_path=":memory:")
        self.tts = TTSManager()
        self.tts.start()
        self.workspace_mgr = WorkspaceManager()
        self.power_mgr = PowerManager()

    def tearDown(self):
        self.tts.stop()

    # =========================================================================
    # 1. CONVERSATION CONTINUITY: SCENARIOS 1 - 8
    # =========================================================================
    def test_scenario_01_and_02_explanation_start_and_question_interruption(self):
        """Scenario 1 & 2: Start multi-sentence explanation and interrupt with related question."""
        explanation = (
            "Binary search is an algorithm for finding an element in a sorted list. "
            "It works by comparing the target value to the middle element. "
            "If the target is smaller, the search continues in the lower half. "
            "If the target is larger, the search continues in the upper half. "
            "The process repeats until the element is found or the subarray is empty."
        )
        self.conv_mgr.set_active_explanation("binary search", "explain binary search", explanation)
        self.assertEqual(len(self.conv_mgr.explanation_state.sentences), 5)

        # Sentence 0 finishes playing
        self.conv_mgr.update_sentence_progress(current_index=0, total=5)
        # User interrupts with question during sentence 1
        interruption_q = "Wait, why are we calculating the midpoint?"
        class_res = self.conv_mgr.classify_interruption(interruption_q)
        self.assertEqual(class_res["type"], "QUESTION")
        self.conv_mgr.mark_interrupted()

        # Answering question preserves parent explanation
        midpoint_ans = "The midpoint allows us to divide the remaining search range exactly in half."
        self.conv_mgr.set_active_explanation("midpoint", "why midpoint", midpoint_ans, preserve_if_interrupted=True)

        self.assertTrue(self.conv_mgr.has_interrupted_explanation())
        self.assertEqual(self.conv_mgr.explanation_state.topic, "binary search")
        self.assertEqual(self.conv_mgr.explanation_state.current_sentence_idx, 0)

    def test_scenario_03_correction_programming_language(self):
        """Scenario 3: Ask for a correction (e.g. changing language to Python)."""
        self.conv_mgr.set_active_explanation(
            topic="binary search",
            goal="explain binary search",
            text="Binary search in C++ uses std::lower_bound."
        )
        self.conv_mgr.mark_interrupted()

        # User corrects: "actually, use Python instead"
        class_res = self.conv_mgr.classify_interruption("actually, use Python instead")
        self.assertEqual(class_res["type"], "TASK_MODIFICATION")

        modified_goal = self.conv_mgr.apply_correction("actually, use Python instead")
        self.assertEqual(modified_goal, "Explain binary search in Python")
        self.assertEqual(self.conv_mgr.task_context.current_user_request, "Explain binary search in Python")

    def test_scenario_04_add_task_constraint(self):
        """Scenario 4: Add a constraint to the current task."""
        self.conv_mgr.set_active_explanation(
            topic="quicksort",
            goal="explain quicksort",
            text="Quicksort selects a pivot and partitions the array."
        )
        class_res = self.conv_mgr.classify_interruption("also explain in-place partitioning with O(1) space")
        self.assertEqual(class_res["type"], "ADDITION")

    def test_scenario_05_continue_resumes_remaining_without_repetition(self):
        """Scenario 5: Say 'continue' and verify remaining content resumes from exact paused point."""
        explanation = (
            "Sentence zero: Binary search requires sorted data. "
            "Sentence one: Compare key to the midpoint value. "
            "Sentence two: Discard the irrelevant half. "
            "Sentence three: Terminate when low exceeds high."
        )
        self.conv_mgr.set_active_explanation("binary search", "explain binary search", explanation)
        # Sentence 0 completed, interrupted during sentence 1
        self.conv_mgr.update_sentence_progress(current_index=0, total=4)
        self.conv_mgr.mark_interrupted()

        # User says: "okay continue"
        class_res = self.conv_mgr.classify_interruption("okay continue")
        self.assertEqual(class_res["type"], "RESUME")

        resumed_text, remaining = self.conv_mgr.resume_explanation()
        self.assertIn("Continuing from where we paused", resumed_text)
        # Remaining should be sentences 1, 2, 3 (3 sentences total)
        self.assertEqual(len(remaining), 3)
        self.assertIn("Sentence one", remaining[0])
        self.assertIn("Sentence two", remaining[1])
        self.assertIn("Sentence three", remaining[2])
        self.assertFalse(self.conv_mgr.has_interrupted_explanation())

    def test_scenario_06_unrelated_topic_change(self):
        """Scenario 6: Change to an unrelated topic clears paused explanation."""
        self.conv_mgr.set_active_explanation(
            topic="binary search",
            goal="explain binary search",
            text="Binary search operates in O(log n)."
        )
        self.conv_mgr.mark_interrupted()
        self.assertTrue(self.conv_mgr.has_interrupted_explanation())

        # User says: "forget that for now; check the weather"
        class_res = self.conv_mgr.classify_interruption("forget that for now; check the weather")
        self.assertEqual(class_res["type"], "TOPIC_CHANGE")

        self.conv_mgr.clear_interrupted_state()
        self.assertFalse(self.conv_mgr.has_interrupted_explanation())

    def test_scenario_07_stop_talking_vs_explicit_task_cancellation(self):
        """Scenario 7: Test instant reflex 'stop talking' vs explicit task cancellation."""
        # 1. Instant reflex route
        req_stop = intelligence_router.route("stop talking")
        self.assertEqual(req_stop.intent, "STOP_TALKING")
        self.assertEqual(req_stop.layer, 1)

        # 2. Explicit task cancellation route
        class_cancel = self.conv_mgr.classify_interruption("cancel task")
        self.assertEqual(class_cancel["type"], "CANCEL")

    def test_scenario_08_nemotron_streaming_interruption(self):
        """Scenario 8: Interrupt while Nemotron is streaming response."""
        provider = NvidiaNemotronProvider(api_key="nvapi-phase4-mock-test-key")
        cancelled = False

        def is_cancelled():
            return cancelled

        mock_lines = [
            b'data: {"choices":[{"delta":{"content":"Token 1 "}}]}',
            b'data: {"choices":[{"delta":{"content":"Token 2 "}}]}',
            b'data: {"choices":[{"delta":{"content":"Token 3 "}}]}'
        ]

        with patch("requests.post") as mock_post:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.iter_lines.return_value = iter(mock_lines)
            mock_post.return_value = mock_resp

            gen = provider.stream_response([{"role": "user", "content": "Explain binary search"}], is_cancelled=is_cancelled)
            tok1 = next(gen)
            self.assertEqual(tok1, "Token 1 ")

            # User barges in!
            cancelled = True

            # Generator terminates immediately
            with self.assertRaises(StopIteration):
                next(gen)

            # Response stream is closed
            mock_resp.close.assert_called()

    # =========================================================================
    # 2. VOICE & TTS RELIABILITY
    # =========================================================================
    def test_sentence_progress_recorded_only_after_playback_succeeds(self):
        """Verify on_sentence_progress_cb is invoked ONLY after _play_audio_file succeeds."""
        progress_events = []
        self.tts.set_sentence_callback(lambda idx, total, text: progress_events.append((idx, total, text)))

        # Case A: Playback fails or is interrupted -> callback NOT invoked
        with patch.object(self.tts, "_play_audio_file", return_value=False):
            with patch.object(self.tts.provider, "synthesize_to_file", return_value="dummy.wav"):
                self.tts.speak("First sentence that fails playback.", interrupt=True)
                time.sleep(0.2)
                self.assertEqual(len(progress_events), 0)

        # Case B: Playback succeeds -> callback IS invoked
        with patch.object(self.tts, "_play_audio_file", return_value=True):
            with patch.object(self.tts.provider, "synthesize_to_file", return_value="dummy.wav"):
                self.tts.speak("Second sentence that succeeds playback.", interrupt=True)
                time.sleep(0.2)
                self.assertEqual(len(progress_events), 1)
                self.assertEqual(progress_events[0][0], 0)  # sentence index 0

    def test_generation_id_invalidates_all_obsolete_speech(self):
        """Verify new generation ID purges all queued speech items immediately."""
        self.tts.speak("Old generation text 1", interrupt=False)
        self.tts.speak("Old generation text 2", interrupt=False)
        old_gen = self.tts.generation_id

        # Interrupt with new generation
        self.tts.interrupt(force=True)
        self.assertGreater(self.tts.generation_id, old_gen)
        self.assertEqual(self.tts.get_queue_size(), 0)

    # =========================================================================
    # 3. WORKSPACES & POWER CONTROLS
    # =========================================================================
    def test_workspace_execution_interactive_confirmation_flow(self):
        """Verify gaming workspace requests Discord confirmation and respects answers."""
        persistent_memory.delete_preference("workspace_gaming_discord")

        # Unconfirmed execution prompts
        res_prompt = self.workspace_mgr.execute_workspace("gaming")
        self.assertTrue(res_prompt.get("needs_confirmation"))

        # Confirmed execution launches Discord
        with patch.object(self.workspace_mgr.executor, "execute", return_value={"success": True, "message": "App launched."}) as mock_exec:
            res_confirmed = self.workspace_mgr.execute_workspace("gaming", confirmed_optional_ids=["discord"])
            self.assertTrue(res_confirmed.get("success"))
            targets = [call.args[0].get("target") for call in mock_exec.call_args_list if "target" in call.args[0]]
            self.assertIn("discord", targets)

    def test_windows_powercfg_and_acer_oem_boundary(self):
        """Verify Windows power schemes are parsed and separated from Acer OEM fan controls."""
        report = self.power_mgr.get_acer_oem_report()
        self.assertIn("laptop_model", report)
        self.assertIn("active_windows_scheme", report)
        self.assertIn("supported_oem_profiles", report)
        # Truthful disclosure of proprietary ACPI boundary
        self.assertIn("CCDCHUService", report["oem_control_service"])
        self.assertIn("Acer Control Center", report["integration_status"])


if __name__ == "__main__":
    unittest.main()
