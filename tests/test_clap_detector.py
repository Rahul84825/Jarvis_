import unittest
from config import config
from core.intent_engine import IntentEngine
from modules.system.permissions import INTENT_RISK_MAPPING

class TestClapAndCameraGestureRemoval(unittest.TestCase):
    """Verifies that clap detection and computer-vision gesture subsystems
    are completely removed, while normal app launching of camera is preserved.
    """

    def test_clap_detector_module_removed(self):
        """Verifies that core.clap_detector no longer exists."""
        with self.assertRaises(ImportError):
            import core.clap_detector  # type: ignore

    def test_clap_config_removed(self):
        """Verifies that clap_threshold is removed from configuration."""
        self.assertFalse(hasattr(config, "clap_threshold"))

    def test_camera_control_intent_removed(self):
        """Verifies that dedicated camera_control intent is removed from permissions mapping."""
        self.assertNotIn("camera_control", INTENT_RISK_MAPPING)

    def test_camera_as_normal_application_preserved(self):
        """Verifies that 'open camera' routes to normal application launch (open_app)."""
        engine = IntentEngine()
        res_open = engine.parse("open camera")
        self.assertEqual(res_open["intent"], "open_app")
        self.assertEqual(res_open["target"], "camera")

        res_close = engine.parse("close camera")
        self.assertEqual(res_close["intent"], "close_app")
        self.assertEqual(res_close["target"], "camera")

    def test_gestures_not_present_in_intent_engine(self):
        """Verifies that vision gesture names are not registered as standalone commands."""
        engine = IntentEngine()
        for gesture in ["OPEN_PALM", "PINCH", "POINT", "CLOSED_FIST", "THUMBS_UP"]:
            res = engine.parse(gesture.lower())
            # Should not map to any camera or gesture intent
            self.assertNotEqual(res.get("intent"), "gesture_control")
            self.assertNotEqual(res.get("intent"), "camera_control")

if __name__ == "__main__":
    unittest.main()
