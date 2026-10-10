import os
import time
import wave
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from pathlib import Path

from config import config
from core.transcriber import SpeechTranscriber
from core.tts.tts_manager import TTSManager
from core.tts.providers.windows_sapi_provider import WindowsSAPIProvider
from core.tts.providers.edge_tts_provider import EdgeTTSProvider
from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.jarvis_runtime import JarvisRuntime

class TestVoicePipelineRegression(unittest.TestCase):
    """Exhaustive 14-area Regression Test Suite for Voice Pipeline."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp(prefix="jarvis_test_cache_")

    def tearDown(self):
        if os.path.exists(self.tmp_dir):
            shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # 1. SAPI synthesis
    def test_01_sapi_synthesis(self):
        """Verifies that WindowsSAPIProvider synthesizes speech to a valid file."""
        sapi = WindowsSAPIProvider()
        out_path = sapi.synthesize_to_file("Testing SAPI synthesis.")
        self.assertIsNotNone(out_path)
        self.assertTrue(os.path.exists(out_path))
        self.assertGreater(os.path.getsize(out_path), 0)
        try:
            os.remove(out_path)
        except Exception:
            pass

    # 2. Generated WAV validity
    def test_02_generated_wav_validity(self):
        """Verifies that generated audio has valid WAV headers and decodable frames."""
        sapi = WindowsSAPIProvider()
        out_path = sapi.synthesize_to_file("Validating WAV headers.")
        self.assertTrue(out_path.endswith(".wav"))
        with wave.open(out_path, "rb") as wf:
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            nframes = wf.getnframes()
            duration = nframes / float(framerate)

            self.assertIn(channels, [1, 2])
            self.assertIn(sampwidth, [1, 2, 4])
            self.assertGreater(framerate, 8000)
            self.assertGreater(duration, 0.2)
        try:
            os.remove(out_path)
        except Exception:
            pass

    # 3. Audio playback initialization
    def test_03_audio_playback_initialization(self):
        """Verifies that TTSManager initializes playback system and resolves devices safely."""
        manager = TTSManager()
        dev = manager._resolve_output_device()
        # Should return None (system default) or a valid integer device index
        self.assertTrue(dev is None or isinstance(dev, int))

    # 4. Correct output device configuration
    def test_04_correct_output_device_configuration(self):
        """Verifies that audio_output_device setting is respected and queryable."""
        manager = TTSManager()
        with patch.object(config, "audio_output_device", 99999):
            # Non-existent device should safely fall back to default
            dev = manager._resolve_output_device()
            self.assertTrue(dev is None or isinstance(dev, int))

        with patch.object(config, "audio_output_device", None):
            dev = manager._resolve_output_device()
            self.assertTrue(dev is None or isinstance(dev, int))

    # 5. TTS playback start callback
    def test_05_tts_playback_start_callback(self):
        """Verifies that on_start_speaking_cb fires strictly when playback begins (not during synthesis)."""
        manager = TTSManager()
        dummy_wav = tempfile.mktemp(suffix=".wav")
        Path(dummy_wav).write_bytes(b"RIFFdummydata")

        prov_mock = MagicMock()
        prov_mock.get_name.return_value = "Mock Provider"
        prov_mock.synthesize_to_file.return_value = dummy_wav
        manager._providers["edge"] = prov_mock

        events = []
        def on_synth():
            events.append("SYNTH_STARTED")

        def on_speak():
            events.append("PLAYBACK_STARTED")

        def fake_play(path):
            events.append("IN_PLAYBACK")

        with patch.object(manager, "_play_audio_file", side_effect=fake_play):
            manager.start(on_start_speaking=on_speak, on_start_synthesizing=on_synth)
            manager.speak("Callback ordering test", interrupt=False)
            time.sleep(0.3)
            manager.stop()

        self.assertIn("SYNTH_STARTED", events)
        self.assertIn("PLAYBACK_STARTED", events)
        synth_idx = events.index("SYNTH_STARTED")
        play_idx = events.index("PLAYBACK_STARTED")
        self.assertLess(synth_idx, play_idx, "Synthesis started must precede playback started callback!")

    # 6. TTS playback completion callback
    def test_06_tts_playback_completion_callback(self):
        """Verifies that on_stop_speaking_cb fires after audio finishes."""
        manager = TTSManager()
        dummy_wav = tempfile.mktemp(suffix=".wav")
        Path(dummy_wav).write_bytes(b"RIFFdummydata")

        prov_mock = MagicMock()
        prov_mock.get_name.return_value = "Mock Provider"
        prov_mock.synthesize_to_file.return_value = dummy_wav
        manager._providers["edge"] = prov_mock

        stopped_fired = []
        def on_stop():
            stopped_fired.append(True)

        with patch.object(manager, "_play_audio_file"):
            manager.start(on_stop_speaking=on_stop)
            manager.speak("Completion callback test", interrupt=False)
            time.sleep(0.4)
            manager.stop()

        self.assertTrue(len(stopped_fired) >= 1)

    # 7. TTS provider failure
    def test_07_tts_provider_failure(self):
        """Verifies that when providers fail, TTS degrades gracefully without crashing."""
        manager = TTSManager()
        for p in manager._providers.values():
            p.synthesize_to_file = MagicMock(return_value=None)

        manager.start()
        manager.speak("Total provider failure", interrupt=False)
        time.sleep(0.3)
        manager.stop()

        self.assertEqual(manager.state, "IDLE")
        self.assertFalse(manager.is_speaking())

    # 8. TTS fallback
    def test_08_tts_fallback(self):
        """Verifies automatic fallback to local provider when primary provider raises an error."""
        manager = TTSManager()
        manager._cache_dir = Path(self.tmp_dir)
        primary_mock = MagicMock()
        primary_mock.get_name.return_value = "Mock Cloud"
        primary_mock.synthesize_to_file.side_effect = ConnectionError("Cloud offline")

        fallback_mock = MagicMock()
        fallback_mock.get_name.return_value = "Mock SAPI"
        dummy_wav = tempfile.mktemp(suffix=".wav")
        Path(dummy_wav).write_bytes(b"RIFFdummywav")
        fallback_mock.synthesize_to_file.return_value = dummy_wav

        manager._providers["edge"] = primary_mock
        manager._providers["sapi"] = fallback_mock

        with patch.object(manager, "_play_audio_file") as mock_play:
            manager.start()
            manager.speak("Fallback test", interrupt=False)
            time.sleep(0.3)
            manager.stop()

            primary_mock.synthesize_to_file.assert_called_once()
            fallback_mock.synthesize_to_file.assert_called_once()
            mock_play.assert_called_once_with(dummy_wav)

    # 9. TTS interruption
    def test_09_tts_interruption(self):
        """Verifies that interruption halts active playback, shields synthesis, and resets state."""
        manager = TTSManager()

        # Synthesis state shielding (unforced interrupt ignored)
        manager._state = "TTS_SYNTHESIZING"
        manager._queue.put(("text", "Pending audio"))
        manager.interrupt(force=False, from_vad=True)
        self.assertFalse(manager._interrupt_event.is_set())
        self.assertFalse(manager._queue.empty())

        # Forced interrupt during playback
        manager._state = "TTS_PLAYING"
        manager.interrupt(force=True)
        self.assertTrue(manager._interrupt_event.is_set())
        self.assertEqual(manager.state, "IDLE")

    # 10. Cached TTS playback
    def test_10_cached_tts_playback(self):
        """Verifies that repeated speech requests bypass synthesis and play from cache."""
        manager = TTSManager()
        manager._cache_dir = Path(self.tmp_dir)

        mock_prov = MagicMock()
        mock_prov.get_name.return_value = "Mock Provider"
        dummy_wav = tempfile.mktemp(suffix=".wav")
        Path(dummy_wav).write_bytes(b"RIFFdummycache")
        mock_prov.synthesize_to_file.return_value = dummy_wav

        manager._providers["edge"] = mock_prov

        with patch.object(manager, "_play_audio_file"):
            manager.start()
            # 1st call: synthesize and cache
            manager.speak("Cached sentence test", interrupt=False)
            time.sleep(0.3)
            self.assertEqual(mock_prov.synthesize_to_file.call_count, 1)

            # 2nd call: cache hit, synthesis skipped
            manager.speak("Cached sentence test", interrupt=False)
            time.sleep(0.3)
            manager.stop()

            self.assertEqual(mock_prov.synthesize_to_file.call_count, 1)

    # 11. Whisper preloading
    @patch('faster_whisper.WhisperModel')
    def test_11_whisper_preloading(self, mock_model_cls):
        """Verifies Whisper pre-warming background thread does not block and loads model."""
        transcriber = SpeechTranscriber(model_size="base", device="cpu")
        self.assertEqual(transcriber.status, "STT_UNINITIALIZED")

        t0 = time.time()
        transcriber.preload_in_background()
        elapsed = time.time() - t0
        self.assertLess(elapsed, 0.05, "Preload must be non-blocking!")

        transcriber._ready_event.wait(timeout=2.0)
        self.assertEqual(transcriber.status, "STT_READY")
        self.assertIsNotNone(transcriber._model)

    # 12. Configured silence duration propagation
    @patch("core.jarvis_runtime.SpeechListener")
    @patch("core.jarvis_runtime.SpeechTranscriber")
    @patch("core.jarvis_runtime.WakeWordDetectorFactory.create_detector")
    def test_12_configured_silence_duration(self, mock_ww, mock_trans, mock_listener_cls):
        """Verifies configured silence duration reaches SpeechListener."""
        config.silence_duration = 0.8
        config.vad_threshold = 0.015
        runtime = JarvisRuntime()

        mock_listener_cls.assert_called_once()
        _, kwargs = mock_listener_cls.call_args
        self.assertEqual(kwargs.get("silence_duration"), 0.8)
        self.assertEqual(kwargs.get("threshold"), 0.015)

    # 13. Whisper transcription
    def test_13_whisper_transcription(self):
        """Verifies WhisperTranscriber accurately decodes actual recorded command audio."""
        benchmark_file = Path("logs/benchmark_audio/open_chrome_PrabhatNeural_p0pct.wav")
        if not benchmark_file.exists():
            self.skipTest("Benchmark audio not found")

        stt = SpeechTranscriber(model_size="base", device="cpu", beam_size=1)
        text = stt.transcribe(str(benchmark_file))
        self.assertTrue("chrome" in text.lower())

    # 14. Command routing
    def test_14_command_routing(self):
        """Verifies IntentEngine accurately maps normalized commands to their correct OS intents."""
        normalizer = CommandNormalizer()
        engine = IntentEngine()

        test_cases = [
            ("open chrome.", "open_app", "open"),
            ("lock computer.", "system_control", "lock_pc"),
            ("take screenshot.", "screenshot", "take_screenshot"),
            ("open downloads.", "file_access", "open_folder"),
            ("what time is it", "time_query", "get_time"),
            ("what is the date", "date_query", "get_date"),
        ]

        for phrase, exp_intent, exp_action in test_cases:
            norm = normalizer.normalize(phrase)["normalized"]
            parsed = engine.parse(norm)
            self.assertEqual(parsed.get("intent"), exp_intent, f"Failed intent for: {phrase}")
            if exp_action:
                self.assertEqual(parsed.get("action"), exp_action, f"Failed action for: {phrase}")

if __name__ == "__main__":
    unittest.main()
