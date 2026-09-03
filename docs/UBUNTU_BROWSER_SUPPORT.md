# Ubuntu Linux Browser Support Guide

## Overview
`LinuxPlatform` (`core/platform/linux_platform.py`) implements dynamic browser discovery and execution across Ubuntu Linux environments.

---

## Supported Ubuntu Browsers

1. **Google Chrome**: Probes `google-chrome` and `google-chrome-stable` via `shutil.which`.
2. **Chromium**: Probes `chromium-browser` and `chromium` via `shutil.which`.
3. **Mozilla Firefox**: Probes `firefox` via `shutil.which`.
4. **Microsoft Edge**: Probes `microsoft-edge` and `microsoft-edge-dev` via `shutil.which`.
5. **Default System Browser**: Fallback via `xdg-open` or `webbrowser.open`.

---

## Architecture & Testing

- **Environment**: Ubuntu Linux (AMD64 architecture)
- **Status**: **VERIFIED VIA AUTOMATED UNIT & ADAPTER TESTS**
- **Test Output**: Adapter resolution and fallback logic pass all unit test assertions.
