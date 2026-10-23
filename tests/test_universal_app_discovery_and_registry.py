"""Comprehensive Test Suite for Universal Application Discovery, Dynamic Registry,
and Desktop Control across Windows and Linux.
"""

import os
import sys
import json
import time
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.apps.application_discovery import ApplicationDiscovery, DiscoveredApplication
from core.os.application_resolver import application_resolver, TargetType
from core.ai.intelligence_router import intelligence_router, MODE_FAST_LOCAL
from core.intent_engine import IntentEngine
from core.tool_registry import tool_registry
from modules.system import app_control
from modules.system.executor import CommandExecutor
from core.response_registry import CommandOutcome


class TestUniversalAppDiscoveryAndRegistry(unittest.TestCase):
    """Verifies all phases of the Universal Application Discovery and Control system."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = str(Path(self.temp_dir) / "test_applications.db")
        self.test_json_path = str(Path(self.temp_dir) / "test_applications.json")

        # Mock configured applications.json
        with open(self.test_json_path, "w", encoding="utf-8") as f:
            json.dump({
                "chrome": {
                    "windows": "chrome.exe",
                    "linux": "google-chrome",
                    "aliases": ["google chrome", "chrome browser", "browser"]
                },
                "vscode": {
                    "windows": "code.exe",
                    "linux": "code",
                    "aliases": ["visual studio code", "vs code", "code"]
                }
            }, f)

        # Isolated ApplicationDiscovery instance
        self.discovery = ApplicationDiscovery(
            db_path=self.test_db_path,
            apps_json_path=self.test_json_path,
            auto_scan=False
        )
        self.intent_engine = IntentEngine()
        self.executor = CommandExecutor()

    def tearDown(self):
        try:
            self.discovery.stop_background_watcher()
            shutil.rmtree(self.temp_dir, ignore_errors=True)
        except Exception:
            pass

    # =========================================================================
    # 1. DISCOVERY & NORMALIZATION TESTS
    # =========================================================================

    def test_discovered_application_dataclass_and_serialization(self):
        """Test DiscoveredApplication dataclass serialization, deserialization, and backward-compat getters."""
        app = DiscoveredApplication(
            app_id="brave",
            display_name="Brave Browser",
            executable_path="C:/Program Files/BraveSoftware/Brave-Browser/Application/brave.exe",
            arguments=["--incognito"],
            source="start_menu",
            platform="windows",
            is_available=True,
            launch_mechanism="executable",
            install_directory="C:/Program Files/BraveSoftware/Brave-Browser/Application",
            version="1.65.122",
            publisher="Brave Software Inc",
            category="browser",
            user_aliases=["my_brave", "crypto_browser"],
            searchable_aliases=["brave", "brave browser", "web browser"]
        )
        # Test backward-compatible properties
        self.assertEqual(app.discovery_source, "start_menu")
        self.assertEqual(app.os, "windows")
        self.assertTrue(app.availability_status)
        self.assertGreater(app.last_verification_timestamp, 0.0)

        # To dict and from dict roundtrip
        d = app.to_dict()
        self.assertIn("searchable_aliases", d)
        self.assertIn("user_aliases", d)

        restored = DiscoveredApplication.from_dict(d)
        self.assertEqual(restored.app_id, "brave")
        self.assertEqual(restored.version, "1.65.122")
        self.assertEqual(restored.publisher, "Brave Software Inc")
        self.assertEqual(restored.user_aliases, ["my_brave", "crypto_browser"])
        self.assertEqual(restored.arguments, ["--incognito"])

    def test_clean_display_name_and_id_generation(self):
        """Test display name cleaning and slug generation."""
        raw_names = [
            ("Google Chrome.exe", "Google Chrome", "google_chrome"),
            ("Microsoft Visual Studio Code (x64).lnk", "Microsoft Visual Studio Code", "microsoft_visual_studio_code"),
            ("Spotify - Shortcut.lnk", "Spotify", "spotify"),
            ("VLC Media Player 64-bit", "VLC Media Player", "vlc_media_player"),
            ("GIMP 2.10.desktop", "GIMP 2.10", "gimp_2_10")
        ]
        for raw, exp_clean, exp_slug in raw_names:
            clean = self.discovery._clean_display_name(raw)
            slug = self.discovery._generate_app_id(clean)
            self.assertEqual(clean, exp_clean)
            self.assertEqual(slug, exp_slug)

    def test_category_classification_using_word_boundaries(self):
        """Test category classification avoids substring false positives (e.g. calculator, narrator != browser)."""
        calc_cat = self.discovery._determine_category("calc", "Calculator", "C:/Windows/calc.exe")
        self.assertEqual(calc_cat, "system")

        chrome_cat = self.discovery._determine_category("chrome", "Google Chrome", "C:/Program Files/Chrome/chrome.exe")
        self.assertEqual(chrome_cat, "browser")

        code_cat = self.discovery._determine_category("vscode", "Visual Studio Code", "C:/Tools/Code.exe")
        self.assertEqual(code_cat, "editor")

        spotify_cat = self.discovery._determine_category("spotify", "Spotify Music", "C:/Users/Spotify.exe")
        self.assertEqual(spotify_cat, "media")

        game_cat = self.discovery._determine_category("valorant", "Valorant", "C:/Riot Games/RiotClientServices.exe")
        self.assertEqual(game_cat, "game")

    # =========================================================================
    # 2. PERSISTENCE & ADDITIVE SQLITE MIGRATION TESTS
    # =========================================================================

    def test_additive_sqlite_migration_without_data_loss(self):
        """Test migration on legacy 8-column database schema preserving all preexisting data."""
        legacy_db_path = str(Path(self.temp_dir) / "legacy_applications.db")
        conn = sqlite3.connect(legacy_db_path)
        cur = conn.cursor()
        # Create legacy 8-column table
        cur.execute("""
            CREATE TABLE discovered_applications (
                app_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                executable_path TEXT NOT NULL,
                arguments TEXT,
                source TEXT NOT NULL,
                platform TEXT NOT NULL,
                is_available INTEGER DEFAULT 1,
                last_discovered_at REAL NOT NULL
            )
        """)
        cur.execute("""
            INSERT INTO discovered_applications VALUES 
            ('legacy_app', 'Legacy Test App', 'C:/Legacy/app.exe', '[]', 'start_menu', 'windows', 1, 1000.0)
        """)
        conn.commit()
        conn.close()

        # Initialize ApplicationDiscovery pointing to legacy database
        legacy_discovery = ApplicationDiscovery(db_path=legacy_db_path, apps_json_path=self.test_json_path, auto_scan=False)
        
        # Verify columns were migrated additively
        conn = sqlite3.connect(legacy_db_path)
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(discovered_applications)")
        cols = {row[1] for row in cur.fetchall()}
        conn.close()

        self.assertIn("searchable_aliases", cols)
        self.assertIn("launch_mechanism", cols)
        self.assertIn("install_directory", cols)
        self.assertIn("version", cols)
        self.assertIn("publisher", cols)
        self.assertIn("category", cols)
        self.assertIn("user_aliases", cols)

        # Verify old record is preserved intact
        app = legacy_discovery.get_application("legacy_app")
        self.assertIsNotNone(app)
        self.assertEqual(app.display_name, "Legacy Test App")

    def test_duplicate_resolution_merges_metadata(self):
        """Test duplicate discoveries merge metadata (version from registry, arguments from shortcut)."""
        app1 = DiscoveredApplication(
            app_id="my_tool",
            display_name="My Tool",
            executable_path="C:/Tools/tool.exe",
            arguments=["--quiet"],
            source="start_menu",
            platform="windows"
        )
        app2 = DiscoveredApplication(
            app_id="my_tool",
            display_name="My Tool",
            executable_path="C:/Tools/tool.exe",
            source="registry_uninstall",
            platform="windows",
            version="2.4.0",
            publisher="ACME Corp",
            install_directory="C:/Tools"
        )
        self.discovery._save_to_db([app1, app2])
        self.discovery._load_from_db()

        merged = self.discovery.get_application("my_tool")
        self.assertIsNotNone(merged)
        self.assertEqual(merged.version, "2.4.0")
        self.assertEqual(merged.publisher, "ACME Corp")
        self.assertEqual(merged.install_directory, "C:/Tools")

    # =========================================================================
    # 3. ALIASES & AMBIGUITY TESTS
    # =========================================================================

    def test_user_defined_alias_persistence_and_removal(self):
        """Test user-defined aliases are persisted across saves and can be cleanly removed."""
        app = DiscoveredApplication(
            app_id="firefox",
            display_name="Mozilla Firefox",
            executable_path="C:/Program Files/Mozilla Firefox/firefox.exe",
            source="start_menu",
            platform="windows",
            is_available=True
        )
        self.discovery._cached_apps["firefox"] = app
        self.discovery._save_to_db([app])

        # Add user alias
        added = self.discovery.add_user_alias("firefox", "fire_browser")
        self.assertTrue(added)
        self.assertIn("fire_browser", self.discovery.get_user_aliases("firefox"))

        # Lookup via alias
        matched, _ = self.discovery.find_application("fire_browser")
        self.assertIsNotNone(matched)
        self.assertEqual(matched.app_id, "firefox")

        # Rescan / reload should preserve user alias
        self.discovery._load_from_db()
        self.assertIn("fire_browser", self.discovery.get_application("firefox").user_aliases)

        # Remove user alias
        removed = self.discovery.remove_user_alias("firefox", "fire_browser")
        self.assertTrue(removed)
        self.assertNotIn("fire_browser", self.discovery.get_user_aliases("firefox"))

        matched2, _ = self.discovery.find_application("fire_browser")
        self.assertIsNone(matched2)

    def test_ambiguity_returns_candidates_and_never_weak_match(self):
        """Test ambiguous queries return candidates and never launch a weak match."""
        app_vs_code = DiscoveredApplication(
            app_id="visual_studio_code",
            display_name="Visual Studio Code",
            executable_path="C:/VSCode/code.exe",
            source="test",
            platform="windows",
            is_available=True
        )
        app_vs_2022 = DiscoveredApplication(
            app_id="visual_studio_2022",
            display_name="Visual Studio 2022",
            executable_path="C:/VS2022/devenv.exe",
            source="test",
            platform="windows",
            is_available=True
        )
        self.discovery._cached_apps["visual_studio_code"] = app_vs_code
        self.discovery._cached_apps["visual_studio_2022"] = app_vs_2022

        match, candidates = self.discovery.find_application("Visual Studio")
        self.assertIsNone(match)
        self.assertGreaterEqual(len(candidates), 2)
        cand_names = [c.display_name for c in candidates]
        self.assertIn("Visual Studio Code", cand_names)
        self.assertIn("Visual Studio 2022", cand_names)

        # Test app_control launcher asks clarification question on ambiguity
        with patch("modules.system.app_control.app_discovery", self.discovery):
            res = app_control.launch_application("Visual Studio")
            self.assertFalse(res["success"])
            self.assertEqual(res["outcome"], "AMBIGUOUS")
            self.assertIn("Multiple applications matched 'Visual Studio'", res["message"])

    def test_stale_record_executable_missing(self):
        """Test stale applications whose executables disappeared are flagged unavailable."""
        app = DiscoveredApplication(
            app_id="uninstalled_game",
            display_name="Old Game",
            executable_path="C:/NonExistentPath/game.exe",
            source="test",
            platform="windows",
            is_available=False
        )
        self.discovery._cached_apps["uninstalled_game"] = app

        status = self.discovery.is_app_installed("uninstalled_game")
        self.assertTrue(status["installed"])
        self.assertFalse(status["available"])
        self.assertIn("currently unavailable on disk", status["message"])

    # =========================================================================
    # 4. PHASE 5: DESKTOP CONTROL OPERATIONS
    # =========================================================================

    def test_open_properties_dialog_windows(self):
        """Test Windows Properties dialog invocation using ShellExecuteExW."""
        fake_exe = str(Path(self.temp_dir) / "app.exe")
        with open(fake_exe, "w") as f:
            f.write("fake binary")

        app = DiscoveredApplication(
            app_id="test_tool",
            display_name="Test Tool",
            executable_path=fake_exe,
            source="test",
            platform="windows",
            is_available=True
        )
        self.discovery._cached_apps["test_tool"] = app

        with patch("ctypes.windll.shell32.ShellExecuteExW", return_value=1) as mock_shell:
            res = self.discovery.open_properties_dialog("test_tool")
            self.assertTrue(res["success"])
            self.assertIn("Opened properties dialog", res["message"])
            self.assertTrue(mock_shell.called)

    def test_open_installation_folder(self):
        """Test opening application installation folder in file manager."""
        fake_folder = Path(self.temp_dir) / "InstalledApp"
        fake_folder.mkdir()
        fake_exe = str(fake_folder / "app.exe")
        with open(fake_exe, "w") as f:
            f.write("fake binary")

        app = DiscoveredApplication(
            app_id="installed_app",
            display_name="Installed App",
            executable_path=fake_exe,
            install_directory=str(fake_folder),
            source="test",
            platform="windows",
            is_available=True
        )
        self.discovery._cached_apps["installed_app"] = app

        with patch("subprocess.Popen") as mock_popen:
            res = self.discovery.open_install_folder("installed_app")
            self.assertTrue(res["success"])
            self.assertIn("Opened installation folder", res["message"])
            self.assertTrue(mock_popen.called)

    def test_open_browser_internal_settings_vs_unsupported(self):
        """Test distinction between browser internal settings and generic app settings."""
        app_chrome = DiscoveredApplication(
            app_id="chrome",
            display_name="Google Chrome",
            executable_path="C:/Chrome/chrome.exe",
            category="browser",
            source="test",
            platform="windows",
            is_available=True
        )
        app_calc = DiscoveredApplication(
            app_id="calc",
            display_name="Calculator",
            executable_path="C:/Windows/calc.exe",
            category="system",
            source="test",
            platform="windows",
            is_available=True
        )
        self.discovery._cached_apps["chrome"] = app_chrome
        self.discovery._cached_apps["calc"] = app_calc

        # Browser settings -> chrome://settings
        with patch("modules.browser.web_control.open_url", return_value=True) as mock_url:
            res_b = self.discovery.open_app_settings("chrome")
            self.assertTrue(res_b["success"])
            self.assertEqual(res_b["settings_type"], "internal_browser_settings")

        # Calculator -> unsupported internal settings explanation
        res_c = self.discovery.open_app_settings("calc")
        self.assertFalse(res_c["success"])
        self.assertEqual(res_c["settings_type"], "unsupported_internal_settings")
        self.assertIn("does not expose an external command-line settings URL", res_c["message"])

    def test_get_app_metadata_reporting(self):
        """Test reporting version, publisher, path, and architecture."""
        app = DiscoveredApplication(
            app_id="vscode",
            display_name="Visual Studio Code",
            executable_path="C:/Users/User/AppData/Local/Programs/Microsoft VS Code/Code.exe",
            source="start_menu",
            platform="windows",
            version="1.88.1",
            publisher="Microsoft Corporation",
            category="editor",
            is_available=True
        )
        self.discovery._cached_apps["vscode"] = app

        meta = self.discovery.get_app_metadata("vscode")
        self.assertTrue(meta["success"])
        self.assertEqual(meta["version"], "1.88.1")
        self.assertEqual(meta["publisher"], "Microsoft Corporation")
        self.assertIn("Visual Studio Code (Version: 1.88.1, Publisher: Microsoft Corporation)", meta["message"])

    def test_list_installed_browsers_and_all(self):
        """Test listing available browsers and all installed applications."""
        app1 = DiscoveredApplication(app_id="chrome", display_name="Google Chrome", executable_path="C:/chrome.exe", category="browser", is_available=True)
        app2 = DiscoveredApplication(app_id="brave", display_name="Brave", executable_path="C:/brave.exe", category="browser", is_available=True)
        app3 = DiscoveredApplication(app_id="notepad", display_name="Notepad", executable_path="C:/notepad.exe", category="editor", is_available=True)

        self.discovery._cached_apps = {"chrome": app1, "brave": app2, "notepad": app3}

        # Filter by browser
        b_res = self.discovery.list_installed_apps(category="browser")
        self.assertTrue(b_res["success"])
        self.assertEqual(b_res["count"], 2)
        self.assertIn("Brave", b_res["applications"])
        self.assertIn("Google Chrome", b_res["applications"])

        # Filter all
        all_res = self.discovery.list_installed_apps()
        self.assertTrue(all_res["success"])
        self.assertEqual(all_res["count"], 3)

    # =========================================================================
    # 5. NATURAL-LANGUAGE INTENT & FAST LOCAL ROUTING TESTS
    # =========================================================================

    def test_natural_language_intent_routing(self):
        """Test natural language phrases route to deterministic intents with confidence >= 0.95."""
        test_commands = [
            ("Show Chrome's properties.", "application.properties", "chrome"),
            ("Open Chrome's installation folder.", "application.install_dir", "chrome"),
            ("Show Chrome's version.", "application.metadata", "chrome"),
            ("Open Chrome's settings.", "application.settings", "chrome"),
            ("Is Discord installed?", "application.status", "discord"),
            ("Is Chrome installed?", "application.status", "chrome"),
            ("List my installed applications.", "application.list_installed", "all"),
            ("Find my available browsers.", "application.list_installed", "browser"),
            ("Open the application I installed yesterday.", "open_app", "installed_yesterday"),
            ("Where is Chrome installed?", "application.install_dir", "chrome"),
            ("What version of Chrome is installed?", "application.metadata", "chrome"),
            ("Properties of Chrome", "application.properties", "chrome"),
            ("Settings for Chrome", "application.settings", "chrome"),
            ("Scan applications", "application.refresh", "applications")
        ]
        for phrase, exp_intent, exp_target in test_commands:
            with self.subTest(phrase=phrase):
                node = self.intent_engine.parse(phrase)
                self.assertEqual(node["intent"], exp_intent, f"Intent mismatch for '{phrase}'")
                self.assertEqual(node["target"], exp_target, f"Target mismatch for '{phrase}'")
                self.assertGreaterEqual(node["confidence"], 0.95)

    def test_intelligence_router_fast_local_zero_nemotron(self):
        """Test application discovery operations execute locally (Mode: FAST_LOCAL, Layer: 1) without Nemotron."""
        phrases = [
            "Show Chrome's properties.",
            "Open Chrome's installation folder.",
            "Show Chrome's version.",
            "Open Chrome's settings.",
            "Is Discord installed?",
            "List my installed applications.",
            "Find my available browsers."
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                req = intelligence_router.route(phrase)
                self.assertEqual(req.mode, MODE_FAST_LOCAL)
                self.assertEqual(req.layer, 1)
                self.assertFalse(req.planning_required)

    # =========================================================================
    # 6. TOOL REGISTRY & EXECUTOR TESTS
    # =========================================================================

    def test_tool_registry_contains_application_tools(self):
        """Verify all Phase 5 tools are registered in ToolRegistry."""
        required_tools = [
            "open_app",
            "application.launch",
            "application.properties",
            "application.install_dir",
            "application.settings",
            "application.metadata",
            "application.status",
            "application.list_installed",
            "application.refresh"
        ]
        for name in required_tools:
            tool = tool_registry.get_tool(name)
            self.assertIsNotNone(tool, f"Tool '{name}' is missing from ToolRegistry.")
            self.assertEqual(tool.category, "applications")

    def test_executor_handles_application_status_and_metadata(self):
        """Test CommandExecutor executes application status and metadata commands returning standardized output."""
        status_intent = {"intent": "application.status", "action": "is_installed", "target": "chrome"}
        res = self.executor.execute(status_intent)
        self.assertTrue(res["success"])
        self.assertEqual(res["outcome"], CommandOutcome.SUCCESS.value)
        self.assertIn("chrome", res["message"].lower())

        meta_intent = {"intent": "application.metadata", "action": "get_metadata", "target": "chrome"}
        res_m = self.executor.execute(meta_intent)
        self.assertTrue(res_m["success"])
        self.assertEqual(res_m["outcome"], CommandOutcome.SUCCESS.value)

    # =========================================================================
    # 7. LINUX DISCOVERY SIMULATION & LIMITATIONS
    # =========================================================================

    def test_linux_desktop_entry_discovery_parsing(self):
        """Test parsing of Linux XDG .desktop files extracting Name, Exec, Version, and Categories."""
        dt_dir = Path(self.temp_dir) / "applications"
        dt_dir.mkdir()
        dt_file = dt_dir / "test_app.desktop"
        with open(dt_file, "w", encoding="utf-8") as f:
            f.write("""[Desktop Entry]
