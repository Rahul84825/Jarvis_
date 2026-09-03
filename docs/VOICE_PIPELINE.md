# End-to-End Voice Pipeline Architecture

## Overview
Jarvis implements a local-first, low-latency duplex voice pipeline. Audio input, wake word detection, speech-to-text, intent recognition, response synthesis, and audio output execute through decoupled background threads coordinated by `JarvisRuntime`.

---

## Detailed Pipeline Stages

```
   ┌────────────────────────────────────────────────────────┐
   │                   MIC INPUT STAGE                      │
   │  SpeechListener (PyAudio + Energy VAD / Silero VAD)   │
   └──────────────────────────┬─────────────────────────────┘
                              │
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │                  WAKE WORD DETECTOR                    │
   │  WakeWordDetector (Mock / OpenWakeWord / Porcupine)    │
   └──────────────────────────┬─────────────────────────────┘
                              │ Wake Word Detected ("Jarvis")
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │                 SPEECH TRANSCRIBER                     │
   │        SpeechTranscriber (Faster Whisper CPU/int8)     │
   └──────────────────────────┬─────────────────────────────┘
                              │ Transcribed WAV Text
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │                 COMMAND NORMALIZER                     │
   │   Strips wake prefixes, applies phonetic corrections   │
   └──────────────────────────┬─────────────────────────────┘
                              │ Clean Normalized Command
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │                   INTENT ENGINE                        │
   │ Multi-command clause splitting + Regex Intent Parsing   │
   └──────────────────────────┬─────────────────────────────┘
                              │ Intent Node / Action
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │                 COMMAND EXECUTOR                       │
   │       Executes OS controls / Apps / Screenshots        │
   └──────────────────────────┬─────────────────────────────┘
                              │ Execution Result
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │                 LOCAL RESPONSE ENGINE                  │
   │   Formats concise natural output from `responses.json`  │
   └──────────────────────────┬─────────────────────────────┘
                              │ Spoken Text
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │                   RESPONSE MANAGER                     │
   │    Routes text & enqueues to active TTS provider       │
   └──────────────────────────┬─────────────────────────────┘
                              │ Spoken Text Queue
                              ▼
   ┌────────────────────────────────────────────────────────┐
   │                      TTS MANAGER                       │
   │     Synthesizes audio & streams via PyAV / SoundDevice │
   └────────────────────────────────────────────────────────┘
```

---

## Duplex Audio Lockout Mechanism
To prevent Jarvis from listening to its own spoken voice output (audio feedback loop):
1. `TTSManager` triggers `on_start_speaking_cb` when audio playback begins.
2. `JarvisRuntime` sets `_tts_speaking_lock = True` and calls `SpeechListener.set_speaking_active(True)`.
3. VAD speech onset and WakeWord triggers are suppressed during speech playback.
4. When audio finishes, `TTSManager` triggers `on_stop_speaking_cb`, unlocking the microphone input and returning system status to `STANDBY`.
