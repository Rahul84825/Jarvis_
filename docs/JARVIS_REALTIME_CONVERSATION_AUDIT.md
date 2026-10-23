# Pre-Implementation Audit: Real-Time Conversational Intelligence, NVIDIA Nemotron & Personal Workspace Agent

**Date:** 2026-10-20  
**Project:** JARVIS Desktop Assistant  
**Platform Scope:** Windows 11 (AMD64), Acer ALG Gaming Laptop (AELEN15G52, NVIDIA RTX 3050)  
**Baseline Test Status:** 587 tests passing (0 failures, 0 errors, 100% OK)  
**Objective:** Audit existing codebase, identify defects and architectural gaps, and define minimal focused changes for Tracks 1–8.

---

## 1. Actual Files Inspected

| Component | Files Inspected | Current State & Responsibilities |
|---|---|---|
| **Audio Capture & VAD** | `core/listener.py`, `core/audio_device_resolver.py` | Single-stream `sd.InputStream` at 16kHz float32; dual-threshold VAD; pre-roll ring buffer (0.6s); external audio consumer registry for wake-word engine; barge-in RMS threshold checking during `speaking_active`. |
| **TTS & Speech Playback** | `core/tts/tts_manager.py`, `core/tts/base_tts.py` | Queue-based multi-provider TTS (Edge-TTS, Windows SAPI, pyttsx3, gTTS, ElevenLabs); chunk-by-chunk amplitude calculation; synchronous `sd.play()` / `sd.stop()`. |
| **Runtime Coordinator** | `core/jarvis_runtime.py` | State machine (`STANDBY`, `LISTENING`, `TRANSCRIBING`, `UNDERSTANDING`, `THINKING`, `EXECUTING`, `SPEAKING`); observer callbacks; speech-start/end routing. |
| **Conversation & Memory** | `core/conversation_manager.py`, `memory/conversation_persistence.py` | Rolling in-memory turn history (`history`), 60s session timeout, SQLite persistence (`memory/conversations.db`); lacks granular task continuation and paused explanation tracking. |
| **AI Routing & Providers** | `core/ai/intelligence_router.py`, `core/ai/provider_manager.py`, `core/ai/providers/nvidia_provider.py` | 3-layer architecture (L1 Local, L2 Social/Context, L3 Reasoning); `NvidiaNemotronProvider` wired for `nvidia/nemotron-3.5-super-vl-120b-a12b` via OpenAI-compatible endpoint; live smoke test verified. |
| **Wake-Word & Manual Talk** | `core/wakeword.py` | `OpenWakeWordDetector` with `hey_jarvis_v0.1.onnx` model; fed via external PCM chunks from `SpeechListener`; manual talk button bypasses detector. |
| **Workspaces & Tools** | `core/tool_registry.py`, `modules/system/executor.py`, `core/multi_step_planner.py` | Executable tool definitions with risk levels and safety checks; compound clause execution; lacking dedicated `config/workspaces.json` and interactive optional action prompts. |
| **Hardware & Power** | Windows ACPI / WMI / `powercfg` | ACPI bridge service `CCDCHUService` active for Control Center hotkeys; `powercfg /list` reports active `Balanced` power scheme; `Win32_Battery` reports charge percentage and status. |

---

## 2. Identified Defects, Gaps, and Root Causes

### Track 1: Voice Barge-In & Interruption
- **Defect 1.1 (Suppression Collision):** In `core/jarvis_runtime.py` line 300:
  ```python
  def _on_speech_start(self):
      if self._tts_speaking_lock or self.tts_manager.is_speaking():
          logger.info("Suppressing VAD speech onset during TTS playback.")
          return
  ```
  This unconditionally suppresses speech onset callbacks whenever TTS is active. While `core/listener.py` attempted to fire `on_barge_in_cb`, any subsequent onset callback was discarded, causing state synchronization lag.
- **Defect 1.2 (Missing Generation Invalidation):** `TTSManager` had no generation ID / cancellation token concept. If multiple sentences were queued for an answer, interrupting the active playback chunk did not guarantee that a background synthesis worker or scheduled item wouldn't emit a residual sound or overwrite newer state.
- **Defect 1.3 (Lack of Interruption State Tracking):** When speech playback was stopped, no metadata was captured regarding *which sentence* or *what point* in the explanation was reached.

### Track 2: NVIDIA Nemotron Streaming & Token Cancellation
- **Gap 2.1 (Cancellation During Streaming):** The provider generates responses via HTTP requests. If the user interrupts while Nemotron is streaming or generating, the runtime must immediately invalidate the generation ID so incoming chunks are discarded and never spoken or rendered to the UI.
- **Gap 2.2 (Secure Redaction & Config):** `NVIDIA_API_KEY` is loaded from `.env` and redacted via `PrivacyGuard` (pattern 18: `nvapi-[a-zA-Z0-9_\-]{40,}`). Need to ensure fallback to local response engine when offline or unconfigured.

