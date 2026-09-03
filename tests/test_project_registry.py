import unittest
import tempfile
from pathlib import Path
from core.os.project_registry import ProjectRegistry

class TestProjectRegistry(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "projects.json"
        self.pr = ProjectRegistry(config_path=str(self.config_path))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_register_and_lookup(self):
        self.pr.register_project("test_proj", self.temp_dir.name)
        lookup = self.pr.get_project_path("test_proj")
        self.assertIsNotNone(lookup)
        self.assertEqual(lookup, str(Path(self.temp_dir.name).resolve()))

    def test_set_and_get_current_project(self):
        self.pr.register_project("sample_app", self.temp_dir.name)
        success = self.pr.set_current_project("sample_app")
        self.assertTrue(success)
        curr = self.pr.get_current_project()
        self.assertEqual(curr["alias"], "sample_app")

if __name__ == "__main__":
    unittest.main()
