import os
import wave
import time
import logging
import tempfile
import threading
import numpy as np
import sounddevice as sd

logger = logging.getLogger("Jarvis.Listener")

class SpeechListener:
    """Microphone audio listener.
    Supports energy-based Voice Activity Detection (VAD) for automatic speech capture,
    and manual trigger controls (push-to-talk). Saves speech to WAV files (16kHz, 16-bit Mono),
    satisfying Whisper speech-to-text input requirements.
    """
    
    def __init__(self, sample_rate=16000, threshold=0.015, silence_duration=1.5, max_duration=10.0, enable_vad_onset=True):
        self.sample_rate = sample_rate
        self.threshold = threshold
        self.silence_duration = silence_duration
        self.max_duration = max_duration
        self.enable_vad_onset = enable_vad_onset
        
        self._running = False
        self._recording = False
        self._recording_start_time = None
        self._ambient_rms = 0.005
        self._stream = None
        self._lock = threading.Lock()
        
        self._audio_buffer = []
        self._pre_roll_buffer = []
        self.pre_roll_duration = 1.0
        self._silence_start = None
        self._speech_detected = False
        self._manual_recording = False
        
        self.on_speech_start_cb = None
        self.on_speech_end_cb = None  # Signature: callback(wav_path: str)
        
        # Stabilization lock
        self.speaking_active = False

    def set_speaking_active(self, is_speaking: bool):
        """Mutes speech listener background VAD while Jarvis is speaking."""
        with self._lock:
            self.speaking_active = is_speaking
            if is_speaking:
                # Suppress unconfirmed background VAD recording while Jarvis speaks, but keep manual wake recordings
                if self._recording and not self._manual_recording:
                    logger.debug("Suppressing background VAD recording: Jarvis is speaking.")
                    self._recording = False
                    self._audio_buffer = []
                    self._silence_start = None
                    self._recording_start_time = None

    def start(self, on_speech_start=None, on_speech_end=None):
        """Starts monitoring the microphone stream for voice activity."""
        with self._lock:
            if self._running:
                logger.warning("Listener is already active.")
                return
            
            if on_speech_start is not None:
                self.on_speech_start_cb = on_speech_start
            if on_speech_end is not None:
                self.on_speech_end_cb = on_speech_end
            self._running = True
            self._recording = False
            self._manual_recording = False
            self._recording_start_time = None
            self._ambient_rms = 0.005
            self._audio_buffer = []
            self._pre_roll_buffer = []
            self.speaking_active = False
            
            try:
                self._stream = sd.InputStream(
                    samplerate=self.sample_rate,
                    channels=1,
                    callback=self._audio_callback,
                    blocksize=2048,  # increased from 1024 for stability
                    latency='high',   # prioritized buffer stability
                    dtype='float32'
                )
                self._stream.start()
                logger.info("Speech Listener stream started successfully.")
            except Exception as e:
                self._running = False
                logger.error(f"Failed to start Speech Listener stream: {e}", exc_info=True)
                raise e

    def stop(self):
        """Stops the stream and releases microphone hardware."""
        with self._lock:
            if not self._running:
                return
            
            logger.info("Stopping Speech Listener.")
            self._running = False
            self._recording = False
            self._manual_recording = False
            self._recording_start_time = None
            
            if self._stream:
                try:
                    self._stream.stop()
                    self._stream.close()
                except Exception as e:
                    logger.error(f"Error closing Speech Listener stream: {e}")
                self._stream = None
            
            logger.info("Speech Listener stopped.")

    def is_listening(self) -> bool:
        """Returns True if monitoring microphone."""
        with self._lock:
            return self._running

    def trigger_manual_recording(self, manual=True):
        """Bypasses voice activity detection and begins capturing audio immediately."""
        with self._lock:
            if not self._running:
                logger.warning("Cannot start recording. Listener is not running.")
                return
            
            logger.info(f"Speech recording triggered (manual={manual}). Resetting buffer.")
            self._audio_buffer = list(self._pre_roll_buffer)
            self._recording = True
            self._recording_start_time = time.time()
            self._manual_recording = manual
            self._silence_start = None
            
            if self.on_speech_start_cb:
                threading.Thread(target=self.on_speech_start_cb, name="ListenerStartCB", daemon=True).start()

    def stop_manual_recording(self):
        """Stops manual audio recording and processes the WAV output."""
        with self._lock:
            if not self._recording or not self._manual_recording:
                logger.warning("No manual recording session is active.")
                return
            
            logger.info("Manual speech recording stopped. Processing WAV file.")
            self._recording = False
            self._manual_recording = False
            self._recording_start_time = None
            
            if self._audio_buffer:
                captured_data = np.concatenate(self._audio_buffer, axis=0)
                self._audio_buffer = []
                threading.Thread(target=self._save_and_dispatch, args=(captured_data,), name="ListenerSaveThread", daemon=True).start()

    def _audio_callback(self, indata, frames, time_info, status):
        """High-priority audio callback that captures buffer chunks."""
        if status:
            logger.debug(f"Speech Listener stream warning: {status}")
            
        if not self._running:
            return
 
        with self._lock:
            # Maintain pre-roll buffer when running
            if self._running:
                self._pre_roll_buffer.append(indata.copy())
                # Ensure it doesn't exceed pre-roll duration
                total_samples = sum(len(x) for x in self._pre_roll_buffer)
                max_samples = int(self.sample_rate * self.pre_roll_duration)
                while total_samples - len(self._pre_roll_buffer[0]) >= max_samples:
                    total_samples -= len(self._pre_roll_buffer[0])
                    self._pre_roll_buffer.pop(0)
 
        samples = indata[:, 0]
        rms = float(np.sqrt(np.mean(samples**2)))
        
        with self._lock:
            # Dynamically update ambient noise baseline when NOT actively recording speech
            if not self._recording:
                self._ambient_rms = self._ambient_rms * 0.95 + rms * 0.05
                
            # Dynamic speech threshold (at least self.threshold, or 2.0x ambient floor)
            speech_threshold = max(self.threshold, self._ambient_rms * 2.0)

            # If in standby monitoring mode (VAD)
            if self._running and not self._recording:
                if self.enable_vad_onset and rms > speech_threshold:
                    logger.info(f"VAD: Speech onset detected (RMS: {rms:.4f} > Threshold: {speech_threshold:.4f}, Ambient: {self._ambient_rms:.4f}). Recording started.")
                    self._recording = True
                    self._recording_start_time = time.time()
                    self._manual_recording = False
                    self._audio_buffer = list(self._pre_roll_buffer)
                    self._silence_start = None
                    
                    if self.on_speech_start_cb:
                        threading.Thread(target=self.on_speech_start_cb, name="ListenerStartCB", daemon=True).start()
            
            # If actively recording
            elif self._recording:
                self._audio_buffer.append(indata.copy())
                now = time.time()
                
                # Check for max recording duration safety cap (e.g., 10 seconds)
                if self._recording_start_time and (now - self._recording_start_time > self.max_duration):
                    logger.info(f"VAD: Max recording duration limit reached ({self.max_duration}s). Finalizing audio.")
                    self._recording = False
                    captured_data = np.concatenate(self._audio_buffer, axis=0)
                    self._audio_buffer = []
                    self._silence_start = None
                    self._recording_start_time = None
                    threading.Thread(target=self._save_and_dispatch, args=(captured_data,), name="ListenerSaveThread", daemon=True).start()
                    return

                # Check for VAD silence timeout (only if not manually triggered)
                if not self._manual_recording:
                    if rms < speech_threshold:
                        if self._silence_start is None:
                            self._silence_start = now
                        elif now - self._silence_start > self.silence_duration:
                            logger.info(f"VAD: Silence duration limit reached ({self.silence_duration}s). Speech finalized.")
                            self._recording = False
                            
                            captured_data = np.concatenate(self._audio_buffer, axis=0)
                            self._audio_buffer = []
                            self._silence_start = None
                            self._recording_start_time = None
                            
                            threading.Thread(target=self._save_and_dispatch, args=(captured_data,), name="ListenerSaveThread", daemon=True).start()
                    else:
                        self._silence_start = None  # Speech continues, reset silence timer

    def _save_and_dispatch(self, audio_data):
        """Encodes float32 samples to 16-bit WAV and triggers end-of-speech callback."""
        from pathlib import Path
        try:
            # Clip values to ensure safe range, then convert to 16-bit PCM integers
            clipped = np.clip(audio_data, -1.0, 1.0)
            pcm_data = (clipped * 32767.0).astype(np.int16)
            
            # Set up temporary file
            fd, temp_path = tempfile.mkstemp(suffix=".wav", prefix="jarvis_speech_")
            os.close(fd)
            
            with wave.open(temp_path, 'wb') as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)  # 2 bytes for 16-bit PCM
                wav_file.setframerate(self.sample_rate)
                wav_file.writeframes(pcm_data.tobytes())
                
            logger.info(f"Speech WAV file saved: {temp_path}")
            
            # Save a debug copy in logs/debug_wavs/ and maintain last 20 files if debug_audio is enabled
            try:
                from config import config
                if config.debug_audio:
                    debug_dir = config.LOGS_DIR / "debug_wavs"
                    debug_dir.mkdir(exist_ok=True, parents=True)
                    
                    # Clean up old debug files to keep only the last 20
                    existing_wavs = sorted(debug_dir.glob("*.wav"), key=os.path.getmtime)
                    while len(existing_wavs) >= 20:
                        try:
                            existing_wavs[0].unlink()
                            existing_wavs.pop(0)
                        except Exception as e:
                            logger.warning(f"Could not delete old debug wav: {e}")
                            break
                    
                    timestamp = int(time.time() * 1000)
                    debug_path = debug_dir / f"speech_{timestamp}.wav"
                    
                    with wave.open(str(debug_path), 'wb') as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(self.sample_rate)
                        wav_file.writeframes(pcm_data.tobytes())
                    
                    logger.info(f"Saved debug WAV file: {debug_path}")
            except Exception as e:
                logger.error(f"Failed to save debug WAV file copy: {e}", exc_info=True)
            
            if self.on_speech_end_cb:
                self.on_speech_end_cb(temp_path)

        except Exception as e:
            logger.error(f"Failed to process and save speech WAV: {e}", exc_info=True)

    @staticmethod
    def get_available_microphones():
        """Lists available audio input devices (microphones)."""
        devices = []
        try:
            device_list = sd.query_devices()
            for idx, dev in enumerate(device_list):
                if dev.get("max_input_channels", 0) > 0:
                    devices.append({
                        "id": idx,
                        "name": dev.get("name", "Unknown Microphone"),
                        "channels": dev.get("max_input_channels", 1),
                        "sample_rate": int(dev.get("default_samplerate", 16000))
                    })
        except Exception as e:
            logger.error(f"Failed to query microphone devices: {e}")
        return devices

    def run_microphone_diagnostics(self, duration: float = 2.0) -> dict:
        """Runs a real-time diagnostic test on the microphone stream."""
        logger.info(f"Running microphone diagnostics for {duration} seconds...")
        mic_name = "Default System Microphone"
        try:
            default_in = sd.query_devices(kind='input')
            mic_name = default_in.get("name", mic_name)
        except Exception:
            pass

        try:
            recording = sd.rec(int(duration * self.sample_rate), samplerate=self.sample_rate, channels=1, dtype='float32')
            sd.wait()
            recording = recording.flatten()

            rms = float(np.sqrt(np.mean(recording ** 2)))
            max_val = float(np.max(np.abs(recording)))
            clipping = max_val >= 0.98
            noise_floor = float(np.percentile(np.abs(recording), 10))
            snr = float(20 * np.log10(rms / (noise_floor + 1e-6))) if rms > noise_floor else 0.0

            quality = "Excellent" if (rms > 0.01 and not clipping and snr > 12) else (
                "Fair" if (rms > 0.003 and not clipping) else "Low Signal / Muted"
            )

            report = {
                "microphone_name": mic_name,
                "sample_rate": self.sample_rate,
                "channels": 1,
                "input_rms_level": round(rms, 4),
                "peak_amplitude": round(max_val, 4),
                "noise_floor": round(noise_floor, 4),
                "signal_to_noise_ratio_db": round(snr, 1),
                "clipping_detected": clipping,
                "signal_quality": quality,
                "spoken_summary": f"Microphone test complete. Input device '{mic_name}' detected. Signal quality is {quality}."
            }
            logger.info(f"[MIC_DIAGNOSTICS] {report}")
            return report
        except Exception as e:
            logger.error(f"Microphone diagnostics failed: {e}", exc_info=True)
            return {
                "microphone_name": mic_name,
                "sample_rate": self.sample_rate,
                "channels": 1,
                "signal_quality": "Error",
                "clipping_detected": False,
                "spoken_summary": "I couldn't complete the microphone test because the audio device was unavailable."
            }
