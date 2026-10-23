"""Persistent File and Folder Memory Subsystem for JARVIS.

Provides:
- Non-blocking background indexing of permitted user locations (Desktop, Documents, Projects)
- Safe exclusion of sensitive directories (system, AppData, .git, node_modules)
- SQLite persistent indexing in memory/jarvis_memory.db
- Fast search: exact, partial, extension filters, recent files
- Stale path detection & cleanup
- File Explorer integration
"""

import os
import time
import sqlite3
import threading
import logging
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional

from core.files.path_resolver import path_resolver

logger = logging.getLogger("Jarvis.FileMemory")

DEFAULT_DB_PATH = Path(__file__).parent.parent.parent / "memory" / "jarvis_memory.db"


@dataclass
class IndexedFileRecord:
    """Metadata record for an indexed file."""
    path: str
    filename: str
    extension: str
    size_bytes: int
    mtime: float
    project_alias: str = ""
    created_by_jarvis: bool = False
    tags: str = ""
    indexed_at: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FileMemoryManager:
    """Manages file indexing, persistent memory, and fast desktop file discovery."""

    EXCLUDED_DIRS = {
        "appdata", "node_modules", ".git", ".venv", "venv", "__pycache__",
        "windows", "program files", "program files (x86)", "$recycle.bin",
        "system volume information", "recovery", ".gemini", ".vscode"
    }

    SUPPORTED_EXTENSIONS = {
        ".py", ".cpp", ".c", ".h", ".hpp", ".java", ".js", ".ts", ".jsx", ".tsx",
        ".html", ".css", ".sql", ".md", ".json", ".yaml", ".yml", ".txt", ".csv",
        ".pdf", ".docx", ".xlsx", ".sh", ".ps1"
    }

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self._init_tables()
        self._indexing_thread: Optional[threading.Thread] = None
        self._is_indexing: bool = False

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_tables(self):
        """Creates additive indexing tables if they do not exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS files_indexed (
                    path TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    extension TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    mtime REAL NOT NULL,
                    project_alias TEXT DEFAULT '',
                    created_by_jarvis INTEGER DEFAULT 0,
                    tags TEXT DEFAULT '',
                    indexed_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_filename ON files_indexed(filename);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_extension ON files_indexed(extension);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_files_project ON files_indexed(project_alias);")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS recent_save_locations (
                    alias TEXT PRIMARY KEY,
                    path TEXT NOT NULL,
                    use_count INTEGER DEFAULT 1,
                    last_used REAL NOT NULL
                )
            """)
            conn.commit()

    def record_created_file(self, path: str, filename: str, language: str, size_bytes: int, project_alias: str = ""):
        """Records a file newly created by JARVIS into persistent file memory."""
        now = time.time()
        ext = Path(path).suffix.lower()
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO files_indexed
                (path, filename, extension, size_bytes, mtime, project_alias, created_by_jarvis, tags, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
            """, (path, filename, ext, size_bytes, now, project_alias, language, now))
            conn.commit()
        logger.info(f"[FILE_MEMORY] Recorded created file in memory: {filename} ({path})")

    def search_files(
        self,
        query: str,
        extension: Optional[str] = None,
        project_alias: Optional[str] = None,
        only_jarvis_created: bool = False,
        limit: int = 15
    ) -> List[IndexedFileRecord]:
        """Searches indexed files with stale path filtering."""
        clean_q = query.strip().lower()
        sql = "SELECT * FROM files_indexed WHERE 1=1"
        params: List[Any] = []

        if clean_q:
            q_underscore = clean_q.replace(" ", "_")
            q_wildcard = clean_q.replace(" ", "%")
            sql += " AND (LOWER(filename) LIKE ? OR LOWER(filename) LIKE ? OR LOWER(filename) LIKE ? OR LOWER(path) LIKE ? OR LOWER(tags) LIKE ?)"
            params.extend([f"%{clean_q}%", f"%{q_underscore}%", f"%{q_wildcard}%", f"%{q_wildcard}%", f"%{clean_q}%"])

        if extension:
            ext_clean = extension if extension.startswith(".") else f".{extension}"
            sql += " AND LOWER(extension) = ?"
            params.append(ext_clean.lower())

        if project_alias:
            sql += " AND LOWER(project_alias) = ?"
            params.append(project_alias.lower())

        if only_jarvis_created:
            sql += " AND created_by_jarvis = 1"

        sql += " ORDER BY mtime DESC LIMIT ?"
        params.append(limit * 2)  # retrieve extra to account for pruned stale paths

        records: List[IndexedFileRecord] = []
        stale_paths: List[str] = []

        with self._get_connection() as conn:
            rows = conn.execute(sql, params).fetchall()
            for r in rows:
                p = r["path"]
                # Stale path check
                if not os.path.exists(p):
                    stale_paths.append(p)
                    continue

                rec = IndexedFileRecord(
                    path=p,
                    filename=r["filename"],
                    extension=r["extension"],
                    size_bytes=r["size_bytes"],
                    mtime=r["mtime"],
                    project_alias=r["project_alias"],
                    created_by_jarvis=bool(r["created_by_jarvis"]),
                    tags=r["tags"],
                    indexed_at=r["indexed_at"]
                )
                records.append(rec)
                if len(records) >= limit:
                    break

            # Clean up stale paths asynchronously
            if stale_paths:
                for sp in stale_paths:
                    conn.execute("DELETE FROM files_indexed WHERE path = ?", (sp,))
                conn.commit()
                logger.info(f"[FILE_MEMORY] Pruned {len(stale_paths)} stale paths from index.")

        return records

    def start_background_indexing(self, custom_roots: Optional[List[Path]] = None):
        """Launches a non-blocking background indexing scan."""
        if self._is_indexing:
            logger.info("[FILE_MEMORY] Indexing scan already in progress.")
            return

        def _worker():
            self._is_indexing = True
            try:
                self._run_indexing_scan(custom_roots)
            finally:
                self._is_indexing = False

        self._indexing_thread = threading.Thread(target=_worker, daemon=True, name="JarvisFileIndexer")
        self._indexing_thread.start()
        logger.info("[FILE_MEMORY] Background file indexer started.")

    def _run_indexing_scan(self, custom_roots: Optional[List[Path]] = None):
        """Scans permitted directories and indexes supported files."""
        roots = custom_roots or [
            path_resolver.get_known_folder("desktop"),
            path_resolver.get_known_folder("documents"),
            path_resolver.get_known_folder("downloads")
        ]

        total_indexed = 0
        now = time.time()

        for root in roots:
            if not root or not root.exists():
                continue
            logger.info(f"[FILE_MEMORY] Indexing directory: {root}")

            try:
                for dirpath, dirnames, filenames in os.walk(str(root)):
                    # Exclude sensitive / heavy directories
                    dirnames[:] = [
                        d for d in dirnames
                        if d.lower() not in self.EXCLUDED_DIRS and not d.startswith(".")
                    ]

                    for fn in filenames:
                        ext = Path(fn).suffix.lower()
                        if ext in self.SUPPORTED_EXTENSIONS:
                            full_path = os.path.join(dirpath, fn)
                            try:
                                stat = os.stat(full_path)
                                with self._get_connection() as conn:
                                    conn.execute("""
                                        INSERT OR REPLACE INTO files_indexed
                                        (path, filename, extension, size_bytes, mtime, project_alias, created_by_jarvis, tags, indexed_at)
                                        VALUES (?, ?, ?, ?, ?, '', 0, '', ?)
                                    """, (full_path, fn, ext, stat.st_size, stat.st_mtime, now))
                                    conn.commit()
                                total_indexed += 1
                            except Exception as ex:
                                logger.debug(f"Failed to index file {full_path}: {ex}")

            except Exception as e:
                logger.warning(f"[FILE_MEMORY] Error scanning root {root}: {e}")

        logger.info(f"[FILE_MEMORY] Indexing completed. Indexed {total_indexed} files.")

    def open_in_explorer(self, file_path: str) -> bool:
        """Opens the folder containing the file in Windows File Explorer and selects it."""
        p = Path(file_path).resolve()
        if not p.exists():
            logger.warning(f"File does not exist: {file_path}")
            return False

        try:
            import subprocess
            if sys.platform.startswith("win"):
                # Select the specific file in Explorer
                subprocess.Popen(f'explorer /select,"{p}"')
                return True
            else:
                os.startfile(str(p.parent))
                return True
        except Exception as e:
            logger.error(f"Failed to open explorer for '{file_path}': {e}")
            return False


# Global singleton instance
file_memory_manager = FileMemoryManager()
