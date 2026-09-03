import unittest
from unittest.mock import MagicMock, patch
from core.tts.base_tts import BaseTTS
from core.tts.tts_manager import TTSManager
from core.tts.providers.edge_tts_provider import EdgeTTSProvider
from core.tts.providers.pyttsx3_provider import Pyttsx3Provider
from core.tts.providers.gtts_provider import GTTSProvider

class TestTTSManager(unittest.TestCase):

    def setUp(self):
        self.manager = TTSManager()

    def test_default_provider(self):
        self.assertIsInstance(self.manager.provider, BaseTTS)

    def test_provider_switching(self):
        self.manager.set_provider("pyttsx3")
        self.assertIsInstance(self.manager.provider, Pyttsx3Provider)

        self.manager.set_provider("gtts")
        self.assertIsInstance(self.manager.provider, GTTSProvider)

        self.manager.set_provider("edge")
        self.assertIsInstance(self.manager.provider, EdgeTTSProvider)

    def test_speech_queueing(self):
        self.manager.speak("Test line 1", interrupt=False)
        self.assertFalse(self.manager._queue.empty())

    def test_interrupt_flushes_queue(self):
        self.manager.speak("Test line 1", interrupt=False)
        self.manager.speak("Test line 2", interrupt=False)
        self.manager.interrupt()
        self.assertTrue(self.manager._queue.empty())

if __name__ == "__main__":
    unittest.main()
