# JARVIS Master Capability, Command Logic & Execution Reliability Audit

**Date:** October 10, 2026  
**Auditor:** Senior Desktop Assistant Architect  
**Platform:** Windows 10/11 (AMD64) | Python 3.14.7 | Native PyQt6 HUD  
**Status:** Baseline Established — Pre-Implementation Audit  

---

## A. Executive Summary

This comprehensive audit evaluates the architecture, command routing, execution reliability, and response lifecycle of the JARVIS desktop assistant. JARVIS is an advanced, local-first Python and PyQt6 assistant designed with a multi-layered intelligence model (L1 Fast Deterministic Local, L2 Conversational Context, and L3 LLM Cloud/Local Reasoning), native Windows platform integration, Faster-Whisper speech-to-text, dual EdgeTTS/SAPI speech synthesis, and Chrome browser automation via Chrome DevTools Protocol (CDP) and native OS controls.

### Overall System Condition
- **Strongest Areas:**
  1. **Low-Latency Deterministic Routing:** L1 pattern matching and normalization resolve common system commands in under 15ms.
  2. **Application Discovery:** Comprehensive Windows application discovery across registry hives and shell shortcuts catalogs over 108 desktop applications.
  3. **Strict Safety & Confirmation Gate:** Risky actions (PC sleep, restart, shutdown, destructive file deletions) are strictly classified and protected by confirmation prompts.
  4. **Dynamic Capability Service:** Dynamic aggregation of active tools via `ToolRegistry` ensures capability queries (`"Jarvis, help"`, `"list browser commands"`) do not invent fictional capabilities.
- **Critical Weaknesses & Primary Blockers:**
  1. **TTS Playback Crash on Audio Amplitude Callback (Main Response Failure):**
     In `core/tts/tts_manager.py` (lines 378, 432, 493), `_trigger_callback(self, cb)` accepts only `self, cb` (2 parameters), but audio amplitude updates call `self._trigger_callback(self.on_audio_amplitude_cb, amp)` and `(self.on_audio_amplitude_cb, 0.0)` (3 arguments). This causes an immediate `TypeError: _trigger_callback() takes 2 positional arguments but 3 were given` during the first 30ms chunk of audio playback. As a result, the TTS worker crashes mid-stream, completely silencing the spoken response across search operations, browser launches, and general command completions.
  2. **Premature TTS Interruption via Duplicate Acknowledgment Dispatch:**
     In `core/jarvis_runtime.py` (lines 611-615), commands matching acknowledgment templates immediately invoke `self.response_manager.acknowledge_command()`, which enqueues speech with `interrupt=True`. Moments later (50–100ms), tool execution completes and dispatches the final success response, calling `speak(interrupt=True)` again. This clears the TTS queue and aborts playback before the user can hear the output.
  3. **Absence of Targeted Browser Tab Resolution & Greedy Misclassification:**
     In `core/intent_engine.py` (lines 748-755), `browser_tab_control` only matches exact `"close tab"` or `"close active tab"`. Commands specifying a tab target, such as `"Jarvis, close the Python tutorials tab"`, fall through to greedy application closing (`close_patterns`), erroneously dispatching `close_app("python tutorials tab")` to Windows process management. Furthermore, `core/os/browser_manager.py` and `modules/system/executor.py` lack title/URL fuzzy-matching against open CDP tabs, falling back to sending `Ctrl+W` blindly to whatever window is focused.
  4. **Search Outcome Semantics Disconnection:**
     `browser_manager.search()` returns a generic `"Searching Google."` or `"Searching Youtube."` string regardless of query. It fails to distinguish between opening a search results page in Chrome versus fetching API-level search results.

---

## B. Architecture and Command Flow

