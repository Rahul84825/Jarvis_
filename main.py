import sys
import os
import time
import signal
import argparse
import logging
from pathlib import Path

from config import config
from core.lazy_loader import lazy_attr

JarvisRuntime = lazy_attr("core.jarvis_runtime", "JarvisRuntime")

logger = logging.getLogger("Jarvis.Main")

def print_headless_banner(runtime: JarvisRuntime):
    banner = f"""
============================================================
           SANTRA VOICE CORE INITIALIZING
============================================================
Wake word engine : READY ({getattr(config, "wakeword_engine", "mock")})
Microphone       : READY ({getattr(runtime.listener, "active_input_device_name", "Default Mic")} | VAD: {getattr(config, "vad_threshold", 0.015)})
Whisper Model    : READY ({getattr(config, "whisper_model_size", "small")} on {getattr(config, "whisper_device", "cpu")})
Command Engine   : READY (Intent & Multi-Command Parser)
Executor         : READY (Platform: {runtime.executor.history_tracker and "Active"})
TTS Engine       : READY (Provider: {runtime.tts_manager.provider.get_name()})
============================================================
SANTRA ONLINE — Standing by for wake word...
============================================================
"""
    print(banner)

def run_headless(guard=None):
    logger.info("Initializing Santra in Headless Voice Core Mode.")
    runtime = JarvisRuntime()
    print_headless_banner(runtime)

    def handle_sigint(sig, frame):
        print("\nStopping Santra Voice Core...")
        runtime.stop()
        if guard:
            guard.release()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigint)
    runtime.start()

    # Keep main thread alive in headless mode
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping Santra Voice Core...")
        runtime.stop()
        if guard:
            guard.release()
        sys.exit(0)

