"""User Profile and Preference Manager for JARVIS.
Loads and manages user profile, active project context, permanent instructions,
and persistent memories from config/profile.json or ~/.jarvis/profile.json.
Reference: https://jarvis.institute/guide/#profile
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger("Jarvis.ProfileManager")

DEFAULT_PROFILE = {
    "name": "Active Gamer",
    "role": "Lead Architect & Implementation Engineer",
    "projects": ["jarvis"],
    "instructions": [
        "Prefer concise and actionable answers.",
        "Keep local system commands fast and offline.",
        "Verify outcomes before reporting completion."
    ],
    "memories": [
        "Project jarvis is a native Python and PyQt desktop assistant.",
        "Prefers local execution over unnecessary cloud API calls."
    ]
}

class ProfileManager:
    """Manages user profile, persistent memory, and bounded prompt context injection."""

    def __init__(self, profile_path: Optional[str] = None):
        if profile_path:
            self.profile_path = Path(profile_path)
        else:
            base_dir = Path(__file__).parent.parent
            # Check ~/.jarvis/profile.json first, else config/profile.json
            user_home_profile = Path.home() / ".jarvis" / "profile.json"
            if user_home_profile.exists():
                self.profile_path = user_home_profile
            else:
                self.profile_path = base_dir / "config" / "profile.json"

        self.profile: Dict[str, Any] = self._load_profile()
        logger.info(f"ProfileManager loaded user profile for: '{self.profile.get('name', 'User')}'")

    def _load_profile(self) -> Dict[str, Any]:
        """Loads profile from JSON file or writes default profile if absent."""
        if self.profile_path.exists():
            try:
                with open(self.profile_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return {**DEFAULT_PROFILE, **data}
            except Exception as e:
                logger.error(f"Error loading profile from {self.profile_path}: {e}")

        # Ensure directory exists and write default profile
        try:
            self.profile_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.profile_path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_PROFILE, f, indent=4)
        except Exception as e:
            logger.warning(f"Failed to save default profile: {e}")

        return dict(DEFAULT_PROFILE)

    def save_profile(self) -> bool:
        """Saves current in-memory profile to disk."""
        try:
            self.profile_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.profile_path, "w", encoding="utf-8") as f:
                json.dump(self.profile, f, indent=4)
            return True
        except Exception as e:
            logger.error(f"Failed to persist profile: {e}")
            return False

    def add_memory(self, memory_text: str) -> bool:
        """Appends a new persistent memory entry."""
        clean = memory_text.strip()
        if not clean:
            return False
        memories = self.profile.setdefault("memories", [])
        if clean not in memories:
            memories.append(clean)
            logger.info(f"[MEMORY] Saved new persistent memory: '{clean}'")
            return self.save_profile()
        return True

    def query_memories(self, topic: str) -> List[str]:
        """Searches persistent memories for relevant keywords."""
        if not topic or not topic.strip():
            return list(self.profile.get("memories", []))
        words = [w.lower() for w in topic.strip().split() if len(w) > 2]
        matches = []
        for mem in self.profile.get("memories", []):
            mem_lower = mem.lower()
            if any(w in mem_lower for w in words):
                matches.append(mem)
        return matches if matches else list(self.profile.get("memories", []))

    def forget_memory(self, topic: str) -> bool:
        """Removes memory entries matching topic string."""
        topic_lower = topic.strip().lower()
        memories = self.profile.get("memories", [])
        initial_len = len(memories)
        self.profile["memories"] = [m for m in memories if topic_lower not in m.lower()]
        if len(self.profile["memories"]) < initial_len:
            logger.info(f"[MEMORY] Removed memories matching '{topic}'")
            return self.save_profile()
        return False

    def get_bounded_prompt_context(self) -> str:
        """Generates a concise, token-bounded context summary for LLM prompts.
        Ensures context injection does not overload prompt length.
        """
        name = self.profile.get("name", "User")
        role = self.profile.get("role", "")
        instructions = self.profile.get("instructions", [])[:2]
        memories = self.profile.get("memories", [])[:2]

        lines = [f"User Name: {name}"]
        if role: lines.append(f"User Role: {role}")
        if instructions: lines.append("Preferences: " + "; ".join(instructions))
        if memories: lines.append("Context: " + "; ".join(memories))
        return "\n".join(lines)


# Global Singleton Instance
profile_manager = ProfileManager()
