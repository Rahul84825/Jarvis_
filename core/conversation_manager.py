import time
import logging
from typing import List, Dict, Any, Optional
from core.ai.provider_manager import ProviderManager
from core.local_response_engine import LocalResponseEngine

logger = logging.getLogger("Jarvis.ConversationManager")

class ConversationManager:
    """Manages multi-turn conversation memory, session timeout, follow-up query context,
    and routing to the ProviderManager.
    """

    def __init__(self, max_turns: int = 20, session_timeout: float = 60.0):
        self.max_turns = max_turns
        self.session_timeout = session_timeout
        self.history: List[Dict[str, str]] = []
        self.last_interaction_timestamp: float = 0.0
        self.provider_manager = ProviderManager()
        self.local_engine = LocalResponseEngine()

    def _check_session_timeout(self):
        """Resets conversation memory if inactivity period exceeds session_timeout."""
        if self.last_interaction_timestamp > 0:
            elapsed = time.time() - self.last_interaction_timestamp
            if elapsed > self.session_timeout:
                logger.info(f"Conversation session timed out after {elapsed:.1f}s inactivity. Resetting history.")
                self.history.clear()

    def process_query(self, query: str) -> Dict[str, Any]:
        """Processes a conversational user query, preserving short-term context for follow-up resolution."""
        self._check_session_timeout()

        # Add user query to conversation context
        user_msg = {"role": "user", "content": query.strip()}
        messages_payload = self.history + [user_msg]

        t0 = time.time()
        response_text = self.provider_manager.generate_response(messages_payload)
        t_duration_ms = (time.time() - t0) * 1000

        if response_text:
            logger.info(f"[CONVERSATION] AI Provider Response ({t_duration_ms:.1f}ms): '{response_text}'")
            # Save interaction turn in rolling history
            self.history.append(user_msg)
            self.history.append({"role": "assistant", "content": response_text})

            # Trim history to max_turns
            if len(self.history) > (self.max_turns * 2):
                self.history = self.history[-(self.max_turns * 2):]

            self.last_interaction_timestamp = time.time()
            return {
                "text": response_text,
                "source": self.provider_manager.get_active_provider_name(),
                "ai_available": True,
                "latency_ms": t_duration_ms
            }

        # Fallback when no AI provider is configured or available
        logger.info("[CONVERSATION] No AI provider available. Outputting polite local capability fallback.")
        fallback_text = "I'm currently limited to my local capabilities for that question."
        return {
            "text": fallback_text,
            "source": "Local Fallback",
            "ai_available": False,
            "latency_ms": t_duration_ms
        }

    def clear_session(self):
        """Clears all conversation session history."""
        self.history.clear()
        self.last_interaction_timestamp = 0.0
        logger.info("Conversation session memory cleared manually.")
