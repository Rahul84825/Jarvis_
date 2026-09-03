# Headless Runtime Guide — Project Jarvis

## Overview
Jarvis can operate in pure headless voice core mode without loading PyQt6 or any graphical user interface libraries.

---

## Command Line Usage

### Headless Core Mode (Default / Terminal Mode)
```bash
python main.py --headless
```

Expected Terminal Output:
```
============================================================
           JARVIS VOICE CORE INITIALIZING
============================================================
Wake word engine : READY (mock)
Microphone       : READY (VAD Threshold: 0.015)
Whisper Model    : READY (small on cpu)
Command Engine   : READY (Intent & Multi-Command Parser)
Executor         : READY (Platform: Active)
TTS Engine       : READY (Provider: EdgeTTS (Neural Cloud))
============================================================
JARVIS ONLINE — Standing by for wake word...
============================================================
```

### GUI Dashboard Mode (Optional UI Client)
```bash
python main.py --ui
```

---

## Signal Handling & Clean Shutdown
In headless mode, pressing `Ctrl+C` sends `SIGINT`. `JarvisRuntime` catches `SIGINT`, halts background listener and TTS worker threads, cleans temporary audio files, and exits cleanly with code `0`.
