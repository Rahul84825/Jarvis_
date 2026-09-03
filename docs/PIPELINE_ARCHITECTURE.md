# JARVIS PIPELINE ARCHITECTURE

## Pipeline Diagram

```
                       +-------------------------+
                       |    Microphone Stream    |
                       +-------------------------+
                                    |
                                    v
                       +-------------------------+
                       |  SpeechListener (VAD)   |
                       +-------------------------+
                                    | (WAV Audio)
                                    v
                       +-------------------------+
                       |    SpeechTranscriber    |
                       |    (Faster-Whisper)     |
                       +-------------------------+
                                    | (Raw Speech Text)
                                    v
                       +-------------------------+
                       |    CommandNormalizer    |
                       |  (Strips wake words,    |
                       | polite phrases, fillers)|
                       +-------------------------+
                                    | (Normalized Command)
                                    v
                       +-------------------------+
                       |      IntentEngine       |
                       | (Classifies intent,     |
                       |  action, entity, conf)  |
                       +-------------------------+
                                    | (Intent Node Dict)
                                    v
                       +-------------------------+
                       |     CommandExecutor     |
                       | (Executes OS function,  |
                       |  checks safety/perm)    |
                       +-------------------------+
                                    | (Execution Result Dict)
                                    v
                       +-------------------------+
                       |     ResponseManager     |
                       | (Formats natural spoken |
                       |  responses & types)     |
                       +-------------------------+
                                    | (Spoken Response Text)
                                    v
                       +-------------------------+
                       |         Speaker         |
                       |       (Edge-TTS)        |
                       +-------------------------+
                                    |
                                    v
                       +-------------------------+
                       |     Audio Output        |
                       +-------------------------+
```

---

## Detailed Data Transformations

### Stage 1: Speech to Raw Text
- **Input**: Microphone audio stream (16kHz PCM mono WAV)
- **Component**: `SpeechTranscriber` (Faster-Whisper model)
- **Output**: `Raw Whisper Text` (e.g., *"Jarvis please lock my PC."*)

### Stage 2: Text Normalization
- **Input**: `Raw Whisper Text`
- **Component**: `CommandNormalizer`
- **Output**: `Normalized Command` (e.g., *"lock computer"*)
- **Metadata**: Stripped wake words (`jarvis`), polite phrases (`please`), normalized synonyms (`pc` $\rightarrow$ `computer`).

### Stage 3: Intent Classification & Entity Extraction
- **Input**: `Normalized Command`
- **Component**: `IntentEngine`
- **Output**: `Intent Node`
  ```json
  {
    "intent": "system_control",
    "action": "lock_pc",
    "target": null,
    "confidence": 0.98,
    "query": "lock computer",
    "raw_text": "Jarvis please lock my PC."
  }
  ```

### Stage 4: OS Execution & Safety Enforcement
- **Input**: `Intent Node`
- **Component**: `CommandExecutor`
- **Output**: `Execution Result`
  ```json
  {
    "success": true,
    "message": "Computer locked successfully.",
    "intent": "system_control",
    "action": "lock_pc",
    "target": null,
    "spoken": true,
    "pending_confirmation": false
  }
  ```

### Stage 5: Response Management & Audio Synthesis
- **Input**: `Execution Result`
- **Component**: `ResponseManager` $\rightarrow$ `Speaker`
- **Output**: Natural spoken audio output via Edge-TTS (e.g., *"Computer locked successfully."*)

---

## Debug Panel Telemetry Mapping

The PyQt6 HUD window displays all 6 pipeline stages live in the **Command Understanding Debug** panel:
1. `RAW WHISPER OUTPUT`
2. `NORMALIZED COMMAND`
3. `DETECTED INTENT`
4. `EXECUTOR RESULT`
5. `RESPONSE / PLAYBACK`
6. `CONFIDENCE & METRICS`
