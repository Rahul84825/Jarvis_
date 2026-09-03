# Conversation Engine & Short-Term Memory Architecture

## Overview
The Conversation Engine (`core/conversation_manager.py`) manages short-term multi-turn conversation memory, active session tracking, follow-up query context resolution, and intelligent fallback when no AI provider is configured.

---

## Key Capabilities

### 1. Rolling Turn Memory
- Stores user questions and assistant answers as structured role messages (`[{"role": "user", "content": ...}, {"role": "assistant", "content": ...}]`).
- Automatically caps history to the last `max_turns` (default: 20 turns / 40 messages), discarding older interactions to manage token usage and memory overhead.

### 2. Follow-up Question Resolution
- Passes the full active conversation window to `ProviderManager`.
- Example:
  - User: *"Explain quantum computing."*
  - Assistant: *"Quantum computing uses qubits..."*
  - User: *"Make that simpler."*
  - The provider receives the complete message history, allowing it to correctly resolve *"that"* to the quantum computing explanation.

### 3. Session Timeout & Reset
- Tracks `last_interaction_timestamp`.
- If user inactivity exceeds `session_timeout` (default: 60 seconds), conversation session memory is automatically cleared to prepare for a fresh context.

### 4. No-Provider Fallback
- If `AI_PROVIDER=none` or the active AI provider is unreachable, `ConversationManager` returns a polite local response: *"I'm currently limited to my local capabilities for that question."*
