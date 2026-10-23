# JARVIS Intelligence Baseline & Phase 0 Audit Report

**Date:** 2026-10-19  
**Platform:** Windows 11 (x64)  
**Python Runtime:** Python 3.14.7  
**UI Framework:** PyQt6  
**Repository Branch:** `main` (Ahead of origin by 6 commits)  
**Baseline Test Result:** **549 Passed / 0 Failed / 0 Errors** (Execution time: 52.58s)

---

## 1. Executive Summary

This audit establishes the ground-truth technical baseline for the **JARVIS Personal AI Desktop Assistant** prior to making broad architectural modifications. 

JARVIS is built as a modular desktop system combining deterministic automation (L1), structured multi-step planning (L2), and adaptive language model reasoning (L3). The existing codebase contains robust building blocks: a comprehensive 549-test suite, an extensible `ToolRegistry`, a deterministic `CommandExecutor`, an active `OpenWakeWordDetector` ONNX pipeline (`hey_jarvis`), an audio transcription validator with hallucination suppression, and multi-tier TTS fallback.

However, several critical gaps must be resolved to achieve the user's vision of an always-available, conversational, local-first assistant:
1. **Startup & Lifecycle:** Windows auto-start (`core/startup.py`) is implemented at the registry level but disconnected from user commands, intent routing, and UI controls. No single-instance guard exists, risking audio hardware collisions.
2. **State Machine & Interruption:** The runtime state machine currently defines 9 states. It lacks explicit states for `WAITING_FOR_CONFIRMATION`, `PLANNING`, `PAUSED`, `INTERRUPTED`, and `CANCELLING`. TTS interruption relies on boolean lock polling rather than formal cancellation tokens and context-preserving state rollback.
3. **Working Memory:** While persistent SQLite storage and session turn buffers exist, there is no structured Working Memory tracking active plans, pending questions, active goals, and pending user corrections.
4. **Workspaces Subsystem:** Personal automation templates (Study, Software Development, Gaming, Excel, Research, Custom) do not yet exist as a unified engine.
5. **Engineering Mentorship:** Explaining plans, code architectures, and debugging trade-offs is not yet formalized into the response pipeline.

---

## 2. Test Baseline & Actual Command Output

The complete test suite was executed against the current working tree.

### Command
```powershell
python -m unittest discover -s tests -p "test_*.py"
```

### Verified Terminal Output
```text
Ran 549 tests in 52.583s

OK
```

### Test Suite Distribution
- `tests/test_track_a_reliability.py`: 12 tests (audio device resolution, TTS fallbacks, transcript validator)
- `tests/test_track_b_social.py`: 23 tests (social engine, mood detection, personality adaptation)
- `tests/test_track_c_agentic_execution.py`: 18 tests (multi-step planner, tool registry, dependency skip, retries)
- `tests/test_jarvis_runtime.py`: 14 tests (runtime state transitions, command processing)
- `tests/test_multi_step_planner.py`: 11 tests (ordered step execution, recovery policies)
- `tests/test_wakeword.py`: 9 tests (openwakeword ONNX loading, mock fallback)
- `tests/test_memory.py`: 28 tests (SQLite persistence, turn history, secret redaction)
- `tests/test_system_executor.py`: 44 tests (apps, windows, volume, browser, media)
- Remaining modular test suites: 390 tests covering listeners, normalizers, camera manager, intent engine, and network tools.

### Identified Test Warnings
- **ResourceWarning:** Unclosed SQLite database connections detected during mock connection tear-downs in memory unit tests (`<sqlite3.Connection object>`). Explicit connection closure in fixture tear-downs should be enforced.

---

## 3. Verified Working Functionality

The following subsystems are verified operational by code inspection and direct unit/integration tests:

| Subsystem | Primary Modules | Status & Verified Capabilities |
| :--- | :--- | :--- |
| **L1 Deterministic Execution** | `modules/system/executor.py`, `core/command_normalizer.py` | Launches registered apps (Chrome, VS Code, Notepad, Terminal), browser search, tab management, media play/pause, volume stepping, lock workstation, screenshot capture, weather querying. |
| **Tool Registry & Safety Gate** | `core/tool_registry.py`, `core/security/safety_gate.py` | Schema-validated tool execution, risk tier assignment (`LOW`, `MEDIUM`, `HIGH`), permission verification, execution timeout guards. |
| **Wake Word Detection** | `core/wakeword.py` | Verified `openwakeword` ONNX integration with `hey_jarvis` model (`Model(wakeword_models=['hey_jarvis'], inference_framework='onnx')`). Real-time audio chunk feeding supported. |
| **Transcript Sanitization** | `core/transcript_validator.py` | Filters repetitive Whisper hallucinations (e.g., repeating "thank you", "bye bye", or background noise loops), normalizes casing, validates command candidates. |
| **Multi-Provider TTS** | `core/tts/tts_manager.py` | Three-layer fallback: `EdgeTTSProvider` (high-quality online neural) -> `WindowsSAPIProvider` (local native Windows voice) -> `Pyttsx3Provider` (cross-platform offline). Audio interrupt triggers playback kill. |
| **Multi-Step Planner (L2)** | `core/multi_step_planner.py` | Parses complex user utterances into ordered `AgentTask` and `TaskStep` objects, enforces dependency DAGs, skips dependents on failure, applies bounded retries (max 2) strictly on safe/idempotent tools. |
| **Persistent Memory** | `memory/persistent_memory.py`, `memory/conversation_persistence.py` | SQLite store (`logs/smart_memory.db`) with tables for user profiles, episodic events, and knowledge notes. Built-in regex redaction suite for API keys, passwords, and tokens. |
| **Social Intelligence** | `core/social_engine.py` | Tone modulation, roast/banter generation, dynamic response length regulation, conversation pacing. |

