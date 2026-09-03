# Browser Search & Navigation Architecture

## Overview
The Browser Architecture decouples voice command parsing, search URL building, browser selection priorities, and OS-specific executable launching into distinct platform-agnostic and platform-specific layers.

---

## Subsystem Architecture Diagram

```
                        JARVIS VOICE CORE
                                │
                        Command Router
                                │
                                ▼
         BrowserManager (`core/os/browser_manager.py`)
                                │
             ┌──────────────────┴──────────────────┐
             ▼                                     ▼
   Search URL Synthesis                  Priority Resolution
(`build_search_url` quote_plus)    (Preferred -> Fallback Chain)
             │                                     │
             └──────────────────┬──────────────────┘
                                │
                                ▼
          PlatformManager (`core/platform/platform_manager.py`)
                                │
             ┌──────────────────┴──────────────────┐
             ▼                                     ▼
     WindowsPlatform                      LinuxPlatform
  (`windows_platform.py`)              (`linux_platform.py`)
             │                                     │
     ┌───────┼───────┐                     ┌───────┼───────┐
     ▼       ▼       ▼                     ▼       ▼       ▼
  Chrome   Edge   Firefox               Chrome  Chromium Firefox
```

---

## Design Principles

1. **Platform Decoupling**: `BrowserManager` contains zero `if sys.platform == "win32"` logic. Platform specifics remain inside `WindowsPlatform` and `LinuxPlatform`.
2. **Dynamic Executable Probing**: Probes executable names via `shutil.which` and PATH/standard directories instead of hardcoding static paths.
3. **Configurable Fallback Chain**: Respects `config/browser.json` preferences and supports graceful fallback (`Chrome` -> `Chromium` -> `Default Browser`).
4. **Zero AI API Network Overhead**: Search URL synthesis and browser execution run 100% locally.
