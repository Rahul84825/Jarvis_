import unittest
from unittest.mock import MagicMock, patch, call
import time
import os
from pathlib import Path

# Import modules under test
from modules.system.permissions import RiskLevel, get_action_risk_level, is_safe_command
from modules.system.executor import CommandExecutor
from memory.execution_history import ExecutionHistory
import modules.system.app_control as app_control
import modules.system.window_control as window_control
import modules.system.system_control as system_control
import modules.system.screenshot as screenshot
import modules.files.file_control as file_control

class TestPermissions(unittest.TestCase):
    def test_get_action_risk_level(self):
        """1. Verify correct safety risk level mapping for actions."""
        self.assertEqual(get_action_risk_level("open_app"), RiskLevel.LOW)
        self.assertEqual(get_action_risk_level("close_app"), RiskLevel.MEDIUM)
        self.assertEqual(get_action_risk_level("window_control", "minimize"), RiskLevel.MEDIUM)
        self.assertEqual(get_action_risk_level("file_access", "search_file"), RiskLevel.MEDIUM)
        
        # System control specific actions
        self.assertEqual(get_action_risk_level("system_control", "shutdown"), RiskLevel.HIGH)
        self.assertEqual(get_action_risk_level("system_control", "restart"), RiskLevel.HIGH)
        self.assertEqual(get_action_risk_level("system_control", "sleep"), RiskLevel.HIGH)
        self.assertEqual(get_action_risk_level("system_control", "lock"), RiskLevel.MEDIUM)
        self.assertEqual(get_action_risk_level("system_control", "volume_up"), RiskLevel.MEDIUM)

    def test_is_safe_command_valid(self):
        """2. Verify that safe parameters pass validation checks."""
        params = {"intent": "open_app", "target": "notepad", "query": "open notepad"}
        self.assertTrue(is_safe_command("open_app", params))

    def test_is_safe_command_invalid(self):
        """3. Verify that shell injection characters are blocked."""
        unsafe_params = {"intent": "open_app", "target": "notepad; calc.exe", "query": "open notepad"}
        self.assertFalse(is_safe_command("open_app", unsafe_params))
        
        unsafe_params2 = {"intent": "open_app", "target": "chrome & format c:", "query": "open chrome"}
        self.assertFalse(is_safe_command("open_app", unsafe_params2))


class TestExecutionHistory(unittest.TestCase):
    def test_history_limit(self):
        """4. Verify that execution history maintains its size limit."""
        history = ExecutionHistory(limit=5)
        for i in range(10):
            history.add_action(f"cmd {i}", "intent", f"res {i}", True)
            
        records = history.get_history()
        self.assertEqual(len(records), 5)
        self.assertEqual(records[0]["command"], "cmd 5")
        self.assertEqual(records[-1]["command"], "cmd 9")


class TestCommandExecutor(unittest.TestCase):
    def setUp(self):
        self.history = ExecutionHistory(limit=10)
        self.executor = CommandExecutor(history_tracker=self.history)

    def test_executor_block_metacharacters(self):
        """5. Verify Executor rejects unsafe commands directly."""
        intent = {"intent": "open_app", "target": "notepad | shutdown", "query": "open it"}
        result = self.executor.execute(intent)
        self.assertFalse(result["success"])
        self.assertIn("blocked", result["message"].lower())

    @patch('modules.system.app_control.open_app')
    def test_executor_low_risk_direct(self, mock_open):
        """6. Verify Executor routes LOW risk actions without confirmation."""
        mock_open.return_value = True
        intent = {"intent": "open_app", "target": "chrome", "query": "open chrome"}
        
        result = self.executor.execute(intent, confirm=False)
        self.assertTrue(result["success"])
        mock_open.assert_called_once_with("chrome")
        
        # Verify history is populated
        self.assertEqual(len(self.history.get_history()), 1)

    def test_executor_high_risk_pending(self):
        """7. Verify Executor returns confirmation pending status for HIGH risk actions."""
        intent = {"intent": "system_control", "action": "sleep", "query": "sleep computer"}
        
        result = self.executor.execute(intent, confirm=False)
        self.assertFalse(result["success"])
        self.assertTrue(result.get("pending_confirmation"))
        self.assertIn("high risk", result["message"].lower())

    @patch('modules.system.system_control.sleep_pc')
    def test_executor_high_risk_confirmed(self, mock_sleep):
        """8. Verify Executor runs HIGH risk actions once confirmed."""
        mock_sleep.return_value = (True, "Sleeping")
        intent = {"intent": "system_control", "action": "sleep", "query": "sleep computer"}
        
        result = self.executor.execute(intent, confirm=True)
        self.assertTrue(result["success"])
        mock_sleep.assert_called_once()


