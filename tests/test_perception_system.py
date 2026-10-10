"""
Unit and Integration Tests for JARVIS Perception & Vision Subsystem.
Covers:
1. CameraDevice & MockCameraDevice lifecycle, frame generation, and device discovery
2. RollingFrameBuffer thread-safe in-memory ring buffer
3. HandTracker landmark parsing & fallbacks
4. GestureEngine landmark geometric analysis & temporal debounce
5. CameraManager refcounted ownership, device discovery & lifecycle
6. Layer 1 IntentEngine camera commands & Tool Registry integration
"""

import unittest
import time
from core.perception.vision_config import VisionConfig
from core.perception.perception_events import (
    CameraState, GestureType, NormalizedLandmark, HandObservation, GestureEvent, CameraDeviceInfo
)
from core.perception.camera_device import MockCameraDevice, create_camera_device
from core.perception.frame_pipeline import RollingFrameBuffer
from core.perception.hand_tracker import HandTracker
from core.perception.gesture_engine import GestureEngine
from core.perception.camera_manager import CameraManager, get_camera_manager
from core.intent_engine import IntentEngine
from core.ai.tools.registry import ToolRegistry


class TestPerceptionEvents(unittest.TestCase):
    def test_landmark_and_observation(self):
        lm = NormalizedLandmark(x=0.5, y=0.5, z=0.0)
        self.assertEqual(lm.x, 0.5)

        obs = HandObservation(
            hand_id=0,
            handedness="Right",
            confidence=0.95,
            landmarks=[lm] * 21,
            bbox=(0.4, 0.4, 0.6, 0.6)
        )
        self.assertEqual(obs.handedness, "Right")
        self.assertEqual(len(obs.landmarks), 21)

    def test_gesture_event(self):
        event = GestureEvent(
            gesture=GestureType.PINCH,
            confidence=0.88,
            hand="Right"
        )
        self.assertEqual(event.gesture, GestureType.PINCH)
        self.assertGreater(event.timestamp, 0)

    def test_camera_device_info(self):
        info = CameraDeviceInfo(index=0, name="Integrated Webcam", backend="DSHOW", is_default=True, available=True)
        self.assertEqual(info.index, 0)
        self.assertTrue(info.is_default)


class TestCameraDevice(unittest.TestCase):
    def test_mock_camera_device(self):
        device = MockCameraDevice()
        self.assertFalse(device.is_opened())

        success = device.open(0, width=640, height=480, fps=30)
        self.assertTrue(success)
        self.assertTrue(device.is_opened())

        ret, frame = device.read_frame()
        self.assertTrue(ret)
        self.assertEqual(frame.shape, (480, 640, 3))

        devices = device.list_devices()
        self.assertGreaterEqual(len(devices), 1)

        device.release()
        self.assertFalse(device.is_opened())


class TestRollingFrameBuffer(unittest.TestCase):
    def test_frame_buffer_push_and_get(self):
        buffer = RollingFrameBuffer(max_seconds=2.0, fps=10)
        latest, _ = buffer.get_latest()
        self.assertIsNone(latest)

        device = MockCameraDevice()
        device.open(0)
        _, frame = device.read_frame()
        device.release()

        buffer.push(frame)
        latest, ts = buffer.get_latest()
        self.assertIsNotNone(latest)
        self.assertEqual(latest.shape, frame.shape)

        recent = buffer.get_recent_frames(duration_seconds=5.0)
        self.assertEqual(len(recent), 1)

        sheet = buffer.get_contact_sheet(grid_size=(1, 1))
        self.assertIsNotNone(sheet)

        buffer.clear()
        latest, _ = buffer.get_latest()
        self.assertIsNone(latest)


class TestHandTracker(unittest.TestCase):
    def test_hand_tracker_synthetic_frame(self):
        tracker = HandTracker()
        device = MockCameraDevice()
        device.open(0)
        _, frame = device.read_frame()
        device.release()

        hands = tracker.process_frame(frame)
        self.assertIsInstance(hands, list)
        self.assertGreaterEqual(len(hands), 1)
        self.assertEqual(len(hands[0].landmarks), 21)
        tracker.close()


