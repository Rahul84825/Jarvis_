# Audio Routing & Duplex Lockout — Project Jarvis

## Overview
Jarvis strictly decouples microphone audio input from TTS audio output to eliminate self-triggering feedback loops and false wake events.

---

## Audio Stream Isolation Matrix

| Subsystem | Input Device | Output Device | Active During TTS Speech |
| :--- | :--- | :--- | :--- |
| **SpeechListener (VAD)** | Soundcard Microphone | None | **Locked / Paused** |
| **WakeWordDetector** | Soundcard Microphone | None | **Locked / Suppressed** |
| **TTSManager (Speaker)** | None | Soundcard Speakers | **Active** |
| **ClapDetector** | Soundcard Microphone | None | **Locked / Paused** |

---

## Duplex Lockout Lifecycle

1. **TTS Speech Onset (`on_start_speaking_cb`)**:
   - Sets `_tts_speaking_lock = True` in `JarvisRuntime`.
   - Invokes `listener.set_speaking_active(True)`, suppressing VAD onset capture.
   - Suppresses wake word trigger processing.

2. **TTS Speech Completion (`on_stop_speaking_cb`)**:
   - Invokes `listener.set_speaking_active(False)`.
   - Resets `_tts_speaking_lock = False`.
   - Returns pipeline state machine to `STANDBY`.
