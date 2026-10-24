"""SANTRA - Production Windows Startup Launcher.

Reliably launches Santra at Windows user login / startup:
- Resolves project root directory dynamically.
- Selects the correct Python / Pythonw interpreter (preferring virtualenv if present).
- Enforces correct working directory and Python module search paths.
- Safely loads environment variables without logging secret credentials.
- Checks single-instance mutex and IPC before launching.
- Logs detailed, privacy-safe startup health records to logs/startup.log.
- Applies bounded retries (max 2 attempts) for transient startup failures.
- Runs windowlessly under pythonw without console window popups.
"""

import os
import sys
import time
import argparse
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

# Ensure project root is determined strictly relative to this launcher file
PROJECT_ROOT = Path(__file__).resolve().parent
LOGS_DIR = PROJECT_ROOT / "logs"
STARTUP_LOG = LOGS_DIR / "startup.log"

# Sensitive key patterns to mask from startup logs
SENSITIVE_KEY_PATTERNS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "AUTH", "CREDENTIAL", "PRIVATE")


def setup_startup_logging() -> logging.Logger:
    """Configures a dedicated, persistent, privacy-safe startup logger."""
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

    logger = logging.getLogger("Santra.StartupLauncher")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s - [%(levelname)s] - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    try:
        from logging.handlers import RotatingFileHandler
        fh = RotatingFileHandler(
            str(STARTUP_LOG),
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8"
        )
        fh.setFormatter(formatter)
        fh.setLevel(logging.INFO)
        logger.addHandler(fh)
    except Exception:
        pass

    # Console stream handler (only if console is attached)
    if sys.stderr is not None:
        try:
            ch = logging.StreamHandler(sys.stderr)
            ch.setFormatter(formatter)
            ch.setLevel(logging.INFO)
            logger.addHandler(ch)
        except Exception:
            pass

    return logger


logger = setup_startup_logging()


def find_python_interpreter() -> Tuple[Path, Path]:
    """Locates the project's virtualenv Python interpreter or current Python interpreter.
    Returns:
        (python_exe, pythonw_exe)
    """
    candidates = [
        PROJECT_ROOT / ".venv" / "Scripts",
        PROJECT_ROOT / "venv" / "Scripts",
        PROJECT_ROOT / "env" / "Scripts",
    ]

    for cand in candidates:
        py = cand / "python.exe"
        pyw = cand / "pythonw.exe"
        if py.exists():
            target_pyw = pyw if pyw.exists() else py
            return py.resolve(), target_pyw.resolve()

    # Fallback: Current running interpreter
    current_py = Path(sys.executable).resolve()
    current_pyw = current_py.parent / "pythonw.exe"
    target_pyw = current_pyw if current_pyw.exists() else current_py
    return current_py, target_pyw.resolve()


