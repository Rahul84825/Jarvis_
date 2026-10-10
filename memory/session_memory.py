import time
import logging
from typing import List, Dict, Any, Optional
from memory.conversation_persistence import ConversationPersistence

logger = logging.getLogger("Jarvis.Memory")

class SessionMemory:
    """Conversation history store with SQLite persistence across application restarts.
    Holds the recent conversational turns in memory for fast access and formats them
    for LLM providers (including Gemini role/parts format), while durable SQLite storage
    persists dialogue across restarts.
    """

    def __init__(self, max_turns: int = 20, db_path: Optional[str] = None):
        self.max_turns = max_turns
        self.history: List[Dict[str, Any]] = []
        self.persistence = ConversationPersistence(db_path=db_path)

    def load_from_persistence(self, limit: Optional[int] = None):
        """Loads recent conversation interactions from SQLite storage into session memory."""
        if not self.persistence.is_enabled():
            return

        target_limit = limit or self.max_turns
        try:
            raw_messages = self.persistence.get_recent_turns(limit=target_limit)
            reconstructed = []
            i = 0
            while i < len(raw_messages):
                msg = raw_messages[i]
                if msg["role"] == "user":
                    user_text = msg["content"]
                    ts = msg["timestamp"]
                    asst_text = ""
                    if i + 1 < len(raw_messages) and raw_messages[i + 1]["role"] == "assistant":
                        asst_text = raw_messages[i + 1]["content"]
                        i += 1
                    reconstructed.append({
                        "user": user_text,
                        "assistant": asst_text,
                        "timestamp": ts
                    })
                elif msg["role"] == "assistant":
                    reconstructed.append({
                        "user": "",
                        "assistant": msg["content"],
                        "timestamp": msg["timestamp"]
                    })
                i += 1

            self.history = reconstructed[-target_limit:]
            if self.history:
                logger.info(f"Loaded {len(self.history)} conversation turns from durable SQLite storage.")
        except Exception as e:
            logger.error(f"Error restoring conversation turns from persistence: {e}")

    def add_interaction(self, user_text: str, assistant_text: str, session_id: str = "default", source: str = "assistant"):
        """Adds a new interaction turn to in-memory rolling memory and SQLite persistent storage."""
        interaction = {
            "user": user_text,
            "assistant": assistant_text,
            "timestamp": time.time()
        }
        self.history.append(interaction)
        logger.info(f"Added conversation turn to session memory. History length: {len(self.history)}")

        # Persist to durable SQLite database
        self.persistence.save_turn(
            user_text=user_text,
            assistant_text=assistant_text,
            session_id=session_id,
            source=source
        )

        # Trim in-memory history if it exceeds the maximum turns allowed
        if len(self.history) > self.max_turns:
            trimmed = self.history.pop(0)
            logger.debug(f"Trimmed oldest in-memory conversation turn: '{trimmed.get('user', '')}'")

    def get_gemini_history(self) -> list:
        """Formats the stored conversation history into the structured role/parts format
        required by the Google Gemini API.
        """
        gemini_history = []
        for turn in self.history:
            if turn.get("user"):
                gemini_history.append({
                    "role": "user",
                    "parts": [turn["user"]]
                })
            if turn.get("assistant"):
                gemini_history.append({
                    "role": "model",
                    "parts": [turn["assistant"]]
                })
        return gemini_history

    def search_history(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Searches past conversation history for relevant exchanges."""
        return self.persistence.search_relevant_history(query, limit=limit)

    def get_context_summary(self, max_turns: int = 4) -> str:
        """Returns a concise summary of relevant recent conversation turns for context injection."""
        return self.persistence.get_context_summary(max_turns=max_turns)

    def clear(self, clear_persistence: bool = False):
        """Clears in-memory session history and optionally durable database history."""
        self.history.clear()
        if clear_persistence:
            self.persistence.clear_all()
        logger.info(f"Session memory cleared (clear_persistence={clear_persistence}).")
