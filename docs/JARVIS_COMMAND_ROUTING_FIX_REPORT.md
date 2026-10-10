# JARVIS Command Routing, Response Fix & Universal Command System Audit Report

**Date:** October 10, 2026  
**Status:** Completed & Verified  
**Test Suite:** 447 Ran, 445 Passed, 2 Skipped, 0 Failures, 0 Errors  

---

## 1. Executive Summary & Root Cause Analysis

### 1.1 Root Cause of Repeated Fallback Message
Previously, JARVIS repeatedly outputted variations of the following generic message:
> *"I'm not sure how to help with that yet, and I can open applications, manage your computer, control volume, open folders and websites, take screenshots, and execute multiple commands."*

A systematic trace of user commands through transcription, normalization, intent routing, execution, and response synthesis revealed five compounding architectural flaws:

1. **Fragmented, Unsynchronized Fallback Chains:**
   - Fallback text generation was fragmented across `core/local_response_engine.py`, `core/conversation_manager.py`, and `modules/system/executor.py`.
   - When a command did not match a primary pattern or when external AI providers were offline, multiple layers consecutively triggered their own fallback generators. Each generator returned the same generic capability recitation.

2. **Greedy Pattern Matching & Misclassification:**
   - In `core/intent_engine.py`, broad regular expressions such as `r"^(?:open|launch|start)\s+(.+)$"` and `close_patterns` caught domain-specific phrases prematurely (e.g., `"close tab"` was caught as closing an application named `"tab"`; `"open ChatGPT in Chrome"` launched generic Chrome without the ChatGPT destination; `"run tests"` was normalized to `"open tests"` and failed application discovery).
   - "Jarvis, help" was historically matched by multi-command or generic intent splitters because comma-separated phrases triggered multi-action heuristics.

3. **Duplicated Spoken vs Display Output Channels:**
   - The runtime previously invoked streaming UI callbacks and blocking TTS playback calls with divergent strings. When TTS encountered latency or fallback provider switching, it re-enqueued raw prompt responses, producing duplicate spoken speech alongside HUD updates.

4. **Absence of Unified Outcome Contracts:**
   - Execution paths returned ad-hoc strings instead of an authoritative, typed outcome contract (`OutcomeType`). This led to handlers claiming success or masking provider failures with generic fallback strings.

5. **Disconnection from Dynamic Tool Truth:**
   - Help responses were hardcoded rather than dynamically derived from actively registered tools, platform capabilities, and installed applications.

---

## 2. Files Changed & Architectural Implementations

### 2.1 File Change Log
1. **`core/capability_service.py` (New):**
   - Central capability registry querying `ToolRegistry`, `ApplicationDiscovery`, and `CustomCommandRegistry` as the single source of truth.
   - Provides `get_help_overview()` (short category overview for "Jarvis, help"), `get_all_commands_reference()` (detailed command catalog with examples and arguments), and `get_scoped_commands(scope)` (filtered capabilities for `browser`, `file`, `system`, etc.).
   - Distinguishes active, temporarily unavailable, and unsupported capabilities.

2. **`core/intent_engine.py`:**
   - Prioritized `browser_tab_control` (`new tab`, `close tab`, `go back`, `forward`, `refresh`, `scroll`, `click`) before generic `close_patterns` and `open_patterns`.
   - Added deterministic routing for `"open <website> in <browser>"` (e.g., `"open ChatGPT in Chrome"`), extracting destination site, resolving known site URLs, and binding target browser.
   - Added scoped help and command discovery patterns (`"list browser commands"`, `"what file operations can you perform"`, `"show all commands"`).
   - Added browser DOM inspection intent (`"read the current webpage"`, `"inspect page"`).
   - Ensured `"Jarvis, help"` is strictly resolved to deterministic `help` intent with zero multi-command splitting.

3. **`modules/system/executor.py`:**
   - Implemented browser-specific destination routing (`intent == "open_website"` with `browser` attribute) calling `BrowserManager.open_browser(browser_name, url)`.
   - Implemented `browser_tab_control` commands (`new_tab`, `close_tab`, `back`, `forward`, `refresh`).
   - Implemented DOM inspection (`read_page`) verifying CDP availability. If CDP is disconnected, truthfully explains: *"Chrome is open, but page interaction is unavailable because CDP is not connected. Launch Chrome with --remote-debugging-port=9222 to enable DOM automation."*
   - Routed help requests through `CapabilityService` for dynamic, truthful capability enumeration.
   - Handled empty search queries by prompting for clarification: *"What would you like me to search for, Sir?"*

4. **`core/jarvis_runtime.py`:**
   - Added `browser_tab_control` and `browser_action` to native OS intents.
   - Routed `help` intent through `CapabilityService` ensuring single, formatted spoken and display responses.
   - Preserved thread safety and single-turn response guarantee.