def load_environment_safely(env_path: Path) -> Dict[str, str]:
    """Loads environment variables from .env if present.
    Never exposes or logs secret values.
    """
    loaded_keys = []
    if not env_path.exists():
        logger.info(f"[BOOT] No .env file at '{env_path}'. Using system environment.")
        return {}

    try:
        with open(env_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip().strip("'\"")
                if key and key not in os.environ:
                    os.environ[key] = val
                    loaded_keys.append(key)

        sanitized_summary = [
            f"{k}=[SET]" if any(p in k.upper() for p in SENSITIVE_KEY_PATTERNS) else f"{k}={os.environ.get(k)}"
            for k in loaded_keys[:10]
        ]
        logger.info(f"[BOOT] Loaded {len(loaded_keys)} variables from .env ({', '.join(sanitized_summary)})")
    except Exception as e:
        logger.warning(f"[BOOT] Error reading .env file: {e}")

    return {k: "[SET]" for k in loaded_keys}


def is_already_running() -> bool:
    """Checks whether another Santra instance is currently running using single-instance guard."""
    try:
        from core.single_instance import SingleInstanceGuard
        guard = SingleInstanceGuard()
        if not guard.acquire():
            logger.info("[BOOT] Active Santra instance already detected on localhost IPC. Signaling restore.")
            guard.notify_existing("RESTORE_HUD")
            return True
        guard.release()
        return False
    except Exception as e:
        logger.debug(f"[BOOT] Single-instance precheck error: {e}")
        return False


def launch_santra(args_list=None) -> int:
    """Launches Santra with environment setup, single-instance verification, and bounded retry on boot errors."""
    start_time = time.time()
    logger.info("============================================================")
    logger.info("SANTRA APPLICATION LAUNCHER STARTING")
    logger.info(f"Project Directory : {PROJECT_ROOT}")
    logger.info(f"Working Directory : {os.getcwd()}")

    # 1. Enforce working directory and sys.path
    os.chdir(PROJECT_ROOT)
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    # 2. Identify interpreter
    py_exe, pyw_exe = find_python_interpreter()
    logger.info(f"Interpreter       : {py_exe} (Windowless: {pyw_exe.name})")

    # 3. Load .env safely
    load_environment_safely(PROJECT_ROOT / ".env")

    # 4. Check for already running instance
    if is_already_running():
        logger.info("[BOOT] Existing instance notified. Launcher exiting cleanly without spawning duplicates.")
        return 0

    # 5. Execute main application with bounded retries on transient boot failures
    max_retries = 2
    retry_delay = 2.0

    flags = sys.argv[1:] if args_list is None else args_list
    if "--minimized" not in flags and "--hidden" not in flags and not any(f in flags for f in ["--ui", "--headless"]):
        flags.append("--minimized")

    logger.info(f"[BOOT] Execution Flags: {flags}")

    for attempt in range(max_retries + 1):
        try:
            logger.info(f"[LAUNCH] Attempt {attempt + 1}/{max_retries + 1}: Starting main application...")
            import main

            # Override sys.argv with target launcher flags
            sys.argv = ["main.py"] + flags

            # Execute main entry point
            main.main()

            duration = time.time() - start_time
            logger.info(f"[EXIT] Santra completed cleanly after {duration:.2f}s.")
            return 0

        except SystemExit as se:
            duration = time.time() - start_time
            code = se.code if isinstance(se.code, int) else 0
            if code == 0:
                logger.info(f"[EXIT] Santra shut down cleanly (exit code 0) after {duration:.2f}s.")
                return 0
            else:
                logger.warning(f"[EXIT] Santra exited with status code {code} after {duration:.2f}s.")
                if attempt < max_retries:
                    logger.info(f"[RETRY] Waiting {retry_delay}s before retry attempt {attempt + 2}...")
                    time.sleep(retry_delay)
                else:
                    return code

        except Exception as err:
            duration = time.time() - start_time
            logger.error(f"[FAILURE] Unhandled startup exception: {err}", exc_info=True)
            if attempt < max_retries:
                logger.info(f"[RETRY] Retrying launch in {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                logger.critical(f"[ABORT] Santra startup failed after {max_retries + 1} bounded attempts.")
                return 1

    return 0


def main_cli():
    parser = argparse.ArgumentParser(description="Santra Startup Launcher")
    parser.add_argument("--minimized", action="store_true", help="Launch Santra minimized to system tray")
    parser.add_argument("--hidden", action="store_true", help="Launch Santra hidden in system tray")
    parser.add_argument("--ui", action="store_true", help="Launch Santra with HUD dashboard open")
    parser.add_argument("--headless", action="store_true", help="Launch in headless voice core mode")
    parser.add_argument("--verify", action="store_true", help="Perform pre-flight verification only without starting UI")

    args, unknown = parser.parse_known_args()

    if args.verify:
        py_exe, pyw_exe = find_python_interpreter()
        print(f"Project Root     : {PROJECT_ROOT}")
        print(f"Python           : {py_exe} (Exists: {py_exe.exists()})")
        print(f"Pythonw          : {pyw_exe} (Exists: {pyw_exe.exists()})")
        print(f"Main Entry Point : {PROJECT_ROOT / 'main.py'} (Exists: {(PROJECT_ROOT / 'main.py').exists()})")
        print(f"Already Running  : {is_already_running()}")
        sys.exit(0)

    exit_code = launch_santra()
    sys.exit(exit_code)


if __name__ == "__main__":
    main_cli()
