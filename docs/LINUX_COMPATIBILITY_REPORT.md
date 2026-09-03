# Linux Compatibility Report — Project Goliya

## Overview
This report documents the cross-platform Linux compatibility implementation added to Goliya. Goliya now operates natively across both **Windows** and **Linux** environments using a modular platform abstraction architecture.

---

## Supported Linux Environments
- **Tested & Verified Distribution**: Ubuntu / Debian-based distributions (22.04 LTS, 24.04 LTS).
- **Compatible Desktop Environments**: GNOME, KDE Plasma, XFCE, Cinnamon, MATE.

---

## Supported & Implemented Capabilities

| Feature Category | Feature Name | Linux Mechanism | Status |
| :--- | :--- | :--- | :--- |
| **Application Launching** | Launch Apps (`Chrome`, `VS Code`, `Steam`, etc.) | `shutil.which()`, `subprocess.Popen([cmd])`, `config/applications.json` | Supported |
| **Application Termination**| Close Apps | `psutil` process termination, `pkill -f` fallback | Supported |
| **Folder Access** | Open Logical Folders (`Downloads`, `Desktop`, `Documents`, etc.) | `Path.home()`, `xdg-open` | Supported |
| **Web Browser Launching** | Open Web URLs (`YouTube`, `GitHub`, `ChatGPT`, etc.) | `xdg-open`, `webbrowser.open()` | Supported |
| **Audio Volume Control** | Volume Up, Volume Down, Mute, Unmute | `pactl` (PulseAudio / PipeWire), `amixer` fallback | Supported |
| **Voice Input & STT** | Microphone Input & Whisper Transcription | Cross-platform PyAudio & Faster-Whisper CPU pipeline | Supported |
| **Speech Output (TTS)** | Edge TTS & Pygame Audio Output | `edge-tts`, `pygame.mixer` | Supported |
| **Screenshots** | Capture Full Desktop Screenshot | Pillow `ImageGrab`, PyAutoGUI | Supported |
| **Power Management** | Lock, Sleep, Restart, Shutdown | `loginctl`, `systemctl`, `shutdown` | Supported |
| **System Telemetry** | CPU, RAM, Disk, Battery Metrics | `psutil`, `shutil.disk_usage("/")` | Supported |
| **Multi-Command Parsing** | Sequential Compound Sentences | `MultiCommandParser` clause & verb propagation | Supported |

---

## Unsupported / Graceful Fallback Features
- **Legacy Pycaw COM Calls**: Windows-only Pycaw audio hardware calls are isolated inside `WindowsPlatform`. On Linux, PulseAudio/PipeWire `pactl` is used without COM dependencies.
- **Unsupported Environment Fallback**: If a specific power command or audio tool is missing in a minimal/headless Linux container, Goliya gracefully returns:
  `{"success": false, "message": "This operation is not supported on the current system."}`
  and never crashes or exposes tracebacks to the user.

---

## Dependencies & Requirements
```bash
# Core Dependencies
pip install psutil faster-whisper edge-tts pygame Pillow PyYAML

# Recommended System Packages (Debian/Ubuntu)
sudo apt-get update
sudo apt-get install -y pulseaudio-utils xdg-utils wmctrl psmisc
```

---

## Known Limitations
1. Window focusing on Wayland sessions may require `wmctrl` or XWayland fallback depending on display compositor permissions.
2. Battery metrics require `psutil.sensors_battery()` support from kernel sysfs `/sys/class/power_supply/`.