class TestGestureEngine(unittest.TestCase):
    def _create_mock_landmarks(self, thumb_tip_pos, index_tip_pos, other_extended=True):
        # 21 landmarks
        # 0: Wrist, 4: Thumb Tip, 8: Index Tip, 6: Index PIP
        # 12: Middle Tip, 10: Middle PIP, 16: Ring Tip, 14: Ring PIP, 20: Pinky Tip, 18: Pinky PIP
        lms = [NormalizedLandmark(x=0.5, y=0.5, z=0.0) for _ in range(21)]
        lms[0] = NormalizedLandmark(x=0.5, y=0.8, z=0.0)  # wrist
        lms[4] = NormalizedLandmark(x=thumb_tip_pos[0], y=thumb_tip_pos[1], z=0.0)
        lms[8] = NormalizedLandmark(x=index_tip_pos[0], y=index_tip_pos[1], z=0.0)
        lms[6] = NormalizedLandmark(x=0.5, y=0.5, z=0.0)

        other_y = 0.2 if other_extended else 0.7
        pip_y = 0.5
        lms[12] = NormalizedLandmark(x=0.5, y=other_y, z=0.0)
        lms[10] = NormalizedLandmark(x=0.5, y=pip_y, z=0.0)
        lms[16] = NormalizedLandmark(x=0.6, y=other_y, z=0.0)
        lms[14] = NormalizedLandmark(x=0.6, y=pip_y, z=0.0)
        lms[20] = NormalizedLandmark(x=0.7, y=other_y, z=0.0)
        lms[18] = NormalizedLandmark(x=0.7, y=pip_y, z=0.0)
        return lms

    def test_pinch_gesture_recognition(self):
        engine = GestureEngine(debounce_frames=2, cooldown_seconds=0.1, confidence_threshold=0.5)
        # Thumb & Index close together (dist < 0.065)
        lms = self._create_mock_landmarks(thumb_tip_pos=(0.50, 0.30), index_tip_pos=(0.51, 0.30))
        hand = HandObservation(hand_id=0, handedness="Right", confidence=0.9, landmarks=lms, bbox=(0, 0, 1, 1))

        # Feed frames to trigger temporal debounce
        engine.evaluate_hand(hand)
        e2 = engine.evaluate_hand(hand)
        self.assertIsNotNone(e2)
        self.assertEqual(e2.gesture, GestureType.PINCH)

    def test_open_palm_recognition(self):
        engine = GestureEngine(debounce_frames=2, cooldown_seconds=0.1, confidence_threshold=0.5)
        # Thumb & Index far apart, all fingers extended (y tip < y pip)
        lms = self._create_mock_landmarks(thumb_tip_pos=(0.2, 0.3), index_tip_pos=(0.4, 0.2), other_extended=True)
        hand = HandObservation(hand_id=0, handedness="Right", confidence=0.9, landmarks=lms, bbox=(0, 0, 1, 1))

        engine.evaluate_hand(hand)
        e2 = engine.evaluate_hand(hand)
        self.assertIsNotNone(e2)
        self.assertEqual(e2.gesture, GestureType.OPEN_PALM)

    def test_point_recognition(self):
        engine = GestureEngine(debounce_frames=2, cooldown_seconds=0.1, confidence_threshold=0.5)
        # Index extended, others folded (y tip > y pip)
        lms = self._create_mock_landmarks(thumb_tip_pos=(0.4, 0.6), index_tip_pos=(0.5, 0.2), other_extended=False)
        hand = HandObservation(hand_id=0, handedness="Right", confidence=0.9, landmarks=lms, bbox=(0, 0, 1, 1))

        engine.evaluate_hand(hand)
        e2 = engine.evaluate_hand(hand)
        self.assertIsNotNone(e2)
        self.assertEqual(e2.gesture, GestureType.POINT)

    def test_closed_fist_recognition(self):
        engine = GestureEngine(debounce_frames=2, cooldown_seconds=0.1, confidence_threshold=0.5)
        # All fingers curled
        lms = self._create_mock_landmarks(thumb_tip_pos=(0.5, 0.7), index_tip_pos=(0.5, 0.7), other_extended=False)
        lms[4] = NormalizedLandmark(x=0.5, y=0.7, z=0.0)
        hand = HandObservation(hand_id=0, handedness="Right", confidence=0.9, landmarks=lms, bbox=(0, 0, 1, 1))

        engine.evaluate_hand(hand)
        e2 = engine.evaluate_hand(hand)
        self.assertIsNotNone(e2)
        self.assertEqual(e2.gesture, GestureType.CLOSED_FIST)


