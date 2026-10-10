"""
Thread-safe In-Memory Rolling Frame Buffer & Pipeline for Jarvis Perception.
Maintains a rolling ring buffer of recent frames in RAM (never touching disk),
supporting instantaneous snapshot retrieval and multi-frame contact sheet synthesis.
"""

import time
import threading
from collections import deque
from typing import Optional, List, Tuple
import numpy as np

class RollingFrameBuffer:
    """In-memory rolling ring buffer of timestamped camera frames."""

    def __init__(self, max_seconds: float = 10.0, fps: int = 10):
        self.max_seconds = max_seconds
        self.fps = fps
        self.max_frames = int(max_seconds * fps)
        self._buffer = deque(maxlen=self.max_frames)
        self._lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_timestamp: float = 0.0

    def push(self, frame: np.ndarray, timestamp: Optional[float] = None):
        """Pushes a new frame into the rolling buffer."""
        ts = timestamp or time.time()
        with self._lock:
            self._latest_frame = frame.copy()
            self._latest_timestamp = ts
            self._buffer.append((ts, self._latest_frame))

    def get_latest(self) -> Tuple[Optional[np.ndarray], float]:
        """Returns the most recent frame and timestamp."""
        with self._lock:
            if self._latest_frame is None:
                return None, 0.0
            return self._latest_frame.copy(), self._latest_timestamp

    def get_recent_frames(self, duration_seconds: float = 5.0) -> List[Tuple[float, np.ndarray]]:
        """Returns all frames within the past `duration_seconds`."""
        now = time.time()
        cutoff = now - duration_seconds
        with self._lock:
            return [(ts, f) for (ts, f) in self._buffer if ts >= cutoff]

    def clear(self):
        """Clears all frames from the buffer."""
        with self._lock:
            self._buffer.clear()
            self._latest_frame = None
            self._latest_timestamp = 0.0

    def get_contact_sheet(self, grid_size: Tuple[int, int] = (3, 3)) -> Optional[np.ndarray]:
        """Synthesizes an NxM contact sheet grid from sampled rolling frames."""
        with self._lock:
            if not self._buffer:
                return None

            frames = [f for (_, f) in self._buffer]
            total_cells = grid_size[0] * grid_size[1]
            if not frames:
                return None

            indices = np.linspace(0, len(frames) - 1, total_cells, dtype=int)
            sampled = [frames[i] for i in indices]

            # Assume uniform frame dimensions
            h, w, c = sampled[0].shape
            rows, cols = grid_size
            sheet = np.zeros((rows * h, cols * w, c), dtype=np.uint8)

            for idx, img in enumerate(sampled):
                r = idx // cols
                col = idx % cols
                sheet[r * h:(r + 1) * h, col * w:(col + 1) * w] = img

            return sheet
