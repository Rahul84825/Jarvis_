import time
import unittest
from unittest.mock import MagicMock
from core.wakeword import MockWakeWordDetector

class TestWakeWord(unittest.TestCase):
    def test_callback_trigger(self):
        """Verifies that the registered callback triggers when wake word is detected."""
        detector = MockWakeWordDetector(wake_words=["jarvis", "computer"])
        
        callback_mock = MagicMock()
        detector.start(callback_mock)
        
        try:
            # Trigger mock detection
            detector.trigger_mock_detection("jarvis")
            callback_mock.assert_called_once_with("jarvis")
            
            # Reset mock and trigger default
            callback_mock.reset_mock()
            detector.trigger_mock_detection("invalid_word")  # Should fall back to first word
            callback_mock.assert_called_once_with("jarvis")
            
        finally:
            detector.stop()

    def test_start_stop_state(self):
        """Verifies startup/shutdown listening states of the detector."""
        detector = MockWakeWordDetector()
        
        self.assertFalse(detector.is_listening())
        
        callback_mock = MagicMock()
        detector.start(callback_mock)
        
        self.assertTrue(detector.is_listening())
        
        detector.stop()
        self.assertFalse(detector.is_listening())

    def test_factory_creation(self):
        """Verifies that WakeWordDetectorFactory instantiates correct engines."""
        from core.wakeword import WakeWordDetectorFactory, MockWakeWordDetector, OpenWakeWordDetector, PorcupineWakeWordDetector
        
        mock_det = WakeWordDetectorFactory.create_detector("mock")
        self.assertIsInstance(mock_det, MockWakeWordDetector)

        oww_det = WakeWordDetectorFactory.create_detector("openwakeword")
        self.assertIsInstance(oww_det, OpenWakeWordDetector)

        porc_det = WakeWordDetectorFactory.create_detector("porcupine")
        self.assertIsInstance(porc_det, PorcupineWakeWordDetector)

        fallback_det = WakeWordDetectorFactory.create_detector("unknown_engine_type")
        self.assertIsInstance(fallback_det, MockWakeWordDetector)

if __name__ == "__main__":
    unittest.main()

