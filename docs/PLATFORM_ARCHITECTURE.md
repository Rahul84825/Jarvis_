# Platform Architecture — Project Goliya

## Overview
Goliya uses a clean platform abstraction layer decoupling core intelligence, command parsing, and response management from operating system specific APIs.

---

## Architectural Diagram

```
Goliya Core (main.py / executor.py / intent_engine.py)
                   │
                   ▼
       Platform Manager (core/platform/platform_manager.py)
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
 Windows Platform    Linux Platform
(windows_platform.py) (linux_platform.py)
         │                   │
         ▼                   ▼
 Windows OS          Linux OS
 (Win32, Pycaw)     (PulseAudio, xdg-open)
```

---

## Layer Definitions

### 1. Goliya Core
- **`main.py`**: System coordinator managing VAD listener, transcriber, response manager, HUD UI, and event callbacks.
- **`core/intent_engine.py`**: Classifies raw natural language input into structured intent nodes.
- **`modules/system/executor.py`**: Executes structured intent nodes safely.

### 2. Platform Manager (`core/platform/platform_manager.py`)
- Detects running OS automatically (`platform.system()`).
- Exposes standard attributes:
  - `platform_manager.os_name` ('Windows' or 'Linux')
  - `platform_manager.os_version`
  - `platform_manager.architecture`
  - `platform_manager.is_windows()` -> `bool`
  - `platform_manager.is_linux()` -> `bool`
- Delegates all application, folder, URL, audio, and power control calls to the active platform instance.

### 3. Base Platform (`core/platform/base_platform.py`)
- Defines the abstract contract that all platform implementations must satisfy.

### 4. Windows Platform (`core/platform/windows_platform.py`)
- Implements Windows application launching using Windows registry probes (`winreg`) and `subprocess`.
- Implements Pycaw audio volume management (`IAudioEndpointVolume`).
- Implements Win32 workstation locking (`LockWorkStation`) and system power suspend.

### 5. Linux Platform (`core/platform/linux_platform.py`)
- Implements Linux executable resolution using `shutil.which` and `config/applications.json`.
- Implements PulseAudio / PipeWire volume adjustments via `pactl` and `amixer`.
- Implements Linux folder opening via `xdg-open` and desktop directory structures (`Path.home()`).
