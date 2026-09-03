import unittest
import os
import datetime
from pathlib import Path

from core.tts.providers.windows_sapi_provider import WindowsSAPIProvider
from core.tts.providers.edge_tts_provider import EdgeTTSProvider
from core.tts.tts_manager import TTSManager
from core.transcriber import SpeechTranscriber
from core.intent_engine import IntentEngine
from core.command_normalizer import CommandNormalizer
from modules.system.executor import CommandExecutor

class TestSpeechAndCapabilities(unittest.TestCase):

    def test_01_windows_sapi_provider(self):
        sapi = WindowsSAPIProvider()
        self.assertTrue(sapi.is_available(), "Windows SAPI should be available on Windows")
        wav_file = sapi.synthesize_to_file("Testing Windows SAPI offline speech.")
        self.assertIsNotNone(wav_file, "SAPI should generate audio file")
        self.assertTrue(os.path.exists(wav_file), "Generated audio file must exist")
        self.assertGreater(os.path.getsize(wav_file), 1000, "Generated WAV file must have non-zero size")
        if os.path.exists(wav_file):
            os.remove(wav_file)

    def test_02_tts_manager_providers(self):
        manager = TTSManager()
        self.assertIn("sapi", manager._providers)
        self.assertIn("windows", manager._providers)
        self.assertIn("edge", manager._providers)

    def test_03_intent_engine_new_capabilities(self):
        engine = IntentEngine()

        # Time
        res_time = engine.parse("what time is it")
        self.assertEqual(res_time["intent"], "time_query")

        # Date
        res_date = engine.parse("what is today's date")
        self.assertEqual(res_date["intent"], "date_query")

        # Math
        res_math1 = engine.parse("calculate 25 * 4")
        self.assertEqual(res_math1["intent"], "math_calculation")

        res_math2 = engine.parse("what is 15 percent of 800")
        self.assertEqual(res_math2["intent"], "math_calculation")

        # Media
        res_media1 = engine.parse("play music")
        self.assertEqual(res_media1["intent"], "media_control")

        res_media2 = engine.parse("next song")
        self.assertEqual(res_media2["intent"], "media_control")

        # Speech test
        res_speech = engine.parse("test speech")
        self.assertEqual(res_speech["intent"], "test_speech")

        # Web search
        res_search = engine.parse("search google for python")
        self.assertEqual(res_search["intent"], "web_search")

    def test_04_executor_new_capabilities(self):
        executor = CommandExecutor()

        # Time
        res_time = executor.execute({"intent": "time_query", "action": "get_time"})
        self.assertTrue(res_time["success"])
        self.assertIn("The time is", res_time["message"])

        # Date
        res_date = executor.execute({"intent": "date_query", "action": "get_date"})
        self.assertTrue(res_date["success"])
        self.assertIn("Today is", res_date["message"])

        # Math
        res_math = executor.execute({"intent": "math_calculation", "target": "calculate 25 * 4"})
        self.assertTrue(res_math["success"])
        self.assertIn("100", res_math["message"])

        res_pct = executor.execute({"intent": "math_calculation", "target": "15 percent of 800"})
        self.assertTrue(res_pct["success"])
        self.assertIn("120", res_pct["message"])

        # Speech test
        res_speech = executor.execute({"intent": "test_speech", "action": "test_speech"})
        self.assertTrue(res_speech["success"])

if __name__ == "__main__":
    unittest.main()
