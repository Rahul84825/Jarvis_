import unittest
from unittest.mock import patch, MagicMock
from core.platform.windows_platform import WindowsPlatform

class TestWindowsPlatform(unittest.TestCase):

    def setUp(self):
        self.win = WindowsPlatform()

    def test_windows_properties(self):
        self.assertTrue(self.win.is_windows() or self.win.os_name != "")

    def test_resolve_app_key_aliases(self):
        self.assertEqual(self.win.resolve_app_key("browser"), "chrome")
        self.assertEqual(self.win.resolve_app_key("visual studio code"), "vscode")
        self.assertEqual(self.win.resolve_app_key("file explorer"), "explorer")
        self.assertEqual(self.win.resolve_app_key("calc"), "calculator")

    def test_resolve_executable(self):
        exec_name = self.win.resolve_executable("chrome")
        self.assertIn("chrome", exec_name.lower())

    def test_folder_paths(self):
        p = self.win.get_folder_path("downloads")
        self.assertEqual(p.name, "Downloads")

    @patch("psutil.sensors_battery")
    def test_battery_status(self, mock_bat):
        mock_bat.return_value = MagicMock(percent=85, power_plugged=True, secsleft=-1)
        success, msg = self.win.get_battery_status()
        self.assertTrue(success)
        self.assertIn("85%", msg)

    def test_system_metrics(self):
        success, metrics = self.win.get_system_metrics()
        self.assertTrue(success)
        self.assertIn("cpu", metrics)
        self.assertIn("ram", metrics)
        self.assertIn("disk", metrics)

if __name__ == "__main__":
    unittest.main()