### Track 3: Wake-Word Phrasing & Manual Talk Reliability
- **Defect 3.1 (Phrase Mismatch: "Hey Jarvis" vs "Jarvis"):** The ONNX model loaded is `hey_jarvis_v0.1.onnx`. Its acoustic embedding is specifically trained on "Hey Jarvis". When a user speaks bare "Jarvis", the prediction score is lower (~0.20–0.35) compared to "Hey Jarvis" (~0.55–0.85). If threshold is 0.5, bare "Jarvis" may miss.
- **Defect 3.2 (Talk Button Buffer Safety):** `trigger_manual_recording(manual=True)` resets the buffer using `list(self._pre_roll_buffer)`. Clicking Talk twice must toggle recording off without losing the captured audio or corrupting pipeline state.

### Track 4 & 5: Personal Workspaces & Laptop Power Controls
- **Gap 4.1 (Dedicated Workspace System):** Multi-step tasks existed, but reusable task environments ("Gaming", "Development", "Study", "Research") were not structured as declarative workspaces with step dependencies and interactive optional prompts (e.g., asking "Do you want Discord open as well?").
- **Gap 4.2 (Device-Specific Power vs Standard Windows Power Schemes):**
  - Standard Windows: `powercfg /list` reveals one active scheme: `Balanced` (`381b4222-f694-41f0-9685-ff5bb260df2e`).
  - Acer ALG (AELEN15G52): Uses `CCDCHUService` (Control Center Hotkey Service). Fan curves (Quiet, Performance), GPU muxing, and 80% battery charging limits are proprietary ACPI commands without a public API. Attempting undocumented registry hacks would risk hardware instability. We must truthfully expose Windows power schemes and battery telemetry while explaining that OEM-specific fan/battery limits are set in the Control Center application.

### Track 6 & 7: Social Intelligence, YouTube Search & Single-Response Guarantee
- **Preservation:** Track A YouTube regex queries and Track B social engine must not be bypassed or collided with by conversational interruption.
- **Single-Response Guarantee:** Each user query must have a single authoritative response lifecycle; stale LLM chunks or delayed callbacks from interrupted responses must never overwrite newer turns.

---

## 3. Minimal Proposed Changes

1. **Phase 1: Voice Lifecycle & Immediate TTS Interruption**
   - In `core/tts/tts_manager.py`:
     - Add `generation_id` tracking to speech items and playback.
     - Enhance `interrupt(force=True, from_vad=False)`: synchronously call `sd.stop()`, clear queue, increment `generation_id`, and emit cancellation event.
   - In `core/listener.py`:
     - Keep pre-roll audio intact upon barge-in so the user's first words are not clipped.
   - In `core/jarvis_runtime.py`:
     - When `_on_speech_start` fires during speaking, immediately trigger `_on_barge_in` (<50ms cutoff) and transition to `LISTENING`.

2. **Phase 2: Conversational Interruption Types & Task Continuity**
   - In `core/conversation_manager.py`:
     - Maintain active task state: `active_task_id`, `current_explanation_sentences`, `interrupted_sentence_idx`, `is_interrupted`.
     - Implement interruption classification:
       - `correction`: "No, I meant binary search..." -> updates target, answers correction.
       - `clarification`: "I mean C++..." -> refines context.
       - `addition`: "Also explain its time complexity..." -> appends to active response.
       - `question`: "Wait, why are we calculating midpoint?" -> answers question, preserves resume point.
       - `resume`: "Continue" / "Go on" -> resumes remaining sentences from `interrupted_sentence_idx`.
       - `stop`: "Stop talking" -> halts audio, retains paused task.
       - `cancel`: "Cancel that" -> clears task state.

3. **Phase 3: Wake-Word & Manual Talk Verification**
   - In `core/wakeword.py`:
     - Add clear diagnostic logging clarifying that `hey_jarvis_v0.1.onnx` matches "Hey Jarvis", and support configurable threshold/phrases.
   - In `core/jarvis_runtime.py`:
     - Ensure manual Talk button toggles start/stop cleanly.

4. **Phase 4: NVIDIA Nemotron Streaming & Token Cancellation**
   - In `core/ai/providers/nvidia_provider.py`:
     - Support generation token cancellation so interrupted requests immediately abort streaming and discard trailing tokens.

5. **Phase 5: Social Engine & Dynamic Help Synchronization**
   - Ensure `core/social_engine.py` handles greetings, identity, and jokes locally with zero latency, without routing to cloud LLMs.

6. **Phase 6: Personal Workspaces & Windows Power Management**
   - Create `config/workspaces.json` defining development, study, gaming, research, and excel workspaces.
   - Implement `core/os/workspace_manager.py` for workspace execution with optional step confirmation (e.g. Discord in gaming mode).
   - Implement `core/os/power_manager.py` using `powercfg` and WMI `Win32_Battery`, truthfully reporting standard Windows power capabilities and OEM Control Center limitations.

7. **Phase 7: Comprehensive Regression & Integration Testing**
   - Add unit tests in `tests/test_realtime_conversation.py` and `tests/test_workspaces.py`.
   - Run full regression suite and document all results in `docs/JARVIS_REALTIME_CONVERSATION_IMPLEMENTATION_REPORT.md`.
