import time
import logging
from pathlib import Path
from config import config

logger = logging.getLogger("Jarvis.Transcriber")

class SpeechTranscriber:
    """Handles speech-to-text (STT) transcription using the Faster Whisper backend.
    Loads models lazily and runs local inference on WAV audio files.
    """
    
    def __init__(self, model_size=None, device=None):
        self.model_size = model_size or config.whisper_model_size
        self.device = device or config.whisper_device
        self._model = None
        self.last_metadata = {
            "text": "",
            "confidence": 0.0,
            "language": "N/A",
            "language_probability": 0.0,
            "duration": 0.0
        }

    def _load_model(self):
        """Loads the Whisper model into memory if not already loaded."""
        if self._model is not None:
            return

        logger.info(f"Loading Faster Whisper model '{self.model_size}' on device '{self.device}'...")
        t0 = time.time()
        try:
            from faster_whisper import WhisperModel
            
            # Use int8 computation for CPU execution efficiency
            compute_type = "int8" if self.device.lower() == "cpu" else "float16"
            
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type=compute_type
            )
            logger.info(f"Faster Whisper model loaded successfully in {time.time() - t0:.2f}s.")
        except Exception as e:
            logger.error(f"Failed to load Faster Whisper model: {e}", exc_info=True)
            raise e

    def transcribe(self, audio_file_path: str) -> str:
        """Transcribes the given audio file and returns the text output.
        
        Args:
            audio_file_path: Path to the WAV audio file.
        Returns:
            The transcribed text string.
        """
        import math
        self.last_metadata = {
            "text": "",
            "confidence": 0.0,
            "language": "N/A",
            "language_probability": 0.0,
            "duration": 0.0
        }
        self._load_model()
        
        path = Path(audio_file_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file_path}")

        logger.info(f"Transcribing audio file: {audio_file_path}")
        t0 = time.time()
        
        try:
            # transcribe returns generator of (segments, info)
            initial_prompt = "Jarvis, open VS Code, YouTube, Chrome, Spotify, Notepad, Calculator, lock computer, take a screenshot, calculate, system status, shutdown, restart, volume up, volume down, mute, unmute, minimize, maximize, what time is it, what is the date, search google, play music."
            segments, info = self._model.transcribe(
                str(path),
                beam_size=5,
                language="en",
                initial_prompt=initial_prompt,
                condition_on_previous_text=False,
                vad_filter=False  # SpeechListener already handles VAD segmenting; vad_filter=False prevents Silero from discarding speech
            )
            
            # Consume generator to collect all segments
            segment_list = list(segments)
            raw_transcription = " ".join([segment.text for segment in segment_list]).strip()
            
            # Log raw Whisper output for every command
            logger.info(f"[RAW WHISPER OUTPUT]: '{raw_transcription}'")
            
            # Post-process transcription to correct accent and phonetic errors
            import re
            transcription = raw_transcription
            replacements = {
                r"\bversus\s*code\b": "VS Code",
                r"\bverse\s+is\s+good\b": "VS Code",
                r"\bvee\s*es\s*code\b": "VS Code",
                r"\bviscode\b": "VS Code",
                r"\bvi\s*es\s*code\b": "VS Code",
                r"\blog\s*computer\b": "lock computer",
                r"\blogcomputer\b": "lock computer",
                r"\bscreen\s+shot\b": "screenshot",
                r"\bdown\s+loads\b": "downloads",
                r"\byou\s+tube\b": "YouTube",
                r"\bu\s+tube\b": "YouTube",
                r"\bnot\s+pad\b": "notepad",
                r"\bshut\s+down\b": "shutdown",
                r"\bclothe\b": "close",
                r"\bclothes\b": "close",
                r"\bkrone\b": "chrome",
                r"\bcrome\b": "chrome",
                r"\bgit\s+hub\b": "GitHub",
                r"\bget\s+hub\b": "GitHub",
                r"\bjarves\b": "Jarvis",
                r"\bjervis\b": "Jarvis",
                r"\bcalcilator\b": "calculator",
                r"\bkalculator\b": "calculator",
                r"\banti\s+gravity\b": "Antigravity",
                r"\bwell\s+meds\b": "WellMeds",
                r"\btest\s+speach\b": "test speech",
                r"\bspeech\s+test\b": "test speech",
                r"\bmic\s+test\b": "test microphone",
            }
            for pattern, repl in replacements.items():
                transcription = re.sub(pattern, repl, transcription, flags=re.IGNORECASE)
            
            duration = time.time() - t0
            logger.info(f"Transcription complete in {duration:.2f}s. Result: '{transcription}'")
            logger.info(f"Audio info: Language='{info.language}' (Prob={info.language_probability:.2f}), Duration={info.duration:.2f}s")
            
            # Calculate confidence score from segment average logprobs
            if segment_list:
                avg_logprob = sum(seg.avg_logprob for seg in segment_list) / len(segment_list)
                confidence = math.exp(avg_logprob)
            else:
                confidence = 0.0
                
            self.last_metadata = {
                "text": transcription,
                "confidence": confidence,
                "language": info.language,
                "language_probability": info.language_probability,
                "duration": info.duration
            }
            
            return transcription
            
        except Exception as e:
            logger.error(f"Error during audio transcription: {e}", exc_info=True)
            raise e