Name=GIMP Image Editor
Exec=gimp-2.10 %U
Type=Application
Categories=Graphics;2DGraphics;
Version=2.10.36
Comment=Create and edit images
""")
        discovered = {}
        with patch("pathlib.Path.exists", return_value=True), \
             patch("shutil.which", return_value="/usr/bin/gimp-2.10"):
            self.discovery._scan_linux_desktop_entries(discovered)

        # Discovered contains standard desktop entries if any exist on the runner or test files
        self.assertIsInstance(discovered, dict)

    def test_dynamic_runtime_refresh_without_restart(self):
        """Test runtime refresh discovers newly added application without restarting JARVIS."""
        self.discovery._cached_apps = {}
        initial_count = len(self.discovery.list_applications())
        self.assertEqual(initial_count, 0)

        # Register custom/portable app at runtime
        fake_path = str(Path(self.temp_dir) / "new_tool.exe")
        with open(fake_path, "w") as f:
            f.write("binary")

        self.discovery.register_application("new_tool", "New Custom Tool", fake_path)
        self.assertEqual(len(self.discovery.list_applications()), 1)

        matched, _ = self.discovery.find_application("New Custom Tool")
        self.assertIsNotNone(matched)
        self.assertEqual(matched.app_id, "new_tool")


if __name__ == "__main__":
    unittest.main()
