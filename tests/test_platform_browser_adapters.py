import sys
import unittest
from unittest.mock import patch
from core.platform.windows_platform import WindowsPlatform
from core.platform.linux_platform import LinuxPlatform

class TestPlatformBrowserAdapters(unittest.TestCase):

    def test_windows_platform_browser_probe(self):
        wp = WindowsPlatform()
        browsers = wp.get_available_browsers()
        self.assertIsInstance(browsers, list)
        self.assertGreater(len(browsers), 0)
        self.assertTrue(wp.is_browser_available("default"))

    def test_linux_platform_browser_probe(self):
        lp = LinuxPlatform()
        browsers = lp.get_available_browsers()
        self.assertIsInstance(browsers, list)
        self.assertGreater(len(browsers), 0)
        self.assertTrue(lp.is_browser_available("default"))

    def test_windows_open_browser_mock(self):
        wp = WindowsPlatform()
        with patch.object(wp, "_probe_browser_executable", return_value="C:\\Fake\\chrome.exe"):
            with patch("subprocess.Popen") as mock_popen:
                success = wp.open_browser("chrome", "https://www.google.com")
                self.assertTrue(success)
                mock_popen.assert_called_once()

    def test_linux_open_browser_mock(self):
        lp = LinuxPlatform()
        with patch.object(lp, "_probe_browser_executable", return_value="/usr/bin/google-chrome"):
            with patch("subprocess.Popen") as mock_popen:
                success = lp.open_browser("chrome", "https://www.google.com")
                self.assertTrue(success)
                mock_popen.assert_called_once()

if __name__ == "__main__":
    unittest.main()
