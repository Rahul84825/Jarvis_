# JARVIS Failure, Timeout, Fallback & Cancellation Paths

## 1. Overview

This document maps out every failure mode, timeout ceiling, graceful degradation path, and cancellation mechanism across the JARVIS runtime.

- **Confirmed [CONFIRMED]**: Verified by code logic and empirical test execution.
- **Inferred [INFERRED]**: Theoretical edge conditions.

---

## 2. Global Failure & Fallback Decision Matrix

```mermaid
graph TD
    subgraph STT_Failures ["Speech-to-Text Failure Modes"]
        MIC_ERR["Microphone Stream Fails to Start<br/>[core/listener.py:L90]"] -->|Raises Exception| RUN_ABORT["Runtime Fails Startup Gracefully"]
        VAD_SIL["Silence Detected / No Voice Energy"] -->|text == ''| ST_RET["Return to STANDBY<br/>No TTS triggered"]
        STT_INIT_ERR["Whisper Model Initialization Fails"] -->|STT_FAILED| STT_EXC["Raises Exception / Empty Result"]
        STT_CORRUPT["Corrupted WAV File / Zero Bytes"] -->|FileNotFoundError| TRANS_FAIL["Log Error -> Return Empty Text"]
        STT_HALLUC["Hallucinated Output (e.g. '. . . . .')"] -->|Compression ratio check fails| NORM_STRIP["Normalizer strips or routes to Chat"]
    end

    subgraph Intent_Failures ["Intent & Intelligence Fallback Paths"]
        NORM_EMPTY["Normalized Text Empty"] -->|Unknown Intent| RET_SIL["'I didn't catch that. Please speak again.'"]
        UNMAPPED_CMD["Unmapped Custom Command"] -->|Fallback to Conversation| CM_ROUT["Route to ConversationManager"]
        
        CM_ROUT --> PM_CHK{"ProviderManager has Active AI?"}
        PM_CHK -->|ai_provider == 'none'| LOC_FALL["Local Fallback:<br/>'I'm not sure how to help with that yet.'"]
        PM_CHK -->|API Key Missing| LOC_FALL
        PM_CHK -->|API Request Timeout / 5xx| LOC_FALL
    end

    subgraph Tool_Failures ["Tool & OS Execution Failures"]
        HIGH_RISK_BLOCK["High Risk Action (e.g. Shutdown)"] -->|User confirmation pending| WARN_RESP["Prompt Warning Dialog & Await 'Yes'"]
        CMD_INVAL["Metacharacter Injection Detected"] -->|is_safe_command == False| SEC_BLK["Block Execution & Output Security Notice"]
        APP_NOT_FOUND["App Executable Not Installed"] -->|Exception in app_control| ERR_RESP["ResponseManager.failure('App not found')"]
        PROC_TERMINATE_ERR["Process Termination Permission Denied"] -->|psutil.AccessDenied| ERR_RESP
    end

    subgraph TTS_Failures ["TTS Synthesis & Playback Fallback Paths"]
        EDGE_TIMEOUT["EdgeTTS Cloud Timeout (>2.5s)"] -->|TimeoutError / Network Drop| SAPI_FB["Fallback 1: Windows SAPI COM (Native Offline)"]
        SAPI_ERR["Windows SAPI Error / Empty WAV"] -->|Exception in SAPI| PYTX_FB["Fallback 2: pyttsx3 Local Provider"]
        PYTX_ERR["pyttsx3 Not Installed or Fails"] -->|Exception in pyttsx3| GTTS_FB["Fallback 3: gTTS Cloud Provider"]
        ALL_TTS_FAIL["All TTS Providers Return None"] -->|audio_file_to_play is None| NO_SOUND["Silent Failure / No Audio Emitted"]
        
        AV_ERR["PyAV Stream Open Error / Unsupported Codec"] -->|Exception in av.open| WS_FB["Winsound Fallback: winsound.PlaySound (WAV only)"]
        PA_ERR["PortAudio Device Busy / Stream Error"] -->|Exception in sd.OutputStream| WS_FB
    end

    subgraph Interruption_Cancellations ["Cancellation & Interruption Paths"]
        WAKE_BARGE["Wake Word Spoken During TTS Playback"] -->|Barge-In Detected| FORCE_INT["tts_manager.interrupt(force=True)<br/>Stream stopped, queue cleared"]
        VAD_ECHO_BUG["[AUDIT DEFECT] Speaker Output Triggers VAD"] -->|Acoustic Echo Detected| ECHO_CMD["Transcribes Echo -> Generates Fallback -> Cuts Playback!"]
        MUTE_TOGGLE["User Toggles Microphone Mute"] -->|runtime.set_mute_state(True)| HALT_LIS["Stop Listener + TTS 'Systems muted'"]
    end
```

