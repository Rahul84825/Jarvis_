"""Platform-Aware Application Discovery Service for JARVIS.

Discovers native applications on Windows and Linux, normalizes application records,
caches catalogues in SQLite, and provides safe lookup and disambiguation.
"""

import os
import sys
import glob
import json
import time
import shutil
import sqlite3
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Tuple, Any

logger = logging.getLogger("Jarvis.AppDiscovery")


@dataclass
class DiscoveredApplication:
    """Normalized record of an installed application."""
    app_id: str
    display_name: str
    executable_path: str
    arguments: List[str] = field(default_factory=list)
    source: str = "unknown"  # start_menu, registry_uninstall, registry_app_paths, desktop_entry, config, path
    platform: str = "windows"  # windows, linux, darwin
    is_available: bool = True
    last_discovered_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["arguments"] = json.dumps(self.arguments)
        d["is_available"] = 1 if self.is_available else 0
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DiscoveredApplication":
        args = data.get("arguments", "[]")
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = []
        return cls(
            app_id=data["app_id"],
            display_name=data["display_name"],
            executable_path=data["executable_path"],
            arguments=args,
            source=data.get("source", "unknown"),
            platform=data.get("platform", "windows"),
            is_available=bool(data.get("is_available", 1)),
            last_discovered_at=float(data.get("last_discovered_at", time.time()))
        )


