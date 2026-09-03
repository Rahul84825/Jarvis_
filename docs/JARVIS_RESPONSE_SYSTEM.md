# Jarvis Response System Architecture

## Overview
The Jarvis Response System (`core/response_manager.py`) aggregates spoken outputs from all subsystems: Local Response Engine, Command Executor, Conversation Manager, and AI Providers.

---

## Response Priority Hierarchy

1. **Immediate Local Response**: Fast acknowledgment for wake words and simple actions.
2. **Executor Result**: Direct output from computer control commands.
3. **Local Conversation Response**: Offline greetings, identity questions, help, and status queries.
4. **AI Provider Response**: High-level conversational outputs when an AI provider is active.
5. **Graceful No-Provider Response**: Polite fallback when no AI provider is configured (*"I'm currently limited to my local capabilities for that question."*).

---

## Output Pipeline

```
Subsystem Source ──► ResponseManager ──► Sanitizer ──► TTSManager ──► Speaker
```

- **Sanitization Rule**: Raw stack traces, API keys, and internal module errors are hidden from spoken audio output and written exclusively to `logs/jarvis.log`.
