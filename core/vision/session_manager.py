"""Bounded Screen Analysis Session Manager for JARVIS.

Maintains multi-turn context for teaching, follow-up explanations,
screen change detection, and point references across conversational turns.
"""

import time
import uuid
import logging
from typing import Optional, Dict, Any, List

from core.vision.models import ScreenContext, ScreenExplanation, ExplanationStyle

logger = logging.getLogger("Jarvis.ScreenSession")


class ScreenSession:
    """Represents an active multi-turn screen analysis conversation."""

    def __init__(self, context: ScreenContext):
        self.session_id: str = uuid.uuid4().hex[:8]
        self.created_at: float = time.time()
        self.updated_at: float = time.time()
        self.context: ScreenContext = context
        self.initial_analysis: Dict[str, Any] = {}
        self.extracted_points: List[str] = []
        self.explanations: List[ScreenExplanation] = []
        self.follow_up_turns: List[Dict[str, str]] = []  # [{"role": "user"|"jarvis", "text": "..."}]
        self.current_point_index: Optional[int] = None
        self.preferred_style: ExplanationStyle = ExplanationStyle.SUMMARY_THEN_DETAIL

    def add_explanation(self, explanation: ScreenExplanation):
        self.explanations.append(explanation)
        self.updated_at = time.time()

    def add_turn(self, role: str, text: str):
        self.follow_up_turns.append({"role": role, "text": text, "timestamp": time.time()})
        self.updated_at = time.time()

    def get_point(self, index: int) -> Optional[str]:
        """Returns 1-based indexed point from extracted points."""
        if 1 <= index <= len(self.extracted_points):
            return self.extracted_points[index - 1]
        return None

    def has_screen_changed(self, current_hwnd: int, current_title: str) -> bool:
        """Compares current desktop state with session initial capture."""
        initial_hwnd = getattr(self.context, "metadata", {}).get("hwnd")
        initial_title = self.context.window_title
        if initial_hwnd and current_hwnd and initial_hwnd != current_hwnd:
            return True
        if initial_title and current_title and initial_title.strip() != current_title.strip():
            return True
        return False


class ScreenSessionManager:
    """Manages active screen sessions and ensures bounded conversational memory."""

    def __init__(self, max_idle_seconds: float = 1800.0):
        self._active_session: Optional[ScreenSession] = None
        self._session_history: Dict[str, ScreenSession] = {}
        self.max_idle_seconds = max_idle_seconds

    def create_session(self, context: ScreenContext) -> ScreenSession:
        """Starts a new screen understanding session."""
        session = ScreenSession(context)
        self._active_session = session
        self._session_history[session.session_id] = session
        logger.info(f"[SESSION] Created new screen session '{session.session_id}' for '{context.window_title}'")
        return session

    def get_active_session(self) -> Optional[ScreenSession]:
        """Returns the current active screen session if within idle threshold."""
        if not self._active_session:
            return None
        if time.time() - self._active_session.updated_at > self.max_idle_seconds:
            logger.info(f"[SESSION] Active session '{self._active_session.session_id}' expired due to idle timeout.")
            self._active_session = None
            return None
        return self._active_session

    def end_session(self):
        """Terminates the active screen session."""
        if self._active_session:
            logger.info(f"[SESSION] Ending screen session '{self._active_session.session_id}'.")
            self._active_session = None


# Global singleton instance
screen_session_manager = ScreenSessionManager()
