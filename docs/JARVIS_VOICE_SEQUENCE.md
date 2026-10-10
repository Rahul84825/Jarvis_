# JARVIS Voice Command Execution Sequence

## 1. Overview & Pipeline Lifecycle

This sequence diagram illustrates the complete chronological path of a voice command from acoustic vibration at the microphone to spoken audio response through the sound card.

- **Confirmed [CONFIRMED]**: Verified by code inspection and runtime log tracing.
- **Inferred [INFERRED]**: Timing approximations and edge-case execution paths.

---

## 2. End-to-End Sequence Diagram

```mermaid
sequenceDiagram
    autonumber
    actor User as User Voice
    participant Mic as Microphone / PortAudio
    participant SL as SpeechListener<br/>[core/listener.py]
    participant WW as WakeWordDetector<br/>[core/wakeword.py]
    participant JR as JarvisRuntime<br/>[core/jarvis_runtime.py]
    participant UI as MainWindow (PyQt6)<br/>[ui/main_window.py]
    participant STT as SpeechTranscriber<br/>[core/transcriber.py]
    participant CN as CommandNormalizer<br/>[core/command_normalizer.py]
    participant IE as IntentEngine<br/>[core/intent_engine.py]
    participant EX as CommandExecutor<br/>[modules/system/executor.py]
    participant RM as ResponseManager<br/>[core/response_manager.py]
    participant TTS as TTSManager<br/>[core/tts/tts_manager.py]
    participant Spk as Speaker Output<br/>[sounddevice OutputStream]

    %% 1. Wake word or Speech Onset
    Note over User, Mic: Audio Capture & Acoustic Onset
    alt Wake Word Activation
        User ->> Mic: "Hey Jarvis"
        Mic ->> WW: Audio stream chunk
        WW ->> JR: _on_wakeword("jarvis") [CONFIRMED]
        JR ->> TTS: play_wake_chime() [CONFIRMED]
        TTS -->> Spk: winsound.Beep chime (B5, E6)
        JR ->> UI: sig_status_changed("LISTENING") [CONFIRMED]
        JR ->> SL: trigger_manual_recording(manual=True) [CONFIRMED]
    else Background VAD Activation
        User ->> Mic: User begins speaking
        Mic ->> SL: _audio_callback(indata) [CONFIRMED]
        Note over SL: RMS > threshold (0.015)<br/>Copies rolling pre-roll (1.0s)
        SL ->> JR: _on_speech_start() [CONFIRMED]
        JR ->> UI: sig_status_changed("LISTENING") [CONFIRMED]
    end

    %% 2. Audio Capture & Speech-End
    Note over User, SL: User speaks command (e.g. "Open Chrome")
    User ->> Mic: "Open Chrome"
    Mic ->> SL: Audio chunks buffered in _audio_buffer
    User ->> Mic: Silence (user stops speaking)
    Note over SL: Silence detection: RMS < threshold for 0.8s<br/>or max_duration (5.0s) limit reached
    SL ->> SL: _save_and_dispatch() [CONFIRMED]
    Note over SL: Converts float32 to 16-bit PCM WAV<br/>Saves temporary file jarvis_speech_*.wav
    SL ->> JR: _on_speech_end(wav_path) on ListenerSaveThread [CONFIRMED]

    %% 3. Speech Transcription
    Note over JR, STT: STT Transcription Phase
    JR ->> UI: sig_status_changed("TRANSCRIBING") [CONFIRMED]
    JR ->> STT: transcribe(wav_path) [CONFIRMED]
    STT ->> STT: WhisperModel.transcribe(beam_size=1, int8)
    Note over STT: Phonetic & accent regex normalization<br/>Duration: 800ms - 1500ms
    STT -->> JR: "Open Chrome" (confidence=0.98, duration=1.7s) [CONFIRMED]
    JR ->> UI: sig_speech_text_updated("You: Open Chrome") [CONFIRMED]

    %% 4. Command Normalization & Intent Routing
    Note over JR, IE: Normalization & Intent Routing
    JR ->> UI: sig_status_changed("THINKING") [CONFIRMED]
    JR ->> CN: normalize("Open Chrome") [CONFIRMED]
    CN -->> JR: {"normalized": "open chrome", "removed": []}
    JR ->> IE: parse("open chrome") [CONFIRMED]
    Note over IE: Regex matches "open {app}"<br/>Resolves alias: "chrome"
    IE -->> JR: {"intent": "open_app", "action": "open", "target": "chrome"} [CONFIRMED]

    %% 5. Execution Phase
    Note over JR, EX: Tool Execution & Safety Check
    JR ->> UI: sig_status_changed("EXECUTING") [CONFIRMED]
    JR ->> EX: execute(intent_node) [CONFIRMED]
    EX ->> EX: permissions.is_safe_command() & risk check
    EX ->> EX: app_control.open_app("chrome")
    EX -->> JR: {"success": True, "action": "open_app", "message": "Opening Chrome"} [CONFIRMED]
    JR ->> UI: sig_last_action_updated("open_app", True, "Opening Chrome") [CONFIRMED]

    %% 6. Spoken Response Synthesis & Duplex Control
    Note over JR, TTS: Spoken Response Formatting & Playback
    JR ->> RM: local_engine.format_intent_response(...) [CONFIRMED]
    RM ->> RM: get_template("open_app") -> "Sure, opening Chrome."
    RM ->> TTS: speak("Sure, opening Chrome.") [CONFIRMED]
    TTS ->> TTS: Enqueue ("text", "Sure, opening Chrome.", t0, t1)
    
    %% TTS Worker Thread Processing
    Note over TTS: Background TTSThread picks item from FIFO queue
    TTS ->> JR: _on_speaker_synthesizing() [CONFIRMED]
    JR ->> SL: set_speaking_active(True) [CONFIRMED]
    JR ->> UI: sig_status_changed("SYNTHESIZING") [CONFIRMED]
    
    alt TTS Cache Hit
        TTS ->> TTS: _check_cache() -> hits logs/tts_cache/
    else TTS Cloud Synthesis (EdgeTTS)
        TTS ->> TTS: EdgeTTSProvider.synthesize_to_file()
        Note over TTS: Synthesizes MP3 in 300-800ms
    else Cloud Timeout / Fallback (Windows SAPI)
        Note over TTS: EdgeTTS timed out (>2.5s) -> Fallback to Windows SAPI
        TTS ->> TTS: WindowsSAPIProvider.synthesize_to_file()
        Note over TTS: Native offline SpFileStream WAV output
    end

    %% 7. Audio Playback
    TTS ->> JR: _on_speaker_started() [CONFIRMED]
    JR ->> UI: sig_status_changed("SPEAKING") [CONFIRMED]
    TTS ->> Spk: _play_audio_file(audio_path) [CONFIRMED]
    Note over TTS, Spk: PyAV decodes frames -> sd.OutputStream.write(arr)<br/>Physical sound emitted through Realtek / Headphones
    Spk -->> User: "Sure, opening Chrome." (Audible Sound)

    %% 8. Stream Teardown & Standby Return
    TTS ->> Spk: audio_stream.stop() & close() [CONFIRMED]
    TTS ->> JR: _on_speaker_stopped() [CONFIRMED]
    JR ->> SL: set_speaking_active(False) [CONFIRMED]
    JR ->> UI: sig_status_changed("STANDBY") [CONFIRMED]
    JR ->> UI: sig_speech_text_updated("Standby. Say 'Jarvis'...") [CONFIRMED]
```

---

## 3. Thread Concurrency & Execution Contexts

| Stage | Execution Thread | Blocking Nature | Thread Safety Mechanism |
|---|---|---|---|
| **Audio Capture** | PortAudio C-thread / `_audio_callback` | Non-blocking realtime | `self._lock` inside `SpeechListener` |
| **WAV File Serialization** | `ListenerSaveThread` (Daemon) | Short disk write (~10ms) | Independent temporary file name |
| **Whisper STT** | `ListenerSaveThread` (Daemon) | Blocking CPU inference (0.8s-1.5s) | CTranslate2 multithreading (`cpu_threads=4`) |
| **Command & Intent Routing** | `ListenerSaveThread` (Daemon) | Fast synchronous (<5ms) | Read-only regex and dict lookups |
| **Command Execution** | `ListenerSaveThread` (Daemon) | OS subprocess / API call | Thread-isolated |
| **TTS Synthesis & Output** | `TTSThread` (Daemon) | Blocking synthesis & audio streaming | `queue.Queue` FIFO + `_interrupt_event` |
| **UI Updates** | Main GUI Thread (PyQt6) | Asynchronous via Qt Signals | `pyqtSignal` cross-thread slots |
