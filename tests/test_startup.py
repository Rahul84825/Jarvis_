import sys
import unittest
from unittest.mock import MagicMock, patch

# Import startup module to test
import core.startup

class TestStartup(unittest.TestCase):
    
    @patch('core.startup.IS_WINDOWS', True)
    @patch('core.startup.winreg', create=True)
    def test_is_startup_enabled_true(self, mock_winreg):
        """Verifies is_startup_enabled returns True when matching registry key exists."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        expected_cmd = core.startup.get_app_command()
        mock_winreg.QueryValueEx.return_value = (expected_cmd, 1)  # (value, registry type)
        
        enabled = core.startup.is_startup_enabled()
        
        self.assertTrue(enabled)
        mock_winreg.OpenKey.assert_called_once_with(
            mock_winreg.HKEY_CURRENT_USER,
            core.startup.REG_KEY_PATH,
            0,
            mock_winreg.KEY_READ
        )
        mock_winreg.QueryValueEx.assert_called_once_with(mock_key, core.startup.REG_VAL_NAME)
        mock_winreg.CloseKey.assert_called_once_with(mock_key)

    @patch('core.startup.IS_WINDOWS', True)
    @patch('core.startup.winreg', create=True)
    def test_is_startup_enabled_false_missing(self, mock_winreg):
        """Verifies is_startup_enabled returns False when key is missing."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        # Raise FileNotFoundError to simulate missing registry entry
        mock_winreg.QueryValueEx.side_effect = FileNotFoundError()
        
        enabled = core.startup.is_startup_enabled()
        
        self.assertFalse(enabled)
        mock_winreg.CloseKey.assert_called_once_with(mock_key)

    @patch('core.startup.IS_WINDOWS', True)
    @patch('core.startup.winreg', create=True)
    def test_enable_startup(self, mock_winreg):
        """Verifies enable_startup writes the correct command to registry."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        
        success = core.startup.enable_startup()
        
        self.assertTrue(success)
        expected_cmd = core.startup.get_app_command()
        mock_winreg.SetValueEx.assert_called_once_with(
            mock_key,
            core.startup.REG_VAL_NAME,
            0,
            mock_winreg.REG_SZ,
            expected_cmd
        )
        mock_winreg.CloseKey.assert_called_once_with(mock_key)

    @patch('core.startup.IS_WINDOWS', True)
    @patch('core.startup.winreg', create=True)
    def test_disable_startup(self, mock_winreg):
        """Verifies disable_startup removes registry value."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        
        success = core.startup.disable_startup()
        
        self.assertTrue(success)
        mock_winreg.DeleteValue.assert_called_once_with(mock_key, core.startup.REG_VAL_NAME)
        mock_winreg.CloseKey.assert_called_once_with(mock_key)

if __name__ == "__main__":
    unittest.main()
