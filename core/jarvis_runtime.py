import os
import time
import uuid
import logging
import threading
from collections import deque
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

from core.ai.intelligence_router import intelligence_router, MODE_FAST_LOCAL, MODE_CONTEXT, MODE_REASONING, MODE_QUESTION
from core.proactive_daemon import proactive_daemon

logger = logging.getLogger("Jarvis.Runtime")

VALID_STATES = {"STANDBY", "LISTENING", "TRANSCRIBING", "UNDERSTANDING", "EXECUTING", "THINKING", "SPEAKING", "ERROR"}

LEGAL_TRANSITIONS = {
    "STANDBY": {"LISTENING", "THINKING", "UNDERSTANDING", "EXECUTING", "SPEAKING", "STANDBY", "ERROR"},
    "LISTENING": {"TRANSCRIBING", "STANDBY", "SPEAKING", "ERROR"},
    "TRANSCRIBING": {"UNDERSTANDING", "THINKING", "EXECUTING", "STANDBY", "SPEAKING", "ERROR"},
    "UNDERSTANDING": {"EXECUTING", "THINKING", "SPEAKING", "STANDBY", "ERROR"},
    "EXECUTING": {"SPEAKING", "STANDBY", "THINKING", "ERROR"},
    "THINKING": {"EXECUTING", "SPEAKING", "STANDBY", "ERROR"},
    "SPEAKING": {"STANDBY", "LISTENING", "ERROR"},
    "ERROR": {"STANDBY", "LISTENING"}
}

