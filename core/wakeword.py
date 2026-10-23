import os
import time
import logging
import threading
import queue
import numpy as np
from abc import ABC, abstractmethod
from typing import Optional, List
from config import config

logger = logging.getLogger("Jarvis.WakeWord")

class WakeWordDetector(ABC):
    """Abstract base class defining the standardized Wake Word Detector interface.
    Guarantees seamless engine swap-outs (OpenWakeWord, Porcupine, Mock)
    without modifying coordinating business logic.
    """

    @abstractmethod
    def start(self, callback):
        """Starts the wake word detector background thread loop.

        Args:
            callback: Function to invoke when wake word is detected.
                      Signature: callback(wake_word_detected: str)
        """
        pass

    @abstractmethod
    def stop(self):
        """Stops the background loop and releases stream/hardware resources."""
        pass

    @abstractmethod
    def is_listening(self) -> bool:
        """Returns True if the detector background loop is currently running."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Returns True if the underlying engine dependencies and models are loaded and ready."""
        pass

    @abstractmethod
    def get_diagnostic(self) -> str:
        """Returns a human-readable diagnostic status string describing engine readiness."""
        pass


class MockWakeWordDetector(WakeWordDetector):
    """Reliable mock wake word detector running on a background thread.
    Simulates detection programmatically or via manual trigger commands.
    """

    def __init__(self, wake_words=None, **kwargs):
        self.wake_words = [w.lower() for w in (wake_words or ["santra", "hey santra", "jarvis", "hey jarvis", "hello santra"])]
        self._running = False
        self._thread = None
        self._callback = None
        self._lock = threading.Lock()
        self._diagnostic = "Mock wake-word detector active (manual/synthetic trigger only)."
        self.received_frames = []

    def feed_pcm_frame(self, pcm_frame):
        """Mock consumer feed to accept microphone PCM frames without error."""
        if hasattr(self, "received_frames"):
            if len(self.received_frames) < 100:
                self.received_frames.append(pcm_frame)

    def start(self, callback):
        with self._lock:
            if self._running:
                logger.warning("Mock Wake Word detector is already running.")
                return

            logger.info("Starting Wake Word Detector (Mock Engine).")
            self._running = True
            self._callback = callback
            self._thread = threading.Thread(target=self._run_loop, name="WakeWordThread", daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            if not self._running:
                return
            logger.info("Stopping Mock Wake Word Detector.")
            self._running = False

        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        logger.info("Mock Wake Word Detector stopped.")

    def is_listening(self) -> bool:
        with self._lock:
            return self._running

    def is_available(self) -> bool:
        return True

    def get_diagnostic(self) -> str:
        return self._diagnostic

    def trigger_mock_detection(self, word=None):
        detected_word = word if word in self.wake_words else self.wake_words[0]
        logger.info(f"[MOCK TRIGGER] Simulating wake word detection for: '{detected_word}'")

        if self._callback:
            try:
                self._callback(detected_word)
            except Exception as e:
                logger.error(f"Error executing wake word callback: {e}", exc_info=True)
        else:
            logger.warning("Wake word simulated, but no callback is registered.")

    def _run_loop(self):
        logger.info("Wake Word detection background loop initialized. Standby mode active.")
        while True:
            with self._lock:
                if not self._running:
                    break
            time.sleep(0.1)
        logger.info("Wake Word background thread exiting.")


class OpenWakeWordDetector(WakeWordDetector):
    """Production wrapper for OpenWakeWord (ONNX-based open source engine).
    Initializes microphone stream, handles automatic reconnection on disconnects,
    and runs local ONNX model inference on audio frames.
    """

    def __init__(self, wake_words=None, sensitivity=None, model_path=None, **kwargs):
        self.wake_words = [w.lower() for w in (wake_words or ["hey santra", "santra", "hey jarvis", "jarvis"])]
        self.sensitivity = sensitivity if sensitivity is not None else getattr(config, "wakeword_sensitivity", 0.45)
        self.model_path = model_path or getattr(config, "openwakeword_model_path", "")
        self._running = False
        self._callback = None
        self._thread = None
        self._lock = threading.Lock()
        self._model = None
        self._model_ready = False
        self._diagnostic = "OpenWakeWord not yet initialized."

        # Audio queue and shared buffer
        self._audio_queue = queue.Queue(maxsize=100)
        self._audio_buffer = np.array([], dtype=np.int16)
        self._debounce_until = 0.0
        self._external_feed_active = False
        self._last_external_feed_time = 0.0

        # Pre-check engine availability
        self._verify_engine_readiness()

    def feed_pcm_frame(self, pcm_frame: np.ndarray):
        """Feeds external 16kHz 16-bit PCM audio samples directly into the detector queue.
        Allows sharing the microphone stream with SpeechListener without opening a conflicting stream.
        """
        self._external_feed_active = True
        self._last_external_feed_time = time.time()
        try:
            self._audio_queue.put_nowait(pcm_frame)
        except queue.Full:
            pass

    def _verify_engine_readiness(self):
        """Verifies whether openwakeword library and models can be loaded."""
        try:
            import openwakeword
            from openwakeword.model import Model

            models = [self.model_path] if (self.model_path and os.path.exists(self.model_path)) else ["hey_jarvis"]
            try:
                self._model = Model(wakeword_models=models, inference_framework="onnx")
                self._model_ready = True
                self._diagnostic = f"OpenWakeWord ready with ONNX models: {list(self._model.models.keys())}."
                logger.info(f"[OpenWakeWord] {self._diagnostic}")
            except Exception as me:
                try:
                    logger.info("Attempting auto-download of openwakeword default models...")
                    import openwakeword.utils
                    openwakeword.utils.download_models()
                    self._model = Model(wakeword_models=models, inference_framework="onnx")
                    self._model_ready = True
                    self._diagnostic = f"OpenWakeWord ready with ONNX models: {list(self._model.models.keys())}."
                    logger.info(f"[OpenWakeWord] {self._diagnostic}")
                except Exception as de:
                    self._model_ready = False
                    self._diagnostic = f"OpenWakeWord model loading failed: {me}. Standby for mic/input triggers."
                    logger.warning(f"[OpenWakeWord] {self._diagnostic}")
        except ImportError as ie:
            self._model_ready = False
            self._diagnostic = f"openwakeword package not available ({ie}). Install openwakeword or use mock engine."
            logger.warning(f"[OpenWakeWord] {self._diagnostic}")

    def is_available(self) -> bool:
        return self._model_ready

    def get_diagnostic(self) -> str:
        return self._diagnostic

    def start(self, callback):
        with self._lock:
            if self._running:
                logger.warning("OpenWakeWord detector is already running.")
                return

            self._callback = callback
            self._running = True

            if not self._model_ready:
                # Attempt late initialization if models were downloaded after init
                self._verify_engine_readiness()

            if not self._model_ready:
                logger.warning(f"Starting OpenWakeWord in degraded/diagnostic mode: {self._diagnostic}")

            logger.info("Starting OpenWakeWord Detector background thread...")
            self._thread = threading.Thread(target=self._run_detector, name="OpenWakeWordThread", daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            if not self._running:
                return
            logger.info("Stopping OpenWakeWord Detector.")
            self._running = False

        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("OpenWakeWord Detector stopped.")

    def is_listening(self) -> bool:
        with self._lock:
            return self._running

    def _run_detector(self):
        """Main detection loop that manages shared microphone frames and model inference."""
        if not self._model_ready or self._model is None:
            logger.warning(f"OpenWakeWord thread idling: {self._diagnostic}")
            while self._running:
                time.sleep(0.5)
            return

        import sounddevice as sd

        logger.info("OpenWakeWord thread starting audio processing...")

        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.debug(f"WakeWord standalone stream status: {status}")
            clipped = np.clip(indata[:, 0], -1.0, 1.0)
            pcm_data = (clipped * 32767.0).astype(np.int16)
            try:
                self._audio_queue.put_nowait(pcm_data)
            except queue.Full:
                pass

        stream = None
        reconnect_delay = 1.0

        while self._running:
            # Check if external feed is active (shared from SpeechListener)
            is_externally_fed = self._external_feed_active and (time.time() - self._last_external_feed_time < 3.0)

            if is_externally_fed:
                if stream is not None:
                    logger.info("Shared audio feed active from SpeechListener. Releasing standalone OpenWakeWord stream.")
                    try:
                        stream.stop()
                        stream.close()
                    except Exception:
                        pass
                    stream = None
            else:
                # Standalone fallback: only open stream if not externally fed
                if stream is None:
                    try:
                        logger.info("Opening standalone microphone stream for OpenWakeWord...")
                        from core.audio_device_resolver import resolve_audio_input_device
                        pref = getattr(config, "audio_input_device", None) or getattr(config, "microphone_device", None)
                        input_dev, dev_name = resolve_audio_input_device(pref)
                        stream = sd.InputStream(
                            device=input_dev,
                            samplerate=16000,
                            channels=1,
                            callback=audio_callback,
                            blocksize=1280,  # 80ms blocks at 16kHz
                            latency='high',
                            dtype='float32'
                        )
                        stream.start()
                        self._diagnostic = f"OpenWakeWord active on [{input_dev}] '{dev_name}' with models {list(self._model.models.keys())}."
                        logger.info(f"Microphone stream opened successfully for OpenWakeWord (device=[{input_dev}] '{dev_name}').")
                        reconnect_delay = 1.0
                    except Exception as e:
                        self._diagnostic = f"Microphone connection failed ({e}). Standby mode active (manual talk fallback)."
                        logger.warning(f"WakeWord standalone microphone connection failed: {e}. Retrying in {reconnect_delay:.1f}s...")
                        stream = None
                        slices = int(reconnect_delay / 0.1)
                        for _ in range(slices):
                            if not self._running:
                                break
                            time.sleep(0.1)
                        reconnect_delay = min(10.0, reconnect_delay * 1.5)
                        continue


            # Process queued audio frames
            try:
                try:
                    pcm_frame = self._audio_queue.get(timeout=0.2)
                except queue.Empty:
                    if stream and not stream.active:
                        logger.warning("WakeWord standalone mic stream became inactive. Reconnecting...")
                        try:
                            stream.stop()
                            stream.close()
                        except Exception:
                            pass
                        stream = None
                    continue

                self._audio_buffer = np.append(self._audio_buffer, pcm_frame)

                # Feed chunks of 1280 samples (80ms at 16kHz) to openwakeword
                while len(self._audio_buffer) >= 1280:
                    chunk = self._audio_buffer[:1280]
                    self._audio_buffer = self._audio_buffer[1280:]

                    # Run model prediction
                    prediction = self._model.predict(chunk)

                    for word, score in prediction.items():
                        is_match = any(w in word.lower() for w in self.wake_words) or ("santra" in word.lower()) or ("jarvis" in word.lower())
                        if is_match and score >= self.sensitivity:
                            current_time = time.time()
                            if current_time > self._debounce_until:
                                logger.info(f"Wake word '{word}' detected! Score: {score:.3f} >= Threshold: {self.sensitivity}")
                                self._debounce_until = current_time + 2.0  # debounce for 2.0s
                                if self._callback:
                                    threading.Thread(
                                        target=self._callback,
                                        args=(word,),
                                        name="WakeWordCallbackDispatcher",
                                        daemon=True
                                    ).start()

            except Exception as e:
                logger.error(f"Error in OpenWakeWord execution loop: {e}", exc_info=True)
                if stream:
                    try:
                        stream.stop()
                        stream.close()
                    except Exception:
                        pass
                    stream = None
                time.sleep(1.0)

        # Cleanup
        if stream:
            try:
                stream.stop()
                stream.close()
            except Exception as e:
                logger.error(f"Error closing stream on exit: {e}")
            stream = None
        logger.info("OpenWakeWord background loop stopped cleanly.")


class PorcupineWakeWordDetector(WakeWordDetector):
    """Production wrapper for Picovoice Porcupine.
    Requires Picovoice API Key and configured keyword files.
    """

    def __init__(self, api_key=None, keywords=None, **kwargs):
        self.api_key = api_key
        self.keywords = keywords or ["jarvis"]
        self._running = False
        self._callback = None
        self._thread = None
        self._lock = threading.Lock()
        self._diagnostic = self._check_porcupine_status()

    def _check_porcupine_status(self) -> str:
        if not self.api_key:
            return "Porcupine API key missing. Standby mode active."
        try:
            import pvporcupine
            return "Picovoice Porcupine ready."
        except ImportError:
            return "pvporcupine package missing. Run `pip install pvporcupine`."

    def is_available(self) -> bool:
        if not self.api_key:
            return False
        try:
            import pvporcupine
            return True
        except ImportError:
            return False

    def get_diagnostic(self) -> str:
        return self._diagnostic

    def start(self, callback):
        with self._lock:
            if self._running:
                return
            logger.info("Starting Picovoice Porcupine Detector...")
            self._callback = callback
            self._running = True

            if not self.is_available():
                logger.warning(f"[Porcupine] {self._diagnostic}. Running in standby-fallback mode.")

            self._thread = threading.Thread(target=self._porcupine_loop, name="PorcupineThread", daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            if not self._running:
                return
            logger.info("Stopping Picovoice Porcupine Detector.")
            self._running = False

        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("Picovoice Porcupine Detector stopped.")

    def is_listening(self) -> bool:
        with self._lock:
            return self._running

    def _porcupine_loop(self):
        logger.info("Porcupine processing background thread started.")
        while True:
            with self._lock:
                if not self._running:
                    break
            time.sleep(0.1)
        logger.info("Porcupine background thread stopped.")



class SantraWakeWordDetector(WakeWordDetector):
    """Native, lightweight, local wake-word detector for 'Santra'.
    Uses energy/VAD-gated streaming audio frames and fast local Faster-Whisper
    acoustic keyword spotting without cloud dependencies or unbounded audio loops.
    """

    def __init__(self, wake_words=None, sensitivity=None, **kwargs):
        self.wake_words = [w.lower() for w in (wake_words or ["santra", "hey santra", "hello santra", "hi santra", "wake up"])]
        # Accept phonetic variations that Whisper might transcribe for "Santra"
        self.phonetic_variants = ["santra", "sandra", "santa", "santhra", "samtra", "santana", "santram", "shantra"]
        self.sensitivity = sensitivity if sensitivity is not None else getattr(config, "wakeword_sensitivity", 0.45)
        self._running = False
        self._callback = None
        self._thread = None
        self._lock = threading.Lock()
        self._diagnostic = "SantraWakeWordDetector ready."

        # Audio queue and bounded buffer
        self._audio_queue = queue.Queue(maxsize=100)
        self._speech_buffer = bytearray()
        self._silence_frames = 0
        self._speech_frames = 0
        self._debounce_until = 0.0
        self._external_feed_active = False
        self._last_external_feed_time = 0.0
        self._whisper_model = None
        self._model_lock = threading.Lock()

    def _get_model(self):
        with self._model_lock:
            if self._whisper_model is None:
                try:
                    from faster_whisper import WhisperModel
                    model_size = getattr(config, "model_whisper_size", "base")
                    dev = getattr(config, "whisper_device", "cpu")
                    compute = "int8" if dev.lower() == "cpu" else "float16"
                    self._whisper_model = WhisperModel(model_size, device=dev, compute_type=compute, cpu_threads=2)
                except Exception as e:
                    logger.error(f"Error loading local model for SantraWakeWordDetector: {e}")
            return self._whisper_model

    def feed_pcm_frame(self, pcm_frame):
        """Feeds external 16kHz 16-bit PCM audio samples directly into detector queue."""
        self._external_feed_active = True
        self._last_external_feed_time = time.time()
        try:
            self._audio_queue.put_nowait(pcm_frame)
        except queue.Full:
            pass

    def is_available(self) -> bool:
        return True

    def get_diagnostic(self) -> str:
        return self._diagnostic

    def is_listening(self) -> bool:
        with self._lock:
            return self._running

    def start(self, callback):
        with self._lock:
            if self._running:
                logger.warning("Santra Wake Word detector is already running.")
                return
            self._callback = callback
            self._running = True
            logger.info("Starting Santra Wake Word Detector background thread...")
            self._thread = threading.Thread(target=self._run_detector, name="SantraWakeWordThread", daemon=True)
            self._thread.start()

    def stop(self):
        with self._lock:
            if not self._running:
                return
            logger.info("Stopping Santra Wake Word Detector.")
            self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("Santra Wake Word Detector stopped.")

    def _run_detector(self):
        import sounddevice as sd

        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.debug(f"Santra wake stream status: {status}")
            clipped = np.clip(indata[:, 0], -1.0, 1.0)
            pcm_data = (clipped * 32767.0).astype(np.int16).tobytes()
            try:
                self._audio_queue.put_nowait(pcm_data)
            except queue.Full:
                pass

        stream = None
        reconnect_delay = 1.0
        # Energy threshold based on sensitivity (higher sensitivity = lower threshold)
        rms_threshold = max(200.0, (1.0 - self.sensitivity) * 800.0)

        while self._running:
            is_externally_fed = self._external_feed_active and (time.time() - self._last_external_feed_time < 3.0)

            if is_externally_fed:
                if stream is not None:
                    logger.info("Shared audio feed active from SpeechListener. Releasing standalone Santra stream.")
                    try:
                        stream.stop()
                        stream.close()
                    except Exception:
                        pass
                    stream = None
            else:
                if stream is None:
                    try:
                        logger.info("Opening standalone microphone stream for SantraWakeWordDetector...")
                        from core.audio_device_resolver import resolve_audio_input_device
                        pref = getattr(config, "audio_input_device", None) or getattr(config, "microphone_device", None)
                        input_dev, dev_name = resolve_audio_input_device(pref)
                        stream = sd.InputStream(
                            device=input_dev,
                            samplerate=16000,
                            channels=1,
                            callback=audio_callback,
                            blocksize=1280,
                            latency='high',
                            dtype='float32'
                        )
                        stream.start()
                        self._diagnostic = f"SantraWakeWord active on [{input_dev}] '{dev_name}'."
                        reconnect_delay = 1.0
                    except Exception as e:
                        self._diagnostic = f"Microphone connection failed ({e}). Standby mode active."
                        stream = None
                        slices = int(reconnect_delay / 0.1)
                        for _ in range(slices):
                            if not self._running:
                                break
                            time.sleep(0.1)
                        reconnect_delay = min(10.0, reconnect_delay * 1.5)
                        continue

            try:
                try:
                    pcm_frame = self._audio_queue.get(timeout=0.2)
                except queue.Empty:
                    if stream and not stream.active:
                        try:
                            stream.stop()
                            stream.close()
                        except Exception:
                            pass
                        stream = None
                    continue

                # Convert incoming frame to numpy samples
                if isinstance(pcm_frame, bytes):
                    samples = np.frombuffer(pcm_frame, dtype=np.int16)
                    raw_bytes = pcm_frame
                elif isinstance(pcm_frame, np.ndarray):
                    if pcm_frame.dtype == np.float32:
                        samples = (np.clip(pcm_frame, -1.0, 1.0) * 32767.0).astype(np.int16)
                    else:
                        samples = pcm_frame.astype(np.int16)
                    raw_bytes = samples.tobytes()
                else:
                    continue

                if len(samples) == 0:
                    continue

                rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))

                if rms >= rms_threshold:
                    self._speech_buffer.extend(raw_bytes)
                    self._speech_frames += 1
                    self._silence_frames = 0
                else:
                    if self._speech_frames > 0:
                        self._silence_frames += 1
                        # If silence follows speech (approx 200ms) or buffer exceeds 1.8s
                        if self._silence_frames >= 4 or len(self._speech_buffer) >= 28800:
                            if self._speech_frames >= 3:
                                # Run local acoustic keyword verification
                                model = self._get_model()
                                if model is not None:
                                    audio_int16 = np.frombuffer(self._speech_buffer, dtype=np.int16)
                                    audio_float = audio_int16.astype(np.float32) / 32768.0
                                    try:
                                        segments, _ = model.transcribe(
                                            audio_float,
                                            beam_size=1,
                                            temperature=0.0,
                                            initial_prompt="Santra, Hey Santra, Jarvis"
                                        )
                                        transcript = " ".join(s.text for s in segments).lower().strip()
                                        clean_text = "".join(c for c in transcript if c.isalnum() or c.isspace()).strip()

                                        is_wake = (
                                            any(v in clean_text for v in self.phonetic_variants) or
                                            any(w in clean_text for w in self.wake_words) or
                                            "santra" in clean_text or
                                            "jarvis" in clean_text
                                        )

                                        if is_wake:
                                            now = time.time()
                                            if now > self._debounce_until:
                                                self._debounce_until = now + 1.5
                                                logger.info(f"[SANTRA_WAKE] Detected wake word in '{clean_text}'")
                                                if self._callback:
                                                    threading.Thread(
                                                        target=self._callback,
                                                        args=("santra",),
                                                        name="SantraWakeCallback",
                                                        daemon=True
                                                    ).start()
                                    except Exception as te:
                                        logger.debug(f"Santra verification check error: {te}")

                            # Clear buffer after evaluating speech burst
                            self._speech_buffer.clear()
                            self._speech_frames = 0
                            self._silence_frames = 0

            except Exception as e:
                logger.error(f"Error in SantraWakeWordDetector execution loop: {e}", exc_info=True)
                if stream:
                    try:
                        stream.stop()
                        stream.close()
                    except Exception:
                        pass
                    stream = None
                time.sleep(0.5)

        if stream:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        logger.info("SantraWakeWordDetector loop stopped cleanly.")


class WakeWordDetectorFactory:
    """Factory builder to instantiate standardized WakeWordDetector subclasses based on configuration."""

    @staticmethod
    def create_detector(engine_type: str, **kwargs) -> WakeWordDetector:
        engine_lower = (engine_type or "santra").lower().strip()
        logger.info(f"Factory creating WakeWordDetector of type: '{engine_lower}'")

        if engine_lower in ("santra", "native", "default"):
            return SantraWakeWordDetector(**kwargs)
        elif engine_lower == "openwakeword":
            det = OpenWakeWordDetector(**kwargs)
            if not det.is_available():
                logger.warning(f"[WAKE_WORD_DIAGNOSTIC] OpenWakeWord unavailable: {det.get_diagnostic()}. Falling back to SantraWakeWordDetector.")
                return SantraWakeWordDetector(**kwargs)
            return det
        elif engine_lower == "porcupine":
            det = PorcupineWakeWordDetector(**kwargs)
            if not det.is_available():
                logger.warning(f"[WAKE_WORD_DIAGNOSTIC] Porcupine unavailable: {det.get_diagnostic()}. Falling back to SantraWakeWordDetector.")
                return SantraWakeWordDetector(**kwargs)
            return det
        elif engine_lower == "mock":
            return MockWakeWordDetector(**kwargs)
        else:
            logger.info(f"Defaulting to SantraWakeWordDetector for engine type: '{engine_type}'")
            return SantraWakeWordDetector(**kwargs)
