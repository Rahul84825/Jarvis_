# Engineering Report: NVIDIA Nemotron Reasoning Engine Integration

**Project:** JARVIS (Just A Rather Very Intelligent System)  
**Model:** `nvidia/nemotron-3.5-super-vl-120b-a12b`  
**API Endpoint:** `https://integrate.api.nvidia.com/v1`  
**Date:** October 20, 2026  
**Status:** IMPLEMENTED, TESTED, AND VERIFIED (587 Tests Passing)  

---

## 1. Executive Summary

This report documents the architectural integration of **NVIDIA Nemotron** (`nvidia/nemotron-3.5-super-vl-120b-a12b`) into JARVIS as its primary cloud reasoning, coding, and algorithmic intelligence engine.

The integration was completed in a single comprehensive pass while strictly adhering to all architectural constraints:
- **No Rewrite:** The existing PyQt6 desktop application, async thread pool workers, single-instance Win32 guard, and three-layer intelligence design were 100% preserved.
- **Layer 1 & Layer 2 Intact:** Fast local deterministic OS automation (application control, windows, audio, screenshots, telemetry) and local conversational capabilities (greetings, social intelligence, offline templates) remain zero-latency and local.
- **Layer 3 Upgraded:** Advanced algorithm explanations (DSA, C++ code, complexity dry runs, LeetCode debugging) and multi-step reasoning are now routed to NVIDIA Nemotron.
- **Controlled Tool Execution:** The model proposes tool actions in standard OpenAI or ReAct format; actions are strictly filtered through `ToolRegistry` and `ToolSafetyGate` policy checks before execution. Arbitrary shell command generation is disallowed.
- **Strict Secret Isolation:** Outbound credentials (including `nvapi-` tokens) are automatically redacted in GUARDED mode, forbidden from transmission in STRICT mode, never printed in error traces or UI widgets, and stored strictly in `.env`.
- **Verified by Tests:** 22 focused provider/routing/security/tool tests passed, a live cloud smoke test succeeded against `https://integrate.api.nvidia.com/v1`, and all 587 automated regression tests in the repository passed cleanly.

---

## 2. Initial Architecture Findings

During Phase 1 auditing, the checkout revealed:
1. **Provider Registry (`core/ai/provider_manager.py`):** Manages AI providers subclassing `BaseAIProvider`. It already supported `local`, `ollama`, `openrouter`, `cerebras`, `gemini`, and `openai`, with prefix extraction (`claude:`, `gpt:`, `gemini:`, etc.). Outbound requests passed through `PrivacyGuard`.
2. **Deterministic Intent Engine (`core/intent_engine.py` & `core/ai/intelligence_router.py`):** Classifies requests into:
   - Layer 1 (`MODE_FAST_LOCAL`): Reflex commands dispatched to `CommandExecutor` in <2ms.
   - Layer 2 (`MODE_CONTEXT` / `MODE_QUESTION`): Pronominals, preferences, and conversational requests.
   - Layer 3 (`MODE_REASONING`): Complex agentic tasks dispatched to `AgentBrain` or `MultiStepPlanner`.
3. **Safety & Tool Execution (`core/tool_safety_gate.py` & `core/ai/tools/registry.py`):** Enforces a default-deny policy for write operations unless write permissions are enabled.
4. **Context & Conversation Memory (`core/conversation_manager.py`):** Maintains in-memory multi-turn history (`history`), 60-second inactivity timeout resetting stale sessions, and SQLite durable persistence (`memory/conversations.db`).
5. **Observed Nemotron Behavior:**
   - Evaluated endpoint: `https://integrate.api.nvidia.com/v1/chat/completions`
   - Model `nvidia/nemotron-3.5-super-vl-120b-a12b` generates internal chain-of-thought tokens into `reasoning_content` (typically 300–1000 tokens) before outputting the user-facing response into `content`.
   - Bounded token limits (`max_tokens`) must be at least 1024–2048 to prevent premature truncation inside the reasoning phase.
   - Tool calling is natively supported using OpenAI's `tools` array parameter, returning standard `choices[0].message.tool_calls`.

