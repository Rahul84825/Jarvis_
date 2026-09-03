import json
import logging
from pathlib import Path
from config import config
from core.platform.platform_manager import platform_manager

logger = logging.getLogger("Jarvis.WebControl")

class WebControl:
    """Configurable Web Link Controller.
    Loads site-to-URL mappings dynamically from config/links.json and opens websites.
    """

    def __init__(self):
        self.links_file = getattr(config, 'links_path', Path(config.BASE_DIR) / "config" / "links.json")
        self.links = self._load_links()

    def _load_links(self) -> dict:
        """Loads URL mappings from JSON configuration."""
        if Path(self.links_file).exists():
            try:
                with open(self.links_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    logger.info(f"Loaded {len(data)} website link mappings from {self.links_file}")
                    return {k.lower().strip(): v for k, v in data.items()}
            except Exception as e:
                logger.error(f"Failed to load links.json: {e}")
        return {}

    def get_supported_sites(self) -> list:
        """Returns list of all configured site names."""
        if not self.links:
            self.links_file = getattr(config, 'links_path', Path(config.BASE_DIR) / "config" / "links.json")
            self.links = self._load_links()
        return sorted(list(self.links.keys()))

    def open_website(self, site_name: str) -> (bool, str):
        """Opens a website in the default browser by name or direct URL.

        Args:
            site_name: Standardized site key (e.g., 'youtube', 'github') or direct URL.

        Returns:
            Tuple of (success: bool, message: str)
        """
        if not site_name:
            return False, "No website specified."

        key = site_name.lower().strip()
        url = self.links.get(key)

        if not url:
            if key.startswith("http://") or key.startswith("https://"):
                url = key
            elif "." in key and " " not in key:
                url = f"https://{key}"
            else:
                return False, f"Website '{site_name}' is not in configured links."

        try:
            logger.info(f"Opening web URL: {url} for target '{site_name}'")
            success = platform_manager.open_url(url)
            display_name = site_name.title()
            if success:
                return True, f"Opening {display_name} in your default browser."
            return False, f"Failed to open website {display_name}."
        except Exception as e:
            logger.error(f"Failed to open website '{site_name}': {e}")
            return False, f"Failed to open website: {e}"

# Global instance
web_control = WebControl()
