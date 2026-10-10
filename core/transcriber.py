import time
import logging
import threading
from pathlib import Path
from config import config

logger = logging.getLogger("Jarvis.Transcriber")

class SpeechTranscriber:
    """Handles speech-to-text (STT) transcription using the Faster Whisper backend.
    Loads models lazily or via background pre-warming and runs local inference on WAV audio files.
    """
    
    def __init__(self, model_size=None, device=None, beam_size=None, cpu_threads=None):
        self.model_size = model_size or config.whisper_model_size
        self.device = device or config.whisper_device
        self.beam_size = beam_size if beam_size is not None else getattr(config, "whisper_beam_size", 1)
        self.cpu_threads = cpu_threads
        self._model = None
        self.status = "STT_UNINITIALIZED"
        self._init_lock = threading.Lock()
        self._ready_event = threading.Event()
        self._init_thread = None
        self.last_metadata = {
            "text": "",
            "confidence": 0.0,
            "language": "N/A",
            "language_probability": 0.0,
            "duration": 0.0
        }

    def preload_in_background(self):
        """Asynchronously pre-warms the Whisper model in a daemon thread."""
        with self._init_lock:
            if self._model is not None or self.status == "STT_READY":
                return
            if self.status == "STT_INITIALIZING":
                return
            self.status = "STT_INITIALIZING"
            self._ready_event.clear()
            self._init_thread = threading.Thread(
                target=self._load_model_worker,
                name="STT-Prewarm",
                daemon=True
            )
            self._init_thread.start()

    def _load_model_worker(self):
        """Worker thread entry point for model loading."""
        try:
            self._load_model()
        except Exception:
            # _load_model already logs failures and sets status to STT_FAILED
            pass

    def _load_model(self):
        """Loads the Whisper model into memory if not already loaded."""
        with self._init_lock:
            if self._model is not None:
                self.status = "STT_READY"
                self._ready_event.set()
                return

            self.status = "STT_INITIALIZING"
            logger.info(f"[STT] Loading Whisper model '{self.model_size}' on device '{self.device}'...")
            t0 = time.time()
            try:
                from faster_whisper import WhisperModel
                
                # Use int8 computation for CPU execution efficiency
                compute_type = "int8" if self.device.lower() == "cpu" else "float16"
                
                kwargs = {
                    "device": self.device,
                    "compute_type": compute_type
                }
                if self.cpu_threads is not None:
                    kwargs["cpu_threads"] = self.cpu_threads

                self._model = WhisperModel(self.model_size, **kwargs)
                elapsed_ms = int((time.time() - t0) * 1000)
                self.status = "STT_READY"
                self._ready_event.set()
                logger.info(f"[STT] Whisper model ready in {elapsed_ms} ms")
            except Exception as e:
                self.status = "STT_FAILED"
                self._ready_event.set()
                logger.error(f"[STT] Whisper initialization failed: {e}", exc_info=True)
                raise e

    def transcribe(self, audio_file_path: str, beam_size: int = None) -> str:
        """Transcribes the given audio file and returns the text output.
        
        Args:
            audio_file_path: Path to the WAV audio file.
            beam_size: Optional beam size override.
        Returns:
            The transcribed text string.
        """
        import math
        from core.tracing import tracer
        trace = tracer.get_current_trace()
        if trace:
            trace.record_timestamp("whisper_ready", time.time())
            trace.record_timestamp("stt_start", time.time())

        self.last_metadata = {
            "text": "",
            "confidence": 0.0,
            "language": "N/A",
            "language_probability": 0.0,
            "duration": 0.0
        }
        
        # If pre-warming in background, wait gracefully
        if self.status == "STT_INITIALIZING" and self._init_thread and self._init_thread.is_alive():
            logger.info("[STT] Waiting for background Whisper model initialization to complete...")
            self._ready_event.wait(timeout=30.0)

        self._load_model()
        
        path = Path(audio_file_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file_path}")

        effective_beam = beam_size if beam_size is not None else self.beam_size
        logger.info(f"Transcribing audio file: {audio_file_path} (beam_size={effective_beam})")
        t0 = time.time()
        
        try:
            # transcribe returns generator of (segments, info)
            initial_prompt = "Jarvis, open VS Code, YouTube, Chrome, Spotify, Notepad, Calculator, lock computer, take a screenshot, calculate, system status, shutdown, restart, volume up, volume down, mute, unmute, minimize, maximize, what time is it, what is the date, search google, play music."
            segments, info = self._model.transcribe(
                str(path),
                beam_size=effective_beam,
                best_of=effective_beam,
                temperature=0.0,
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
            
            if trace:
                trace.record_timestamp("stt_end", time.time())
                trace.recognized_text = transcription

            return transcription
            
        except Exception as e:
            if trace:
                trace.record_timestamp("stt_end", time.time())
                trace.status = "STT_ERROR"
            logger.error(f"Error during audio transcription: {e}", exc_info=True)
            raise e
