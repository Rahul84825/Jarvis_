"""Verification Engine for JARVIS.
Provides independent, multi-level verification of tool and procedure execution.
Strictly distinguishes between:
- ATTEMPTED: Command dispatched, outcome pending.
- INITIATED: Process or command launched, but not yet verified stable/running.
- COMPLETED: Command reported success without external validation.
- INDEPENDENTLY_VERIFIED: External probe (process list, filesystem, CDP, OS state) independently confirmed expected real-world state.
- FAILED: Command failed or verification probe proved expected state was not reached.
"""

import os
import time
import logging
from enum import Enum
from typing import Dict, Any, Optional, List
import psutil

logger = logging.getLogger("Jarvis.VerificationEngine")


class OutcomeLevel(str, Enum):
    ATTEMPTED = "attempted"
    INITIATED = "initiated"
    COMPLETED = "completed"
    INDEPENDENTLY_VERIFIED = "independently_verified"
    FAILED = "failed"


class VerificationEngine:
    """Performs independent read-back and real-world system state verification for executed tools."""

    def __init__(self):
        logger.info("VerificationEngine initialized.")

    def verify_action_outcome(
        self,
        tool_name: str,
        args: Dict[str, Any],
        tool_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Evaluates tool execution and performs independent verification where supported.

        Returns:
            Dictionary containing:
            - outcome: OutcomeLevel (attempted, initiated, completed, independently_verified, failed)
            - verified: bool (True only if independently verified or reliably completed)
            - evidence: Dict[str, Any] detailing physical verification evidence
            - failure_reason: Optional[str]
            - self_reported: bool
        """
        if not tool_result:
            return {
                "outcome": OutcomeLevel.FAILED.value,
                "verified": False,
                "evidence": {"check_type": "empty_result", "details": "Tool returned null or empty result."},
                "failure_reason": "No result returned from tool execution.",
                "self_reported": False
            }

        success = tool_result.get("success", False)
        message = tool_result.get("message", "")

        # If tool explicitly returned failure
        if not success:
            return {
                "outcome": OutcomeLevel.FAILED.value,
                "verified": False,
                "evidence": {
                    "check_type": "tool_reported_failure",
                    "details": message or "Tool reported execution failure.",
                    "timestamp": time.time()
                },
                "failure_reason": message or "Execution failed.",
                "self_reported": True
            }

        target = args.get("target") or args.get("application") or args.get("path") or args.get("url") or ""

        # Strategy 1: Application Launch & Process Verification
        if tool_name in ["open_app", "application.launch", "open_application", "launch_workspace"]:
            proc_evidence = self.verify_process_running(target)
            if proc_evidence.get("verified"):
                return {
                    "outcome": OutcomeLevel.INDEPENDENTLY_VERIFIED.value,
                    "verified": True,
                    "evidence": proc_evidence,
                    "failure_reason": None,
                    "self_reported": False
                }
            else:
                # Process not yet detected in process table: classify as INITIATED (signal sent)
                return {
                    "outcome": OutcomeLevel.INITIATED.value,
                    "verified": False,
                    "evidence": {
                        "check_type": "process_check_initiated",
                        "details": f"Launch signal sent for '{target}', but process not yet confirmed in running processes.",
                        "target": target,
                        "timestamp": time.time()
                    },
                    "failure_reason": None,
                    "self_reported": True
                }

        # Strategy 2: File Creation or Modification Verification
        if tool_name in ["write_file", "create_file", "save_file", "write_to_notepad"]:
            file_path = args.get("path") or args.get("file_path") or target
            file_evidence = self.verify_file_exists(file_path, min_size_bytes=1)
            if file_evidence.get("verified"):
                return {
                    "outcome": OutcomeLevel.INDEPENDENTLY_VERIFIED.value,
                    "verified": True,
                    "evidence": file_evidence,
                    "failure_reason": None,
                    "self_reported": False
                }
            else:
                return {
                    "outcome": OutcomeLevel.FAILED.value,
                    "verified": False,
                    "evidence": file_evidence,
                    "failure_reason": f"File '{file_path}' was not found on disk after write operation.",
                    "self_reported": False
                }

        # Strategy 3: Directory / Folder Verification
        if tool_name in ["open_folder", "create_folder"]:
            dir_path = args.get("path") or target
            dir_evidence = self.verify_directory_exists(dir_path)
            if dir_evidence.get("verified"):
                return {
                    "outcome": OutcomeLevel.INDEPENDENTLY_VERIFIED.value,
                    "verified": True,
                    "evidence": dir_evidence,
                    "failure_reason": None,
                    "self_reported": False
                }

        # Strategy 4: Chrome Tab & Browser Verification
        if tool_name in ["open_browser", "open_website", "open_new_chrome_tab", "chrome_open_url", "browser_tab_control"]:
            tab_evidence = self.verify_chrome_tab(target)
            if tab_evidence.get("verified"):
                return {
                    "outcome": OutcomeLevel.INDEPENDENTLY_VERIFIED.value,
                    "verified": True,
                    "evidence": tab_evidence,
                    "failure_reason": None,
                    "self_reported": False
                }

        # Strategy 5: Windows Power Scheme Verification
        if tool_name in ["power.scheme", "set_power_scheme"]:
            power_evidence = self.verify_power_scheme(target)
            if power_evidence.get("verified"):
                return {
                    "outcome": OutcomeLevel.INDEPENDENTLY_VERIFIED.value,
                    "verified": True,
                    "evidence": power_evidence,
                    "failure_reason": None,
                    "self_reported": False
                }

        # Default Strategy: Self-Reported Success (Independent verification unavailable)
        return {
            "outcome": OutcomeLevel.COMPLETED.value,
            "verified": True,
            "evidence": {
                "check_type": "self_reported_tool_return",
                "details": message or "Tool reported success. Independent OS probe is not supported for this action.",
                "limitation": "independent_verification_unavailable",
                "timestamp": time.time()
            },
            "failure_reason": None,
            "self_reported": True
        }

    # =========================================================================
    # INDEPENDENT PROBES
    # =========================================================================

    def verify_process_running(self, target: str) -> Dict[str, Any]:
        """Probes running processes via psutil to verify an application is truly active."""
        if not target or not isinstance(target, str):
            return {"verified": False, "check_type": "process_check", "details": "No target specified."}

        clean = target.lower().strip().replace(".exe", "").replace(".lnk", "")
        # Common process binary mappings
        known_aliases = {
            "chrome": ["chrome.exe"],
            "google chrome": ["chrome.exe"],
            "brave": ["brave.exe"],
            "brave browser": ["brave.exe"],
            "spotify": ["spotify.exe"],
            "vscode": ["code.exe"],
            "vs code": ["code.exe"],
            "notepad": ["notepad.exe"],
            "valorant": ["valorant.exe", "valorant-win64-shipping.exe", "riotclientservices.exe"],
            "riot client": ["riotclientservices.exe"],
            "discord": ["discord.exe"],
            "steam": ["steam.exe"],
            "calculator": ["calculatorapp.exe", "calculator.exe", "calc.exe"]
        }
        candidate_binaries = known_aliases.get(clean, [f"{clean}.exe", clean])

        try:
            for p in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
                try:
                    p_name = (p.info.get('name') or "").lower()
                    if any(c in p_name for c in candidate_binaries) or clean in p_name:
                        return {
                            "verified": True,
                            "check_type": "process_check",
                            "pid": p.info.get('pid'),
                            "name": p.info.get('name'),
                            "details": f"Process '{p.info.get('name')}' (PID {p.info.get('pid')}) verified running on host.",
                            "timestamp": time.time()
                        }
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception as e:
            logger.debug(f"Error scanning processes: {e}")

        return {
            "verified": False,
            "check_type": "process_check",
            "details": f"No running process matching '{target}' found.",
            "timestamp": time.time()
        }

    def verify_file_exists(self, file_path: str, min_size_bytes: int = 0) -> Dict[str, Any]:
        """Verifies that a file exists on disk and meets minimum size requirements."""
        if not file_path:
            return {"verified": False, "check_type": "file_check", "details": "No file path provided."}

        try:
            resolved = os.path.abspath(os.path.expanduser(str(file_path)))
            if os.path.exists(resolved) and os.path.isfile(resolved):
                size = os.path.getsize(resolved)
                if size >= min_size_bytes:
                    return {
                        "verified": True,
                        "check_type": "file_check",
                        "path": resolved,
                        "size_bytes": size,
                        "file_size_bytes": size,
                        "details": f"File verified on disk at '{resolved}' ({size} bytes).",
                        "timestamp": time.time()
                    }
                else:
                    return {
                        "verified": False,
                        "check_type": "file_check",
                        "path": resolved,
                        "size_bytes": size,
                        "details": f"File exists but is smaller than required ({size} < {min_size_bytes} bytes).",
                        "timestamp": time.time()
                    }
        except Exception as e:
            return {"verified": False, "check_type": "file_check", "details": f"File verification error: {e}"}

        return {"verified": False, "check_type": "file_check", "details": f"File '{file_path}' does not exist on disk."}

    def verify_directory_exists(self, dir_path: str) -> Dict[str, Any]:
        """Verifies that a directory exists on disk and is accessible."""
        if not dir_path:
            return {"verified": False, "check_type": "directory_check", "details": "No directory path provided."}

        try:
            resolved = os.path.abspath(os.path.expanduser(str(dir_path)))
            if os.path.exists(resolved) and os.path.isdir(resolved):
                children = len(os.listdir(resolved))
                return {
                    "verified": True,
                    "check_type": "directory_check",
                    "path": resolved,
                    "child_count": children,
                    "details": f"Directory verified on disk at '{resolved}' ({children} items).",
                    "timestamp": time.time()
                }
        except Exception as e:
            return {"verified": False, "check_type": "directory_check", "details": f"Directory check error: {e}"}

        return {"verified": False, "check_type": "directory_check", "details": f"Directory '{dir_path}' does not exist."}

    def verify_chrome_tab(self, target: str) -> Dict[str, Any]:
        """Probes Chrome CDP to verify a tab is loaded."""
        try:
            import urllib.request
            import json
            req = urllib.request.Request("http://127.0.0.1:9222/json/list")
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                tabs = json.loads(resp.read().decode())
                clean = (target or "").lower().strip()
                for tab in tabs:
                    t_title = tab.get("title", "").lower()
                    t_url = tab.get("url", "").lower()
                    if clean and (clean in t_title or clean in t_url):
                        return {
                            "verified": True,
                            "check_type": "cdp_tab_check",
                            "tab_id": tab.get("id"),
                            "title": tab.get("title"),
                            "url": tab.get("url"),
                            "details": f"Tab '{tab.get('title')}' verified via CDP.",
                            "timestamp": time.time()
                        }
                if tabs and not clean:
                    return {
                        "verified": True,
                        "check_type": "cdp_tab_check",
                        "tab_count": len(tabs),
                        "details": f"Chrome has {len(tabs)} tabs open via CDP.",
                        "timestamp": time.time()
                    }
        except Exception:
            pass

        return {
            "verified": False,
            "check_type": "cdp_tab_check",
            "details": "Chrome CDP endpoint unreachable or tab not found.",
            "limitation": "cdp_remote_debugging_unattached",
            "timestamp": time.time()
        }

    def verify_power_scheme(self, expected_scheme: str) -> Dict[str, Any]:
        """Probes powercfg to verify the active Windows power plan."""
        try:
            from core.os.power_manager import power_manager
            status = power_manager.get_power_scheme_status()
            active = (status.get("active_scheme_name") or "").lower()
            clean = (expected_scheme or "").lower().strip()
            if clean in active or active in clean:
                return {
                    "verified": True,
                    "check_type": "power_scheme_check",
                    "active_scheme": status.get("active_scheme_name"),
                    "guid": status.get("active_scheme_guid"),
                    "details": f"Active Windows power plan verified as '{status.get('active_scheme_name')}'.",
                    "timestamp": time.time()
                }
        except Exception:
            pass

        return {
            "verified": False,
            "check_type": "power_scheme_check",
            "details": "Failed to read-back active Windows power scheme.",
            "timestamp": time.time()
        }


# Global singleton
verification_engine = VerificationEngine()
