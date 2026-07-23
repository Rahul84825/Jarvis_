import sys
import os
import time
import signal
import logging
from pathlib import Path

from PyQt6.QtCore import QTimer, pyqtSlot, Qt
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QAction

# Import Config and Logging setup
from config import config

# Import Core modules
from core.brain import Brain
from core.wakeword import WakeWordDetectorFactory
from core.clap_detector import ClapDetector
from core.listener import SpeechListener
from core.speaker import Speaker
from core.transcriber import SpeechTranscriber
from core.intent_engine import IntentEngine
from core.llm import GeminiClient
from memory.session_memory import SessionMemory
from memory.execution_history import ExecutionHistory
from modules.system.executor import CommandExecutor

# Import UI Main Window
from ui.main_window import MainWindow

# Global logger
logger = logging.getLogger("Jarvis.Main")

class JarvisApp:
    """Coordinator class that initializes, manages, and cleanly shuts down
    all Jarvis services and interfaces.
    """
    
    def __init__(self, start_minimized=False):
        logger.info("Initializing Jarvis Application Coordinator...")
        self.start_minimized = start_minimized
        self.muted = False
        self.current_status = "Standby"
        self.current_speech_text = "Standby. Say 'Jarvis' or double-clap."
        
        # Safety & confirmation state
        self.pending_intent = None
        
        # Initialize Core Engines
        self.brain = Brain()
        self.transcriber = SpeechTranscriber()
        self.intent_engine = IntentEngine()
        self.llm = GeminiClient()
        self.memory = SessionMemory(max_turns=20)
        self.history_tracker = ExecutionHistory(limit=100)
        self.executor = CommandExecutor(history_tracker=self.history_tracker)
        
        self.speaker = Speaker()
        self.listener = SpeechListener(threshold=config.vad_threshold, enable_vad_onset=False)
        
        # Initialize WakeWord engine using the factory
        self.wakeword_detector = WakeWordDetectorFactory.create_detector(
            config.wakeword_engine,
            wake_words=config.wake_words,
            api_key=config.porcupine_api_key,
            model_path=config.openwakeword_model_path,
            sensitivity=config.wakeword_sensitivity
        )
        
        self.clap_detector = ClapDetector(
            threshold=config.clap_threshold,
            min_gap=config.double_clap_min_gap,
            max_gap=config.double_clap_max_gap
        )
        
        # Wire callbacks
        self._wire_subsystems()
        
        # UI Reference
        self.window = None
        self.tray_icon = None
        
        # Start background engines
        self._start_services()
        
        # Setup tray icon
        self._setup_tray_icon()
        
        # Launch window if requested
        if not self.start_minimized:
            # Restore window asynchronously
            QTimer.singleShot(0, self.show_window)
        else:
            logger.info("Jarvis launched minimized to System Tray.")

    def _wire_subsystems(self):
        """Wires up callbacks and signal slots between subsystems."""
        # VAD Speech Listener
        self.listener.on_speech_start_cb = self._on_speech_start
        self.listener.on_speech_end_cb = self._on_speech_end
        
        # Double-clap & single-clap monitoring
        self.clap_detector.on_single_clap_cb = self._on_single_clap
        self.clap_detector.on_double_clap_cb = self._on_double_clap
        
        # TTS Audio Speaker callbacks
        self.speaker.on_start_speaking_cb = self._on_speaker_started
        self.speaker.on_stop_speaking_cb = self._on_speaker_stopped

    def _start_services(self):
        """Starts all VAD, wake-word and clap detection loops."""
        logger.info("Starting background services...")
        self.speaker.start(self._on_speaker_started, self._on_speaker_stopped)
        self.listener.start(self._on_speech_start, self._on_speech_end)
        self.clap_detector.start(self._on_single_clap, self._on_double_clap)
        
        # Wake word detector callback
        self.wakeword_detector.start(self._on_wakeword)
        logger.info("All background threads active.")

    def _setup_tray_icon(self):
        """Creates a system tray entry for Jarvis."""
        from PyQt6.QtWidgets import QStyle
        self.tray_icon = QSystemTrayIcon()
        
        # Use a system computer icon as default
        dummy_widget = MainWindow() # create a temporary reference to fetch styles
        icon = dummy_widget.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        dummy_widget.close()
        
        self.tray_icon.setIcon(icon)
        self.tray_icon.setToolTip("JARVIS Assistant")
        
        # Tray context menu
        menu = QMenu()
        show_action = QAction("Open HUD Dashboard", menu)
        show_action.triggered.connect(self.show_window)
        
        mute_action = QAction("Toggle Privacy Mute", menu)
        mute_action.triggered.connect(lambda: self._on_toggle_mute_manually(not self.muted))
        
        exit_action = QAction("Shut Down Jarvis", menu)
        exit_action.triggered.connect(self.exit_app)
        
        menu.addAction(show_action)
        menu.addAction(mute_action)
        menu.addSeparator()
        menu.addAction(exit_action)
        
        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()
        
        # Tray click handler
        self.tray_icon.activated.connect(self._on_tray_activated)
        logger.info("Persistent System Tray Icon initialized successfully.")

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.window and self.window.isVisible():
                self.window.hide()
                logger.info("Main window minimized to system tray.")
            else:
                self.show_window()

    def show_window(self):
        """Spawns and focuses the main UI window."""
        if not self.window:
            logger.info("Initializing Jarvis PyQt6 Window...")
            self.window = MainWindow()
            
            # Map window button trigger callbacks
            self.window.trigger_wakeword_cb = self._on_wakeword_triggered_manually
            self.window.trigger_clap_cb = self._on_clap_triggered_manually
            self.window.toggle_mute_cb = self._on_toggle_mute_manually
            
            # De-couple references on close
            self.window.sig_closed.connect(self._on_window_closed)
            # Map confirmation dialog signal resolution
            self.window.sig_permission_resolved.connect(self._on_confirm_resolved_from_ui)
            
            # Populate initial states
            self.window.sig_status_changed.emit(self.current_status)
            self.window.sig_speech_text_updated.emit(self.current_speech_text)
            self.window.sig_mic_state_changed.emit(self.muted)
            self.window.sig_history_updated.emit(self.history_tracker.get_history())
            
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
        logger.info("Jarvis window opened.")

    def _on_window_closed(self):
        logger.info("MainWindow closed signal intercepted. De-coupling references from coordinator.")
        self.window = None

    # ==========================================
    # DETECTOR CALLBACK EVENTS (Runs on Background Threads)
    # ==========================================

    def _on_wakeword(self, word):
        """Callback from WakeWordDetector thread."""
        logger.info(f"Wake word '{word}' detected. Activating Jarvis speech interface.")
        if self.speaker.is_speaking():
            logger.info("User barge-in: Interrupting speaker.")
            self.speaker.interrupt()
            
        self.current_status = "Listening"
        self.current_speech_text = "Listening..."
        if self.window:
            self.window.sig_status_changed.emit(self.current_status)
            self.window.sig_speech_text_updated.emit(self.current_speech_text)
            
        self.listener.trigger_manual_recording(manual=False)

    def _on_speech_start(self):
        """Callback from VAD SpeechListener when voice onset detected."""
        logger.info("User speech onset detected.")
        # Lockout clap detection during user speech to prevent speech plosives from triggering claps
        self.clap_detector.set_speaking_active(True)
        self.current_status = "Listening"
        self.current_speech_text = "Listening..."
        if self.window:
            self.window.sig_status_changed.emit(self.current_status)
            self.window.sig_speech_text_updated.emit(self.current_speech_text)

    def _on_speech_end(self, wav_path):
        """Callback from SpeechListener when user finishes speaking."""
        logger.info(f"User speech finished. WAV: {wav_path}")
        self.current_status = "Transcribing"
        if self.window:
            self.window.sig_status_changed.emit(self.current_status)
            
        # Run local transcriber
        text = ""
        try:
            text = self.transcriber.transcribe(wav_path)
            logger.info(f"[RAW WHISPER OUTPUT]: '{text}'")
            
            # Emit signal to update Speech Debug Panel
            if self.window and hasattr(self.transcriber, 'last_metadata'):
                meta = self.transcriber.last_metadata
                self.window.sig_speech_debug_updated.emit(
                    meta["text"],
                    meta["confidence"],
                    meta["language"],
                    meta["duration"]
                )
        except Exception as e:
            logger.error(f"Transcriber error: {e}")
            if self.window and hasattr(self.transcriber, 'last_metadata'):
                meta = self.transcriber.last_metadata
                self.window.sig_speech_debug_updated.emit(
                    meta["text"],
                    meta["confidence"],
                    meta["language"],
                    meta["duration"]
                )
        finally:
            # Clean up temporary VAD WAV file
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception as ex:
                    logger.warning(f"Could not remove WAV file: {ex}")
                    
        if not text:
            logger.info("Silence detected. Resetting VAD monitor.")
            self.current_status = "Standby"
            self.current_speech_text = "Standby. Say 'Jarvis' or double-clap."
            if self.window:
                self.window.sig_status_changed.emit(self.current_status)
                self.window.sig_speech_text_updated.emit(self.current_speech_text)
            # Re-enable clap detector since speaker callbacks won't be triggered
            self.clap_detector.set_speaking_active(False)
            return

        self.current_speech_text = f"You: {text}"
        if self.window:
            self.window.sig_speech_text_updated.emit(self.current_speech_text)
            
        # Process transcription
        self._process_text_command(text)

    def _on_single_clap(self):
        """Triggered by single clap detection."""
        if self.speaker.is_speaking():
            logger.debug("Single clap ignored: Speaker is active.")
            return
            
        logger.info("Single clap processed.")
        if self.muted:
            return
            
        self.current_speech_text = "Single clap detected. (System Ping)"
        if self.window:
            self.window.sig_speech_text_updated.emit(self.current_speech_text)
            
        self.speaker.speak("Ping acknowledged", interrupt=False)

    def _on_double_clap(self):
        """Triggered by double clap detection."""
        if self.speaker.is_speaking():
            logger.debug("Double clap ignored: Speaker is active.")
            return
            
        logger.info("Double clap processed.")
        new_mute = not self.muted
        logger.info(f"Double clap action: Toggling mute state to {new_mute}")
        self.set_mute_state(new_mute)
        
        if new_mute:
            self.speaker.speak("Systems muted", interrupt=True)
        else:
            self.speaker.speak("Systems active", interrupt=True)

    # ==========================================
    # COGNITION & COMMAND ROUTING ENGINE
    # ==========================================

    def _process_text_command(self, text: str):
        """Routes parsed text commands to either OS Executor or LLM Brain."""
        self.current_status = "Thinking"
        if self.window:
            self.window.sig_status_changed.emit(self.current_status)
            
        clean_text = text.lower().strip()
        
        # 1. Check if we are waiting for safety confirmation
        if self.pending_intent:
            yes_phrases = ["yes", "confirm", "sure", "ok", "go ahead", "do it"]
            if any(phrase in clean_text for phrase in yes_phrases):
                logger.info("Safety confirmation received via speech.")
                self._execute_with_executor(self.pending_intent, confirm=True)
            else:
                logger.info("Safety confirmation rejected via speech.")
                self.pending_intent = None
                self.speaker.speak("Cancellation acknowledged.")
                self.current_status = "Standby"
                self.current_speech_text = "Action canceled. Standby."
                if self.window:
                    self.window.sig_status_changed.emit(self.current_status)
                    self.window.sig_speech_text_updated.emit(self.current_speech_text)
            return

        # 2. Parse intent using the IntentEngine
        intent_node = self.intent_engine.parse(text)
        intent = intent_node.get("intent", "unknown")
        
        # 3. Check if it's an OS control or safety permission action
        os_intents = ["open_app", "close_app", "window_control", "file_access", "screenshot", "system_control", "status_request", "system_action"]
        
        if intent in os_intents:
            # Map standard Week 1 & 2 intent test cases:
            # IntentEngine.parse returns 'system_action' for shutdown/restart/lock
            # Map it here for the executor
            if intent == "system_action":
                action_map = intent_node.get("action")
                intent_node["intent"] = "system_control"
                intent_node["action"] = f"{action_map}_pc" if action_map in ["shutdown", "restart", "sleep", "lock"] else action_map
                
            self._execute_with_executor(intent_node, confirm=False)
        else:
            # Route to local/API LLM brain
            logger.info("Query routed to conversational cognitive model.")
            response = self.llm.generate_response(text, self.memory.get_gemini_history())
            self.memory.add_interaction(text, response)
            
            # Speak responses
            self.speaker.speak(response)

    def _execute_with_executor(self, intent_node: dict, confirm: bool = False):
        """Helper to invoke executor and process results."""
        self.current_status = "Executing"
        if self.window:
            self.window.sig_status_changed.emit(self.current_status)
            
        result = self.executor.execute(intent_node, confirm=confirm)
        
        # Handle pending high-risk confirmation
        if result.get("pending_confirmation"):
            self.pending_intent = intent_node
            
            # Speak warning
            self.speaker.speak(result["message"])
            self.current_speech_text = f"Safety Warning: {result['message']}"
            
            # Popup warning dialog on UI thread
            if self.window:
                self.window.sig_speech_text_updated.emit(self.current_speech_text)
                self.window.sig_show_permission_dialog.emit(result["action"], result["message"])
            return

        # Complete execution logic
        self.pending_intent = None
        success = result["success"]
        action = result["action"]
        message = result["message"]
        
        logger.info(f"Execution complete: Success={success} | Msg={message}")
        
        # Update HUD window elements
        if self.window:
            self.window.sig_last_action_updated.emit(action, success, message)
            self.window.sig_history_updated.emit(self.history_tracker.get_history())
            
        self.speaker.speak(message)

    def _on_confirm_resolved_from_ui(self, confirmed: bool):
        """Invoked when user accepts/rejects the modal safety popup dialog in the HUD UI."""
        if self.pending_intent:
            if confirmed:
                logger.info("Safety confirmation received via HUD UI.")
                self._execute_with_executor(self.pending_intent, confirm=True)
            else:
                logger.info("Safety confirmation rejected via HUD UI.")
                self.pending_intent = None
                self.speaker.speak("Cancellation acknowledged.")
                self.current_status = "Standby"
                self.current_speech_text = "Action canceled. Standby."
                if self.window:
                    self.window.sig_status_changed.emit(self.current_status)
                    self.window.sig_speech_text_updated.emit(self.current_speech_text)

    # ==========================================
    # SPEAKER STATUS CALLBACKS (Speaking Locks)
    # ==========================================

    def _on_speaker_started(self):
        """Triggered when Speaker begins outputting sound."""
        self.current_status = "Speaking"
        
        # Lockout VAD and Clap detectors during speaking to prevent feedback loops
        self.listener.set_speaking_active(True)
        self.clap_detector.set_speaking_active(True)
        
        if self.window:
            self.window.sig_status_changed.emit(self.current_status)

    def _on_speaker_stopped(self):
        """Triggered when Speaker queue empties."""
        if not self.speaker.is_speaking():
            self.current_status = "Standby"
            self.current_speech_text = "Standby. Say 'Jarvis' or double-clap."
            
            # Re-enable VAD and Clap detectors after speaking completes
            self.listener.set_speaking_active(False)
            self.clap_detector.set_speaking_active(False)
            
            if self.window:
                self.window.sig_status_changed.emit(self.current_status)
                self.window.sig_speech_text_updated.emit(self.current_speech_text)

    # ==========================================
    # USER CONTROLS & LIFECYCLE
    # ==========================================

    def _on_wakeword_triggered_manually(self):
        logger.info("Wake word manually triggered via UI button.")
        self._on_wakeword("jarvis")

    def _on_clap_triggered_manually(self):
        logger.info("Clap manually triggered via UI button.")
        # Trigger single clap callback
        self._on_single_clap()

    def _on_toggle_mute_manually(self, muted: bool):
        logger.info(f"Mute state manually toggled in UI to: {muted}")
        self.set_mute_state(muted)
        
        if muted:
            self.speaker.speak("Systems muted", interrupt=True)
        else:
            self.speaker.speak("Systems active", interrupt=True)

    def set_mute_state(self, muted: bool):
        """Changes system privacy mute state."""
        self.muted = muted
        
        # Update UI check state
        if self.window:
            self.window.sig_mic_state_changed.emit(muted)
            
        if muted:
            logger.info("Microphone mute active. Stopping listener.")
            self.listener.stop()
        else:
            logger.info("Microphone active. Starting listener.")
            self.listener.start()

    def exit_app(self):
        """Stops background threads and exits application."""
        logger.info("Shutting down Jarvis application coordinator...")
        self.wakeword_detector.stop()
        self.clap_detector.stop()
        self.listener.stop()
        self.speaker.stop()
        
        if self.tray_icon:
            self.tray_icon.hide()
            
        if self.window:
            self.window.close()
            
        QApplication.quit()
        logger.info("Jarvis Coordinator terminated.")

def main():
    # Set thread-safe signal handler for clean Ctrl+C exits
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Keep running in system tray even if window closed
    
    # Check startup arguments
    start_minimized = "--minimized" in sys.argv
    
    # Create the coordinator
    coordinator = JarvisApp(start_minimized=start_minimized)
    
    # Run application main loop
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
