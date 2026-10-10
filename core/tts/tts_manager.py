import os
import time
import queue
import logging
import threading
import numpy as np
import sounddevice as sd
import av
from pathlib import Path
from typing import Optional, Dict, Any

from config import config
from core.tts.base_tts import BaseTTS
from core.tts.providers.edge_tts_provider import EdgeTTSProvider
from core.tts.providers.windows_sapi_provider import WindowsSAPIProvider
from core.tts.providers.pyttsx3_provider import Pyttsx3Provider
from core.tts.providers.gtts_provider import GTTSProvider
from core.tts.providers.elevenlabs_provider import ElevenLabsProvider
from core.speech_sanitizer import sanitize_speech_text

logger = logging.getLogger("Jarvis.TTSManager")

class TTSManager:
    """Central Queue-based, Multi-Provider TTS Manager.
    Manages active provider, speech FIFO queue, audio streaming, instant interruption,
    automatic multi-tier fallback, and verified audio playback lifecycle tracking.
    """

    def __init__(self):
        self._queue = queue.Queue()
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        # Interruption & Speaking states
        self._interrupt_event = threading.Event()
        self._current_player_stream = None
        self._is_speaking = False
        self._state = "IDLE"
        self._current_job_id: Optional[str] = None
        self._last_playback_success = False

        # Providers
        self._providers: Dict[str, BaseTTS] = {
            "edge": EdgeTTSProvider(),
            "sapi": WindowsSAPIProvider(),
            "windows": WindowsSAPIProvider(),
            "pyttsx3": Pyttsx3Provider(),
            "gtts": GTTSProvider(),
            "elevenlabs": ElevenLabsProvider()
        }
        self._active_provider_key = getattr(config, "tts_provider", "edge")

        # Callbacks
        self.on_start_speaking_cb = None
        self.on_stop_speaking_cb = None
        self.on_audio_amplitude_cb = None
        self.on_start_synthesizing_cb = None

        # On-disk audio cache
        self._cache_dir = Path(".cache/tts")
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        self._log_audio_devices()

    def _log_audio_devices(self):
        try:
            dev = sd.query_devices(kind='output')
            logger.info(f"[AUDIO_DEVICE_INFO] Default Output: '{dev.get('name')}' | Rate: {dev.get('default_samplerate')}Hz | Channels: {dev.get('max_output_channels')}")
        except Exception as e:
            logger.debug(f"Could not query default audio output device: {e}")

    def _resolve_output_device(self) -> Optional[int]:
        target = getattr(config, "audio_output_device", None)
        if target is None:
            return None
        try:
            target_idx = int(target)
            devices = sd.query_devices()
            if 0 <= target_idx < len(devices):
                dev = devices[target_idx]
                if dev.get('max_output_channels', 0) > 0:
                    return target_idx
        except Exception:
            pass
        return None

    @property
    def state(self) -> str:
        return self._state

    @property
    def provider(self) -> BaseTTS:
        key = getattr(config, "tts_provider", self._active_provider_key).lower()
        return self._providers.get(key, self._providers["edge"])

    def set_provider(self, provider_name: str):
        key = provider_name.lower().strip()
        if key in self._providers:
            self._active_provider_key = key
            config.tts_provider = key
            logger.info(f"TTSManager set active provider to: '{self.provider.get_name()}'")
        else:
            logger.warning(f"Unknown TTS provider '{provider_name}'. Retaining '{self.provider.get_name()}'.")

    def start(self, on_start_speaking=None, on_stop_speaking=None, on_audio_amplitude=None, on_start_synthesizing=None):
        """Starts background worker thread."""
        with self._lock:
            if self._running:
                return

            if on_start_speaking is not None:
                self.on_start_speaking_cb = on_start_speaking
            if on_stop_speaking is not None:
                self.on_stop_speaking_cb = on_stop_speaking
            if on_audio_amplitude is not None:
                self.on_audio_amplitude_cb = on_audio_amplitude
            if on_start_synthesizing is not None:
                self.on_start_synthesizing_cb = on_start_synthesizing

            self._running = True
            self._interrupt_event.clear()
            self._thread = threading.Thread(target=self._process_queue, name="TTSThread", daemon=True)
            self._thread.start()
            logger.info(f"TTSManager active with provider: {self.provider.get_name()}")

    def stop(self):
        """Halts active speech and terminates worker."""
        logger.info("Stopping TTSManager Subsystem.")
        self.interrupt()
        with self._lock:
            self._running = False
            self._queue.put(None)

        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("TTSManager Subsystem stopped.")

    def speak(self, text: str, interrupt: bool = True, job_id: Optional[str] = None):
        """Enqueues text for TTS synthesis and audio playback."""
        if not text or not text.strip():
            return

        if interrupt:
            self.interrupt()

        self._interrupt_event.clear()
        if job_id:
            self._current_job_id = job_id
            logger.info(f"[TTS_ENQUEUED][{job_id}] Text: '{text}' (Interrupt={interrupt})")
            self._queue.put(("text", text, job_id))
        else:
            self._current_job_id = None
            logger.info(f"[TTS_ENQUEUED] Text: '{text}' (Interrupt={interrupt})")
            self._queue.put(("text", text))

    def play_wav(self, file_path: str, interrupt: bool = True, job_id: Optional[str] = None):
        """Enqueues an audio file for playback."""
        import uuid
        actual_job_id = job_id or uuid.uuid4().hex[:8]
        if interrupt:
            self.interrupt()
        self._current_job_id = actual_job_id
        self._interrupt_event.clear()
        logger.info(f"[TTS_ENQUEUED][{actual_job_id}] Audio file: {file_path}")
        self._queue.put(("file", file_path, actual_job_id))

    def interrupt(self, force: bool = True, from_vad: bool = False):
        """Halts active audio output and flushes the queue."""
        if not force and self._state == "TTS_SYNTHESIZING":
            return
        logger.info("Speech interruption requested. Clearing queue.")
        self._interrupt_event.set()
        self._current_job_id = None
        self._state = "IDLE"

        try:
            sd.stop()
        except Exception:
            pass

        with self._lock:
            if self._current_player_stream:
                try:
                    self._current_player_stream.stop()
                except Exception as e:
                    logger.debug(f"Error stopping audio stream on interrupt: {e}")

        self.clear_queue()

    def clear_queue(self):
        """Empties pending speech items in queue."""
        try:
            while not self._queue.empty():
                item = self._queue.get_nowait()
                if item and item[0] == "temp_file":
                    self._delete_file_safely(item[1])
                self._queue.task_done()
        except queue.Empty:
            pass

    def is_speaking(self) -> bool:
        return self._is_speaking or not self._queue.empty()

    def get_audio_device_info(self) -> dict:
        """Returns metadata about the active audio playback device."""
        try:
            dev = sd.query_devices(kind='output')
            return {
                "name": dev.get("name", "Default Audio Device"),
                "sample_rate": dev.get("default_samplerate", 44100.0),
                "channels": dev.get("max_output_channels", 2),
                "index": dev.get("index", 0)
            }
        except Exception as e:
            return {
                "name": "Default Audio Device",
                "sample_rate": 44100.0,
                "channels": 2,
                "error": str(e)
            }

    def play_wake_chime(self):
        """Plays a crisp non-blocking audio earcon chime acknowledging wake word."""
        def _beep():
            try:
                import winsound
                winsound.Beep(987, 70)   # B5 note
                winsound.Beep(1318, 90)  # E6 note
            except Exception:
                pass
        threading.Thread(target=_beep, name="ChimeThread", daemon=True).start()

    def test_speakers(self) -> Dict[str, Any]:
        """Diagnostic routine to test audio output hardware directly."""
        try:
            dev = sd.query_devices(kind='output')
            dev_name = dev.get('name', 'Unknown Output Device')
            self.speak("Testing audio output. Speaker playback is operational.", interrupt=True)
            return {
                "success": True,
                "device": dev_name,
                "message": f"Audio test tone dispatched to '{dev_name}'."
            }
        except Exception as e:
            logger.error(f"[AUDIO_PLAYBACK_FAILED] Speaker test error: {e}")
            return {
                "success": False,
                "device": "Unknown",
                "message": f"Audio diagnostic failed: {str(e)}"
            }

    def _get_cache_path(self, text: str) -> Optional[Path]:
        """Generates deterministic cache path for short phrases."""
        if len(text.strip()) > 80:
            return None
        import hashlib
        key = f"{text.strip().lower()}:{self.provider.get_name()}"
        h = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        return self._cache_dir / f"tts_{h}.wav"

    def _process_queue(self):
        while self._running:
            try:
                item = self._queue.get(timeout=0.1)
                if item is None:
                    break

                if len(item) == 3:
                    item_type, payload, item_job_id = item
                else:
                    item_type, payload = item
                    item_job_id = None

                # Discard superseded jobs
                if item_job_id and self._current_job_id and item_job_id != self._current_job_id:
                    logger.info(f"Skipping superseded TTS job '{item_job_id}' (Current: '{self._current_job_id}')")
                    self._queue.task_done()
                    continue

                self._interrupt_event.clear()
                temp_file_to_clean = None
                self._last_playback_success = False

                try:
                    if item_type == "text":
                        self._state = "TTS_SYNTHESIZING"
                        if self.on_start_synthesizing_cb:
                            self._trigger_callback(self.on_start_synthesizing_cb)
                        logger.info(f"[TTS_SYNTHESIS_STARTED][{item_job_id}] Text: '{payload}'")
                        t0_synth = time.time()

                        # Check Cache
                        cache_file = self._get_cache_path(payload)
                        cached_audio_path = None
                        if cache_file and cache_file.exists() and cache_file.stat().st_size > 0:
                            cached_audio_path = str(cache_file)
                            synth_ms = (time.time() - t0_synth) * 1000
                            logger.info(f"[TTS_CACHE_HIT][{item_job_id}] Cached audio found in {synth_ms:.1f}ms: {cached_audio_path}")

                        if cached_audio_path:
                            audio_file_to_play = cached_audio_path
                        else:
                            # 1. Try primary active provider
                            primary_p = self.provider
                            try:
                                temp_file_to_clean = primary_p.synthesize_to_file(payload)
                            except Exception as prim_err:
                                logger.warning(f"Primary TTS provider '{primary_p.get_name()}' failed: {prim_err}")
                                temp_file_to_clean = None

                            # 2. Fallback providers
                            if not temp_file_to_clean and not self._interrupt_event.is_set():
                                for p_key, p_inst in self._providers.items():
                                    if p_inst is not primary_p:
                                        try:
                                            logger.info(f"Attempting fallback TTS synthesis with: {p_inst.get_name()}")
                                            temp_file_to_clean = p_inst.synthesize_to_file(payload)
                                            if temp_file_to_clean:
                                                logger.info(f"Fallback TTS synthesis succeeded using: {p_inst.get_name()}")
                                                break
                                        except Exception as fb_err:
                                            logger.debug(f"Fallback TTS '{p_inst.get_name()}' failed: {fb_err}")

                            synth_ms = (time.time() - t0_synth) * 1000
                            audio_file_to_play = temp_file_to_clean

                            # Save to cache if eligible
                            if cache_file and temp_file_to_clean and os.path.exists(temp_file_to_clean):
                                try:
                                    import shutil
                                    shutil.copy2(temp_file_to_clean, str(cache_file))
                                except Exception:
                                    pass

                        if audio_file_to_play:
                            logger.info(f"[TTS_SYNTHESIS_FINISHED][{item_job_id}] Succeeded in {synth_ms:.1f}ms -> {audio_file_to_play}")
                            if not self._interrupt_event.is_set():
                                self._state = "TTS_PLAYING"
                                self._is_speaking = True
                                self._trigger_callback(self.on_start_speaking_cb)
                                if item_job_id:
                                    self._last_playback_success = self._play_audio_file(audio_file_to_play, item_job_id, synth_ms=synth_ms)
                                else:
                                    self._last_playback_success = self._play_audio_file(audio_file_to_play)
                        else:
                            logger.error(f"[TTS_SYNTHESIS_FAILED][{item_job_id}] All TTS providers failed to synthesize audio.")

                    elif item_type in ["file", "temp_file"]:
                        temp_file_to_clean = payload if item_type == "temp_file" else None
                        self._state = "TTS_PLAYING"
                        self._is_speaking = True
                        self._trigger_callback(self.on_start_speaking_cb)
                        if item_job_id:
                            self._last_playback_success = self._play_audio_file(payload, item_job_id)
                        else:
                            self._last_playback_success = self._play_audio_file(payload)

                except Exception as e:
                    logger.error(f"Error in TTS processing: {e}", exc_info=True)
                finally:
                    if temp_file_to_clean and (not cache_file or str(cache_file) != temp_file_to_clean):
                        self._delete_file_safely(temp_file_to_clean)

                    self._state = "IDLE"
                    self._is_speaking = False
                    if self._last_playback_success:
                        logger.info(f"[TTS_COMPLETED][{item_job_id}] Speech playback completed successfully.")
                    else:
                        logger.warning(f"[TTS_COMPLETED_WITH_WARNINGS][{item_job_id}] Speech cycle finished.")

                    self._trigger_callback(self.on_stop_speaking_cb)
                    if self.on_audio_amplitude_cb:
                        self._trigger_callback(self.on_audio_amplitude_cb, 0.0)
                    self._queue.task_done()

            except queue.Empty:
                continue

    def _play_audio_file(self, file_path: str, job_id: Optional[str] = None, synth_ms: float = 0.0) -> bool:
        played_successfully = False
        container = None
        uid = job_id or "DIRECT"
        t0_play = time.time()

        try:
            dev = sd.query_devices(kind='output')
            dev_name = dev.get('name', 'Default Audio Device')
            logger.info(f"[AUDIO_PLAYBACK_STARTED][{uid}] File: {file_path}")

            container = av.open(file_path)
            if container.streams.audio:
                stream = container.streams.audio[0]
                sample_rate = stream.codec_context.sample_rate
                channels = stream.codec_context.channels

                frames = [f.to_ndarray() for f in container.decode(stream)]
                if frames:
                    formatted_frames = []
                    for f in frames:
                        if len(f.shape) > 1 and f.shape[0] == channels:
                            formatted_frames.append(f.T)
                        else:
                            formatted_frames.append(f)
                    audio_data = np.concatenate(formatted_frames, axis=0)

                    # Ensure float32 format
                    if audio_data.dtype != np.float32:
                        audio_data = audio_data.astype(np.float32)

                    # Mark speaking state and trigger callback at start of audio playback
                    self._is_speaking = True
                    self._trigger_callback(self.on_start_speaking_cb)

                    sd.play(audio_data, samplerate=sample_rate)
                    
                    # Compute chunk-by-chunk amplitude for UI pulsation
                    chunk_size = int(sample_rate * 0.03)  # ~30ms
                    num_samples = len(audio_data)
                    pos = 0

                    while pos < num_samples and not self._interrupt_event.is_set():
                        chunk = audio_data[pos:pos + chunk_size]
                        if len(chunk) > 0:
                            rms = float(np.sqrt(np.mean(chunk**2)))
                            amp = min(1.0, rms * 4.0)
                            if self.on_audio_amplitude_cb:
                                self._trigger_callback(self.on_audio_amplitude_cb, amp)
                        pos += chunk_size
                        time.sleep(0.03)

                    if self._interrupt_event.is_set():
                        sd.stop()
                        logger.info(f"[AUDIO_PLAYBACK_INTERRUPTED][{uid}] Playback stopped mid-stream.")
                    else:
                        sd.wait()
                        played_successfully = True
                        play_dur_ms = (time.time() - t0_play) * 1000
                        logger.info(f"[TTS_TIMELINE][{uid}] synth={synth_ms:.1f}ms play_dur={play_dur_ms:.1f}ms -> SUCCESS")

        except Exception as e:
            logger.warning(f"[AUDIO_PLAYBACK_FAILED][{uid}] PyAV/sounddevice playback error: {e}")
        finally:
            if container:
                try:
                    container.close()
                except Exception:
                    pass
            with self._lock:
                self._current_player_stream = None

        # Multi-tier playback fallback if PyAV/sounddevice encountered an issue
        if not played_successfully and not self._interrupt_event.is_set():
            logger.info(f"Attempting multi-tier secondary audio player fallback for {file_path}...")
            # 1. Try Pygame if installed
            try:
                import pygame
                if not pygame.mixer.get_init():
                    pygame.mixer.init()
                pygame.mixer.music.load(file_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy() and not self._interrupt_event.is_set():
                    time.sleep(0.05)
                played_successfully = True
                logger.info("[AUDIO_PLAYBACK_FINISHED] Playback succeeded via Pygame mixer fallback.")
            except Exception:
                pass

            # 2. Try native winsound for WAV
            if not played_successfully and not self._interrupt_event.is_set() and file_path.lower().endswith(".wav"):
                try:
                    import winsound
                    logger.info("Playing audio via native Windows PlaySound fallback.")
                    winsound.PlaySound(file_path, winsound.SND_FILENAME)
                    played_successfully = True
                    logger.info("[AUDIO_PLAYBACK_FINISHED] Playback succeeded via Windows PlaySound fallback.")
                except Exception as ws_err:
                    logger.error(f"[AUDIO_PLAYBACK_FAILED] Winsound fallback playback failed: {ws_err}")

        return played_successfully

    def _delete_file_safely(self, path: str):
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.debug(f"Could not remove file {path}: {e}")

    def _trigger_callback(self, cb, *args):
        if cb:
            try:
                if args:
                    cb(*args)
                else:
                    threading.Thread(target=cb, name="TTSCallbackThread", daemon=True).start()
            except Exception as e:
                logger.error(f"Error triggering TTS callback: {e}")
