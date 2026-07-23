import logging
import pygetwindow as gw

logger = logging.getLogger("Jarvis.WindowControl")

def get_active_window():
    """Returns the currently active window object."""
    try:
        return gw.getActiveWindow()
    except Exception as e:
        logger.error(f"Failed to get active window: {e}")
        return None

def list_open_windows() -> list:
    """Returns a list of titles of all visible, non-empty windows."""
    try:
        windows = gw.getWindowsWithTitle("")
        titles = []
        for win in windows:
            if win.title and win.title.strip():
                # Filter out system/empty artifacts
                titles.append(win.title)
        return titles
    except Exception as e:
        logger.error(f"Failed to list open windows: {e}")
        return []

def minimize_window(title_keyword: str = None) -> bool:
    """Minimizes the active window or the first window matching title_keyword."""
    try:
        if title_keyword:
            windows = gw.getWindowsWithTitle(title_keyword)
            if windows:
                windows[0].minimize()
                logger.info(f"Minimized window: '{windows[0].title}'")
                return True
            logger.warning(f"No window found matching '{title_keyword}' to minimize.")
            return False
        else:
            win = get_active_window()
            if win:
                win.minimize()
                logger.info(f"Minimized active window: '{win.title}'")
                return True
            logger.warning("No active window to minimize.")
            return False
    except Exception as e:
        logger.error(f"Error minimizing window: {e}", exc_info=True)
        return False

def maximize_window(title_keyword: str = None) -> bool:
    """Maximizes the active window or the first window matching title_keyword."""
    try:
        if title_keyword:
            windows = gw.getWindowsWithTitle(title_keyword)
            if windows:
                if windows[0].isMinimized:
                    windows[0].restore()
                windows[0].maximize()
                logger.info(f"Maximized window: '{windows[0].title}'")
                return True
            logger.warning(f"No window found matching '{title_keyword}' to maximize.")
            return False
        else:
            win = get_active_window()
            if win:
                if win.isMinimized:
                    win.restore()
                win.maximize()
                logger.info(f"Maximized active window: '{win.title}'")
                return True
            logger.warning("No active window to maximize.")
            return False
    except Exception as e:
        logger.error(f"Error maximizing window: {e}", exc_info=True)
        return False

def restore_window(title_keyword: str = None) -> bool:
    """Restores the active window or the first window matching title_keyword from minimized/maximized state."""
    try:
        if title_keyword:
            windows = gw.getWindowsWithTitle(title_keyword)
            if windows:
                windows[0].restore()
                logger.info(f"Restored window: '{windows[0].title}'")
                return True
            logger.warning(f"No window found matching '{title_keyword}' to restore.")
            return False
        else:
            win = get_active_window()
            if win:
                win.restore()
                logger.info(f"Restored active window: '{win.title}'")
                return True
            logger.warning("No active window to restore.")
            return False
    except Exception as e:
        logger.error(f"Error restoring window: {e}", exc_info=True)
        return False

def switch_to_window(title_keyword: str) -> bool:
    """Finds a window matching title_keyword, restores it, and brings it to front."""
    try:
        windows = gw.getWindowsWithTitle("")
        target_win = None
        for win in windows:
            if win.title and title_keyword.lower() in win.title.lower():
                target_win = win
                break
                
        if target_win:
            if target_win.isMinimized:
                target_win.restore()
            target_win.activate()
            logger.info(f"Switched focus to window: '{target_win.title}'")
            return True
            
        logger.warning(f"No window found matching '{title_keyword}' to focus.")
        return False
    except Exception as e:
        logger.error(f"Error switching to window '{title_keyword}': {e}", exc_info=True)
        return False

def close_window(title_keyword: str = None) -> bool:
    """Closes the active window or the first window matching title_keyword."""
    try:
        if title_keyword:
            windows = gw.getWindowsWithTitle(title_keyword)
            if windows:
                windows[0].close()
                logger.info(f"Closed window: '{windows[0].title}'")
                return True
            logger.warning(f"No window found matching '{title_keyword}' to close.")
            return False
        else:
            win = get_active_window()
            if win:
                win.close()
                logger.info(f"Closed active window: '{win.title}'")
                return True
            logger.warning("No active window to close.")
            return False
    except Exception as e:
        logger.error(f"Error closing window: {e}", exc_info=True)
        return False
