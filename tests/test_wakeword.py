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

    def test_openwakeword_real_readiness(self):
        """Verifies that OpenWakeWordDetector loads models and reports readiness."""
        from core.wakeword import OpenWakeWordDetector
        det = OpenWakeWordDetector(wake_words=["jarvis"])
        self.assertTrue(det.is_available())
        diag = det.get_diagnostic()
        self.assertIn("OpenWakeWord ready with ONNX models", diag)

    def test_porcupine_diagnostic_reporting(self):
        """Verifies that Porcupine reports clear diagnostic when API key is missing."""
        from core.wakeword import PorcupineWakeWordDetector
        det = PorcupineWakeWordDetector(api_key="")
        self.assertFalse(det.is_available())
        self.assertIn("API key missing", det.get_diagnostic())

    def test_openwakeword_prediction_call(self):
        """Verifies that the loaded ONNX model can perform inference on audio chunk."""
        import numpy as np
        from core.wakeword import OpenWakeWordDetector
        det = OpenWakeWordDetector(wake_words=["jarvis"])
        self.assertTrue(det.is_available())
        dummy_chunk = np.zeros(1280, dtype=np.int16)
        pred = det._model.predict(dummy_chunk)
        self.assertIsInstance(pred, dict)
        self.assertIn("hey_jarvis", pred)

if __name__ == "__main__":
    unittest.main()


