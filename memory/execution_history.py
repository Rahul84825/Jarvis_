import time
import logging

logger = logging.getLogger("Jarvis.ExecutionHistory")

class ExecutionHistory:
    """In-memory tracker for recently executed OS controls and actions.
    Retains the last 100 operations.
    """
    
    def __init__(self, limit=100):
        self.limit = limit
        self.history = []

    def add_action(self, command: str, intent: str, result: str, success: bool):
        """Records a new execution action into history, maintaining the size limit."""
        record = {
            "timestamp": time.time(),
            "command": command,
            "intent": intent,
            "result": result,
            "success": success
        }
        self.history.append(record)
        logger.info(f"Recorded action history. Count: {len(self.history)}")
        
        # Trim history if it exceeds the limit
        if len(self.history) > self.limit:
            self.history.pop(0)

    def get_history(self) -> list:
        """Returns the chronological list of recent execution records."""
        return list(self.history)

    def clear(self):
        """Clears all execution history records."""
        self.history.clear()
        logger.info("Execution history cleared.")
