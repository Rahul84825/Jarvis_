# JARVIS System Architecture & Component Dependency Graph

## 1. Architectural Overview

JARVIS is structured as a layered, modular desktop assistant with duplex audio handling, local-first intelligence routing, and cross-platform operating system automation. The core coordinator (`JarvisRuntime`) acts as the central hub, decoupling audio input/output hardware from cognitive classification and execution layers.

### Component Relationship Legend:
- **[CONFIRMED]**: Verified directly by code analysis and runtime execution paths.
- **[INFERRED]**: Plausible extension points or optional runtime branches.

---

## 2. System Architecture Graph

```mermaid
graph TB
    subgraph UI_Layer ["Presentation & UI Layer"]
        MW["MainWindow (PyQt6)<br/>[ui/main_window.py]"]
        LV["ListeningVisualizer (QPainter)<br/>[ui/main_window.py]"]
        QH["QSignalingLogHandler<br/>[ui/main_window.py]"]
    end

    subgraph Runtime_Coordinator ["Central Coordination Layer"]
        JR["JarvisRuntime<br/>[core/jarvis_runtime.py]"]
        TR["CommandTracer<br/>[core/tracing.py]"]
    end

    subgraph Audio_Input_Pipeline ["Audio Capture & STT Subsystem"]
        WW["WakeWordDetector<br/>[core/wakeword.py]"]
        SL["SpeechListener<br/>[core/listener.py]"]
        VAD["Energy VAD & Rolling Pre-Roll<br/>[core/listener.py]"]
        STT["SpeechTranscriber (Faster-Whisper)<br/>[core/transcriber.py]"]
    end

    subgraph Language_Routing ["Intent & Language Routing Layer"]
        CN["CommandNormalizer<br/>[core/command_normalizer.py]"]
        MCP["MultiCommandParser<br/>[core/multi_command_parser.py]"]
        IE["IntentEngine<br/>[core/intent_engine.py]"]
    end

    subgraph Intelligence_Layers ["Intelligence Layers (L1 / L2 / L3)"]
        LRE["L1: LocalResponseEngine<br/>[core/local_response_engine.py]"]
        BRN["L2: Brain / LocalAIProvider<br/>[core/brain.py]"]
        CM["ConversationManager<br/>[core/conversation_manager.py]"]
        PM["L3: ProviderManager<br/>[core/ai/provider_manager.py]"]
        LLM["Cloud LLMs (Gemini, OpenRouter, Cerebras, OpenAI)<br/>[core/ai/providers/*]"]
    end

    subgraph Execution_Layer ["Tool & OS Execution Layer"]
        EX["CommandExecutor<br/>[modules/system/executor.py]"]
        SEC["Safety Gate: permissions.py<br/>[modules/system/permissions.py]"]
        AC["AppControl<br/>[modules/system/app_control.py]"]
        WC["WindowControl<br/>[modules/system/window_control.py]"]
        SC["SystemControl (Volume/Lock)<br/>[modules/system/system_control.py]"]
        SS["Screenshot<br/>[modules/system/screenshot.py]"]
        FC["FileControl<br/>[modules/files/file_control.py]"]
        WEB["WebControl<br/>[modules/browser/web_control.py]"]
        TM["TerminalManager<br/>[core/os/terminal_manager.py]"]
        FS["FilesystemManager<br/>[core/os/filesystem_manager.py]"]
        PR["ProcessManager<br/>[core/os/process_manager.py]"]
    end

    subgraph Audio_Output_Pipeline ["Response & TTS Playback Subsystem"]
        RM["ResponseManager<br/>[core/response_manager.py]"]
        TTS["TTSManager<br/>[core/tts/tts_manager.py]"]
        TC["TTS Disk Cache<br/>[logs/tts_cache/]"]
        EDGE["EdgeTTSProvider<br/>[core/tts/providers/edge_tts_provider.py]"]
        SAPI["WindowsSAPIProvider<br/>[core/tts/providers/windows_sapi_provider.py]"]
        PYT["Pyttsx3Provider<br/>[core/tts/providers/pyttsx3_provider.py]"]
        GTT["GTTSProvider<br/>[core/tts/providers/gtts_provider.py]"]
        PA["SoundDevice / PyAV OutputStream<br/>[core/tts/tts_manager.py]"]
        WS["Winsound Fallback<br/>[winsound]"]
    end

    %% Confirmed Wiring
    MW -->|sig_command_submitted [CONFIRMED]| JR
    MW -->|trigger_wakeword_cb [CONFIRMED]| JR
    JR -->|register_observers [CONFIRMED]| MW
    MW --> LV
    QH --> MW

    JR -->|start / stop [CONFIRMED]| WW
    JR -->|start / stop / set_speaking_active [CONFIRMED]| SL
    WW -->|_on_wakeword [CONFIRMED]| JR
    SL -->|_audio_callback -> VAD [CONFIRMED]| VAD
    VAD -->|_save_and_dispatch [CONFIRMED]| SL
    SL -->|_on_speech_end [CONFIRMED]| JR
    JR -->|transcribe [CONFIRMED]| STT
    STT -->|returns text [CONFIRMED]| JR

    JR -->|process_command [CONFIRMED]| CN
    CN -->|split_chained_commands [CONFIRMED]| MCP
    CN -->|normalize [CONFIRMED]| JR
    JR -->|parse [CONFIRMED]| IE

    %% Routing to Intelligence or Executor
    IE -->|OS / System Intents [CONFIRMED]| EX
    IE -->|Conversational Fallback [CONFIRMED]| CM
    IE -->|Greetings / Identity / Help [CONFIRMED]| RM

    CM -->|generate_response [CONFIRMED]| PM
    PM -->|Cloud API Call [CONFIRMED]| LLM
    PM -.->|Offline Fallback [CONFIRMED]| LRE
    CM -.->|Brain Reasoning [INFERRED]| BRN

    EX -->|is_safe_command [CONFIRMED]| SEC
    EX -->|execute app [CONFIRMED]| AC
    EX -->|execute window [CONFIRMED]| WC
    EX -->|execute audio/system [CONFIRMED]| SC
    EX -->|execute screenshot [CONFIRMED]| SS
    EX -->|execute files [CONFIRMED]| FC
    EX -->|execute web [CONFIRMED]| WEB
    EX -->|execute terminal [CONFIRMED]| TM
    EX -->|execute fs [CONFIRMED]| FS
    EX -->|execute proc [CONFIRMED]| PR

    EX -->|execution result [CONFIRMED]| RM
    RM -->|format_intent_response [CONFIRMED]| LRE
    RM -->|speak [CONFIRMED]| TTS

    TTS -->|check_cache [CONFIRMED]| TC
    TTS -->|1. Primary: synthesize [CONFIRMED]| EDGE
    TTS -->|2. Fallback: synthesize [CONFIRMED]| SAPI
    TTS -->|3. Fallback: synthesize [CONFIRMED]| PYT
    TTS -->|4. Fallback: synthesize [CONFIRMED]| GTT
    TTS -->|_play_audio_file [CONFIRMED]| PA
    PA -.->|Fallback on error [CONFIRMED]| WS

    %% Feedback / Lockout Loops
    TTS -->|on_start_speaking_cb [CONFIRMED]| JR
    TTS -->|on_stop_speaking_cb [CONFIRMED]| JR
    JR -->|set_speaking_active [CONFIRMED]| SL
    TR -.->|observes events across stages [CONFIRMED]| JR
```

