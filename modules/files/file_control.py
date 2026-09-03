import os
import logging
from pathlib import Path
from core.platform.platform_manager import platform_manager

logger = logging.getLogger("Jarvis.FileControl")

def get_downloads_path() -> Path:
    return Path.home() / "Downloads"

def get_documents_path() -> Path:
    onedrive_docs = Path.home() / "OneDrive" / "Documents"
    if onedrive_docs.exists():
        return onedrive_docs
    return Path.home() / "Documents"

def get_desktop_path() -> Path:
    onedrive_desktop = Path.home() / "OneDrive" / "Desktop"
    if onedrive_desktop.exists():
        return onedrive_desktop
    return Path.home() / "Desktop"

def get_project_path() -> Path:
    return Path(__file__).parent.parent.parent.resolve()

def open_folder(folder_name: str) -> bool:
    """Opens a system folder by name keyword (downloads, documents, desktop, pictures, videos, music) or path."""
    return platform_manager.open_folder(folder_name)

def open_file(file_path: str) -> bool:
    """Opens a file using default application handler."""
    path = Path(file_path)
    if not path.exists():
        logger.warning(f"File not found: {file_path}")
        return False

    if path.is_dir():
        return open_folder(file_path)

    logger.info(f"Opening file: {path}")
    return platform_manager.open_url(str(path))

def search_files(query: str) -> list:
    """Searches for files matching query in Downloads, Documents, and Desktop."""
    logger.info(f"Searching for files matching query: '{query}'")
    search_dirs = [
        get_downloads_path(),
        get_documents_path(),
        get_desktop_path()
    ]

    matches = []
    max_matches = 15
    clean_query = query.lower().strip()

    for sdir in search_dirs:
        if not sdir.exists():
            continue

        try:
            for root, dirs, files in os.walk(str(sdir)):
                try:
                    rel = Path(root).relative_to(sdir)
                    if len(rel.parts) > 2:
                        dirs.clear()
                        continue
                except ValueError:
                    pass

                for file in files:
                    if clean_query in file.lower():
                        full_path = os.path.join(root, file)
                        if full_path not in matches:
                            matches.append(full_path)
                            if len(matches) >= max_matches:
                                return matches
        except Exception as e:
            logger.debug(f"Search warning in directory {sdir}: {e}")

    return matches