5. **`core/response_registry.py`:**
   - Preserved evidence message for `open_website` and `help` so the exact formatted output is spoken and displayed synchronously.
   - Enforced `OutcomeType` contract (`SUCCESS`, `MISSING_ARGUMENT`, `AMBIGUOUS_TARGET`, `UNSUPPORTED_CAPABILITY`, `PROVIDER_UNAVAILABLE`, `PERMISSION_DENIED`, `TIMEOUT`, `EXECUTION_FAILED`, `CANCELLED`).

6. **`tests/test_universal_command_system_regression.py` (New):**
   - Regression suite validating all 10 acceptance criteria from Section 7 of the specification.

---

## 3. Universal Command Flow & Precedence Architecture

The routing pipeline strictly adheres to the unified precedence order:
```
Normalize Input
       │
       ▼
1. Explicit Help, Cancel & Safety Commands
       │
       ▼
2. Explicit Search & Target-Specific Routing (Google, YouTube, GitHub, Local Files)
       │
       ▼
3. Deterministic Browser, Application, Filesystem & OS Commands
       │
       ▼
4. Validated Custom Commands & Workflows
       │
       ▼
5. Contextual L2 Handling
       │
       ▼
6. L3 AI Reasoning or Generation
       │
       ▼
7. One Concise Clarification or Failure Response (via ResponseRegistry)
       │
       ▼
Speak Once (TTS) & Display Once (HUD)
```

---

## 4. Supported Command Taxonomy & Example Phrases

| Family | Keywords / Patterns | Example Phrases | Handlers & Tools | Verification / Response |
|---|---|---|---|---|
| **A. Help & Discovery** | `help`, `commands`, `what can you do`, `list capabilities`, `show browser commands` | - *"Jarvis, help."*<br>- *"Jarvis, show all commands."*<br>- *"Jarvis, list browser commands."*<br>- *"Jarvis, what file operations can you perform?"* | `core/capability_service.py` -> `ToolRegistry`, `CustomCommandRegistry` | Returns categorized active tools, commands, or scoped operations. Never shows fake capabilities. |
| **B. Applications** | `open`, `launch`, `start`, `close`, `switch to` | - *"Jarvis, open Chrome."*<br>- *"Jarvis, launch VS Code."*<br>- *"Jarvis, switch to Notepad."*<br>- *"Jarvis, close Blender."* | `modules/system/app_control.py`, `ApplicationResolver` | Resolves installed native executables. If not installed, states missing app once. |
| **C. Websites & Browser** | `open in Chrome`, `go to`, `new tab`, `close tab`, `go back`, `refresh`, `read page` | - *"Jarvis, open ChatGPT in Chrome."*<br>- *"Jarvis, open YouTube."*<br>- *"Jarvis, open a new Chrome tab."*<br>- *"Jarvis, close tab."*<br>- *"Jarvis, read the current webpage."* | `core/os/browser_manager.py`, CDP Client | Launches/focuses browser, navigates to trusted URL. Verifies CDP connection before claiming DOM inspection. |
| **D. Explicit Search** | `search`, `look up`, `find online` | - *"Jarvis search Python tutorials."*<br>- *"Jarvis, search YouTube for Python tutorials."*<br>- *"Jarvis, search GitHub for React dashboard."*<br>- *"Jarvis, search the web for latest AI news."* | `core/os/browser_manager.py` | Priority routing: preserves verbatim query, routes to YouTube/GitHub/Web destination. Asks for query if missing. |
| **E. Files & Folders** | `find`, `open`, `create`, `rename`, `move`, `copy`, `delete`, `list` | - *"Jarvis, open Downloads."*<br>- *"Jarvis, find my Python project."*<br>- *"Jarvis, create a folder named Jarvis Projects on the desktop."* | `modules/system/executor.py`, `SafetyGate` | Resolves exact paths; asks clarification on ambiguous matches; enforces safety confirmations for destructive actions. |
| **F. System Controls** | `volume`, `mute`, `unmute`, `brightness`, `lock`, `shutdown`, `restart`, `screenshot`, `status` | - *"Jarvis, mute volume."*<br>- *"Jarvis, set volume to 50."*<br>- *"Jarvis, take a screenshot."*<br>- *"Jarvis, lock computer."* | `core/platform/windows_platform.py` | Native Windows COM/PowerShell controls. Truthful success reporting. |
| **G. AI & Content Gen** | `write`, `draft`, `summarize`, `explain`, `analyze`, `code`, `debug` | - *"Jarvis, explain this Python error."*<br>- *"Jarvis, draft an email to the team."* | `core/ai/provider_manager.py` (L3 AI) | Uses configured AI provider (OpenAI, Anthropic, Ollama). If offline, reports specific provider error. |
| **H. Custom Commands** | `add command`, `when I say`, `list custom commands`, `test` | - *"Jarvis, add a command named Focus Mode."*<br>- *"Jarvis, when I say Start Coding, open VS Code and my project folder."*<br>- *"Jarvis, list my custom commands."* | `core/custom_commands/workflow_engine.py` | SQLite backed, strictly validated tool calls. Zero `eval` or dynamic code execution. |