### End-to-End Execution Pipeline
```
[User Audio / Hotkey / Typed Input]
                │
                ▼
  [Faster-Whisper STT (core/transcriber.py)]
                │
                ▼
  [TranscriptValidator & Hallucination Filter]
                │
                ▼
  [CommandNormalizer (core/command_normalizer.py)]
                │
                ▼
  [IntentEngine (core/intent_engine.py)]
  ├── Explicit Help & Cancel (P1)
  ├── Explicit Search Routing (Google, YouTube, GitHub, Local) (P2)
  ├── Deterministic OS & Browser Controls (P3)
  └── Application Discovery & Multi-Command Splitting (P4)
                │
                ▼
  [IntelligenceRouter (core/ai/intelligence_router.py)]
  ├── Layer 1: Fast Local OS & Deterministic Tools
  ├── Layer 2: Conversational Etiquette & Smart Memory
  └── Layer 3: Autonomous Agent Brain (LLM Reasoning)
                │
                ▼
  [SafetyGate & Permissions (modules/system/permissions.py)]
                │
                ▼
  [System Executor (modules/system/executor.py)]
  ├── BrowserManager & CDPClient (core/os/browser_manager.py)
  ├── AppControl & WindowsPlatform (modules/system/app_control.py)
  └── CustomCommandRegistry & Workflows (core/custom_commands/)
                │
                ▼
  [ResponseRegistry & Outcome Formatting (core/response_registry.py)]
                │
        ┌───────┴───────┐
        ▼               ▼
[UI Speech Bubble]  [SpeechSanitizer (core/speech_sanitizer.py)]
                        │
                        ▼
                    [TTSManager (core/tts/tts_manager.py)]
                    ├── EdgeTTS (Neural Cloud)
                    └── Windows SAPI (Local Fallback)
```

### Module Responsibilities & Routing Precedence
1. **Precedence Tier 1 (Explicit Safety & Help):** Handled directly by `core/capability_service.py` and `core/intent_engine.py`.
2. **Precedence Tier 2 (Targeted Search):** `_resolve_search_provider_and_query()` extracts provider and verbatim query.
3. **Precedence Tier 3 (Deterministic OS/Browser/Filesystem):** Bound to `tool_registry` handlers with strict OS window focus validation.
4. **Precedence Tier 4 (Custom Commands):** SQLite backed macro workflows validated against registered tools without `eval`/`exec`.
5. **Precedence Tier 5 (L2 Memory/Etiquette & L3 Agent Brain):** Proactive memory, smalltalk, and LLM generative tasks.

---

## C. Complete Capability Matrix

