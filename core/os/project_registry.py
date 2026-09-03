import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from config import BASE_DIR

logger = logging.getLogger("Jarvis.ProjectRegistry")

class ProjectRegistry:
    """Configurable Project Registry (`config/projects.json`) & Context Manager.
    Maps project aliases (e.g., 'jarvis', 'wellmeds') to local filesystem directories and maintains
    current working project context across voice interactions.
    """

    def __init__(self, config_path: str = None):
        self.config_path = Path(config_path) if config_path else BASE_DIR / "config" / "projects.json"
        self.projects: Dict[str, str] = {}
        self.current_project_alias: Optional[str] = "jarvis"
        self.load()

    def load(self):
        """Loads projects mapping from config/projects.json."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self.projects = json.load(f)
                logger.info(f"[PROJECT_REGISTRY] Loaded {len(self.projects)} projects from '{self.config_path}'")
            except Exception as e:
                logger.error(f"[PROJECT_REGISTRY_ERROR] Error loading projects.json: {e}")
        else:
            # Default fallback
            self.projects = {
                "jarvis": str(BASE_DIR)
            }
            self.save()

    def save(self):
        """Saves project registry to config/projects.json."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self.projects, f, indent=2)
        except Exception as e:
            logger.error(f"[PROJECT_REGISTRY_ERROR] Error saving projects.json: {e}")

    def get_project_path(self, alias_or_name: str) -> Optional[str]:
        """Looks up project filesystem path by alias or name."""
        if not alias_or_name:
            return None
        key = alias_or_name.lower().strip()
        path_str = self.projects.get(key)
        if path_str and os.path.exists(path_str):
            return path_str
        return None

    def register_project(self, alias: str, path: str):
        """Registers a new project mapping."""
        key = alias.lower().strip()
        self.projects[key] = str(Path(path).resolve())
        self.save()
        logger.info(f"[PROJECT_REGISTRY] Registered project '{key}' -> '{self.projects[key]}'")

    def set_current_project(self, alias_or_name: str) -> bool:
        """Sets active working project context."""
        key = alias_or_name.lower().strip()
        path_str = self.get_project_path(key)
        if path_str:
            self.current_project_alias = key
            logger.info(f"[PROJECT_CONTEXT] Switched working project context to '{key}' ({path_str})")
            return True
        logger.warning(f"[PROJECT_CONTEXT_FAILED] Project '{key}' not found in registry.")
        return False

    def get_current_project(self) -> Dict[str, str]:
        """Returns current active project context details."""
        alias = self.current_project_alias or "jarvis"
        path_str = self.get_project_path(alias) or str(BASE_DIR)
        return {
            "alias": alias,
            "path": path_str
        }
