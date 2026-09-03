import time
import logging
from config import config

logger = logging.getLogger("Jarvis.LLM")

class GeminiClient:
    """Interfaces with Google Gemini API to generate intelligent assistant responses.
    Incorporates conversational history, system prompts, error retries, and network timeout protection.
    Features natural offline fallback when API key is unconfigured or network is unavailable.
    """

    def __init__(self, api_key=None):
        self.api_key = api_key if api_key is not None else getattr(config, "gemini_api_key", "")
        self.model_name = "gemini-2.0-flash"
        self._model = None
        self._initialized = False

    def _init_client(self) -> bool:
        """Initializes the Google Generative AI client."""
        if self._initialized:
            return True

        if not self.api_key:
            logger.warning("[Developer Log] Gemini API key is not configured. Falling back to local offline response system.")
            return False

        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)

            system_instruction = (
                "You are Goliya, a sophisticated, helpful, and polite AI desktop assistant. "
                "You are communicating with the user via voice text-to-speech. "
                "Keep your answers brief, conversational, and completely ready to be read aloud. "
                "Do NOT use markdown headers, bold asterisks, bullet lists, or code block segments."
            )

            self._model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={
                    "temperature": getattr(config, "gemini_temperature", 0.7),
                    "max_output_tokens": getattr(config, "gemini_max_tokens", 150),
                },
                system_instruction=system_instruction
            )
            self._initialized = True
            logger.info(f"Gemini API model '{self.model_name}' configured successfully.")
            return True
        except Exception as e:
            logger.error(f"[Developer Log] Failed to initialize Gemini API client: {e}", exc_info=True)
            return False

    def generate_response(self, prompt: str, history_context: list = None) -> str:
        """Sends prompt to Gemini API, including prior conversation history.

        Args:
            prompt: The current user speech request.
            history_context: Structured chat history list of roles and parts.
        Returns:
            Natural spoken response string (never contains internal API errors).
        """
        if not self._init_client():
            return self._fallback_logic(prompt)

        max_retries = 3
        backoff = 1.0

        for attempt in range(max_retries):
            try:
                logger.info(f"Sending request to Gemini API (Attempt {attempt + 1}/{max_retries})...")
                t0 = time.time()
                chat = self._model.start_chat(history=history_context or [])
                response = chat.send_message(prompt)
                duration = time.time() - t0
                logger.info(f"Gemini API response generated in {duration:.2f}s.")
                return response.text.strip()
            except Exception as e:
                logger.warning(f"[Developer Log] Gemini API generation attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    logger.error("[Developer Log] All Gemini API generation attempts failed.", exc_info=True)
                    return self._fallback_logic(prompt)
                time.sleep(backoff)
                backoff *= 2.0

        return self._fallback_logic(prompt)

    def _fallback_logic(self, prompt: str) -> str:
        """Local response engine for basic requests when Gemini is unconfigured or offline."""
        clean = (prompt or "").lower().strip()

        # Greetings
        if any(g in clean for g in ["hello", "hi", "hey", "namaste", "good morning", "good evening", "good afternoon", "good night"]):
            return "Hello! How can I help you today?"

        # Identity queries
        if any(iq in clean for iq in ["who are you", "who made you", "what is your name"]):
            return "I'm Goliya, your personal desktop AI assistant."

        # Capabilities & Help
        if any(hq in clean for hq in ["what can you do", "help", "capabilities"]):
            return "Goliya can control applications, manage your computer, open files and websites, take screenshots, answer questions, and execute multiple commands."

        # Conversational basics
        if "how are you" in clean:
            return "I'm doing well and ready to assist you!"
        if "are you there" in clean:
            return "I'm here! Ready when you are."
        if any(t in clean for t in ["thank you", "thanks"]):
            return "You're very welcome!"
        if any(b in clean for b in ["goodbye", "bye", "see you"]):
            return "Goodbye! Have a great day."

        # General reasoning questions requiring external LLM when offline
        return "I'm currently operating in offline mode, so I can't provide my full AI response for that question right now."
