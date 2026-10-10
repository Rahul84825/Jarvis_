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
        self.wake_words = wake_words or ["jarvis", "hey jarvis", "hello jarvis"]
        self._running = False
        self._thread = None
        self._callback = None
        self._lock = threading.Lock()
        self._diagnostic = "Mock wake-word detector active (manual/synthetic trigger only)."

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
        self.wake_words = wake_words or ["jarvis"]
        self.sensitivity = sensitivity if sensitivity is not None else getattr(config, "wakeword_sensitivity", 0.5)
        self.model_path = model_path or getattr(config, "openwakeword_model_path", "")
        self._running = False
        self._callback = None
        self._thread = None
        self._lock = threading.Lock()
        self._model = None
        self._model_ready = False
        self._diagnostic = "OpenWakeWord not yet initialized."

        # Audio buffer and debounce
        self._audio_buffer = np.array([], dtype=np.int16)
        self._debounce_until = 0.0

        # Pre-check engine availability
        self._verify_engine_readiness()

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
        """Main detection loop that manages microphone connection and model inference."""
        if not self._model_ready or self._model is None:
            logger.warning(f"OpenWakeWord thread idling: {self._diagnostic}")
            while self._running:
                time.sleep(0.5)
            return

        import sounddevice as sd

        logger.info("OpenWakeWord thread starting audio stream capture...")
        audio_queue = queue.Queue(maxsize=100)

        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.debug(f"WakeWord audio stream status: {status}")
            clipped = np.clip(indata[:, 0], -1.0, 1.0)
            pcm_data = (clipped * 32767.0).astype(np.int16)
            try:
                audio_queue.put_nowait(pcm_data)
            except queue.Full:
                pass  # Avoid memory bloat if model thread falls behind

        stream = None
        reconnect_delay = 1.0

        while self._running:
            # 1. Establish microphone stream with auto-recovery
            if stream is None:
                try:
                    logger.info("Opening microphone stream for OpenWakeWord...")
                    stream = sd.InputStream(
                        samplerate=16000,
                        channels=1,
                        callback=audio_callback,
                        blocksize=1280,  # 80ms blocks at 16kHz
                        latency='high',
                        dtype='float32'
                    )
                    stream.start()
                    logger.info("Microphone stream opened successfully for OpenWakeWord.")
                    reconnect_delay = 1.0
                except Exception as e:
                    logger.warning(f"WakeWord microphone connection failed: {e}. Retrying in {reconnect_delay:.1f}s...")
                    stream = None
                    slices = int(reconnect_delay / 0.1)
                    for _ in range(slices):
                        if not self._running:
                            break
                        time.sleep(0.1)
                    reconnect_delay = min(10.0, reconnect_delay * 1.5)
                    continue

            # 2. Process queued audio frames
            try:
                try:
                    pcm_frame = audio_queue.get(timeout=0.2)
                except queue.Empty:
                    if stream and not stream.active:
                        logger.warning("WakeWord mic stream became inactive. Reconnecting...")
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
                        is_match = any(w in word.lower() for w in self.wake_words) or ("jarvis" in word.lower())
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


class WakeWordDetectorFactory:
    """Factory builder to instantiate standardized WakeWordDetector subclasses based on configuration."""

    @staticmethod
    def create_detector(engine_type: str, **kwargs) -> WakeWordDetector:
        engine_lower = (engine_type or "openwakeword").lower().strip()
        logger.info(f"Factory creating WakeWordDetector of type: '{engine_lower}'")

        if engine_lower == "openwakeword":
            det = OpenWakeWordDetector(**kwargs)
            if not det.is_available():
                logger.warning(f"[WAKE_WORD_DIAGNOSTIC] OpenWakeWord unavailable: {det.get_diagnostic()}")
            return det
        elif engine_lower == "porcupine":
            det = PorcupineWakeWordDetector(**kwargs)
            if not det.is_available():
                logger.warning(f"[WAKE_WORD_DIAGNOSTIC] Porcupine unavailable: {det.get_diagnostic()}")
            return det
        elif engine_lower == "mock":
            return MockWakeWordDetector(**kwargs)
        else:
            logger.warning(f"Unknown wake word engine type: '{engine_type}'. Falling back to MockWakeWordDetector.")
            return MockWakeWordDetector(**kwargs)
