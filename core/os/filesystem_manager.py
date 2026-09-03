import os
import shutil
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("Jarvis.FilesystemManager")

class FilesystemManager:
    """Comprehensive Filesystem Control Manager.
    Provides robust, cross-platform path resolution, file reading/writing, targeted file searching,
    directory manipulation, and permission-aware error handling.
    """

    def resolve_path(self, path_str: str) -> Path:
        """Resolves user paths, expanding ~, environment variables, and relative references."""
        if not path_str:
            return Path.cwd()

        expanded = os.path.expandvars(os.path.expanduser(path_str))
        p = Path(expanded)
        if not p.is_absolute():
            p = (Path.cwd() / p).resolve()
        return p

    def exists(self, path_str: str) -> bool:
        try:
            return self.resolve_path(path_str).exists()
        except Exception:
            return False

    def is_file(self, path_str: str) -> bool:
        try:
            return self.resolve_path(path_str).is_file()
        except Exception:
            return False

    def is_directory(self, path_str: str) -> bool:
        try:
            return self.resolve_path(path_str).is_dir()
        except Exception:
            return False

    def list_directory(self, path_str: str = ".") -> Dict[str, Any]:
        """Lists directory entries with file metadata."""
        p = self.resolve_path(path_str)
        if not p.exists():
            return {"success": False, "error": f"Directory not found: {path_str}"}
        if not p.is_dir():
            return {"success": False, "error": f"Path is not a directory: {path_str}"}

        try:
            items = []
            for item in p.iterdir():
                items.append({
                    "name": item.name,
                    "path": str(item),
                    "is_dir": item.is_dir(),
                    "size": item.stat().st_size if item.is_file() else 0
                })
            logger.info(f"[FILESYSTEM] Listed {len(items)} items in '{p}'")
            return {"success": True, "path": str(p), "items": items, "count": len(items)}
        except PermissionError:
            logger.warning(f"[FILESYSTEM] Permission denied accessing directory: {p}")
            return {"success": False, "error": "I don't have permission to access that location."}
        except Exception as e:
            logger.error(f"[FILESYSTEM_ERROR] Failed to list directory {p}: {e}")
            return {"success": False, "error": str(e)}

    def search_files(self, pattern: str, base_dir: str = None, recursive: bool = True, extension: str = None) -> Dict[str, Any]:
        """Searches for files matching a pattern or extension in targeted directory."""
        p = self.resolve_path(base_dir or ".")
        if not p.exists() or not p.is_dir():
            return {"success": False, "error": "Invalid search directory."}

        pattern_clean = pattern.lower().strip() if pattern else ""
        ext_clean = extension.lower().strip() if extension else ""
        if ext_clean and not ext_clean.startswith("."):
            ext_clean = f".{ext_clean}"

        matches = []
        try:
            iterator = p.rglob("*") if recursive else p.glob("*")
            for file_item in iterator:
                if file_item.is_file():
                    if pattern_clean and pattern_clean not in file_item.name.lower():
                        continue
                    if ext_clean and file_item.suffix.lower() != ext_clean:
                        continue
                    matches.append(str(file_item))
                    if len(matches) >= 100:  # Safety cap
                        break

            logger.info(f"[FILESYSTEM_SEARCH] Found {len(matches)} matching files in '{p}' for pattern '{pattern}'")
            return {"success": True, "matches": matches, "count": len(matches), "base_dir": str(p)}
        except PermissionError:
            return {"success": False, "error": "I don't have permission to search that directory."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search_content(self, query: str, base_dir: str = None, extension: str = None) -> Dict[str, Any]:
        """Searches file content for a text string within targeted project files."""
        p = self.resolve_path(base_dir or ".")
        if not p.exists() or not p.is_dir():
            return {"success": False, "error": "Invalid search directory."}

        query_clean = query.lower().strip()
        ext_clean = extension.lower().strip() if extension else ""
        if ext_clean and not ext_clean.startswith("."):
            ext_clean = f".{ext_clean}"

        results = []
        try:
            for file_item in p.rglob("*"):
                if file_item.is_file():
                    # Skip binary/large files
                    if file_item.suffix.lower() in [".exe", ".dll", ".pyc", ".png", ".jpg", ".zip", ".db"]:
                        continue
                    if ext_clean and file_item.suffix.lower() != ext_clean:
                        continue

                    try:
                        with open(file_item, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            if query_clean in content.lower():
                                results.append(str(file_item))
                                if len(results) >= 50:
                                    break
                    except Exception:
                        continue

            logger.info(f"[FILESYSTEM_CONTENT_SEARCH] Found {len(results)} files matching query '{query}'")
            return {"success": True, "results": results, "count": len(results)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def read_file(self, path_str: str, max_bytes: int = 50000) -> Dict[str, Any]:
        """Reads file contents safely."""
        p = self.resolve_path(path_str)
        if not p.exists():
            return {"success": False, "error": f"File not found: {path_str}"}
        if not p.is_file():
            return {"success": False, "error": f"Path is a directory: {path_str}"}

        try:
            with open(p, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(max_bytes)
            logger.info(f"[FILESYSTEM_READ] Read {len(content)} chars from '{p}'")
            return {"success": True, "path": str(p), "content": content, "filename": p.name}
        except PermissionError:
            return {"success": False, "error": "I don't have permission to read that file."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def write_file(self, path_str: str, content: str, append: bool = False) -> Dict[str, Any]:
        """Writes or appends text content to a file."""
        p = self.resolve_path(path_str)
        mode = "a" if append else "w"
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, mode, encoding="utf-8") as f:
                f.write(content)
            logger.info(f"[FILESYSTEM_WRITE] Wrote to file '{p}' (append={append})")
            return {"success": True, "path": str(p), "message": f"Successfully wrote to {p.name}"}
        except PermissionError:
            return {"success": False, "error": "I don't have permission to write to that location."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def open_file(self, path_str: str) -> Dict[str, Any]:
        """Opens a file with its default system application."""
        p = self.resolve_path(path_str)
        if not p.exists():
            return {"success": False, "error": f"File not found: {path_str}"}

        try:
            if os.name == "nt":
                os.startfile(str(p))
            else:
                subprocess.Popen(["xdg-open", str(p)])
            logger.info(f"[FILESYSTEM_OPEN] Opened file in default app: {p}")
            return {"success": True, "message": f"Opened {p.name}."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def open_directory(self, path_str: str) -> Dict[str, Any]:
        """Opens a directory in system file explorer."""
        p = self.resolve_path(path_str)
        if not p.exists():
            return {"success": False, "error": f"Directory not found: {path_str}"}

        try:
            if os.name == "nt":
                os.startfile(str(p))
            else:
                subprocess.Popen(["xdg-open", str(p)])
            logger.info(f"[FILESYSTEM_OPEN_DIR] Opened directory: {p}")
            return {"success": True, "message": f"Opened {p.name} folder."}
        except Exception as e:
            return {"success": False, "error": str(e)}
