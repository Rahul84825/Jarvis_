# Platform Support Matrix — Project Jarvis

## Overview
Jarvis uses a platform abstraction layer (`core/platform/`) ensuring equal architectural compatibility across **Windows** and **Linux**.

---

## Operating System Matrix

| Feature Subsystem | Windows 10/11 | Ubuntu / Debian Linux |
| :--- | :--- | :--- |
| **Headless Voice Core** | Supported | Supported |
| **PyQt6 HUD Dashboard** | Supported | Supported |
| **Edge TTS Cloud Speech** | Supported | Supported |
| **pyttsx3 Local Offline TTS** | Supported (SAPI5) | Supported (eSpeak) |
| **Whisper STT Transcriber** | Supported | Supported |
| **Audio Volume Adjustment** | Supported (Pycaw / Win32) | Supported (pactl / amixer) |
| **Application Launch & Control** | Supported (winreg / Popen) | Supported (which / Popen) |
| **Logical Folder Access** | Supported (Path.home / OneDrive) | Supported (Path.home / xdg-open) |
| **System Power Actions** | Supported (LockWorkStation / rundll32) | Supported (loginctl / systemctl) |
