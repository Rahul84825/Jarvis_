import json
import unittest
from pathlib import Path

class TestAppRegistry(unittest.TestCase):

    def setUp(self):
        self.registry_path = Path(__file__).parent.parent / "config" / "applications.json"

    def test_registry_file_exists(self):
        self.assertTrue(self.registry_path.exists())

    def test_registry_valid_json(self):
        with open(self.registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)
        self.assertIn("chrome", data)
        self.assertIn("vscode", data)
        self.assertIn("steam", data)

    def test_registry_platform_keys(self):
        with open(self.registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for app, config in data.items():
            self.assertIn("windows", config)
            self.assertIn("linux", config)
            self.assertIn("aliases", config)
            self.assertIsInstance(config["aliases"], list)

    def test_chrome_aliases(self):
        with open(self.registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        chrome_aliases = data["chrome"]["aliases"]
        self.assertIn("chrome", chrome_aliases)
        self.assertIn("google chrome", chrome_aliases)
        self.assertIn("browser", chrome_aliases)

    def test_vscode_aliases(self):
        with open(self.registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        vscode_aliases = data["vscode"]["aliases"]
        self.assertIn("vscode", vscode_aliases)
        self.assertIn("vs code", vscode_aliases)
        self.assertIn("visual studio code", vscode_aliases)

if __name__ == "__main__":
    unittest.main()
