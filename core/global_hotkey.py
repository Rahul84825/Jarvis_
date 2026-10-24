"""Global Keyboard Shortcut Manager for Santra on Windows.

Provides system-wide keyboard shortcut registration via Windows Win32 API
RegisterHotKey / UnregisterHotKey without busy polling loops.
Default shortcut: Ctrl+Shift+Space (no conflict with existing in-app shortcuts).
"""

import sys
import logging
import threading
from typing import Optional, Callable

logger = logging.getLogger("Jarvis.GlobalHotkey")

IS_WINDOWS = sys.platform == "win32"

# Win32 Hotkey Modifiers
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

# Virtual Key Codes
VK_SPACE = 0x20
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

DEFAULT_HOTKEY_ID = 0x5341  # 'SA' (Santra Assistant)


class GlobalHotkeyManager:
    """Manages system-wide global hotkey registration for Santra.
    Supports event-driven Windows thread message loop (zero CPU polling)
    without requiring PyQt6 nativeEvent or early HWND creation.
    """

    def __init__(
        self,
        hotkey_id: int = DEFAULT_HOTKEY_ID,
        modifiers: int = MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT,
        vk_code: int = VK_SPACE,
        name: str = "Ctrl+Shift+Space"
    ):
        self.hotkey_id = hotkey_id
        self.modifiers = modifiers
        self.vk_code = vk_code
        self.name = name
        self.is_registered = False
        self._hwnd: Optional[int] = None
        self._callback: Optional[Callable[[], None]] = None
        self._thread: Optional[threading.Thread] = None
        self._thread_id: Optional[int] = None
        self._stop_event = threading.Event()

    def register(self, hwnd: Optional[int] = None, on_trigger: Optional[Callable[[], None]] = None) -> bool:
        """Registers the global hotkey with Windows.
        If hwnd is provided, registers with the specified HWND.
        If hwnd is None, registers on a dedicated background thread message queue.
        """
        if not IS_WINDOWS:
            logger.debug("GlobalHotkeyManager: Not Windows. Hotkey registration skipped.")
            return False

        if self.is_registered:
            self.unregister()

        self._hwnd = hwnd
        self._callback = on_trigger

        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            # Case A: Explicit HWND provided (e.g. in existing unit tests)
            if hwnd is not None:
                res = user32.RegisterHotKey(
                    ctypes.c_void_p(hwnd) if hwnd else None,
                    ctypes.c_int(self.hotkey_id),
                    ctypes.c_uint(self.modifiers),
                    ctypes.c_uint(self.vk_code)
                )
                if res:
                    self.is_registered = True
                    logger.info(f"Registered global hotkey '{self.name}' on HWND {hwnd} (ID: {hex(self.hotkey_id)}).")
                    return True
                else:
                    last_err = ctypes.GetLastError()
                    logger.warning(
                        f"Failed to register global hotkey '{self.name}' on HWND {hwnd} (WinError: {last_err}). "
                        "The shortcut may be in use by another application."
                    )
                    self.is_registered = False
                    return False

            # Case B: No HWND provided - Run dedicated Win32 thread message pump
            ready_event = threading.Event()
            registration_result = [False]

            def _pump_loop():
                self._thread_id = kernel32.GetCurrentThreadId()
                res = user32.RegisterHotKey(
                    None,
                    ctypes.c_int(self.hotkey_id),
                    ctypes.c_uint(self.modifiers),
                    ctypes.c_uint(self.vk_code)
                )
                if res:
                    registration_result[0] = True
                    logger.info(f"Registered thread-pumped global hotkey '{self.name}' (ID: {hex(self.hotkey_id)}).")
                else:
                    last_err = ctypes.GetLastError()
                    logger.warning(f"Failed to register thread-pumped global hotkey '{self.name}' (WinError: {last_err}).")

                ready_event.set()
                if not res:
                    return

                msg = wintypes.MSG()
                while not self._stop_event.is_set():
                    # GetMessageW blocks until a message arrives (zero CPU usage)
                    msg_res = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                    if msg_res <= 0:
                        break
                    if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
                        self.trigger()

                user32.UnregisterHotKey(None, ctypes.c_int(self.hotkey_id))
                logger.debug(f"Thread-pump loop exited for hotkey '{self.name}'.")

            self._stop_event.clear()
            self._thread = threading.Thread(target=_pump_loop, name="GlobalHotkeyPumpThread", daemon=True)
            self._thread.start()
            ready_event.wait(timeout=2.0)

            self.is_registered = registration_result[0]
            return self.is_registered

        except Exception as e:
            logger.error(f"Error registering global hotkey '{self.name}': {e}", exc_info=True)
            self.is_registered = False
            return False

    def unregister(self) -> bool:
        """Unregisters the global hotkey cleanly from Windows."""
        if not IS_WINDOWS or not self.is_registered:
            return True

        try:
            import ctypes
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            if self._hwnd is not None:
                res = user32.UnregisterHotKey(
                    ctypes.c_void_p(self._hwnd) if self._hwnd else None,
                    ctypes.c_int(self.hotkey_id)
                )
                self.is_registered = False
                logger.info(f"Unregistered global hotkey '{self.name}'.")
                return bool(res)

            # Signal thread pump to exit
            self._stop_event.set()
            if self._thread_id:
                user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=1.0)
            self._thread = None
            self._thread_id = None
            self.is_registered = False
            logger.info(f"Unregistered thread-pumped global hotkey '{self.name}'.")
            return True

        except Exception as e:
            logger.error(f"Error unregistering global hotkey '{self.name}': {e}")
            self.is_registered = False
            return False

    def trigger(self):
        """Dispatches the hotkey callback if registered."""
        if self._callback:
            try:
                self._callback()
            except Exception as e:
                logger.error(f"Error executing global hotkey callback: {e}", exc_info=True)

