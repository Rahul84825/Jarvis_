# Windows Browser Support Guide

## Overview
`WindowsPlatform` (`core/platform/windows_platform.py`) implements dynamic browser discovery and execution across Microsoft Windows 10/11 environments.

---

## Supported Windows Browsers

1. **Google Chrome**: Probes PATH, `%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe`, `%ProgramFiles%\Google\Chrome\Application\chrome.exe`, and `%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe`.
2. **Microsoft Edge**: Probes PATH and `%ProgramFiles%\Microsoft\Edge\Application\msedge.exe`.
3. **Mozilla Firefox**: Probes PATH and `%ProgramFiles%\Mozilla Firefox\firefox.exe`.
4. **Chromium**: Probes PATH and `%LOCALAPPDATA%\Chromium\Application\chrome.exe`.
5. **Default System Browser**: Fallback via `os.startfile` or `webbrowser.open`.

---

## Testing Results

- **Environment**: Windows (AMD64 architecture)
- **Status**: **FULLY TESTED & VERIFIED**
- **Test Output**: Chrome, Edge, and Default Browser resolution operating cleanly.
