import os
import logging
from pathlib import Path

logger = logging.getLogger("Jarvis.FileControl")

def get_downloads_path() -> Path:
    return Path.home() / "Downloads"

def get_documents_path() -> Path:
    # On Windows, Documents could be in OneDrive, so check common variants
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
    # Resolves to workspace root c:\Users\activ\Desktop\Jarvis
    return Path(__file__).parent.parent.parent.resolve()

def open_folder(folder_name: str) -> bool:
    """Opens a system folder by name keyword (downloads, documents, desktop, project) or direct path."""
    name = folder_name.lower().strip()
    path = None
    
    if "download" in name:
        path = get_downloads_path()
    elif "document" in name:
        path = get_documents_path()
    elif "desktop" in name:
        path = get_desktop_path()
    elif "project" in name or "workspace" in name:
        path = get_project_path()
    else:
        # Check if it's a direct valid path
        probe_path = Path(folder_name)
        if probe_path.exists() and probe_path.is_dir():
            path = probe_path
            
    if path and path.exists():
        logger.info(f"Opening folder path: {path}")
        try:
            os.startfile(str(path))
            return True
        except Exception as e:
            logger.error(f"Failed to open folder {path}: {e}")
            return False
            
    logger.warning(f"Folder not resolved or does not exist: {folder_name}")
    return False

def open_file(file_path: str) -> bool:
    """Opens a file using its default Windows application handler (read-only command wrapper)."""
    path = Path(file_path)
    if not path.exists():
        logger.warning(f"File not found: {file_path}")
        return False
        
    if path.is_dir():
        # Delegate to open_folder
        return open_folder(file_path)
        
    logger.info(f"Opening file: {path}")
    try:
        os.startfile(str(path))
        return True
    except Exception as e:
        logger.error(f"Failed to open file {path}: {e}")
        return False

def search_files(query: str) -> list:
    """Searches for files matching the query (glob case-insensitive) in Downloads, Documents, and Desktop.
    Limits traversal depth to ensure performance meets constraints.
    Returns a list of matching absolute file paths.
    """
    logger.info(f"Searching for files matching query: '{query}'")
    search_dirs = [
        get_downloads_path(),
        get_documents_path(),
        get_desktop_path()
    ]
    
    matches = []
    max_matches = 15
    
    # Standardise query for matching
    clean_query = query.lower().strip()
    
    # We walk down max 2 levels to keep search execution < 1s
    for sdir in search_dirs:
        if not sdir.exists():
            continue
            
        try:
            for root, dirs, files in os.walk(str(sdir)):
                # Calculate depth
                depth = Path(root).relative_to(sdir).parts
                if len(depth) > 2:
                    # Skip deeper subdirectories to save time
                    dirs.clear() # don't visit subdirs
                    continue
                    
                for file in files:
                    if clean_query in file.lower():
                        full_path = os.path.join(root, file)
                        matches.append(full_path)
                        if len(matches) >= max_matches:
                            return matches
        except Exception as e:
            logger.debug(f"Search warning in directory {sdir}: {e}")
            
    return matches
