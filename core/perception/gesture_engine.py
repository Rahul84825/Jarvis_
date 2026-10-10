"""
Gesture Recognition & Temporal Stabilization Engine for Jarvis.
Classifies hand landmarks into stable gestures (PINCH, POINT, OPEN_PALM, CLOSED_FIST, THUMBS_UP)
with hysteresis, debouncing, and confidence smoothing to eliminate false positives.
"""

import math
import time
import logging
from typing import Optional, List, Tuple

from core.perception.perception_events import (
    HandObservation, GestureType, GestureEvent, NormalizedLandmark
)
from core.perception.vision_config import vision_config

logger = logging.getLogger("Jarvis.GestureEngine")

def _dist(p1: NormalizedLandmark, p2: NormalizedLandmark) -> float:
    return math.sqrt((p1.x - p2.x)**2 + (p1.y - p2.y)**2 + (p1.z - p2.z)**2)

class GestureEngine:
    """Classifies hand landmark geometries into debounced, stable gesture events."""

    def __init__(
        self,
        debounce_frames: int = 3,
        confidence_threshold: float = 0.75,
        cooldown_seconds: float = 0.5
    ):
        self.debounce_frames = debounce_frames
        self.confidence_threshold = confidence_threshold
        self.cooldown_seconds = cooldown_seconds

        # State tracking per hand ("Right", "Left")
        self._candidate_gesture = GestureType.NONE
        self._consecutive_frames = 0
        self._last_emitted_gesture = GestureType.NONE
        self._last_event_time = 0.0

    def evaluate_hand(self, observation: HandObservation) -> Optional[GestureEvent]:
        """Evaluates a single hand observation and returns confirmed GestureEvent if stabilized."""
        if not observation or len(observation.landmarks) < 21:
            return None

        lm = observation.landmarks
        raw_gesture, confidence = self._classify_landmarks(lm)
        now = time.time()

        # Check candidate stabilization
        if raw_gesture != GestureType.NONE and confidence >= self.confidence_threshold:
            if raw_gesture == self._candidate_gesture:
                self._consecutive_frames += 1
            else:
                self._candidate_gesture = raw_gesture
                self._consecutive_frames = 1

            if self._consecutive_frames >= self.debounce_frames:
                # Check cooldown to prevent duplicate event floods
                if (now - self._last_event_time > self.cooldown_seconds) or (raw_gesture != self._last_emitted_gesture):
                    self._last_emitted_gesture = raw_gesture
                    self._last_event_time = now

                    # Compute pointer location from index tip
                    pointer_pos = (lm[8].x, lm[8].y)

                    event = GestureEvent(
                        gesture=raw_gesture,
                        confidence=confidence,
                        hand=observation.handedness,
                        pointer_pos=pointer_pos,
                        timestamp=now
                    )
                    logger.info(f"[GESTURE_CONFIRMED] {raw_gesture.value} ({observation.handedness} hand, conf={confidence:.2f})")
                    return event
        else:
            self._consecutive_frames = 0
            self._candidate_gesture = GestureType.NONE

        return None

    def _classify_landmarks(self, lm: List[NormalizedLandmark]) -> Tuple[GestureType, float]:
        """Geometric classification of 21 landmarks."""
        wrist = lm[0]
        thumb_tip = lm[4]
        index_tip = lm[8]
        index_pip = lm[6]
        middle_tip = lm[12]
        middle_pip = lm[10]
        ring_tip = lm[16]
        ring_pip = lm[14]
        pinky_tip = lm[20]
        pinky_pip = lm[18]

        # Check extended state of fingers (Tip further from wrist than PIP)
        index_extended = _dist(index_tip, wrist) > _dist(index_pip, wrist) * 1.15
        middle_extended = _dist(middle_tip, wrist) > _dist(middle_pip, wrist) * 1.15
        ring_extended = _dist(ring_tip, wrist) > _dist(ring_pip, wrist) * 1.15
        pinky_extended = _dist(pinky_tip, wrist) > _dist(pinky_pip, wrist) * 1.15
        thumb_extended = _dist(thumb_tip, wrist) > _dist(lm[2], wrist) * 1.15

        extended_count = sum([index_extended, middle_extended, ring_extended, pinky_extended])

        # 1. PINCH: Thumb tip and Index tip touching (while other fingers or index extended)
        pinch_dist = _dist(thumb_tip, index_tip)
        if pinch_dist < 0.065 and (extended_count > 0 or index_extended):
            conf = max(0.5, min(1.0, 1.0 - (pinch_dist / 0.065) * 0.5))
            return GestureType.PINCH, conf

        # 2. POINT: Index extended while others are curled
        if index_extended and not middle_extended and not ring_extended and not pinky_extended:
            return GestureType.POINT, 0.88

        # 3. OPEN PALM: All 4 fingers extended
        if extended_count >= 4 and thumb_extended:
            return GestureType.OPEN_PALM, 0.92

        # 4. THUMBS UP: Thumb pointing upward (lower Y in normalized coords) with all other fingers curled
        if thumb_tip.y < wrist.y - 0.15 and extended_count == 0:
            return GestureType.THUMBS_UP, 0.90

        # 5. CLOSED FIST: All 4 fingers curled
        if extended_count == 0:
            return GestureType.CLOSED_FIST, 0.86

        return GestureType.NONE, 0.0