---

## 3. Provider Integration Design

The provider was implemented as `NvidiaNemotronProvider` in `core/ai/providers/nvidia_provider.py`, subclassing `BaseAIProvider`.

```
                    +------------------------------------+
                    |        User Request / Prompt       |
                    +------------------------------------+
                                      |
                                      v
                    +------------------------------------+
                    |       Intelligence Router          |
                    | (Layer 1: Local / Layer 2: Social) |
                    +------------------------------------+
                                      | (Layer 3 Reasoning)
                                      v
                    +------------------------------------+
                    |          ProviderManager           |
                    |  - Prefix Routing ('nemotron:')    |
                    |  - PrivacyGuard (STRICT / GUARDED) |
                    +------------------------------------+
                                      |
                                      v
                    +------------------------------------+
                    |      NvidiaNemotronProvider        |
                    |  - Base URL: integrate.api.nvidia  |
                    |  - Model: nemotron-3.5-super-vl    |
                    |  - Bounded Retries (429 / 5xx)     |
                    |  - Sanitized Error Logging         |
                    +------------------------------------+
                                      |
                                      v
                    +------------------------------------+
                    |  NVIDIA API Endpoint (Cloud Model) |
                    +------------------------------------+
                                      |
                                      v
                    +------------------------------------+
                    |   Response & Tool Call Handler     |
                    |  - Extracts 'content' (Clean UI)   |
                    |  - Translates 'tool_calls'         |
                    |  - Validates via SafetyGate        |
                    +------------------------------------+
```

### Key Capabilities Implemented:
1. **Configurable Base URL and Model:**
   Defaults to `https://integrate.api.nvidia.com/v1` and `nvidia/nemotron-3.5-super-vl-120b-a12b`, fully overridable via `.env` or `config.py`.
2. **Separation of Reasoning from Final Output:**
   User-facing prose is extracted cleanly from `choices[0].message.content`. Internal chain-of-thought in `reasoning_content` is never leaked as raw text into spoken TTS or chat UI.
3. **Resilience & Bounded Retries:**
   - HTTP 401/403 (Authentication/Authorization): Fails immediately without wasteful retries and logs sanitized errors.
   - HTTP 429 (Rate Limit): Automatically backs off with exponential delay (`1s`, `2s`, `4s`) up to `max_retries`.
   - HTTP 500/502/503/504 (Server Outage): Bounded exponential retries before graceful fallback.
   - Network Timeouts: Handled with non-blocking timeouts (`25s` default).
4. **Tool Calling Translation:**
   When Nemotron returns structured `tool_calls`, `NvidiaNemotronProvider` parses the function name and JSON arguments into the ReAct format expected by `AgentBrain`.

---

## 4. Files Added and Modified

