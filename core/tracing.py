import os
import json
import time
import uuid
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from config import config

logger = logging.getLogger("Jarvis.Tracer")

SENSITIVE_KEYS = {
    "api_key", "apikey", "key", "token", "authorization", "auth",
    "password", "secret", "bearer", "cookie", "gemini_api_key",
    "openrouter_api_key", "cerebras_api_key", "openai_api_key",
    "porcupine_api_key"
}

def redact_sensitive(obj: Any) -> Any:
    """Recursively redacts sensitive keys and values from dictionaries and lists."""
    if isinstance(obj, dict):
        clean = {}
        for k, v in obj.items():
            if any(s in str(k).lower() for s in SENSITIVE_KEYS):
                clean[k] = "[REDACTED]"
            elif isinstance(v, (dict, list)):
                clean[k] = redact_sensitive(v)
            elif isinstance(v, str) and any(s in v.lower() for s in ["bearer ", "eyj"]):
                clean[k] = "[REDACTED]"
            else:
                clean[k] = v
        return clean
    elif isinstance(obj, list):
        return [redact_sensitive(x) for x in obj]
    return obj


class CommandTrace:
    """Represents a single command trace lifecycle identified by a unique correlation ID."""

    def __init__(self, correlation_id: Optional[str] = None):
        self.correlation_id = correlation_id or f"cmd-{uuid.uuid4().hex[:8]}"
        self.start_time = time.time()
        self.end_time: Optional[float] = None
        self.status = "IN_PROGRESS"
        
        # Raw Command & Recognition Metadata
        self.recognized_text = ""
        self.normalized_text = ""
        self.intent = ""
        self.action = ""
        self.intelligence_layer = "L1_LOCAL"  # L1_LOCAL | L2_OFFLINE | L3_CLOUD
        
        # Timeline Timestamps
        self.timestamps: Dict[str, float] = {}
        
        # Tool & External API Spans
        self.tool_executions: List[Dict[str, Any]] = []
        self.external_api_calls: List[Dict[str, Any]] = []
        
        # Audio / Playback Verification
        self.playback_info: Dict[str, Any] = {
            "provider": "",
            "file_path": "",
            "file_exists": False,
            "file_size": 0,
            "output_device_idx": None,
            "output_device_name": "",
            "playback_initialized": False,
            "playback_started": False,
            "playback_completed": False,
            "playback_cancelled": False,
            "exception": None
        }

        # Computed Milestones (ms)
        self.milestones: Dict[str, float] = {}

    def record_timestamp(self, event_name: str, t: Optional[float] = None):
        """Records a timestamped event."""
        self.timestamps[event_name] = t if t is not None else time.time()

    def record_tool_execution(
        self,
        name: str,
        category: str,
        operation: str,
        duration_ms: float,
        success: bool,
        error: Optional[str] = None
    ):
        """Records a tool or OS execution event."""
        self.tool_executions.append({
            "name": name,
            "category": category,  # [LOCAL] | [OS] | [TOOL] | [MCP]
            "operation": operation,
            "duration_ms": round(duration_ms, 2),
            "success": success,
            "error": error
        })

    def record_external_api(
        self,
        provider: str,
        operation: str,
        endpoint: str,
        duration_ms: float,
        success: bool,
        status_code: Optional[int] = None,
        timeout: bool = False,
        fallback_used: Optional[str] = None,
        error: Optional[str] = None
    ):
        """Records an external API or remote HTTP/WebSocket call."""
        # Sanitize endpoint
        sanitized_endpoint = endpoint.split("?")[0] if endpoint else ""
        self.external_api_calls.append({
            "provider": provider,
            "operation": operation,
            "endpoint": sanitized_endpoint,
            "duration_ms": round(duration_ms, 2),
            "success": success,
            "status_code": status_code,
            "timeout": timeout,
            "fallback_used": fallback_used,
            "error": error
        })

    def calculate_milestones(self):
        """Calculates standard latency milestones across pipeline transitions."""
        ts = self.timestamps
        
        t_speech_end = ts.get("speech_end") or ts.get("vad_complete")
        t_stt_end = ts.get("stt_end")
        t_tool_start = ts.get("tool_start") or ts.get("intent_end")
        t_tool_end = ts.get("tool_end") or ts.get("response_ready")
        t_response_ready = ts.get("response_ready")
        t_playback_start = ts.get("playback_start")

        # 1. Speech-end -> transcript available
        if t_speech_end and t_stt_end:
            self.milestones["speech_end_to_transcript_ms"] = round((t_stt_end - t_speech_end) * 1000, 1)

        # 2. Transcript -> tool execution
        if t_stt_end and t_tool_start:
            self.milestones["transcript_to_tool_ms"] = round((t_tool_start - t_stt_end) * 1000, 1)

        # 3. Tool completion -> response ready
        if t_tool_end and t_response_ready:
            self.milestones["tool_to_response_ms"] = round((t_response_ready - t_tool_end) * 1000, 1)

        # 4. Response ready -> first playback
        if t_response_ready and t_playback_start:
            self.milestones["response_to_playback_ms"] = round((t_playback_start - t_response_ready) * 1000, 1)

        # 5. Total speech-end -> first audible output
        if t_speech_end and t_playback_start:
            self.milestones["total_speech_to_first_audio_ms"] = round((t_playback_start - t_speech_end) * 1000, 1)
        elif self.start_time and t_playback_start:
            self.milestones["total_speech_to_first_audio_ms"] = round((t_playback_start - self.start_time) * 1000, 1)

    def to_dict(self) -> Dict[str, Any]:
        self.calculate_milestones()
        raw = {
            "correlation_id": self.correlation_id,
            "status": self.status,
            "duration_ms": round((time.time() - self.start_time) * 1000, 1),
            "recognized_text": self.recognized_text,
            "normalized_text": self.normalized_text,
            "intent": self.intent,
            "action": self.action,
            "intelligence_layer": self.intelligence_layer,
            "milestones": self.milestones,
            "timestamps": {k: round(v, 4) for k, v in self.timestamps.items()},
            "playback_info": self.playback_info,
            "tool_executions": self.tool_executions,
            "external_api_calls": self.external_api_calls
        }
        return redact_sensitive(raw)


