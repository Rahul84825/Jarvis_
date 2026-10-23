"""Automated Test Suite for JARVIS File Creation, Language Registry & Desktop File Memory."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

from core.files.path_resolver import PathResolver
from core.files.file_creator import FileCreator, FileCreationResult
from core.files.file_memory import FileMemoryManager


class TestFileCreationAndMemory(unittest.TestCase):
    """Validates real file creation, path resolution, syntax validation, and persistent file memory."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="jarvis_file_test_")
        self.db_path = Path(self.test_dir) / "test_memory.db"
        self.resolver = PathResolver()
        # Mock Desktop/Documents to stay inside test_dir
        self.resolver._cached_known_folders = {
            "desktop": Path(self.test_dir) / "Desktop",
            "documents": Path(self.test_dir) / "Documents",
            "downloads": Path(self.test_dir) / "Downloads"
        }
        for p in self.resolver._cached_known_folders.values():
            p.mkdir(parents=True, exist_ok=True)

        self.file_creator = FileCreator(resolver=self.resolver)
        self.file_memory = FileMemoryManager(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_destination_resolution_with_subfolder(self):
        """Verify natural language save targets resolve to concrete paths."""
        dest, friendly = self.resolver.resolve_destination("Desktop in a folder named DSA")
        expected = self.resolver.get_known_folder("desktop") / "DSA"
        self.assertEqual(dest.resolve(), expected.resolve())
        self.assertIn("DSA", friendly)

    def test_language_detection_and_extension(self):
        """Verify programming languages and default file extensions are properly resolved."""
        cases = [
            ("Write a Python program for binary search", None, "python", ".py"),
            ("Create a C++ program for quicksort", None, "cpp", ".cpp"),
            ("Create a React component", None, "react", ".jsx"),
            ("Generate a SQL schema", None, "sql", ".sql"),
            ("Save this as markdown", None, "markdown", ".md"),
            ("Any task", "server.ts", "typescript", ".ts"),
            ("Any task", "Main.java", "java", ".java")
        ]
        for query, filename, expected_lang, expected_ext in cases:
            lang, ext = self.file_creator.detect_language_and_extension(query, filename)
            self.assertEqual(lang, expected_lang, f"Failed language for '{query}' / '{filename}'")
            self.assertEqual(ext, expected_ext, f"Failed extension for '{query}' / '{filename}'")

    def test_syntax_validation(self):
        """Verify code syntax validation checks valid AST and detects broken code."""
        # Valid Python
        valid_py = "def binary_search(arr, x):\n    return True\n"
        ok, err = self.file_creator.validate_syntax(valid_py, "python")
        self.assertTrue(ok)
        self.assertIsNone(err)

        # Invalid Python
        invalid_py = "def broken_func(:\n    pass\n"
        ok, err = self.file_creator.validate_syntax(invalid_py, "python")
        self.assertFalse(ok)
        self.assertIn("SyntaxError", err)

        # Valid JSON
        ok, _ = self.file_creator.validate_syntax('{"name": "JARVIS", "active": true}', "json")
        self.assertTrue(ok)

        # Invalid JSON
        ok, err = self.file_creator.validate_syntax('{"name": "JARVIS",}', "json")
        self.assertFalse(ok)

    def test_safe_atomic_file_creation_and_verification(self):
        """Verify file is created atomically, verified on disk, and non-empty."""
        code = "def hello():\n    return 'Hello from JARVIS'\n"
        res = self.file_creator.create_file(
            filename="binary_search.py",
            destination="Desktop in a folder named DSA",
            content=code,
            language="python"
        )
        self.assertTrue(res.success)
        self.assertTrue(os.path.exists(res.file_path))
        self.assertGreater(os.path.getsize(res.file_path), 0)
        self.assertIn("DSA", res.file_path)

        # Verify content
        with open(res.file_path, "r", encoding="utf-8") as f:
            read_back = f.read()
        self.assertEqual(read_back, code)

    def test_overwrite_protection_requires_confirmation(self):
        """Verify existing file requires explicit user confirmation before overwriting."""
        code = "initial_content = True\n"
        # First creation succeeds
        res1 = self.file_creator.create_file("test.py", "Desktop", code, "python")
        self.assertTrue(res1.success)

        # Attempt to create again with allow_overwrite=False
        res2 = self.file_creator.create_file("test.py", "Desktop", "new_content = False\n", "python", allow_overwrite=False)
        self.assertFalse(res2.success)
        self.assertTrue(res2.requires_confirmation)
        self.assertIn("already exists", res2.message)

        # Overwrite with allow_overwrite=True
        res3 = self.file_creator.create_file("test.py", "Desktop", "new_content = True\n", "python", allow_overwrite=True)
        self.assertTrue(res3.success)
        with open(res3.file_path, "r", encoding="utf-8") as f:
            self.assertIn("new_content = True", f.read())

    def test_file_memory_indexing_and_fast_search(self):
        """Verify background indexing and search discovery in file memory."""
        # Create test files
        p1 = self.resolver.get_known_folder("desktop") / "binary_search.py"
        p1.write_text("print('binary search')", encoding="utf-8")

        p2 = self.resolver.get_known_folder("documents") / "README.md"
        p2.write_text("# Project Notes", encoding="utf-8")

        # Run indexing scan
        self.file_memory._run_indexing_scan(custom_roots=[
            self.resolver.get_known_folder("desktop"),
            self.resolver.get_known_folder("documents")
        ])

        # Search by name
        results = self.file_memory.search_files("binary search")
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0].filename, "binary_search.py")

        # Search by extension
        md_results = self.file_memory.search_files("", extension=".md")
        self.assertGreaterEqual(len(md_results), 1)
        self.assertEqual(md_results[0].filename, "README.md")

    def test_file_memory_prunes_stale_paths(self):
        """Verify file memory detects and prunes paths that no longer exist on disk."""
        fake_path = str(self.resolver.get_known_folder("desktop") / "deleted_file.py")
        self.file_memory.record_created_file(fake_path, "deleted_file.py", "python", 100)

        # File doesn't exist on disk -> searching should prune it
        results = self.file_memory.search_files("deleted_file")
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
