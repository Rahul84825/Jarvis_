import os
import time
import queue
import shutil
import hashlib
import logging
import threading
import sounddevice as sd
import av
from pathlib import Path
from typing import Optional, Dict

from config import config
from core.tracing import tracer
from core.tts.base_tts import BaseTTS
from core.tts.providers.edge_tts_provider import EdgeTTSProvider
from core.tts.providers.windows_sapi_provider import WindowsSAPIProvider
from core.tts.providers.pyttsx3_provider import Pyttsx3Provider
from core.tts.providers.gtts_provider import GTTSProvider

logger = logging.getLogger("Jarvis.TTSManager")

class TTSManager:
    """Central Queue-based, Multi-Provider TTS Manager.
    Manages active provider, speech FIFO queue, audio streaming, instant interruption,
    automatic multi-tier fallback, disk cache, and completion tracking callbacks.
    """

    def __init__(self):
        self._queue = queue.Queue()
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        # State machine: IDLE -> TTS_PENDING -> TTS_SYNTHESIZING -> TTS_PLAYING -> IDLE
        self._state = "IDLE"
        self._interrupt_event = threading.Event()
        self._current_player_stream = None
        self._is_speaking = False

        # Providers
        self._providers: Dict[str, BaseTTS] = {
            "edge": EdgeTTSProvider(),
            "sapi": WindowsSAPIProvider(),
            "windows": WindowsSAPIProvider(),
            "pyttsx3": Pyttsx3Provider(),
            "gtts": GTTSProvider()
        }
        self._active_provider_key = getattr(config, "tts_provider", "edge")

        # Cache directory
        self._cache_dir = config.BASE_DIR / "logs" / "tts_cache"
        try:
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            logger.warning(f"Could not initialize TTS cache directory: {e}")

        # Callbacks
        self.on_start_synthesizing_cb = None
        self.on_start_speaking_cb = None
        self.on_stop_speaking_cb = None

    @property
    def state(self) -> str:
        return self._state

    def is_synthesizing(self) -> bool:
        return self._state == "TTS_SYNTHESIZING"

    def is_playing(self) -> bool:
        return self._state == "TTS_PLAYING"

    def is_speaking(self) -> bool:
        return self._state in ["TTS_PENDING", "TTS_SYNTHESIZING", "TTS_PLAYING"]

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

    def start(self, on_start_speaking=None, on_stop_speaking=None, on_start_synthesizing=None):
        """Starts background worker thread."""
        with self._lock:
            if self._running:
                return

            if on_start_speaking is not None:
                self.on_start_speaking_cb = on_start_speaking
            if on_stop_speaking is not None:
                self.on_stop_speaking_cb = on_stop_speaking
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
        self.interrupt(force=True)
        with self._lock:
            self._running = False
            self._queue.put(None)

        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        self._state = "IDLE"
        self._is_speaking = False
        logger.info("TTSManager Subsystem stopped.")

    def _resolve_output_device(self) -> Optional[int]:
        """Resolves the configured or system default audio output device."""
        cfg_dev = getattr(config, "audio_output_device", None)
        if cfg_dev is not None:
            try:
                dev_idx = int(cfg_dev)
                devices = sd.query_devices()
                if 0 <= dev_idx < len(devices) and devices[dev_idx]['max_output_channels'] > 0:
                    return dev_idx
            except (ValueError, TypeError):
                pass
            try:
                devices = sd.query_devices()
                for idx, d in enumerate(devices):
                    if d['max_output_channels'] > 0 and str(cfg_dev).lower() in d['name'].lower():
                        return idx
            except Exception:
                pass

        try:
            default_out = sd.default.device[1]
            if default_out is not None and default_out >= 0:
                devices = sd.query_devices()
                if default_out < len(devices) and devices[default_out]['max_output_channels'] > 0:
                    return default_out
        except Exception:
            pass

        return None

    def speak(self, text: str, interrupt: bool = True):
        """Enqueues text for TTS synthesis and audio playback with timeline tracking."""
        if not text or not text.strip():
            return

        t0 = time.time()
        trace = tracer.get_current_trace()
        if trace and "response_ready" not in trace.timestamps:
            trace.record_timestamp("response_ready", t0)

        logger.info(f"[TTS-DEBUG] request received (interrupt={interrupt})")
        logger.info(f"[TTS-DEBUG] text: '{text}'")
        logger.info(f"[TTS_REQUEST] t0={t0:.4f} text='{text}'")

        if interrupt and (self.is_speaking() or not self._queue.empty()):
            self.interrupt(force=True)

        self._state = "TTS_PENDING"
        t1 = time.time()
        logger.info(f"[TTS_QUEUE] t1={t1:.4f} queue_latency={(t1 - t0)*1000:.1f}ms")
        self._queue.put(("text", text, t0, t1))

    def play_wav(self, file_path: str, interrupt: bool = True):
        """Enqueues an audio file for playback with timeline tracking."""
        t0 = time.time()
        logger.info(f"[TTS-DEBUG] request received (interrupt={interrupt})")
        logger.info(f"[TTS-DEBUG] text: '[AUDIO FILE: {file_path}]'")
        logger.info(f"[TTS_REQUEST] t0={t0:.4f} file='{file_path}'")

        if interrupt and (self.is_speaking() or not self._queue.empty()):
            self.interrupt(force=True)

        self._state = "TTS_PENDING"
        t1 = time.time()
        logger.info(f"[TTS_QUEUE] t1={t1:.4f} queue_latency={(t1 - t0)*1000:.1f}ms")
        self._queue.put(("file", file_path, t0, t1))

    def interrupt(self, force: bool = False, from_vad: bool = False):
        """Halts active audio output and flushes the queue.
        Guards pending synthesis from accidental ambient noise cancellation when from_vad=True.
        """
        if from_vad and self._state in ["TTS_PENDING", "TTS_SYNTHESIZING"] and not force:
            logger.info(f"[TTS_INTERRUPT] Suppressing interrupt during {self._state} state (shielding pending response from ambient noise).")
            return

        logger.info(f"Speech interruption requested (force={force}, current_state={self._state}). Clearing queue.")
        self._interrupt_event.set()

        with self._lock:
            if self._current_player_stream:
                try:
                    self._current_player_stream.stop()
                except Exception as e:
                    logger.debug(f"Error stopping audio stream on interrupt: {e}")

        self.clear_queue()
        if self._state == "TTS_PLAYING" or force:
            self._state = "IDLE"
            self._is_speaking = False

    def clear_queue(self):
        """Empties pending speech items in queue."""
        try:
            while not self._queue.empty():
                item = self._queue.get_nowait()
                if item and len(item) >= 2 and item[0] in ["temp_file", "file"]:
                    self._delete_file_safely(item[1])
                self._queue.task_done()
        except queue.Empty:
            pass

    def wait_until_finished(self, timeout: float = 10.0):
        """Blocks until current speech completes or timeout expires."""
        t0 = time.time()
        while self.is_speaking() or not self._queue.empty():
            if time.time() - t0 > timeout:
                break
            time.sleep(0.05)

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

    # ==========================================
    # CACHE MANAGEMENT
    # ==========================================
    def _get_cache_path(self, text: str, provider_key: str, voice: str, rate: str) -> Path:
        token = f"{provider_key}_{voice}_{rate}_{text.strip()}".encode('utf-8')
        h = hashlib.sha256(token).hexdigest()[:24]
        ext = ".mp3" if provider_key in ["edge", "gtts"] else ".wav"
        return self._cache_dir / f"tts_{h}{ext}"

    def _check_cache(self, text: str, provider_key: str, voice: str, rate: str) -> Optional[str]:
        if not getattr(config, "tts_cache_enabled", True):
            return None
        try:
            cache_path = self._get_cache_path(text, provider_key, voice, rate)
            if cache_path.exists():
                if cache_path.stat().st_size > 0:
                    logger.info(f"[TTS_CACHE_HIT] Using cached audio for '{text[:30]}...' -> {cache_path.name}")
                    return str(cache_path)
                else:
                    # Clean up corrupted 0-byte cache file
                    logger.warning(f"[TTS_CACHE] Removing corrupted 0-byte cache file: {cache_path.name}")
                    cache_path.unlink(missing_ok=True)
        except Exception as e:
            logger.debug(f"[TTS_CACHE] Error checking cache: {e}")
        return None

    def _save_to_cache(self, source_path: str, text: str, provider_key: str, voice: str, rate: str):
        if not getattr(config, "tts_cache_enabled", True) or not source_path:
            return
        try:
            if not os.path.exists(source_path) or os.path.getsize(source_path) == 0:
                return
            cache_path = self._get_cache_path(text, provider_key, voice, rate)
            shutil.copyfile(source_path, cache_path)
            logger.info(f"[TTS_CACHE_MISS] Saved newly synthesized audio to cache: {cache_path.name}")
            self._prune_cache(max_items=200)
        except Exception as e:
            logger.debug(f"[TTS_CACHE] Error writing to cache: {e}")

    def _prune_cache(self, max_items: int = 200):
        try:
            cached_files = sorted(self._cache_dir.glob("tts_*"), key=lambda f: f.stat().st_mtime)
            while len(cached_files) > max_items:
                oldest = cached_files.pop(0)
                try:
                    oldest.unlink(missing_ok=True)
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"[TTS_CACHE] Error pruning cache: {e}")

    # ==========================================
    # WORKER QUEUE PROCESSOR
    # ==========================================
    def _process_queue(self):
        while self._running:
            try:
                item = self._queue.get(timeout=0.1)
                if item is None:
                    break

                self._interrupt_event.clear()

                # Extract payload and timeline timestamps
                if len(item) == 4:
                    item_type, payload, t0, t1 = item
                else:
                    item_type, payload = item[0], item[1]
                    t0 = time.time()
                    t1 = t0

                t2 = time.time()
                primary_p = self.provider
                logger.info(f"[TTS-DEBUG] provider selected: {primary_p.get_name()}")
                logger.info(f"[TTS_PROVIDER_SELECTED] t2={t2:.4f} provider='{primary_p.get_name()}' queue_latency={(t2 - t1)*1000:.1f}ms")

                trace = tracer.get_current_trace()
                if trace:
                    trace.record_timestamp("tts_provider_selected", t2)
                    trace.playback_info["provider"] = primary_p.get_name()

                self._state = "TTS_SYNTHESIZING"
                self._is_speaking = True
                self._trigger_callback(self.on_start_synthesizing_cb)

                temp_file_to_clean = None
                audio_file_to_play = None
                from_cache = False

                t3 = time.time()
                if trace:
                    trace.record_timestamp("tts_synthesis_start", t3)
                logger.info("[TTS-DEBUG] synthesis started")
                logger.info(f"[TTS_SYNTHESIS_START] t3={t3:.4f}")

                try:
                    if item_type == "text":
                        voice = getattr(config, "tts_voice", "en-US-GuyNeural")
                        rate = getattr(config, "tts_rate", "+0%")
                        p_key = getattr(config, "tts_provider", self._active_provider_key).lower()

                        # 1. Check disk cache first
                        cached_audio = self._check_cache(payload, p_key, voice, rate)
                        if cached_audio:
                            audio_file_to_play = cached_audio
                            from_cache = True
                        else:
                            # 2. Synthesize using primary provider
                            try:
                                temp_file_to_clean = primary_p.synthesize_to_file(payload)
                            except Exception as prim_err:
                                logger.warning(f"Primary TTS provider '{primary_p.get_name()}' failed: {prim_err}")
                                temp_file_to_clean = None

                            # 3. Automatic local fallback if primary fails, times out, or returns None
                            if not temp_file_to_clean and not self._interrupt_event.is_set():
                                # Prioritize local Windows SAPI fallback
                                fallback_order = ["sapi", "windows", "pyttsx3", "gtts"]
                                for fb_key in fallback_order:
                                    fb_provider = self._providers.get(fb_key)
                                    if fb_provider and fb_provider is not primary_p:
                                        try:
                                            logger.info(f"[TTS_FALLBACK] Attempting fallback TTS synthesis with: {fb_provider.get_name()}")
                                            temp_file_to_clean = fb_provider.synthesize_to_file(payload)
                                            if temp_file_to_clean:
                                                logger.info(f"[TTS_FALLBACK] Fallback TTS synthesis succeeded using: {fb_provider.get_name()}")
                                                p_key = fb_key
                                                if trace:
                                                    trace.playback_info["provider"] = f"{fb_provider.get_name()} (Fallback)"
                                                break
                                        except Exception as fb_err:
                                            logger.debug(f"[TTS_FALLBACK] Provider '{fb_provider.get_name()}' failed: {fb_err}")

                            if temp_file_to_clean:
                                audio_file_to_play = temp_file_to_clean
                                # Save to disk cache for future instant playback
                                self._save_to_cache(temp_file_to_clean, payload, p_key, voice, rate)

                    elif item_type in ["file", "temp_file"]:
                        audio_file_to_play = payload
                        if item_type == "temp_file":
                            temp_file_to_clean = payload

                    t4 = time.time()
                    file_exists = os.path.exists(audio_file_to_play) if audio_file_to_play else False
                    file_size = os.path.getsize(audio_file_to_play) if (audio_file_to_play and file_exists) else 0
                    if trace:
                        trace.record_timestamp("tts_synthesis_end", t4)
                        trace.playback_info["file_exists"] = file_exists
                        trace.playback_info["file_size"] = file_size
                        trace.playback_info["from_cache"] = from_cache
                        trace.playback_info["file_path"] = audio_file_to_play or ""

                    logger.info("[TTS-DEBUG] synthesis completed")
                    logger.info(f"[TTS-DEBUG] generated audio path: {audio_file_to_play}")
                    logger.info(f"[TTS-DEBUG] file exists: {file_exists}")
                    logger.info(f"[TTS-DEBUG] file size: {file_size} bytes")
                    logger.info(f"[TTS_SYNTHESIS_END] t4={t4:.4f} synthesis_latency={(t4 - t3)*1000:.1f}ms (from_cache={from_cache})")

                    # Play audio if available and not interrupted
                    if audio_file_to_play and not self._interrupt_event.is_set():
                        self._state = "TTS_PLAYING"
                        self._trigger_callback(self.on_start_speaking_cb)
                        logger.info("[TTS-DEBUG] playback callback fired")

                        t5 = time.time()
                        playback_startup = (t5 - t4) * 1000
                        time_to_first_audio = (t5 - t0) * 1000
                        logger.info(f"[TTS_PLAYBACK_START] t5={t5:.4f} playback_startup_latency={playback_startup:.1f}ms | time_to_first_audio={time_to_first_audio:.1f}ms")

                        self._play_audio_file(audio_file_to_play)

                        t6 = time.time()
                        playback_latency = (t6 - t5) * 1000
                        total_tts = (t6 - t0) * 1000
                        logger.info(f"[TTS_PLAYBACK_END] t6={t6:.4f} playback_latency={playback_latency:.1f}ms | total_tts_latency={total_tts:.1f}ms")

                except Exception as e:
                    if trace:
                        trace.playback_info["exception"] = str(e)
                    logger.error(f"[TTS-DEBUG] playback exception: Error in TTS processing: {e}", exc_info=True)
                finally:
                    if temp_file_to_clean and not from_cache:
                        self._delete_file_safely(temp_file_to_clean)

                    self._is_speaking = False
                    if self._queue.empty():
                        self._state = "IDLE"
                    logger.info("[TTS_FINISHED] Speech output completed.")
                    self._trigger_callback(self.on_stop_speaking_cb)
                    if trace:
                        tracer.end_trace(trace.correlation_id, status="COMPLETED")
                    self._queue.task_done()

            except queue.Empty:
                continue

    def _play_audio_file(self, file_path: str):
        t_play_req = time.time()
        logger.info("[TTS-DEBUG] playback requested")
        out_dev = self._resolve_output_device()
        out_dev_name = "System Default"
        if out_dev is not None:
            try:
                out_dev_name = sd.query_devices(out_dev)['name']
            except Exception:
                out_dev_name = str(out_dev)
        logger.info(f"[TTS-DEBUG] output device: {out_dev} ({out_dev_name})")

        file_exists = os.path.exists(file_path) if file_path else False
        file_size = os.path.getsize(file_path) if file_exists else 0
        logger.info(f"[TTS-DEBUG] file exists: {file_exists}")
        logger.info(f"[TTS-DEBUG] file size: {file_size} bytes")

        trace = tracer.get_current_trace()
        if trace:
            trace.record_timestamp("playback_init", t_play_req)
            trace.playback_info["output_device_idx"] = out_dev
            trace.playback_info["output_device_name"] = out_dev_name
            trace.playback_info["playback_initialized"] = True

        if not file_exists or file_size == 0:
            if trace:
                trace.playback_info["exception"] = f"Missing or empty audio file: {file_path}"
            logger.error(f"[TTS-DEBUG] playback exception: Missing or empty audio file: {file_path}")
            return

        played_successfully = False
        container = None
        t_play_start = None
        try:
            container = av.open(file_path)
            if container.streams.audio:
                stream = container.streams.audio[0]
                sample_rate = stream.codec_context.sample_rate
                channels = stream.codec_context.channels
                codec_format = stream.codec_context.format.name

                dtype = 'float32'
                if "flt" in codec_format:
                    dtype = 'float32'
                elif "s16" in codec_format:
                    dtype = 'int16'
                elif "u8" in codec_format:
                    dtype = 'uint8'

                logger.info(f"[TTS-AUDIO-FORMAT] sample_rate={sample_rate}Hz channels={channels} codec={stream.codec_context.name} format={codec_format} dtype={dtype}")

                audio_stream = sd.OutputStream(
                    samplerate=sample_rate,
                    channels=channels,
                    dtype=dtype,
                    device=out_dev
                )

                with self._lock:
                    self._current_player_stream = audio_stream

                audio_stream.start()
                t_play_start = time.time()
                if trace:
                    trace.record_timestamp("playback_start", t_play_start)
                    trace.playback_info["playback_started"] = True
                logger.info("[TTS-DEBUG] playback started")

                for frame in container.decode(stream):
                    if self._interrupt_event.is_set():
                        logger.info("[TTS-DEBUG] playback cancelled: Interrupted during streaming")
                        if trace:
                            trace.playback_info["playback_cancelled"] = True
                        break

                    arr = frame.to_ndarray()
                    if len(arr.shape) > 1 and arr.shape[0] == channels:
                        arr = arr.T

                    audio_stream.write(arr)

                # Allow buffered hardware audio frames to drain before stopping
                if not self._interrupt_event.is_set():
                    time.sleep(0.12)
                audio_stream.stop()
                audio_stream.close()
                played_successfully = not self._interrupt_event.is_set()
                if trace:
                    trace.record_timestamp("playback_end", time.time())
                    trace.playback_info["playback_completed"] = played_successfully

        except Exception as e:
            logger.warning(f"[TTS-DEBUG] playback exception: PyAV/sounddevice streaming issue for {file_path}: {e}")
        finally:
            if container:
                try:
                    container.close()
                except Exception:
                    pass
            with self._lock:
                self._current_player_stream = None

        # Fallback to winsound for WAV files if PyAV/sounddevice encountered issues
        if not played_successfully and not self._interrupt_event.is_set():
            try:
                import winsound
                if file_path.lower().endswith(".wav"):
                    logger.info("Attempting native Windows PlaySound fallback...")
                    t_play_start = t_play_start or time.time()
                    logger.info("[TTS-DEBUG] playback started")
                    winsound.PlaySound(file_path, winsound.SND_FILENAME)
                    played_successfully = True
            except Exception as ws_err:
                logger.error(f"[TTS-DEBUG] playback exception: Winsound fallback playback failed: {ws_err}")

        t_play_finish = time.time()
        playback_duration = t_play_finish - (t_play_start or t_play_req)
        logger.info(f"[TTS-DEBUG] playback duration: {playback_duration:.2f}s")
        logger.info("[TTS-DEBUG] playback finished")

    def _delete_file_safely(self, path: str):
        try:
            # Never delete files from cache directory
            if str(self._cache_dir) in path:
                return
            if os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.debug(f"Could not remove file {path}: {e}")

    def _trigger_callback(self, cb):
        if cb:
            try:
                threading.Thread(target=cb, name="TTSCallbackThread", daemon=True).start()
            except Exception as e:
                logger.error(f"Error triggering TTS callback: {e}")