class JarvisRuntime:
    """Headless Central Voice Core Coordinator with Transaction Tracking,
    Authoritative State Machine, and Performance Telemetry.
    """

    def __init__(self):
        logger.info("[JARVIS_INITIALIZING] Starting Voice Core Coordinator...")

        # System state
        self.current_status = "STANDBY"
        self.current_speech_text = "Standby. Say 'Jarvis' or speak into microphone."
        self.muted = False
        self.pending_intent = None
        self._tts_speaking_lock = False
        self._state_lock = threading.Lock()

        # Transaction & Deduplication Cache
        self._dedup_cache: Dict[str, float] = {}
        self._dedup_lock = threading.Lock()

        # Observers / Callbacks
        self.on_status_change_cb: Optional[Callable[[str], None]] = None
        self.on_speech_text_cb: Optional[Callable[[str], None]] = None
        self.on_pipeline_stage_cb: Optional[Callable] = None
        self.on_action_complete_cb: Optional[Callable] = None
        self.on_history_update_cb: Optional[Callable] = None
        self.on_permission_dialog_cb: Optional[Callable] = None
        self.on_speech_debug_cb: Optional[Callable] = None
        self.on_audio_amplitude_cb: Optional[Callable[[float], None]] = None
        self.on_camera_state_cb: Optional[Callable] = None
        self.on_gesture_cb: Optional[Callable] = None

        # Core Engines
        self.history_tracker = ExecutionHistory(limit=100)
        self.executor = CommandExecutor(history_tracker=self.history_tracker)
        self.brain = Brain(executor=self.executor)
        self.transcriber = SpeechTranscriber(cpu_threads=getattr(config, "whisper_threads", 4))
        self.normalizer = CommandNormalizer()
        self.intent_engine = IntentEngine()
        self.memory = SessionMemory(max_turns=20)
        self.conversation_manager = ConversationManager(max_turns=20, session_timeout=60.0)
        self.proactive_daemon = proactive_daemon

        from core.multi_step_planner import multi_step_planner
        self.multi_step_planner = multi_step_planner
        self.multi_step_planner.set_dependencies(self.intent_engine, self.executor)

        # Audio Output Engine
        self.tts_manager = TTSManager()
        self.response_registry = response_registry
        self.response_manager = ResponseManager(speaker=self.tts_manager)

        # Perception & Camera Engine
        from core.perception.camera_manager import camera_manager
        self.camera_manager = camera_manager

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
        self.listener.on_barge_in_cb = self.tts_manager.interrupt

        self.tts_manager.on_start_synthesizing_cb = self._on_speaker_synthesizing
        self.tts_manager.on_start_speaking_cb = self._on_speaker_started
        self.tts_manager.on_stop_speaking_cb = self._on_speaker_stopped
        self.tts_manager.on_audio_amplitude_cb = lambda amp: self._trigger_cb(self.on_audio_amplitude_cb, amp)

        self.camera_manager.on_state_change_cb = lambda event: self._trigger_cb(self.on_camera_state_cb, event)
        self.camera_manager.on_gesture_cb = lambda event: self._trigger_cb(self.on_gesture_cb, event)

    def start(self):
        """Starts background loops (VAD listener, TTS worker, WakeWord detector, STT prewarm)."""
        logger.info("Starting background services...")
        self.transcriber.preload_in_background()
        self.tts_manager.start(
            on_start_speaking=self._on_speaker_started,
            on_stop_speaking=self._on_speaker_stopped,
            on_start_synthesizing=self._on_speaker_synthesizing,
            on_audio_amplitude=lambda amp: self._trigger_cb(self.on_audio_amplitude_cb, amp)
        )
        self.listener.start(self._on_speech_start, self._on_speech_end)
        self.wakeword_detector.start(self._on_wakeword)
        self.proactive_daemon.start(self._on_proactive_alert)
        self._update_status("STANDBY")
        logger.info("[JARVIS_ONLINE] Standing by for wake word...")

    def stop(self):
        """Halts all background threads cleanly."""
        logger.info("Shutting down Jarvis Voice Core...")
        self.camera_manager.force_stop()
        self.proactive_daemon.stop()
        self.wakeword_detector.stop()
        self.listener.stop()
        self.tts_manager.stop()
        logger.info("Jarvis Voice Core terminated cleanly.")

    def _on_proactive_alert(self, title: str, message: str, speak: bool = False):
        """Handles proactive alerts from the background daemon without blocking voice core."""
        logger.info(f"[PROACTIVE_EVENT] [{title}] {message}")
        self._update_speech_text(f"Notice: {message}")
        if speak and not self.muted and not self.tts_manager.is_speaking():
            self.response_manager.conversation(message, speak=True)

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
        on_speech_debug=None,
        on_audio_amplitude=None,
        on_camera_state=None,
        on_gesture=None
    ):
        if on_status_change: self.on_status_change_cb = on_status_change
        if on_speech_text: self.on_speech_text_cb = on_speech_text
        if on_pipeline_stage: self.on_pipeline_stage_cb = on_pipeline_stage
        if on_action_complete: self.on_action_complete_cb = on_action_complete
        if on_history_update: self.on_history_update_cb = on_history_update
        if on_permission_dialog: self.on_permission_dialog_cb = on_permission_dialog
        if on_speech_debug: self.on_speech_debug_cb = on_speech_debug
        if on_audio_amplitude: self.on_audio_amplitude_cb = on_audio_amplitude
        if on_camera_state: self.on_camera_state_cb = on_camera_state
        if on_gesture: self.on_gesture_cb = on_gesture

    def _update_status(self, status: str, utterance_id: Optional[str] = None):
        with self._state_lock:
            allowed = LEGAL_TRANSITIONS.get(self.current_status, VALID_STATES)
            if status not in allowed:
                logger.warning(f"Illegal state transition attempted: {self.current_status} -> {status}. Ignoring.")
                return

            self.current_status = status
            prefix = f"[UTTERANCE {utterance_id}] " if utterance_id else ""
            logger.info(f"{prefix}Pipeline State -> [{status}]")

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

        utterance_id = uuid.uuid4().hex[:6].upper()
        logger.info(f"[UTTERANCE {utterance_id}][WAKE_WORD_DETECTED] Keyword: '{word}'")
        self._update_status("LISTENING", utterance_id)
        self._update_speech_text("Listening...")

        # Play instantaneous acoustic earcon chime acknowledging wake word
        self.tts_manager.play_wake_chime()
        self.listener.trigger_manual_recording(manual=True)

    def _on_speech_start(self):
        if self._tts_speaking_lock or self.tts_manager.is_speaking():
            logger.info("Suppressing VAD speech onset during TTS playback.")
            return

        utterance_id = uuid.uuid4().hex[:6].upper()
        logger.info(f"[UTTERANCE {utterance_id}][RECORDING_STARTED] Voice onset confirmed by VAD.")
        self._update_status("LISTENING", utterance_id)
        self._update_speech_text("Listening...")

    def _on_speech_end(self, wav_path: str):
        utterance_id = uuid.uuid4().hex[:6].upper()
        t_speech_end = time.time()
        trace = tracer.start_trace()
        trace.record_timestamp("speech_end", t_speech_end)
        trace.record_timestamp("vad_complete", t_speech_end)
        logger.info(f"[UTTERANCE {utterance_id}][RECORDING_FINISHED] Speech audio saved: {wav_path}")
        self._update_status("TRANSCRIBING", utterance_id)

        text = ""
        whisper_duration_s = 0.0
        audio_dur_s = 0.0
        t_stt_start = time.time()
        try:
            t0_whisper = time.time()
            text = self.transcriber.transcribe(wav_path)
            whisper_duration_s = time.time() - t0_whisper
            meta = getattr(self.transcriber, "last_metadata", {})
            audio_dur_s = meta.get("duration", 0.0)
            logger.info(f"[UTTERANCE {utterance_id}][WHISPER_RESULT] '{text}' (Confidence={meta.get('confidence', 0.0):.2f})")
            if self.on_speech_debug_cb:
                self._trigger_cb(
                    self.on_speech_debug_cb,
                    text,
                    meta.get("confidence", 0.0),
                    meta.get("language", "en"),
                    audio_dur_s
                )
        except Exception as e:
            logger.error(f"[UTTERANCE {utterance_id}] Transcriber error: {e}", exc_info=True)
        finally:
            if os.path.exists(wav_path):
                try:
                    os.remove(wav_path)
                except Exception as ex:
                    logger.warning(f"Could not remove temporary WAV file: {ex}")

        # Empty speech early exit
        if not text or not text.strip():
            logger.info(f"[UTTERANCE {utterance_id}][EMPTY_TRANSCRIPT] Silence or noise discarded. Returning to STANDBY.")
            tracer.end_trace(trace.correlation_id, status="SILENCE_DETECTED")
            self._update_status("STANDBY", utterance_id)
            self._update_speech_text("Standby. Say 'Jarvis' or speak into microphone.")
            return

        self._update_speech_text(f"You: {text}")
        self.process_command(text, utterance_id=utterance_id, t0_start=t_speech_end, whisper_ms=whisper_duration_s * 1000, audio_dur_s=audio_dur_s)

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
    def process_command(self, text: str, utterance_id: Optional[str] = None, t0_start: Optional[float] = None, whisper_ms: float = 0.0, audio_dur_s: float = 0.0):
        """Dispatches command execution asynchronously."""
        actual_uid = utterance_id or uuid.uuid4().hex[:6].upper()
        t0 = t0_start or time.time()
        threading.Thread(
            target=self._process_command_worker,
            args=(text, actual_uid, t0, whisper_ms, audio_dur_s),
            name=f"CmdWorker-{actual_uid}",
            daemon=True
        ).start()

    def _is_duplicate_request(self, normalized_text: str) -> bool:
        """Suppresses accidental rapid duplicate callbacks within 1.2s."""
        now = time.time()
        with self._dedup_lock:
            last_time = self._dedup_cache.get(normalized_text, 0.0)
            if (now - last_time) < 1.2:
                return True
            self._dedup_cache[normalized_text] = now
            self._dedup_cache = {k: v for k, v in self._dedup_cache.items() if now - v < 5.0}
            return False

    def _process_command_worker(self, text: str, utterance_id: Optional[str] = None, t0_start: Optional[float] = None, whisper_ms: float = 0.0, audio_dur_s: float = 0.0):
        if utterance_id is None:
            utterance_id = uuid.uuid4().hex[:6].upper()
        if t0_start is None:
            t0_start = time.time()
        self._update_status("UNDERSTANDING", utterance_id)
        clean_text = text.lower().strip()

        # 1. Safety confirmation handler
        if self.pending_intent:
            yes_phrases = ["yes", "confirm", "sure", "ok", "go ahead", "do it"]
            if any(p in clean_text for p in yes_phrases):
                logger.info(f"[UTTERANCE {utterance_id}] Safety confirmation accepted.")
                self._execute_intent(self.pending_intent, confirm=True, utterance_id=utterance_id)
            else:
                logger.info(f"[UTTERANCE {utterance_id}] Safety confirmation rejected.")
                self.pending_intent = None
                self.response_manager.cancellation()
                self._update_status("STANDBY", utterance_id)
                self._update_speech_text("Action canceled. Standby.")
            return

        # 2. Duplicate request check
        norm_res = self.normalizer.normalize(text)
        normalized = norm_res["normalized"]
        if self._is_duplicate_request(normalized):
            logger.info(f"[UTTERANCE {utterance_id}][DEDUP] Suppressing duplicate rapid request execution: '{normalized}'")
            self._update_status("STANDBY", utterance_id)
            return

        # 3. Multi-command clause splitting
        chained_commands = self.normalizer.split_chained_commands(text)
        if len(chained_commands) > 1:
            logger.info(f"[UTTERANCE {utterance_id}][MULTI_COMMAND] {len(chained_commands)} sub-commands: {chained_commands}")
            sub_results = []
            for i, sub_cmd in enumerate(chained_commands):
                logger.info(f"[UTTERANCE {utterance_id}] Sub-command {i+1}/{len(chained_commands)}: '{sub_cmd}'")
                res = self._process_single_command(sub_cmd, raw_full_text=text, speak=False, utterance_id=utterance_id)
                if res:
                    sub_results.append(res)
                time.sleep(0.05)

            # Single aggregated concise summary response for multi-commands
            summary_text = self.response_manager.local_engine.format_multi_command_response(sub_results)
            all_ok = all(r.get("success", False) for r in sub_results) if sub_results else False
            if all_ok:
                self.response_manager.success(summary_text, spoken_text=summary_text, speak=True)
            else:
                self.response_manager.failure(summary_text, spoken_text=summary_text, speak=True)
            self._notify_pipeline_stage(text, normalized, "multi_command", "Chain Executed", summary_text, "Speaking")

            t_total_ms = (time.time() - t0_start) * 1000
            logger.info(f"[PERFORMANCE][{utterance_id}] capture={audio_dur_s:.2f}s whisper={whisper_ms:.0f}ms multi_exec={t_total_ms:.0f}ms total={t_total_ms:.0f}ms")
            return

        self._process_single_command(text, raw_full_text=text, speak=True, utterance_id=utterance_id, t0_start=t0_start, whisper_ms=whisper_ms, audio_dur_s=audio_dur_s)

    def _process_single_command(
        self,
        text: str,
        raw_full_text: str = None,
        speak: bool = True,
        utterance_id: Optional[str] = None,
        t0_start: Optional[float] = None,
        whisper_ms: float = 0.0,
        audio_dur_s: float = 0.0
    ) -> dict:
        uid = utterance_id or uuid.uuid4().hex[:6].upper()
        t0_proc = time.time()
        raw_full_text = raw_full_text or text
        trace = tracer.get_current_trace()

        # Route via 3-Layer Intelligence Router
        t0_route = time.time()
        req = intelligence_router.route(text, session_context=self.conversation_manager.get_context())
        routing_ms = (time.time() - t0_route) * 1000
        normalized_text = req.normalized_text
        logger.info(f"[UTTERANCE {uid}][ROUTER] Mode='{req.mode}' | Layer={req.layer} | Intent='{req.intent}' | Target='{req.target}' ({routing_ms:.1f}ms)")

        # Case 1: Clarification Needed
        if req.intent == "CLARIFICATION_REQUIRED":
            clarification_msg = req.clarification_prompt or f"Could you please clarify what you mean by '{req.target}'?"
            self.conversation_manager.pending_clarification = req.entities.get("ambiguous_type")
            self.response_manager.conversation(clarification_msg, speak=speak)
            self._notify_pipeline_stage(raw_full_text, normalized_text, "clarify:request", "N/A (Clarification)", clarification_msg, "Speaking")
            return {"success": True, "action": "clarification", "message": clarification_msg}

        # Case 2: Layer 3 - Complex Reasoning / Agentic Multi-Step Task
        if req.layer == 3 or req.mode == MODE_REASONING:
            self._update_status("THINKING", uid)
            logger.info(f"[UTTERANCE {uid}][AGENTIC_REASONING] Invoking AgentBrain for: '{text}'")
            t0_agent = time.time()
            agent_res = self.conversation_manager.agent.reason_and_execute(text, conversation_history=self.conversation_manager.history)
            agent_ms = (time.time() - t0_agent) * 1000
            response_text = agent_res.get("text", "Task completed, sir.")
            
            self.memory.add_interaction(text, response_text)
            self.response_manager.conversation(response_text, speak=speak)
            source_lbl = agent_res.get("source", "Jarvis ReAct Agent")
            self._notify_pipeline_stage(raw_full_text, normalized_text, f"agent:{req.action}", f"AgentBrain ({source_lbl})", response_text, "Speaking")
            
            total_ms = (time.time() - (t0_start or t0_proc)) * 1000
            logger.info(f"[PERFORMANCE][{uid}] capture={audio_dur_s:.2f}s whisper={whisper_ms:.0f}ms routing={routing_ms:.1f}ms agent={agent_ms:.0f}ms total={total_ms:.0f}ms")
            return {"success": True, "action": "reasoning_agent", "message": response_text, "source": source_lbl}

        # Case 3: Conversational Greetings, Acknowledgments & Etiquette
        intent_lower = req.intent.lower()
        if intent_lower in ["greeting", "thank_you", "goodbye", "help", "identity", "repeat_response", "acknowledgement", "affirmation", "negation", "how_are_you", "status_check"]:
            if intent_lower == "greeting":
                res = self.response_manager.greeting(normalized_text, speak=speak)
                resp_text = res.get("text", "Hello, Sir.")
            elif intent_lower == "help":
                from core.capability_service import capability_service
                scope = (req.entities or {}).get("scope") or req.target or "overview"
                if scope == "all" or req.action == "show_all_commands":
                    resp_text = capability_service.get_all_commands_reference()
                elif scope in ["browser", "filesystem", "applications", "system", "search", "developer", "content", "media", "custom"]:
                    resp_text = capability_service.get_scoped_commands(scope)
                else:
                    resp_text = capability_service.get_help_overview()
                res = self.response_manager.conversation(resp_text, speak=speak)
            elif intent_lower == "identity":
                res = self.response_manager.identity_info(speak=speak)
                resp_text = res.get("text", "I am JARVIS.")
            elif intent_lower == "repeat_response":
                res = self.response_manager.repeat_last_response(speak=speak)
                resp_text = res.get("text", "")
            else:
                resp_text = self.response_manager.local_engine.format_intent_response({"intent": intent_lower, "raw": normalized_text})
                res = self.response_manager.conversation(resp_text, speak=speak)

            self._notify_pipeline_stage(raw_full_text, normalized_text, f"{intent_lower}:respond", f"N/A ({intent_lower.title()})", resp_text, "Speaking")
            total_ms = (time.time() - (t0_start or t0_proc)) * 1000
            logger.info(f"[PERFORMANCE][{uid}] capture={audio_dur_s:.2f}s whisper={whisper_ms:.0f}ms routing={routing_ms:.1f}ms exec=0ms total={total_ms:.0f}ms")
            return {"success": True, "action": intent_lower, "message": resp_text}

        # Case 4: Layer 1 Fast Local & Layer 2 Deterministic Actions
        os_intents = [
            "open_app", "application.launch", "close_app", "minimize_app", "maximize_app", "window_control", "file_access",
            "screenshot", "system_control", "status_request", "system_action",
            "open_website", "history_query", "terminal_execute", "system_telemetry",
            "open_new_chrome_tab", "open_new_chrome_window",
            "project_control", "filesystem_control", "web_search",
            "time_query", "date_query", "math_calculation", "media_control",
            "test_speech", "test_microphone",
            "browser_control", "browser_tab_control", "browser_action", "youtube_control", "content_generation",
            "local_search", "developer_workflow", "follow_up",
            "explain_tool_execution", "memory_control", "privacy_control",
            "command_management", "custom_command",
            "turn_on_camera", "turn_off_camera", "start_hand_tracking", "stop_hand_tracking", "camera_snapshot",
            "unsupported_capability", "invalid_command"
        ]

        if intent_lower in os_intents:
            intent_node = dict(req.entities) if req.entities else {}
            intent_node.update({
                "intent": intent_lower,
                "action": req.action,
                "target": req.target,
                "confidence": req.confidence,
                "entities": req.entities
            })
            t0_exec = time.time()
            exec_res = self._execute_intent(intent_node, confirm=False, speak=speak, utterance_id=uid)
            exec_ms = (time.time() - t0_exec) * 1000
            if exec_res.get("success"):
                self.conversation_manager.update_context(req.action, req.target)

            total_ms = (time.time() - (t0_start or t0_proc)) * 1000
            logger.info(f"[PERFORMANCE][{uid}] capture={audio_dur_s:.2f}s whisper={whisper_ms:.0f}ms routing={routing_ms:.1f}ms exec={exec_ms:.0f}ms total={total_ms:.0f}ms")
            return exec_res
        else:
            # Case 5: Informational Questions & Conversation
            logger.info(f"[UTTERANCE {uid}] Query routed to ConversationManager.")
            t0_conv = time.time()
            conv_res = self.conversation_manager.process_query(text)
            conv_ms = (time.time() - t0_conv) * 1000
            response_text = conv_res["text"]
            self.memory.add_interaction(text, response_text)

            self.response_manager.conversation(response_text, speak=speak)
            stage_source = conv_res.get("source", "Conversation")
            self._notify_pipeline_stage(raw_full_text, normalized_text, f"chat:{req.action}", f"N/A ({stage_source})", response_text, "Speaking")

            total_ms = (time.time() - (t0_start or t0_proc)) * 1000
            logger.info(f"[PERFORMANCE][{uid}] capture={audio_dur_s:.2f}s whisper={whisper_ms:.0f}ms routing={routing_ms:.1f}ms conv={conv_ms:.0f}ms total={total_ms:.0f}ms")
            return {"success": True, "action": "conversation", "message": response_text, "source": stage_source}

    def _execute_intent(self, intent_node: dict, confirm: bool = False, speak: bool = True, utterance_id: Optional[str] = None) -> dict:
        uid = utterance_id or uuid.uuid4().hex[:6].upper()
        self._update_status("EXECUTING", uid)
        intent = intent_node.get("intent", "").lower()
        action = intent_node.get("action") or intent

        # Handle Camera Subsystem Actions Directly
        if intent in ["turn_on_camera", "turn_off_camera", "start_hand_tracking", "stop_hand_tracking", "camera_snapshot"]:
            if intent == "turn_on_camera":
                ok = self.camera_manager.acquire(reason="voice_cmd")
                msg = "Camera activated and vision perception online, Sir." if ok else "Camera hardware unavailable."
            elif intent == "turn_off_camera":
                self.camera_manager.force_stop()
                ok = True
                msg = "Camera deactivated and hardware released, Sir."
            elif intent == "start_hand_tracking":
                ok = self.camera_manager.acquire(reason="hand_tracking")
                msg = "Hand tracking and gesture recognition active, Sir." if ok else "Camera unavailable."
            elif intent == "stop_hand_tracking":
                self.camera_manager.release(reason="hand_tracking")
                ok = True
                msg = "Hand tracking deactivated, Sir."
            elif intent == "camera_snapshot":
                ok, path = self.camera_manager.capture_snapshot()
                msg = f"Photo captured to {path}, Sir." if ok else "Failed to capture photo."

            res = {"success": ok, "action": intent, "target": "camera", "message": msg}
            self.response_manager.conversation(msg, speak=speak)
            self._update_status("STANDBY", uid)
            self._update_speech_text(msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, intent, ok, msg)
            self._notify_pipeline_stage("", "", f"camera:{intent}", "CameraManager", msg, "Speaking")
            return res

        # 1. Missing argument check
        if intent_node.get("missing_arg"):
            missing_msg = self.response_registry.get_missing_arg_prompt(intent_node) or "What would you like me to do, Sir?"
            logger.info(f"[MISSING_ARG] Prompting: '{missing_msg}'")
            self.response_manager.missing_argument(missing_msg, speak=speak)
            self._update_status("STANDBY", uid)
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
            self._update_status("STANDBY", uid)
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
            self._update_status("STANDBY", uid)
            self._update_speech_text(invalid_msg)
            if self.on_action_complete_cb:
                self._trigger_cb(self.on_action_complete_cb, action, False, invalid_msg)
            return {
                "success": False,
                "outcome": CommandOutcome.INVALID_COMMAND.value,
                "action": action,
                "message": invalid_msg
            }

        # 4. Acknowledgment only before long-running / multi-step operations
        # For immediate local operations (<150ms), produce one final response to prevent speech collisions
        if intent in ["content_generation", "multi_step_workflow"] or intent_node.get("is_long_running"):
            ack_msg = self.response_registry.get_acknowledgment(intent_node)
            if ack_msg and speak:
                logger.info(f"[ACKNOWLEDGMENT] Speaking: '{ack_msg}'")
                self.response_manager.acknowledge_command(ack_msg, speak=speak)

        trace = tracer.get_current_trace()
        t_tool_start = time.time()
        if trace:
            trace.record_timestamp("tool_start", t_tool_start)

        self._update_status("EXECUTING", uid)
        result = self.executor.execute(intent_node, confirm=confirm)
        t_tool_end = time.time()

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

        logger.info(f"[UTTERANCE {uid}][EXECUTOR_RESULT] Success={success} | Outcome={outcome.value} | Action='{action}' | Message='{message}'")

        if success:
            spoken = self.response_registry.get_success_response(intent_node, result)
            self.response_manager.success(message, spoken_text=spoken, speak=speak)
        else:
            spoken = self.response_registry.get_failure_response(intent_node, outcome, message)
            self.response_manager.failure(message, spoken_text=spoken, speak=speak)

        self._update_status("STANDBY", uid)
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
