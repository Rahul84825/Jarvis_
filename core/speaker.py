import os
import time
import queue
import logging
import tempfile
import threading
import numpy as np
import sounddevice as sd
import av
from config import config

logger = logging.getLogger("Jarvis.Speaker")

class Speaker:
    """Queue-based, interruptible Speech Output Manager.
    Integrates with Edge TTS for natural voice generation and uses PyAV to decode
    audio files (MP3/WAV) to stream them chunk-by-chunk to the soundcard.
    Supports instant interruption by checking an interrupt flag during playback.
    """
    
    def __init__(self):
        self._queue = queue.Queue()
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        
        # Interruption and playback states
        self._interrupt_event = threading.Event()
        self._current_player_stream = None
        self._is_speaking = False
        
        # Callbacks
        self.on_start_speaking_cb = None
        self.on_stop_speaking_cb = None

    def start(self, on_start_speaking=None, on_stop_speaking=None):
        """Starts the background speaker queue worker thread."""
        with self._lock:
            if self._running:
                logger.warning("Speaker is already running.")
                return
            
            if on_start_speaking is not None:
                self.on_start_speaking_cb = on_start_speaking
            if on_stop_speaking is not None:
                self.on_stop_speaking_cb = on_stop_speaking
            self._running = True
            self._interrupt_event.clear()
            self._thread = threading.Thread(target=self._process_queue, name="SpeakerThread", daemon=True)
            self._thread.start()
            logger.info("Speaker Subsystem initialized.")

    def stop(self):
        """Stops the speaker worker and halts active speech."""
        logger.info("Stopping Speaker Subsystem.")
        self.interrupt()
        
        with self._lock:
            self._running = False
            self._queue.put(None)
            
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("Speaker Subsystem stopped.")

    def speak(self, text: str, interrupt=True):
        """Synthesizes text using Edge TTS and adds it to the queue.
        
        Args:
            text: The text string to speak.
            interrupt: If True, halts any active speaking and clears the queue.
        """
        if not text:
            return
            
        if interrupt:
            self.interrupt()
            
        logger.info(f"Queueing speech: '{text}' (Interrupt={interrupt})")
        self._queue.put(("text", text))

    def play_wav(self, file_path: str, interrupt=True):
        """Queues an audio file (WAV/MP3) for playback.
        
        Args:
            file_path: Absolute path to the audio file.
            interrupt: If True, halts active playback and clears the queue.
        """
        if interrupt:
            self.interrupt()
            
        logger.info(f"Queueing audio playback: {file_path}")
        self._queue.put(("file", file_path))

    def interrupt(self):
        """Instantly halts current audio output, flushes the queue, and resets flags."""
        logger.info("Speech interruption requested. Flushing queue.")
        self._interrupt_event.set()
        
        with self._lock:
            if self._current_player_stream:
                try:
                    self._current_player_stream.stop()
                except Exception as e:
                    logger.debug(f"Error stopping stream on interrupt: {e}")
                    
        # Flush queue
        try:
            while not self._queue.empty():
                item = self._queue.get_nowait()
                if item and item[0] == "temp_file":
                    # Delete orphaned temp files
                    self._delete_file_safely(item[1])
                self._queue.task_done()
        except queue.Empty:
            pass

    def is_speaking(self) -> bool:
        """Returns True if the speaker is currently outputting sound."""
        return self._is_speaking

    def _process_queue(self):
        """Queue processor loop executing on a background thread."""
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
                        # Synthesize text asynchronously using Edge TTS
                        temp_file_to_clean = self._synthesize_tts_to_temp_file(payload)
                        if temp_file_to_clean and not self._interrupt_event.is_set():
                            self._play_audio_file(temp_file_to_clean)
                    elif item_type == "file":
                        self._play_audio_file(payload)
                    elif item_type == "temp_file":
                        temp_file_to_clean = payload
                        self._play_audio_file(payload)
                except Exception as e:
                    logger.error(f"Error in speaker execution: {e}", exc_info=True)
                finally:
                    if temp_file_to_clean:
                        self._delete_file_safely(temp_file_to_clean)
                        
                    self._is_speaking = False
                    self._trigger_callback(self.on_stop_speaking_cb)
                    self._queue.task_done()
                    
            except queue.Empty:
                continue

    def _synthesize_tts_to_temp_file(self, text: str) -> str:
        """Downloads voice synthesis from Edge TTS and writes to a temporary MP3 file."""
        import asyncio
        import edge_tts
        
        logger.info(f"Synthesizing speech via Edge TTS (Voice: {config.tts_voice}): '{text}'")
        
        # Set up temporary file path
        fd, temp_path = tempfile.mkstemp(suffix=".mp3", prefix="jarvis_tts_")
        os.close(fd)
        
        async def run_synthesis():
            communicate = edge_tts.Communicate(text, config.tts_voice, rate=config.tts_rate)
            await communicate.save(temp_path)
            
        try:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    executor.submit(asyncio.run, run_synthesis()).result()
            else:
                loop.run_until_complete(run_synthesis())
                
            logger.debug(f"Edge TTS synthesis written to: {temp_path}")
            return temp_path
        except Exception as e:
            logger.error(f"Edge TTS synthesis failed: {e}", exc_info=True)
            self._delete_file_safely(temp_path)
            return None

    def _play_audio_file(self, file_path: str):
        """Decodes WAV/MP3 files using PyAV and streams them chunk-by-chunk to sounddevice.
        Supports instant interruption by polling the interrupt event at each chunk write.
        """
        logger.info(f"Streaming audio file: {file_path}")
        container = None
        try:
            container = av.open(file_path)
            if not container.streams.audio:
                logger.warning(f"Audio file contains no audio streams: {file_path}")
                return
                
            stream = container.streams.audio[0]
            sample_rate = stream.codec_context.sample_rate
            channels = stream.codec_context.channels
            codec_format = stream.codec_context.format.name
            
            # Determine correct numpy data type
            if "flt" in codec_format:
                dtype = 'float32'
            elif "s16" in codec_format:
                dtype = 'int16'
            elif "u8" in codec_format:
                dtype = 'uint8'
            else:
                dtype = 'float32' # default fallback
                
            # Initialize sounddevice Output Stream matching native audio file formats
            audio_stream = sd.OutputStream(
                samplerate=sample_rate,
                channels=channels,
                dtype=dtype
            )
            
            with self._lock:
                self._current_player_stream = audio_stream
                
            audio_stream.start()
            
            # Decode frames and stream in real-time
            for frame in container.decode(stream):
                if self._interrupt_event.is_set():
                    logger.info("Audio streaming interrupted.")
                    break
                    
                arr = frame.to_ndarray()
                
                # Check formatting: sounddevice expects (samples, channels) shape
                if len(arr.shape) > 1:
                    # PyAV planar formats (like fltp) return shape (channels, samples)
                    if arr.shape[0] == channels:
                        arr = arr.T
                        
                # Write to soundcard output buffer
                audio_stream.write(arr)
                
            audio_stream.stop()
            audio_stream.close()
            
        except Exception as e:
            logger.error(f"Failed to play audio file {file_path}: {e}", exc_info=True)
        finally:
            if container:
                try:
                    container.close()
                except Exception:
                    pass
            with self._lock:
                self._current_player_stream = None

    def _delete_file_safely(self, path: str):
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.debug(f"Cleaned up temporary audio file: {path}")
        except Exception as e:
            logger.warning(f"Failed to delete temp file {path}: {e}")

    def _trigger_callback(self, cb):
        if cb:
            try:
                threading.Thread(target=cb, name="SpeakerCallbackThread", daemon=True).start()
            except Exception as e:
                logger.error(f"Error executing speaker callback: {e}")
