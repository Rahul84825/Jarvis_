import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
from core.platform.linux_platform import LinuxPlatform

class TestLinuxPlatform(unittest.TestCase):

    def setUp(self):
        self.linux = LinuxPlatform()

    def test_linux_properties(self):
        self.assertTrue(self.linux.is_linux() or self.linux.os_name != "")
        self.assertIsInstance(self.linux.architecture, str)

    def test_resolve_app_key_aliases(self):
        self.assertEqual(self.linux.resolve_app_key("google chrome"), "chrome")
        self.assertEqual(self.linux.resolve_app_key("vs code"), "vscode")
        self.assertEqual(self.linux.resolve_app_key("text editor"), "notepad")
        self.assertEqual(self.linux.resolve_app_key("calc"), "calculator")

    def test_resolve_executable(self):
        exec_name = self.linux.resolve_executable("chrome")
        self.assertIn(exec_name, ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium", "chrome"])

    @patch("subprocess.Popen")
    def test_open_application_success(self, mock_popen):
        res = self.linux.open_application("vscode")
        self.assertTrue(res)

    @patch("subprocess.Popen")
    def test_open_url(self, mock_popen):
        res = self.linux.open_url("https://www.youtube.com")
        self.assertTrue(res)

    def test_get_folder_path(self):
        p_down = self.linux.get_folder_path("downloads")
        self.assertEqual(p_down.name, "Downloads")
        p_docs = self.linux.get_folder_path("documents")
        self.assertEqual(p_docs.name, "Documents")
        p_desk = self.linux.get_folder_path("desktop")
        self.assertEqual(p_desk.name, "Desktop")

    @patch("shutil.which", return_value="/usr/bin/pactl")
    @patch("subprocess.run")
    def test_volume_up_pactl(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(returncode=0)
        success, msg = self.linux.volume_up(0.10)
        self.assertTrue(success)
        self.assertIn("Volume increased", msg)

    @patch("shutil.which", return_value="/usr/bin/pactl")
    @patch("subprocess.run")
    def test_volume_down_pactl(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(returncode=0)
        success, msg = self.linux.volume_down(0.10)
        self.assertTrue(success)
        self.assertIn("Volume decreased", msg)

    @patch("shutil.which", return_value="/usr/bin/pactl")
    @patch("subprocess.run")
    def test_mute_unmute(self, mock_run, mock_which):
        mock_run.return_value = MagicMock(returncode=0)
        s_mute, m_mute = self.linux.mute_volume()
        self.assertTrue(s_mute)
        s_unmute, m_unmute = self.linux.unmute_volume()
        self.assertTrue(s_unmute)

    @patch("shutil.which", return_value=None)
    def test_unsupported_operation_graceful_fallback(self, mock_which):
        success, msg = self.linux.lock_pc()
        self.assertFalse(success)
        self.assertEqual(msg, "This operation is not supported on the current system.")

if __name__ == "__main__":
    unittest.main()
