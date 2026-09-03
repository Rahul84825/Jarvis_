# Filesystem Manager Subsystem

## Overview
The Filesystem Manager (`core/os/filesystem_manager.py`) handles cross-platform directory listing, file searching, content pattern matching, reading/writing files, and launching default applications.

---

## Key Methods

- `resolve_path(path_str: str) -> Path`: Normalizes user paths, expanding `~`, environment variables (%USERPROFILE%), relative, and absolute paths.
- `list_directory(path: str = ".") -> dict`: Lists directory contents with file sizes and directory metadata.
- `search_files(pattern: str, base_dir: str = None, extension: str = None) -> dict`: Performs targeted file search with extension filtering.
- `search_content(query: str, base_dir: str = None, extension: str = None) -> dict`: Searches text content across project files.
- `read_file(path: str) -> dict`: Reads text contents safely up to max byte caps.
- `write_file(path: str, content: str, append: bool = False) -> dict`: Writes or appends text to a file.
- `open_file(path: str) -> dict` / `open_directory(path: str) -> dict`: Opens files or folders in native file explorer.

---

## Permission Error Handling
When a `PermissionError` occurs, the manager suppresses raw Python tracebacks and returns a user-friendly message: *"I don't have permission to access that location."*
