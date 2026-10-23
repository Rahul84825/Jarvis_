# JARVIS Phase 6 — Chrome Tab Control, Gaming Workspace Execution & Acer Hardware Integration Implementation Report

**Date:** 2026-10-21  
**Phase:** 6  
**Status:** COMPLETE & VERIFIED  

---

## 1. Executive Summary

JARVIS Phase 6 addresses three critical operational capabilities on the Windows desktop host (Acer ALG AELEN15G52 gaming laptop with NVIDIA GeForce RTX 3050):
1. **Targeted Chrome Tab Control:** Reliable closure of specific Chrome browser tabs (active tab, positional/ordinal tabs such as "second Chrome tab", and tabs matched by distinctive title or URL like "YouTube", "GitHub", or "WellMeds dashboard") via Chrome DevTools Protocol (CDP), with strict distinction between closing a tab, closing a window, and terminating the browser process.
2. **Gaming Mode Confirmation & Execution Lifecycle:** Seamless conversational handoff and resumption for Gaming Mode after answering optional prompts (e.g., Discord confirmation). Execution state is preserved across conversational turns with idempotent step tracking (`completed_step_ids`), ensuring previously completed steps are not repeated and remaining steps execute faithfully.
3. **Valorant Launching & Acer OEM Hardware Integration:** Discovery and execution of Valorant via the official Riot Client launcher (`RiotClientServices.exe --launch-product=valorant --launch-patchline=live`), with process verification distinguishing launcher startup from the game engine; Windows power scheme management via `powercfg` with read-back verification; and an audited, truthful integration for the Acer ALG laptop that respects hardware safety boundaries (identifying Modern Standby constraints and proprietary ACPI bridge limits without resorting to hazardous driver hacks).

All implementations strictly adhere to non-negotiable safety constraints:
- Existing native Python/PyQt6 architecture and 3-layer brain are preserved.
- No administrative privileges are required or assumed by default.
- No screen vision, screenshot capture, OCR, or image analysis was introduced.
- No unsupported hardware commands, undocumented ACPI writes, or risky battery-controller modifications were used.
- Every reported success is verified through read-backs or live system probes.

---

## 2. Reproduced Root Causes & Technical Diagnosis

### 2.1 Specific Chrome Tab Closing Deficiencies
1. **Overly Broad Process Termination:**  
   In earlier iterations, generic "close chrome" commands occasionally routed to `close_app` (`taskkill /F /IM chrome.exe`), killing all Chrome windows and tabs rather than closing a single tab.
2. **Missing Tab Ordinal & Fuzzy Parsing:**  
   `core/intent_engine.py` lacked extraction for ordinal requests ("second Chrome tab", "3rd tab") and conversational title queries ("close the YouTube tab", "close the tab showing my WellMeds dashboard").
3. **Absence of Post-Close Verification:**  
   `core/os/browser_manager.py` dispatched CDP `Target.closeTarget` without checking `/json/list` afterwards. If a tab was unresponsive or held open by a `beforeunload` dialog, JARVIS erroneously reported success.
4. **Lack of Disambiguation for Duplicate Matches:**  
   If multiple tabs matched a query (e.g., two tabs titled "GitHub"), the manager arbitrarily picked the first one without prompting the user.

### 2.2 Gaming Mode Confirmation & Resumption Disconnect
1. **Unconfigured Gaming Actions in `config/workspaces.json`:**  
   The `gaming` workspace definition contained only an unrecognized `system_telemetry` tool. Neither `power.scheme` nor `open_app (valorant)` were configured as executable steps.
2. **Lost Execution State in `core/os/workspace_manager.py`:**  
   When the workspace paused for optional Discord confirmation, it returned `pending_confirmation: True` with `optional_item_id: "discord"`. However, the manager did not record which steps had already run or persist the execution context. When the user replied "Yes" or "No", the response handler had no resume callback or step history, resulting in a dropped execution.
3. **Missing Tool Handlers in `modules/system/executor.py`:**  
   The command executor lacked dispatch cases for `power.scheme`, `battery.status`, and `acer_oem_control`.
