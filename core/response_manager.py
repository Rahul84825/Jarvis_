import random
import logging
from enum import Enum

from core.local_response_engine import LocalResponseEngine
from core.speech_sanitizer import speech_sanitizer, sanitize_speech_text, enforce_conversational_brevity
from core.response_registry import response_registry, CommandOutcome

logger = logging.getLogger("Jarvis.ResponseManager")

class ResponseType(Enum):
    ACKNOWLEDGEMENT = "ACKNOWLEDGEMENT"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    CONVERSATION = "CONVERSATION"
    GREETING = "GREETING"
    HELP = "HELP"
    ABOUT = "ABOUT"
    IDENTITY = "IDENTITY"
    QUESTION = "QUESTION"
    INFORMATION = "INFORMATION"
    WARNING = "WARNING"
    CONFIRMATION = "CONFIRMATION"
    CANCELLATION = "CANCELLATION"

class StructuredResponse:
    """Standardized response data structure returned across all subsystems."""

    def __init__(self, response_type: ResponseType, text: str, spoken_text: str = None, metadata: dict = None):
        self.type = response_type if isinstance(response_type, ResponseType) else ResponseType(response_type)
        self.text = text
        self.spoken_text = spoken_text or text
        self.metadata = metadata or {}

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "text": self.text,
            "spoken_text": self.spoken_text,
            "metadata": self.metadata
        }

