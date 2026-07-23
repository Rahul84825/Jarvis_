import logging

logger = logging.getLogger("Jarvis.Brain")

class Brain:
    def __init__(self):
        logger.info("Initializing Jarvis Brain Reasoning System (Mock).")

    def process_text(self, text: str) -> str:
        """Processes user input text and returns assistant's response.
        In this foundation version, reasoning is simulated with basic rules.
        """
        logger.info(f"Brain received input: '{text}'")
        clean_text = text.lower().strip()

        if not clean_text:
            return "I heard silence. Please speak again if you need assistance."

        if any(word in clean_text for word in ["hello", "hi", "hey"]):
            return "Hello! I am Jarvis. System online. How may I assist you today?"
        
        if "who are you" in clean_text:
            return "I am Jarvis, your intelligent always-running personal assistant."

        if "system status" in clean_text or "status" in clean_text:
            return "All core modules are active. Wake word detection is operational, and clap detector is online."

        # Echo the phrase for verification testing
        return f"I processed your speech: '{text}'. This is a mock response from the Jarvis reasoning foundation."

    def shutdown(self):
        logger.info("Jarvis Brain shutting down.")
