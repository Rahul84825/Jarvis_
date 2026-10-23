"""Safe File Creation & Language-Aware Code Generation Engine for JARVIS.

Supports:
- Multi-language registry (Python, C++, Java, JS/TS, React, SQL, Markdown, HTML, Shell, JSON)
- Conversational save-location workflow
- Atomic writes via temporary files
- Overwrite protection & confirmation
- Syntax validation (AST, JSON, balanced structures)
- Read-back verification
- Separation of file creation from execution
"""

import os
import ast
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Tuple, List

from core.files.path_resolver import path_resolver, PathResolver

logger = logging.getLogger("Jarvis.FileCreator")


@dataclass
class LanguageDefinition:
    """Metadata and validation rules for a programming language or file format."""
    name: str
    extensions: List[str]
    default_ext: str
    comment_prefix: str
    syntax_validator: Optional[str] = None  # "python_ast", "json", "balanced_braces"


@dataclass
class FileCreationResult:
    """Structured outcome of a file creation operation."""
    success: bool
    file_path: Optional[str] = None
    filename: str = ""
    language: str = ""
    file_size_bytes: int = 0
    message: str = ""
    requires_confirmation: bool = False
    existing_file_path: Optional[str] = None
    validation_passed: bool = True
    validation_error: Optional[str] = None


