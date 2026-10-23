"""
Unit tests for core.audio_device_resolver.
Verifies headset auto-pairing, explicit preference matching,
and fallback logic.
"""

import unittest
from unittest.mock import patch, MagicMock

from core.audio_device_resolver import resolve_audio_input_device


class TestAudioDeviceResolver(unittest.TestCase):

    def setUp(self):
        self.mock_devices = [
            {"name": "Microsoft Sound Mapper - Input", "max_input_channels": 2, "max_output_channels": 0},
            {"name": "Microphone (Realtek(R) Audio)", "max_input_channels": 2, "max_output_channels": 0},
            {"name": "Headset (Airdopes 131 Elite ANC)", "max_input_channels": 1, "max_output_channels": 0},
            {"name": "Microsoft Sound Mapper - Output", "max_input_channels": 0, "max_output_channels": 2},
            {"name": "Headphones (Airdopes 131 Elite)", "max_input_channels": 0, "max_output_channels": 2},
            {"name": "Speakers (Realtek(R) Audio)", "max_input_channels": 0, "max_output_channels": 2},
        ]

    @patch("core.lazy_loader.lazy_import")
    def test_headset_auto_pairing(self, mock_lazy_import):
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = self.mock_devices
        # Default in is Realtek (1), default out is Airdopes Headphones (4)
        mock_sd.default.device = [1, 4]
        mock_sd.check_input_settings.return_value = None
        mock_lazy_import.return_value = mock_sd

        idx, name = resolve_audio_input_device()
        # Should auto-pair with Airdopes Headset microphone (index 2)
        self.assertEqual(idx, 2)
        self.assertIn("Airdopes", name)

    @patch("core.lazy_loader.lazy_import")
    def test_fallback_to_default_when_speakers_used(self, mock_lazy_import):
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = self.mock_devices
        # Output is Speakers (index 5)
        mock_sd.default.device = [1, 5]
        mock_sd.check_input_settings.return_value = None
        mock_lazy_import.return_value = mock_sd

        idx, name = resolve_audio_input_device()
        # Should use Realtek default mic (index 1)
        self.assertEqual(idx, 1)
        self.assertIn("Realtek", name)

    @patch("core.lazy_loader.lazy_import")
    def test_explicit_preference_index(self, mock_lazy_import):
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = self.mock_devices
        mock_sd.default.device = [1, 4]
        mock_lazy_import.return_value = mock_sd

        idx, name = resolve_audio_input_device(preferred=1)
        self.assertEqual(idx, 1)
        self.assertIn("Realtek", name)

    @patch("core.lazy_loader.lazy_import")
    def test_explicit_preference_name(self, mock_lazy_import):
        mock_sd = MagicMock()
        mock_sd.query_devices.return_value = self.mock_devices
        mock_sd.default.device = [1, 5]
        mock_sd.check_input_settings.return_value = None
        mock_lazy_import.return_value = mock_sd

        idx, name = resolve_audio_input_device(preferred="Airdopes")
        self.assertEqual(idx, 2)
        self.assertIn("Airdopes", name)


if __name__ == "__main__":
    unittest.main()
