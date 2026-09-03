# Voice Core Architecture — Project Jarvis

## Overview
This document details the decoupled, voice-first core architecture of Jarvis. The assistant core can run completely headless (`python main.py --headless`) without any dependency on the PyQt6 GUI dashboard.

---

## Architectural Diagram

```
                     ┌────────────────────────────────┐
                     │          main.py               │
                     │  (--headless  /  --ui)        │
                     └───────────────┬────────────────┘
                                     │
                                     ▼
                   ┌──────────────────────────────────┐
                   │        JarvisRuntime             │
                   │   (core/jarvis_runtime.py)       │
                   └─────────────────┬────────────────┘
                                     │
    ┌────────────────┬───────────────┼───────────────┬────────────────┐
    ▼                ▼               ▼               ▼                ▼
WakeWordService  SpeechListener  Transcriber   Intent Engine     TTSManager
 (Mock/Porcupine) (VAD Onset)   (Whisper STT)  (Intent & Multi)  (Edge/pyttsx3)
```

---

## Core Lifecycles & Subsystems

### 1. JarvisRuntime (`core/jarvis_runtime.py`)
- Central coordinator managing thread lifecycles, pipeline state machine (`STANDBY`, `LISTENING`, `TRANSCRIBING`, `THINKING`, `EXECUTING`, `SPEAKING`, `ERROR`), and duplex audio lockouts.
- Zero PyQt6 GUI dependencies. Observers can register to receive state changes asynchronously.

### 2. SpeechListener (`core/listener.py`)
- VAD-based voice activity detection monitor listening on default soundcard input. Automatically triggers voice recording upon speech onset and stops upon silence.

### 3. SpeechTranscriber (`core/transcriber.py`)
- Local Faster-Whisper model engine (`tiny` / `small` on CPU) transcribing audio files with duration and confidence metadata.

### 4. Intent & Multi-Command Parsing (`core/intent_engine.py` & `core/multi_command_parser.py`)
- Standardizes natural speech into canonical intents. Splits compound sentences (*"Open Chrome and VS Code"*) into sequential execution items.

### 5. OS Executor (`modules/system/executor.py`)
- Routes structured commands to cross-platform system, application, folder, screenshot, and web handlers.

### 6. TTS Manager (`core/tts/tts_manager.py`)
- Multi-provider speech output engine (`EdgeTTSProvider`, `Pyttsx3Provider`, `GTTSProvider`) managing FIFO speech queueing, cancellation, and audio lockouts.
