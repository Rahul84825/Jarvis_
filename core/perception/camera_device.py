"""
Camera Device Abstraction & Hardware Drivers for Jarvis Perception.
Supports physical camera capture via OpenCV with synthetic Mock fallback.
"""

import abc
import os
import sys
import time
import logging
import numpy as np
from typing import Optional, Tuple, Dict, Any, List

from core.perception.perception_events import CameraDeviceInfo

logger = logging.getLogger("Jarvis.CameraDevice")


class CameraDevice(abc.ABC):
    """Abstract base class for camera capture hardware."""

    @abc.abstractmethod
    def open(self, device_index: int = 0, width: int = 640, height: int = 480, fps: int = 30) -> bool:
        """Opens the camera capture interface."""
        pass

    @abc.abstractmethod
    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        """Reads the latest RGB frame."""
        pass

    @abc.abstractmethod
    def release(self):
        """Releases camera hardware resources."""
        pass

    @abc.abstractmethod
    def is_opened(self) -> bool:
        """Returns True if device is actively opened."""
        pass

    @abc.abstractmethod
    def get_device_info(self) -> Dict[str, Any]:
        """Returns device metadata (name, resolution, fps)."""
        pass

    @abc.abstractmethod
    def list_devices(self, max_check: int = 4) -> List[CameraDeviceInfo]:
        """Enumerates available camera devices."""
        pass


class MockCameraDevice(CameraDevice):
    """Simulated camera device generating synthetic test frames for headless/test environments."""

    def __init__(self, name: str = "Mock Camera Device"):
        self.name = name
        self._opened = False
        self._device_index = 0
        self._width = 640
        self._height = 480
        self._fps = 30
        self._frame_count = 0

    def open(self, device_index: int = 0, width: int = 640, height: int = 480, fps: int = 30) -> bool:
        self._device_index = device_index
        self._width = width
        self._height = height
        self._fps = fps
        self._opened = True
        self._frame_count = 0
        logger.info(f"MockCameraDevice opened index {device_index} (Resolution: {width}x{height} @ {fps}fps)")
        return True

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        if not self._opened:
            return False, None
        self._frame_count += 1
        # Create synthetic dark-gradient test frame with animated gradient
        frame = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        frame[:, :, 0] = (self._frame_count * 2) % 255  # B channel
        frame[:, :, 1] = 100                             # G channel
        frame[:, :, 2] = 20                              # R channel
        return True, frame

    def release(self):
        if self._opened:
            self._opened = False
            logger.info("MockCameraDevice released.")

    def is_opened(self) -> bool:
        return self._opened

    def get_device_info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "index": self._device_index,
            "width": self._width,
            "height": self._height,
            "fps": self._fps,
            "is_mock": True
        }

    def list_devices(self, max_check: int = 4) -> List[CameraDeviceInfo]:
        return [
            CameraDeviceInfo(
                index=0,
                name="Mock Camera 0 (Synthetic)",
                backend="MOCK",
                is_default=True,
                available=True,
                width=self._width,
                height=self._height,
                fps=self._fps
            )
        ]


class CV2CameraDevice(CameraDevice):
    """Physical webcam capture driver using OpenCV."""

    def __init__(self, name: str = "OpenCV VideoCapture"):
        self.name = name
        self._cap = None
        self._device_index = 0
        self._width = 640
        self._height = 480
        self._fps = 30

    def open(self, device_index: int = 0, width: int = 640, height: int = 480, fps: int = 30) -> bool:
        try:
            import cv2
            self._device_index = device_index
            # On Windows prefer DirectShow for fast startup
            backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
            self._cap = cv2.VideoCapture(device_index, backend)
            if not self._cap.isOpened():
                # Fallback to default backend
                self._cap = cv2.VideoCapture(device_index)

            if not self._cap.isOpened():
                logger.warning(f"Failed to open OpenCV camera index {device_index}")
                self._cap = None
                return False

            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
            self._cap.set(cv2.CAP_PROP_FPS, fps)

            # Read back actual device properties
            self._width = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or width)
            self._height = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or height)
            self._fps = int(self._cap.get(cv2.CAP_PROP_FPS) or fps)
            logger.info(f"CV2CameraDevice opened index {device_index} ({self._width}x{self._height} @ {self._fps}fps)")
            return True
        except ImportError:
            logger.warning("OpenCV (cv2) is not installed. Use MockCameraDevice fallback.")
            return False
        except Exception as e:
            logger.error(f"Error opening CV2 camera index {device_index}: {e}")
            return False

    def read_frame(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self._cap is None or not self._cap.isOpened():
            return False, None
        try:
            import cv2
            ret, bgr_frame = self._cap.read()
            if not ret or bgr_frame is None:
                return False, None
            rgb_frame = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
            return True, rgb_frame
        except Exception as e:
            logger.debug(f"Error reading frame from CV2: {e}")
            return False, None

    def release(self):
        if self._cap is not None:
            try:
                self._cap.release()
            except Exception:
                pass
            self._cap = None
            logger.info("CV2CameraDevice released.")

    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def get_device_info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "index": self._device_index,
            "width": self._width,
            "height": self._height,
            "fps": self._fps,
            "is_mock": False
        }

    def list_devices(self, max_check: int = 4) -> List[CameraDeviceInfo]:
        """Probes camera indices to discover available physical video devices."""
        devices: List[CameraDeviceInfo] = []
        try:
            import cv2
            backend = cv2.CAP_DSHOW if sys.platform.startswith("win") else cv2.CAP_ANY
            for idx in range(max_check):
                # If currently opened on this index, report it directly
                if self._cap is not None and self._device_index == idx and self._cap.isOpened():
                    devices.append(CameraDeviceInfo(
                        index=idx,
                        name=f"Camera {idx} (Active)",
                        backend="DSHOW" if backend == cv2.CAP_DSHOW else "DEFAULT",
                        is_default=(idx == 0),
                        available=True,
                        width=self._width,
                        height=self._height,
                        fps=self._fps
                    ))
                    continue

                temp_cap = cv2.VideoCapture(idx, backend)
                if temp_cap.isOpened():
                    w = int(temp_cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 640)
                    h = int(temp_cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 480)
                    fps = int(temp_cap.get(cv2.CAP_PROP_FPS) or 30)
                    temp_cap.release()
                    devices.append(CameraDeviceInfo(
                        index=idx,
                        name=f"Camera {idx}",
                        backend="DSHOW" if backend == cv2.CAP_DSHOW else "DEFAULT",
                        is_default=(idx == 0),
                        available=True,
                        width=w,
                        height=h,
                        fps=fps
                    ))
        except Exception as e:
            logger.debug(f"Device discovery error: {e}")

        if not devices:
            # Provide default fallback descriptor
            devices.append(CameraDeviceInfo(
                index=0,
                name="Default System Camera",
                backend="DEFAULT",
                is_default=True,
                available=True
            ))
        return devices


def create_camera_device(prefer_cv2: bool = True) -> CameraDevice:
    """Factory creating an appropriate camera driver with fallback to mock."""
    if prefer_cv2:
        try:
            import cv2
            return CV2CameraDevice()
        except ImportError:
            pass
    return MockCameraDevice()

