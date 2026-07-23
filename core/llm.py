import time
import logging
from config import config

logger = logging.getLogger("Jarvis.LLM")

class GeminiClient:
    """Interfaces with Google Gemini API to generate intelligent assistant responses.
    Incorporates conversational history, system prompts, error retries, and network timeout protection.
    """
    
    def __init__(self, api_key=None):
        self.api_key = api_key or config.gemini_api_key
        self.model_name = "gemini-1.5-flash"
        self._model = None
        self._initialized = False

    def _init_client(self) -> bool:
        """Initializes the Google Generative AI client."""
        if self._initialized:
            return True
            
        if not self.api_key:
            logger.warning("Gemini API key is not configured. LLM calls will fail or run in mock fallback mode.")
            return False
            
        try:
            import google.generativeai as genai
            genai.configure(api_key=self.api_key)
            
            # Setup model with system instructions optimized for natural voice output
            system_instruction = (
                "You are Jarvis, a sophisticated, helpful, and polite AI desktop assistant. "
                "You are communicating with the user via voice text-to-speech. "
                "Keep your answers brief, conversational, and completely ready to be read aloud. "
                "Do NOT use markdown headers, bold asterisks, bullet lists, or code block segments, "
                "as they sound awkward when read by a voice synthesizer."
            )
            
            self._model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={
                    "temperature": config.gemini_temperature,
                    "max_output_tokens": config.gemini_max_tokens,
                },
                system_instruction=system_instruction
            )
            self._initialized = True
            logger.info(f"Gemini API model '{self.model_name}' configured successfully.")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Gemini API client: {e}", exc_info=True)
            return False

    def generate_response(self, prompt: str, history_context: list = None) -> str:
        """Sends prompt to Gemini API, including prior conversation history.
        Includes retry handling with exponential backoff.
        
        Args:
            prompt: The current user speech request.
            history_context: Structured chat history list of roles and parts.
        Returns:
            The textual assistant response.
        """
        # If API key is empty, run in fallback mock reasoning mode
        if not self._init_client():
            logger.warning("Gemini API client not initialized. Falling back to offline assistant logic.")
            return self._fallback_logic(prompt)
            
        import google.generativeai as genai
        
        # Implement retry loop
        max_retries = 3
        backoff = 1.0
        
        for attempt in range(max_retries):
            try:
                logger.info(f"Sending request to Gemini API (Attempt {attempt + 1}/{max_retries})...")
                t0 = time.time()
                
                # Start chat with loaded history
                chat = self._model.start_chat(history=history_context or [])
                
                # Execute generation request
                response = chat.send_message(prompt)
                
                duration = time.time() - t0
                logger.info(f"Gemini API response generated in {duration:.2f}s.")
                
                return response.text.strip()
                
            except Exception as e:
                logger.warning(f"Gemini API generation attempt {attempt + 1} failed: {e}")
                if attempt == max_retries - 1:
                    logger.error("All Gemini API generation attempts failed.", exc_info=True)
                    return "I'm having trouble connecting to my cognitive services. Please check my API key or network connection."
                time.sleep(backoff)
                backoff *= 2.0

    def _fallback_logic(self, prompt: str) -> str:
        """Fallback local response handler when Gemini API key is missing."""
        clean = prompt.lower().strip()
        if "hello" in clean or "hi" in clean:
            return "Hello. I am operating in offline fallback mode because my Gemini API key is not configured. How else can I help?"
        return f"I received your query: '{prompt}'. However, my Gemini API key is missing. Please configure it in config.py to enable my full reasoning capabilities."