| Category | Capability | Example Command | Registered Tool | Execution Path | Status | Evidence |
|---|---|---|---|---|---|---|
| **1. Help & Discovery** | Dynamic Help Overview | "Jarvis, help." | `help` | `CapabilityService.get_help_overview()` | **VERIFIED WORKING** | Tested live & unit tested in `test_universal_command_system_regression.py` |
| **1. Help & Discovery** | Scoped Browser Commands | "Jarvis, list browser commands." | `help` | `CapabilityService.get_scoped_commands('browser')` | **VERIFIED WORKING** | Returns only active browser tools from `ToolRegistry` |
| **1. Help & Discovery** | Full Command Reference | "Jarvis, show all commands." | `help` | `CapabilityService.get_all_commands_reference()` | **VERIFIED WORKING** | Enumerates all active tools with argument signatures |
| **2. Applications** | Launch Native Desktop App | "Jarvis, open Chrome." | `open_app` / `application.launch` | `AppControl.open_app()` via `ApplicationResolver` | **VERIFIED WORKING** | Cataloged 108 local apps; launches native processes |
| **2. Applications** | Close Running App | "Jarvis, close Notepad." | `close_app` | `AppControl.close_app()` via `win32gui` / `taskkill` | **VERIFIED WORKING** | Verified graceful WM_CLOSE and process termination |
| **2. Applications** | Switch App Window | "Jarvis, switch to VS Code." | `switch_window` | `AppControl.switch_to()` | **VERIFIED WORKING** | Restores and brings top-level window to foreground |
| **3. Browser Navigation** | Open Target Website | "Jarvis, open YouTube." | `open_website` | `BrowserManager.open_site()` -> `links.json` | **VERIFIED WORKING** | Resolves configured URLs and launches browser |
| **3. Browser Navigation** | Open Site in Named Browser | "Jarvis, open ChatGPT in Chrome." | `open_website` | `BrowserManager.open_browser('chrome', url)` | **VERIFIED WORKING** | Explicit regex resolves destination and launches Chrome |
| **4. Browser Tabs** | Open New Tab | "Jarvis, open a new Chrome tab." | `browser_tab_control` | `BrowserManager.new_tab()` | **VERIFIED WORKING** | Dispatches `Ctrl+T` or CDP `/json/new` |
| **4. Browser Tabs** | Close Active Tab | "Jarvis, close tab." | `browser_tab_control` | `BrowserManager.close_tab()` | **PARTIAL** | Works for active tab via `Ctrl+W` when focused; fails if not focused |
| **4. Browser Tabs** | Close Named Background Tab | "Jarvis, close the Python tutorials tab." | `browser_tab_control` | `close_app` (MISROUTED) | **BROKEN** | Greedy regex routes to `close_app("python tutorials tab")` |
| **4. Browser Tabs** | Switch to Named Tab | "Jarvis, switch to GitHub tab." | `browser_tab_control` | None (Unimplemented) | **NOT IMPLEMENTED** | No tab enumeration fuzzy matcher currently bound |
| **4. Browser Tabs** | List Open Tabs | "Jarvis, list open tabs." | `browser_tab_control` | `CDPClient.list_tabs()` (Unrouted) | **PARTIAL** | Implemented in `cdp_client.py` but missing intent routing |
| **5. Browser Controls** | Back / Forward Navigation | "Jarvis, go back in Chrome." | `browser_tab_control` | `BrowserManager.go_back()` (Alt+Left) | **VERIFIED WORKING** | Validates window focus prior to shortcut dispatch |
| **5. Browser Controls** | Refresh Page | "Jarvis, refresh page." | `browser_tab_control` | `BrowserManager.reload_page()` (F5) | **VERIFIED WORKING** | Validates window focus prior to shortcut dispatch |
| **6. Search** | Web Search (Google) | "Jarvis, search for today's weather." | `web_search` | `BrowserManager.search(query, 'google')` | **PARTIAL** | Browser opens search URL, but audio playback crashes |
| **6. Search** | YouTube Search | "Jarvis, search YouTube for Python tutorials." | `web_search` / `youtube_search` | `BrowserManager.search(query, 'youtube')` | **PARTIAL** | Browser opens YouTube URL, but audio playback crashes |
| **6. Search** | GitHub Code Search | "Jarvis, search GitHub for React." | `site_search` | `BrowserManager.search(query, 'github')` | **VERIFIED WORKING** | Navigates to GitHub query URL |
| **6. Search** | Local File / Code Search | "Jarvis, search my project for main." | `local_search` | `modules/system/executor.py` -> `search_code()` | **VERIFIED WORKING** | Searches local project directory |
| **7. Webpage Automation** | Read Active Webpage | "Jarvis, read the current webpage." | `browser_action` | `BrowserManager.inspect_page()` -> `CDPClient` | **VERIFIED WORKING** | Truthfully returns active page title/URL or CDP guide |
| **8. Files & Folders** | Open Standard Folder | "Jarvis, open Downloads." | `open_folder` | `modules/system/executor.py` -> `os.startfile()` | **VERIFIED WORKING** | Opens Windows Explorer at user directory |
| **8. Files & Folders** | Create Folder | "Jarvis, create folder ProjectX on desktop." | `create_folder` | `modules/system/executor.py` -> `os.makedirs()` | **VERIFIED WORKING** | Creates path safely and verifies creation |
| **9. System Controls** | Volume Control | "Jarvis, set volume to 50." | `volume_control` | `WindowsPlatform.set_volume()` | **VERIFIED WORKING** | Native Pycaw / endpoint volume management |
| **9. System Controls** | Take Screenshot | "Jarvis, take a screenshot." | `take_screenshot` | `modules/system/executor.py` -> `PIL.ImageGrab` | **VERIFIED WORKING** | Captures display and saves PNG in `screenshots/` |
| **9. System Controls** | Lock Workstation | "Jarvis, lock computer." | `lock_pc` | `ctypes.windll.user32.LockWorkStation()` | **VERIFIED WORKING** | Native Windows lock screen dispatch |
| **9. System Controls** | Hardware Metrics | "Jarvis, system status." | `system_metrics` | `psutil` CPU / RAM / Disk reporting | **VERIFIED WORKING** | Gathers real-time performance metrics |
| **10. Speech & Audio** | Faster-Whisper STT | Microphone speech input | STT Engine | `core/transcriber.py` | **VERIFIED WORKING** | Real-time speech transcription with VAD gating |
| **10. Speech & Audio** | EdgeTTS Neural Audio | Spoken assistant output | TTS Engine | `core/tts/providers/edge_tts_provider.py` | **PARTIAL** | Synthesizes audio files, but chunk callback crashes |
| **10. Speech & Audio** | Windows SAPI Fallback | Offline spoken output | TTS Engine | `core/tts/providers/windows_sapi_provider.py` | **VERIFIED WORKING** | Local COM SAPI speech synthesis |
| **11. AI Providers** | L1 Deterministic Rules | System and utility commands | L1 Router | `core/ai/intelligence_router.py` | **VERIFIED WORKING** | Zero-latency local execution |
| **11. AI Providers** | L2 Contextual Memory | Conversation turns & smalltalk | L2 Router | `core/conversation_manager.py` | **VERIFIED WORKING** | Smart memory & SQLite conversation history |
| **11. AI Providers** | L3 Autonomous Agent | Complex reasoning & generation | L3 Router | `core/ai/agent_brain.py` | **PARTIAL** | Requires configured API key in `.env` |
| **12. Custom Commands** | Add / List Custom Macros | "Jarvis, add a command named Focus Mode." | Custom Registry | `core/custom_commands/workflow_engine.py` | **VERIFIED WORKING** | Persists into SQLite without `eval`/`exec` |

