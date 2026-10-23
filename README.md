# SANTRA — Autonomous AI Desktop Assistant & Reasoning Brain

**SANTRA** is a state-of-the-art, local-first voice assistant and agentic desktop copilot engineered in native Python and PyQt6.

> [!IMPORTANT]
> **Project Identity Convention:**
> **SANTRA is the official assistant name. New features, prompts, documentation, and user-facing interfaces must use Santra rather than the former identity.**

SANTRA combines:
1. **Layer 1 — Deterministic OS Reflex Core:** Fast local execution (<2ms) for desktop applications, window management, audio controls, browser navigation, screenshots, and system telemetry.
2. **Layer 2 — Context & Offline Intelligence Engine:** Pronominal resolution, user preferences, social conversational engine, jokes, identity, and robust 100% offline fallback when cloud connectivity is unavailable.
3. **Layer 3 — Multimodal AI Reasoning Brain:** Powered by NVIDIA Nemotron, OpenAI GPT-4o, and Google Gemini for advanced programming assistance, C++ algorithms, DSA explanations, time/space complexity, and safe tool-calling orchestration through a centralized Safety Gate.
4. **Visual Desktop Intelligence & Screen Understanding:** Multi-monitor, active window, and screen region visual interpretation using multimodal AI with 12 explanation styles and bounded multi-turn screen sessions.
5. **Transactional File Creation & Project Memory:** Conversational save-location workflow, Windows Known Folders and OneDrive redirection resolution, atomic writes with syntax checks across 15 languages, and non-blocking background SQLite file indexing.
6. **Smart Sleep Mode & Hands-Free Activation:** Ultra-low resource sleep mode (<0.2% CPU) with energy/VAD-gated streaming wake-word detection for **"Santra"**, instantly restoring full speech pipeline upon detection without dropping commands.

---

## Quick Start

### 1. Requirements & Setup
- Windows 10/11 (or Linux)
- Python 3.10+ (tested on Python 3.14 x64)
- Dependencies: `pip install -r requirements.txt`

### 2. Configure AI Providers
Configure providers via GUI (`Ctrl+Shift+A` or `⚙️ AI` button) or add keys to `.env`:
```env
NVIDIA_API_KEY=nvapi-your_key_here
OPENAI_API_KEY=sk-your_key_here
GEMINI_API_KEY=AIza-your_key_here
```

### 3. Run SANTRA
```bash
python main.py
```

### 4. Interactive Voice & Shortcut Controls
- Wake phrase: `"Santra"` or `"Hey Santra"`
- Sleep command: `"Santra, go to sleep."`
- Example commands:
  - `"Santra, open Chrome."`
  - `"Santra, search YouTube for Valorant highlights."`
  - `"Santra, explain my screen."`
  - `"Santra, create a C++ file on my Desktop."`
- `Space`: Voice wake / talk
- `Ctrl+Shift+S`: Visual Screen Intelligence & Explanation
- `Ctrl+Shift+A`: AI Providers & API Key Settings

### 5. Running Without Cloud (100% Local Mode)
To run SANTRA purely offline with deterministic local tools and offline responses:
```env
AI_PROVIDER=none
SANTRA_PRIVACY_MODE=STRICT
```

### 6. Run Automated Tests
```bash
# Run Santra identity, sleep mode, and wake word test suite (10 tests)
python -m unittest tests/test_santra_identity_and_wakeword.py

# Run smart sleep mode and wake preservation tests (12 tests)
python -m unittest tests/test_smart_sleep_mode.py

# Run screen understanding and browser automation tests (38 tests)
python -m unittest tests/test_screen_understanding.py tests/test_browser_intent_automation.py
```

---

## Architecture & Integration Reports
- [Santra Complete Identity Migration Report](docs/SANTRA_IDENTITY_MIGRATION_REPORT.md)
- [Comprehensive Master User Guide & Architecture](JARVIS_MASTER_ARCHITECTURE_AND_USER_GUIDE.md)
- [NVIDIA Nemotron Reasoning Engine Integration Report](docs/NVIDIA_NEMOTRON_INTEGRATION_REPORT.md)
- [Universal Desktop Interaction Report](docs/JARVIS_PHASE7_UNIVERSAL_DESKTOP_INTERACTION_REPORT.md)
- [Intelligence Baseline & Architecture Audit](docs/JARVIS_INTELLIGENCE_BASELINE.md)
