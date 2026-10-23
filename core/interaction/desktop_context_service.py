"""Central Desktop Context Service for Universal Application Awareness."""

import sys
import logging
from typing import Optional, Callable, Dict, Any

from core.interaction.models import DesktopContext
from core.interaction.context_adapter import (
    BaseDesktopContextAdapter,
    WindowsDesktopContextAdapter,
    LinuxDesktopContextAdapter
)

logger = logging.getLogger("Jarvis.DesktopContextService")


class DesktopContextService:
    """Universal service for detecting active desktop application, window title, focused elements, and input controls."""

    def __init__(self, adapter: Optional[BaseDesktopContextAdapter] = None):
        if adapter:
            self.adapter = adapter
        else:
            if sys.platform.startswith("win"):
                self.adapter = WindowsDesktopContextAdapter()
            else:
                self.adapter = LinuxDesktopContextAdapter()

        self._last_context: Optional[DesktopContext] = None
        self.on_screen_reading_indicator: Optional[Callable[[bool, str], None]] = None

    def get_current_context(
        self,
        explicit_destination: Optional[str] = None,
        allow_ocr: bool = False
    ) -> DesktopContext:
        """Captures active foreground application, window title, and accessible input fields."""
        if allow_ocr and self.on_screen_reading_indicator:
            try:
                self.on_screen_reading_indicator(True, "Reading screen context...")
            except Exception as e:
                logger.debug(f"Indicator callback error: {e}")

        try:
            ctx = self.adapter.get_desktop_context(
                explicit_destination=explicit_destination,
                allow_ocr=allow_ocr
            )
            self._last_context = ctx
            return ctx
        finally:
            if allow_ocr and self.on_screen_reading_indicator:
                try:
                    self.on_screen_reading_indicator(False, "")
                except Exception:
                    pass

    def get_last_context(self) -> Optional[DesktopContext]:
        """Returns the most recent captured desktop context."""
        return self._last_context

    def verify_window_stable(self, expected_hwnd: int, expected_title: str = "") -> bool:
        """Verifies foreground window has not changed unexpectedly."""
        return self.adapter.verify_window_stable(expected_hwnd, expected_title)


# Global singleton instance
desktop_context_service = DesktopContextService()
