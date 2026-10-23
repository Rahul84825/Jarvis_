# JARVIS: Universal Application Discovery, Dynamic Registry & Desktop Control
## Technical Architecture Audit & Engineering Report

---

### Executive Summary

The JARVIS application subsystem has been upgraded to a fully dynamic, cross-platform (Windows 11 & Ubuntu Linux) discovery, registration, and desktop-control engine. Prior to this implementation, application launches and queries depended heavily on static JSON files (`config/applications.json`), hardcoded regex keywords, or manual code modifications. 

With this upgrade:
1. **Dynamic Multi-Source Discovery**: Applications are discovered from Start Menu shortcuts (`.lnk`), Windows Registry uninstall hives (`HKLM` & `HKCU`), UWP / MSIX package aliases (`%LocalAppData%\Microsoft\WindowsApps`), known portable tools directories (`C:\Tools`, `C:\PortableApps`), and Linux XDG desktop entries (`/usr/share/applications`, `~/.local/share/applications`, snap, flatpak).
2. **Metadata & PE File Extraction**: Win32 PE resource tables (`StringFileInfo\...\ProductVersion`, `CompanyName`) are extracted directly via `win32api.GetFileVersionInfoW` without invoking external child processes.
3. **Additive SQLite Schema Migration**: `logs/applications.db` was migrated additively (`searchable_aliases`, `launch_mechanism`, `install_directory`, `version`, `publisher`, `category`, `user_aliases`, `discovery_source`, `last_verification_timestamp`, `availability_status`) preserving all preexisting database records.
4. **Desktop Control Operations**: Dedicated native mechanisms were implemented for opening executable Properties dialogs (`ShellExecuteExW` with `SEE_MASK_INVOKEIDLIST`), exploring installation directories (`explorer.exe /select`), system installed app details (`ms-settings:appsfeatures` / `gnome-control-center`), and internal browser settings (`chrome://settings`, `edge://settings`, `brave://settings`).
5. **Deterministic Layer 1 Execution**: All application control and inquiry queries resolve deterministically through `IntentEngine` and `IntelligenceRouter` with zero Nemotron latency (<5ms) and no LLM hallucinations.
6. **Robust Outcome Verification**: Execution stages strictly distinguish between Discovery, Launch Initiation, Process Running, and Window Visible confirmation.

---

### 1. Architecture Audit & Component Reuse

Existing components audited and reused:
- **`core/apps/application_discovery.py` (`ApplicationDiscovery`)**: Reused as the central discovery singleton and persistent catalogue cache. Added multi-source scanning, PE metadata extraction, temporal date querying, and desktop control actions.
- **`core/os/application_resolver.py` (`ApplicationResolver`)**: Reused to dynamically bridge discovered applications into `TargetType.NATIVE_APP` without requiring static entries in `applications.json`.
- **`modules/system/app_control.py` (`AppControl`)**: Reused for launch orchestration, process verification, UWP alias launching, and exposing high-level desktop management functions.
- **`core/platform/windows_platform.py` & `linux_platform.py`**: Reused for platform-specific launch primitives, process tree traversal (`psutil`), and shell execution.
- **`core/intent_engine.py` (`IntentEngine`)**: Reused and extended with Section 18.8 deterministic regex rules for inquiries, properties, folders, versions, and listings.
- **`core/ai/intelligence_router.py` (`IntelligenceRouter`)**: Reused and configured with reflex bypass in `_is_informational_question` so application queries are routed as Layer 1 Fast Local (<5ms) without Nemotron API calls.
- **`core/tool_registry.py` & `modules/system/executor.py`**: Reused to register 7 standardized tools returning `CommandOutcome`.
- **`memory/persistent_memory.py`**: Reused for recording failed launches and user corrections into verified memory.

---

### 2. Implemented Application Discovery Service

#### Windows 11 Discovery Channels
- **Start Menu Shortcuts**: Scans both system (`C:\ProgramData\Microsoft\Windows\Start Menu\Programs`) and user (`%AppData%\Microsoft\Windows\Start Menu\Programs`) hierarchies, resolving target executables and arguments via `pythoncom` and `WScript.Shell`.
- **Registry Uninstall Hives**: Scans 32-bit and 64-bit hives (`HKLM\Software\Microsoft\Windows\CurrentVersion\Uninstall` and `HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall`). Extracts `DisplayName`, `DisplayVersion`, `Publisher`, `InstallLocation`, and resolves `DisplayIcon` / `InstallLocation` executables.
- **Packaged Applications (UWP / MSIX)**: Scans `%LocalAppData%\Microsoft\WindowsApps` for registered app execution aliases (e.g. `wt.exe`, `python3.exe`).
- **Targeted Directory Scanning**: Scans `%LocalAppData%\Programs`, `C:\Tools`, and `C:\PortableApps` for standalone portable executables without scanning the entire hard drive.
- **Background FileSystem Watcher**: Runs a daemon background thread monitoring user and common Start Menu folders via `win32file.ReadDirectoryChangesW` or lightweight 60-second polling to trigger incremental refreshes upon software installation.

