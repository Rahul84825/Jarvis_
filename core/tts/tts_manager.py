import os
import time
import queue
import logging
import threading
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any
from core.lazy_loader import lazy_import

sd = lazy_import("sounddevice")
av = lazy_import("av")

from config import config
from core.tts.base_tts import BaseTTS
from core.tts.providers.edge_tts_provider import EdgeTTSProvider
from core.tts.providers.windows_sapi_provider import WindowsSAPIProvider
from core.tts.providers.pyttsx3_provider import Pyttsx3Provider
from core.tts.providers.gtts_provider import GTTSProvider
from core.tts.providers.elevenlabs_provider import ElevenLabsProvider
from core.speech_sanitizer import sanitize_speech_text

class SentenceProgress(tuple):
    """Hybrid tuple and mapping representing current sentence playback progress."""
    def __new__(cls, index: int, total: int, text: str):
        return super().__new__(cls, (index, total, text))

    @property
    def index(self) -> int:
        return self[0]

    @property
    def total(self) -> int:
        return self[1]

    @property
    def text(self) -> str:
        return self[2]

    def __getitem__(self, item):
        if isinstance(item, str):
            if item in ("index", "idx"):
                return self[0]
            elif item in ("total", "total_sentences"):
                return self[1]
            elif item in ("text", "sentence"):
                return self[2]
            raise KeyError(item)
        return super().__getitem__(item)

    def get(self, key, default=None):
        try:
            return self[key]
        except (KeyError, IndexError):
            return default


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

        # Interruption, Generation & Speaking states
        self._interrupt_event = threading.Event()
        self._current_player_stream = None
        self._is_speaking = False
        self._state = "IDLE"
        self._current_job_id: Optional[str] = None
        self._current_generation_id: int = 1
        self._last_interrupted_generation_id: Optional[int] = None
        self._current_sentence_idx: int = 0
        self._total_sentences: int = 0
        self._current_sentence_text: str = ""
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
        self._active_provider_key = "edge"

        # Callbacks
        self.on_start_speaking_cb = None
        self.on_stop_speaking_cb = None
        self.on_audio_amplitude_cb = None
        self.on_start_synthesizing_cb = None
        self.on_sentence_progress_cb = None

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
    def speech_queue(self):
        return self._queue

    def get_queue_size(self) -> int:
        return self._queue.qsize()

    def set_sentence_callback(self, cb):
        self.on_sentence_progress_cb = cb

    @property
    def primary_provider(self) -> BaseTTS:
        return self.provider

    @property
    def state(self) -> str:
        return self._state

    @property
    def provider(self) -> BaseTTS:
        key = (self._active_provider_key or "edge").lower()
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

    @property
    def current_generation_id(self) -> int:
        return self._current_generation_id

    @property
    def generation_id(self) -> int:
        """Alias for current_generation_id."""
        return self._current_generation_id

    @property
    def last_interrupted_generation_id(self) -> Optional[int]:
        return self._last_interrupted_generation_id

    @property
    def current_sentence_progress(self) -> SentenceProgress:
        return SentenceProgress(self._current_sentence_idx, self._total_sentences, self._current_sentence_text)

    def new_generation(self) -> int:
        """Increments and returns a new generation ID, invalidating prior in-flight speech."""
        with self._lock:
            self._current_generation_id += 1
            logger.debug(f"TTS generation advanced to {self._current_generation_id}")
            return self._current_generation_id

    def speak(self, text: str, interrupt: bool = True, job_id: Optional[str] = None, generation_id: Optional[int] = None):
        """Enqueues text for TTS synthesis and audio playback with generation invalidation."""
        if not text or not text.strip():
            return

        if interrupt:
            self.interrupt()

        gen_id = generation_id if generation_id is not None else self._current_generation_id
        if gen_id != self._current_generation_id:
            logger.info(f"Skipping stale speak call (item gen={gen_id}, active gen={self._current_generation_id})")
            return

        self._interrupt_event.clear()
        if job_id:
            self._current_job_id = job_id
            logger.info(f"[TTS_ENQUEUED][{job_id}] Text: '{text}' (Interrupt={interrupt}, Gen={gen_id})")
            self._queue.put(("text", text, job_id, gen_id, 0, 1))
        else:
            self._current_job_id = None
            logger.info(f"[TTS_ENQUEUED] Text: '{text}' (Interrupt={interrupt}, Gen={gen_id})")
            self._queue.put(("text", text, None, gen_id, 0, 1))

    def speak_sentences(self, sentences: list, interrupt: bool = True, job_id: Optional[str] = None):
        """Enqueues a sequence of sentences for ordered speech playback, tracking sentence indices."""
        clean_sentences = [s.strip() for s in sentences if s and s.strip()]
        if not clean_sentences:
            return

        if interrupt:
            self.interrupt()

        gen_id = self._current_generation_id
        self._interrupt_event.clear()
        total = len(clean_sentences)
        self._total_sentences = total

        for idx, sentence in enumerate(clean_sentences):
            sub_id = f"{job_id}_{idx}" if job_id else f"sent_{idx}"
            self._queue.put(("text", sentence, sub_id, gen_id, idx, total))
        logger.info(f"[TTS_ENQUEUED_BATCH] {total} sentences enqueued under generation {gen_id}.")

    def play_wav(self, file_path: str, interrupt: bool = True, job_id: Optional[str] = None):
        """Enqueues an audio file for playback."""
        import uuid
        actual_job_id = job_id or uuid.uuid4().hex[:8]
        if interrupt:
            self.interrupt()
        self._current_job_id = actual_job_id
        gen_id = self._current_generation_id
        self._interrupt_event.clear()
        logger.info(f"[TTS_ENQUEUED][{actual_job_id}] Audio file: {file_path}")
        self._queue.put(("file", file_path, actual_job_id, gen_id, 0, 1))

    def interrupt(self, force: bool = True, from_vad: bool = False):
        """Halts active audio output instantly, invalidates in-flight generations, and flushes queue."""
        if not force and self._state == "TTS_SYNTHESIZING":
            return
        t0 = time.time()
        logger.info(f"Speech interruption requested (from_vad={from_vad}). Invalidating generation {self._current_generation_id}.")
        self._interrupt_event.set()

        # Stop audio hardware immediately via C API
        try:
            sd.stop()
        except Exception:
            pass

        with self._lock:
            self._last_interrupted_generation_id = self._current_generation_id
            self._current_generation_id += 1
            self._current_job_id = None
            self._state = "IDLE"
            self._is_speaking = False

            if self._current_player_stream:
                try:
                    self._current_player_stream.stop()
                except Exception as e:
                    logger.debug(f"Error stopping audio stream on interrupt: {e}")
                self._current_player_stream = None

        self.clear_queue()

        # Notify UI and listeners that speech has ceased
        self._trigger_callback(self.on_stop_speaking_cb)
        if self.on_audio_amplitude_cb:
            self._trigger_callback(self.on_audio_amplitude_cb, 0.0)

        elapsed_ms = (time.time() - t0) * 1000
        logger.info(f"[TTS_INTERRUPTED] Audio playback silenced and queue cleared in {elapsed_ms:.2f}ms.")

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
        return self._is_speaking or not self._queue.empty() or self._state in ["TTS_SYNTHESIZING", "TTS_PLAYING"]

    def is_playing(self) -> bool:
        """Returns True if audio playback is actively playing through the output device."""
        return self._state == "TTS_PLAYING" or (self._is_speaking and self._state != "TTS_SYNTHESIZING")

    def is_synthesizing(self) -> bool:
        """Returns True if TTS is currently synthesizing speech before playback starts."""
        return self._state == "TTS_SYNTHESIZING"

    def wait_until_finished(self, timeout: float = 10.0) -> bool:
        """Blocks until TTS queue is drained and playback completes, or timeout expires."""
        start = time.time()
        while time.time() - start < timeout:
            if not self.is_speaking():
                return True
            time.sleep(0.05)
        return not self.is_speaking()

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

                if len(item) == 6:
                    item_type, payload, item_job_id, item_gen_id, s_idx, s_total = item
                elif len(item) == 4:
                    item_type, payload, item_job_id, item_gen_id = item
                    s_idx, s_total = 0, 1
                elif len(item) == 3:
                    item_type, payload, item_job_id = item
                    item_gen_id = self._current_generation_id
                    s_idx, s_total = 0, 1
                else:
                    item_type, payload = item
                    item_job_id = None
                    item_gen_id = self._current_generation_id
                    s_idx, s_total = 0, 1

                # Discard items from invalidated generations or superseded jobs
                if item_gen_id != self._current_generation_id or self._interrupt_event.is_set():
                    logger.info(f"Skipping stale TTS item (Item Gen: {item_gen_id}, Active Gen: {self._current_generation_id})")
                    self._queue.task_done()
                    continue

                if item_job_id and self._current_job_id and item_job_id != self._current_job_id:
                    logger.info(f"Skipping superseded TTS job '{item_job_id}' (Current: '{self._current_job_id}')")
                    self._queue.task_done()
                    continue

                self._interrupt_event.clear()
                temp_file_to_clean = None
                self._last_playback_success = False

                self._current_sentence_idx = s_idx
                self._total_sentences = s_total
                self._current_sentence_text = payload if item_type == "text" else ""

                try:
                    if item_type == "text":
                        self._state = "TTS_SYNTHESIZING"
                        if self.on_start_synthesizing_cb:
                            self._trigger_callback(self.on_start_synthesizing_cb)
                        logger.info(f"[TTS_SYNTHESIS_STARTED][{item_job_id}][Gen {item_gen_id}][{s_idx+1}/{s_total}] Text: '{payload}'")
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
                            if not temp_file_to_clean and not self._interrupt_event.is_set() and item_gen_id == self._current_generation_id:
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

                        # Double check generation has not been cancelled during synthesis
                        if self._interrupt_event.is_set() or item_gen_id != self._current_generation_id:
                            logger.info(f"[TTS_CANCELLED_MID_SYNTH] Generation {item_gen_id} cancelled during synthesis.")
                            continue

                        if audio_file_to_play:
                            logger.info(f"[TTS_SYNTHESIS_FINISHED][{item_job_id}] Succeeded in {synth_ms:.1f}ms -> {audio_file_to_play}")
                            if not self._interrupt_event.is_set() and item_gen_id == self._current_generation_id:
                                self._state = "TTS_PLAYING"
                                self._is_speaking = True
                                self._trigger_callback(self.on_start_speaking_cb)
                                if item_job_id:
                                    self._last_playback_success = self._play_audio_file(audio_file_to_play, item_job_id, synth_ms=synth_ms, gen_id=item_gen_id)
                                else:
                                    self._last_playback_success = self._play_audio_file(audio_file_to_play)

                                # Sentence progress is recorded only after the corresponding sentence actually finishes
                                if self._last_playback_success and self.on_sentence_progress_cb:
                                    self._trigger_callback(self.on_sentence_progress_cb, s_idx, s_total, payload)
                        else:
                            logger.error(f"[TTS_SYNTHESIS_FAILED][{item_job_id}] All TTS providers failed to synthesize audio.")

                    elif item_type in ["file", "temp_file"]:
                        temp_file_to_clean = payload if item_type == "temp_file" else None
                        if not self._interrupt_event.is_set() and item_gen_id == self._current_generation_id:
                            self._state = "TTS_PLAYING"
                            self._is_speaking = True
                            self._trigger_callback(self.on_start_speaking_cb)
                            if item_job_id:
                                self._last_playback_success = self._play_audio_file(payload, item_job_id, gen_id=item_gen_id)
                            else:
                                self._last_playback_success = self._play_audio_file(payload, gen_id=item_gen_id)

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

    def _play_audio_file(self, file_path: str, job_id: Optional[str] = None, synth_ms: float = 0.0, gen_id: Optional[int] = None) -> bool:
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

                    # Ensure float32 format and correct integer-to-float normalization
                    if np.issubdtype(audio_data.dtype, np.integer):
                        max_possible = float(np.iinfo(audio_data.dtype).max)
                        audio_data = audio_data.astype(np.float32) / max_possible
                    elif audio_data.dtype != np.float32:
                        audio_data = audio_data.astype(np.float32)

                    # Dynamic peak normalization to avoid DAC clipping distortion
                    peak = float(np.max(np.abs(audio_data))) if audio_data.size > 0 else 0.0
                    if peak > 1.0:
                        audio_data = audio_data / peak

                    # Calibrated comfortable master playback volume (default 0.70 for gentle listening)
                    playback_vol = float(getattr(config, "playback_volume", 0.70))
                    playback_vol = max(0.05, min(1.0, playback_vol))
                    audio_data = audio_data * playback_vol

                    # Mark speaking state and trigger callback at start of audio playback
                    self._is_speaking = True
                    self._trigger_callback(self.on_start_speaking_cb)

                    sd.play(audio_data, samplerate=sample_rate)
                    
                    # Compute chunk-by-chunk amplitude for UI pulsation
                    chunk_size = int(sample_rate * 0.03)  # ~30ms
                    num_samples = len(audio_data)
                    pos = 0

                    while pos < num_samples and not self._interrupt_event.is_set() and (gen_id is None or gen_id == self._current_generation_id):
                        chunk = audio_data[pos:pos + chunk_size]
                        if len(chunk) > 0:
                            rms = float(np.sqrt(np.mean(chunk**2)))
                            amp = min(1.0, rms * 4.0)
                            if self.on_audio_amplitude_cb:
                                self._trigger_callback(self.on_audio_amplitude_cb, amp)
                        pos += chunk_size
                        time.sleep(0.03)

                    if self._interrupt_event.is_set() or (gen_id is not None and gen_id != self._current_generation_id):
                        sd.stop()
                        logger.info(f"[AUDIO_PLAYBACK_INTERRUPTED][{uid}] Playback stopped mid-stream in <30ms.")
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
