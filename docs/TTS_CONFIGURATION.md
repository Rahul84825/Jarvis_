# TTS Subsystem Configuration Guide

## Overview
Jarvis features a fully configurable, multi-provider Text-to-Speech (TTS) architecture. Voice parameters can be adjusted via `config.py`, `config.json`, or environment variables without modifying source code.

---

## Configuration Properties

| Parameter | Type | Default Value | Description |
|---|---|---|---|
| `tts_provider` | String | `"edge"` | Active TTS provider (`"edge"`, `"pyttsx3"`, `"gtts"`) |
| `tts_voice` | String | `"en-US-GuyNeural"` | Neural voice identifier for EdgeTTS |
| `tts_rate` | String | `"+15%"` | Speech playback rate (`"+10%"`, `"+15%"`, `"+20%"`) |
| `tts_pitch` | String | `"+0Hz"` | Pitch offset for EdgeTTS |
| `tts_volume` | String | `"+0%"` | Audio playback volume offset |
| `tts_language` | String | `"en"` | Language code |

---

## Modifying Configuration via `config.json`

Create or update `config.json` in the root directory:

```json
{
    "tts_provider": "edge",
    "tts_voice": "en-US-GuyNeural",
    "tts_rate": "+15%",
    "tts_pitch": "+0Hz",
    "tts_volume": "+0%",
    "tts_language": "en"
}
```

---

## Environment Variable Overrides

The following environment variables dynamically override configuration settings at launch:

```bash
# Set active TTS provider to offline pyttsx3
export JARVIS_TTS_PROVIDER="pyttsx3"

# Change voice for EdgeTTS
export JARVIS_TTS_VOICE="en-US-ChristopherNeural"

# Adjust speed rate
export JARVIS_TTS_RATE="+20%"
```

---

## Programmatic Control

Change the active provider at runtime using `TTSManager`:

```python
from core.tts.tts_manager import TTSManager

tts = TTSManager()
tts.set_provider("pyttsx3")  # Switch to local offline TTS
tts.speak("Systems switched to local offline voice.")
```