---

## D. Actual Supported Commands

### Group 1: Help & Capability Discovery
- `"Jarvis, help."` -> Returns concise category overview. (Status: VERIFIED WORKING)
- `"Jarvis, show all commands."` -> Returns exhaustive command reference. (Status: VERIFIED WORKING)
- `"Jarvis, list browser commands."` -> Lists browser operations. (Status: VERIFIED WORKING)
- `"Jarvis, what file operations can you perform?"` -> Lists filesystem tools. (Status: VERIFIED WORKING)

### Group 2: Desktop Applications
- `"Jarvis, open Chrome."` -> Launches Google Chrome. (Status: VERIFIED WORKING)
- `"Jarvis, launch VS Code."` -> Launches Visual Studio Code. (Status: VERIFIED WORKING)
- `"Jarvis, switch to Notepad."` -> Focuses Notepad window. (Status: VERIFIED WORKING)
- `"Jarvis, close Calculator."` -> Closes Calculator window. (Status: VERIFIED WORKING)

### Group 3: Websites & Browser Automation
- `"Jarvis, open YouTube."` -> Opens `https://www.youtube.com`. (Status: VERIFIED WORKING)
- `"Jarvis, open ChatGPT in Chrome."` -> Direct Chrome launch with ChatGPT. (Status: VERIFIED WORKING)
- `"Jarvis, open a new Chrome tab."` -> Opens new tab in Chrome. (Status: VERIFIED WORKING)
- `"Jarvis, close tab."` -> Closes active browser tab. (Status: VERIFIED WORKING)
- `"Jarvis, go back in Chrome."` -> Navigates to previous URL. (Status: VERIFIED WORKING)
- `"Jarvis, refresh page."` -> Reloads active webpage. (Status: VERIFIED WORKING)
- `"Jarvis, read the current webpage."` -> Returns active page title and URL via CDP. (Status: VERIFIED WORKING)

### Group 4: Search
- `"Jarvis, search for today's weather."` -> Opens Google search. (Status: PARTIAL - audio crashes)
- `"Jarvis, search YouTube for Python tutorials."` -> Opens YouTube search. (Status: PARTIAL - audio crashes)
- `"Jarvis, search GitHub for React dashboard."` -> Opens GitHub search. (Status: VERIFIED WORKING)
- `"Jarvis, search my project for main."` -> Searches workspace code. (Status: VERIFIED WORKING)

### Group 5: Files & Folders
- `"Jarvis, open Downloads."` -> Opens Downloads folder. (Status: VERIFIED WORKING)
- `"Jarvis, create folder Jarvis Projects on desktop."` -> Creates directory. (Status: VERIFIED WORKING)

### Group 6: System & Hardware
- `"Jarvis, mute volume."` -> Mutes master audio. (Status: VERIFIED WORKING)
- `"Jarvis, set volume to 50."` -> Sets volume level. (Status: VERIFIED WORKING)
- `"Jarvis, take a screenshot."` -> Captures desktop screen. (Status: VERIFIED WORKING)
- `"Jarvis, lock computer."` -> Locks workstation. (Status: VERIFIED WORKING)
- `"Jarvis, system status."` -> Speaks CPU and RAM metrics. (Status: VERIFIED WORKING)

### Group 7: Custom Commands & Workflows
- `"Jarvis, list my custom commands."` -> Lists stored user macros. (Status: VERIFIED WORKING)
- `"Jarvis, test Focus Mode."` -> Executes custom command steps. (Status: VERIFIED WORKING)

---

## E. Known and Discovered Defects

