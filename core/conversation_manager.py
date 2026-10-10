import time
import logging
from typing import List, Dict, Any, Optional
from core.ai.provider_manager import ProviderManager
from core.local_response_engine import LocalResponseEngine
from memory.conversation_persistence import ConversationPersistence

logger = logging.getLogger("Jarvis.ConversationManager")

class ConversationManager:
    """Manages multi-turn conversation memory, session timeout, follow-up query context,
    durable SQLite persistence, and routing to the ProviderManager.
    """

    def __init__(self, max_turns: int = 20, session_timeout: float = 60.0, db_path: Optional[str] = None):
        self.max_turns = max_turns
        self.session_timeout = session_timeout
        self.history: List[Dict[str, str]] = []
        self.last_interaction_timestamp: float = 0.0
        self.provider_manager = ProviderManager()
        self.local_engine = LocalResponseEngine()
        self.persistence = ConversationPersistence(db_path=db_path)

    def restore_session_from_persistence(self, limit: int = 5):
        """Restores recent conversation turns from SQLite so context survives app restart when requested."""
        if not self.persistence.is_enabled():
            return
        try:
            recent = self.persistence.get_recent_turns(limit=min(self.max_turns, limit))
            restored = []
            for r in recent:
                restored.append({
                    "role": r["role"],
                    "content": r["content"]
                })
            self.history = restored
            if self.history:
                self.last_interaction_timestamp = time.time()
                logger.info(f"Restored {len(self.history)} messages from persistent storage into active conversation context.")
        except Exception as e:
            logger.error(f"Failed to restore conversation history from persistence: {e}")

    def _check_session_timeout(self):
        """Resets conversation in-memory session if inactivity period exceeds session_timeout."""
        if self.last_interaction_timestamp > 0:
            elapsed = time.time() - self.last_interaction_timestamp
            if elapsed > self.session_timeout:
                logger.info(f"Conversation session timed out after {elapsed:.1f}s inactivity. Resetting in-memory history.")
                self.history.clear()

    def process_query(self, query: str) -> Dict[str, Any]:
        """Processes a conversational user query, preserving short-term context for follow-up resolution
        and persisting interactions to durable SQLite storage.
        """
        self._check_session_timeout()

        # Add user query to conversation context
        user_msg = {"role": "user", "content": query.strip()}
        messages_payload = self.history + [user_msg]

        from core.profile_manager import profile_manager
        system_ctx = profile_manager.get_bounded_prompt_context()

        t0 = time.time()
        response_text = self.provider_manager.generate_response(messages_payload, context={"system_profile": system_ctx})
        t_duration_ms = (time.time() - t0) * 1000

        if response_text:
            source = self.provider_manager.get_active_provider_name()
            logger.info(f"[CONVERSATION] AI Provider Response ({t_duration_ms:.1f}ms): '{response_text}'")

            # Save interaction turn in rolling history
            self.history.append(user_msg)
            self.history.append({"role": "assistant", "content": response_text})

            # Trim history to max_turns
            if len(self.history) > (self.max_turns * 2):
                self.history = self.history[-(self.max_turns * 2):]

            self.last_interaction_timestamp = time.time()

            # Save to durable SQLite persistence
            self.persistence.save_turn(
                user_text=query,
                assistant_text=response_text,
                session_id="default",
                source=source
            )

            return {
                "text": response_text,
                "source": source,
                "ai_available": True,
                "latency_ms": t_duration_ms
            }

        # Fallback when no AI provider is configured or available
        logger.info("[CONVERSATION] No AI provider available. Outputting polite local capability fallback.")
        fallback_text = self.local_engine.get_template("no_provider_fallback")
        if not fallback_text or fallback_text == "Done.":
            fallback_text = "I'm not sure how to help with that yet."

        # Also record local fallback interactions in durable history
        self.persistence.save_turn(
            user_text=query,
            assistant_text=fallback_text,
            session_id="default",
            source="Local Fallback"
        )

        return {
            "text": fallback_text,
            "source": "Local Fallback",
            "ai_available": False,
            "latency_ms": t_duration_ms
        }

    def clear_session(self, clear_persistence: bool = False):
        """Clears all conversation session history."""
        self.history.clear()
        self.last_interaction_timestamp = 0.0
        if clear_persistence:
            self.persistence.clear_all()
        logger.info(f"Conversation session memory cleared (clear_persistence={clear_persistence}).")