---

## 3. Subsystem Detailed Registry

| Subsystem | Primary Class & File | Dependencies | Runtime Role |
|---|---|---|---|
| **Central Coordinator** | `JarvisRuntime`<br/>`core/jarvis_runtime.py` | `SpeechListener`, `SpeechTranscriber`, `IntentEngine`, `CommandExecutor`, `TTSManager`, `ResponseManager` | Manages service lifecycle, audio duplex lockout, pipeline state transitions (`STANDBY`, `LISTENING`, `TRANSCRIBING`, `THINKING`, `SPEAKING`). |
| **Audio Capture** | `SpeechListener`<br/>`core/listener.py` | `sounddevice.InputStream`, `numpy`, `wave` | Captures 16kHz Mono Float32 stream, maintains rolling 1.0s pre-roll, computes RMS energy VAD, saves 16-bit PCM WAV. |
| **STT Engine** | `SpeechTranscriber`<br/>`core/transcriber.py` | `faster_whisper.WhisperModel`, `huggingface_hub` | Runs local CTranslate2 INT8 model inference, applies phonetic accent corrections for Indian English names. |
| **Normalization** | `CommandNormalizer`<br/>`core/command_normalizer.py` | `re`, `MultiCommandParser` | Cleans punctuation, strips wake words and filler words, resolves phonetic synonyms, splits compound sentences. |
| **Intent Engine** | `IntentEngine`<br/>`core/intent_engine.py` | `applications.json`, `platform_manager` | Evaluates regex rules and keyword matches into structured command action nodes. |
| **Intelligence L1** | `LocalResponseEngine`<br/>`core/local_response_engine.py` | `config/responses.json` | Instant (<5ms), deterministic local template engine for confirmations, greetings, and OS statuses. |
| **Intelligence L2** | `Brain`<br/>`core/brain.py` | None | Local simulated reasoning and offline conversational response layer. |
| **Intelligence L3** | `ProviderManager`<br/>`core/ai/provider_manager.py` | `httpx`, `google.generativeai` | Cloud LLM gateway supporting Gemini, OpenRouter, Cerebras, and OpenAI with automatic offline fallback. |
| **Tool Execution** | `CommandExecutor`<br/>`modules/system/executor.py` | `psutil`, `pycaw`, Win32 API, `webbrowser`, `ctypes` | Routes validated commands to OS automation modules; enforces safety gates. |
| **Safety Gate** | `permissions.py`<br/>`modules/system/permissions.py` | None | Validates shell safety, flags dangerous actions (shutdown, restart) as `HIGH` risk requiring confirmation. |
| **Speech Output** | `TTSManager`<br/>`core/tts/tts_manager.py` | `sounddevice.OutputStream`, `av` (PyAV), `edge-tts`, `win32com.client` | Multi-provider FIFO speech queue, SHA256 disk cache, local SAPI fallback, duplex stream control. |
| **GUI Dashboard** | `MainWindow`<br/>`ui/main_window.py` | `PyQt6`, `psutil` | Sci-Fi HUD interface, Arc Reactor style status glow, live soundwave visualizer, system resource telemetry. |

---

## 4. Confirmed vs. Inferred Relationships

### Confirmed Relationships:
1. `JarvisRuntime` calls `listener.set_speaking_active(True/False)` in `_on_speaker_started` and `_on_speaker_stopped`.
2. `SpeechListener._save_and_dispatch` directly invokes `_on_speech_end(wav_path)`.
3. `SpeechTranscriber.transcribe` is called synchronously on `ListenerSaveThread`.
4. `TTSManager.speak` enqueues items to `self._queue`, which is processed by daemon thread `TTSThread`.
5. `TTSManager._play_audio_file` directly decodes with `av` and streams frames to `sd.OutputStream.write()`.
6. `EdgeTTSProvider` times out after `tts_cloud_timeout_ms` (2500ms), falling back to `WindowsSAPIProvider`.

### Inferred / Optional Relationships:
1. `Brain.process_text`: Currently acts as a secondary offline mock fallback; primary conversation routing goes through `ConversationManager.process_query()`.
2. `PorcupineWakeWordDetector` / `OpenWakeWordDetector`: Factory supports both, but system defaults to `MockWakeWordDetector` unless configured with API keys.
3. `winsound.PlaySound`: Activated only as a second-tier fallback if PyAV decoding or PortAudio streaming fails on WAV files.
