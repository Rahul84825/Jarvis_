import time
import logging

logger = logging.getLogger("Jarvis.Memory")

class SessionMemory:
    """In-memory conversation history store.
    Holds the last 20 conversational turns (user requests and Jarvis responses)
    and formats them for direct inclusion as context in Gemini API requests.
    """
    
    def __init__(self, max_turns=20):
        self.max_turns = max_turns
        # Store items as dictionaries: {"user": text, "assistant": text, "timestamp": float}
        self.history = []

    def add_interaction(self, user_text: str, assistant_text: str):
        """Adds a new interaction turn and trims history to maintain the limit."""
        interaction = {
            "user": user_text,
            "assistant": assistant_text,
            "timestamp": time.time()
        }
        self.history.append(interaction)
        logger.info(f"Added conversation turn to memory. History length: {len(self.history)}")
        
        # Trim history if it exceeds the maximum turns allowed
        if len(self.history) > self.max_turns:
            trimmed = self.history.pop(0)
            logger.debug(f"Trimmed oldest conversation turn from memory: '{trimmed['user']}'")

    def get_gemini_history(self) -> list:
        """Formats the stored conversation history into the structured role/parts format
        required by the Google Gemini API.
        """
        gemini_history = []
        for turn in self.history:
            gemini_history.append({
                "role": "user",
                "parts": [turn["user"]]
            })
            gemini_history.append({
                "role": "model",
                "parts": [turn["assistant"]]
            })
        return gemini_history

    def clear(self):
        """Clears all conversation history from memory."""
        self.history.clear()
        logger.info("Session memory cleared.")
