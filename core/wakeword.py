import time
import logging
import threading
import queue
import numpy as np
from abc import ABC, abstractmethod
from config import config

logger = logging.getLogger("Jarvis.WakeWord")

class WakeWordDetector(ABC):
    """Abstract base class defining the standardized Wake Word Detector interface.
    Guarantees seamless engine swap-outs (OpenWakeWord, Porcupine, Mock)
    without modifying the coordinating business logic.
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
    and runs local model inference on frames.
    """
    
    def __init__(self, wake_words=None, sensitivity=None, model_path=None, **kwargs):
        self.wake_words = wake_words or ["jarvis"]
        self.sensitivity = sensitivity if sensitivity is not None else config.wakeword_sensitivity
        self.model_path = model_path
        self._running = False
        self._callback = None
        self._thread = None
        self._lock = threading.Lock()
        
        # Audio buffer and debounce
        self._audio_buffer = np.array([], dtype=np.int16)
        self._debounce_until = 0.0

    def start(self, callback):
        with self._lock:
            if self._running:
                logger.warning("OpenWakeWord detector is already running.")
                return
            logger.info("Starting OpenWakeWord Detector...")
            self._callback = callback
            self._running = True
            
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
        import openwakeword
        from openwakeword.model import Model
        import sounddevice as sd

        logger.info("OpenWakeWord thread starting. Loading ONNX models...")
        try:
            # If a custom model path is specified, load it. Otherwise, use pre-trained jarvis model
            models = [self.model_path] if self.model_path else ["jarvis"]
            oww_model = Model(wakeword_models=models, inference_framework="onnxruntime")
            logger.info(f"OpenWakeWord models loaded successfully: {list(oww_model.models.keys())}")
        except Exception as e:
            logger.error(f"Failed to load OpenWakeWord models: {e}", exc_info=True)
            return

        # Queue for thread-safe transfer of audio frames from callback to model thread
        audio_queue = queue.Queue()

        def audio_callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"WakeWord audio stream status: {status}")
            # indata is float32. Convert to int16 (which openwakeword expects) and queue it
            clipped = np.clip(indata[:, 0], -1.0, 1.0)
            pcm_data = (clipped * 32767.0).astype(np.int16)
            audio_queue.put(pcm_data.copy())

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
                        blocksize=1280,  # ~80ms blocks
                        latency='high',   # prioritized buffer stability
                        dtype='float32'
                    )
                    stream.start()
                    logger.info("Microphone stream opened successfully.")
                    reconnect_delay = 1.0  # Reset backoff on success
                except Exception as e:
                    logger.error(f"Microphone connection failed: {e}. Retrying in {reconnect_delay:.1f}s...")
                    stream = None
                    # Sleep in small slices to remain responsive to stop requests
                    slices = int(reconnect_delay / 0.1)
                    for _ in range(slices):
                        if not self._running:
                            break
                        time.sleep(0.1)
                    reconnect_delay = min(10.0, reconnect_delay * 1.5)  # exponential backoff
                    continue

            # 2. Process queued audio frames
            try:
                # Get block from queue
                try:
                    pcm_frame = audio_queue.get(timeout=0.2)
                except queue.Empty:
                    # Check if stream is still active
                    if stream and not stream.active:
                        logger.warning("Microphone stream became inactive. Initiating recovery.")
                        try:
                            stream.stop()
                            stream.close()
                        except Exception:
                            pass
                        stream = None
                    continue
                
                # Append to buffer
                self._audio_buffer = np.append(self._audio_buffer, pcm_frame)
                
                # Feed chunks of 1280 samples (80ms at 16kHz) to openwakeword
                while len(self._audio_buffer) >= 1280:
                    chunk = self._audio_buffer[:1280]
                    self._audio_buffer = self._audio_buffer[1280:]
                    
                    # Run model prediction
                    prediction = oww_model.predict(chunk)
                    
                    # Check if target wake word crossed threshold
                    for word, score in prediction.items():
                        is_match = any(w in word.lower() for w in self.wake_words) or word.lower() == 'jarvis'
                        if is_match and score >= self.sensitivity:
                            current_time = time.time()
                            # Debounce check to prevent multiple triggers
                            if current_time > self._debounce_until:
                                logger.info(f"Wake word '{word}' detected! Score: {score:.3f}")
                                self._debounce_until = current_time + 2.0  # block triggers for 2s
                                if self._callback:
                                    # Execute callback on dispatcher thread
                                    threading.Thread(
                                        target=self._callback,
                                        args=(word,),
                                        name="WakeWordCallbackDispatcher",
                                        daemon=True
                                    ).start()
                                    
            except Exception as e:
                logger.error(f"Error in OpenWakeWord execution loop: {e}", exc_info=True)
                # Force reconnect
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
        logger.info("OpenWakeWord background loop stopped.")


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

    def start(self, callback):
        with self._lock:
            if self._running:
                return
            logger.info("Starting Picovoice Porcupine Detector...")
            self._callback = callback
            self._running = True
            
            if not self.api_key:
                logger.warning("[Porcupine] Picovoice API key is missing. Running in standby-fallback mode.")
                
            try:
                import pvporcupine
                logger.info("Successfully imported pvporcupine library.")
            except ImportError:
                logger.warning("[Porcupine] pvporcupine library is missing. Running in standby-fallback mode.")
                
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
        engine_lower = engine_type.lower().strip()
        logger.info(f"Factory creating WakeWordDetector of type: '{engine_lower}'")
        
        if engine_lower == "mock":
            return MockWakeWordDetector(**kwargs)
        elif engine_lower == "openwakeword":
            return OpenWakeWordDetector(**kwargs)
        elif engine_lower == "porcupine":
            return PorcupineWakeWordDetector(**kwargs)
        else:
            logger.error(f"Unknown wake word engine type: '{engine_type}'. Falling back to Mock.")
            return MockWakeWordDetector(**kwargs)