4. **UI Permission Dialog Gap in `core/jarvis_runtime.py`:**  
   While voice/text conversational confirmation was handled in `_process_command_worker`, the PyQt6 UI `resolve_permission(confirmed: bool)` method did not handle `workspace_optional_confirmation`, meaning GUI button clicks failed to resume workspaces.

### 2.3 Valorant Launching & Acer Hardware Boundaries
1. **Shortcut (.lnk) Execution Failure (`WinError 193`):**  
   The desktop shortcut for Valorant pointed to a `.lnk` file. Standard `subprocess.Popen([path])` failed on Windows with `[WinError 193] %1 is not a valid Win32 application`.
2. **Riot Client Launch Requirements:**  
   Launching `VALORANT.exe` directly bypasses Vanguard anti-cheat initialization and causes a crash or VAN 9003 error. Official launching requires executing `RiotClientServices.exe` with `--launch-product=valorant --launch-patchline=live` from the Riot Client directory.
3. **Acer Modern Standby (`S0 Low Power Idle`) Power Schemes:**  
   The Acer ALG AELEN15G52 operates under Windows Modern Standby. Running `powercfg /list` revealed that only the `Balanced` scheme (GUID `381b4222-f694-41f0-9685-ff5bb260df2e`) is active and exposed. Requesting "High Performance" failed silently or defaulted without read-back verification.
4. **Proprietary Acer OEM Control Architecture:**  
   Deep system inspection revealed the Acer ALG laptop uses an Insyde DCHU package (`CCDCHUService.exe`, `AcpiBridge.sys`). Performance profiles (Performance, Entertainment, Quiet) and the 80% battery charging threshold are controlled via private IOCTL calls through `AcpiBridge.sys`. No public WMI methods, command-line arguments, or documented APIs are provided by Acer. Attempting raw ACPI register writes carries severe risk of bricking fan controllers or causing thermal runaway.

---

## 3. Architecture & Implementation Details

```
                              USER COMMAND
                                   │
                                   ▼
                       ┌───────────────────────┐
                       │   Intent Engine       │
                       └───────────┬───────────┘
                                   │
         ┌─────────────────────────┼─────────────────────────┐
         ▼                         ▼                         ▼
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│ Chrome Tab Close │     │  Gaming Mode WS  │     │ Power & Hardware │
└────────┬─────────┘     └────────┬─────────┘     └────────┬─────────┘
         │                         │                         │
         ▼                         ▼                         ▼
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  BrowserManager  │     │ WorkspaceManager │     │   PowerManager   │
│  - Ordinals      │     │ - Idempotent Step│     │ - powercfg read- │
│  - Matcher       │     │   tracking       │     │   back verify    │
│  - Disambiguate  │     │ - Yes/No/Always/ │     │ - AcerOEMAdapter │
│  - CDP close     │     │   Never/Cancel   │     │   (honest safety │
│  - Verify absent │     │ - Truthful report│     │   boundary)      │
└────────┬─────────┘     └────────┬─────────┘     └────────┬─────────┘
         │                         │                         │
         ▼                         ▼                         ▼
Chrome DevTools API        Riot Client / Valorant    Windows OS / Control
(CDP Port 9222)            Process Verification      Center Launcher
```

### 3.1 Part 1 — Specific Chrome Tab Closing
- **Intent Routing (`core/intent_engine.py`):**
  - Added dedicated pattern matching for active tabs: `"close (the )?current (chrome )?tab"`, `"close this tab"`.
  - Added ordinal matching: `"close the (first|second|third|fourth|fifth|2nd|3rd) chrome tab"`.
  - Added descriptive/title matching: `"close the (YouTube|GitHub|WellMeds dashboard) tab"`.
  - Strictly differentiated tab closure (`action: close_tab`) from window closure (`intent: window_control, action: close`) and app termination (`intent: close_app`).