class TestCameraManagerLifecycle(unittest.TestCase):
    def setUp(self):
        self.mgr = CameraManager()
        self.mgr.force_stop()

    def tearDown(self):
        self.mgr.force_stop()

    def test_acquire_and_release(self):
        ok = self.mgr.acquire("test_client_1")
        self.assertTrue(ok)
        self.assertTrue(self.mgr.is_active)
        self.assertEqual(self.mgr.get_state(), CameraState.ACTIVE)

        # Acquire second reference
        ok2 = self.mgr.acquire("test_client_2")
        self.assertTrue(ok2)
        self.assertEqual(self.mgr._holders, 2)

        # Release first reference - should still be active
        self.mgr.release("test_client_1")
        self.assertTrue(self.mgr.is_active)

        # Release second reference - should stop
        self.mgr.release("test_client_2")
        self.assertFalse(self.mgr.is_active)
        self.assertEqual(self.mgr.get_state(), CameraState.OFF)

    def test_device_discovery(self):
        cams = self.mgr.list_cameras()
        self.assertIsInstance(cams, list)
        self.assertGreaterEqual(len(cams), 1)

        default_cam = self.mgr.get_default_camera()
        self.assertIsNotNone(default_cam)
        self.assertTrue(self.mgr.is_available())

    def test_capture_snapshot(self):
        self.mgr.acquire("snapshot_test")
        time.sleep(0.05)
        success, path = self.mgr.capture_snapshot("screenshots/test_snap.png")
        self.assertTrue(success)
        self.assertIn("screenshots", path)
        self.mgr.release("snapshot_test")

    def test_status_report(self):
        status = self.mgr.get_status()
        self.assertIn("state", status)
        self.assertIn("is_active", status)
        self.assertIn("fps_capture", status)
        self.assertIn("fps_vision", status)


class TestIntentAndToolPerception(unittest.TestCase):
    def setUp(self):
        self.intent_engine = IntentEngine()

    def test_camera_layer1_intents(self):
        commands = [
            ("turn on camera", "turn_on_camera"),
            ("start vision", "turn_on_camera"),
            ("enable webcam", "turn_on_camera"),
            ("turn off camera", "turn_off_camera"),
            ("stop vision", "turn_off_camera"),
            ("disable camera", "turn_off_camera"),
            ("start hand tracking", "start_hand_tracking"),
            ("stop hand tracking", "stop_hand_tracking"),
            ("take a photo", "camera_snapshot"),
            ("capture camera frame", "camera_snapshot"),
        ]
        for phrase, expected_intent in commands:
            res = self.intent_engine.parse(phrase)
            self.assertIsNotNone(res, f"Failed to match phrase: '{phrase}'")
            self.assertEqual(res["intent"], expected_intent, f"Mismatch for phrase: '{phrase}' (got {res.get('intent')})")

    def test_tool_registry_camera_tools(self):
        registry = ToolRegistry()
        tools = registry.list_tools()
        names = [t["name"] for t in tools]
        self.assertIn("camera.list", names)
        self.assertIn("camera.start", names)
        self.assertIn("camera.stop", names)
        self.assertIn("camera.status", names)
        self.assertIn("camera.capture_frame", names)
        self.assertIn("vision.start", names)
        self.assertIn("vision.stop", names)
        self.assertIn("vision.status", names)
        self.assertIn("gesture.status", names)

        # Test tool execution
        res_list = registry.execute("camera.list")
        self.assertTrue(res_list["success"])

        res_start = registry.execute("camera.start")
        self.assertTrue(res_start["success"])

        res_status = registry.execute("camera.status")
        self.assertTrue(res_status["success"])

        res_snap = registry.execute("camera.capture_frame")
        self.assertTrue(res_snap["success"])

        res_vstatus = registry.execute("vision.status")
        self.assertTrue(res_vstatus["success"])

        res_gstatus = registry.execute("gesture.status")
        self.assertTrue(res_gstatus["success"])

        res_stop = registry.execute("camera.stop")
        self.assertTrue(res_stop["success"])


if __name__ == "__main__":
    unittest.main()