class FileCreator:
    """Manages secure file creation, code generation, and verification."""

    LANGUAGE_REGISTRY: Dict[str, LanguageDefinition] = {
        "python": LanguageDefinition("Python", [".py", ".pyw"], ".py", "#", "python_ast"),
        "cpp": LanguageDefinition("C++", [".cpp", ".cc", ".cxx", ".hpp", ".h"], ".cpp", "//", "balanced_braces"),
        "c": LanguageDefinition("C", [".c", ".h"], ".c", "//", "balanced_braces"),
        "java": LanguageDefinition("Java", [".java"], ".java", "//", "balanced_braces"),
        "javascript": LanguageDefinition("JavaScript", [".js", ".mjs"], ".js", "//", "balanced_braces"),
        "typescript": LanguageDefinition("TypeScript", [".ts"], ".ts", "//", "balanced_braces"),
        "react": LanguageDefinition("React", [".jsx", ".tsx"], ".jsx", "//", "balanced_braces"),
        "html": LanguageDefinition("HTML", [".html", ".htm"], ".html", "<!--"),
        "css": LanguageDefinition("CSS", [".css", ".scss"], ".css", "/*"),
        "sql": LanguageDefinition("SQL", [".sql"], ".sql", "--"),
        "markdown": LanguageDefinition("Markdown", [".md", ".markdown"], ".md", "<!--"),
        "json": LanguageDefinition("JSON", [".json"], ".json", "//", "json"),
        "yaml": LanguageDefinition("YAML", [".yaml", ".yml"], ".yaml", "#"),
        "shell": LanguageDefinition("Shell", [".sh", ".bash"], ".sh", "#"),
        "powershell": LanguageDefinition("PowerShell", [".ps1"], ".ps1", "#")
    }

    def __init__(self, resolver: Optional[PathResolver] = None):
        self.resolver = resolver or path_resolver

    def detect_language_and_extension(self, query: str, filename: Optional[str] = None) -> Tuple[str, str]:
        """Infers programming language and appropriate file extension."""
        # 1. Check filename extension if provided
        if filename:
            ext = Path(filename).suffix.lower()
            for lang_id, lang_def in self.LANGUAGE_REGISTRY.items():
                if ext in lang_def.extensions:
                    return lang_id, ext

        # 2. Check query keywords
        q_lower = query.lower()
        keyword_map = {
            "python": "python",
            "c++": "cpp",
            "cpp": "cpp",
            "c language": "c",
            "java": "java",
            "javascript": "javascript",
            "typescript": "typescript",
            "react": "react",
            "html": "html",
            "css": "css",
            "sql": "sql",
            "markdown": "markdown",
            "readme": "markdown",
            "json": "json",
            "yaml": "yaml",
            "bash": "shell",
            "shell": "shell",
            "powershell": "powershell"
        }
        for kw, lang_id in keyword_map.items():
            if kw in q_lower:
                return lang_id, self.LANGUAGE_REGISTRY[lang_id].default_ext

        # Default fallback
        return "python", ".py"

    def validate_syntax(self, content: str, language: str) -> Tuple[bool, Optional[str]]:
        """Performs syntax sanity validation before writing to disk."""
        lang_def = self.LANGUAGE_REGISTRY.get(language)
        if not lang_def or not lang_def.syntax_validator:
            return True, None

        validator = lang_def.syntax_validator
        if validator == "python_ast":
            try:
                ast.parse(content)
                return True, None
            except SyntaxError as e:
                return False, f"Python SyntaxError at line {e.lineno}: {e.msg}"

        elif validator == "json":
            try:
                json.loads(content)
                return True, None
            except json.JSONDecodeError as e:
                return False, f"JSONDecodeError: {e}"

        elif validator == "balanced_braces":
            stack = []
            mapping = {')': '(', '}': '{', ']': '['}
            for ch in content:
                if ch in "({[":
                    stack.append(ch)
                elif ch in ")}]":
                    if not stack or stack[-1] != mapping[ch]:
                        return False, f"Mismatched closing bracket '{ch}'"
                    stack.pop()
            if stack:
                return False, f"Unclosed bracket: '{stack[-1]}'"
            return True, None

        return True, None

    def create_file(
        self,
        filename: str,
        destination: str,
        content: str,
        language: Optional[str] = None,
        allow_overwrite: bool = False
    ) -> FileCreationResult:
        """Safely creates and verifies a file on disk."""
        # 1. Determine language
        detected_lang, def_ext = self.detect_language_and_extension(filename, filename)
        final_lang = language or detected_lang

        # Ensure correct extension
        clean_fn = filename.strip()
        if not Path(clean_fn).suffix:
            clean_fn += self.LANGUAGE_REGISTRY.get(final_lang, self.LANGUAGE_REGISTRY["python"]).default_ext

        # 2. Resolve destination path
        dest_path, friendly_loc = self.resolver.resolve_destination(destination)
        if not dest_path:
            return FileCreationResult(
                success=False,
                filename=clean_fn,
                language=final_lang,
                message=f"Could not resolve destination folder '{destination}'."
            )

        # 3. Path safety check
        target_file = dest_path / clean_fn
        if not self.resolver.is_safe_path(target_file):
            return FileCreationResult(
                success=False,
                filename=clean_fn,
                language=final_lang,
                message=f"Access denied: Path '{target_file}' is in a protected system directory."
            )

        # 4. Overwrite guard
        if target_file.exists() and not allow_overwrite:
            return FileCreationResult(
                success=False,
                filename=clean_fn,
                language=final_lang,
                file_path=str(target_file),
                existing_file_path=str(target_file),
                requires_confirmation=True,
                message=(
                    f"A file named '{clean_fn}' already exists in {friendly_loc}. "
                    f"Would you like me to overwrite it, or choose a different filename?"
                )
            )

        # 5. Syntax validation
        valid, val_err = self.validate_syntax(content, final_lang)
        if not valid and val_err:
            logger.warning(f"Syntax validation warning for {clean_fn}: {val_err}")

        # 6. Atomic file write
        try:
            dest_path.mkdir(parents=True, exist_ok=True)
            tmp_file = dest_path / f".tmp_{clean_fn}_{os.getpid()}"

            with open(tmp_file, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            # Atomic rename / replace
            os.replace(tmp_file, target_file)

        except Exception as e:
            logger.error(f"Failed to write file '{target_file}': {e}")
            if 'tmp_file' in locals() and tmp_file.exists():
                try: tmp_file.unlink()
                except Exception: pass
            return FileCreationResult(
                success=False,
                filename=clean_fn,
                language=final_lang,
                message=f"Failed to create file: {e}"
            )

        # 7. Read-back verification
        if not target_file.exists() or target_file.stat().st_size == 0:
            return FileCreationResult(
                success=False,
                filename=clean_fn,
                language=final_lang,
                message="Read-back verification failed: File was not created or is empty."
            )

        file_size = target_file.stat().st_size
        logger.info(f"[FILE_CREATED] Successfully created '{target_file}' ({file_size} bytes). Verified.")

        # 8. Record in file memory
        try:
            from core.files.file_memory import file_memory_manager
            file_memory_manager.record_created_file(
                path=str(target_file),
                filename=clean_fn,
                language=final_lang,
                size_bytes=file_size
            )
        except Exception as ex:
            logger.debug(f"Could not record file in memory: {ex}")

        # 8B. Invalidate AI cache entries for this modified file (Section 7)
        try:
            from core.ai.caching import nemotron_cache
            nemotron_cache.invalidate_by_file(str(target_file))
        except Exception as e:
            logger.debug(f"Cache invalidation error on file write: {e}")

        return FileCreationResult(
            success=True,
            file_path=str(target_file),
            filename=clean_fn,
            language=final_lang,
            file_size_bytes=file_size,
            validation_passed=valid,
            validation_error=val_err,
            message=f"Created `{clean_fn}` in your {friendly_loc}. The file has been verified, and I can explain or run it next."
        )


# Global singleton instance
file_creator = FileCreator()