---

## 3. Detailed Failure Mode Inventory

### A. Audio Input & STT
| Failure Point | Trigger Condition | Code Location | System Behavior | Recovery / Fallback |
|---|---|---|---|---|
| **Microphone Hardware Missing** | `sd.InputStream` fails to initialize | `core/listener.py:89` | Raises `Exception`, logs error | Prevents startup; diagnostics return `"Device Unavailable"` |
| **Silence / Zero Energy** | Audio energy below threshold throughout utterance | `core/jarvis_runtime.py:211` | `text == ""` | Pipeline returns to `STANDBY`; no TTS speech triggered |
| **Whisper Prewarm Unfinished** | Command arrives while model is still loading in background | `core/transcriber.py:106` | `_ready_event.wait(timeout=30.0)` | Blocks worker until ready (up to 30s), then transcribes |
| **Whisper Model Failure** | Missing model files or CTranslate2 execution fault | `core/transcriber.py:81` | Sets `status = "STT_FAILED"` | Logs traceback; returns empty transcription |
| **Manual Recording Timeout** | Wake word triggered without subsequent speech | `core/listener.py:205` | Hit `max_duration` (5.0s) | Audio saved and dispatched; empty/noise result ignored |

### B. Command Routing & Intelligence
| Failure Point | Trigger Condition | Code Location | System Behavior | Recovery / Fallback |
|---|---|---|---|---|
| **Dangerous Shell Injection** | Metacharacters `;`, `&`, `\|`, `>`, `$` in command | `modules/system/permissions.py:25` | `is_safe_command()` returns `False` | Command blocked; outputs warning speech |
| **Unconfirmed High Risk Action** | Shutdown, restart, or raw terminal execution requested | `modules/system/executor.py:71` | `risk_level == RiskLevel.HIGH` | Action blocked; sets `pending_intent`, speaks confirmation prompt |
| **Cloud AI Provider Offline** | Gemini/OpenRouter API key empty or network unreachable | `core/ai/provider_manager.py:62` | Provider returns `None` | Outputs local fallback: `"I'm not sure how to help with that yet."` |
| **Conversation Session Stale** | Inactivity exceeds 60 seconds | `core/conversation_manager.py:25` | Session timeout checked | Clears history list; starts fresh conversation turn |

### C. Text-to-Speech & Physical Playback
| Failure Point | Trigger Condition | Code Location | System Behavior | Recovery / Fallback |
|---|---|---|---|---|
| **EdgeTTS Cloud Timeout** | Network latency or DNS failure exceeds 2500ms | `core/tts/providers/edge_tts_provider.py:62` | `asyncio.wait_for` raises `TimeoutError` | Seamless local fallback: `WindowsSAPIProvider` synthesizes offline WAV |
| **Windows SAPI COM Error** | COM registration fault or invalid voice description | `core/tts/providers/windows_sapi_provider.py:97` | Catches `Exception`, deletes temp file | Falls back to `Pyttsx3Provider` |
| **PyAV Decoding Failure** | Corrupt container or unsupported audio stream | `core/tts/tts_manager.py:487` | Catches PyAV streaming error | If file is WAV, falls back to `winsound.PlaySound` |
| **Acoustic Feedback Interruption** | Speaker sound triggers VAD onset while Jarvis speaks | `core/listener.py:186` + `core/tts/tts_manager.py:163` | New response triggers `speak(interrupt=True)` | Interrupted active playback immediately |
| **Output Device Lockout** | Non-existent or disconnected audio device index | `core/tts/tts_manager.py:123` | Index validation in `_resolve_output_device` | Falls back to system default audio device |