- **Tab Resolution & Disambiguation (`core/os/browser_manager.py`):**
  - Implemented `ORDINAL_MAP` mapping English and numeric ordinals (`first`, `1st`, `second`, `2nd`, etc.) to zero-based tab indices.
  - Upgraded `find_matching_tabs` to normalize titles and strip common boilerplate prefixes ("close the", "tab showing", "tab titled").
  - In `close_tab(target)`:
    - If `target="current"`, targets the first visible page tab.
    - If target resolves to an ordinal, targets that specific index.
    - If matching produces multiple candidates, returns `disambiguation_required: True` along with the candidate titles, prompting the user for clarification.
    - If no tab matches, returns `success: False` with a descriptive message.
    - Calls `CDPClient.close_tab(target_id)` and verifies closure with `CDPClient.verify_tab_closed(target_id)`.
- **CDP Verification (`core/os/cdp_client.py`):**
  - Added `verify_tab_closed(tab_id)` which polls `/json/list` to guarantee the tab is no longer enumerated, ensuring unrelated tabs remain open.

### 3.2 Part 2 — Gaming Mode Confirmation & Resumption Lifecycle
- **Workspace Configuration (`config/workspaces.json`):**
  Configured the `gaming` workspace with 3 sequential steps:
  1. `power.scheme` (Set Gaming Power Scheme, required: false)
  2. `open_app` (Launch Valorant, required: true)
  3. Optional Discord prompt (`"I'll prepare your gaming setup. Would you like Discord open as well?"`)
- **Idempotent Resumption (`core/os/workspace_manager.py`):**
  - Maintained `_pending_executions` dictionary indexed by `workspace_id`.
  - Stored `completed_step_ids` as steps execute.
  - On optional confirmation:
    - Returns `pending_confirmation: True`, registering the execution state.
    - If user replies **"Yes"**: Launches Discord, marks step completed, executes any remaining steps, and returns a verified summary.
    - If user replies **"No"**: Skips Discord without error, executes remaining steps, and returns a verified summary.
    - If user replies **"Always"**: Saves preference `workspace_gaming_discord = true` in `persistent_memory`, launches Discord, and completes workspace.
    - If user replies **"Never"**: Saves preference `workspace_gaming_discord = false` in `persistent_memory`, skips Discord, and completes workspace.
    - If user replies **"Cancel"**: Safely clears pending execution state and cancels.
    - Ambiguous replies prompt for clarification without consuming the pending state.
  - **Truthful Status Reporting:** Completed steps and skipped optional steps are itemized in the final message (e.g., *"Gaming workspace is ready, Sir. All 2 actions completed successfully."* or reporting skipped items explicitly).
- **Runtime Permission Integration (`core/jarvis_runtime.py`):**
  - Added `workspace_optional_confirmation` handler to `resolve_permission(confirmed: bool)`, ensuring GUI dialogs and voice interactions both resume the workspace identically.

### 3.3 Part 3 — Valorant & Application Launching
- **Application Discovery (`core/apps/application_discovery.py`):**
  - Upgraded `_parse_windows_lnk` using Windows `WScript.Shell` via `win32com.client` to extract true `TargetPath` and `Arguments`, resolving `.lnk` execution failures.
  - Added `_scan_windows_special_launchers` inspecting `C:\ProgramData\Riot Games\RiotClientInstalls.json` to auto-discover installed Riot Client and Valorant paths.
- **Official Valorant Execution (`core/platform/windows_platform.py`):**
  - Registered `valorant` and `control_center` in known application locations.
  - Implemented `launch_valorant()`:
    - Executes `RiotClientServices.exe --launch-product=valorant --launch-patchline=live` with working directory set to the Riot Client folder.
    - Polls running processes up to 3 seconds.
    - Distinguishes between `launcher_started` (`RiotClientServices.exe` running) and `running` (`VALORANT.exe` or `VALORANT-Win64-Shipping.exe` active).
  - Fixed `open_application` to validate binary paths and return `False` when applications do not exist, eliminating false-positive success reports.

### 3.4 Part 4 — Windows Power Plans & Acer OEM Controls
- **Windows Power Schemes (`core/os/power_manager.py`):**
  - Implemented `set_power_scheme(name_or_guid)` using `powercfg /list` and `powercfg /setactive <GUID>`.
  - Performs immediate read-back verification via `powercfg /getactivescheme`.
  - If a requested scheme (such as High Performance) is unavailable due to Modern Standby, does not simulate success; returns `success: False`, reports the current active scheme (`Balanced`), and itemizes available schemes.