class CommandTracer:
    """Lightweight, configurable per-command runtime tracer."""

    def __init__(self):
        self._enabled = getattr(config, "tracing_enabled", True)
        self._active_traces: Dict[str, CommandTrace] = {}
        self._current_correlation_id: Optional[str] = None
        self._trace_log_path = config.LOGS_DIR / "traces.jsonl"

    @property
    def enabled(self) -> bool:
        return getattr(config, "tracing_enabled", True)

    def set_enabled(self, enabled: bool):
        self._enabled = enabled

    def start_trace(self, correlation_id: Optional[str] = None) -> CommandTrace:
        """Initializes and activates a new command trace."""
        if not self.enabled:
            return CommandTrace(correlation_id)

        trace = CommandTrace(correlation_id)
        self._active_traces[trace.correlation_id] = trace
        self._current_correlation_id = trace.correlation_id
        logger.info(f"[TRACER] Started trace: {trace.correlation_id}")
        return trace

    def get_current_trace(self) -> Optional[CommandTrace]:
        if not self.enabled:
            return None
        if self._current_correlation_id and self._current_correlation_id in self._active_traces:
            return self._active_traces[self._current_correlation_id]
        return None

    def get_trace(self, correlation_id: str) -> Optional[CommandTrace]:
        return self._active_traces.get(correlation_id)

    def end_trace(self, correlation_id: Optional[str] = None, status: str = "COMPLETED") -> Optional[CommandTrace]:
        if not self.enabled:
            return None

        cid = correlation_id or self._current_correlation_id
        if not cid or cid not in self._active_traces:
            return None

        trace = self._active_traces[cid]
        trace.status = status
        trace.end_time = time.time()
        trace.calculate_milestones()

        # Write to JSONL
        try:
            with open(self._trace_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace.to_dict()) + "\n")
        except Exception as e:
            logger.debug(f"[TRACER] Error saving trace log: {e}")

        logger.info(
            f"[TRACER] Finished trace: {trace.correlation_id} "
            f"| Total Latency: {trace.milestones.get('total_speech_to_first_audio_ms', 'N/A')}ms "
            f"| Status: {status}"
        )
        return trace


# Global Singleton Tracer
tracer = CommandTracer()