| File | Change Type | Description |
|---|---|---|
| `core/ai/providers/nvidia_provider.py` | **Added** | Native `NvidiaNemotronProvider` implementing cloud reasoning, bounded retry, error sanitization, and OpenAI tool calling. |
| `tests/test_nvidia_provider.py` | **Added** | 22 comprehensive tests: provider unit tests, routing, multi-turn conversation, ToolSafetyGate checks, secret redaction, and live API smoke test. |
| `.env.example` | **Added** | Public configuration template containing NVIDIA credentials placeholders. |
| `README.md` | **Added** | Project documentation covering quick start, configuration, testing, and architecture. |
| `docs/NVIDIA_NEMOTRON_INTEGRATION_REPORT.md` | **Added** | Detailed engineering report (this document). |
| `config.py` | **Modified** | Added `nvidia_api_key`, `nvidia_base_url`, `nvidia_model`, `nvidia_temperature`, `nvidia_max_tokens`, `nvidia_timeout_sec`, `nvidia_max_retries`, and `.env` loading overrides. |
| `.env` | **Modified** | Configured `NVIDIA_API_KEY`, `NVIDIA_BASE_URL`, and `NVIDIA_MODEL` (excluded from git). |
| `core/security/privacy_guard.py` | **Modified** | Added pattern 18 to `REDACTION_PATTERNS` for `nvapi-` NVIDIA API keys to guarantee outbound and audit isolation. |
| `core/ai/provider_manager.py` | **Modified** | Registered `nvidia` provider, supported `nemotron` and `nvidia` active provider keys, and added `nvidia:` and `nemotron:` prefix routing. |
| `core/ai/intelligence_router.py` | **Modified** | Added explicit prefix detection for `nvidia:` / `nemotron:`, and added DSA/coding reasoning patterns into `_is_complex_reasoning`. |
| `core/ai/agent_brain.py` | **Modified** | Enhanced `_build_system_prompt` to provide comprehensive educational code and complexity dry runs for technical queries, and added `get_active_provider_name`. |
| `core/conversation_manager.py` | **Modified** | Updated `ai_available` check to respect active NVIDIA provider and forced prefix overrides. |
| `core/jarvis_runtime.py` | **Modified** | Directed pure reasoning queries to `AgentBrain` rather than treating them as compound OS desktop workflow tasks. |
| `modules/system/executor.py` | **Modified** | Supported `explain_concept` intent routing through `ContentGenerator`. |
| `ui/panels/agent_trace_panel.py` | **Modified** | Updated trace panel to display `LAYER 3 // NVIDIA NEMOTRON REASONING` in NVIDIA green when the cloud engine is engaged. |

---

## 5. Environment Variable Setup

The following environment variables are recognized and loaded from `.env` or system environment:

```env
# NVIDIA Nemotron Configuration
NVIDIA_API_KEY=your_nvidia_api_key_here
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=nvidia/nemotron-3.5-super-vl-120b-a12b
NVIDIA_TIMEOUT_SEC=25.0
NVIDIA_MAX_RETRIES=3

# Global Provider Selection
# Options: "none" (local only), "nvidia", "openai", "gemini", "cerebras", "openrouter", "local"
AI_PROVIDER=nvidia

# Privacy Mode
# STRICT (zero cloud), GUARDED (auto-redaction + local audit), RELAXED (development)
JARVIS_PRIVACY_MODE=GUARDED
```

---

## 6. Model and Endpoint Configuration

- **API Base URL:** `https://integrate.api.nvidia.com/v1`
- **Chat Endpoint:** `https://integrate.api.nvidia.com/v1/chat/completions`
- **Models Endpoint:** `https://integrate.api.nvidia.com/v1/models`
- **Primary Model:** `nvidia/nemotron-3.5-super-vl-120b-a12b`
- **Token Budget:** `max_tokens: 2048` (accommodates 300–1000 reasoning tokens + user output)
- **Temperature:** `0.6`

---

## 7. Request Routing Behavior

JARVIS evaluates user utterances across three distinct tiers:

### Tier 1 — Deterministic Local Commands (<2ms)
*Actions:* App launching/closing, system volume, mute, lock screen, taking screenshots, local time/date queries, math calculations.  
*Examples:*  
- `"Jarvis, open Chrome."`  
- `"Jarvis, increase volume."`  
- `"Jarvis, take a screenshot."`  
*Path:* `IntelligenceRouter` (Layer 1) -> `CommandExecutor` -> Native OS API.

### Tier 2 — Local Conversation & Offline Engine
*Actions:* Greetings, identity questions, capabilities, social banter, offline templates.  
*Examples:*  
- `"Hello Jarvis."`  
- `"Who created you?"`  
- `"Tell me a programming joke."`  
*Path:* `IntelligenceRouter` (Layer 2) -> `LocalResponseEngine` / `SocialEngine`.

