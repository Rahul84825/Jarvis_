"""JARVIS File Management, Creation, and Project Subsystem."""

from core.files.path_resolver import path_resolver, PathResolver
from core.files.file_creator import file_creator, FileCreator, FileCreationResult, LanguageDefinition
from core.files.file_memory import file_memory_manager, FileMemoryManager, IndexedFileRecord
from core.files.project_inspector import project_inspector, ProjectInspector, ProjectMetadata, ModificationPlan

__all__ = [
    "path_resolver",
    "PathResolver",
    "file_creator",
    "FileCreator",
    "FileCreationResult",
    "LanguageDefinition",
    "file_memory_manager",
    "FileMemoryManager",
    "IndexedFileRecord",
    "project_inspector",
    "ProjectInspector",
    "ProjectMetadata",
    "ModificationPlan"
]