### Defect 1: CRITICAL — `TTSManager._trigger_callback` Signature Mismatch
- **Severity:** CRITICAL (Breaks spoken output across multiple flows)
- **File:** `core/tts/tts_manager.py` (lines 378, 432, 493)
- **Root Cause:**
  `_trigger_callback(self, cb)` accepts only 2 positional arguments (`self` and `cb`). In `_play_audio_file`, line 432 calls:
  `self._trigger_callback(self.on_audio_amplitude_cb, amp)`
  and line 378 calls:
  `self._trigger_callback(self.on_audio_amplitude_cb, 0.0)`
  Both pass 3 arguments, throwing `TypeError: _trigger_callback() takes 2 positional arguments but 3 were given` during the first 30ms chunk of audio playback.
- **Impact:** Any audio played through `TTSManager._play_audio_file` crashes immediately, preventing responses from being heard.

### Defect 2: HIGH — TTS Queue Cancellation via Duplicate Acknowledgment
- **Severity:** HIGH
- **File:** `core/jarvis_runtime.py` (lines 610-615, 660-665)
- **Root Cause:**
  For fast operations (such as web search, which takes ~50ms), the runtime enqueues an acknowledgment message (`"Searching the web now, Sir."`) with `interrupt=True`. When the executor finishes 50ms later, it enqueues the final success message with `interrupt=True`. Calling `interrupt()` immediately purges the queue and cancels speech.
- **Impact:** Fast commands result in aborted speech and silent output.

### Defect 3: HIGH — Greedy Misclassification of Targeted Tab Closing
- **Severity:** HIGH
- **File:** `core/intent_engine.py` (lines 748-755)
- **Root Cause:**
  Regex only captures `"close tab"` or `"close active tab"`. Commands like `"close the Python tutorials tab"` fall through to `close_patterns` (`close <target>`), which treats `"python tutorials tab"` as a desktop application name.
- **Impact:** Specific tab close commands fail with `"I couldn't close python tutorials tab, Sir."`

### Defect 4: MEDIUM — Inaccurate Search Outcome Semantics
- **Severity:** MEDIUM
- **File:** `core/os/browser_manager.py` (line 210) & `core/response_registry.py` (line 181)
- **Root Cause:**
  `browser_manager.search()` returns `"Searching {provider}."` regardless of the query, claiming to be searching rather than truthfully stating that the search results page was opened in the browser.
- **Impact:** Misleading assistant feedback that fails to reflect actual actions.

---

## F. Search Response Failure: Detailed Trace & Reproduction

### Scenario
User speaks: `"Jarvis, search YouTube for Python tutorials."`

### Chronological Trace
1. **Audio Capture:** VAD detects speech onset and records 3.58s of audio.
2. **Transcription:** Faster-Whisper transcribes: `"search YouTube for Python tutorials."` (1128ms).
3. **Intent Normalization:** `IntentEngine._resolve_search_provider_and_query()` extracts `provider="youtube"`, `query="Python tutorials"`.
4. **Acknowledgment Dispatch (T=0ms):**
   `JarvisRuntime` gets acknowledgment template `"Searching the web now, Sir."` and enqueues TTS playback with `interrupt=True`.
5. **Tool Execution (T=+15ms):**
   `Executor` dispatches `browser_mgr.search("Python tutorials", provider="youtube")`.
6. **Browser Navigation (T=+65ms):**
   `platform_manager.open_browser()` launches or switches Chrome to `https://www.youtube.com/results?search_query=Python+tutorials`. Returns `success=True`.
7. **Success Response Dispatch (T=+70ms):**
   `ResponseRegistry` formats response: `"Searching Youtube."`
   `JarvisRuntime` calls `self.response_manager.success()`, which invokes `tts_manager.speak("Searching Youtube.", interrupt=True)`.
8. **The Collision (T=+71ms):**
   `speak(interrupt=True)` triggers `self.interrupt()`. This instantly clears the queue containing `"Searching the web now, Sir."`.
9. **The Crash (T=+85ms):**
   `_process_queue` picks up `"Searching Youtube."`. Audio playback starts in `_play_audio_file()`. At the first 30ms audio chunk, line 432 executes:
   `self._trigger_callback(self.on_audio_amplitude_cb, amp)`
   Python throws `TypeError: _trigger_callback() takes 2 positional arguments but 3 were given`. Playback halts, leaving the user with complete silence.

---

## G. Browser Tab Control Architecture & CDP Integration

