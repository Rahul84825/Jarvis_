import os
import logging
import pyautogui
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("Jarvis.Screenshot")

# Base directory for screenshots
SCREENSHOT_DIR = Path(__file__).parent.parent.parent.resolve() / "screenshots"

# Ensure the screenshots directory exists
SCREENSHOT_DIR.mkdir(exist_ok=True)

def take_screenshot() -> (bool, str):
    """Captures a full screen screenshot and saves it as a timestamped PNG under screenshots/."""
    try:
        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        filepath = SCREENSHOT_DIR / filename
        
        logger.info(f"Taking screenshot. Saving to: {filepath}")
        # Capture and save screenshot
        screenshot = pyautogui.screenshot()
        screenshot.save(str(filepath))
        
        msg = f"Screenshot saved successfully to screenshots folder as {filename}."
        return True, msg
    except Exception as e:
        logger.error(f"Failed to capture screenshot: {e}", exc_info=True)
        return False, f"Failed to capture screenshot: {e}"

def open_screenshot_folder() -> bool:
    """Opens the screenshots directory in Windows Explorer."""
    logger.info(f"Opening screenshots folder: {SCREENSHOT_DIR}")
    try:
        if not SCREENSHOT_DIR.exists():
            SCREENSHOT_DIR.mkdir(exist_ok=True)
        os.startfile(str(SCREENSHOT_DIR))
        return True
    except Exception as e:
        logger.error(f"Failed to open screenshots directory: {e}")
        return False
