# Text-to-Speech (TTS) Engine Comparison Matrix

## Overview
This document evaluates the practical Python-compatible Text-to-Speech (TTS) providers integrated into Jarvis: **EdgeTTS**, **pyttsx3**, and **gTTS**.

---

## Evaluation Matrix

| Metric | EdgeTTS (Neural Cloud) | pyttsx3 (Offline Local) | gTTS (Google Web Fallback) |
|---|---|---|---|
| **Voice Naturalness** | **Excellent (Human-like)** | Robotic / Metallic | Moderate |
| **Synthesis Latency** | Fast (~150 - 300 ms) | **Ultra Fast (~20 - 50 ms)** | Moderate (~300 - 600 ms) |
| **Offline Operation** | No (Requires Internet) | **Yes (100% Offline Local)** | No (Requires Internet) |
| **CPU Usage** | Very Low (< 2%) | Very Low (< 3%) | Very Low (< 2%) |
| **RAM Usage** | Low (~15 MB) | Low (~10 MB) | Low (~12 MB) |
| **Windows Support** | Full | **Full (SAPI5)** | Full |
| **Linux Support** | Full | **Full (eSpeak)** | Full |
| **Voice Variety** | 300+ Neural Voices | System Native Voices | Single Voice per Lang |
| **Speech Rate Control** | **Yes (`+10%` to `+20%`)** | **Yes (WPM control)** | No |
| **Pitch & Volume Control** | **Yes (`+0Hz`, `+0%`)** | Partial | No |

---

## Comparative Assessment

### 1. EdgeTTS (`edge_tts`)
- **Pros**: Outstanding neural voice quality (`en-US-GuyNeural` / `en-US-ChristopherNeural`), natural intonation, pitch, and speed adjustments.
- **Cons**: Requires active network connection.
- **Best Use Case**: Default daily assistant experience when connected to internet.

### 2. pyttsx3 (`pyttsx3`)
- **Pros**: Zero network dependency, instant zero-latency speech synthesis, native Windows SAPI5 / Linux eSpeak support.
- **Cons**: Robotic voice tone compared to modern neural models.
- **Best Use Case**: Primary offline fallback when internet is disconnected.

### 3. gTTS (`gtts`)
- **Pros**: Simple Google Web TTS fallback option.
- **Cons**: Slower synthesis latency, lacks rate and pitch control.
- **Best Use Case**: Secondary cloud backup provider.

---

## Recommendation & Default Setup
- **Primary Provider**: EdgeTTS (`en-US-GuyNeural` at `+15%` speech rate).
- **Offline Provider**: pyttsx3 (Automatically activated when offline).