- **Acer OEM Adapter (`core/os/power_manager.py:AcerOEMAdapter`):**
  - Audited WMI namespaces (`root/wmi`, `root/cimv2`), Insyde DCHU services (`CCDCHUService`), and registry settings.
  - Accurately declares `is_supported() = False` for direct programmatic profile and battery threshold changes.
  - Provides `launch_control_center()` to launch the official OEM GUI (`C:\Program Files\OEM\ControlCenter\ControlCenter.exe`).
  - Implemented `set_battery_threshold(percentage)`: Explains the hardware boundary truthfully, reports that the threshold remains unchanged, and instructs the user how to toggle 80% charging in Control Center.
- **Comprehensive Status Reporting (`core/os/power_manager.py`):**
  - `get_comprehensive_status()` provides discrete status fields:
    - `active_windows_power_plan`
    - `active_acer_oem_profile` (reported as `"manual_only"` with boundary explanation)
    - `battery_percentage` and `battery_charging_status`
    - `configured_battery_threshold` (reported as `"unknown_unverified"`)
    - `valorant_launch_status`
    - `discord_launch_status`

---

## 4. Files Changed

| File | Changes Made |
|---|---|
| `core/intent_engine.py` | Added regex patterns for active tab, ordinals (first through tenth, 1st through 10th), and distinctive titles/URLs; differentiated tab vs. window vs. application close intents. |
| `core/os/cdp_client.py` | Added `verify_tab_closed(tab_id)` polling `/json/list` to guarantee tab removal. |
| `core/os/browser_manager.py` | Added `ORDINAL_MAP` and ordinal resolver; enhanced `find_matching_tabs` title stripping; updated `close_tab` to handle ordinals, disambiguation, and verification. |
| `config/browser.json` | Enabled Chrome CDP remote debugging support (`cdp_enabled: true`). |
| `config/applications.json` | Registered `valorant` and `control_center` metadata and alias mappings. |
| `config/workspaces.json` | Updated `gaming` workspace with `power.scheme`, `open_app (valorant)`, and optional Discord confirmation. |
| `core/apps/application_discovery.py` | Added `WScript.Shell` `.lnk` resolution; added `_scan_windows_special_launchers` for Riot Client discovery. |
| `core/platform/windows_platform.py` | Added `launch_valorant` with official Riot Client parameters and process polling; validated binary existence in `open_application`. |
| `core/os/power_manager.py` | Added `set_power_scheme` with read-back verification; created `AcerOEMAdapter` with honest capability boundaries and `launch_control_center`; added `get_comprehensive_status`. |
| `modules/system/executor.py` | Added execution handlers for `power.scheme`, `battery.status`, `acer_oem_control`, and `system_telemetry`. |
| `modules/browser/web_control.py` | Added `open_url` wrapper directing to `open_website`. |
| `core/os/workspace_manager.py` | Added `_pending_executions` tracking `completed_step_ids` for idempotent resumption upon Yes/No/Always/Never; truthful summary generation. |
| `core/jarvis_runtime.py` | Added `workspace_optional_confirmation` handler to `resolve_permission` for UI dialog parity with voice. |
| `tests/test_phase6_chrome_gaming_acer.py` | Exhaustive 27-test regression suite covering all Phase 6 requirements. |
| `tests/test_workspaces.py` | Updated mock patch targets to match `workspace_manager.execute_workspace`. |

---

## 5. Verification & Test Results

### 5.1 Phase 6 Master Test Suite (`tests/test_phase6_chrome_gaming_acer.py`)
All 27 focused tests passed in **4.65 seconds**:

