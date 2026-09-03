import os
import time
import logging
import threading
from typing import Callable, Optional, List, Dict, Any

from config import config
from core.brain import Brain
from core.wakeword import WakeWordDetectorFactory
from core.listener import SpeechListener
from core.transcriber import SpeechTranscriber
from core.command_normalizer import CommandNormalizer
from core.intent_engine import IntentEngine
from core.response_manager import ResponseManager
from core.tts.tts_manager import TTSManager
from core.conversation_manager import ConversationManager
from memory.session_memory import SessionMemory
from memory.execution_history import ExecutionHistory
from modules.system.executor import CommandExecutor

logger = logging.getLogger("Jarvis.Runtime")

class JarvisRuntime:
    """Headless Central Voice Core Coordinator.
    Manages all service lifecycles, pipeline stage transitions, duplex audio lockouts,
    and observer callbacks without any UI event loop dependencies.
    """

    def __init__(self):
        logger.info("[JARVIS_INITIALIZING] Starting Voice Core Coordinator...")

        # System state
        self.current_status = "STANDBY"
        self.current_speech_text = "Standby. Say 'Jarvis' or speak into microphone."
        self.muted = False
        self.pending_intent = None
        self._tts_speaking_lock = False

        # Observers / Callbacks
        self.on_status_change_cb: Optional[Callable[[str], None]] = None
        self.on_speech_text_cb: Optional[Callable[[str], None]] = None
        self.on_pipeline_stage_cb: Optional[Callable] = None
        self.on_action_complete_cb: Optional[Callable] = None
        self.on_history_update_cb: Optional[Callable] = None
        self.on_permission_dialog_cb: Optional[Callable] = None
        self.on_speech_debug_cb: Optional[Callable] = None

        # Core Engines
        self.brain = Brain()
        self.transcriber = SpeechTranscriber()
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.memory = SessionMemory(max_turns=20)
        self.conversation_manager = ConversationManager(max_turns=20, session_timeout=60.0)
        self.history_tracker = ExecutionHistory(limit=100)
        self.executor = CommandExecutor(history_tracker=self.history_tracker)

        # Audio Output Engine
        self.tts_manager = TTSManager()
        self.response_manager = ResponseManager(speaker=self.tts_manager)

        # Audio Input Engine
        self.listener = SpeechListener(threshold=getattr(config, "vad_threshold", 0.015), enable_vad_onset=True)

        # Wake Word Detector
        self.wakeword_detector = WakeWordDetectorFactory.create_detector(
            getattr(config, "wakeword_engine", "mock"),
            wake_words=getattr(config, "wake_words", ["jarvis"]),
            api_key=getattr(config, "porcupine_api_key", ""),
            model_path=getattr(config, "openwakeword_model_path", ""),
            sensitivity=getattr(config, "wakeword_sensitivity", 0.5)
        )

        # Wire Subsystem Callbacks
        self._wire_subsystems()
        logger.info("[JARVIS_ONLINE] Voice Core Subsystems Initialized & Ready.")

    def _wire_subsystems(self):
        self.listener.on_speech_start_cb = self._on_speech_start
        self.listener.on_speech_end_cb = self._on_speech_end

        self.tts_manager.on_start_speaking_cb = self._on_speaker_started
        self.tts_manager.on_stop_speaking_cb = self._on_speaker_stopped

    def start(self):
        """Starts background loops (VAD listener, TTS worker, WakeWord detector)."""
        logger.info("Starting background services...")
        self.tts_manager.start(self._on_speaker_started, self._on_speaker_stopped)
        self.listener.start(self._on_speech_start, self._on_speech_end)
        self.wakeword_detector.start(self._on_wakeword)
        self._update_status("STANDBY")
        logger.info("[JARVIS_ONLINE] Standing by for wake word...")

    def stop(self):
        """Halts all background threads cleanly."""
        logger.info("Shutting down Jarvis Voice Core...")
        self.wakeword_detector.stop()
        self.listener.stop()
        self.tts_manager.stop()
        logger.info("Jarvis Voice Core terminated cleanly.")

    # ==========================================
    # OBSERVER / CALLBACK REGISTRATION
    # ==========================================
    def register_observers(
        self,
        on_status_change=None,
        on_speech_text=None,
        on_pipeline_stage=None,
        on_action_complete=None,
        on_history_update=None,
        on_permission_dialog=None,
        on_speech_debug=None
    ):
        if on_status_change: self.on_status_change_cb = on_status_change
        if on_speech_text: self.on_speech_text_cb = on_speech_text
        if on_pipeline_stage: self.on_pipeline_stage_cb = on_pipeline_stage
        if on_action_complete: self.on_action_complete_cb = on_action_complete
        if on_history_update: self.on_history_update_cb = on_history_update
        if on_permission_dialog: self.on_permission_dialog_cb = on_permission_dialog
        if on_speech_debug: self.on_speech_debug_cb = on_speech_debug

    def _update_status(self, status: str):
        self.current_status = status
        logger.info(f"Pipeline State -> [{status}]")
        if self.on_status_change_cb:
            self._trigger_cb(self.on_status_change_cb, status)

    def _update_speech_text(self, text: str):
        self.current_speech_text = text
        if self.on_speech_text_cb:
            self._trigger_cb(self.on_speech_text_cb, text)

    def _trigger_cb(self, cb, *args):
        if cb:
            try:
                cb(*args)
            except Exception as e:
                logger.error(f"Error in observer callback: {e}")

    # ==========================================
    # DETECTOR EVENT CALLBACKS
    # ==========================================
    def _on_wakeword(self, word: str):
        if self._tts_speaking_lock or self.tts_manager.is_speaking():
            logger.info("Suppressing wake word trigger during TTS speech playback.")
            return

        logger.info(f"[WAKE_WORD_DETECTED] Triggered for keyword: '{word}'")
        if self.tts_manager.is_speaking():
            self.tts_manager.interrupt()

        self._update_status("LISTENING")
        self._update_speech_text("Listening...")

        # Play instantaneous acoustic earcon chime acknowledging wake word
        self.tts_manager.play_wake_chime()
        self.listener.trigger_manual_recording(manual=True)

    def _on_speech_start(self):
        if self._tts_speaking_lock or self.tts_manager.is_speaking():
            logger.info("Suppressing VAD speech onset during TTS playback.")
            return

        logger.info("[RECORDING_STARTED] Voice onset detected by VAD.")
        self._update_status("LISTENING")
        self._update_speech_text("Listening...")

    def _on_speech_end(self, wav_path: str):
        logger.info(f"[RECORDING_FINISHED] Speech audio saved to temporary file: {wav_path}")
        self._update_status("TRANSCRIBING")

        text = ""
        try:
            text = self.transcriber.transcribe(wav_path)
            logger.info(f"[WHISPER_RESULT] Transcribed text: '{text}'")
            meta = getattr(self.transcriber, "last_metadata", {})
            if self.on_speech_debug_cb:
                self._trigger_cb(
                    self.on_speech_debug_cb,
                    text,
                    meta.get("confidence", 0.0),
                    meta.get("language", "en"),
                    meta.get("duration", 0.0)
                )
        except Exception as e:
            logger.error(f"Transcriber error: {e}", exc_info=True)
        finally:
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception as ex:
                    logger.warning(f"Could not remove temporary WAV file: {ex}")

        if not text:
            logger.info("[RETURNED_TO_STANDBY] Silence detected.")
            self._update_status("STANDBY")
            self._update_speech_text("Standby. Say 'Jarvis' or speak into microphone.")
            return

        self._update_speech_text(f"You: {text}")
        self.process_command(text)

    def resolve_permission(self, confirmed: bool):
        """Resolves a pending safety-restricted action from UI dialog confirmation."""
        if self.pending_intent:
            if confirmed:
                logger.info("Safety confirmation accepted via UI permission dialog.")
                pending = self.pending_intent
                self.pending_intent = None
                self._execute_intent(pending, confirm=True)
            else:
                logger.info("Safety confirmation rejected via UI permission dialog.")
                self.pending_intent = None
                self.response_manager.cancellation()
                self._update_status("STANDBY")
                self._update_speech_text("Action canceled. Standby.")

    # ==========================================
    # COMMAND PIPELINE & EXECUTION
    # ==========================================
    def process_command(self, text: str):
        t0_start = time.time()
        self._update_status("THINKING")
        clean_text = text.lower().strip()

        # 1. Safety confirmation handler
        if self.pending_intent:
            yes_phrases = ["yes", "confirm", "sure", "ok", "go ahead", "do it"]
            if any(p in clean_text for p in yes_phrases):
                logger.info("Safety confirmation received.")
                self._execute_intent(self.pending_intent, confirm=True)
            else:
                logger.info("Safety confirmation rejected.")
                self.pending_intent = None
                self.response_manager.cancellation()
                self._update_status("STANDBY")
                self._update_speech_text("Action canceled. Standby.")
            return

        # 2. Multi-command clause splitting
        chained_commands = self.normalizer.split_chained_commands(text)
        if len(chained_commands) > 1:
            logger.info(f"Multi-command chain detected ({len(chained_commands)} sub-commands): {chained_commands}")
            sub_results = []
            for i, sub_cmd in enumerate(chained_commands):
                logger.info(f"Executing sequential sub-command {i+1}/{len(chained_commands)}: '{sub_cmd}'")
                res = self._process_single_command(sub_cmd, raw_full_text=text, speak=False)
                if res:
                    sub_results.append(res)
                time.sleep(0.1)

            # Single concise summary response for multi-commands
            summary_text = self.response_manager.local_engine.format_multi_command_response(sub_results)
            self.response_manager.success(summary_text, spoken_text=summary_text, speak=True)
            self._notify_pipeline_stage(text, text, "multi_command", "Chain Executed", summary_text, "Speaking")

            t_total_ms = (time.time() - t0_start) * 1000
            logger.info(f"[PERFORMANCE] Multi-Command Total: {t_total_ms:.1f} ms")
            return

        self._process_single_command(text, raw_full_text=text, speak=True)

    def _process_single_command(self, text: str, raw_full_text: str = None, speak: bool = True) -> dict:
        t0_proc = time.time()
        raw_full_text = raw_full_text or text
        norm_res = self.normalizer.normalize(text)
        normalized_text = norm_res["normalized"]
        t_norm_ms = (time.time() - t0_proc) * 1000
        logger.info(f"[NORMALIZED_COMMAND] Cleaned text: '{normalized_text}' (Raw: '{raw_full_text}')")

        t0_intent = time.time()
        intent_node = self.intent_engine.parse(normalized_text)
        t_intent_ms = (time.time() - t0_intent) * 1000
        intent = intent_node.get("intent", "unknown")
        logger.info(f"[INTENT_RESULT] Intent='{intent}', Action='{intent_node.get('action')}', Target='{intent_node.get('target')}' (Intent Latency: {t_intent_ms:.1f}ms)")

        if intent == "greeting":
            res = self.response_manager.greeting(normalized_text, speak=speak)
            self._notify_pipeline_stage(raw_full_text, normalized_text, "greeting:respond", "N/A (Greeting)", res["spoken_text"], "Speaking")
            return {"success": True, "action": "greeting", "message": res["spoken_text"]}

        if intent == "thank_you":
            resp_text = self.response_manager.local_engine.get_template("thank_you")
            res = self.response_manager.conversation(resp_text, speak=speak)
            self._notify_pipeline_stage(raw_full_text, normalized_text, "thank_you:respond", "N/A (Thank You)", res["spoken_text"], "Speaking")
            return {"success": True, "action": "thank_you", "message": res["spoken_text"]}

        if intent == "goodbye":
            resp_text = self.response_manager.local_engine.get_template("goodbye")
            res = self.response_manager.conversation(resp_text, speak=speak)
            self._notify_pipeline_stage(raw_full_text, normalized_text, "goodbye:respond", "N/A (Goodbye)", res["spoken_text"], "Speaking")
            return {"success": True, "action": "goodbye", "message": res["spoken_text"]}

        if intent == "help":
            res = self.response_manager.help_info(speak=speak)
            self._notify_pipeline_stage(raw_full_text, normalized_text, "help:info", "N/A (Help)", res["spoken_text"], "Speaking")
            return {"success": True, "action": "help", "message": res["spoken_text"]}

        if intent == "identity":
            res = self.response_manager.identity_info(speak=speak)
            self._notify_pipeline_stage(raw_full_text, normalized_text, "identity:info", "N/A (Identity)", res["spoken_text"], "Speaking")
            return {"success": True, "action": "identity", "message": res["spoken_text"]}

        if intent == "repeat_response":
            res = self.response_manager.repeat_last_response(speak=speak)
            self._notify_pipeline_stage(raw_full_text, normalized_text, "repeat:speech", "N/A (Repeat)", res["spoken_text"], "Speaking")
            return {"success": True, "action": "repeat", "message": res["spoken_text"]}

        os_intents = [
            "open_app", "close_app", "window_control", "file_access",
            "screenshot", "system_control", "status_request", "system_action",
            "open_website", "history_query", "terminal_execute", "system_telemetry",
            "project_control", "filesystem_control", "web_search",
            "time_query", "date_query", "math_calculation", "media_control",
            "test_speech", "test_microphone"
        ]

        if intent in os_intents:
            return self._execute_intent(intent_node, confirm=False, speak=speak)
        else:
            logger.info("Query routed to ConversationManager for processing.")
            conv_res = self.conversation_manager.process_query(text)
            response_text = conv_res["text"]
            self.memory.add_interaction(text, response_text)
            self.response_manager.conversation(response_text, speak=speak)
            stage_source = conv_res.get("source", "Conversation")
            self._notify_pipeline_stage(raw_full_text, normalized_text, f"chat:{intent_node.get('action')}", f"N/A ({stage_source})", response_text, "Speaking")
            return {"success": True, "action": "conversation", "message": response_text, "source": stage_source}

    def _execute_intent(self, intent_node: dict, confirm: bool = False, speak: bool = True) -> dict:
        self._update_status("EXECUTING")
        result = self.executor.execute(intent_node, confirm=confirm)

        if result.get("pending_confirmation"):
            self.pending_intent = intent_node
            self.response_manager.warning(result["message"], speak=speak)
            self._update_speech_text(f"Safety Warning: {result['message']}")
            if self.on_permission_dialog_cb:
                self._trigger_cb(self.on_permission_dialog_cb, result["action"], result["message"])
            return result

        self.pending_intent = None
        success = result["success"]
        action = result["action"]
        message = result["message"]
        logger.info(f"[EXECUTOR_RESULT] Success={success} | Action='{action}' | Message='{message}'")

        spoken = self.response_manager.local_engine.format_intent_response(intent_node, result)

        if success:
            self.response_manager.success(message, spoken_text=spoken, speak=speak)
        else:
            self.response_manager.failure(message, spoken_text=spoken, speak=speak)

        if self.on_action_complete_cb:
            self._trigger_cb(self.on_action_complete_cb, action, success, message)
        if self.on_history_update_cb:
            self._trigger_cb(self.on_history_update_cb, self.history_tracker.get_history())

        return {"success": success, "action": action, "message": spoken}

    def _notify_pipeline_stage(self, raw, norm, intent_str, exec_str, resp_str, state):
        if self.on_pipeline_stage_cb:
            self._trigger_cb(self.on_pipeline_stage_cb, raw, norm, intent_str, exec_str, resp_str, state)

    # ==========================================
    # DUPLEX AUDIO & SPEAKER STATUS
    # ==========================================
    def _on_speaker_started(self):
        self._tts_speaking_lock = True
        self.listener.set_speaking_active(True)
        self._update_status("SPEAKING")

    def _on_speaker_stopped(self):
        if not self.tts_manager.is_speaking():
            self._tts_speaking_lock = False
            self.listener.set_speaking_active(False)
            self._update_status("STANDBY")
            self._update_speech_text("Standby. Say 'Jarvis' or speak into microphone.")
            logger.info("[RETURNED_TO_STANDBY] Speech complete. Voice Core on Standby.")

    def set_mute_state(self, muted: bool):
        self.muted = muted
        if muted:
            logger.info("Microphone muted. Halting listener.")
            self.listener.stop()
            self.tts_manager.speak("Systems muted", interrupt=True)
        else:
            logger.info("Microphone active. Starting listener.")
            self.listener.start()
            self.tts_manager.speak("Systems active", interrupt=True)