class TestAppControl(unittest.TestCase):
    @patch('psutil.process_iter')
    def test_is_app_running(self, mock_process_iter):
        """9. Verify checking running process state."""
        proc1 = MagicMock()
        proc1.info = {'name': 'chrome.exe'}
        mock_process_iter.return_value = [proc1]
        
        self.assertTrue(app_control.is_app_running("chrome"))
        self.assertFalse(app_control.is_app_running("spotify"))

    @patch('modules.system.app_control.is_app_running')
    @patch('modules.system.app_control.bring_app_to_front')
    @patch('subprocess.Popen')
    def test_open_app_already_running(self, mock_popen, mock_bring, mock_running):
        """10. Verify opening app already running switches focus instead of launching duplicate."""
        mock_running.return_value = True
        mock_bring.return_value = True
        
        res = app_control.open_app("chrome")
        self.assertTrue(res)
        mock_popen.assert_not_called()
        mock_bring.assert_called_once_with("chrome")

    @patch('modules.system.app_control.is_app_running')
    @patch('modules.system.app_control.resolve_app_path')
    @patch('subprocess.Popen')
    def test_open_app_launch_new(self, mock_popen, mock_resolve, mock_running):
        """11. Verify launching a new process when not running."""
        mock_running.return_value = False
        mock_resolve.return_value = "notepad.exe"
        
        res = app_control.open_app("notepad")
        self.assertTrue(res)
        mock_popen.assert_called_once()

    @patch('psutil.process_iter')
    def test_close_app_terminate(self, mock_process_iter):
        """12. Verify terminating target processes."""
        proc = MagicMock()
        proc.info = {'name': 'spotify.exe', 'pid': 1234}
        mock_process_iter.return_value = [proc]
        
        res = app_control.close_app("spotify")
        self.assertTrue(res)
        proc.terminate.assert_called_once()

    def test_close_app_explorer_safety(self):
        """13. Verify safety lock prevents closing File Explorer."""
        res = app_control.close_app("explorer")
        self.assertFalse(res)


class TestWindowControl(unittest.TestCase):
    @patch('pygetwindow.getActiveWindow')
    def test_minimize_window_active(self, mock_get_active):
        """14. Verify minimizing the active window."""
        mock_win = MagicMock()
        mock_win.title = "Notepad"
        mock_get_active.return_value = mock_win
        
        res = window_control.minimize_window()
        self.assertTrue(res)
        mock_win.minimize.assert_called_once()

    @patch('pygetwindow.getWindowsWithTitle')
    def test_minimize_window_by_title(self, mock_get_windows):
        """15. Verify minimizing window matching title."""
        mock_win = MagicMock()
        mock_win.title = "Google Chrome"
        mock_get_windows.return_value = [mock_win]
        
        res = window_control.minimize_window("chrome")
        self.assertTrue(res)
        mock_win.minimize.assert_called_once()

    @patch('pygetwindow.getActiveWindow')
    def test_maximize_window_active(self, mock_get_active):
        """16. Verify maximizing active window."""
        mock_win = MagicMock()
        mock_win.title = "VS Code"
        mock_win.isMinimized = False
        mock_get_active.return_value = mock_win
        
        res = window_control.maximize_window()
        self.assertTrue(res)
        mock_win.maximize.assert_called_once()

    @patch('pygetwindow.getWindowsWithTitle')
    def test_switch_to_window(self, mock_get_windows):
        """17. Verify switching/focusing window titles."""
        mock_win = MagicMock()
        mock_win.title = "Spotify Premium"
        mock_win.isMinimized = True
        mock_get_windows.return_value = [mock_win]
        
        res = window_control.switch_to_window("spotify")
        self.assertTrue(res)
        mock_win.restore.assert_called_once()
        mock_win.activate.assert_called_once()

    @patch('pygetwindow.getWindowsWithTitle')
    def test_list_open_windows(self, mock_get_windows):
        """18. Verify listing visible windows."""
        win1 = MagicMock()
        win1.title = "Notepad"
        win2 = MagicMock()
        win2.title = ""
        win3 = MagicMock()
        win3.title = "Slack"
        mock_get_windows.return_value = [win1, win2, win3]
        
        titles = window_control.list_open_windows()
        self.assertEqual(titles, ["Notepad", "Slack"])


