import os
import unittest
from unittest.mock import patch, MagicMock
from core.tts.providers.edge_tts_provider import EdgeTTSProvider
from core.tts.providers.pyttsx3_provider import Pyttsx3Provider
from core.tts.providers.gtts_provider import GTTSProvider

class TestTTSProviders(unittest.TestCase):

    def test_provider_names(self):
        e = EdgeTTSProvider()
        p = Pyttsx3Provider()
        g = GTTSProvider()

        self.assertIn("EdgeTTS", e.get_name())
        self.assertIn("pyttsx3", p.get_name())
        self.assertIn("gTTS", g.get_name())

    def test_edge_tts_empty_input(self):
        e = EdgeTTSProvider()
        self.assertIsNone(e.synthesize_to_file(""))
        self.assertIsNone(e.synthesize_to_file("   "))

    def test_pyttsx3_empty_input(self):
        p = Pyttsx3Provider()
        self.assertIsNone(p.synthesize_to_file(""))

    def test_gtts_empty_input(self):
        g = GTTSProvider()
        self.assertIsNone(g.synthesize_to_file(""))

if __name__ == "__main__":
    unittest.main()
