import unittest
from unittest.mock import patch, MagicMock
from core.platform.platform_manager import platform_manager, PlatformManager
from core.platform.base_platform import BasePlatform

class TestPlatformManager(unittest.TestCase):

    def test_singleton_instance_exists(self):
        self.assertIsNotNone(platform_manager)
        self.assertTrue(isinstance(platform_manager, PlatformManager))

    def test_os_properties(self):
        self.assertIn(platform_manager.os_name, ["Windows", "Linux", "Darwin"])
        self.assertIsInstance(platform_manager.os_version, str)
        self.assertIsInstance(platform_manager.architecture, str)

    def test_is_windows_or_linux_boolean(self):
        self.assertIsInstance(platform_manager.is_windows(), bool)
        self.assertIsInstance(platform_manager.is_linux(), bool)

    @patch("platform.system", return_value="Windows")
    def test_windows_instantiation(self, mock_sys):
        mgr = PlatformManager()
        self.assertTrue(mgr.is_windows())
        self.assertFalse(mgr.is_linux())

    @patch("platform.system", return_value="Linux")
    def test_linux_instantiation(self, mock_sys):
        mgr = PlatformManager()
        self.assertTrue(mgr.is_linux())
        self.assertFalse(mgr.is_windows())

    @patch("platform.system", return_value="FreeBSD")
    def test_unsupported_platform_fallback(self, mock_sys):
        mgr = PlatformManager()
        self.assertFalse(mgr.is_windows())
        self.assertFalse(mgr.is_linux())
        self.assertIsInstance(mgr.platform, BasePlatform)

    def test_delegated_folder_path(self):
        path = platform_manager.get_folder_path("downloads")
        self.assertTrue("Downloads" in str(path) or path.exists())

    def test_delegated_system_metrics(self):
        success, metrics = platform_manager.get_system_metrics()
        self.assertIsInstance(success, bool)
        self.assertIsInstance(metrics, dict)

if __name__ == "__main__":
    unittest.main()
