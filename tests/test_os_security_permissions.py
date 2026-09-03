import unittest
from unittest.mock import patch
from core.os.filesystem_manager import FilesystemManager

class TestOSSecurityPermissions(unittest.TestCase):

    def setUp(self):
        self.fm = FilesystemManager()

    def test_permission_error_handling(self):
        with patch("pathlib.Path.iterdir", side_effect=PermissionError("Access denied")):
            res = self.fm.list_directory("C:\\System Volume Information")
            self.assertFalse(res["success"])
            self.assertIn("permission", res["error"].lower())
            self.assertNotIn("PermissionError", res["error"])

if __name__ == "__main__":
    unittest.main()
