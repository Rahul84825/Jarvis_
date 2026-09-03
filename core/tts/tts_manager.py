import os
import time
import queue
import logging
import threading
import sounddevice as sd
import av
from pathlib import Path
from typing import Optional, Dict

from config import config
from core.tts.base_tts import BaseTTS
from core.tts.providers.edge_tts_provider import EdgeTTSProvider
from core.tts.providers.windows_sapi_provider import WindowsSAPIProvider
from core.tts.providers.pyttsx3_provider import Pyttsx3Provider
from core.tts.providers.gtts_provider import GTTSProvider

logger = logging.getLogger("Jarvis.TTSManager")

class TTSManager:
    """Central Queue-based, Multi-Provider TTS Manager.
    Manages active provider, speech FIFO queue, audio streaming, instant interruption,
    automatic multi-tier fallback, and completion tracking callbacks.
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

        # Providers
        self._providers: Dict[str, BaseTTS] = {
            "edge": EdgeTTSProvider(),
            "sapi": WindowsSAPIProvider(),
            "windows": WindowsSAPIProvider(),
            "pyttsx3": Pyttsx3Provider(),
            "gtts": GTTSProvider()
        }
        self._active_provider_key = getattr(config, "tts_provider", "edge")

        # Callbacks
        self.on_start_speaking_cb = None
        self.on_stop_speaking_cb = None

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

    def start(self, on_start_speaking=None, on_stop_speaking=None):
        """Starts background worker thread."""
        with self._lock:
            if self._running:
                return

            if on_start_speaking is not None:
                self.on_start_speaking_cb = on_start_speaking
            if on_stop_speaking is not None:
                self.on_stop_speaking_cb = on_stop_speaking

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

    def speak(self, text: str, interrupt: bool = True):
        """Enqueues text for TTS synthesis and audio playback."""
        if not text or not text.strip():
            return

        if interrupt:
            self.interrupt()

        logger.info(f"[TTS_STARTED] Enqueuing speech: '{text}' (Interrupt={interrupt})")
        self._queue.put(("text", text))

    def play_wav(self, file_path: str, interrupt: bool = True):
        """Enqueues an audio file for playback."""
        if interrupt:
            self.interrupt()
        logger.info(f"Enqueuing audio file playback: {file_path}")
        self._queue.put(("file", file_path))

    def interrupt(self):
        """Halts active audio output and flushes the queue."""
        logger.info("Speech interruption requested. Clearing queue.")
        self._interrupt_event.set()

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
        return self._is_speaking

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

    def _process_queue(self):
        while self._running:
            try:
                self._interrupt_event.clear()
                item = self._queue.get(timeout=0.1)
                if item is None:
                    break

                item_type, payload = item
                self._is_speaking = True
                self._trigger_callback(self.on_start_speaking_cb)

                temp_file_to_clean = None
                try:
                    if item_type == "text":
                        # 1. Try primary active provider
                        primary_p = self.provider
                        try:
                            temp_file_to_clean = primary_p.synthesize_to_file(payload)
                        except Exception as prim_err:
                            logger.warning(f"Primary TTS provider '{primary_p.get_name()}' failed: {prim_err}")
                            temp_file_to_clean = None

                        # 2. If failed, attempt fallback providers
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

                        if temp_file_to_clean and not self._interrupt_event.is_set():
                            self._play_audio_file(temp_file_to_clean)

                    elif item_type in ["file", "temp_file"]:
                        temp_file_to_clean = payload if item_type == "temp_file" else None
                        self._play_audio_file(payload)

                except Exception as e:
                    logger.error(f"Error in TTS processing: {e}", exc_info=True)
                finally:
                    if temp_file_to_clean:
                        self._delete_file_safely(temp_file_to_clean)

                    self._is_speaking = False
                    logger.info("[TTS_FINISHED] Speech output completed.")
                    self._trigger_callback(self.on_stop_speaking_cb)
                    self._queue.task_done()

            except queue.Empty:
                continue

    def _play_audio_file(self, file_path: str):
        played_successfully = False
        container = None
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

                audio_stream = sd.OutputStream(
                    samplerate=sample_rate,
                    channels=channels,
                    dtype=dtype
                )

                with self._lock:
                    self._current_player_stream = audio_stream

                audio_stream.start()

                for frame in container.decode(stream):
                    if self._interrupt_event.is_set():
                        logger.info("Playback streaming interrupted.")
                        break

                    arr = frame.to_ndarray()
                    if len(arr.shape) > 1 and arr.shape[0] == channels:
                        arr = arr.T

                    audio_stream.write(arr)

                audio_stream.stop()
                audio_stream.close()
                played_successfully = True

        except Exception as e:
            logger.warning(f"PyAV/sounddevice playback encountered an issue for {file_path}: {e}")
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
                    logger.info("Playing audio via native Windows PlaySound fallback.")
                    winsound.PlaySound(file_path, winsound.SND_FILENAME)
            except Exception as ws_err:
                logger.error(f"Winsound fallback playback failed: {ws_err}")

    def _delete_file_safely(self, path: str):
        try:
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
