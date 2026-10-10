import logging
from core.ai.agent_brain import agent_brain

logger = logging.getLogger("Jarvis.Brain")

class Brain:
    """Jarvis Central Brain Reasoning Subsystem.
    Powered by ReAct AgentBrain with tool calling, memory retrieval, and multi-turn reasoning.
    """
    def __init__(self, executor=None):
        logger.info("Initializing Jarvis Brain Autonomous Reasoning System.")
        self.agent = agent_brain
        if executor:
            self.agent.executor = executor

    def process_text(self, text: str, history: list = None) -> str:
        """Processes user input text, runs reasoning & tool execution, and returns spoken response."""
        logger.info(f"Brain received input: '{text}'")
        if not text or not text.strip():
            return "I heard silence. Please speak again if you need assistance."

        res = self.agent.reason_and_execute(text, conversation_history=history)
        return res.get("text", "Task completed, sir.")

    def shutdown(self):
        logger.info("Jarvis Brain shutting down.")