```
test_01_close_current_tab_intent (tests.test_phase6_chrome_gaming_acer.TestPhase6ChromeTabControl) ... ok
test_02_close_ordinal_tab_intent (tests.test_phase6_chrome_gaming_acer.TestPhase6ChromeTabControl) ... ok
test_03_close_titled_tab_intent (tests.test_phase6_chrome_gaming_acer.TestPhase6ChromeTabControl) ... ok
test_04_close_window_not_confused_with_close_tab (tests.test_phase6_chrome_gaming_acer.TestPhase6ChromeTabControl) ... ok
test_05_browser_manager_close_active_tab_cdp (tests.test_phase6_chrome_gaming_acer.TestPhase6ChromeTabControl) ... ok
test_06_browser_manager_close_by_title_cdp (tests.test_phase6_chrome_gaming_acer.TestPhase6ChromeTabControl) ... ok
test_07_browser_manager_close_by_ordinal_cdp (tests.test_phase6_chrome_gaming_acer.TestPhase6ChromeTabControl) ... ok
test_08_browser_manager_duplicate_tabs_requires_disambiguation (tests.test_phase6_chrome_gaming_acer.TestPhase6ChromeTabControl) ... ok
test_09_browser_manager_missing_tab_handled_gracefully (tests.test_phase6_chrome_gaming_acer.TestPhase6ChromeTabControl) ... ok
test_10_unrelated_tabs_and_browser_preserved (tests.test_phase6_chrome_gaming_acer.TestPhase6ChromeTabControl) ... ok
test_11_gaming_workspace_prompt_then_resume_yes (tests.test_phase6_chrome_gaming_acer.TestPhase6GamingWorkspaceExecution) ... ok
test_12_gaming_workspace_prompt_then_resume_no (tests.test_phase6_chrome_gaming_acer.TestPhase6GamingWorkspaceExecution) ... ok
test_13_gaming_workspace_always_preference_updates_memory (tests.test_phase6_chrome_gaming_acer.TestPhase6GamingWorkspaceExecution) ... ok
test_14_gaming_workspace_never_preference_updates_memory (tests.test_phase6_chrome_gaming_acer.TestPhase6GamingWorkspaceExecution) ... ok
test_15_gaming_workspace_cancel_aborts_safely (tests.test_phase6_chrome_gaming_acer.TestPhase6GamingWorkspaceExecution) ... ok
test_16_gaming_workspace_idempotency_does_not_repeat_steps (tests.test_phase6_chrome_gaming_acer.TestPhase6GamingWorkspaceExecution) ... ok
test_17_gaming_workspace_partial_success_reported_accurately (tests.test_phase6_chrome_gaming_acer.TestPhase6GamingWorkspaceExecution) ... ok
test_18_runtime_permission_dialog_resolves_workspace_confirmation (tests.test_phase6_chrome_gaming_acer.TestPhase6GamingWorkspaceExecution) ... ok
test_19_valorant_discovery_and_launch_args (tests.test_phase6_chrome_gaming_acer.TestPhase6ValorantAndHardwareControls) ... ok
test_20_valorant_missing_executable_reports_honest_failure (tests.test_phase6_chrome_gaming_acer.TestPhase6ValorantAndHardwareControls) ... ok
test_21_valorant_process_verification_distinguishes_launcher_vs_game (tests.test_phase6_chrome_gaming_acer.TestPhase6ValorantAndHardwareControls) ... ok
test_22_power_scheme_switch_and_read_back_verification (tests.test_phase6_chrome_gaming_acer.TestPhase6ValorantAndHardwareControls) ... ok
test_23_power_scheme_unavailable_reports_schemes_and_fails_truthfully (tests.test_phase6_chrome_gaming_acer.TestPhase6ValorantAndHardwareControls) ... ok
test_24_acer_oem_adapter_reports_unsupported_interface_truthfully (tests.test_phase6_chrome_gaming_acer.TestPhase6ValorantAndHardwareControls) ... ok
test_25_battery_threshold_change_reports_hardware_boundary (tests.test_phase6_chrome_gaming_acer.TestPhase6ValorantAndHardwareControls) ... ok
test_26_comprehensive_status_exposes_discrete_unambiguous_fields (tests.test_phase6_chrome_gaming_acer.TestPhase6ValorantAndHardwareControls) ... ok
test_27_open_application_does_not_claim_success_for_missing_binaries (tests.test_phase6_chrome_gaming_acer.TestPhase6ValorantAndHardwareControls) ... ok

----------------------------------------------------------------------
Ran 27 tests in 4.648s
OK
```

