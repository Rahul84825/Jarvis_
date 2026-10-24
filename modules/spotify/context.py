"""Conversational Spotify Context Tracker for Multi-turn tasks.

Remembers:
- Active target playlist (ID, name, and latest verified snapshot of tracks).
- Enables ordinal track references ("remove the second one", "move the third song to the top").
- Remembers active/preferred playback device.
- Stores pending destructive confirmations and track disambiguation options.
"""

import time
import logging
from typing import Optional, List, Dict, Any, Tuple
from modules.spotify.models import SpotifyTrack, SpotifyPlaylist, SpotifyDevice

logger = logging.getLogger("Jarvis.Spotify.Context")


class SpotifyContext:
    """Manages active Spotify conversation state across multiple turns."""

    def __init__(self, ttl_seconds: float = 300.0):
        self.ttl_seconds = ttl_seconds
        self.active_playlist_id: Optional[str] = None
        self.active_playlist_name: Optional[str] = None
        self.active_playlist_tracks: List[SpotifyTrack] = []
        self.active_device_id: Optional[str] = None
        self.active_device_name: Optional[str] = None
        self.last_search_results: List[SpotifyTrack] = []
        self.pending_confirmation: Optional[Dict[str, Any]] = None
        self.last_updated: float = time.time()

    def update_timestamp(self):
        self.last_updated = time.time()

    def is_expired(self) -> bool:
        return (time.time() - self.last_updated) > self.ttl_seconds

    def set_active_playlist(self, playlist_id: str, playlist_name: str, tracks: Optional[List[SpotifyTrack]] = None):
        """Sets the active playlist context with an optional track snapshot."""
        self.active_playlist_id = playlist_id
        self.active_playlist_name = playlist_name
        if tracks is not None:
            self.active_playlist_tracks = list(tracks)
        self.update_timestamp()
        logger.info(f"Updated Spotify context: Active playlist = '{playlist_name}' ({playlist_id}), {len(self.active_playlist_tracks)} tracks in snapshot.")

    def update_playlist_tracks(self, tracks: List[SpotifyTrack]):
        """Updates the verified tracks snapshot of the active playlist."""
        self.active_playlist_tracks = list(tracks)
        self.update_timestamp()

    def set_active_device(self, device_id: str, device_name: str):
        self.active_device_id = device_id
        self.active_device_name = device_name
        self.update_timestamp()
        logger.info(f"Updated Spotify context: Active device = '{device_name}' ({device_id})")

    def resolve_track_by_index(self, index_1_based: int) -> Optional[SpotifyTrack]:
        """Resolves a track by 1-based index (e.g. 'the second song' -> index 2 -> item 1)."""
        idx = index_1_based - 1
        if 0 <= idx < len(self.active_playlist_tracks):
            return self.active_playlist_tracks[idx]
        return None

    def resolve_track_by_name(self, track_name: str, artist: Optional[str] = None) -> Optional[SpotifyTrack]:
        """Resolves a track by title/artist within the active playlist snapshot."""
        if not self.active_playlist_tracks:
            return None

        clean_name = track_name.lower().strip()
        clean_artist = artist.lower().strip() if artist else ""

        # Exact match (name + artist)
        if clean_artist:
            for t in self.active_playlist_tracks:
                if clean_name in t.name.lower() and clean_artist in t.artist.lower():
                    return t

        # Exact name match
        for t in self.active_playlist_tracks:
            if clean_name == t.name.lower():
                return t

        # Partial substring match
        for t in self.active_playlist_tracks:
            if clean_name in t.name.lower() or t.name.lower() in clean_name:
                return t

        return None

    def set_pending_confirmation(
        self,
        action: str,
        target_id: str,
        target_name: str,
        description: str,
        params: Optional[Dict[str, Any]] = None
    ):
        """Sets a pending destructive action awaiting user confirmation."""
        self.pending_confirmation = {
            "action": action,
            "target_id": target_id,
            "target_name": target_name,
            "description": description,
            "params": params or {},
            "timestamp": time.time()
        }
        self.update_timestamp()

    def get_pending_confirmation(self) -> Optional[Dict[str, Any]]:
        if not self.pending_confirmation:
            return None
        # Timeout after 60 seconds
        if time.time() - self.pending_confirmation.get("timestamp", 0) > 60.0:
            self.pending_confirmation = None
            return None
        return self.pending_confirmation

    def clear_pending_confirmation(self):
        self.pending_confirmation = None

    def clear_all(self):
        self.active_playlist_id = None
        self.active_playlist_name = None
        self.active_playlist_tracks = []
        self.active_device_id = None
        self.active_device_name = None
        self.last_search_results = []
        self.pending_confirmation = None
        self.last_updated = time.time()


# Global singleton context
spotify_context = SpotifyContext()
