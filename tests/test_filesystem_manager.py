import os
import unittest
import tempfile
from pathlib import Path
from core.os.filesystem_manager import FilesystemManager

class TestFilesystemManager(unittest.TestCase):

    def setUp(self):
        self.fm = FilesystemManager()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.dir_path = self.temp_dir.name

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_and_read_file(self):
        file_path = os.path.join(self.dir_path, "test.txt")
        w_res = self.fm.write_file(file_path, "Hello Filesystem")
        self.assertTrue(w_res["success"])

        r_res = self.fm.read_file(file_path)
        self.assertTrue(r_res["success"])
        self.assertEqual(r_res["content"], "Hello Filesystem")

    def test_list_directory(self):
        file_path = os.path.join(self.dir_path, "sample.txt")
        self.fm.write_file(file_path, "data")
        res = self.fm.list_directory(self.dir_path)
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 1)

    def test_search_files(self):
        file_path = os.path.join(self.dir_path, "target_file.py")
        self.fm.write_file(file_path, "# python code")
        res = self.fm.search_files("target", base_dir=self.dir_path, extension="py")
        self.assertTrue(res["success"])
        self.assertEqual(res["count"], 1)

    def test_exists_and_checks(self):
        self.assertTrue(self.fm.exists(self.dir_path))
        self.assertTrue(self.fm.is_directory(self.dir_path))
        file_path = os.path.join(self.dir_path, "check.txt")
        self.fm.write_file(file_path, "text")
        self.assertTrue(self.fm.is_file(file_path))

if __name__ == "__main__":
    unittest.main()