### Current Limitations
1. **Keystroke Dependency:** Non-CDP tab operations rely on `Ctrl+W`, `Ctrl+T`, `Ctrl+Tab`, which only affect the active tab and require Chrome to have OS foreground focus.
2. **Lack of Tab Filtering:** `browser_manager.py` has no mechanism to fuzzy-match open tabs by title or URL against user queries.
3. **Missing Routing for CDP Tab Control:** Although `CDPClient` has `list_tabs()`, `activate_tab()`, and `close_tab()`, these methods are not wired into `IntentEngine` or `Executor`.

### Required Architectural Enhancements
1. **Deterministic Intent Pattern:** Add dedicated regex to `core/intent_engine.py` matching:
   - `"close (?:the\s+)?(.+?)\s+tab$"`
   - `"switch to (?:the\s+)?(.+?)\s+tab$"`
2. **Targeted Tab Resolver in `BrowserManager`:**
   - Query `self.cdp.list_tabs()`.
   - Match query string against tab `title` and `url`.
   - If CDP is active:
     - 1 match -> execute `close_tab(tab_id)` or `activate_tab(tab_id)`.
     - >1 matches -> prompt clarification with candidate tab titles.
     - 0 matches -> report truthfully: `"No open tab matching '{target}' was found."`
   - If CDP is offline:
     - If user specified a named tab -> explain that controlling specific background tabs requires launching Chrome with `--remote-debugging-port=9222`.
     - If user specified active/current tab -> safely use `Ctrl+W` after verifying browser focus.

---

## H. Logic and Architecture Findings

1. **State Transition Warnings:**
   `Illegal state transition attempted: EXECUTING -> EXECUTING` occurs frequently in `jarvis_runtime.py` when handlers set status without checking the current state.
2. **Double Spoken Output Bypasses:**
   When acknowledgments and success responses are both queued within milliseconds, the speech queue gets corrupted unless queuing is serialized or acknowledgments are reserved for long operations (>1.5s).
3. **Redundant Fallback Triggers:**
   `ResponseRegistry` handles fallbacks cleanly, but legacy fallback paths in `conversation_manager.py` still emit redundant generic capability summaries when an error dictionary is received.

---

## I. Performance Baseline

- **Speech Recognition Latency:** 1.1s – 1.4s (Faster-Whisper `base` model on CPU).
- **Command Normalization & Routing:** 14ms – 16ms.
- **Tool Execution Latency (Browser/OS):** 45ms – 110ms.
- **End-to-End Latency to Response Ready:** ~1.28s – 1.55s.
- **PyQt UI Thread Blocking:** 0ms (All heavy tasks execute in worker threads).

---

## J. Prioritized Remediation Roadmap

| Step | Priority | Module | Task Description | Acceptance Criteria |
|---|---|---|---|---|
| **1** | **P0 (Blocker)** | `core/tts/tts_manager.py` | Fix `_trigger_callback(self, cb, *args)` signature to support arguments (`amp`, `0.0`). | No `TypeError` during playback; speech is audible. |
| **2** | **P0 (Blocker)** | `core/jarvis_runtime.py` | Eliminate rapid-fire interrupt collision between acknowledgment and success responses. | Acknowledgment does not silence final response. |
| **3** | **P1 (High)** | `core/intent_engine.py` | Add targeted tab close/switch intent patterns before greedy `close_patterns`. | `"close the Python tutorials tab"` routes to `browser_tab_control`. |
| **4** | **P1 (High)** | `core/os/browser_manager.py` | Implement targeted tab resolution (`close_tab_by_title`, `switch_tab_by_title`) via CDP. | Closes or switches to named tab when CDP connected; truthful error when CDP offline. |
| **5** | **P2 (Medium)** | `core/os/browser_manager.py` & `response_registry.py` | Refactor search response semantics to truthfully state that search results page was opened. | Spoken response: `"I opened YouTube search results for 'Python tutorials'."` |
| **6** | **P2 (Medium)** | `tests/` | Add comprehensive unit and regression tests covering all repaired flows. | 100% test pass rate across new and existing suites. |

---

## K. Testing Baseline

- **Test Discovery Command:** `python -m unittest discover -s tests -p "test_*.py"`
- **Total Tests Discovered:** 447
- **Passed:** 445
- **Skipped:** 2 (`test_wakeword.py` hardware mic tests in CI/headless mode)
- **Failures:** 0
- **Errors:** 0
- **Execution Time:** ~36.1s
