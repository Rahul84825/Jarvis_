# Local Command Routing Architecture

## Overview
Jarvis strictly separates local computer control commands from general conversational queries. Local computer commands execute immediately via `CommandExecutor` with zero AI API network overhead.

---

## Execution Flow Comparison

### 1. Local Command Flow (Zero API Latency)
```
Whisper STT ──► Command Normalizer ──► Intent Engine ──► Command Executor ──► Response Manager ──► TTS
```
- **Bypasses AI Providers Completely**.
- **Execution Latency**: < 20 ms.
- **Commands Covered**:
  - App Launching / Closing (`Open Chrome`, `Close Calculator`)
  - Volume Control (`Volume up`, `Volume down`, `Mute`, `Unmute`)
  - Screen Operations (`Take screenshot`)
  - Security (`Lock computer`)
  - Web & Folder Access (`Open YouTube`, `Open Downloads`)

---

### 2. Conversational Query Flow (Routed to Conversation Engine)
```
Whisper STT ──► Router ──► ConversationManager ──► ProviderManager ──► Active AI Provider / Local Fallback ──► Response Manager ──► TTS
```
- Used only for general questions, explanations, and knowledge queries.
- Incorporates multi-turn history for follow-up resolution.
