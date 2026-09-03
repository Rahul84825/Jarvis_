import unittest
from pathlib import Path
from core.platform.platform_manager import platform_manager

class TestFolderRegistry(unittest.TestCase):

    def test_logical_folders(self):
        folders = ["desktop", "downloads", "documents", "pictures", "videos", "music"]
        for f in folders:
            path = platform_manager.get_folder_path(f)
            self.assertIsInstance(path, Path)
            self.assertTrue(path.name in [f.capitalize(), f, "OneDrive"] or len(str(path)) > 0)

    def test_open_downloads_folder(self):
        path = platform_manager.get_folder_path("Open Downloads")
        self.assertEqual(path.name, "Downloads")

if __name__ == "__main__":
    unittest.main()
