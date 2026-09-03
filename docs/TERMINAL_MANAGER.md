# Terminal Manager Subsystem

## Overview
The Terminal Manager (`core/os/terminal_manager.py`) provides cross-platform shell execution for Jarvis, automatically detecting native shells (PowerShell / CMD on Windows; bash / sh on Linux) and executing shell commands with full stdout, stderr, process ID, and duration metrics.

---

## Capabilities & Methods

- `_detect_shell() -> str`: Detects host system shell.
- `execute(command: str, cwd: str = None, timeout: float = 30.0) -> dict`: Executes a shell command synchronously and returns a structured metric payload.
- `execute_async(command: str, cwd: str = None) -> dict`: Spawns long-running commands (e.g., `npm run dev`) in the background.
- `terminate_process(pid: int) -> bool`: Terminates background processes safely.
- `_redact_secrets(text: str) -> str`: Masks API keys, passwords, and `.env` credentials.

---

## Spoken Summarization Rule
- If terminal output is short (<= 150 characters), Jarvis reads the output concisely.
- If output is long (> 150 characters), Jarvis speaks: *"I found the output. I've displayed it in the Jarvis interface."* and renders full output in the UI console.