def run_ui_mode(start_minimized=False, guard=None):
    logger.info("Initializing Santra in UI GUI Dashboard Mode.")
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
    from PyQt6.QtGui import QAction
    from ui.main_window import MainWindow

    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    runtime = JarvisRuntime()
    window = MainWindow()

    # Map UI button triggers to runtime
    window.trigger_wakeword_cb = lambda: runtime.trigger_manual_talk()
    window.toggle_mute_cb = lambda muted: runtime.set_mute_state(muted)
    window.toggle_sleep_cb = lambda: runtime.wake_up(source="manual_click") if runtime.current_status == "SLEEPING" else runtime.enter_sleep_mode()
    window.speak_cb = lambda text: runtime.response_manager.conversation(text, speak=True)

    # Map typed command submission
    window.sig_command_submitted.connect(lambda cmd: runtime.process_command(cmd))

    # Map safety permission dialog response
    window.sig_permission_resolved.connect(lambda confirmed: runtime.resolve_permission(confirmed))

    def safe_emit(signal_obj, *args):
        try:
            signal_obj.emit(*args)
        except RuntimeError:
            pass

    # Connect runtime observers to UI signals
    runtime.register_observers(
        on_status_change=lambda status: (safe_emit(window.sig_status_changed, status), update_tray_status(status)),
        on_speech_text=lambda text: safe_emit(window.sig_speech_text_updated, text),
        on_pipeline_stage=lambda raw, norm, intent, exec_str, resp, state: safe_emit(window.sig_pipeline_stage_updated, raw, norm, intent, exec_str, resp, state),
        on_action_complete=lambda action, success, msg: safe_emit(window.sig_last_action_updated, action, success, msg),
        on_history_update=lambda history: safe_emit(window.sig_history_updated, history),
        on_permission_dialog=lambda action, msg: safe_emit(window.sig_show_permission_dialog, action, msg),
        on_speech_debug=lambda text, conf, lang, dur: safe_emit(window.sig_speech_debug_updated, text, conf, lang, dur),
        on_audio_amplitude=lambda amp: safe_emit(window.sig_audio_amplitude_updated, amp),
        on_camera_state=lambda event: safe_emit(window.sig_camera_state_updated, event),
        on_gesture=lambda event: safe_emit(window.sig_gesture_detected, event)
    )

    def show_window():
        window.show()
        window.raise_()
        window.activateWindow()

    runtime.open_virtual_lab_cb = lambda: window._open_virtual_lab()

    # Start single-instance IPC server to listen for wakeups from secondary launches
    if guard:
        guard.start_ipc_server(on_activate=show_window)

    # System Tray
    tray_icon = QSystemTrayIcon()
    from PyQt6.QtWidgets import QStyle
    icon = app.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)

    tray_icon.setIcon(icon)
    menu = QMenu()

    show_action = QAction("🖥️ Open HUD Dashboard", menu)
    show_action.triggered.connect(show_window)

    lab_action = QAction("🧪 Virtual Testing Room", menu)
    lab_action.triggered.connect(lambda: window._open_virtual_lab())

    talk_action = QAction("🎙️ Talk / Activate Now", menu)
    talk_action.triggered.connect(lambda: runtime.trigger_manual_talk())

    standby_action = QAction("⏸️ Return to Standby", menu)
    standby_action.triggered.connect(lambda: runtime.enter_standby())

    sleep_action = QAction("🌙 Sleep / Wake Santra", menu)
    sleep_action.triggered.connect(lambda: runtime.wake_up(source="manual_click") if runtime.current_status == "SLEEPING" else runtime.enter_sleep_mode())

    from core.startup import is_startup_enabled, enable_startup, disable_startup
    startup_action = QAction("🚀 Start with Windows", menu)
    startup_action.setCheckable(True)
    startup_action.setChecked(is_startup_enabled())

    def toggle_startup():
        if startup_action.isChecked():
            ok = enable_startup()
            if not ok:
                startup_action.setChecked(False)
        else:
            ok = disable_startup()
            if not ok:
                startup_action.setChecked(True)

    startup_action.triggered.connect(toggle_startup)

    mute_action = QAction("🔇 Mute Microphone (Privacy)", menu)
    mute_action.setCheckable(True)
    mute_action.setChecked(runtime.muted)

    def toggle_mute():
        runtime.set_mute_state(mute_action.isChecked())

    mute_action.triggered.connect(toggle_mute)

    exit_action = QAction("❌ Shut Down Santra", menu)
    def handle_exit():
        if guard:
            guard.release()
        runtime.stop()
        tray_icon.hide()
        app.quit()

    exit_action.triggered.connect(handle_exit)

    menu.addAction(show_action)
    menu.addAction(lab_action)
    menu.addAction(talk_action)
    menu.addAction(standby_action)
    menu.addSeparator()
    menu.addAction(mute_action)
    menu.addAction(startup_action)
    menu.addSeparator()
    menu.addAction(exit_action)
    tray_icon.setContextMenu(menu)
    tray_icon.show()

    def update_tray_status(status: str):
        mic_lbl = "MUTED" if runtime.muted else "ACTIVE"
        tray_icon.setToolTip(f"SANTRA Autonomous Assistant Core // [{status}] (Mic: {mic_lbl})")
        mute_action.setChecked(runtime.muted)

    tray_icon.activated.connect(lambda reason: show_window() if reason in (QSystemTrayIcon.ActivationReason.DoubleClick, QSystemTrayIcon.ActivationReason.Trigger) else None)
    update_tray_status("STANDBY")

    runtime.start()

    if not start_minimized:
        show_window()

    exit_code = app.exec()
    if guard:
        guard.release()
    sys.exit(exit_code)

def main():
    parser = argparse.ArgumentParser(description="Santra Desktop Assistant")
    parser.add_argument("--headless", action="store_true", help="Run in headless voice core mode (no GUI)")
    parser.add_argument("--ui", action="store_true", help="Run with PyQt6 HUD UI Dashboard")
    parser.add_argument("--minimized", action="store_true", help="Launch UI minimized to system tray")

    args, unknown = parser.parse_known_args()

    # Single-Instance Enforcement
    from core.single_instance import SingleInstanceGuard
    guard = SingleInstanceGuard()
    if not guard.acquire():
        logger.warning("Another instance of SANTRA is already running. Notifying existing instance and exiting cleanly.")
        guard.notify_existing("RESTORE_HUD")
        sys.exit(0)

    if args.headless:
        run_headless(guard=guard)
    else:
        run_ui_mode(start_minimized=args.minimized, guard=guard)

if __name__ == "__main__":
    main()