### Tier 3 — NVIDIA Nemotron Reasoning Brain
*Actions:* Algorithmic explanations, C++ code generation, dry runs, edge-case analysis, LeetCode debugging, time/space complexity analysis, multi-turn contextual programming follow-ups, explicit `nemotron:` / `nvidia:` prompts.  
*Examples:*  
- `"Explain binary search in C++ with an example."`  
- `"Why does my remove-duplicates algorithm fail?"`  
- `"Compare merge sort and quicksort."`  
- `"Explain LeetCode 26 in C++."`  
- `"nemotron: write a recursive DFS graph traversal in C++."`  
*Path:* `IntelligenceRouter` (Layer 3) -> `AgentBrain` -> `ProviderManager` -> `NvidiaNemotronProvider` -> NVIDIA Cloud API.

---

## 8. Tool-Calling and Permission Architecture

When the user asks JARVIS to perform actions that require external tools (e.g., launching an editor, inspecting Chrome tabs, searching the web, drafting notes), the flow enforces strict boundaries:

1. **Tool Whitelist:** Nemotron receives descriptions only for registered capabilities in `ToolRegistry` (e.g. `open_application`, `chrome_open_url`, `morning_briefing`).
2. **Schema Validation:** Arguments returned in `tool_calls` are parsed and validated against expected parameters.
3. **Safety Gate Gatekeeping:** Before executing any tool, `ToolSafetyGate.evaluate_tool(tool_name)` determines if the action is permitted:
   - Read-only actions (`inspect_tab`, `get_system_status`, `search_web`) are allowed in safe mode.
   - Effectful / Write actions (`open_application`, `run_terminal_command`, `write_file`) require explicit confirmation or write authorization.
4. **Observation Feedback:** The structured execution outcome (`success`, `message`, `data`) is formatted into an `Observation` and fed back into the next ReAct turn.
5. **No Hallucinated Success:** JARVIS never informs the user an operation succeeded unless verified by the underlying tool execution return code.
6. **No Arbitrary Shell Execution:** The model cannot run arbitrary bash/powershell strings outside registered tools.

---

## 9. Privacy and Secret-Handling Safeguards

1. **Pattern 18 Redaction:** Added `(r"\bnvapi-[a-zA-Z0-9_-]{20,}\b", "[REDACTED_NVIDIA_KEY]")` to `PrivacyGuard`. Any prompt containing an NVIDIA API key is sanitized before leaving the host.
2. **STRICT Mode Enforcement:** In `STRICT` mode, `privacy_guard.is_cloud_allowed()` returns `False`. All cloud requests to NVIDIA are blocked, logged to `logs/security_audit.db` with status `BLOCKED`, and redirected to local fallbacks.
3. **GUARDED Mode Audit:** In `GUARDED` mode, all outbound prompts are sanitized and audited with prompt length, timestamp, and redaction count.
4. **Log Sanitization:** `NvidiaNemotronProvider._sanitize_error_message` strips API keys from all error logs and exception messages.
5. **Git Safety:** Real keys reside in `.env`, which is strictly ignored by `.gitignore`.

---

## 10. Fallback Behavior

When the NVIDIA API is unreachable or fails:
- **Missing API Key:** JARVIS operates cleanly in local-only mode; UI status reports `None (Local Core)`.
- **401/403 Authentication Error:** Logged clearly without retries; informs user of credential authorization failure without exposing the key.
- **429 Rate Limit:** Automatically executes exponential backoff retries (`1s`, `2s`, `4s`). If all retries are exhausted, falls back to `LocalResponseEngine`.
- **Network Outage / 5xx:** Bounded retries before falling back to local offline responses.
- **Application Stability:** The desktop application never crashes, and the Qt event loop is never blocked.

---

## 11. Automated Test Results

