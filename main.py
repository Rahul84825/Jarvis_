import sys
import os
import time
import signal
import argparse
import logging
from pathlib import Path

from config import config
from core.jarvis_runtime import JarvisRuntime

logger = logging.getLogger("Jarvis.Main")

def print_headless_banner(runtime: JarvisRuntime):
    banner = f"""
============================================================
           JARVIS VOICE CORE INITIALIZING
============================================================
Wake word engine : READY ({getattr(config, "wakeword_engine", "mock")})
Microphone       : READY (VAD Threshold: {getattr(config, "vad_threshold", 0.015)})
Whisper Model    : READY ({getattr(config, "whisper_model_size", "small")} on {getattr(config, "whisper_device", "cpu")})
Command Engine   : READY (Intent & Multi-Command Parser)
Executor         : READY (Platform: {runtime.executor.history_tracker and "Active"})
TTS Engine       : READY (Provider: {runtime.tts_manager.provider.get_name()})
============================================================
JARVIS ONLINE — Standing by for wake word...
============================================================
"""
    print(banner)

def run_headless():
    logger.info("Initializing Jarvis in Headless Voice Core Mode.")
    runtime = JarvisRuntime()
    print_headless_banner(runtime)

    def handle_sigint(sig, frame):
        print("\nStopping Jarvis Voice Core...")
        runtime.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    runtime.start()

    # Keep main thread alive in headless mode
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping Jarvis Voice Core...")
        runtime.stop()
        sys.exit(0)

def run_ui_mode(start_minimized=False):
    logger.info("Initializing Jarvis in UI GUI Dashboard Mode.")
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
    from PyQt6.QtGui import QAction
    from ui.main_window import MainWindow

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    runtime = JarvisRuntime()
    window = None

    def _on_window_closed():
        nonlocal window
        logger.info("MainWindow closed signal intercepted. De-coupling references from coordinator.")
        window = None

    def show_window():
        nonlocal window
        if not window:
            window = MainWindow()
            window.sig_closed.connect(_on_window_closed)

            # Map UI button triggers to runtime
            window.trigger_wakeword_cb = lambda: runtime._on_wakeword("jarvis")
            window.toggle_mute_cb = lambda muted: runtime.set_mute_state(muted)

            # Map typed command submission
            window.sig_command_submitted.connect(lambda cmd: runtime.process_command(cmd))

            # Map safety permission dialog response
            window.sig_permission_resolved.connect(lambda confirmed: runtime.resolve_permission(confirmed))

            # Connect runtime observers to UI signals
            runtime.register_observers(
                on_status_change=lambda status: window and window.sig_status_changed.emit(status),
                on_speech_text=lambda text: window and window.sig_speech_text_updated.emit(text),
                on_pipeline_stage=lambda raw, norm, intent, exec_str, resp, state: window and window.sig_pipeline_stage_updated.emit(raw, norm, intent, exec_str, resp, state),
                on_action_complete=lambda action, success, msg: window and window.sig_last_action_updated.emit(action, success, msg),
                on_history_update=lambda history: window and window.sig_history_updated.emit(history),
                on_permission_dialog=lambda action, msg: window and window.sig_show_permission_dialog.emit(action, msg),
                on_speech_debug=lambda text, conf, lang, dur: window and window.sig_speech_debug_updated.emit(text, conf, lang, dur)
            )

        window.show()
        window.raise_()
        window.activateWindow()

    # System Tray
    tray_icon = QSystemTrayIcon()
    from PyQt6.QtWidgets import QStyle
    dummy = MainWindow()
    icon = dummy.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
    dummy.close()

    tray_icon.setIcon(icon)
    tray_icon.setToolTip("GOLIYA Assistant Core")
    menu = QMenu()

    show_action = QAction("Open HUD Dashboard", menu)
    show_action.triggered.connect(show_window)
    exit_action = QAction("Shut Down Goliya", menu)
    exit_action.triggered.connect(lambda: (runtime.stop(), tray_icon.hide(), app.quit()))

    menu.addAction(show_action)
    menu.addSeparator()
    menu.addAction(exit_action)
    tray_icon.setContextMenu(menu)
    tray_icon.show()

    runtime.start()

    if not start_minimized:
        QTimer.singleShot(0, show_window)

    sys.exit(app.exec())

def main():
    parser = argparse.ArgumentParser(description="Goliya / Jarvis Desktop Assistant")
    parser.add_argument("--headless", action="store_true", help="Run in headless voice core mode (no GUI)")
    parser.add_argument("--ui", action="store_true", help="Run with PyQt6 HUD UI Dashboard")
    parser.add_argument("--minimized", action="store_true", help="Launch UI minimized to system tray")

    args, unknown = parser.parse_known_args()

    if args.headless:
        run_headless()
    else:
        run_ui_mode(start_minimized=args.minimized)

if __name__ == "__main__":
    main()
