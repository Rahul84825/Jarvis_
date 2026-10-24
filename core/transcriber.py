import math
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
        self.device = device or getattr(config, "whisper_device", "auto")
        self.beam_size = beam_size if beam_size is not None else getattr(config, "whisper_beam_size", 1)
        self.cpu_threads = cpu_threads or getattr(config, "whisper_threads", 4)
        self._model = None
        self.status = "STT_UNINITIALIZED"
        self._init_lock = threading.Lock()
        self._ready_event = threading.Event()
        self._init_thread = None
        self.actual_device = "cpu"
        self.actual_compute_type = "int8"
        self._last_used_time = time.time()
        self.last_metadata = {
            "text": "",
            "confidence": 0.0,
            "language": "N/A",
            "language_probability": 0.0,
            "duration": 0.0
        }

    def touch_activity(self):
        """Updates last activity timestamp for idle unload tracking."""
        self._last_used_time = time.time()

    def is_loaded(self) -> bool:
        """Returns True if the Whisper model is currently loaded in memory."""
        with self._init_lock:
            return self._model is not None

    def unload_model(self) -> bool:
        """Safely unloads the Whisper model from memory and reclaims RAM/VRAM."""
        with self._init_lock:
            if self._model is None:
                return False
            logger.info(f"[STT] Unloading Faster-Whisper model '{self.model_size}' to reclaim resources.")
            try:
                del self._model
            except Exception:
                pass
            self._model = None
            self.status = "STT_UNINITIALIZED"
            self._ready_event.clear()
            import gc
            gc.collect()
            try:
                from core.system_resource_manager import system_resource_manager
                system_resource_manager.update_task_context(
                    task="Idle (Model Unloaded)",
                    model="None",
                    device=f"{self.actual_device.upper()} (unloaded)"
                )
            except Exception:
                pass
            logger.info("[STT] Faster-Whisper model unloaded and memory collected.")
            return True

    def check_idle_unload(self, timeout_sec: float = 600.0) -> bool:
        """Unloads model if idle beyond the specified timeout in seconds."""
        if not self.is_loaded() or timeout_sec <= 0:
            return False
        if (time.time() - self._last_used_time) > timeout_sec:
            logger.info(f"[STT_IDLE_POLICY] Model idle for {time.time() - self._last_used_time:.1f}s > {timeout_sec}s. Unloading.")
            return self.unload_model()
        return False

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

    def _determine_target_device(self):
        """Determines target execution device and compute type based on capability audit and user config."""
        dev = self.device.lower().strip()
        from core.system_resource_manager import system_resource_manager
        caps = system_resource_manager.capabilities

        if dev == "auto":
            if caps.get("ctranslate2_cuda_verified", False):
                return "cuda", "float16"
            return "cpu", "int8"
        elif dev == "cuda":
            return "cuda", "float16"
        else:
            return "cpu", "int8"

    def _load_model(self):
        """Loads the Whisper model into memory with safe hardware detection and CPU fallback."""
        with self._init_lock:
            if self._model is not None:
                self.status = "STT_READY"
                self._ready_event.set()
                logger.debug("[WHISPER_MODEL_REUSED] Reusing persistent Faster Whisper model instance.")
                return

            self.status = "STT_INITIALIZING"
            target_device, target_compute = self._determine_target_device()
            logger.info(f"[STT] Loading Whisper model '{self.model_size}' (requested: '{self.device}', target: '{target_device}/{target_compute}')...")
            t0 = time.time()

            from faster_whisper import WhisperModel

            def _try_instantiate(device_name, compute_name):
                kwargs = {
                    "device": device_name,
                    "compute_type": compute_name
                }
                if device_name == "cpu" and self.cpu_threads is not None:
                    kwargs["cpu_threads"] = self.cpu_threads

                # Fast offline check: try local_files_only first to avoid huggingface network delay
                try:
                    return WhisperModel(self.model_size, local_files_only=True, **kwargs)
                except (FileNotFoundError, OSError):
                    logger.info(f"[STT] Local cache miss for '{self.model_size}'. Fetching model...")
                    return WhisperModel(self.model_size, local_files_only=False, **kwargs)

            try:
                self._model = _try_instantiate(target_device, target_compute)
                self.actual_device = target_device
                self.actual_compute_type = target_compute
            except Exception as target_err:
                if target_device != "cpu":
                    logger.warning(
                        f"[STT_FALLBACK] Failed initializing Whisper on '{target_device}': {target_err}. "
                        f"Falling back safely to CPU (int8)."
                    )
                    try:
                        self._model = _try_instantiate("cpu", "int8")
                        self.actual_device = "cpu"
                        self.actual_compute_type = "int8"
                    except Exception as cpu_err:
                        self.status = "STT_FAILED"
                        self._ready_event.set()
                        logger.error(f"[STT] Whisper CPU fallback initialization failed: {cpu_err}", exc_info=True)
                        raise cpu_err
                else:
                    self.status = "STT_FAILED"
                    self._ready_event.set()
                    logger.error(f"[STT] Whisper initialization failed: {target_err}", exc_info=True)
                    raise target_err

            elapsed_ms = int((time.time() - t0) * 1000)
            self.status = "STT_READY"
            self.touch_activity()
            self._ready_event.set()
            logger.info(f"[STT] Whisper model ready in {elapsed_ms} ms on {self.actual_device.upper()} ({self.actual_compute_type})")

            try:
                from core.system_resource_manager import system_resource_manager
                system_resource_manager.update_task_context(
                    task="Ready / Standby",
                    model=f"faster-whisper-{self.model_size}",
                    device=f"{self.actual_device.upper()} ({self.actual_compute_type})"
                )
            except Exception:
                pass

    def transcribe(self, audio_file_path: str, beam_size: int = None) -> str:
        """Transcribes the given audio file and returns the text output.
        
        Args:
            audio_file_path: Path to the WAV audio file.
            beam_size: Optional beam size override.
        Returns:
            The transcribed text string.
        """
        from core.transcript_validator import transcript_validator
        try:
            from core.tracing import tracer
            trace = tracer.get_current_trace()
            if trace:
                trace.record_timestamp("whisper_ready", time.time())
                trace.record_timestamp("stt_start", time.time())
        except Exception:
            trace = None

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
        self.touch_activity()
        
        try:
            from core.system_resource_manager import system_resource_manager
            system_resource_manager.update_task_context(
                task="Transcribing Speech",
                model=f"faster-whisper-{self.model_size}",
                device=f"{self.actual_device.upper()} ({self.actual_compute_type})"
            )
        except Exception:
            pass
        
        try:
            from core.os.domain_manager import domain_manager
            domain_vocab = domain_manager.get_vocabulary_prompt()
            initial_prompt = (
                f"Santra, Hey Santra, Samtra, Suntra, San-tra, Jarvis, open VS Code, YouTube, Chrome, "
                f"{domain_vocab}, Spotify, Notepad, Calculator, lock computer, take a screenshot, calculate, "
                f"system status, shutdown, restart, volume up, volume down, mute, unmute, minimize, maximize, "
                f"what time is it, what is the date, search google, play music."
            )
            hotwords = domain_manager.get_hotwords_string()
            
            def _execute_inference():
                kwargs = {
                    "beam_size": effective_beam,
                    "best_of": effective_beam,
                    "temperature": 0.0,
                    "language": "en",
                    "initial_prompt": initial_prompt,
                    "condition_on_previous_text": False,
                    "vad_filter": False
                }
                if hotwords:
                    kwargs["hotwords"] = hotwords
                try:
                    segs, inf = self._model.transcribe(str(path), **kwargs)
                except TypeError:
                    kwargs.pop("hotwords", None)
                    segs, inf = self._model.transcribe(str(path), **kwargs)
                return list(segs), inf

            try:
                segment_list, info = _execute_inference()
            except Exception as infer_err:
                if self.actual_device != "cpu":
                    logger.warning(
                        f"[STT_RUNTIME_FALLBACK] Inference failed on {self.actual_device}: {infer_err}. "
                        f"Re-initializing model on CPU (int8)..."
                    )
                    from faster_whisper import WhisperModel
                    self._model = WhisperModel(
                        self.model_size,
                        device="cpu",
                        compute_type="int8",
                        cpu_threads=self.cpu_threads,
                        local_files_only=True
                    )
                    self.actual_device = "cpu"
                    self.actual_compute_type = "int8"
                    segment_list, info = _execute_inference()
                else:
                    raise infer_err

            raw_transcription = " ".join([segment.text for segment in segment_list]).strip()
            
            # Log raw Whisper output for every command
            logger.info(f"[RAW WHISPER OUTPUT]: '{raw_transcription}'")
            logger.info(f"[DOMAIN_TRACE][STT] raw_transcript='{raw_transcription}', confidence=N/A, duration={info.duration:.2f}s")
            
            # Early empty transcript check
            if not raw_transcription:
                duration = time.time() - t0
                logger.info(f"[EMPTY_TRANSCRIPT] Silence or inaudible audio received ({duration:.2f}s).")
                return ""

            # Post-process transcription to correct accent and phonetic errors
            import re
            from core.pronunciation_manager import pronunciation_manager
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

            # Apply contextual assistant-addressing normalization (e.g., 'Samtra, open Chrome' -> 'Santra, open Chrome')
            # while preserving payload commands and avoiding corrupting ordinary words
            transcription, pron_meta = pronunciation_manager.contextual_normalize(transcription)
            if pron_meta.get("is_addressed"):
                logger.info(f"[PRONUNCIATION_NORMALIZED] Assistant address normalized to '{pron_meta.get('canonical')}' from '{pron_meta.get('original')}'")
            
            # Calculate confidence score from segment average logprobs
            if segment_list:
                avg_logprob = sum(seg.avg_logprob for seg in segment_list) / len(segment_list)
                confidence = math.exp(avg_logprob)
            else:
                confidence = 0.0

            # Transcript Quality Control & Hallucination Filter
            val_res = transcript_validator.validate(transcription, confidence=confidence, audio_duration=info.duration)
            if not val_res.is_valid or val_res.status in ["EMPTY", "TOO_SHORT"]:
                logger.info(f"[TRANSCRIPT_FILTERED] Discarding invalid transcript: status={val_res.status}")
                return ""

            if val_res.repetition_detected:
                logger.info(f"[TRANSCRIPT_VALIDATED] Repetitions compressed ({val_res.original_repetition_count}x -> '{val_res.cleaned_text}')")
                transcription = val_res.cleaned_text

            duration = time.time() - t0
            logger.info(f"Transcription complete in {duration:.2f}s. Result: '{transcription}'")
            logger.info(f"Audio info: Language='{info.language}' (Prob={info.language_probability:.2f}), Duration={info.duration:.2f}s")
            
            self.last_metadata = {
                "text": transcription,
                "raw": raw_transcription,
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
        finally:
            try:
                from core.system_resource_manager import system_resource_manager
                system_resource_manager.update_task_context(
                    task="Ready / Standby",
                    model=f"faster-whisper-{self.model_size}",
                    device=f"{self.actual_device.upper()} ({self.actual_compute_type})"
                )
            except Exception:
                pass
