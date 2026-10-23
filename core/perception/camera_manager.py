"""
Central Camera & Perception Manager for Jarvis.
Manages refcounted camera hardware ownership, frame ingestion background thread,
vision processing worker, and gesture event dispatching.
"""

import os
import time
import logging
import threading
from typing import Optional, List, Dict, Any, Callable, Tuple
import numpy as np
from core.lazy_loader import lazy_import

Image = lazy_import("PIL.Image")

from core.perception.vision_config import vision_config, VisionConfig
from core.perception.perception_events import (
    CameraState, CameraStateEvent, GestureEvent, HandObservation, CameraDeviceInfo
)
from core.perception.camera_device import CameraDevice, create_camera_device
from core.perception.frame_pipeline import RollingFrameBuffer
from core.perception.hand_tracker import HandTracker
from core.perception.gesture_engine import GestureEngine

logger = logging.getLogger("Jarvis.CameraManager")


class CameraManager:
    """Refcounted Singleton Camera & Perception Coordinator."""

    _instance = None
    _singleton_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._singleton_lock:
            if cls._instance is None:
                cls._instance = super(CameraManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, config: Optional[VisionConfig] = None):
        if self._initialized:
            return

        self.config = config or vision_config
        self.device: CameraDevice = create_camera_device(prefer_cv2=True)
        self.buffer = RollingFrameBuffer(
            max_seconds=self.config.buffer_seconds,
            fps=self.config.vision_fps
        )
        self.hand_tracker = HandTracker()
        self.gesture_engine = GestureEngine(
            debounce_frames=self.config.gesture_debounce_frames,
            confidence_threshold=self.config.gesture_confidence_threshold,
            cooldown_seconds=self.config.gesture_cooldown_seconds
        )

        self._lock = threading.Lock()
        self._holders = 0
        self._state = CameraState.OFF
        self._running = False
        self._selected_camera_index = self.config.default_camera_index

        # Background Threads
        self._camera_thread: Optional[threading.Thread] = None
        self._vision_thread: Optional[threading.Thread] = None

        # Callbacks
        self.on_gesture_cb: Optional[Callable[[GestureEvent], None]] = None
        self.on_state_change_cb: Optional[Callable[[CameraStateEvent], None]] = None
        self.on_frame_cb: Optional[Callable[[np.ndarray], None]] = None

        self._actual_fps = 0.0
        self._vision_fps = 0.0
        self._detected_hands_count = 0
        self._initialized = True
        logger.info("CameraManager perception subsystem initialized in OFF state.")

    @property
    def state(self) -> CameraState:
        return self._state

    @property
    def is_active(self) -> bool:
        return self._state == CameraState.ACTIVE and self._running

    def is_running(self) -> bool:
        return self.is_active

    def is_available(self) -> bool:
        """Checks if a valid camera device is available on the system."""
        devices = self.list_cameras()
        return any(d.get("available", False) for d in devices)

    def list_cameras(self) -> List[Dict[str, Any]]:
        """Discovers and returns all available camera hardware devices."""
        device_infos = self.device.list_devices(max_check=4)
        return [
            {
                "index": d.index,
                "name": d.name,
                "backend": d.backend,
                "is_default": (d.index == self._selected_camera_index),
                "available": d.available,
                "resolution": f"{d.width}x{d.height}",
                "fps": d.fps
            }
            for d in device_infos
        ]

    def get_default_camera(self) -> Dict[str, Any]:
        """Returns metadata for the currently configured default camera."""
        cams = self.list_cameras()
        for c in cams:
            if c.get("is_default"):
                return c
        return cams[0] if cams else {"index": 0, "name": "Default Camera", "available": True}

    def open(self, camera_id: int = 0) -> bool:
        """Sets the active camera index and initiates stream ingestion."""
        self._selected_camera_index = camera_id
        return self.acquire(reason=f"camera_open_{camera_id}")

    def start(self) -> bool:
        """Direct start alias acquiring a hold."""
        return self.acquire(reason="manual_start")

    def stop(self) -> bool:
        """Direct stop alias releasing a hold."""
        return self.release(reason="manual_stop")

    def acquire(self, reason: str = "general") -> bool:
        """Takes a hold on the camera stream. Starts background workers if first holder."""
        with self._lock:
            self._holders += 1
            logger.info(f"Camera hold acquired by '{reason}'. Total active holders: {self._holders}")
            if self._holders == 1 and not self._running:
                return self._start_capture()
            return True

    def release(self, reason: str = "general") -> bool:
        """Releases a hold on the camera stream. Shuts down device when holders reach 0."""
        with self._lock:
            if self._holders > 0:
                self._holders -= 1
            logger.info(f"Camera hold released by '{reason}'. Remaining holders: {self._holders}")
            if self._holders == 0 and self._running:
                self._stop_capture()
            return True

    def force_stop(self):
        """Immediately halts all camera capture and vision threads regardless of holder count."""
        with self._lock:
            self._holders = 0
            if self._running:
                self._stop_capture()

    def get_frame(self) -> Tuple[Optional[np.ndarray], float]:
        """Returns the newest RGB frame and timestamp from the buffer."""
        return self.buffer.get_latest()

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Convenience method returning only the numpy RGB frame."""
        frame, _ = self.buffer.get_latest()
        return frame

    def _start_capture(self) -> bool:
        """Opens camera hardware and starts worker threads."""
        self._set_state(CameraState.STARTING, "Initializing camera stream")
        success = self.device.open(
            device_index=self._selected_camera_index,
            width=self.config.capture_width,
            height=self.config.capture_height,
            fps=self.config.capture_fps
        )

        if not success:
            logger.warning(f"Failed to open camera hardware on index {self._selected_camera_index}. Attempting Mock fallback.")
            from core.perception.camera_device import MockCameraDevice
            if not isinstance(self.device, MockCameraDevice):
                self.device = MockCameraDevice()
                success = self.device.open(
                    device_index=self._selected_camera_index,
                    width=self.config.capture_width,
                    height=self.config.capture_height,
                    fps=self.config.capture_fps
                )

        if not success:
            logger.error(f"Failed to open camera hardware on index {self._selected_camera_index}.")
            self._set_state(CameraState.UNAVAILABLE, "Camera hardware unavailable")
            return False

        self._running = True
        self._set_state(CameraState.ACTIVE, "Camera stream online")

        # 1. Camera Capture Worker (Ingestion @ 30 FPS)
        self._camera_thread = threading.Thread(
            target=self._camera_worker_loop,
            name="CameraCaptureWorker",
            daemon=True
        )
        self._camera_thread.start()

        # 2. Vision / Gesture Processing Worker (Processing @ 12-15 FPS)
        if self.config.hand_tracking_enabled:
            self._vision_thread = threading.Thread(
                target=self._vision_worker_loop,
                name="VisionGestureWorker",
                daemon=True
            )
            self._vision_thread.start()

        logger.info("[CAMERA_ONLINE] Video ingestion (30 FPS) and vision workers started.")
        return True

    def _stop_capture(self):
        """Stops background workers and releases camera hardware."""
        self._set_state(CameraState.STOPPING, "Releasing camera hardware")
        self._running = False

        if self._camera_thread and self._camera_thread.is_alive():
            self._camera_thread.join(timeout=1.0)
        if self._vision_thread and self._vision_thread.is_alive():
            self._vision_thread.join(timeout=1.0)

        self.device.release()
        self.buffer.clear()
        self._actual_fps = 0.0
        self._vision_fps = 0.0
        self._detected_hands_count = 0
        self._set_state(CameraState.OFF, "Camera offline")
        logger.info("[CAMERA_OFFLINE] Camera hardware released cleanly.")

    def _camera_worker_loop(self):
        """High-frequency camera frame ingestion loop (30 FPS)."""
        interval = 1.0 / max(1, self.config.capture_fps)
        frame_counter = 0
        t_start = time.time()

        while self._running:
            t0 = time.time()
            success, frame = self.device.read_frame()
            if success and frame is not None:
                self.buffer.push(frame)
                frame_counter += 1

                if self.on_frame_cb:
                    try:
                        self.on_frame_cb(frame)
                    except Exception as e:
                        logger.debug(f"Error in on_frame_cb: {e}")

            # FPS calculation
            now = time.time()
            if now - t_start >= 1.0:
                self._actual_fps = frame_counter / (now - t_start)
                frame_counter = 0
                t_start = now

            elapsed = time.time() - t0
            sleep_dur = max(0.001, interval - elapsed)
            time.sleep(sleep_dur)

    def _vision_worker_loop(self):
        """Vision & Hand Gesture processing loop (12-15 FPS, drops stale frames)."""
        interval = 1.0 / max(1, self.config.vision_fps)
        vision_counter = 0
        t_start = time.time()

        while self._running:
            t0 = time.time()
            frame, _ = self.buffer.get_latest()
            if frame is not None:
                vision_counter += 1
                observations = self.hand_tracker.process_frame(frame)
                self._detected_hands_count = len(observations)
                for obs in observations:
                    gesture_event = self.gesture_engine.evaluate_hand(obs)
                    if gesture_event and self.on_gesture_cb:
                        try:
                            self.on_gesture_cb(gesture_event)
                        except Exception as e:
                            logger.error(f"Error in on_gesture_cb: {e}")
            else:
                self._detected_hands_count = 0

            now = time.time()
            if now - t_start >= 1.0:
                self._vision_fps = vision_counter / (now - t_start)
                vision_counter = 0
                t_start = now

            elapsed = time.time() - t0
            sleep_dur = max(0.002, interval - elapsed)
            time.sleep(sleep_dur)

    def capture_snapshot(self, output_path: str = "screenshots/camera_snap.png") -> Tuple[bool, str]:
        """Captures a photo from the live camera stream and saves to disk."""
        was_active = self.is_active
        if not was_active:
            ok = self.acquire(reason="snapshot")
            if not ok:
                return False, "Failed to initialize camera for snapshot."

        frame, _ = self.buffer.get_latest()
        if frame is None:
            # Wait briefly for worker ingestion
            for _ in range(10):
                time.sleep(0.05)
                frame, _ = self.buffer.get_latest()
                if frame is not None:
                    break

        if frame is None and self.device.is_opened():
            ret, direct_frame = self.device.read_frame()
            if ret and direct_frame is not None:
                frame = direct_frame

        if not was_active:
            self.release(reason="snapshot")

        if frame is None:
            return False, "Failed to capture camera frame."

        try:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            img = Image.fromarray(frame)
            img.save(output_path)
            logger.info(f"[SNAPSHOT_SAVED] Photo captured to {output_path}")
            return True, output_path
        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")
            return False, str(e)

    def get_status(self) -> Dict[str, Any]:
        """Returns structured status telemetry."""
        return {
            "state": self._state.value,
            "is_active": self.is_active,
            "is_running": self.is_running(),
            "holders": self._holders,
            "selected_device_index": self._selected_camera_index,
            "fps_capture": round(self._actual_fps, 1),
            "fps_vision": round(self._vision_fps, 1),
            "hands_detected": self._detected_hands_count,
            "device": self.device.get_device_info()
        }

    def get_state(self) -> CameraState:
        return self._state

    def _set_state(self, new_state: CameraState, message: str = ""):
        self._state = new_state
        if self.on_state_change_cb:
            info = self.device.get_device_info()
            event = CameraStateEvent(
                state=new_state,
                device_index=self._selected_camera_index,
                device_name=info.get("name", "Camera"),
                fps_capture=self._actual_fps,
                fps_vision=self._vision_fps,
                message=message
            )
            try:
                self.on_state_change_cb(event)
            except Exception as e:
                logger.debug(f"Error in on_state_change_cb: {e}")


camera_manager = CameraManager()

def get_camera_manager(config: Optional[VisionConfig] = None) -> CameraManager:
    """Returns the singleton CameraManager instance."""
    return CameraManager(config=config)