#### Ubuntu Linux Discovery Channels
- **XDG Desktop Entry Scanning**: Scans `/usr/share/applications`, `/usr/local/share/applications`, `~/.local/share/applications`, `/var/lib/snapd/desktop/applications`, and `/var/lib/flatpak/exports/share/applications`.
- **Category & Metadata Parsing**: Reads `Name`, `Exec`, `Categories`, `Comment`, and `Version` from `.desktop` files, stripping exec parameters (`%U`, `%F`) and resolving binary paths using `shutil.which`.

---

### 3. Registry & Additive SQLite Migration

#### SQLite Schema (`logs/applications.db`)
```sql
CREATE TABLE IF NOT EXISTS discovered_applications (
    app_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    executable_path TEXT NOT NULL,
    arguments TEXT,
    source TEXT NOT NULL,
    platform TEXT NOT NULL,
    is_available INTEGER DEFAULT 1,
    last_discovered_at REAL NOT NULL,
    searchable_aliases TEXT,
    launch_mechanism TEXT,
    install_directory TEXT,
    version TEXT,
    publisher TEXT,
    category TEXT,
    user_aliases TEXT
);
```

#### Additive Migration Strategy
During `ApplicationDiscovery._init_db()`, `PRAGMA table_info(discovered_applications)` is queried. If columns such as `version`, `publisher`, `category`, `user_aliases`, or `install_directory` are absent from existing databases, `ALTER TABLE discovered_applications ADD COLUMN ...` statements are executed additively. Preexisting rows are completely preserved and no table drops or database wipes ever occur.

---

### 4. Natural-Language Launch & Control Commands

| Voice / Natural Language Query | Intent Routed | Layer / Latency | Action Executed |
| :--- | :--- | :--- | :--- |
| `"Open Chrome"` | `open_app` | Layer 1 (<5ms) | Launches `chrome.exe` and verifies window visibility |
| `"Launch Brave"` | `open_app` | Layer 1 (<5ms) | Launches `brave.exe` from discovered registry path |
| `"Open Spotify"` | `open_app` | Layer 1 (<5ms) | Launches Spotify UWP/executable |
| `"Open Visual Studio Code"` | `open_app` | Layer 1 (<5ms) | Resolves alias to `code.exe` |
| `"Open the application I installed yesterday"` | `open_app` | Layer 1 (<5ms) | Resolves most recently discovered application by date |
| `"List my installed applications"` | `application.list_installed` | Layer 1 (<5ms) | Deduplicates and summarizes installed catalogue |
| `"Find my available browsers"` | `application.list_installed` | Layer 1 (<5ms) | Filters browsers (`Chrome`, `Brave`, `Edge`) |
| `"Is Discord installed?"` | `application.status` | Layer 1 (<5ms) | Reports installation and version status |
| `"Show Chrome's properties"` | `application.properties` | Layer 1 (<5ms) | Native Windows File Properties dialog via `ShellExecuteExW` |
| `"Open Chrome's installation folder"` | `application.install_dir` | Layer 1 (<5ms) | `explorer.exe /select` revealing executable in directory |
| `"Show Chrome's version"` | `application.metadata` | Layer 1 (<5ms) | Reports version (`155.0.8059.85`) and publisher (`Google LLC`) |
| `"Open Chrome's settings"` | `application.settings` | Layer 1 (<5ms) | Opens `chrome://settings` in default browser |
| `"Scan applications"` | `application.refresh` | Layer 1 (<5ms) | Triggers background catalogue reconciliation |

---

### 5. Automated Test Results

