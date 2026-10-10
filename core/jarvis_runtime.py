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
from core.tracing import tracer
from core.response_registry import response_registry, CommandOutcome

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
        self.transcriber = SpeechTranscriber(cpu_threads=getattr(config, "whisper_threads", 4))
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.memory = SessionMemory(max_turns=20)
        self.conversation_manager = ConversationManager(max_turns=20, session_timeout=60.0)
        self.history_tracker = ExecutionHistory(limit=100)
        self.executor = CommandExecutor(history_tracker=self.history_tracker)
        from core.multi_step_planner import multi_step_planner
        self.multi_step_planner = multi_step_planner
        self.multi_step_planner.set_dependencies(self.intent_engine, self.executor)

        # Audio Output Engine
        self.tts_manager = TTSManager()
        self.response_registry = response_registry
        self.response_manager = ResponseManager(speaker=self.tts_manager)

        # Audio Input Engine
        self.listener = SpeechListener(
            sample_rate=getattr(config, "audio_sample_rate", 16000),
            threshold=getattr(config, "vad_threshold", 0.015),
            silence_duration=getattr(config, "silence_duration", 0.8),
            max_duration=getattr(config, "max_duration", 5.0),
            enable_vad_onset=True
        )

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

        self.tts_manager.on_start_synthesizing_cb = self._on_speaker_synthesizing
        self.tts_manager.on_start_speaking_cb = self._on_speaker_started
        self.tts_manager.on_stop_speaking_cb = self._on_speaker_stopped

    def start(self):
        """Starts background loops (VAD listener, TTS worker, WakeWord detector, STT prewarm)."""
        logger.info("Starting background services...")
        self.transcriber.preload_in_background()
        self.tts_manager.start(self._on_speaker_started, self._on_speaker_stopped, self._on_speaker_synthesizing)
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
            if self.tts_manager.is_playing():
                logger.info(f"[BARGE_IN] Wake word '{word}' detected during active playback. Interrupting TTS.")
                self.tts_manager.interrupt(force=True)
            else:
                logger.info("Suppressing wake word trigger during TTS synthesis.")
                return

        logger.info(f"[WAKE_WORD_DETECTED] Triggered for keyword: '{word}'")
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
        t_speech_end = time.time()
        trace = tracer.start_trace()
        trace.record_timestamp("speech_end", t_speech_end)
        trace.record_timestamp("vad_complete", t_speech_end)
        logger.info(f"[VOICE] speech_end={t_speech_end:.4f}")
        logger.info(f"[RECORDING_FINISHED] Speech audio saved to temporary file: {wav_path}")
        self._update_status("TRANSCRIBING")

        text = ""
        t_stt_start = time.time()
        logger.info(f"[STT] start={t_stt_start:.4f}")
        try:
            text = self.transcriber.transcribe(wav_path)
            t_stt_end = time.time()
            logger.info(f"[STT] end={t_stt_end:.4f} (latency: {(t_stt_end - t_stt_start)*1000:.1f}ms)")
            logger.info(f"[TIMELINE] Speech -> Transcript: {(t_stt_end - t_speech_end)*1000:.1f}ms")
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
            tracer.end_trace(trace.correlation_id, status="SILENCE_DETECTED")
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
        trace = tracer.get_current_trace() or tracer.start_trace()
        trace.recognized_text = text
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

            # Single concise summary response for multi-commands with truthful reporting
            summary_text = self.response_manager.local_engine.format_multi_command_response(sub_results)
            all_ok = all(r.get("success", False) for r in sub_results) if sub_results else False
            if all_ok:
                self.response_manager.success(summary_text, spoken_text=summary_text, speak=True)
            else:
                self.response_manager.failure(summary_text, spoken_text=summary_text, speak=True)
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

        trace = tracer.get_current_trace()
        if trace:
            trace.normalized_text = normalized_text
            trace.record_timestamp("norm_end", time.time())

        t0_intent = time.time()
        intent_node = self.intent_engine.parse(normalized_text, raw_text=raw_full_text or text)
        t_intent_end = time.time()
        t_intent_ms = (t_intent_end - t0_intent) * 1000
        intent = intent_node.get("intent", "unknown")
        action = intent_node.get("action") or intent
        logger.info(f"[ROUTER] end={t_intent_end:.4f} (latency: {t_intent_ms:.1f}ms)")
        logger.info(f"[INTENT_RESULT] Intent='{intent}', Action='{action}', Target='{intent_node.get('target')}' (Intent Latency: {t_intent_ms:.1f}ms)")

        if trace:
            trace.intent = intent
            trace.action = action
            trace.record_timestamp("intent_end", t_intent_end)

        if intent in ["greeting", "thank_you", "goodbye", "help", "identity", "repeat_response"]:
            if trace:
                trace.intelligence_layer = "L1_LOCAL"
                t_t_start = time.time()
                trace.record_timestamp("tool_start", t_t_start)

            if intent == "greeting":
                res = self.response_manager.greeting(normalized_text, speak=speak)
                action_name = "greeting"
            elif intent == "thank_you":
                resp_text = self.response_manager.local_engine.get_template("thank_you")
                res = self.response_manager.conversation(resp_text, speak=speak)
                action_name = "thank_you"
            elif intent == "goodbye":
                resp_text = self.response_manager.local_engine.get_template("goodbye")
                res = self.response_manager.conversation(resp_text, speak=speak)
                action_name = "goodbye"
            elif intent == "help":
                res = self.response_manager.help_info(speak=speak)
                action_name = "help"
            elif intent == "identity":
                res = self.response_manager.identity_info(speak=speak)
                action_name = "identity"
            elif intent == "repeat_response":
                res = self.response_manager.repeat_last_response(speak=speak)
                action_name = "repeat"

            t_t_end = time.time()
            if trace:
                trace.record_timestamp("tool_end", t_t_end)
                trace.record_timestamp("response_ready", t_t_end)
                trace.record_tool_execution(action_name, "[LOCAL]", f"{action_name}_template", (t_t_end - t_t_start)*1000, True)

            self._notify_pipeline_stage(raw_full_text, normalized_text, f"{action_name}:respond", f"N/A ({action_name.title()})", res["spoken_text"], "Speaking")
            return {"success": True, "action": action_name, "message": res["spoken_text"]}

        os_intents = [
            "open_app", "application.launch", "close_app", "window_control", "file_access",
            "screenshot", "system_control", "status_request", "system_action",
            "open_website", "history_query", "terminal_execute", "system_telemetry",
            "project_control", "filesystem_control", "web_search",
            "time_query", "date_query", "math_calculation", "media_control",
            "test_speech", "test_microphone",
            "browser_control", "youtube_control", "content_generation",
            "local_search", "developer_workflow", "follow_up",
            "explain_tool_execution", "memory_control", "privacy_control",
            "command_management", "custom_command",
            "unsupported_capability", "invalid_command"
        ]

        if intent in os_intents:
            if trace:
                trace.intelligence_layer = "L1_LOCAL"
            return self._execute_intent(intent_node, confirm=False, speak=speak)
        else:
            logger.info("Query routed to ConversationManager for processing.")
            t_conv_start = time.time()
            if trace:
                trace.record_timestamp("tool_start", t_conv_start)
                trace.intelligence_layer = "L3_CLOUD" if self.conversation_manager.provider_manager.is_ai_available() else "L2_OFFLINE"

            conv_res = self.conversation_manager.process_query(text)
            t_conv_end = time.time()
            response_text = conv_res["text"]
            self.memory.add_interaction(text, response_text)

            if trace:
                trace.record_timestamp("tool_end", t_conv_end)
                trace.record_timestamp("response_ready", t_conv_end)
                if conv_res.get("ai_available"):
                    trace.record_external_api(
                        provider=conv_res.get("source", "Cloud AI"),
                        operation="generate_response",
                        endpoint="api.ai_provider",
                        duration_ms=conv_res.get("latency_ms", (t_conv_end - t_conv_start)*1000),
                        success=True
                    )
                else:
                    trace.record_tool_execution("conversation_fallback", "[LOCAL]", "local_fallback", (t_conv_end - t_conv_start)*1000, True)

            self.response_manager.conversation(response_text, speak=speak)
            stage_source = conv_res.get("source", "Conversation")
            self._notify_pipeline_stage(raw_full_text, normalized_text, f"chat:{intent_node.get('action')}", f"N/A ({stage_source})", response_text, "Speaking")
            return {"success": True, "action": "conversation", "message": response_text, "source": stage_source}

    def _execute_intent(self, intent_node: dict, confirm: bool = False, speak: bool = True) -> dict:
        intent = intent_node.get("intent", "unknown")
        action = intent_node.get("action") or intent

        # 1. Missing argument check
        if intent_node.get("missing_arg"):
            missing_msg = self.response_registry.get_missing_arg_prompt(intent_node) or "What would you like me to do, Sir?"
            logger.info(f"[MISSING_ARG] Prompting: '{missing_msg}'")
            self.response_manager.missing_argument(missing_msg, speak=speak)
            self._update_status("STANDBY")
            self._update_speech_text(missing_msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, action, False, missing_msg)
            return {
                "success": False,
                "outcome": CommandOutcome.MISSING_ARGUMENT.value,
                "action": action,
                "message": missing_msg
            }

        # 2. Unsupported capability
        if intent == "unsupported_capability":
            unsupported_msg = self.response_registry.get_outcome_response(CommandOutcome.UNSUPPORTED_CAPABILITY)
            logger.info(f"[UNSUPPORTED] '{unsupported_msg}'")
            self.response_manager.unsupported_capability(unsupported_msg, speak=speak)
            self._update_status("STANDBY")
            self._update_speech_text(unsupported_msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, action, False, unsupported_msg)
            return {
                "success": False,
                "outcome": CommandOutcome.UNSUPPORTED_CAPABILITY.value,
                "action": action,
                "message": unsupported_msg
            }

        # 3. Invalid command
        if intent == "invalid_command":
            invalid_msg = self.response_registry.get_outcome_response(CommandOutcome.INVALID_COMMAND)
            logger.info(f"[INVALID_COMMAND] '{invalid_msg}'")
            self.response_manager.invalid_command(invalid_msg, speak=speak)
            self._update_status("STANDBY")
            self._update_speech_text(invalid_msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, action, False, invalid_msg)
            return {
                "success": False,
                "outcome": CommandOutcome.INVALID_COMMAND.value,
                "action": action,
                "message": invalid_msg
            }

        # 4. Acknowledgment before potentially longer operations
        ack_msg = self.response_registry.get_acknowledgment(intent_node)
        if ack_msg and speak:
            logger.info(f"[ACKNOWLEDGMENT] Speaking: '{ack_msg}'")
            self.response_manager.acknowledge_command(ack_msg, speak=speak)

        trace = tracer.get_current_trace()
        t_tool_start = time.time()
        if trace:
            trace.record_timestamp("tool_start", t_tool_start)

        self._update_status("EXECUTING")
        result = self.executor.execute(intent_node, confirm=confirm)
        t_tool_end = time.time()
        logger.info(f"[TOOL] end={t_tool_end:.4f}")

        if trace:
            trace.record_timestamp("tool_end", t_tool_end)
            category = "[EXTERNAL_API]" if intent in ["open_website", "web_search"] else "[OS]"
            trace.record_tool_execution(
                name=action,
                category=category,
                operation=action,
                duration_ms=(t_tool_end - t_tool_start) * 1000,
                success=result.get("success", False),
                error=result.get("message") if not result.get("success") else None
            )

        if result.get("pending_confirmation"):
            self.pending_intent = intent_node
            self.response_manager.warning(result["message"], speak=speak)
            self._update_speech_text(f"Safety Warning: {result['message']}")
            if self.on_permission_dialog_cb:
                self._trigger_cb(self.on_permission_dialog_cb, result["action"], result["message"])
            return result

        self.pending_intent = None
        success = result.get("success", False)
        action = result.get("action", intent)
        message = result.get("message", "")
        raw_outcome = result.get("outcome")
        if raw_outcome:
            try:
                outcome = CommandOutcome(raw_outcome)
            except ValueError:
                outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED
        else:
            outcome = CommandOutcome.SUCCESS if success else CommandOutcome.EXECUTION_FAILED

        logger.info(f"[EXECUTOR_RESULT] Success={success} | Outcome={outcome.value} | Action='{action}' | Message='{message}'")

        if success:
            spoken = self.response_registry.get_success_response(intent_node, result)
            self.response_manager.success(message, spoken_text=spoken, speak=speak)
        else:
            spoken = self.response_registry.get_failure_response(intent_node, outcome, message)
            self.response_manager.failure(message, spoken_text=spoken, speak=speak)

        self._update_status("STANDBY")
        self._update_speech_text(spoken)

        if trace:
            trace.record_timestamp("response_ready", time.time())

        if self.on_action_complete_cb:
            self._trigger_cb(self.on_action_complete_cb, action, success, spoken)
        if self.on_history_update_cb:
            self._trigger_cb(self.on_history_update_cb, self.history_tracker.get_history())

        return {"success": success, "outcome": outcome.value, "action": action, "message": spoken}

    def _notify_pipeline_stage(self, raw, norm, intent_str, exec_str, resp_str, state):
        if self.on_pipeline_stage_cb:
            self._trigger_cb(self.on_pipeline_stage_cb, raw, norm, intent_str, exec_str, resp_str, state)

    # ==========================================
    # DUPLEX AUDIO & SPEAKER STATUS
    # ==========================================
    def _on_speaker_synthesizing(self):
        self._tts_speaking_lock = True
        self.listener.set_speaking_active(True)
        self._update_status("SYNTHESIZING")

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
