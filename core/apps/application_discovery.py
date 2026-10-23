"""Platform-Aware Universal Application Discovery, Dynamic Registry and Desktop Control Service for JARVIS.

Discovers native, packaged, and portable applications on Windows 11 and Ubuntu Linux,
normalizes application records, caches catalogues in SQLite with additive schema migration,
provides safe lookup, disambiguation, properties dialog, installation folder reveal,
settings, version metadata extraction, and runtime refresh.
"""

import os
import sys
import glob
import json
import time
import shutil
import sqlite3
import logging
import threading
import subprocess
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger("Jarvis.AppDiscovery")


@dataclass
class DiscoveredApplication:
    """Normalized, persistent record of an installed application."""
    app_id: str
    display_name: str
    executable_path: str
    arguments: List[str] = field(default_factory=list)
    source: str = "unknown"  # start_menu, registry_uninstall, registry_app_paths, packaged_app, desktop_entry, config, path, user
    platform: str = "windows"  # windows, linux, darwin
    is_available: bool = True
    last_discovered_at: float = field(default_factory=time.time)

    # Phase 2 extensions
    searchable_aliases: List[str] = field(default_factory=list)
    launch_mechanism: str = "executable"  # executable, uwp, desktop_entry, uri, shell_execute
    install_directory: Optional[str] = None
    version: Optional[str] = None
    publisher: Optional[str] = None
    category: Optional[str] = None  # browser, editor, media, game, utility, system
    user_aliases: List[str] = field(default_factory=list)
    discovery_source: str = "unknown"
    last_verification_timestamp: float = field(default_factory=time.time)
    availability_status: bool = True

    def __post_init__(self):
        # Synchronize backward-compatible aliases
        if self.discovery_source == "unknown" and self.source != "unknown":
            self.discovery_source = self.source
        elif self.source == "unknown" and self.discovery_source != "unknown":
            self.source = self.discovery_source

        if self.last_verification_timestamp == 0.0 or self.last_verification_timestamp == self.last_discovered_at:
            self.last_verification_timestamp = self.last_discovered_at
        else:
            self.last_discovered_at = self.last_verification_timestamp

        self.availability_status = bool(self.is_available)

    @property
    def os(self) -> str:
        return self.platform

    def to_dict(self) -> Dict[str, Any]:
        return {
            "app_id": self.app_id,
            "display_name": self.display_name,
            "executable_path": self.executable_path,
            "arguments": json.dumps(self.arguments),
            "source": self.source,
            "platform": self.platform,
            "is_available": 1 if self.is_available else 0,
            "last_discovered_at": self.last_discovered_at,
            "searchable_aliases": json.dumps(self.searchable_aliases),
            "launch_mechanism": self.launch_mechanism,
            "install_directory": self.install_directory or "",
            "version": self.version or "",
            "publisher": self.publisher or "",
            "category": self.category or "utility",
            "user_aliases": json.dumps(self.user_aliases),
            "discovery_source": self.discovery_source,
            "last_verification_timestamp": self.last_verification_timestamp,
            "availability_status": 1 if self.is_available else 0,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscoveredApplication":
        def _parse_list(val):
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                try:
                    res = json.loads(val)
                    return res if isinstance(res, list) else []
                except Exception:
                    return []
            return []

        args = _parse_list(data.get("arguments", "[]"))
        search_aliases = _parse_list(data.get("searchable_aliases", "[]"))
        u_aliases = _parse_list(data.get("user_aliases", "[]"))

        src = data.get("source") or data.get("discovery_source") or "unknown"
        plat = data.get("platform") or data.get("os") or "windows"
        avail = bool(data.get("is_available", data.get("availability_status", 1)))
        ts = float(data.get("last_discovered_at", data.get("last_verification_timestamp", time.time())))

        return cls(
            app_id=data["app_id"],
            display_name=data["display_name"],
            executable_path=data.get("executable_path", ""),
            arguments=args,
            source=src,
            platform=plat,
            is_available=avail,
            last_discovered_at=ts,
            searchable_aliases=search_aliases,
            launch_mechanism=data.get("launch_mechanism", "executable"),
            install_directory=data.get("install_directory") or None,
            version=data.get("version") or None,
            publisher=data.get("publisher") or None,
            category=data.get("category") or "utility",
            user_aliases=u_aliases,
            discovery_source=src,
            last_verification_timestamp=ts,
            availability_status=avail
        )


class ApplicationDiscovery:
    """Discovers, normalizes, caches, and resolves installed desktop applications."""

    SEMANTIC_ALIASES = {
        "code editor": ["vscode", "code", "vscodium", "sublime_text", "notepad++", "antigravity"],
        "my code editor": ["vscode", "code", "vscodium", "sublime_text", "antigravity"],
        "3d editor": ["blender", "maya", "3dsmax"],
        "my 3d editor": ["blender"],
        "text editor": ["notepad", "gedit", "kate", "notepad++", "sublime_text"],
        "music": ["spotify", "apple_music", "vlc"],
        "music player": ["spotify", "vlc"],
        "web browser": ["chrome", "google_chrome", "firefox", "msedge", "brave", "opera"],
        "browser": ["chrome", "google_chrome", "firefox", "msedge", "brave", "opera"],
        "terminal": ["powershell", "cmd", "wt", "bash", "gnome-terminal"],
        "calculator": ["calc", "calculator", "gnome-calculator"],
        "file manager": ["explorer", "nautilus", "dolphin", "thunar"],
    }

    def __init__(self, db_path: Optional[str] = None, apps_json_path: Optional[str] = None, auto_scan: bool = True):
        base_dir = Path(__file__).parent.parent.parent
        self.db_path = db_path or str(base_dir / "logs" / "applications.db")
        self.apps_json_path = apps_json_path or str(base_dir / "config" / "applications.json")
        self.platform_name = "windows" if sys.platform.startswith("win") else "linux"
        self._cached_apps: Dict[str, DiscoveredApplication] = {}
        self._last_scan_time: float = 0.0
        self._stop_watcher = False
        self._watcher_thread: Optional[threading.Thread] = None

        self._init_db()
        self._load_from_db()
        if auto_scan and not self._cached_apps:
            self.scan(force=True)

    def _init_db(self):
        """Initializes SQLite schema with additive migrations to avoid data loss."""
        conn = None
        try:
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS discovered_applications (
                    app_id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    executable_path TEXT NOT NULL,
                    arguments TEXT,
                    source TEXT NOT NULL,
                    platform TEXT NOT NULL,
                    is_available INTEGER DEFAULT 1,
                    last_discovered_at REAL NOT NULL,
                    searchable_aliases TEXT,
                    launch_mechanism TEXT,
                    install_directory TEXT,
                    version TEXT,
                    publisher TEXT,
                    category TEXT,
                    user_aliases TEXT
                )
            """)

            # Additive migration: check existing columns and alter table if missing
            cursor.execute("PRAGMA table_info(discovered_applications)")
            existing_cols = {row[1] for row in cursor.fetchall()}
            migrations = [
                ("searchable_aliases", "TEXT"),
                ("launch_mechanism", "TEXT"),
                ("install_directory", "TEXT"),
                ("version", "TEXT"),
                ("publisher", "TEXT"),
                ("category", "TEXT"),
                ("user_aliases", "TEXT")
            ]
            for col_name, col_type in migrations:
                if col_name not in existing_cols:
                    logger.info(f"Applying additive migration to applications.db: adding {col_name} ({col_type})")
                    cursor.execute(f"ALTER TABLE discovered_applications ADD COLUMN {col_name} {col_type}")

            conn.commit()
        except Exception as e:
            logger.error(f"Failed to initialize applications.db: {e}")
        finally:
            if conn:
                conn.close()

    def _load_from_db(self):
        """Loads cached applications from SQLite."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM discovered_applications")
            rows = cursor.fetchall()
            for r in rows:
                app = DiscoveredApplication.from_dict(dict(r))
                self._cached_apps[app.app_id] = app
            logger.info(f"Loaded {len(self._cached_apps)} applications from database cache.")
        except Exception as e:
            logger.warning(f"Failed to load cached applications: {e}")
        finally:
            if conn:
                conn.close()

    def _save_to_db(self, apps: List[DiscoveredApplication]):
        """Persists discovered applications into SQLite without overwriting user customizations."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            for app in apps:
                d = app.to_dict()
                cursor.execute("""
                    INSERT INTO discovered_applications 
                    (app_id, display_name, executable_path, arguments, source, platform, is_available, 
                     last_discovered_at, searchable_aliases, launch_mechanism, install_directory, 
                     version, publisher, category, user_aliases)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(app_id) DO UPDATE SET
                        display_name = excluded.display_name,
                        executable_path = excluded.executable_path,
                        arguments = excluded.arguments,
                        source = excluded.source,
                        platform = excluded.platform,
                        is_available = excluded.is_available,
                        last_discovered_at = excluded.last_discovered_at,
                        searchable_aliases = excluded.searchable_aliases,
                        launch_mechanism = excluded.launch_mechanism,
                        install_directory = excluded.install_directory,
                        version = CASE WHEN excluded.version != '' THEN excluded.version ELSE discovered_applications.version END,
                        publisher = CASE WHEN excluded.publisher != '' THEN excluded.publisher ELSE discovered_applications.publisher END,
                        category = excluded.category,
                        user_aliases = excluded.user_aliases
                """, (
                    d["app_id"], d["display_name"], d["executable_path"],
                    d["arguments"], d["source"], d["platform"],
                    d["is_available"], d["last_discovered_at"],
                    d["searchable_aliases"], d["launch_mechanism"],
                    d["install_directory"], d["version"],
                    d["publisher"], d["category"], d["user_aliases"]
                ))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to save discovered applications to DB: {e}")
        finally:
            if conn:
                conn.close()

    # =========================================================================
    # METADATA & HELPER UTILITIES
    # =========================================================================

    def _determine_category(self, app_id: str, display_name: str, exec_path: str = "") -> str:
        """Determines coarse functional category for the application using word boundaries."""
        import re
        comb = f"{app_id} {display_name} {exec_path}".lower()
        if re.search(r"\b(terminal|powershell|cmd|explorer|calc|calculator|taskmgr|taskmanager|settings|control|system)\b", comb):
            return "system"
        if re.search(r"\b(chrome|google chrome|edge|msedge|firefox|brave|opera|vivaldi|chromium|tor browser)\b", comb):
            return "browser"
        if re.search(r"\b(code|vscode|vs code|studio|pycharm|sublime|editor|notepad|gedit|vim|antigravity|cursor|intellij)\b", comb):
            return "editor"
        if re.search(r"\b(spotify|music|media player|vlc|player|audio|itunes|obs studio|sound)\b", comb):
            return "media"
        if re.search(r"\b(game|steam|valorant|riot|epic games|minecraft|ea desktop|battle\.net)\b", comb):
            return "game"
        if "browser" in comb:
            return "browser"
        return "utility"

    def _generate_aliases(self, app_id: str, display_name: str, category: str) -> List[str]:
        """Generates searchable aliases and abbreviations."""
        aliases = set()
        clean_disp = display_name.lower().strip()
        clean_id = app_id.lower().strip()
        aliases.add(clean_disp)
        aliases.add(clean_id)

        words = clean_disp.split()
        if len(words) > 1:
            aliases.add(words[-1])
            if "visual studio code" in clean_disp:
                aliases.update(["vscode", "vs code", "code", "vsc"])
            elif "google chrome" in clean_disp:
                aliases.update(["chrome", "google_chrome"])
            elif "microsoft edge" in clean_disp:
                aliases.update(["edge", "msedge"])
            elif "file explorer" in clean_disp:
                aliases.update(["explorer", "files"])

        if category == "browser":
            aliases.add("browser")
            aliases.add("web browser")
        elif category == "editor":
            aliases.add("editor")
            aliases.add("code editor")

        return sorted(list(aliases))

    def _clean_display_name(self, name: str) -> str:
        """Cleans up names by removing version numbers, architectures, and file extensions."""
        cleaned = name.strip()
        for ext in [".exe", ".lnk", ".desktop"]:
            if cleaned.lower().endswith(ext):
                cleaned = cleaned[:-len(ext)]
        for suffix in [" (x64)", " (x86)", " 64-bit", " 32-bit", " - Shortcut"]:
            if cleaned.endswith(suffix):
                cleaned = cleaned[:-len(suffix)]
        return cleaned.strip()

    def _generate_app_id(self, name: str) -> str:
        """Generates a stable, lowercase slug for an application name."""
        clean = self._clean_display_name(name).lower()
        slug = "".join(c if c.isalnum() else "_" for c in clean).strip("_")
        while "__" in slug:
            slug = slug.replace("__", "_")
        return slug or "app"

    # =========================================================================
    # PLATFORM DISCOVERY SCANNERS
    # =========================================================================

    def scan(self, force: bool = False) -> List[DiscoveredApplication]:
        """Performs a platform-aware scan for installed applications without running them."""
        now = time.time()
        if not force and (now - self._last_scan_time < 30.0) and self._cached_apps:
            return list(self._cached_apps.values())

        logger.info(f"Scanning installed applications for platform: {self.platform_name}...")
        discovered: Dict[str, DiscoveredApplication] = {}

        # 1. Configured static applications
        self._scan_configured_applications(discovered)

        # 2. Platform-specific scanning
        if self.platform_name == "windows":
            self._scan_windows_start_menu(discovered)
            self._scan_windows_registry_app_paths(discovered)
            self._scan_windows_registry_uninstall(discovered)
            self._scan_windows_special_launchers(discovered)
            self._scan_windows_packaged_apps(discovered)
            self._scan_windows_known_directories(discovered)
        else:
            self._scan_linux_desktop_entries(discovered)
            self._scan_linux_path_executables(discovered)
            self._scan_linux_standard_directories(discovered)

        # 3. Filter stale / invalid entries and populate metadata
        valid_apps = []
        for app in discovered.values():
            # Validate launch mechanism / executable path
            if app.launch_mechanism == "uwp":
                app.is_available = True
            else:
                p = Path(app.executable_path)
                if p.exists() or shutil.which(app.executable_path):
                    app.is_available = True
                else:
                    app.is_available = False

            if not app.install_directory and app.executable_path and Path(app.executable_path).exists():
                app.install_directory = str(Path(app.executable_path).parent)

            # Extract PE metadata on Windows if missing
            if self.platform_name == "windows" and (not app.version or not app.publisher):
                if app.executable_path and Path(app.executable_path).exists() and app.executable_path.lower().endswith(".exe"):
                    pe_ver, pe_pub = self._extract_windows_exe_metadata(app.executable_path)
                    if pe_ver and not app.version:
                        app.version = pe_ver
                    if pe_pub and not app.publisher:
                        app.publisher = pe_pub

            # Assign category & aliases
            app.category = app.category or self._determine_category(app.app_id, app.display_name, app.executable_path)
            auto_aliases = self._generate_aliases(app.app_id, app.display_name, app.category)
            merged_searchable = sorted(list(set(app.searchable_aliases + auto_aliases)))
            app.searchable_aliases = merged_searchable

            # Preserve existing user aliases from memory cache if available
            if app.app_id in self._cached_apps:
                old_app = self._cached_apps[app.app_id]
                if old_app.user_aliases:
                    app.user_aliases = old_app.user_aliases

            valid_apps.append(app)
            self._cached_apps[app.app_id] = app

        self._save_to_db(valid_apps)
        self._last_scan_time = now
        logger.info(f"Scan complete. Discovered {len(valid_apps)} applications ({sum(1 for a in valid_apps if a.is_available)} available).")
        return valid_apps

    def refresh(self) -> int:
        """On-demand safe refresh mechanism for runtime updates without restart."""
        apps = self.scan(force=True)
        return len(apps)

    def start_background_watcher(self, interval_sec: float = 300.0):
        """Starts a periodic background watcher thread keeping discovery off the GUI and audio critical paths."""
        if self._watcher_thread and self._watcher_thread.is_alive():
            return

        self._stop_watcher = False

        def _worker():
            logger.info("ApplicationDiscovery background periodic watcher started.")
            while not self._stop_watcher:
                time.sleep(interval_sec)
                if self._stop_watcher:
                    break
                try:
                    self.scan(force=True)
                except Exception as e:
                    logger.debug(f"Background application reconciliation error: {e}")

        self._watcher_thread = threading.Thread(target=_worker, name="JarvisAppDiscoveryWatcher", daemon=True)
        self._watcher_thread.start()

    def stop_background_watcher(self):
        """Stops the periodic background watcher thread."""
        self._stop_watcher = True

    # -------------------------------------------------------------------------
    # Windows Discovery Mechanisms
    # -------------------------------------------------------------------------

    def _extract_windows_exe_metadata(self, exe_path: str) -> Tuple[Optional[str], Optional[str]]:
        """Extracts FileVersion and CompanyName/Publisher from PE executable resources."""
        if not exe_path or not sys.platform.startswith("win"):
            return None, None
        try:
            import win32api
            p = os.path.abspath(exe_path)
            if not os.path.exists(p):
                return None, None

            version_str = None
            publisher_str = None

            try:
                info = win32api.GetFileVersionInfo(p, "\\")
                ms = info.get('FileVersionMS', 0)
                ls = info.get('FileVersionLS', 0)
                if ms or ls:
                    version_str = f"{win32api.HIWORD(ms)}.{win32api.LOWORD(ms)}.{win32api.HIWORD(ls)}.{win32api.LOWORD(ls)}"
            except Exception:
                pass

            try:
                trans = win32api.GetFileVersionInfo(p, '\\VarFileInfo\\Translation')
                if trans:
                    lang, codepage = trans[0]
                    str_info = f'\\StringFileInfo\\{lang:04x}{codepage:04x}\\'
                    pub = win32api.GetFileVersionInfo(p, str_info + 'CompanyName')
                    if pub and isinstance(pub, str) and pub.strip():
                        publisher_str = pub.strip()
            except Exception:
                pass

            return version_str, publisher_str
        except Exception:
            return None, None

    def _parse_windows_lnk(self, lnk_path: str) -> Tuple[Optional[str], List[str]]:
        """Safely parses a Windows Shell Link (.lnk) extracting target path and arguments."""
        try:
            import win32com.client
            shell = win32com.client.Dispatch("WScript.Shell")
            shortcut = shell.CreateShortcut(lnk_path)
            target = shortcut.TargetPath
            raw_args = shortcut.Arguments
            import shlex
            args = shlex.split(raw_args) if raw_args else []
            if target and Path(target).exists():
                return target, args
        except Exception:
            pass

        try:
            with open(lnk_path, "rb") as f:
                content = f.read(4096)
            if len(content) < 0x4C or content[:4] != b"\x4C\x00\x00\x00":
                return None, []
            flags = int.from_bytes(content[0x14:0x18], "little")
            has_id_list = bool(flags & 0x01)
            has_link_info = bool(flags & 0x02)
            offset = 0x4C
            if has_id_list:
                if len(content) < offset + 2:
                    return None, []
                id_list_size = int.from_bytes(content[offset:offset+2], "little")
                offset += 2 + id_list_size
            if has_link_info and len(content) > offset + 4:
                info_len = int.from_bytes(content[offset:offset+4], "little")
                local_base_offset = int.from_bytes(content[offset+0x10:offset+0x14], "little")
                if local_base_offset and offset + local_base_offset < len(content):
                    target_bytes = content[offset+local_base_offset:min(len(content), offset+info_len)]
                    target_str = target_bytes.split(b"\x00")[0].decode("latin1", errors="ignore")
                    if target_str and Path(target_str).exists():
                        return target_str, []
        except Exception:
            pass
        return None, []

    def _scan_windows_start_menu(self, discovered: Dict[str, DiscoveredApplication]):
        """Scans Start Menu folders for application shortcuts."""
        search_dirs = []
        appdata = os.environ.get("APPDATA")
        if appdata:
            search_dirs.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
        progdata = os.environ.get("ProgramData")
        if progdata:
            search_dirs.append(Path(progdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

        for s_dir in search_dirs:
            if not s_dir.exists():
                continue
            for lnk_file in s_dir.rglob("*.lnk"):
                try:
                    file_name = lnk_file.stem
                    name_lower = file_name.lower()
                    if any(bad in name_lower for bad in ["uninstall", "remove", "help", "readme", "documentation", "manual"]):
                        continue

                    target_exe, shortcut_args = self._parse_windows_lnk(str(lnk_file))
                    exec_path = target_exe if (target_exe and Path(target_exe).exists()) else str(lnk_file)
                    display_name = self._clean_display_name(file_name)
                    app_id = self._generate_app_id(display_name)

                    if app_id not in discovered:
                        discovered[app_id] = DiscoveredApplication(
                            app_id=app_id,
                            display_name=display_name,
                            executable_path=exec_path,
                            arguments=shortcut_args or [],
                            source="start_menu",
                            platform="windows",
                            launch_mechanism="executable" if exec_path.lower().endswith(".exe") else "shell_execute",
                            install_directory=str(Path(exec_path).parent) if Path(exec_path).exists() else None
                        )
                except Exception as e:
                    logger.debug(f"Error parsing shortcut {lnk_file}: {e}")

    def _scan_windows_special_launchers(self, discovered: Dict[str, DiscoveredApplication]):
        """Discovers games and specialized launchers with structured launch arguments."""
        try:
            riot_installs = Path(os.environ.get("ProgramData", "C:/ProgramData")) / "Riot Games" / "RiotClientInstalls.json"
            if riot_installs.exists():
                with open(riot_installs, "r", encoding="utf-8") as f:
                    rdata = json.load(f)
                rc_exe = rdata.get("rc_live") or rdata.get("rc_default")
                if not rc_exe and "associated_client" in rdata:
                    for _, client_p in rdata["associated_client"].items():
                        if client_p and Path(client_p).exists():
                            rc_exe = client_p
                            break
                if rc_exe and Path(rc_exe).exists():
                    discovered["valorant"] = DiscoveredApplication(
                        app_id="valorant",
                        display_name="Valorant",
                        executable_path=str(rc_exe),
                        arguments=["--launch-product=valorant", "--launch-patchline=live"],
                        source="riot_client_installs",
                        platform="windows",
                        category="game",
                        launch_mechanism="executable",
                        install_directory=str(Path(rc_exe).parent)
                    )
        except Exception as e:
            logger.debug(f"Special launcher discovery (Riot) failed: {e}")

    def _scan_windows_registry_app_paths(self, discovered: Dict[str, DiscoveredApplication]):
        """Scans Windows Registry App Paths."""
        try:
            import winreg
        except ImportError:
            return

        roots = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths")
        ]

        for hkey, subkey in roots:
            try:
                with winreg.OpenKey(hkey, subkey) as key:
                    num_subkeys = winreg.QueryInfoKey(key)[0]
                    for i in range(num_subkeys):
                        try:
                            app_key_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, app_key_name) as app_key:
                                raw_path, _ = winreg.QueryValueEx(app_key, "")
                                if raw_path:
                                    clean_p = raw_path.strip('\"')
                                    if Path(clean_p).exists() and clean_p.lower().endswith(".exe"):
                                        disp_name = self._clean_display_name(app_key_name)
                                        app_id = self._generate_app_id(disp_name)
                                        if app_id not in discovered or discovered[app_id].source != "start_menu":
                                            discovered[app_id] = DiscoveredApplication(
                                                app_id=app_id,
                                                display_name=disp_name,
                                                executable_path=clean_p,
                                                source="registry_app_paths",
                                                platform="windows",
                                                launch_mechanism="executable",
                                                install_directory=str(Path(clean_p).parent)
                                            )
                        except OSError:
                            continue
            except OSError:
                continue

    def _scan_windows_registry_uninstall(self, discovered: Dict[str, DiscoveredApplication]):
        """Scans Windows Registry Uninstall keys for installed software metadata and executables."""
        try:
            import winreg
        except ImportError:
            return

        roots = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")
        ]

        for hkey, subkey in roots:
            try:
                with winreg.OpenKey(hkey, subkey) as key:
                    num_subkeys = winreg.QueryInfoKey(key)[0]
                    for i in range(num_subkeys):
                        try:
                            sub_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, sub_name) as app_key:
                                disp_name = None
                                try:
                                    disp_name, _ = winreg.QueryValueEx(app_key, "DisplayName")
                                except OSError:
                                    pass

                                if not disp_name or not isinstance(disp_name, str):
                                    continue

                                clean_disp = self._clean_display_name(disp_name)
                                if any(bad in clean_disp.lower() for bad in ["update", "redistributable", "sdk", "runtime", "driver"]):
                                    continue

                                app_id = self._generate_app_id(clean_disp)

                                # Extract version, publisher, install location
                                ver_str = None
                                pub_str = None
                                install_loc = None
                                try:
                                    ver_str, _ = winreg.QueryValueEx(app_key, "DisplayVersion")
                                except OSError:
                                    pass
                                try:
                                    pub_str, _ = winreg.QueryValueEx(app_key, "Publisher")
                                except OSError:
                                    pass
                                try:
                                    install_loc, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                except OSError:
                                    pass

                                # If app already discovered from start menu, enrich its metadata
                                if app_id in discovered:
                                    if ver_str and not discovered[app_id].version:
                                        discovered[app_id].version = str(ver_str).strip()
                                    if pub_str and not discovered[app_id].publisher:
                                        discovered[app_id].publisher = str(pub_str).strip()
                                    if install_loc and not discovered[app_id].install_directory:
                                        discovered[app_id].install_directory = str(install_loc).strip('\"')
                                    continue

                                # Probe executable from DisplayIcon or InstallLocation
                                exec_path = None
                                try:
                                    icon, _ = winreg.QueryValueEx(app_key, "DisplayIcon")
                                    if icon:
                                        icon_p = icon.split(",")[0].strip('\"')
                                        if Path(icon_p).exists() and icon_p.lower().endswith(".exe"):
                                            exec_path = icon_p
                                except OSError:
                                    pass

                                if not exec_path and install_loc and Path(install_loc).is_dir():
                                    for candidate in Path(install_loc).glob("*.exe"):
                                        if candidate.is_file() and not candidate.name.lower().startswith("unins"):
                                            exec_path = str(candidate)
                                            break

                                if exec_path and Path(exec_path).exists():
                                    discovered[app_id] = DiscoveredApplication(
                                        app_id=app_id,
                                        display_name=clean_disp,
                                        executable_path=exec_path,
                                        source="registry_uninstall",
                                        platform="windows",
                                        version=str(ver_str).strip() if ver_str else None,
                                        publisher=str(pub_str).strip() if pub_str else None,
                                        install_directory=str(install_loc).strip('\"') if install_loc else str(Path(exec_path).parent),
                                        launch_mechanism="executable"
                                    )
                        except OSError:
                            continue
            except OSError:
                continue

    def _scan_windows_packaged_apps(self, discovered: Dict[str, DiscoveredApplication]):
        """Discovers Windows packaged Store/UWP apps using App execution aliases in WindowsApps."""
        local_app = os.environ.get("LOCALAPPDATA")
        if not local_app:
            return
        wapps_dir = Path(local_app) / "Microsoft" / "WindowsApps"
        if not wapps_dir.exists():
            return

        for alias_exe in wapps_dir.glob("*.exe"):
            try:
                name = alias_exe.stem
                if name.lower().endswith("_alias"):
                    name = name[:-6]
                if any(bad in name.lower() for bad in ["host", "helper", "elevated", "mcp"]):
                    continue
                disp_name = self._clean_display_name(name)
                app_id = self._generate_app_id(disp_name)
                if app_id not in discovered:
                    discovered[app_id] = DiscoveredApplication(
                        app_id=app_id,
                        display_name=disp_name,
                        executable_path=str(alias_exe),
                        source="packaged_app",
                        platform="windows",
                        launch_mechanism="uwp",
                        install_directory=str(alias_exe.parent)
                    )
            except Exception as e:
                logger.debug(f"Error scanning packaged app {alias_exe}: {e}")

    def _scan_windows_known_directories(self, discovered: Dict[str, DiscoveredApplication]):
        """Targeted discovery for portable and user-installed programs in standard locations without full disk scan."""
        local_app = os.environ.get("LOCALAPPDATA")
        target_roots = []
        if local_app:
            target_roots.append(Path(local_app) / "Programs")
        for tool_dir in ["C:/Tools", "C:/PortableApps"]:
            if Path(tool_dir).exists():
                target_roots.append(Path(tool_dir))

        for root in target_roots:
            if not root.exists():
                continue
            for sub in root.iterdir():
                if sub.is_dir():
                    for exe in sub.glob("*.exe"):
                        if exe.is_file() and not exe.name.lower().startswith("unins"):
                            disp_name = self._clean_display_name(sub.name)
                            app_id = self._generate_app_id(disp_name)
                            if app_id not in discovered:
                                discovered[app_id] = DiscoveredApplication(
                                    app_id=app_id,
                                    display_name=disp_name,
                                    executable_path=str(exe),
                                    source="known_directory",
                                    platform="windows",
                                    install_directory=str(sub),
                                    launch_mechanism="executable"
                                )
                            break

    # -------------------------------------------------------------------------
    # Linux Discovery Mechanisms
    # -------------------------------------------------------------------------

    def _scan_linux_desktop_entries(self, discovered: Dict[str, DiscoveredApplication]):
        """Scans Linux .desktop entry files."""
        dirs = [
            Path("/usr/share/applications"),
            Path("/usr/local/share/applications"),
            Path.home() / ".local" / "share" / "applications",
            Path("/var/lib/snapd/desktop/applications"),
            Path("/var/lib/flatpak/exports/share/applications")
        ]
        for d in dirs:
            if not d.exists():
                continue
            for dt_file in d.glob("*.desktop"):
                try:
                    name, exec_cmd, no_display, comment, categories, ver = None, None, False, None, None, None
                    with open(dt_file, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("Name=") and not name:
                                name = line[5:].strip()
                            elif line.startswith("Exec=") and not exec_cmd:
                                exec_cmd = line[5:].strip()
                            elif line.startswith("NoDisplay=true"):
                                no_display = True
                            elif line.startswith("Comment=") and not comment:
                                comment = line[8:].strip()
                            elif line.startswith("Categories=") and not categories:
                                categories = line[11:].strip()
                            elif line.startswith("Version=") and not ver:
                                ver = line[8:].strip()

                    if no_display or not name or not exec_cmd:
                        continue

                    clean_exec = exec_cmd.split()[0].strip('\"')
                    resolved_exec = shutil.which(clean_exec) or clean_exec
                    if Path(resolved_exec).exists() or shutil.which(clean_exec):
                        app_id = self._generate_app_id(name)
                        if app_id not in discovered:
                            discovered[app_id] = DiscoveredApplication(
                                app_id=app_id,
                                display_name=self._clean_display_name(name),
                                executable_path=resolved_exec,
                                source="desktop_entry",
                                platform="linux",
                                launch_mechanism="desktop_entry",
                                version=ver,
                                install_directory=str(Path(resolved_exec).parent) if Path(resolved_exec).exists() else None
                            )
                except Exception as e:
                    logger.debug(f"Error parsing desktop file {dt_file}: {e}")

    def _scan_linux_path_executables(self, discovered: Dict[str, DiscoveredApplication]):
        """Checks common Linux software via PATH."""
        common = [
            ("blender", "Blender"),
            ("code", "Visual Studio Code"),
            ("google-chrome", "Google Chrome"),
            ("firefox", "Firefox"),
            ("brave-browser", "Brave"),
            ("spotify", "Spotify"),
            ("vlc", "VLC Media Player"),
            ("gimp", "GIMP"),
            ("steam", "Steam"),
            ("nautilus", "Files"),
            ("gnome-calculator", "Calculator"),
            ("gnome-terminal", "Terminal")
        ]
        for bin_name, disp in common:
            p = shutil.which(bin_name)
            if p:
                app_id = self._generate_app_id(disp)
                if app_id not in discovered:
                    discovered[app_id] = DiscoveredApplication(
                        app_id=app_id,
                        display_name=disp,
                        executable_path=p,
                        source="path",
                        platform="linux",
                        launch_mechanism="executable",
                        install_directory=str(Path(p).parent)
                    )

    def _scan_linux_standard_directories(self, discovered: Dict[str, DiscoveredApplication]):
        """Checks standard Linux portable AppImage folders."""
        for app_dir in [Path.home() / "Applications", Path.home() / ".local" / "bin"]:
            if app_dir.exists():
                for item in app_dir.glob("*.AppImage"):
                    if item.is_file() and os.access(item, os.X_OK):
                        disp = self._clean_display_name(item.stem)
                        app_id = self._generate_app_id(disp)
                        if app_id not in discovered:
                            discovered[app_id] = DiscoveredApplication(
                                app_id=app_id,
                                display_name=disp,
                                executable_path=str(item),
                                source="portable_appimage",
                                platform="linux",
                                launch_mechanism="executable",
                                install_directory=str(item.parent)
                            )

    # -------------------------------------------------------------------------
    # Static Configuration Scanning
    # -------------------------------------------------------------------------

    def _scan_configured_applications(self, discovered: Dict[str, DiscoveredApplication]):
        """Loads configured applications from applications.json."""
        p = Path(self.apps_json_path)
        if not p.exists():
            return
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, info in data.items():
                target_exec = info.get(self.platform_name) or info.get("windows" if self.platform_name == "windows" else "linux")
                if not target_exec:
                    continue
                resolved = shutil.which(target_exec) or target_exec
                aliases = info.get("aliases", [])
                disp = aliases[0].title() if aliases else key.title()
                app_id = self._generate_app_id(key)
                discovered[app_id] = DiscoveredApplication(
                    app_id=app_id,
                    display_name=disp,
                    executable_path=resolved,
                    source="config",
                    platform=self.platform_name,
                    searchable_aliases=aliases,
                    launch_mechanism="executable"
                )
        except Exception as e:
            logger.warning(f"Failed to load applications.json in discovery: {e}")

    # =========================================================================
    # CATALOGUE QUERYING, DISAMBIGUATION & USER ALIASES
    # =========================================================================

    def list_applications(self, available_only: bool = True) -> List[DiscoveredApplication]:
        """Returns all registered discovered applications."""
        if available_only:
            return [app for app in self._cached_apps.values() if app.is_available]
        return list(self._cached_apps.values())

    def get_application(self, app_id: str) -> Optional[DiscoveredApplication]:
        """Gets application by exact app_id."""
        return self._cached_apps.get(app_id.lower())

    def register_application(self, app_id: str, display_name: str, executable_path: str,
                             launch_mechanism: str = "executable", arguments: List[str] = None) -> DiscoveredApplication:
        """Registers a custom or portable application dynamically at runtime."""
        app = DiscoveredApplication(
            app_id=app_id.lower().strip(),
            display_name=display_name.strip(),
            executable_path=executable_path,
            arguments=arguments or [],
            source="user",
            platform=self.platform_name,
            launch_mechanism=launch_mechanism,
            install_directory=str(Path(executable_path).parent) if Path(executable_path).exists() else None
        )
        self._cached_apps[app.app_id] = app
        self._save_to_db([app])
        return app

    def add_user_alias(self, app_id: str, alias: str) -> bool:
        """Adds a user-defined alias for an application, persisting it across restarts and scans."""
        app = self.get_application(app_id)
        if not app:
            return False
        clean_alias = alias.lower().strip()
        if clean_alias not in app.user_aliases:
            app.user_aliases.append(clean_alias)
            self._save_to_db([app])
            logger.info(f"Added user alias '{clean_alias}' to app '{app_id}'.")
            return True
        return False

    def remove_user_alias(self, app_id: str, alias: str) -> bool:
        """Removes a user-defined alias for an application."""
        app = self.get_application(app_id)
        if not app:
            return False
        clean_alias = alias.lower().strip()
        if clean_alias in app.user_aliases:
            app.user_aliases.remove(clean_alias)
            self._save_to_db([app])
            return True
        return False

    def get_user_aliases(self, app_id: str) -> List[str]:
        """Retrieves user-defined aliases for an application."""
        app = self.get_application(app_id)
        return list(app.user_aliases) if app else []

    def find_application(self, query: str) -> Tuple[Optional[DiscoveredApplication], List[DiscoveredApplication]]:
        """Resolves natural language name or alias against discovered applications.

        Resolution order:
        1. Exact match on user-defined aliases.
        2. Exact match on app_id or display_name.
        3. Exact match on searchable aliases.
        4. Generic semantic alias ("code editor", "browser").
        5. Static applications.json aliases.
        6. Substring / controlled fuzzy token match with ambiguity detection.
        """
        if not query or not query.strip():
            return None, []

        clean = query.lower().strip()
        for prefix in ["launch ", "open ", "start ", "run ", "the ", "my "]:
            if clean.startswith(prefix):
                clean = clean[len(prefix):].strip()

        # 1. User-defined aliases first (Highest precedence)
        for app in self._cached_apps.values():
            if not app.is_available:
                continue
            if clean in [a.lower() for a in app.user_aliases]:
                return app, []

        # 2. Exact app_id or exact display name match
        for app in self._cached_apps.values():
            if not app.is_available:
                continue
            if app.app_id == clean or app.display_name.lower() == clean:
                return app, []

        # 3. Exact searchable alias match
        for app in self._cached_apps.values():
            if not app.is_available:
                continue
            if clean in [a.lower() for a in app.searchable_aliases]:
                return app, []

        # 4. Generic semantic aliases ("code editor", "3d editor", "browser")
        if clean in self.SEMANTIC_ALIASES:
            for target_id in self.SEMANTIC_ALIASES[clean]:
                matched = self._match_single_identifier(target_id)
                if matched:
                    return matched, []

        # 5. Configured applications.json aliases
        static_app = self._check_static_aliases(clean)
        if static_app:
            return static_app, []

        # 6. Prefix / Substring / Token matching
        candidates = []
        for app in self._cached_apps.values():
            if not app.is_available:
                continue
            name_lower = app.display_name.lower()
            id_lower = app.app_id.lower()
            # Token boundary or containment check
            if (clean in name_lower) or (clean in id_lower) or (name_lower in clean):
                candidates.append(app)
            elif any(clean in a.lower() for a in app.searchable_aliases):
                candidates.append(app)

        unique_candidates = {c.app_id: c for c in candidates}
        candidates = list(unique_candidates.values())

        if len(candidates) == 1:
            return candidates[0], []
        elif len(candidates) > 1:
            # Check for a perfect standalone word match
            for c in candidates:
                words = c.display_name.lower().split()
                if clean in words or c.app_id == clean:
                    return c, []
            return None, candidates

        return None, []

    def _match_single_identifier(self, ident: str) -> Optional[DiscoveredApplication]:
        """Tries to match a target identifier or slug against cached apps."""
        clean = ident.lower().strip()
        if clean in self._cached_apps and self._cached_apps[clean].is_available:
            return self._cached_apps[clean]
        for app in self._cached_apps.values():
            if not app.is_available:
                continue
            if clean == app.app_id or clean == app.display_name.lower():
                return app
        return None

    def _check_static_aliases(self, clean: str) -> Optional[DiscoveredApplication]:
        """Checks configured applications.json aliases."""
        p = Path(self.apps_json_path)
        if not p.exists():
            return None
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, info in data.items():
                aliases = [a.lower() for a in info.get("aliases", [])]
                if clean == key.lower() or clean in aliases:
                    return self._match_single_identifier(key)
        except Exception:
            pass
        return None

    def find_application_by_date(self, day_offset: int = 0) -> Optional[DiscoveredApplication]:
        """Finds an application installed or discovered around a certain day offset (0 = today, 1 = yesterday)."""
        import datetime
        target_date = datetime.date.today() - datetime.timedelta(days=day_offset)

        matches = []
        for app in self._cached_apps.values():
            if not app.is_available:
                continue
            app_date = None
            if app.executable_path and os.path.exists(app.executable_path):
                try:
                    mtime = os.path.getmtime(app.executable_path)
                    ctime = os.path.getctime(app.executable_path)
                    ref_time = min(ctime, mtime)
                    app_date = datetime.datetime.fromtimestamp(ref_time).date()
                except Exception:
                    pass
            if not app_date and app.last_discovered_at:
                app_date = datetime.datetime.fromtimestamp(app.last_discovered_at).date()

            if app_date == target_date:
                matches.append((app, getattr(app, "last_discovered_at", 0)))

        if matches:
            matches.sort(key=lambda x: x[1], reverse=True)
            return matches[0][0]
        return None

    # =========================================================================
    # PHASE 5: DESKTOP CONTROL OPERATIONS (PROPERTIES, FOLDER, SETTINGS, META)
    # =========================================================================

    def open_properties_dialog(self, app_id_or_name: str) -> Dict[str, Any]:
        """Opens the native file Properties dialog for the application executable."""
        app, candidates = self.find_application(app_id_or_name)
        if not app:
            cand_msg = f" Did you mean: {', '.join([c.display_name for c in candidates[:3]])}?" if candidates else ""
            return {
                "success": False,
                "message": f"I couldn't find an application matching '{app_id_or_name}' to open properties.{cand_msg}",
                "app_id": None
            }

        target_path = app.executable_path
        if not target_path or not os.path.exists(target_path):
            return {
                "success": False,
                "message": f"The executable file for {app.display_name} could not be located on disk.",
                "app_id": app.app_id
            }

        if sys.platform.startswith("win"):
            try:
                import ctypes
                from ctypes import wintypes

                class SHELLEXECUTEINFOW(ctypes.Structure):
                    _fields_ = [
                        ("cbSize", wintypes.DWORD),
                        ("fMask", wintypes.ULONG),
                        ("hwnd", wintypes.HWND),
                        ("lpVerb", wintypes.LPCWSTR),
                        ("lpFile", wintypes.LPCWSTR),
                        ("lpParameters", wintypes.LPCWSTR),
                        ("lpDirectory", wintypes.LPCWSTR),
                        ("nShow", ctypes.c_int),
                        ("hInstApp", wintypes.HINSTANCE),
                        ("lpIDList", wintypes.LPVOID),
                        ("lpClass", wintypes.LPCWSTR),
                        ("hkeyClass", wintypes.HKEY),
                        ("dwHotKey", wintypes.DWORD),
                        ("hIconOrMonitor", wintypes.HANDLE),
                        ("hProcess", wintypes.HANDLE),
                    ]

                SEE_MASK_INVOKEIDLIST = 0x0000000C
                SW_SHOWNORMAL = 1

                sei = SHELLEXECUTEINFOW()
                sei.cbSize = ctypes.sizeof(SHELLEXECUTEINFOW)
                sei.fMask = SEE_MASK_INVOKEIDLIST
                sei.hwnd = None
                sei.lpVerb = "properties"
                sei.lpFile = os.path.abspath(target_path)
                sei.lpParameters = None
                sei.lpDirectory = None
                sei.nShow = SW_SHOWNORMAL

                res = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(sei))
                if res:
                    return {
                        "success": True,
                        "message": f"Opened properties dialog for {app.display_name}.",
                        "app_id": app.app_id,
                        "path": target_path
                    }
                else:
                    err_code = ctypes.windll.kernel32.GetLastError()
                    return {
                        "success": False,
                        "message": f"Failed to open properties dialog for {app.display_name} (Error code: {err_code}).",
                        "app_id": app.app_id
                    }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Error opening properties dialog: {e}",
                    "app_id": app.app_id
                }
        else:
            # Linux: Nautilus properties
            try:
                if shutil.which("nautilus"):
                    subprocess.Popen(["nautilus", "--properties", os.path.abspath(target_path)])
                    return {
                        "success": True,
                        "message": f"Opened file properties for {app.display_name} via Nautilus.",
                        "app_id": app.app_id
                    }
            except Exception:
                pass
            return {
                "success": False,
                "message": f"Ubuntu Linux desktop does not expose a standard Properties dialog API for background agents. Executable is at {target_path}.",
                "app_id": app.app_id,
                "path": target_path
            }

    def open_install_folder(self, app_id_or_name: str) -> Dict[str, Any]:
        """Opens the installation directory in File Explorer / desktop file manager with the executable selected."""
        app, candidates = self.find_application(app_id_or_name)
        if not app:
            cand_msg = f" Did you mean: {', '.join([c.display_name for c in candidates[:3]])}?" if candidates else ""
            return {
                "success": False,
                "message": f"I couldn't find an application matching '{app_id_or_name}'.{cand_msg}",
                "app_id": None
            }

        target_path = app.executable_path
        install_dir = app.install_directory or (str(Path(target_path).parent) if target_path else None)

        if not install_dir or not os.path.exists(install_dir):
            return {
                "success": False,
                "message": f"The installation directory for {app.display_name} could not be found.",
                "app_id": app.app_id
            }

        try:
            if sys.platform.startswith("win"):
                if target_path and os.path.exists(target_path):
                    subprocess.Popen(["explorer.exe", f"/select,{os.path.abspath(target_path)}"])
                else:
                    os.startfile(os.path.abspath(install_dir))
            else:
                subprocess.Popen(["xdg-open", os.path.abspath(install_dir)])

            return {
                "success": True,
                "message": f"Opened installation folder for {app.display_name}.",
                "app_id": app.app_id,
                "path": install_dir
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to open installation folder: {e}",
                "app_id": app.app_id
            }

    def open_installed_app_details(self, app_id_or_name: str) -> Dict[str, Any]:
        """Opens the operating system's installed apps management details page."""
        app, _ = self.find_application(app_id_or_name)
        app_name = app.display_name if app else app_id_or_name.title()
        try:
            if sys.platform.startswith("win"):
                os.startfile("ms-settings:appsfeatures")
                return {
                    "success": True,
                    "message": f"Opened Windows Installed Apps settings for {app_name}.",
                    "app_id": app.app_id if app else None
                }
            else:
                if shutil.which("gnome-control-center"):
                    subprocess.Popen(["gnome-control-center", "default-applications"])
                elif shutil.which("software-properties-gtk"):
                    subprocess.Popen(["software-properties-gtk"])
                else:
                    return {
                        "success": False,
                        "message": "System application details manager is not installed on this Linux environment.",
                        "app_id": app.app_id if app else None
                    }
                return {
                    "success": True,
                    "message": f"Opened system application details for {app_name}.",
                    "app_id": app.app_id if app else None
                }
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to open installed app details: {e}",
                "app_id": app.app_id if app else None
            }

    def open_app_settings(self, app_id_or_name: str) -> Dict[str, Any]:
        """Opens internal application settings (e.g. chrome://settings) or reports unsupported internal URI."""
        app, _ = self.find_application(app_id_or_name)
        app_key = app.app_id if app else app_id_or_name.lower().strip()
        disp_name = app.display_name if app else app_id_or_name.title()

        browser_settings = {
            "chrome": "chrome://settings",
            "google_chrome": "chrome://settings",
            "edge": "edge://settings",
            "msedge": "edge://settings",
            "brave": "brave://settings",
            "firefox": "about:preferences",
            "opera": "opera://settings",
            "vivaldi": "vivaldi://settings"
        }

        if app_key in browser_settings or (app and app.category == "browser"):
            url = browser_settings.get(app_key, "chrome://settings")
            from modules.browser.web_control import open_url
            ok = open_url(url)
            return {
                "success": ok,
                "message": f"Opened {disp_name} settings ({url})." if ok else f"Failed to open {disp_name} settings.",
                "app_id": app_key,
                "settings_type": "internal_browser_settings"
            }

        # For non-browsers that do not provide an external CLI settings URI
        return {
            "success": False,
            "message": f"{disp_name} does not expose an external command-line settings URL. Opening its system app details instead.",
            "app_id": app_key,
            "settings_type": "unsupported_internal_settings"
        }

    def get_app_metadata(self, app_id_or_name: str) -> Dict[str, Any]:
        """Reports rich metadata, version, publisher, and path for an installed application."""
        app, candidates = self.find_application(app_id_or_name)
        if not app:
            cand_msg = f" Similar applications found: {', '.join([c.display_name for c in candidates[:3]])}." if candidates else ""
            return {
                "success": False,
                "message": f"Application '{app_id_or_name}' is not found in the registry.{cand_msg}",
                "candidates": [c.display_name for c in candidates[:4]]
            }

        ver_str = app.version or "Not reported"
        pub_str = app.publisher or "Not reported"
        msg = f"{app.display_name} (Version: {ver_str}, Publisher: {pub_str}) is installed at {app.executable_path}."

        return {
            "success": True,
            "message": msg,
            "app_id": app.app_id,
            "display_name": app.display_name,
            "version": app.version,
            "publisher": app.publisher,
            "executable_path": app.executable_path,
            "install_directory": app.install_directory,
            "launch_mechanism": app.launch_mechanism,
            "category": app.category,
            "discovery_source": app.source,
            "is_available": app.is_available,
            "user_aliases": app.user_aliases,
            "searchable_aliases": app.searchable_aliases,
            "last_verification": app.last_discovered_at
        }

    def is_app_installed(self, app_id_or_name: str) -> Dict[str, Any]:
        """Checks if a specific application is installed and available."""
        app, candidates = self.find_application(app_id_or_name)
        if not app:
            clean = app_id_or_name.lower().strip()
            for prefix in ["launch ", "open ", "start ", "run ", "the ", "my "]:
                if clean.startswith(prefix):
                    clean = clean[len(prefix):].strip()
            for cached in self._cached_apps.values():
                if (cached.app_id == clean or 
                    cached.display_name.lower() == clean or 
                    clean in [a.lower() for a in cached.searchable_aliases] or 
                    clean in [u.lower() for u in cached.user_aliases]):
                    app = cached
                    break

        if app:
            if app.is_available:
                ver_text = f" (version {app.version})" if app.version else ""
                return {
                    "installed": True,
                    "available": True,
                    "message": f"Yes, {app.display_name} is installed and available{ver_text}.",
                    "app": app.to_dict()
                }
            else:
                return {
                    "installed": True,
                    "available": False,
                    "message": f"{app.display_name} is registered in the system, but its executable is currently unavailable on disk.",
                    "app": app.to_dict()
                }

        if candidates:
            names = ", ".join([c.display_name for c in candidates[:3]])
            return {
                "installed": False,
                "available": False,
                "message": f"'{app_id_or_name}' was not found directly, but similar installed applications exist: {names}.",
                "candidates": [c.display_name for c in candidates]
            }

        return {
            "installed": False,
            "available": False,
            "message": f"No, {app_id_or_name} is not installed on this system."
        }

    def list_installed_apps(self, category: Optional[str] = None, filter_query: Optional[str] = None) -> Dict[str, Any]:
        """Lists installed applications or filters by category (e.g. browsers)."""
        apps = [a for a in self._cached_apps.values() if a.is_available]
        if category:
            c_clean = category.lower().strip()
            apps = [a for a in apps if a.category == c_clean or c_clean in [s.lower() for s in a.searchable_aliases]]

        if filter_query:
            f_clean = filter_query.lower().strip()
            apps = [a for a in apps if f_clean in a.display_name.lower() or f_clean in a.app_id.lower()]

        if category == "browser" or (filter_query and "browser" in filter_query.lower()):
            apps = [a for a in apps if not any(bad in a.display_name.lower() for bad in ["host", "helper", "mcafee", "webadvisor"])]

        # Clean display names and deduplicate by resolved binary path (e.g. msedge vs Microsoft Edge)
        exe_map: Dict[str, str] = {}
        for a in apps:
            norm_p = str(Path(a.executable_path).resolve()).lower() if (a.executable_path and Path(a.executable_path).exists()) else a.app_id
            disp = a.display_name.title() if a.display_name.islower() else a.display_name
            if norm_p not in exe_map or len(disp) > len(exe_map[norm_p]):
                exe_map[norm_p] = disp

        names = sorted(list(set(exe_map.values())))
        if category == "browser" or (filter_query and "browser" in filter_query.lower()):
            if names:
                msg = f"Available browsers found on this system: {', '.join(names)}."
            else:
                msg = "No web browsers were found in the registry."
        else:
            sample_count = min(len(names), 10)
            sample = ", ".join(names[:sample_count])
            if len(names) > sample_count:
                msg = f"You have {len(names)} applications installed, including: {sample}, and {len(names) - sample_count} more."
            elif names:
                msg = f"Installed applications ({len(names)}): {sample}."
            else:
                msg = "No installed applications found in the registry."

        return {
            "success": True,
            "count": len(names),
            "applications": names,
            "message": msg
        }


# Global singleton instance
app_discovery = ApplicationDiscovery()
