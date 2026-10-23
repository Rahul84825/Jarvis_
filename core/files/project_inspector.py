"""Project-Aware Code Inspector & Modification Planner for JARVIS.

Inspects project architecture, conventions, frameworks, dependencies,
and generates structured modification plans with diff previews.
"""

import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

logger = logging.getLogger("Jarvis.ProjectInspector")


@dataclass
class ProjectMetadata:
    """Discovered project structure and conventions."""
    root_path: str
    name: str
    framework: str = "Generic"
    package_manager: str = "Unknown"
    languages: List[str] = field(default_factory=list)
    entry_point: Optional[str] = None
    config_files: List[str] = field(default_factory=list)
    is_git: bool = False


@dataclass
class ModificationPlan:
    """Structured preview of files to be created, updated, or tested."""
    project_root: str
    intent_summary: str
    files_to_create: List[Dict[str, str]] = field(default_factory=list)  # [{"path": "...", "description": "..."}]
    files_to_modify: List[Dict[str, str]] = field(default_factory=list)  # [{"path": "...", "diff": "..."}]
    dependencies_to_add: List[str] = field(default_factory=list)
    test_commands: List[str] = field(default_factory=list)


class ProjectInspector:
    """Inspects existing project directories to understand architecture and conventions."""

    FRAMEWORK_SIGNATURES = {
        "FastAPI": ["fastapi", "uvicorn"],
        "Flask": ["flask"],
        "Django": ["django", "manage.py"],
        "Next.js": ["next.config.js", "next.config.mjs", "next.config.ts"],
        "React": ["react", "react-dom"],
        "Express": ["express"],
        "PyQt6": ["PyQt6", "pyqt6"],
        "CMake": ["CMakeLists.txt"]
    }

    def inspect_project(self, project_path: str) -> ProjectMetadata:
        """Analyzes a project directory and returns architectural metadata."""
        p = Path(project_path).resolve()
        name = p.name
        framework = "Standard Python"
        pkg_manager = "pip"
        languages = set()
        config_files = []
        entry_point = None

        if not p.exists() or not p.is_dir():
            return ProjectMetadata(root_path=str(p), name=name)

        # Check git
        is_git = (p / ".git").exists()

        # Check config & dependency files
        for item in p.iterdir():
            fn = item.name.lower()
            if fn in ["requirements.txt", "pyproject.toml", "setup.py"]:
                pkg_manager = "pip / poetry"
                languages.add("Python")
                config_files.append(item.name)
            elif fn in ["package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml"]:
                pkg_manager = "npm / yarn / pnpm"
                languages.add("JavaScript")
                config_files.append(item.name)
            elif fn in ["carg.toml"]:
                pkg_manager = "cargo"
                languages.add("Rust")
            elif fn in ["cmakelists.txt"]:
                pkg_manager = "cmake"
                languages.add("C++")

            # Check potential entry points
            if fn in ["main.py", "app.py", "index.js", "server.js", "index.ts", "main.cpp"]:
                entry_point = item.name

        # Detect Framework from dependencies or files
        req_file = p / "requirements.txt"
        if req_file.exists():
            try:
                content = req_file.read_text(encoding="utf-8", errors="ignore").lower()
                for fw, sigs in self.FRAMEWORK_SIGNATURES.items():
                    if any(s.lower() in content for s in sigs):
                        framework = fw
                        break
            except Exception:
                pass

        pkg_json = p / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8", errors="ignore"))
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                for fw, sigs in self.FRAMEWORK_SIGNATURES.items():
                    if any(s.lower() in deps for s in sigs):
                        framework = fw
                        break
            except Exception:
                pass

        return ProjectMetadata(
            root_path=str(p),
            name=name,
            framework=framework,
            package_manager=pkg_manager,
            languages=sorted(list(languages)) if languages else ["Python"],
            entry_point=entry_point,
            config_files=config_files,
            is_git=is_git
        )

    def generate_modification_plan(
        self,
        project_path: str,
        user_request: str
    ) -> ModificationPlan:
        """Creates a preview plan for modifications within a project."""
        meta = self.inspect_project(project_path)
        plan = ModificationPlan(
            project_root=str(meta.root_path),
            intent_summary=f"Implement: {user_request} (Framework: {meta.framework})"
        )

        # Predict target files based on request
        if "api" in user_request.lower() or "endpoint" in user_request.lower() or "route" in user_request.lower():
            if "fastapi" in meta.framework.lower() or "flask" in meta.framework.lower():
                plan.files_to_create.append({
                    "path": str(Path(meta.root_path) / "routers" / "new_endpoint.py"),
                    "description": "API Router definition for the requested endpoint"
                })
            else:
                plan.files_to_create.append({
                    "path": str(Path(meta.root_path) / "api" / "route.py"),
                    "description": "API route handler"
                })

        return plan


# Global singleton instance
project_inspector = ProjectInspector()