---

## 5. Test Suite Results & Regression Verification

### 5.1 Full Test Suite Execution Summary
Executed via `python -m unittest discover -s tests -p "test_*.py"`:
- **Total Tests Executed:** 447
- **Passed:** 445
- **Skipped:** 2 (Hardware-specific audio device tests in CI mode)
- **Failures:** 0
- **Errors:** 0
- **Execution Time:** ~36.1s

### 5.2 Universal Command System Regression Tests (`tests/test_universal_command_system_regression.py`)
All 10 acceptance criteria from Section 7 of the Master Prompt were verified:

| Test Case | Scenario Tested | Result | Verification Detail |
|---|---|---|---|
| `test_01_jarvis_help_not_multi_command` | "Jarvis, help" classification | **PASSED** | Intent resolved to `help`, not `multi_command`. Single overview returned. |
| `test_02_no_duplicate_generic_response` | Zero duplicate fallback output | **PASSED** | Response generated once via `ResponseRegistry`; zero duplicate speech enqueued. |
| `test_03_open_chatgpt_in_chrome` | "Open ChatGPT in Chrome" routing | **PASSED** | Intent `open_website`, site `chatgpt`, browser `chrome`, target `https://chat.openai.com/`. |
| `test_04_app_launch_distinct_from_website` | App vs Website disambiguation | **PASSED** | "open chrome" -> `open_app`; "open youtube.com" / "open youtube" -> `open_website`. |
| `test_05_explicit_search_routing` | YouTube, GitHub, Web search priority | **PASSED** | "search youtube for python" -> target `youtube`; preserves verbatim query text. |
| `test_06_missing_arguments_and_ambiguity` | Empty search argument handling | **PASSED** | Prompts concise clarification: *"What would you like me to search for, Sir?"*. |
| `test_07_truthful_failure_reporting` | Nonexistent app error reporting | **PASSED** | Reports missing app truthfully (`UNSUPPORTED_CAPABILITY`) instead of generic fallback. |
| `test_08_dynamic_capability_list` | Dynamic ToolRegistry synchronization | **PASSED** | `CapabilityService` categorizes active registered tools without static stale lists. |
| `test_09_custom_command_persistence_safety` | Custom command storage and validation | **PASSED** | Workflow stored in SQLite; validates tools; forbids arbitrary script execution. |
| `test_10_browser_tab_and_action_controls` | Tab control and DOM read verification | **PASSED** | "new tab", "close tab", "go back" route to `browser_tab_control`; "read webpage" routes to `browser_action`. |

---

## 6. Real-World Smoke Tests & Verification

1. **Browser Navigation Smoke Test:**
   - Tested `"open ChatGPT in Chrome"`: Verified `BrowserManager` selects Chrome launcher and navigates to `https://chat.openai.com/` without falling back to Google search.
2. **CDP Offline Guidance Test:**
   - Tested `"read the current webpage"`: When Chrome is running without remote debugging port `9222`, the system accurately informs the user that CDP is not connected and provides the exact flag (`--remote-debugging-port=9222`) rather than hallucinating page content.
3. **Tab Navigation vs App Closing:**
   - Tested `"close tab"`: Correctly dispatches `ctrl+w` browser tab closure instead of attempting to close an OS window named `"tab"`.
4. **Speech Sanitization & Single Voice Output:**
   - Verified that `SpeechSanitizer` cleans formatted output, while `JarvisRuntime` issues exactly one TTS invocation per user turn.

---

## 7. Known Limitations & Untested Features

1. **CDP Port Requirement:**
   - DOM interaction (`click`, `scroll`, `read page`) requires Google Chrome or Microsoft Edge to be started with `--remote-debugging-port=9222`. When launched normally via Windows shell, DOM automation is truthfully reported as offline.
2. **Multi-Monitor Window Snapping:**
   - Advanced multi-monitor coordinate placement is limited to standard Windows API bounds (`win32gui`); custom virtual desktop switching requires Windows 11 VirtualDesktopManager COM interfaces.
3. **Wake-Word Hardware Devices in Headless/CI:**
   - 2 tests skipped correspond to physical audio hardware checks (`test_wakeword.py` real mic streams), which gracefully fall back to mock detectors when no physical microphone is attached.
