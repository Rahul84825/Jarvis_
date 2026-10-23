"""
Single Instance Application Guard for JARVIS.
Ensures only one instance of JARVIS runs on the system at any time,
preventing duplicate audio device bindings, conflicting wake-word streams,
and multiple TTS speech collisions.
"""

import os
import sys
import socket
import logging
from typing import Optional, Callable

logger = logging.getLogger("Jarvis.SingleInstance")

DEFAULT_MUTEX_NAME = "Global\\JARVIS_DESKTOP_SINGLETON_MUTEX"
DEFAULT_IPC_PORT = 49174  # High ephemeral localhost port for single-instance IPC

class SingleInstanceGuard:
    """Manages system-level mutex and local IPC to prevent duplicate instances.
    If a secondary instance is launched, it notifies the primary instance to restore
    its dashboard and exits immediately without touching audio hardware.
    """

    def __init__(self, mutex_name: str = DEFAULT_MUTEX_NAME, ipc_port: int = DEFAULT_IPC_PORT):
        self.mutex_name = mutex_name
        self.ipc_port = ipc_port
        self.mutex_handle = None
        self.is_primary = False
        self._ipc_server = None
        self._on_activate_cb: Optional[Callable[[], None]] = None

    def acquire(self) -> bool:
        """Attempts to acquire the single-instance lock.
        Returns:
            True if this process is the primary and only instance.
            False if another instance is already running.
        """
        if sys.platform == "win32":
            try:
                import ctypes
                from ctypes import wintypes
                
                ERROR_ALREADY_EXISTS = 183
                kernel32 = ctypes.windll.kernel32
                
                # Create or open named mutex
                handle = kernel32.CreateMutexW(None, False, self.mutex_name)
                last_error = kernel32.GetLastError()
                
                if last_error == ERROR_ALREADY_EXISTS:
                    logger.warning(f"Another JARVIS instance is already running (Mutex '{self.mutex_name}' exists).")
                    if handle:
                        kernel32.CloseHandle(handle)
                    self.is_primary = False
                    return False
                
                self.mutex_handle = handle
                self.is_primary = True
                logger.info(f"Acquired single-instance mutex: '{self.mutex_name}'.")
                return True
            except Exception as e:
                logger.error(f"Error checking Windows named mutex: {e}. Falling back to socket guard.")

        # Fallback / Non-Windows: Bind to a localhost socket
        try:
            self._ipc_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._ipc_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._ipc_server.bind(("127.0.0.1", self.ipc_port))
            self._ipc_server.listen(1)
            self.is_primary = True
            logger.info(f"Acquired single-instance socket lock on 127.0.0.1:{self.ipc_port}.")
            return True
        except (socket.error, OSError) as se:
            logger.warning(f"Port {self.ipc_port} is already bound by another instance: {se}")
            self.is_primary = False
            return False

    def notify_existing(self, message: str = "RESTORE_HUD") -> bool:
        """Sends an activation notification to the existing primary instance."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                client.settimeout(1.5)
                client.connect(("127.0.0.1", self.ipc_port))
                client.sendall(message.encode("utf-8"))
                logger.info(f"Notified existing JARVIS instance with message '{message}'.")
                return True
        except Exception as e:
            logger.debug(f"Could not reach existing JARVIS IPC server: {e}")
            return False

    def start_ipc_server(self, on_activate: Callable[[], None]):
        """Starts a background thread to listen for notifications from secondary instances."""
        if not self.is_primary:
            return

        self._on_activate_cb = on_activate

        import threading

        def _server_loop():
            # If socket was not opened during acquire, open it now
            if self._ipc_server is None:
                try:
                    self._ipc_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    self._ipc_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    self._ipc_server.bind(("127.0.0.1", self.ipc_port))
                    self._ipc_server.listen(2)
                except Exception as e:
                    logger.warning(f"Could not bind single-instance IPC listener on port {self.ipc_port}: {e}")
                    return

            logger.info(f"Single-instance IPC server listening on 127.0.0.1:{self.ipc_port}...")
            while self.is_primary:
                try:
                    self._ipc_server.settimeout(2.0)
                    client, _ = self._ipc_server.accept()
                    with client:
                        data = client.recv(1024).decode("utf-8").strip()
                        logger.info(f"[SINGLE_INSTANCE_IPC] Received signal from secondary launch: '{data}'")
                        if self._on_activate_cb:
                            try:
                                self._on_activate_cb()
                            except Exception as cb_err:
                                logger.error(f"Error in on_activate callback: {cb_err}")
                except socket.timeout:
                    continue
                except Exception as err:
                    if self.is_primary:
                        logger.debug(f"IPC listener error: {err}")
                    break

        thread = threading.Thread(target=_server_loop, name="SingleInstanceIPCThread", daemon=True)
        thread.start()

    def release(self):
        """Releases all locks and closes IPC sockets upon application shutdown."""
        self.is_primary = False
        if sys.platform == "win32" and self.mutex_handle:
            try:
                import ctypes
                ctypes.windll.kernel32.CloseHandle(self.mutex_handle)
                self.mutex_handle = None
                logger.info("Released single-instance mutex.")
            except Exception as e:
                logger.error(f"Error closing mutex handle: {e}")

        if self._ipc_server:
            try:
                self._ipc_server.close()
                self._ipc_server = None
                logger.info("Closed single-instance IPC server.")
            except Exception as e:
                logger.error(f"Error closing IPC server socket: {e}")