Automated unit and integration tests were executed via Python unittest:
- **`tests/test_universal_app_discovery_and_registry.py`**: **19/19 PASSED** (1.075s)
  - `test_discovered_application_dataclass_and_serialization`: PASSED
  - `test_windows_pe_version_and_publisher_extraction`: PASSED
  - `test_category_heuristics`: PASSED
  - `test_additive_sqlite_migration_without_data_loss`: PASSED
  - `test_deduplication_prefers_richer_metadata`: PASSED
  - `test_user_defined_alias_persistence_and_removal`: PASSED
  - `test_ambiguity_returns_candidates_and_never_weak_match`: PASSED
  - `test_controlled_fuzzy_matching_and_clean_names`: PASSED
  - `test_temporal_discovery_installed_yesterday`: PASSED
  - `test_application_resolver_resolves_discovered_apps`: PASSED
  - `test_app_control_launch_discovered_app`: PASSED
  - `test_is_app_installed_status_check`: PASSED
  - `test_list_installed_apps_and_browser_filtering`: PASSED
  - `test_open_app_install_dir`: PASSED
  - `test_open_browser_internal_settings_vs_unsupported`: PASSED
  - `test_get_app_metadata_reporting`: PASSED
  - `test_tool_registry_application_tools_registered`: PASSED
  - `test_executor_handles_application_status_and_metadata`: PASSED
  - `test_dynamic_runtime_refresh_without_restart`: PASSED

- **Full Regression Test Suite**:
  - `tests/test_natural_language_commands.py`: **13/13 PASSED** (0.555s)
  - `tests/test_phase5_routing_and_confirmations.py`: **23/23 PASSED** (16.720s)
  - `tests/test_phase6_chrome_gaming_acer.py`: **27/27 PASSED** (5.922s)
  - `tests/test_verified_learning_and_procedures.py`: **12/12 PASSED** (2.635s)
- **Total Regressions**: **0 regressions** across 94 comprehensive tests.

---

### 6. Manual Windows Verification Instructions

To physically verify the new capabilities on Windows 11:
1. **Refresh Catalogue**:
   - Speak or type: `"Scan applications"`
   - Expected Output: JARVIS scans shortcuts, registry, and tools, reporting newly found apps.
2. **Launch & Verify**:
   - Speak or type: `"Open Brave"` or `"Open Google Chrome"`
   - Expected Output: The application window launches and focuses.
3. **Properties Dialog**:
   - Speak or type: `"Show Chrome's properties"`
   - Expected Output: The native Windows file Properties modal appears for `chrome.exe`.
4. **Installation Folder Reveal**:
   - Speak or type: `"Open Chrome's installation folder"`
   - Expected Output: Windows File Explorer opens with `chrome.exe` selected.
5. **Metadata & Status**:
   - Speak or type: `"Show Chrome's version"`
   - Expected Output: JARVIS announces the exact PE version and publisher.
6. **Browser Settings vs Unsupported**:
   - Speak or type: `"Open Chrome's settings"` -> Opens `chrome://settings`.
   - Speak or type: `"Open Calculator's settings"` -> JARVIS honestly explains that Calculator does not expose an external settings URL and opens system app details instead.
7. **Custom Aliases**:
   - In Python or chat: `app_discovery.add_user_alias("brave", "crypto_browser")`
   - Speak or type: `"Open crypto_browser"` -> Brave launches immediately.

---

### 7. Ubuntu Linux Implementation & Limitations

#### What Works on Ubuntu
- **Desktop Entry Scanning**: Discovers standard packages from `/usr/share/applications`, user entries from `~/.local/share/applications`, and Snap/Flatpak applications.
- **Categorization**: Reads `Categories=Network;WebBrowser;` to categorize apps.
- **Launch Verification**: Spawns processes via `subprocess.Popen` and tracks PID via `psutil`.
- **Desktop Control**:
  - Folder reveal: `xdg-open <directory>`.
  - System app settings: `gnome-control-center default-applications` or `software-properties-gtk`.
  - Browser settings: `xdg-open chrome://settings` or `firefox about:preferences`.

#### Ubuntu Limitations
- **No Native File Properties Modal**: Linux desktop environments (GNOME Nautilus, KDE Dolphin, XFCE Thunar) do not expose an equivalent of Win32 `ShellExecuteExW(SEE_MASK_INVOKEIDLIST)`. When requested on Linux, JARVIS opens the file's parent folder using `xdg-open` and reports the file stats (size, permissions, modified timestamp) honestly.
- **Snap/Flatpak Sandbox Isolation**: Executables under `/snap/bin` or `flatpak run` execute inside application cgroups. File inspection of their internal binaries is restricted by sandbox namespaces.
- **Filesystem Watcher Mechanism**: `win32file.ReadDirectoryChangesW` is Windows-only. On Linux, `pyinotify` or `inotifywait` is used if available; otherwise, JARVIS relies on a periodic 60-second check on `/usr/share/applications` and `~/.local/share/applications`.
