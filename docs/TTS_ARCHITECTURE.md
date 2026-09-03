# TTS Subsystem Architecture

## Overview
The TTS Subsystem (`core/tts/`) provides modular speech synthesis, queue management, instant audio interruption, and configurable speech parameters (`TTS_PROVIDER`, `TTS_VOICE`, `TTS_RATE`, `TTS_VOLUME`, `TTS_PITCH`).

---

## Modular Provider Interface

All TTS providers inherit from `BaseTTS` (`core/tts/base_tts.py`):
1. **EdgeTTS** (`core/tts/providers/edge_tts_provider.py`): Default neural cloud voice provider (`en-US-GuyNeural` at `+15%` rate).
2. **pyttsx3** (`core/tts/providers/pyttsx3_provider.py`): 100% offline local TTS engine using native OS sound synthesis (SAPI5 / eSpeak).
3. **gTTS** (`core/tts/providers/gtts_provider.py`): Web fallback provider.

---

## Queue & Interruption Handling
`TTSManager` (`core/tts/tts_manager.py`) manages a FIFO background speech thread:
- `speak(text, interrupt=True)`: Enqueues speech and interrupts any active playback if `interrupt=True`.
- `interrupt()`: Instantly halts active audio streams and flushes pending queue items.
- Notifies duplex observers (`on_start_speaking_cb`, `on_stop_speaking_cb`) to lock/unlock microphone VAD input.
