"""Windows Known Folders and Path Resolver for JARVIS.

Resolves Desktop, Documents, Downloads, user project directories,
and OneDrive redirected folders safely. Protects against path traversal.
"""

import os
import re
import sys
import uuid
import logging
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger("Jarvis.PathResolver")


class PathResolver:
    """Resolves natural language folder references to verified Windows file paths."""

    KNOWN_FOLDER_GUIDS = {
        "desktop": "{B4BFCC3A-DB2C-424C-B029-7FE99A87C641}",
        "documents": "{FDD39AD0-238F-46AF-ADB4-6C85480369C7}",
        "downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
        "music": "{4BD8D570-509A-49E5-8E0D-C1FF0363ACEE}",
        "pictures": "{33E28130-4E1E-4676-835A-98395C3BC3BB}",
        "videos": "{18989B1D-99D5-45B2-B648-57777FA64C60}"
    }

    def __init__(self):
        self._cached_known_folders: Dict[str, Path] = {}
        self._init_known_folders()

    def _init_known_folders(self):
        """Discovers real system paths for Windows Known Folders."""
        if not sys.platform.startswith("win"):
            home = Path.home()
            self._cached_known_folders = {
                "desktop": home / "Desktop",
                "documents": home / "Documents",
                "downloads": home / "Downloads"
            }
            return

        try:
            from win32com.shell import shell
            for name, guid_str in self.KNOWN_FOLDER_GUIDS.items():
                try:
                    p_str = shell.SHGetKnownFolderPath(guid_str, 0)
                    if p_str and os.path.exists(p_str):
                        self._cached_known_folders[name] = Path(p_str).resolve()
                except Exception as ex:
                    logger.debug(f"SHGetKnownFolderPath failed for {name}: {ex}")

        except ImportError:
            logger.debug("win32com.shell not available, using fallback paths.")

        # Fallback to standard user home directory if not populated
        home = Path.home()
        defaults = {
            "desktop": home / "Desktop",
            "documents": home / "Documents",
            "downloads": home / "Downloads"
        }
        for k, v in defaults.items():
            if k not in self._cached_known_folders or not self._cached_known_folders[k].exists():
                # Check OneDrive redirection fallback
                onedrive_desktop = home / "OneDrive" / "Desktop"
                onedrive_docs = home / "OneDrive" / "Documents"
                if k == "desktop" and onedrive_desktop.exists():
                    self._cached_known_folders[k] = onedrive_desktop
                elif k == "documents" and onedrive_docs.exists():
                    self._cached_known_folders[k] = onedrive_docs
                else:
                    self._cached_known_folders[k] = v

    def get_known_folder(self, folder_name: str) -> Optional[Path]:
        """Returns verified Path for 'desktop', 'documents', 'downloads', etc."""
        fn = folder_name.lower().strip()
        return self._cached_known_folders.get(fn)

    def resolve_destination(self, raw_input: str) -> Tuple[Optional[Path], str]:
        r"""Resolves natural language location into a concrete Path.
        Examples:
        - "Desktop" -> C:\Users\...\Desktop
        - "Desktop in a folder named DSA" -> C:\Users\...\Desktop\DSA
        - "my documents in project folder" -> C:\Users\...\Documents\project folder
        - "C:\\MyProjects" -> C:\MyProjects
        """
        text = raw_input.strip()
        if not text:
            return self.get_known_folder("desktop"), "Desktop (default)"

        # 1. Check for absolute path
        try:
            p = Path(text)
            if p.is_absolute():
                return p.resolve(), str(p)
        except Exception:
            pass

        # 2. Extract base folder and subfolder patterns
        base_path = None
        base_name = ""

        # Check known base folders
        for kf in ["desktop", "documents", "downloads"]:
            if kf in text.lower():
                base_path = self.get_known_folder(kf)
                base_name = kf.title()
                break

        if not base_path:
            base_path = self.get_known_folder("desktop") or Path.home()
            base_name = "Desktop"

        # Check for subfolder specifications:
        # "in a folder named X", "in folder X", "subfolder X", "folder X", "in X"
        m_sub = re.search(r"(?:in\s+(?:a\s+)?(?:folder|directory|subfolder)(?:\s+named|\s+called)?\s+([a-zA-Z0-9_\-\s]+))", text, re.IGNORECASE)
        if not m_sub:
            m_sub = re.search(r"(?:(?:in|into)\s+([a-zA-Z0-9_\-]+))", text, re.IGNORECASE)

        if m_sub:
            sub = m_sub.group(1).strip()
            # Filter out the base name itself (e.g. "in desktop")
            if sub.lower() not in ["desktop", "documents", "downloads", "my desktop", "my documents"]:
                dest = base_path / sub
                return dest.resolve(), f"{base_name} / {sub}"

        return base_path.resolve(), base_name

    def is_safe_path(self, target_path: Path) -> bool:
        """Ensures target path does not traverse into protected Windows system directories."""
        try:
            resolved = target_path.resolve()
            str_path = str(resolved).lower()

            # Prohibited system roots
            prohibited = [
                "c:\\windows",
                "c:\\program files",
                "c:\\program files (x86)",
                "c:\\system volume information",
                "c:\\recovery",
                "c:\\boot"
            ]
            for p in prohibited:
                if str_path.startswith(p):
                    logger.warning(f"Prevented write to protected system path: {resolved}")
                    return False

            return True
        except Exception:
            return False


# Global singleton instance
path_resolver = PathResolver()