---

## 4. Partially Implemented Functionality

These modules exist in the codebase but have structural or integration gaps:

1. **Windows Startup Management (`core/startup.py`)**
   - *Current State:* Contains registry functions (`enable_startup`, `disable_startup`, `is_startup_enabled`) writing to `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
   - *Gaps:* Disconnected from `IntentEngine` and `CommandExecutor`—speaking "enable startup" or "start with Windows" does not invoke these functions. UI settings menu does not expose a startup toggle.
2. **Runtime State Machine (`core/jarvis_runtime.py`, `ui/state_machine.py`)**
   - *Current State:* Manages 9 states (`STANDBY`, `LISTENING`, `TRANSCRIBING`, `UNDERSTANDING`, `EXECUTING`, `THINKING`, `SYNTHESIZING`, `SPEAKING`, `ERROR`).
   - *Gaps:* Missing required states: `WAITING_FOR_CONFIRMATION`, `PLANNING`, `PAUSED`, `INTERRUPTED`, `CANCELLING`. Barge-in interruption currently sets a boolean flag (`_tts_speaking_lock = False`) rather than transitioning to an `INTERRUPTED` state with worker cancellation tokens.
3. **Barge-in Interruption & Echo Management (`core/listener.py`, `core/tts/tts_manager.py`)**
   - *Current State:* Listener checks `tts.is_speaking()` and attempts energy-based voice activity detection.
   - *Gaps:* Lacks acoustic echo suppression or reference audio subtraction; when JARVIS speaks loud TTS through speakers, it risks transcribing its own speech as user input. Interruption does not yet cleanly associate user corrections (e.g., "Wait, use PyCharm instead") with the pending task step.
4. **Session Memory (`memory/session_memory.py`)**
   - *Current State:* In-memory sliding window of conversation turns (`UserTurn`, `JarvisTurn`).
   - *Gaps:* Does not persist unresolved goals, pending clarification questions, or interrupted workflows across brief pauses.

---

## 5. Missing or Broken Functionality

1. **Single-Instance Enforcement (`main.py`)**
   - *Issue:* No Windows named mutex (`CreateMutexW`) or single-instance socket check. If launched twice, two processes bind to the microphone stream and TTS engine, producing audio feedback and lockouts.
2. **Dedicated Working Memory Engine**
   - *Issue:* No formal Working Memory structure tracking:
     - Active User Goal
     - Pending Confirmation / Clarification Question
     - Active Plan & Step Status
     - Interruption Context & Correction Slot
3. **Workspace Management Engine (`core/workspaces/`)**
   - *Issue:* Completely absent. No centralized configuration or runner for Study, Software Development, Gaming, Excel, Research, or Custom workspaces.
4. **Engineering Mentor Architecture (`core/mentor/`)**
   - *Issue:* No subsystem to explain plans, detail code architectures, diagnose bugs, or teach programming concepts in response to user inquiry.
5. **Hardware-Aware Local LLM Profiling (`core/ai/`)**
   - *Issue:* `ProviderManager` can route to cloud APIs or mock providers, but does not benchmark local RAM, VRAM, or Ollama availability before delegating reasoning.

---

## 6. Existing Modules Worth Reusing

To avoid rebuilding working code from scratch, the following components must be preserved and extended:

- **`core/tool_registry.py`**: Clean, decoratored tool registration with type validation and safety metadata.
- **`modules/system/executor.py`**: Reliable Windows automation (app launching via `ShellExecute`, volume, media keys, browser dispatch).
- **`core/multi_step_planner.py`**: Structured task planning, step execution, and DAG dependencies.
- **`core/wakeword.py` (`OpenWakeWordDetector`)**: Highly reliable local wake-word engine.
- **`core/tts/tts_manager.py`**: Fully functional multi-provider TTS pipeline.
- **`core/transcript_validator.py`**: Battle-tested hallucination filter.
- **`memory/conversation_persistence.py`**: Robust SQLite interaction and secret redaction.
- **`core/startup.py`**: Working Windows registry integration for startup entries.

---

## 7. Critical Dependencies and Risks

1. **Audio Device Switching & Bluetooth Headsets:**
   - *Risk:* Windows Bluetooth headsets often switch between Stereo (playback only) and Hands-Free AG Audio (mic + low-bitrate playback). If sample rates mismatch (e.g., 44.1kHz vs 16kHz), PyAudio throws stream errors.
   - *Mitigation:* Audio device resolver with automatic fallback to standard WASAPI default communication device.
2. **Multiple Process Collisions:**
   - *Risk:* Users double-clicking JARVIS or auto-start firing while already running causes dual audio listeners.
   - *Mitigation:* Implement a Win32 Named Mutex (`Global\JARVIS_DESKTOP_SINGLETON_MUTEX`) at `main.py` entry point.
3. **Destructive Memory Resets:**
   - *Risk:* Adding new memory columns or tables could wipe existing session logs or user profiles.
   - *Mitigation:* Use strict `CREATE TABLE IF NOT EXISTS` and `ALTER TABLE ADD COLUMN` migration scripts with try/except wrappers. Never drop tables.
4. **Safety Gate Bypass:**
   - *Risk:* Agentic planner executing high-risk commands (e.g., disk formatting, process termination, file deletion) without user confirmation.
   - *Mitigation:* Non-negotiable `SafetyGate` inspection on every step before tool invocation.

---

## 8. Proposed Implementation Sequence

Following the master project phases:

### Phase 1: Reliable Startup & Wake-Word Lifecycle
- Implement Win32 Named Mutex in `main.py` for single-instance protection.
- Wire `core/startup.py` to `CommandExecutor` ("enable startup", "disable startup") and UI settings.
- Implement silent startup to Windows system tray (`--minimized` flag).
- Enhance `OpenWakeWordDetector` with runtime diagnostics, microphone permission verification, and explicit fallback triggers (hotkey / UI push-to-talk).

### Phase 2: Real-Time Conversation and Interruption
- Extend state machine to 12 formal states: `STANDBY`, `LISTENING`, `TRANSCRIBING`, `THINKING`, `SPEAKING`, `WAITING_FOR_CONFIRMATION`, `PLANNING`, `EXECUTING`, `PAUSED`, `INTERRUPTED`, `CANCELLING`, `ERROR`.
- Implement thread-safe `CancellationToken` pattern across audio synthesis and planner execution.
- Add acoustic echo suppression and user speech detection during TTS playback.
- Implement contextual correction routing (e.g., "Wait, use PyCharm instead").

### Phase 3: Conversational Memory
- Implement `WorkingMemory` dataclass (active goal, pending question, active plan, interruption stack).
- Connect `WorkingMemory` with `SessionMemory` and persistent SQLite store.
- Support non-destructive schema migrations and secret redaction across restarts.
- Support recall queries ("Continue yesterday's study session") with honest fallback if not found.

### Phase 4: Intelligence and Planning Engine
- Unify `IntentEngine`, `MultiStepPlanner`, and `SafetyGate` with the expanded 12-state lifecycle.
- Add user confirmation for risky actions via `WAITING_FOR_CONFIRMATION`.
- Enforce deterministic tools first, reserving LLM for intent clarification and complex reasoning.
- Bounded retries and dependency-aware step cancellation.

### Phase 5: Workspaces and Personal Automation
- Build `core/workspaces/workspace_manager.py` with templates: Study, Software Development, Gaming, Excel & Productivity, Research, Custom.
- Support natural language configuration ("Create my DSA workspace", "Add Spotify to gaming").
- Implement application discovery and safe restoration of prior settings.

### Phase 6: Engineering Mentor and Personalization
- Build `core/mentor/mentor_engine.py` to provide architectural explanations, trade-off analysis, bug diagnoses, and test recommendations on request.
- Keep normal conversational responses concise while supporting deep dive explanations when asked.

### Phase 7: Local AI, Performance, and Extensibility
- Hardware profiling (RAM, VRAM, CPU) before invoking local LLM (Ollama).
- Privacy boundary enforcement: do not send local code/secrets to external APIs unless explicitly authorized.

### Phase 8: UI, Testing, and Documentation
- Enhance PyQt6 dashboard: display state machine status, mic state, active workspace, pending confirmation, and step-by-step plan execution.
- Run complete test suite and document full architecture and workflows.

---

## 9. Baseline Audit Conclusion

Phase 0 is complete. The system architecture is sound, with 549 passing tests validating the existing components. The implementation will proceed sequentially, beginning with **Phase 1: Reliable Startup and Wake-Word Lifecycle**.
