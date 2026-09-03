import os
import re
import sys
import time
import shutil
import logging
import subprocess
import threading
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("Jarvis.TerminalManager")

class TerminalManager:
    """Native Terminal Subsystem Manager for executing shell commands, capturing outputs,
    monitoring processes, and redacting secret credentials across Windows and Linux.
    """

    def __init__(self):
        self.shell = self._detect_shell()
        self.running_processes: Dict[int, subprocess.Popen] = {}
        self.process_outputs: Dict[int, Dict[str, Any]] = {}
        logger.info(f"TerminalManager initialized using shell: {self.shell}")

    def _detect_shell(self) -> str:
        """Detects native OS shell binary."""
        if sys.platform == "win32":
            powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
            if powershell:
                return powershell
            return "cmd.exe"
        else:
            user_shell = os.environ.get("SHELL")
            if user_shell and shutil.which(user_shell):
                return user_shell
            return shutil.which("bash") or "/bin/sh"

    def _redact_secrets(self, text: str) -> str:
        """Masks API keys, passwords, tokens, and credentials from terminal outputs."""
        if not text:
            return ""
        patterns = [
            (r"(api[_-]?key|secret|password|token|bearer|auth)\s*[:=]\s*['\"]?([a-zA-Z0-9_\-\.]{8,})['\"]?", r"\1=***REDACTED***"),
            (r"\b(AIzaSy[a-zA-Z0-9_\-]{33})\b", "***REDACTED_GEMINI_KEY***"),
            (r"\b(sk-[a-zA-Z0-9]{32,})\b", "***REDACTED_OPENAI_KEY***"),
            (r"\b(csk-[a-zA-Z0-9]{32,})\b", "***REDACTED_CEREBRAS_KEY***")
        ]
        redacted = text
        for pat, repl in patterns:
            redacted = re.sub(pat, repl, redacted, flags=re.IGNORECASE)
        return redacted

    def execute(self, command: str, cwd: str = None, timeout: float = 30.0) -> Dict[str, Any]:
        """Executes a shell command synchronously and returns structured metrics and output."""
        if not command or not command.strip():
            return {"success": False, "operation": "terminal", "error": "Empty command string."}

        target_cwd = cwd or os.getcwd()
        t0 = time.time()

        if sys.platform == "win32" and "cmd.exe" not in self.shell.lower():
            cmd_args = [self.shell, "-NoProfile", "-NonInteractive", "-Command", command]
        elif sys.platform == "win32":
            cmd_args = [self.shell, "/c", command]
        else:
            cmd_args = [self.shell, "-c", command]

        logger.info(f"[TERMINAL_EXEC] Running command: '{command}' in '{target_cwd}'")
        try:
            proc = subprocess.Popen(
                cmd_args,
                cwd=target_cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )

            stdout, stderr = proc.communicate(timeout=timeout)
            duration = time.time() - t0

            stdout_clean = self._redact_secrets(stdout.strip()) if stdout else ""
            stderr_clean = self._redact_secrets(stderr.strip()) if stderr else ""

            success = proc.returncode == 0
            logger.info(f"[TERMINAL_RESULT] ExitCode={proc.returncode} | Duration={duration:.2f}s | PID={proc.pid}")

            return {
                "success": success,
                "operation": "terminal",
                "command": command,
                "stdout": stdout_clean,
                "stderr": stderr_clean,
                "exit_code": proc.returncode,
                "duration": duration,
                "pid": proc.pid,
                "cwd": target_cwd
            }

        except subprocess.TimeoutExpired:
            logger.error(f"[TERMINAL_TIMEOUT] Command timed out after {timeout}s: '{command}'")
            return {
                "success": False,
                "operation": "terminal",
                "command": command,
                "stdout": "",
                "stderr": f"Execution timed out after {timeout} seconds.",
                "exit_code": -1,
                "duration": timeout,
                "pid": -1,
                "cwd": target_cwd
            }
        except Exception as e:
            logger.error(f"[TERMINAL_ERROR] Execution failed: {e}", exc_info=True)
            return {
                "success": False,
                "operation": "terminal",
                "command": command,
                "stdout": "",
                "stderr": self._redact_secrets(str(e)),
                "exit_code": -1,
                "duration": time.time() - t0,
                "pid": -1,
                "cwd": target_cwd
            }

    def execute_async(self, command: str, cwd: str = None) -> Dict[str, Any]:
        """Launches a background terminal process."""
        target_cwd = cwd or os.getcwd()
        if sys.platform == "win32" and "cmd.exe" not in self.shell.lower():
            cmd_args = [self.shell, "-NoProfile", "-NonInteractive", "-Command", command]
        elif sys.platform == "win32":
            cmd_args = [self.shell, "/c", command]
        else:
            cmd_args = [self.shell, "-c", command]

        try:
            proc = subprocess.Popen(
                cmd_args,
                cwd=target_cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            self.running_processes[proc.pid] = proc
            logger.info(f"[TERMINAL_ASYNC] Process started: PID={proc.pid} Command='{command}'")

            return {
                "success": True,
                "operation": "terminal_async",
                "command": command,
                "pid": proc.pid,
                "cwd": target_cwd
            }
        except Exception as e:
            logger.error(f"[TERMINAL_ASYNC_ERROR] Failed to start async process: {e}")
            return {
                "success": False,
                "operation": "terminal_async",
                "command": command,
                "error": str(e)
            }

    def terminate_process(self, pid: int) -> bool:
        """Terminates a running terminal background process by PID."""
        proc = self.running_processes.get(pid)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=2.0)
                logger.info(f"[TERMINAL_TERMINATE] Terminated process PID={pid}")
                return True
            except Exception as e:
                logger.error(f"[TERMINAL_TERMINATE_ERROR] Failed to terminate PID={pid}: {e}")
        return False

    def is_running(self, pid: int) -> bool:
        proc = self.running_processes.get(pid)
        if proc:
            return proc.poll() is None
        return False
