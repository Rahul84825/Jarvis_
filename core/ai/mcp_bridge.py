import os
import json
import logging
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger("Jarvis.MCPBridge")


class MCPBridge:
    """Discovers and interfaces with local Model Context Protocol (MCP) servers
    configured in ~/.claude.json, and enables headless Claude CLI reasoning turns.
    """

    def __init__(self):
        self.config_path = Path.home() / ".claude.json"
        self._servers = self._load_mcp_servers()
        self.claude_cli_path = shutil.which("claude")

    def _load_mcp_servers(self) -> Dict[str, Any]:
        """Loads configured MCP servers from ~/.claude.json."""
        if not self.config_path.exists():
            return {}

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            servers = data.get("mcpServers", {}) or {}
            # Check project level servers if home directory has projects
            home_str = str(Path.home())
            project_servers = data.get("projects", {}).get(home_str, {}).get("mcpServers", {}) or {}
            servers.update(project_servers)
            return servers
        except Exception as e:
            logger.warning(f"Could not parse ~/.claude.json: {e}")
            return {}

    def get_configured_servers(self) -> Dict[str, Any]:
        """Returns the dictionary of configured MCP servers."""
        return self._load_mcp_servers()

    def has_claude_cli(self) -> bool:
        """Returns True if the Claude Code CLI is available on PATH."""
        return self.claude_cli_path is not None

    def execute_claude_query(self, user_prompt: str, timeout: float = 30.0) -> Optional[str]:
        """Executes a single headless turn via the local Claude CLI."""
        if not self.has_claude_cli():
            logger.debug("Claude CLI not found on PATH.")
            return None

        try:
            cmd = ["claude", "-p", user_prompt]
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip()
            logger.warning(f"Claude CLI error (exit {result.returncode}): {result.stderr}")
            return None
        except subprocess.TimeoutExpired:
            logger.warning("Claude CLI query timed out.")
            return None
        except Exception as e:
            logger.error(f"Failed to execute Claude CLI: {e}")
            return None


mcp_bridge = MCPBridge()
