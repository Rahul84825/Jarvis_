# Local Response System Architecture

## Overview
The Local Response System is the core response engine for Jarvis. It replaces cloud-dependent LLM API calls (such as Gemini) with a fast, deterministic, and local-first architecture. This design guarantees instant response times, 100% offline capability for core actions, zero API key configuration requirements, and predictable speech outputs.

---

## Key Components

### 1. Response Template Registry (`config/responses.json`)
The response template registry defines human-curated variations of concise, natural responses mapped by intent keys.
- **Location**: `config/responses.json`
- **Supported Intent Categories**:
  - `greeting`, `namaste`, `wake_response`, `thank_you`, `goodbye`
  - `help`, `identity`
  - `open_app`, `close_app`, `open_website`, `file_access`
  - `screenshot`, `volume_up`, `volume_down`, `mute`, `unmute`, `lock_pc`
  - `repeat`, `cancellation`, `unknown`, `error_generic`, `error_not_found`, `error_unsupported`

### 2. Local Response Engine (`core/local_response_engine.py`)
- Provides `LocalResponseEngine` class.
- Dynamically loads `config/responses.json` at initialization (with built-in fallback defaults).
- Formats intent variables (`{app}`, `{site}`, `{folder}`, `{assistant_name}`, `{owner_name}`).
- Formats sequential multi-command results into a single concise spoken summary.

### 3. Response Manager Integration (`core/response_manager.py`)
- Interfaces `LocalResponseEngine` with `TTSManager`.
- Enforces speech brevity guidelines.
- Sanitizes error messages to ensure technical tracebacks are kept strictly in system logs while speaking user-friendly responses.

---

## Workflow Diagram

```
User Voice Input / Typed Command
          │
          ▼
   Speech Listener / VAD
          │
          ▼
 Speech Transcriber (Whisper)
          │
          ▼
  Command Normalizer
          │
          ▼
    Intent Engine
          │
          ▼
   Command Executor  <───►  Local Response Engine (`config/responses.json`)
          │
          ▼
  Response Manager
          │
          ▼
     TTS Manager (EdgeTTS / pyttsx3)
          │
          ▼
    Audio Speaker
```

---

## Benefits
1. **Zero Latency Overhead**: Response generation executes in under 1 millisecond.
2. **Zero Cloud Dependencies**: No network calls or API keys required.
3. **Predictable Behavior**: Eliminates hallucinated or excessively long conversational responses.
4. **Reliability**: Works reliably under all network conditions.