class TestSystemControl(unittest.TestCase):
    @patch('modules.system.system_control.get_volume_interface')
    def test_volume_up(self, mock_get_vol):
        """19. Verify master volume increase."""
        mock_vol = MagicMock()
        mock_vol.GetMasterVolumeLevelScalar.return_value = 0.50
        mock_vol.GetMute.return_value = False
        mock_get_vol.return_value = mock_vol
        
        success, msg = system_control.volume_up()
        self.assertTrue(success)
        mock_vol.SetMasterVolumeLevelScalar.assert_called_once_with(0.60, None)

    @patch('modules.system.system_control.get_volume_interface')
    def test_mute_volume(self, mock_get_vol):
        """20. Verify volume mute."""
        mock_vol = MagicMock()
        mock_get_vol.return_value = mock_vol
        
        success, msg = system_control.mute_volume()
        self.assertTrue(success)
        mock_vol.SetMute.assert_called_once_with(1, None)

    @patch('ctypes.windll.user32.LockWorkStation')
    def test_lock_pc(self, mock_lock):
        """21. Verify computer locking DLL call."""
        success, msg = system_control.lock_pc()
        self.assertTrue(success)
        mock_lock.assert_called_once()

    @patch('subprocess.Popen')
    def test_power_commands(self, mock_popen):
        """22. Verify power commands issue subprocess calls."""
        # Sleep
        success, msg = system_control.sleep_pc()
        self.assertTrue(success)
        
        # Shutdown
        success2, msg2 = system_control.shutdown_pc()
        self.assertTrue(success2)
        mock_popen.assert_has_calls([
            call(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"]),
            call(["shutdown.exe", "/s", "/t", "0"])
        ])

    @patch('psutil.sensors_battery')
    def test_battery_status(self, mock_battery):
        """23. Verify battery diagnostic query."""
        bat = MagicMock()
        bat.percent = 85
        bat.power_plugged = True
        mock_battery.return_value = bat
        
        success, msg = system_control.get_battery_status()
        self.assertTrue(success)
        self.assertIn("85%", msg)
        self.assertIn("plugged in", msg)


class TestScreenshot(unittest.TestCase):
    @patch('pyautogui.screenshot')
    @patch('modules.system.screenshot.SCREENSHOT_DIR')
    def test_take_screenshot(self, mock_dir, mock_screenshot):
        """24. Verify taking screenshot and saving file."""
        mock_dir.resolve.return_value = Path("dummy_folder")
        mock_img = MagicMock()
        mock_screenshot.return_value = mock_img
        
        success, msg = screenshot.take_screenshot()
        self.assertTrue(success)
        mock_screenshot.assert_called_once()
        mock_img.save.assert_called_once()

    @patch('os.startfile')
    def test_open_screenshot_folder(self, mock_startfile):
        """25. Verify opening screenshots folder."""
        res = screenshot.open_screenshot_folder()
        self.assertTrue(res)
        mock_startfile.assert_called_once()


class TestFileControl(unittest.TestCase):
    @patch('os.startfile')
    def test_open_folder_standard(self, mock_startfile):
        """26. Verify opening standard user folders."""
        res = file_control.open_folder("downloads")
        self.assertTrue(res)
        mock_startfile.assert_called_once()

    @patch('os.walk')
    def test_search_files(self, mock_walk):
        """27. Verify safe file search."""
        mock_walk.return_value = [
            ("C:\\Users\\activ\\Downloads", [], ["resume.pdf", "photo.jpg"])
        ]
        
        matches = file_control.search_files("resume.pdf")
        self.assertEqual(len(matches), 1)
        self.assertTrue(matches[0].endswith("resume.pdf"))

if __name__ == "__main__":
    unittest.main()
