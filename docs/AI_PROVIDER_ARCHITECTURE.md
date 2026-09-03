# AI Provider Abstraction Architecture

## Overview
The AI Provider Abstraction Framework decouples the core Jarvis voice runtime from specific cloud LLM services (Gemini, OpenRouter, Cerebras, OpenAI, NVIDIA NIM, or local engines). This design enforces strict provider independence: Jarvis starts and operates without any API keys configured, and AI providers plug in dynamically via a standardized interface.

---

## Core Components

### 1. Abstract Base Class (`core/ai/base_provider.py`)
Defines the required interface for all AI providers:
- `is_available() -> bool`: Returns True if the provider has valid credentials and is ready for requests.
- `generate_response(messages: list, context: dict = None) -> Optional[str]`: Generates a response string for role-based conversation turns.
- `stream_response(messages: list, context: dict = None)`: Yields streaming text chunks.
- `get_name() -> str`: Returns provider display name.
- `health_check() -> bool`: Verifies connectivity.

### 2. Provider Manager (`core/ai/provider_manager.py`)
- Reads `config.ai_provider` (Options: `"none"`, `"local"`, `"openrouter"`, `"cerebras"`, `"gemini"`, `"openai"`, `"nvidia"`).
- Dynamically selects the active provider and handles graceful fallbacks if key is missing or service is down.
- Guarantees zero crashes or API error outputs when `AI_PROVIDER=none`.

### 3. Provider Implementations (`core/ai/providers/`)
- `LocalAIProvider`: Local template engine provider (100% offline).
- `OpenRouterProvider`: OpenRouter cloud API integration.
- `CerebrasProvider`: Cerebras ultra-fast inference API integration.
- `GeminiProvider`: Google Gemini API integration.
- `OpenAIProvider`: OpenAI Chat Completions API integration.
- `NVIDIAProvider`: NVIDIA NIM Chat Completions API integration.

---

## Architecture Flow Diagram

```
                 Jarvis Voice Core / Runtime
                             │
                             ▼
                    Conversation Router
                             │
                             ▼
                   ProviderManager (`core/ai/`)
                             │
            ┌────────────────┼────────────────┐
            ▼                ▼                ▼
     LocalAIProvider  OpenRouterProvider  CerebrasProvider ...
```

---

## Zero API Key Dependency Rule
No provider-specific code (`if provider == 'gemini'`) exists inside the Jarvis runtime. If no provider key exists, `ProviderManager` returns `None` safely and `ConversationManager` outputs a polite local fallback without showing API errors to the user.