### 5.2 Phase 5 Regression Verification (`tests/test_phase5_routing_and_confirmations.py`)
All 23 Phase 5 tests passed in **23.6 seconds**:
```
Ran 23 tests in 23.633s
OK
```

### 5.3 Combined Core Workspace & Browser Reliability Suites
```
python -m unittest tests.test_phase6_chrome_gaming_acer tests.test_browser_tab_and_search_reliability tests.test_workspaces
Ran 48 tests in 9.514s
OK
```

---

## 6. Physical Integration vs. Mocked Tests

| Test Component | Physical Host Check | Mocked Scenario | Rationale |
|---|---|---|---|
| **Chrome CDP Tab Enumeration & Closure** | Tested against running Chrome with `--remote-debugging-port=9222` | Mocked CDP HTTP server in unit tests (`test_05`–`test_10`) | Unit tests require fast, deterministic tab fixtures without mutating the user's active browser session during test runs. |
| **Valorant Application Discovery** | Verified live reading of `RiotClientInstalls.json` and desktop `.lnk` parsing via `WScript.Shell` on `C:\ProgramData\Riot Games\` | Mocked `subprocess.Popen` and process polling in test suite (`test_19`, `test_21`) | Avoids launching full Vanguard anti-cheat client and full-screen 3D game engine repeatedly during automated test execution. |
| **Windows Power Plans (`powercfg`)** | Ran live `powercfg /list` and `powercfg /getactivescheme` to verify Modern Standby GUIDs on the host | Mocked CLI responses in `test_22`–`test_23` | Validates error recovery when unavailable schemes are requested without modifying laptop power policies during testing. |
| **Acer OEM Profile & Battery Limit** | Audited live WMI namespaces (`root/wmi`, `root/cimv2`), Insyde DCHU services (`CCDCHUService`), and registry | Mocked hardware adapter calls in `test_24`–`test_25` | Confirmed no public command-line interface exists. Unit tests verify JARVIS refuses unsafe ACPI modifications and reports boundaries truthfully. |
| **Gaming Mode Yes/No Resumption** | Verified state persistence in `persistent_memory` SQLite database | Mocked step executors in `test_11`–`test_17` | Asserts idempotent step resumption without spawning real desktop applications. |

---

## 7. Operational Guidelines & Remaining Hardware Boundaries

1. **Chrome Tab Closing Prerequisite:**  
   To control Chrome tabs via CDP, Chrome must be launched with remote debugging enabled (`--remote-debugging-port=9222`). If Chrome is launched externally without this flag, CDP port 9222 will be unreachable, and JARVIS will explain that remote debugging is not attached.
2. **Acer ALG Performance Profiles & Battery Threshold:**  
   Because Acer's Insyde DCHU architecture relies on private kernel IOCTLs via `AcpiBridge.sys`, JARVIS cannot directly write fan or battery registers via public Windows APIs without administrator privilege and driver modification. When requested, JARVIS:
   - Accurately explains the limitation.
   - Offers to launch Acer Control Center (`C:\Program Files\OEM\ControlCenter\ControlCenter.exe`) where the user can click Performance mode or toggle the 80% battery charging threshold safely.
3. **Valorant Vanguard Anti-Cheat:**  
   Valorant requires Riot Vanguard to run. JARVIS initiates the game through the official Riot Client launcher (`RiotClientServices.exe --launch-product=valorant --launch-patchline=live`) ensuring Vanguard initializes cleanly. Process status tracking distinguishes when the launcher is starting from when the game client itself is running.
4. **Modern Standby Power Schemes:**  
   The laptop defaults to Windows Balanced mode. When gaming mode runs, JARVIS attempts to activate the gaming power scheme and verifies the active plan through `powercfg`. If High Performance is unavailable under Modern Standby, it reports that Balanced remains active.