### Focused NVIDIA Provider Suite (`tests/test_nvidia_provider.py`)
```
Ran 22 tests in 6.025s
OK
```
Tests verified:
- Provider initialization and default configurations
- Missing API key graceful degradation
- Successful reasoning response generation
- HTTP 401 authentication error handling without wasteful retries
- HTTP 429 rate limiting with exponential backoff recovery
- Network timeout handling and bounded retry exhaustion
- OpenAI-compatible tool call parsing (`open_application`)
- Safe logging ensuring `nvapi-` keys are never logged
- Layer 1 deterministic commands remain local
- Layer 2 social and offline responses remain local
- Layer 3 programming and DSA queries route to Nemotron
- Explicit `nvidia:` and `nemotron:` prefix routing
- Active provider key resolution
- Multi-turn conversation history preservation
- Conversation history bounding (max turns cap)
- Session clearing and timeout lifecycle
- Tool registry capability integrity
- SafetyGate default-deny policy enforcement
- Safe tool execution in AgentBrain ReAct loop
- Secret redaction of `nvapi-` credentials in PrivacyGuard
- STRICT privacy mode cloud blocking

### Full Repository Regression Suite (`tests/`)
```
Ran 587 tests in 61.339s
OK
```
**0 Failures, 0 Errors, 0 Regressions.** (Up from 565 baseline tests).

---

## 12. Live API Smoke Test Result

Executed against the live endpoint `https://integrate.api.nvidia.com/v1`:
- **Model:** `nvidia/nemotron-3.5-super-vl-120b-a12b`
- **Query:** *"In one concise sentence, what is time complexity in computer science?"*
- **Health Check:** `200 OK` (HTTP latency: ~380ms)
- **Response Duration:** `1.76s`
- **Output:** *"Time complexity is a measure of how the runtime of an algorithm grows relative to the size of its input, typically expressed in big O notation."*
- **Result:** **PASSED**

---

## 13. Known Limitations

1. **Inference Latency:** As a 120-billion parameter reasoning model, response latency over cloud API averages 1.5s–3.5s depending on reasoning depth.
2. **Internet Dependency:** Cloud reasoning requires active internet connectivity. When offline, JARVIS falls back to the local conversational engine and deterministic local commands.
3. **Early Access Availability:** NVIDIA classifies Nemotron 3.5 Super VL 120B as an early-access preview model. Endpoint URLs or token quotas may be adjusted by NVIDIA.

---

## 14. How to Run JARVIS with NVIDIA Enabled

1. Ensure `.env` contains your NVIDIA API key:
   ```env
   NVIDIA_API_KEY=your_nvidia_api_key_here
   NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
   NVIDIA_MODEL=nvidia/nemotron-3.5-super-vl-120b-a12b
   AI_PROVIDER=nvidia
   ```
2. Start JARVIS:
   ```bash
   python main.py
   ```
3. Test a reasoning prompt by voice or text:
   - *"Explain binary search in C++ with an example."*
   - *"Explain LeetCode 26 in C++."*
   - Or with prefix: *"nemotron: compare merge sort and quicksort."*

---

## 15. How to Disable NVIDIA and Use Local Functionality

To run JARVIS purely offline with zero cloud requests:
1. In `.env`, set:
   ```env
   AI_PROVIDER=none
   JARVIS_PRIVACY_MODE=STRICT
   ```
2. Or pass an environment variable when launching:
   ```bash
   JARVIS_AI_PROVIDER=none JARVIS_PRIVACY_MODE=STRICT python main.py
   ```
All deterministic system tools, application launchers, window controls, volume sliders, screenshots, and offline conversational responses continue to function locally.

---

## 16. Recommended Next Improvements

1. **Streaming Audio Pipeline:** Connect Nemotron's token generator (`stream_response`) directly to a streaming sentence-boundary buffer for EdgeTTS to achieve <500ms initial speech latency.
2. **Local C++ Sandbox Tool:** Add a validated Docker/g++ compilation runner tool so JARVIS can optionally compile and run C++ code snippets in a sandbox with user confirmation.
3. **Vision / Multimodal Perception:** Connect the existing `CameraManager` snapshot tool to Nemotron's VL (Vision-Language) capabilities for real-time visual analysis of user desktop screens or camera frames.
