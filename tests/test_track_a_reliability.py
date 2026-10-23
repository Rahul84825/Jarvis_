import os
import unittest
from unittest.mock import patch, MagicMock
import numpy as np

from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.os.browser_manager import BrowserManager
from core.wakeword import OpenWakeWordDetector, MockWakeWordDetector, WakeWordDetectorFactory
from core.listener import SpeechListener
from core.jarvis_runtime import JarvisRuntime

class TestTrackAReliability(unittest.TestCase):
    """Focused regression test suite covering Track A Master Implementation objectives:
    1. Wake-Word reliability and audio concurrency.
    2. Manual Talk button reliability and state safety.
    3. Dedicated natural-language YouTube search intent and browser navigation.
    """

    def setUp(self):
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.browser_mgr = BrowserManager()

    # =========================================================================
    # 1. WAKE-WORD DETECTION & AUDIO CONCURRENCY TESTS
    # =========================================================================
    def test_openwakeword_model_loaded(self):
        """Verify OpenWakeWord engine initializes ONNX model successfully."""
        detector = OpenWakeWordDetector(wake_words=["jarvis"])
        self.assertTrue(detector.is_available(), f"Model failed to load: {detector.get_diagnostic()}")
        self.assertIn("hey_jarvis", detector.get_diagnostic().lower())

    def test_missing_model_produces_explicit_failure_state(self):
        """Verify detector handles non-existent model path safely with clear diagnostic."""
        detector = OpenWakeWordDetector(model_path="non_existent_model_file_12345.onnx")
        # Should either fallback gracefully or set diagnostic explaining failure
        self.assertIsInstance(detector.get_diagnostic(), str)
        self.assertTrue(len(detector.get_diagnostic()) > 0)

    def test_external_audio_feeding_prevents_duplicate_stream(self):
        """Verify feeding PCM chunks marks detector as externally fed without opening secondary stream."""
        detector = OpenWakeWordDetector(wake_words=["jarvis"])
        dummy_pcm = np.zeros(1280, dtype=np.int16)
        detector.feed_pcm_frame(dummy_pcm)
        self.assertTrue(detector._external_feed_active)
        self.assertFalse(detector._audio_queue.empty())

    def test_listener_registers_and_dispatches_audio_consumers(self):
        """Verify SpeechListener registers consumers and dispatches PCM frames in audio callback."""
        listener = SpeechListener()
        received_chunks = []

        def consumer_cb(pcm_data):
            received_chunks.append(pcm_data)

        listener.add_audio_consumer(consumer_cb)
        self.assertIn(consumer_cb, listener._audio_consumers)

        listener._running = True
        # Simulate audio callback with 2048 float samples
        fake_indata = np.ones((2048, 1), dtype=np.float32) * 0.5
        listener._audio_callback(fake_indata, 2048, None, None)

        self.assertEqual(len(received_chunks), 1)
        self.assertIsInstance(received_chunks[0], np.ndarray)
        self.assertEqual(received_chunks[0].dtype, np.int16)

        # Test unregistering
        listener.remove_audio_consumer(consumer_cb)
        self.assertNotIn(consumer_cb, listener._audio_consumers)

    def test_listener_acoustic_cooldown_after_tts(self):
        """Verify SpeechListener sets acoustic cooldown when TTS speaking completes."""
        listener = SpeechListener()
        listener.set_speaking_active(True)
        self.assertTrue(listener.speaking_active)
        listener.set_speaking_active(False)
        self.assertFalse(listener.speaking_active)
        self.assertGreater(listener._speaking_cooldown_until, 0.0)

    # =========================================================================
    # 2. MANUAL TALK BUTTON RELIABILITY TESTS
    # =========================================================================
    @patch("core.jarvis_runtime.TTSManager")
    @patch("core.jarvis_runtime.SpeechListener")
    @patch("core.jarvis_runtime.WakeWordDetectorFactory")
    def test_manual_talk_initiates_listening_independently(self, mock_ww_factory, mock_listener_cls, mock_tts_cls):
        """Verify manual Talk button transitions to LISTENING and triggers capture."""
        mock_ww = MagicMock()
        mock_ww_factory.create_detector.return_value = mock_ww
        mock_listener = MagicMock()
        mock_listener.is_recording.return_value = False
        mock_listener.is_listening.return_value = True
        mock_listener_cls.return_value = mock_listener
        mock_tts = MagicMock()
        mock_tts.is_speaking.return_value = False
        mock_tts_cls.return_value = mock_tts

        runtime = JarvisRuntime()
        runtime.current_status = "STANDBY"

        runtime.trigger_manual_talk()

        self.assertEqual(runtime.current_status, "LISTENING")
        self.assertEqual(runtime.current_speech_text, "Listening...")
        mock_listener.trigger_manual_recording.assert_called_once_with(manual=True)

    @patch("core.jarvis_runtime.TTSManager")
    @patch("core.jarvis_runtime.SpeechListener")
    def test_manual_talk_toggles_stop_when_already_recording(self, mock_listener_cls, mock_tts_cls):
        """Verify clicking Talk button while already recording toggles off to finalize speech without buffer wipe."""
        mock_listener = MagicMock()
        mock_listener.is_recording.return_value = True
        mock_listener_cls.return_value = mock_listener
        mock_tts = MagicMock()
        mock_tts.is_speaking.return_value = False
        mock_tts_cls.return_value = mock_tts

        runtime = JarvisRuntime()
        runtime.current_status = "LISTENING"

        runtime.trigger_manual_talk()

        # Should call stop_manual_recording to commit utterance, not restart/wipe buffer
        mock_listener.stop_manual_recording.assert_called_once()
        mock_listener.trigger_manual_recording.assert_not_called()

    @patch("core.jarvis_runtime.TTSManager")
    @patch("core.jarvis_runtime.SpeechListener")
    def test_manual_talk_interrupts_tts_playback(self, mock_listener_cls, mock_tts_cls):
        """Verify clicking Talk button while TTS is active interrupts speech immediately."""
        mock_listener = MagicMock()
        mock_listener.is_recording.return_value = False
        mock_listener.is_listening.return_value = True
        mock_listener_cls.return_value = mock_listener
        mock_tts = MagicMock()
        mock_tts.is_speaking.return_value = True
        mock_tts_cls.return_value = mock_tts

        runtime = JarvisRuntime()
        runtime.trigger_manual_talk()

        mock_tts.interrupt.assert_called_once_with(force=True)
        self.assertEqual(runtime.current_status, "LISTENING")

    @patch("core.jarvis_runtime.TTSManager")
    @patch("core.jarvis_runtime.SpeechListener")
    def test_manual_talk_suppressed_during_busy_stages(self, mock_listener_cls, mock_tts_cls):
        """Verify clicking Talk button during TRANSCRIBING or EXECUTING does not disrupt pipeline."""
        mock_listener = MagicMock()
        mock_listener.is_recording.return_value = False
        mock_listener_cls.return_value = mock_listener
        mock_tts = MagicMock()
        mock_tts.is_speaking.return_value = False
        mock_tts_cls.return_value = mock_tts

        runtime = JarvisRuntime()
        for busy_state in ["TRANSCRIBING", "UNDERSTANDING", "EXECUTING"]:
            runtime.current_status = busy_state
            runtime.trigger_manual_talk()
            self.assertEqual(runtime.current_status, busy_state)
            mock_listener.trigger_manual_recording.assert_not_called()

    # =========================================================================
    # 3. YOUTUBE SEARCH NATURAL-LANGUAGE INTENT & EXTRACTION TESTS
    # =========================================================================
    def test_all_master_prompt_youtube_search_patterns(self):
        """Verify query extraction from all 10 supported natural-language prompt patterns."""
        cases = [
            ("Search YouTube for Python tutorials.", "Python tutorials", "default"),
            ("Jarvis, search anything on YouTube about React.", "React", "default"),
            ("Find DSA lectures on YouTube.", "DSA lectures", "default"),
            ("Look up the best C++ inheritance tutorials on YouTube.", "the best C++ inheritance tutorials", "default"),
            ("Search YouTube for relaxing music.", "relaxing music", "default"),
            ("Find recent AI news videos on YouTube.", "recent AI news videos", "default"),
            ("Search YouTube for how to build a desktop AI assistant.", "how to build a desktop AI assistant", "default"),
            ("Open YouTube and search for MERN stack projects.", "MERN stack projects", "default"),
            ("Find a video about binary search and open the results.", "binary search", "default"),
            ("Search YouTube for this topic: machine learning for beginners.", "machine learning for beginners", "default"),
            ("search YouTube for Python tutorials in Chrome", "Python tutorials", "chrome")
        ]

        for text, expected_query, expected_browser in cases:
            is_yt, query, browser = self.normalizer.extract_youtube_search(text)
            self.assertTrue(is_yt, f"Failed to recognize YouTube search for: '{text}'")
            self.assertEqual(query, expected_query, f"Query mismatch for: '{text}' (Got: '{query}', Expected: '{expected_query}')")
            self.assertEqual(browser, expected_browser, f"Browser mismatch for: '{text}'")

            # Verify IntentEngine routes to web_search with provider=youtube
            node = self.intent_engine.parse(text)
            self.assertEqual(node["intent"], "web_search", f"Intent mismatch for '{text}'")
            self.assertEqual(node["provider"], "youtube", f"Provider mismatch for '{text}'")
            self.assertEqual(node["query"], expected_query, f"Engine query mismatch for '{text}'")
            self.assertEqual(node["browser"], expected_browser, f"Engine browser mismatch for '{text}'")

    def test_open_youtube_does_not_trigger_search(self):
        """Verify 'Open YouTube' opens homepage/app and does not trigger search."""
        node = self.intent_engine.parse("Open YouTube")
        self.assertNotEqual(node.get("action"), "search")
        self.assertIn(node.get("intent"), ["open_app", "open_website"])

    def test_search_google_does_not_route_to_youtube(self):
        """Verify 'Search Google for Python tutorials' remains standard Google search."""
        node = self.intent_engine.parse("Search Google for Python tutorials")
        self.assertEqual(node["intent"], "web_search")
        self.assertEqual(node["provider"], "google")

    def test_open_chatgpt_in_chrome_preserved(self):
        """Verify 'Open ChatGPT in Chrome' is preserved as browser/app command."""
        node = self.intent_engine.parse("Open ChatGPT in Chrome")
        self.assertNotEqual(node.get("provider"), "youtube")
        self.assertIn(node.get("intent"), ["open_app", "open_website"])

    def test_arbitrary_topic_search(self):
        """Verify arbitrary user topics without hardcoded lists work seamlessly."""
        text = "search YouTube for quantum telemetry algorithms in rust"
        is_yt, query, browser = self.normalizer.extract_youtube_search(text)
        self.assertTrue(is_yt)
        self.assertEqual(query, "quantum telemetry algorithms in rust")

    def test_youtube_search_url_encoding(self):
        """Verify URL encoding handles spaces, plus signs, and punctuation safely."""
        query = "C++ & Python: best practices?"
        url = self.browser_mgr.build_search_url("youtube", query)
        self.assertEqual(url, "https://www.youtube.com/results?search_query=C%2B%2B+%26+Python%3A+best+practices%3F")

    @patch("core.platform.platform_manager.platform_manager.open_browser", return_value=True)
    def test_youtube_search_execution_and_truthful_response(self, mock_open):
        """Verify YouTube search execution returns truthful success response."""
        res = self.browser_mgr.search("React project tutorials", provider="youtube")
        self.assertTrue(res["success"])
        self.assertEqual(res["provider"], "youtube")
        self.assertIn("I opened YouTube search results for 'React project tutorials'", res["message"])

    @patch("core.platform.platform_manager.platform_manager.open_browser", return_value=False)
    def test_browser_launch_failure_reported_truthfully(self, mock_open):
        """Verify browser launch failure does not falsely claim success."""
        res = self.browser_mgr.search("Python", provider="youtube")
        self.assertFalse(res["success"])
        self.assertIn("couldn't open", res["message"].lower())

    def test_multi_command_chain_protection(self):
        """Verify 'Open YouTube and search for MERN stack projects' is not prematurely split."""
        split_cmds = self.normalizer.split_chained_commands("Open YouTube and search for MERN stack projects")
        self.assertEqual(len(split_cmds), 1)
        self.assertIn("search for MERN stack projects", split_cmds[0])

if __name__ == "__main__":
    unittest.main()