class ResponseManager:
    """Central Response Manager formatting natural language spoken outputs,
    managing assistant personality variations, and interfacing with TTS.
    Powered by local response engine (no LLM/cloud dependency).
    """

    def __init__(self, speaker=None):
        self.speaker = speaker
        self.last_spoken_response = None
        self.local_engine = LocalResponseEngine()
        self.wake_responses = self.local_engine.responses.get("wake_response", ["Yes?", "I'm listening.", "Go ahead."])
        self.success_prefixes = ["Sure.", "Got it.", "On it.", "Done.", "Right away."]
        logger.info("Initializing Central Response Manager (Local-First Voice Engine).")

    def set_speaker(self, speaker):
        self.speaker = speaker

    def handle_response(self, response: StructuredResponse, speak: bool = True) -> dict:
        if isinstance(response, dict):
            resp_type = response.get("type", ResponseType.INFORMATION.value)
            text = response.get("text", "")
            spoken_text = response.get("spoken_text", text)
            metadata = response.get("metadata", {})
        else:
            resp_type = response.type.value
            text = response.text
            spoken_text = response.spoken_text
            metadata = response.metadata

        # Sanitize speech for audible natural pronunciation
        if spoken_text:
            spoken_text = speech_sanitizer.sanitize(spoken_text)
            spoken_text = enforce_conversational_brevity(spoken_text, max_sentences=2)
            self.last_spoken_response = spoken_text

        tts_success = True
        if speak and self.speaker and spoken_text:
            try:
                self.speaker.speak(spoken_text)
            except Exception as e:
                tts_success = False
                logger.error(f"Response Manager failed to output speech: {e}")

        logger.info(f"Response Manager [{resp_type}]: '{text}' (Spoken: '{spoken_text}', TTS_Success={tts_success})")
        metadata["tts_success"] = tts_success

        return {
            "type": resp_type,
            "text": text,
            "spoken_text": spoken_text,
            "spoken": speak and self.speaker is not None,
            "tts_success": tts_success,
            "metadata": metadata
        }

    def wake_response(self, speak: bool = True) -> dict:
        """Outputs concise, natural wake word acknowledgment."""
        text = self.local_engine.get_wake_response()
        resp = StructuredResponse(ResponseType.ACKNOWLEDGEMENT, text)
        return self.handle_response(resp, speak=speak)

    def repeat_last_response(self, speak: bool = True) -> dict:
        if not self.last_spoken_response:
            return self.handle_response(StructuredResponse(ResponseType.INFORMATION, "I haven't spoken any response yet."), speak=speak)
        text = f"I said: {self.last_spoken_response}"
        return self.handle_response(StructuredResponse(ResponseType.INFORMATION, text, spoken_text=self.last_spoken_response), speak=speak)

    def greeting(self, query: str = "", speak: bool = True) -> dict:
        text = self.local_engine.format_intent_response({"intent": "greeting", "raw": query})
        resp = StructuredResponse(ResponseType.GREETING, text)
        return self.handle_response(resp, speak=speak)

    def help_info(self, speak: bool = True) -> dict:
        text = self.local_engine.get_help_response()
        resp = StructuredResponse(ResponseType.HELP, text)
        return self.handle_response(resp, speak=speak)

    def identity_info(self, speak: bool = True) -> dict:
        text = self.local_engine.get_identity_response()
        resp = StructuredResponse(ResponseType.IDENTITY, text)
        return self.handle_response(resp, speak=speak)

    def acknowledge(self, text: str = "On it.", speak: bool = True) -> dict:
        resp = StructuredResponse(ResponseType.ACKNOWLEDGEMENT, text)
        return self.handle_response(resp, speak=speak)

    def success(self, text: str, spoken_text: str = None, speak: bool = True) -> dict:
        if not spoken_text:
            if "screenshot" in text.lower():
                spoken_text = "Done. Screenshot saved."
            elif any(kw in text.lower() for kw in ["launched", "opened", "opening"]):
                spoken_text = f"Sure. {text}"
            else:
                spoken_text = text
        resp = StructuredResponse(ResponseType.SUCCESS, text, spoken_text=spoken_text)
        return self.handle_response(resp, speak=speak)

    def failure(self, text: str, spoken_text: str = None, speak: bool = True) -> dict:
        if not spoken_text:
            if "not found" in text.lower() or "couldn't find" in text.lower():
                spoken_text = self.local_engine.get_template("error_not_found")
            elif "unknown" in text.lower() or "unexecutable" in text.lower():
                spoken_text = "I'm not sure what you meant."
            else:
                spoken_text = self.local_engine.get_template("error_generic")
        resp = StructuredResponse(ResponseType.FAILURE, text, spoken_text=spoken_text)
        return self.handle_response(resp, speak=speak)

    def conversation(self, text: str, speak: bool = True) -> dict:
        resp = StructuredResponse(ResponseType.CONVERSATION, text)
        return self.handle_response(resp, speak=speak)

    def warning(self, text: str, spoken_text: str = None, speak: bool = True) -> dict:
        resp = StructuredResponse(ResponseType.WARNING, text, spoken_text=spoken_text)
        return self.handle_response(resp, speak=speak)

    def confirmation(self, text: str, speak: bool = True) -> dict:
        resp = StructuredResponse(ResponseType.CONFIRMATION, text)
        return self.handle_response(resp, speak=speak)

    def cancellation(self, text: str = "Action canceled. Standby.", speak: bool = True) -> dict:
        resp = StructuredResponse(ResponseType.CANCELLATION, text)
        return self.handle_response(resp, speak=speak)

    def acknowledge_command(self, text: str, speak: bool = True) -> dict:
        """Emits brief acknowledgment before executing a longer command."""
        resp = StructuredResponse(ResponseType.ACKNOWLEDGEMENT, text)
        return self.handle_response(resp, speak=speak)

    def missing_argument(self, question: str, speak: bool = True) -> dict:
        """Asks a concise clarification question when required command argument is missing."""
        resp = StructuredResponse(ResponseType.QUESTION, question, metadata={"outcome": CommandOutcome.MISSING_ARGUMENT.value})
        return self.handle_response(resp, speak=speak)

    def unsupported_capability(self, text: str = "That capability isn't available yet, Sir.", speak: bool = True) -> dict:
        """Responds when an unsupported feature or uninstalled application is requested."""
        resp = StructuredResponse(ResponseType.FAILURE, text, metadata={"outcome": CommandOutcome.UNSUPPORTED_CAPABILITY.value})
        return self.handle_response(resp, speak=speak)

    def invalid_command(self, text: str = "I couldn't complete that request, Sir. Try another command.", speak: bool = True) -> dict:
        """Responds with concise default fallback for invalid commands."""
        resp = StructuredResponse(ResponseType.FAILURE, text, metadata={"outcome": CommandOutcome.INVALID_COMMAND.value})
        return self.handle_response(resp, speak=speak)

    def permission_denied(self, text: str = "I don't have permission to do that, Sir.", speak: bool = True) -> dict:
        """Responds when an action is blocked by safety gate or denied permissions."""
        resp = StructuredResponse(ResponseType.WARNING, text, metadata={"outcome": CommandOutcome.PERMISSION_DENIED.value})
        return self.handle_response(resp, speak=speak)

    def timeout(self, text: str = "That action timed out, Sir. Please try again.", speak: bool = True) -> dict:
        """Responds when a tool or API operation times out."""
        resp = StructuredResponse(ResponseType.FAILURE, text, metadata={"outcome": CommandOutcome.TIMEOUT.value})
        return self.handle_response(resp, speak=speak)