class ApplicationDiscovery:
    """Discovers, normalizes, caches, and resolves installed desktop applications."""

    # Common semantic aliases mapping generic terms to typical applications
    SEMANTIC_ALIASES = {
        "code editor": ["vscode", "code", "vscodium", "sublime_text", "notepad++"],
        "my code editor": ["vscode", "code", "vscodium", "sublime_text"],
        "3d editor": ["blender", "maya", "3dsmax"],
        "my 3d editor": ["blender"],
        "text editor": ["notepad", "gedit", "kate", "notepad++", "sublime_text"],
        "music": ["spotify", "apple_music", "vlc"],
        "music player": ["spotify", "vlc"],
        "web browser": ["chrome", "google_chrome", "firefox", "msedge", "brave"],
        "browser": ["chrome", "google_chrome", "firefox", "msedge", "brave"],
        "terminal": ["powershell", "cmd", "wt", "bash", "gnome-terminal"],
        "calculator": ["calc", "calculator", "gnome-calculator"],
        "file manager": ["explorer", "nautilus", "dolphin", "thunar"],
    }

    def __init__(self, db_path: Optional[str] = None, apps_json_path: Optional[str] = None):
        base_dir = Path(__file__).parent.parent.parent
        self.db_path = db_path or str(base_dir / "logs" / "applications.db")
        self.apps_json_path = apps_json_path or str(base_dir / "config" / "applications.json")
        self.platform_name = "windows" if sys.platform.startswith("win") else "linux"
        self._cached_apps: Dict[str, DiscoveredApplication] = {}
        self._last_scan_time: float = 0.0
        self._init_db()
        self._load_from_db()
        if not self._cached_apps:
            self.scan(force=True)

    def _init_db(self):
        """Initializes SQLite schema with additive migrations."""
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
                    last_discovered_at REAL NOT NULL
                )
            """)
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
        """Persists discovered applications into SQLite."""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            for app in apps:
                d = app.to_dict()
                cursor.execute("""
                    INSERT INTO discovered_applications 
                    (app_id, display_name, executable_path, arguments, source, platform, is_available, last_discovered_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(app_id) DO UPDATE SET
                        display_name = excluded.display_name,
                        executable_path = excluded.executable_path,
                        arguments = excluded.arguments,
                        source = excluded.source,
                        platform = excluded.platform,
                        is_available = excluded.is_available,
                        last_discovered_at = excluded.last_discovered_at
                """, (
                    d["app_id"], d["display_name"], d["executable_path"],
                    d["arguments"], d["source"], d["platform"],
                    d["is_available"], d["last_discovered_at"]
                ))
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to save discovered applications to DB: {e}")
        finally:
            if conn:
                conn.close()

    # =========================================================================
    # PLATFORM DISCOVERY SCANNERS
    # =========================================================================

    def scan(self, force: bool = False) -> List[DiscoveredApplication]:
        """Performs a platform-aware scan for installed applications without running them."""
        now = time.time()
        # Avoid scans more frequent than 30 seconds unless forced
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
        else:
            self._scan_linux_desktop_entries(discovered)
            self._scan_linux_path_executables(discovered)

        # 3. Filter stale / invalid entries
        valid_apps = []
        for app in discovered.values():
            # Check availability safely (does file exist and is it not a directory)
            p = Path(app.executable_path)
            if p.exists() or shutil.which(app.executable_path):
                app.is_available = True
            else:
                app.is_available = False

            # Keep available applications in catalogue
            if app.is_available:
                valid_apps.append(app)
                self._cached_apps[app.app_id] = app

        self._save_to_db(valid_apps)
        self._last_scan_time = now
        logger.info(f"Scan complete. Discovered {len(valid_apps)} available applications.")
        return valid_apps

    def refresh(self) -> int:
        """On-demand safe refresh mechanism."""
        apps = self.scan(force=True)
        return len(apps)

    def _clean_display_name(self, name: str) -> str:
        """Cleans up names by removing version numbers, architectures, and file extensions."""
        cleaned = name.strip()
        for ext in [".exe", ".lnk", ".desktop"]:
            if cleaned.lower().endswith(ext):
                cleaned = cleaned[:-len(ext)]
        # Remove noisy suffixes
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

    # -------------------------------------------------------------------------
    # Windows Discovery Mechanisms
    # -------------------------------------------------------------------------

    def _parse_windows_lnk(self, lnk_path: str) -> Optional[str]:
        """Safely parses a Windows Shell Link (.lnk) without executing it or launching processes."""
        try:
            with open(lnk_path, "rb") as f:
                content = f.read(4096)  # Shell links headers are small
            if len(content) < 0x4C or content[:4] != b"\x4C\x00\x00\x00":
                return None
            flags = int.from_bytes(content[0x14:0x18], "little")
            has_id_list = bool(flags & 0x01)
            has_link_info = bool(flags & 0x02)
            offset = 0x4C
            if has_id_list:
                if len(content) < offset + 2:
                    return None
                id_list_size = int.from_bytes(content[offset:offset+2], "little")
                offset += 2 + id_list_size
            if has_link_info and len(content) > offset + 4:
                info_len = int.from_bytes(content[offset:offset+4], "little")
                local_base_offset = int.from_bytes(content[offset+0x10:offset+0x14], "little")
                if local_base_offset and offset + local_base_offset < len(content):
                    target_bytes = content[offset+local_base_offset:min(len(content), offset+info_len)]
                    target_str = target_bytes.split(b"\x00")[0].decode("latin1", errors="ignore")
                    if target_str and Path(target_str).exists():
                        return target_str
        except Exception:
            pass
        return None

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
                    # Ignore uninstaller, help, or documentation shortcuts
                    name_lower = file_name.lower()
                    if any(bad in name_lower for bad in ["uninstall", "remove", "help", "readme", "documentation", "manual"]):
                        continue

                    target_exe = self._parse_windows_lnk(str(lnk_file))
                    exec_path = target_exe if (target_exe and Path(target_exe).exists()) else str(lnk_file)
                    display_name = self._clean_display_name(file_name)
                    app_id = self._generate_app_id(display_name)

                    if app_id not in discovered:
                        discovered[app_id] = DiscoveredApplication(
                            app_id=app_id,
                            display_name=display_name,
                            executable_path=exec_path,
                            source="start_menu",
                            platform="windows"
                        )
                except Exception as e:
                    logger.debug(f"Error parsing shortcut {lnk_file}: {e}")

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
                                                platform="windows"
                                            )
                        except OSError:
                            continue
            except OSError:
                continue

    def _scan_windows_registry_uninstall(self, discovered: Dict[str, DiscoveredApplication]):
        """Scans Windows Registry Uninstall keys for installed software display names and executables."""
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
                                if app_id in discovered:
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

                                if not exec_path:
                                    try:
                                        install_loc, _ = winreg.QueryValueEx(app_key, "InstallLocation")
                                        if install_loc and Path(install_loc).is_dir():
                                            # Find primary executable
                                            for candidate in Path(install_loc).glob("*.exe"):
                                                if candidate.is_file() and not candidate.name.lower().startswith("unins"):
                                                    exec_path = str(candidate)
                                                    break
                                    except OSError:
                                        pass

                                if exec_path and Path(exec_path).exists():
                                    discovered[app_id] = DiscoveredApplication(
                                        app_id=app_id,
                                        display_name=clean_disp,
                                        executable_path=exec_path,
                                        source="registry_uninstall",
                                        platform="windows"
                                    )
                        except OSError:
                            continue
            except OSError:
                continue

    # -------------------------------------------------------------------------
    # Linux Discovery Mechanisms
    # -------------------------------------------------------------------------

    def _scan_linux_desktop_entries(self, discovered: Dict[str, DiscoveredApplication]):
        """Scans Linux .desktop entry files."""
        dirs = [
            Path("/usr/share/applications"),
            Path("/usr/local/share/applications"),
            Path.home() / ".local" / "share" / "applications"
        ]
        for d in dirs:
            if not d.exists():
                continue
            for dt_file in d.glob("*.desktop"):
                try:
                    name, exec_cmd, no_display = None, None, False
                    with open(dt_file, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith("Name=") and not name:
                                name = line[5:].strip()
                            elif line.startswith("Exec=") and not exec_cmd:
                                exec_cmd = line[5:].strip()
                            elif line.startswith("NoDisplay=true"):
                                no_display = True

                    if no_display or not name or not exec_cmd:
                        continue

                    # Strip arguments like %U, %f, etc.
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
                                platform="linux"
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
            ("spotify", "Spotify"),
            ("vlc", "VLC Media Player"),
            ("gimp", "GIMP"),
            ("steam", "Steam"),
            ("nautilus", "Files"),
            ("gnome-calculator", "Calculator")
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
                        platform="linux"
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
                # Try resolving
                resolved = shutil.which(target_exec) or target_exec
                # Use primary alias or formatted key as display name
                aliases = info.get("aliases", [])
                disp = aliases[0].title() if aliases else key.title()
                app_id = self._generate_app_id(key)
                discovered[app_id] = DiscoveredApplication(
                    app_id=app_id,
                    display_name=disp,
                    executable_path=resolved,
                    source="config",
                    platform=self.platform_name
                )
        except Exception as e:
            logger.warning(f"Failed to load applications.json in discovery: {e}")

    # =========================================================================
    # CATALOGUE QUERYING AND DISAMBIGUATION
    # =========================================================================

    def list_applications(self, available_only: bool = True) -> List[DiscoveredApplication]:
        """Returns all registered discovered applications."""
        if available_only:
            return [app for app in self._cached_apps.values() if app.is_available]
        return list(self._cached_apps.values())

    def get_application(self, app_id: str) -> Optional[DiscoveredApplication]:
        """Gets application by exact app_id."""
        return self._cached_apps.get(app_id.lower())

    def find_application(self, query: str) -> Tuple[Optional[DiscoveredApplication], List[DiscoveredApplication]]:
        """Resolves natural language name or alias against discovered applications.

        Returns:
            Tuple of (exact_match, candidates):
            - If exactly one clear match: (match, [])
            - If ambiguous multiple matches: (None, candidates)
            - If no match found: (None, [])
        """
        if not query or not query.strip():
            return None, []

        clean = query.lower().strip()
        # Strip common speech prefixes ("my", "the", "open", "launch", "start", "application", "app")
        for prefix in ["launch ", "open ", "start ", "run ", "the ", "my "]:
            if clean.startswith(prefix):
                clean = clean[len(prefix):].strip()

        # 1. Check semantic generic aliases ("code editor", "3d editor", etc.)
        if clean in self.SEMANTIC_ALIASES:
            for target_id in self.SEMANTIC_ALIASES[clean]:
                matched = self._match_single_identifier(target_id)
                if matched:
                    return matched, []

        # 2. Exact app_id or exact display name match
        for app in self._cached_apps.values():
            if not app.is_available:
                continue
            if app.app_id == clean or app.display_name.lower() == clean:
                return app, []

        # 3. Known static alias check
        static_app = self._check_static_aliases(clean)
        if static_app:
            return static_app, []

        # 4. Prefix or substring matching
        candidates = []
        for app in self._cached_apps.values():
            if not app.is_available:
                continue
            name_lower = app.display_name.lower()
            id_lower = app.app_id.lower()
            if (clean in name_lower) or (clean in id_lower) or (name_lower in clean):
                candidates.append(app)

        # Deduplicate candidates
        unique_candidates = {c.app_id: c for c in candidates}
        candidates = list(unique_candidates.values())

        if len(candidates) == 1:
            return candidates[0], []
        elif len(candidates) > 1:
            # Check if one is a perfect token match
            for c in candidates:
                if c.display_name.lower() == clean or c.app_id == clean:
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


# Global singleton instance
app_discovery = ApplicationDiscovery()
