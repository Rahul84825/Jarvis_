import time
import logging
import threading
import numpy as np
import sounddevice as sd

logger = logging.getLogger("Jarvis.ClapDetector")

class ClapDetector:
    """Monitors real-time microphone stream to detect single and double claps.
    Uses signal processing (peak threshold, crest factor, ambient noise floor tracking, and timing)
    to differentiate claps from speech or background noise.
    """
    
    def __init__(self, threshold=0.15, min_gap=0.15, max_gap=0.5, sample_rate=16000):
        self.threshold = threshold
        self.min_gap = min_gap
        self.max_gap = max_gap
        self.sample_rate = sample_rate
        
        self.on_single_clap_cb = None
        self.on_double_clap_cb = None
        
        self._stream = None
        self._running = False
        self._lock = threading.Lock()
        
        # Clap detection state
        self._last_clap_time = 0.0
        self._waiting_for_second = False
        self._single_clap_timer = None
        
        # Exponential moving average for background noise floor estimation
        self._ambient_level = 0.01
        self._alpha = 0.98
        
        # Stabilization locks
        self.speaking_active = False
        self._lockout_until = 0.0

    def set_speaking_active(self, is_speaking: bool):
        """Mutes clap detection while Jarvis is speaking to prevent feedback loops."""
        with self._lock:
            self.speaking_active = is_speaking
            if is_speaking:
                # Cancel pending single clap timer
                if self._single_clap_timer:
                    self._single_clap_timer.cancel()
                    self._single_clap_timer = None
                self._waiting_for_second = False

    def start(self, on_single_clap=None, on_double_clap=None):
        """Opens audio stream and starts background clap detection."""
        with self._lock:
            if self._running:
                logger.warning("Clap detector is already running.")
                return
            
            if on_single_clap is not None:
                self.on_single_clap_cb = on_single_clap
            if on_double_clap is not None:
                self.on_double_clap_cb = on_double_clap
            self._running = True
            self.speaking_active = False
            self._lockout_until = 0.0
            
            try:
                # Open sounddevice input stream with larger buffer to prevent overflow
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    callback=self._audio_callback,
                    blocksize=1024,  # increased from 512 for stability
                    latency='high',   # prioritized buffer stability over low-latency
                    dtype='float32'
                )
                self._stream.start()
                logger.info(f"Clap Detector started. Sensitivity Threshold: {self.threshold}")
            except Exception as e:
                self._running = False
                logger.error(f"Failed to initialize Clap Detector audio stream: {e}", exc_info=True)
                raise e

    def stop(self):
        """Stops the audio stream and cancels any pending clap timers."""
        with self._lock:
            if not self._running:
                return
            
            logger.info("Stopping Clap Detector.")
            self._running = False
            
            if self._single_clap_timer:
                self._single_clap_timer.cancel()
                self._single_clap_timer = None
                
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception as e:
                    logger.error(f"Error closing clap detector stream: {e}")
                self._stream = None
            
            logger.info("Clap Detector stopped.")

    def is_active(self) -> bool:
        """Returns True if the clap detector is actively running."""
        with self._lock:
            return self._running

    def set_threshold(self, threshold: float):
        """Adjusts the peak sensitivity threshold on the fly."""
        self.threshold = threshold
        logger.info(f"Clap detector threshold adjusted to: {self.threshold}")

    def _audio_callback(self, indata, frames, time_info, status):
        """Audio callback running on high-priority audio thread."""
        if status:
            logger.debug(f"Audio stream status issue: {status}")
            
        if not self._running:
            return

        current_time = time.time()
        
        # Check speaking lock or post-detection lockout period
        if getattr(self, 'speaking_active', False) or current_time < self._lockout_until:
            return

        # Extract samples (1 channel)
        samples = indata[:, 0]
        if len(samples) == 0:
            return
            
        peak = np.max(np.abs(samples))
        
        # Track background ambient noise level when it's relatively quiet
        if peak < self.threshold * 0.5:
            self._ambient_level = self._alpha * self._ambient_level + (1.0 - self._alpha) * peak
            
        # Detect clap transient
        if peak > self.threshold and peak > (self._ambient_level * 3.0):
            time_diff = current_time - self._last_clap_time
            
            # Debounce filter
            if time_diff < self.min_gap:
                return
                
            # Crest factor check: Claps have high peaks relative to average energy (sharp transients)
            mean_abs = np.mean(np.abs(samples))
            crest_factor = peak / (mean_abs + 1e-6)
            
            if crest_factor < 4.0:
                # Sustained sound like speaking or humming, filter out
                return
                
            logger.debug(f"Potential clap detected: peak={peak:.3f}, crest={crest_factor:.2f}")
            self._handle_clap_event(current_time)

    def _handle_clap_event(self, current_time):
        """Handles single/double clap transition logic in a thread-safe manner."""
        with self._lock:
            # Check speaking lock or lockout once more under lock
            if self.speaking_active or current_time < self._lockout_until:
                return

            if self._waiting_for_second:
                gap = current_time - self._last_clap_time
                if self.min_gap <= gap <= self.max_gap:
                    logger.info(f"Double clap detected (Gap: {gap:.3f}s)")
                    
                    if self._single_clap_timer:
                        self._single_clap_timer.cancel()
                        self._single_clap_timer = None
                        
                    self._waiting_for_second = False
                    self._last_clap_time = 0.0
                    
                    # Establish double clap lockout period to ignore reverb/re-trigger
                    self._lockout_until = time.time() + 1.0
                    
                    if self.on_double_clap_cb:
                        threading.Thread(target=self.on_double_clap_cb, name="ClapCallbackThread", daemon=True).start()
                else:
                    # Gap too large, treat current clap as first clap of a new potential double-clap
                    self._last_clap_time = current_time
                    self._schedule_single_clap_timer(current_time)
            else:
                self._waiting_for_second = True
                self._last_clap_time = current_time
                self._schedule_single_clap_timer(current_time)

    def _schedule_single_clap_timer(self, clap_time):
        """Starts timer. If no second clap occurs before timer fires, registers single clap."""
        if self._single_clap_timer:
            self._single_clap_timer.cancel()
            
        self._single_clap_timer = threading.Timer(
            self.max_gap,
            self._trigger_single_clap,
            args=[clap_time]
        )
        self._single_clap_timer.daemon = True
        self._single_clap_timer.start()

    def _trigger_single_clap(self, clap_time):
        with self._lock:
            if self.speaking_active:
                return

            if self._waiting_for_second and self._last_clap_time == clap_time:
                logger.info("Single clap detected")
                self._waiting_for_second = False
                
                # Establish single clap lockout period to ignore reverb/re-trigger
                self._lockout_until = time.time() + 0.5
                
                if self.on_single_clap_cb:
                    threading.Thread(target=self.on_single_clap_cb, name="ClapCallbackThread", daemon=True).start()

