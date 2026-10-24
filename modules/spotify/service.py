"""High-Level Spotify Tool Service for Santra.

Integrates Spotify Web API with Santra's tool registry, permissions, context, and desktop automation.
Complies with Spotify policies:
- Explicit unfollow semantics for playlist removal (accurate explanation, no false claims of permanent deletion).
- Safe confirmation gates for destructive actions (unfollow, replace tracks, deduplication).
- Premium requirement detection & graceful Windows media keys fallback.
- Active device detection, intelligent resolution, and prompt when no player is running.
- Thread-safe playlist mutations with locking.
"""

import time
import re
import logging
import threading
from typing import Optional, List, Dict, Any, Tuple, Union

from modules.spotify.models import (
    SpotifyTrack, SpotifyPlaylist, SpotifyDevice, SpotifyUser,
    PlaybackState, DuplicateReport, DuplicateGroup
)
from modules.spotify.client import (
    SpotifyClient, spotify_client, SpotifyApiError,
    SpotifyPremiumRequiredError, SpotifyNoActiveDeviceError, SpotifyRateLimitError
)
from modules.spotify.context import SpotifyContext, spotify_context

logger = logging.getLogger("Jarvis.Spotify.Service")


class SpotifyService:
    """Core Spotify Tool Service."""

    def __init__(self, client: Optional[SpotifyClient] = None, context: Optional[SpotifyContext] = None):
        self.client = client or spotify_client
        self.context = context or spotify_context
        self._mutation_lock = threading.RLock()

    # =========================================================================
    # Account & Profile
    # =========================================================================

    def get_profile(self) -> SpotifyUser:
        """Retrieves the current user's Spotify profile (cached for 60s)."""
        data = self.client.get("me", cache_ttl=60.0)
        return SpotifyUser.from_api(data)

    def is_connected(self) -> bool:
        """Checks if Spotify is currently authorized and connected."""
        return self.client.oauth.is_connected()

    # =========================================================================
    # Playlists Listing & Inspection
    # =========================================================================

    def list_playlists(self, limit: int = 50) -> List[SpotifyPlaylist]:
        """Lists user's playlists (cached for 20s)."""
        data = self.client.get("me/playlists", params={"limit": min(limit, 50)}, cache_ttl=20.0)
        items = data.get("items", []) if isinstance(data, dict) else []
        playlists = [SpotifyPlaylist.from_api(p) for p in items if p]
        return playlists

    def get_playlist(self, playlist_id: str) -> SpotifyPlaylist:
        """Gets full playlist metadata."""
        data = self.client.get(f"playlists/{playlist_id}")
        return SpotifyPlaylist.from_api(data)

    def get_playlist_tracks(self, playlist_id: str, limit: int = 100) -> List[SpotifyTrack]:
        """Gets tracks of a playlist and updates the active context snapshot."""
        data = self.client.get(f"playlists/{playlist_id}/tracks", params={"limit": min(limit, 100)})
        items = data.get("items", []) if isinstance(data, dict) else []
        tracks = [SpotifyTrack.from_api(item) for item in items if item and item.get("track")]

        # Update context snapshot if this is the active playlist
        if self.context.active_playlist_id == playlist_id:
            self.context.update_playlist_tracks(tracks)

        return tracks

    def find_playlist_by_name(self, name: str) -> Optional[SpotifyPlaylist]:
        """Finds a user's playlist by exact or fuzzy case-insensitive title match."""
        playlists = self.list_playlists(limit=50)
        clean = name.lower().strip()
        # 1. Exact match
        for p in playlists:
            if p.name.lower() == clean:
                return p
        # 2. Substring match
        for p in playlists:
            if clean in p.name.lower() or p.name.lower() in clean:
                return p
        return None

    # =========================================================================
    # Search & Disambiguation
    # =========================================================================

    def search_tracks(self, query: str, limit: int = 10) -> List[SpotifyTrack]:
        """Searches Spotify catalog for tracks."""
        data = self.client.get("search", params={"q": query, "type": "track", "limit": limit})
        tracks_obj = data.get("tracks", {}) if isinstance(data, dict) else {}
        items = tracks_obj.get("items", []) if isinstance(tracks_obj, dict) else []
        results = [SpotifyTrack.from_api(item) for item in items if item]
        self.context.last_search_results = results
        return results

    def search_item(self, query: str, search_type: str = "track", limit: int = 5) -> List[Dict[str, Any]]:
        """General catalog search for tracks, albums, artists, or playlists."""
        data = self.client.get("search", params={"q": query, "type": search_type, "limit": limit})
        category_key = f"{search_type}s"
        return data.get(category_key, {}).get("items", [])

    def get_saved_tracks(self, limit: int = 50) -> List[SpotifyTrack]:
        """Gets user's saved/liked tracks."""
        data = self.client.get("me/tracks", params={"limit": limit})
        items = data.get("items", []) if isinstance(data, dict) else []
        return [SpotifyTrack.from_api(item) for item in items if item]

    # =========================================================================
    # Playlist Creation & Mutations
    # =========================================================================

    def create_playlist(self, name: str, description: str = "", public: bool = False) -> SpotifyPlaylist:
        """Creates a new playlist for the user and marks it active in conversation context."""
        with self._mutation_lock:
            user = self.get_profile()
            payload = {
                "name": name,
                "description": description or f"Created by Santra AI assistant.",
                "public": public
            }
            data = self.client.post(f"users/{user.id}/playlists", json_data=payload)
            playlist = SpotifyPlaylist.from_api(data)
            self.context.set_active_playlist(playlist.id, playlist.name, tracks=[])
            logger.info(f"Created new playlist: '{playlist.name}' (ID: {playlist.id})")
            return playlist

    def rename_playlist(self, playlist_id: str, new_name: str, description: Optional[str] = None, public: Optional[bool] = None) -> Dict[str, Any]:
        """Renames and updates details of a playlist."""
        with self._mutation_lock:
            payload: Dict[str, Any] = {"name": new_name}
            if description is not None:
                payload["description"] = description
            if public is not None:
                payload["public"] = public

            self.client.put(f"playlists/{playlist_id}", json_data=payload)
            if self.context.active_playlist_id == playlist_id:
                self.context.active_playlist_name = new_name
            return {"success": True, "message": f"Playlist renamed to '{new_name}'."}

    def add_tracks_to_playlist(
        self,
        playlist_id: str,
        track_uris: List[str],
        position: Optional[int] = None
    ) -> Dict[str, Any]:
        """Adds tracks by URIs to a playlist."""
        with self._mutation_lock:
            payload: Dict[str, Any] = {"uris": track_uris}
            if position is not None:
                payload["position"] = position

            self.client.post(f"playlists/{playlist_id}/tracks", json_data=payload)
            # Refresh context tracks
            updated_tracks = self.get_playlist_tracks(playlist_id)
            return {
                "success": True,
                "added_count": len(track_uris),
                "total_tracks": len(updated_tracks),
                "message": f"Added {len(track_uris)} song{'s' if len(track_uris) != 1 else ''} to the playlist."
            }

    def add_tracks_by_search(
        self,
        playlist_name_or_id: Optional[str],
        query: str,
        artist: Optional[str] = None,
        count: int = 1
    ) -> Dict[str, Any]:
        """Natural language helper: searches tracks and adds them to the resolved playlist."""
        # 1. Resolve playlist
        playlist_id = None
        playlist_name = ""
        if playlist_name_or_id:
            found = self.find_playlist_by_name(playlist_name_or_id)
            if found:
                playlist_id = found.id
                playlist_name = found.name
            else:
                playlist_id = playlist_name_or_id
                playlist_name = playlist_name_or_id
        elif self.context.active_playlist_id:
            playlist_id = self.context.active_playlist_id
            playlist_name = self.context.active_playlist_name or "active playlist"
        else:
            return {"success": False, "message": "Which playlist would you like me to add songs to?"}

        # 2. Search for tracks
        search_q = query
        if artist and artist.lower() not in query.lower():
            search_q = f"{query} artist:{artist}"
        tracks = self.search_tracks(search_q, limit=max(count, 5))

        if not tracks:
            return {"success": False, "message": f"I couldn't find any songs matching '{query}' on Spotify."}

        selected_tracks = tracks[:count]
        uris = [t.uri for t in selected_tracks if t.uri]
        res = self.add_tracks_to_playlist(playlist_id, uris)
        track_names = ", ".join(f"'{t.name}' by {t.artist}" for t in selected_tracks)
        return {
            "success": True,
            "playlist_id": playlist_id,
            "playlist_name": playlist_name,
            "added_tracks": selected_tracks,
            "message": f"Added {len(selected_tracks)} song{'s' if len(selected_tracks) != 1 else ''} ({track_names}) to {playlist_name}."
        }

    def remove_tracks_from_playlist(
        self,
        playlist_id: str,
        track_uris: Optional[List[str]] = None,
        positions: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """Removes specific tracks or track positions from a playlist."""
        with self._mutation_lock:
            # Current snapshot
            current_tracks = self.get_playlist_tracks(playlist_id)
            payload: Dict[str, Any] = {}

            if positions is not None:
                # Remove by positions
                track_items = []
                for pos in positions:
                    if 0 <= pos < len(current_tracks):
                        t = current_tracks[pos]
                        track_items.append({"uri": t.uri, "positions": [pos]})
                payload["tracks"] = track_items
            elif track_uris:
                payload["tracks"] = [{"uri": uri} for uri in track_uris]
            else:
                return {"success": False, "message": "No tracks specified to remove."}

            self.client.delete(f"playlists/{playlist_id}/tracks", json_data=payload)
            updated = self.get_playlist_tracks(playlist_id)
            return {
                "success": True,
                "message": "Track removed from playlist.",
                "total_tracks": len(updated)
            }

    def reorder_playlist_tracks(
        self,
        playlist_id: str,
        range_start: int,
        insert_before: int,
        range_length: int = 1
    ) -> Dict[str, Any]:
        """Reorders tracks within a playlist."""
        with self._mutation_lock:
            payload = {
                "range_start": range_start,
                "insert_before": insert_before,
                "range_length": range_length
            }
            self.client.put(f"playlists/{playlist_id}/tracks", json_data=payload)
            self.get_playlist_tracks(playlist_id)  # update snapshot
            return {"success": True, "message": f"Reordered track in playlist."}

    def replace_playlist_tracks(self, playlist_id: str, track_uris: List[str]) -> Dict[str, Any]:
        """Replaces all items in a playlist with new tracks (requires explicit confirmation)."""
        with self._mutation_lock:
            self.client.put(f"playlists/{playlist_id}/tracks", json_data={"uris": track_uris})
            self.get_playlist_tracks(playlist_id)
            return {"success": True, "message": f"Playlist contents replaced with {len(track_uris)} tracks."}

    # =========================================================================
    # Duplicate Detection & Cleanup
    # =========================================================================

    def find_duplicate_tracks(self, playlist_id: str) -> DuplicateReport:
        """Scans a playlist for duplicate tracks (by URI or title+artist)."""
        tracks = self.get_playlist_tracks(playlist_id)
        playlist = self.get_playlist(playlist_id)

        seen: Dict[str, List[int]] = {}
        for idx, t in enumerate(tracks):
            key = t.uri or f"{t.name.lower()}:::{t.artist.lower()}"
            seen.setdefault(key, []).append(idx)

        dup_groups: List[DuplicateGroup] = []
        for key, pos_list in seen.items():
            if len(pos_list) > 1:
                first_t = tracks[pos_list[0]]
                dup_groups.append(DuplicateGroup(
                    track_uri=first_t.uri,
                    track_name=first_t.name,
                    artist=first_t.artist,
                    positions=pos_list
                ))

        return DuplicateReport(
            playlist_id=playlist_id,
            playlist_name=playlist.name,
            duplicate_groups=dup_groups
        )

    def cleanup_duplicates(self, playlist_id: str) -> Dict[str, Any]:
        """Removes redundant occurrences of duplicate tracks, keeping the first occurrence."""
        with self._mutation_lock:
            report = self.find_duplicate_tracks(playlist_id)
            if report.total_duplicates == 0:
                return {"success": True, "removed": 0, "message": "No duplicate tracks found in this playlist."}

            # Collect positions to remove (all except the first occurrence of each group)
            positions_to_remove: List[int] = []
            for g in report.duplicate_groups:
                positions_to_remove.extend(g.positions[1:])

            # Sort descending to safely remove from tail without index shifting
            positions_to_remove.sort(reverse=True)

            res = self.remove_tracks_from_playlist(playlist_id, positions=positions_to_remove)
            return {
                "success": True,
                "removed": len(positions_to_remove),
                "message": f"Cleaned up {len(positions_to_remove)} duplicate track{'s' if len(positions_to_remove) != 1 else ''} from {report.playlist_name}."
            }

    # =========================================================================
    # Playlist Removal (Official Unfollow Semantics)
    # =========================================================================

    def unfollow_playlist(self, playlist_id: str) -> Dict[str, Any]:
        """Removes a playlist from the user's library via official Spotify Unfollow API.
        Accurately reports that Spotify API removes/unfollows the playlist from the library,
        not permanent deletion from Spotify servers.
        """
        with self._mutation_lock:
            # Fetch playlist name before removing
            p_name = "the playlist"
            try:
                p = self.get_playlist(playlist_id)
                p_name = f"'{p.name}'"
            except Exception:
                pass

            self.client.delete(f"playlists/{playlist_id}/followers")

            if self.context.active_playlist_id == playlist_id:
                self.context.clear_all()

            msg = (
                f"{p_name} has been removed from your Spotify library. "
                "(Note: In accordance with Spotify's Web API, the playlist is unfollowed and removed from your profile; "
                "permanent hard deletion is not supported by Spotify's API)."
            )
            return {"success": True, "message": msg}

    # =========================================================================
    # Playback Controls & Devices
    # =========================================================================

    def get_devices(self) -> List[SpotifyDevice]:
        """Retrieves available Spotify Connect playback devices (cached for 5s)."""
        data = self.client.get("me/player/devices", cache_ttl=5.0)
        items = data.get("devices", []) if isinstance(data, dict) else []
        return [SpotifyDevice.from_api(d) for d in items if d]

    def resolve_target_device(self, preferred_name_or_id: Optional[str] = None) -> Tuple[Optional[SpotifyDevice], str]:
        """Selects the best available playback device.
        Prefers active device, or matched device, or stored context device.
        """
        devices = self.get_devices()
        if not devices:
            return None, "No active Spotify devices found. Please launch Spotify on your PC or phone."

        # 1. Match explicitly requested device
        if preferred_name_or_id:
            clean_pref = preferred_name_or_id.lower().strip()
            for d in devices:
                if d.id == preferred_name_or_id or clean_pref in d.name.lower():
                    return d, f"Selected requested device: {d.name}"

        # 2. Prefer context device if available
        if self.context.active_device_id:
            for d in devices:
                if d.id == self.context.active_device_id:
                    return d, f"Using current context device: {d.name}"

        # 3. Prefer currently active device
        for d in devices:
            if d.is_active:
                return d, f"Using active device: {d.name}"

        # 4. If only one device exists, use it
        if len(devices) == 1:
            return devices[0], f"Using available device: {devices[0].name}"

        # Multiple devices available, none active
        names = ", ".join(d.name for d in devices)
        return devices[0], f"Multiple devices found ({names}). Defaulting to {devices[0].name}."

    def get_current_playback(self) -> Optional[PlaybackState]:
        """Retrieves currently playing track and player status."""
        try:
            data = self.client.get("me/player")
            if not data or data.get("status_code") == 204:
                return None
            return PlaybackState.from_api(data)
        except (SpotifyNoActiveDeviceError, SpotifyApiError):
            return None

    def play(
        self,
        context_uri: Optional[str] = None,
        uris: Optional[List[str]] = None,
        offset: Optional[Dict[str, Any]] = None,
        position_ms: Optional[int] = None,
        device_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Starts or resumes playback."""
        device, dev_msg = self.resolve_target_device(device_id)
        target_dev_id = device.id if device else None

        params = {}
        if target_dev_id:
            params["device_id"] = target_dev_id

        payload: Dict[str, Any] = {}
        if context_uri:
            payload["context_uri"] = context_uri
        elif uris:
            payload["uris"] = uris

        if offset:
            payload["offset"] = offset
        if position_ms is not None:
            payload["position_ms"] = position_ms

        try:
            self.client.put("me/player/play", json_data=payload if payload else None, params=params if params else None)
            if device:
                self.context.set_active_device(device.id, device.name)
            return {"success": True, "message": f"Playback started on {device.name if device else 'Spotify'}."}
        except SpotifyPremiumRequiredError:
            # Fallback to local desktop automation
            logger.warning("Web API play failed: Spotify Premium required. Falling back to desktop media key.")
            self._fallback_desktop_media_key("play")
            return {
                "success": True,
                "fallback": True,
                "message": "Spotify Web API playback requires Spotify Premium. Triggered local desktop media playback as a fallback."
            }
        except SpotifyNoActiveDeviceError:
            return {
                "success": False,
                "message": "No active Spotify playback device detected. Please open Spotify on your PC or phone."
            }

    def play_playlist(self, playlist_name_or_id: str, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Plays a playlist by name or URI."""
        playlist = self.find_playlist_by_name(playlist_name_or_id)
        if not playlist:
            # Check if it's already an ID or URI
            p_uri = playlist_name_or_id if playlist_name_or_id.startswith("spotify:playlist:") else f"spotify:playlist:{playlist_name_or_id}"
            p_name = playlist_name_or_id
        else:
            p_uri = playlist.uri
            p_name = playlist.name
            self.context.set_active_playlist(playlist.id, playlist.name)

        return self.play(context_uri=p_uri, device_id=device_id)

    def play_liked_songs(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Plays the user's saved/liked tracks."""
        tracks = self.get_saved_tracks(limit=50)
        if not tracks:
            return {"success": False, "message": "You don't have any saved tracks in your Spotify library."}
        uris = [t.uri for t in tracks if t.uri]
        return self.play(uris=uris, device_id=device_id)

    def pause(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Pauses playback."""
        device, _ = self.resolve_target_device(device_id)
        params = {"device_id": device.id} if device else {}
        try:
            self.client.put("me/player/pause", params=params)
            return {"success": True, "message": "Playback paused."}
        except SpotifyPremiumRequiredError:
            self._fallback_desktop_media_key("pause")
            return {"success": True, "fallback": True, "message": "Spotify Web API requires Premium. Toggled local media keys as fallback."}
        except SpotifyNoActiveDeviceError:
            return {"success": False, "message": "No active Spotify player to pause."}

    def next_track(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Skips to next track."""
        device, _ = self.resolve_target_device(device_id)
        params = {"device_id": device.id} if device else {}
        try:
            self.client.post("me/player/next", params=params)
            return {"success": True, "message": "Skipped to next track."}
        except SpotifyPremiumRequiredError:
            self._fallback_desktop_media_key("next")
            return {"success": True, "fallback": True, "message": "Skipped track via local media keys (Spotify Premium required for Web API)."}
        except SpotifyNoActiveDeviceError:
            return {"success": False, "message": "No active Spotify player found."}

    def previous_track(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Returns to previous track."""
        device, _ = self.resolve_target_device(device_id)
        params = {"device_id": device.id} if device else {}
        try:
            self.client.post("me/player/previous", params=params)
            return {"success": True, "message": "Returned to previous track."}
        except SpotifyPremiumRequiredError:
            self._fallback_desktop_media_key("prev")
            return {"success": True, "fallback": True, "message": "Returned to previous track via local media keys."}
        except SpotifyNoActiveDeviceError:
            return {"success": False, "message": "No active Spotify player found."}

    def seek(self, position_ms: int, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Seeks to a specific position in milliseconds."""
        device, _ = self.resolve_target_device(device_id)
        params = {"position_ms": position_ms}
        if device:
            params["device_id"] = device.id
        try:
            self.client.put("me/player/seek", params=params)
            secs = position_ms // 1000
            mins = secs // 60
            s_rem = secs % 60
            return {"success": True, "message": f"Seeked to {mins}:{s_rem:02d}."}
        except SpotifyPremiumRequiredError:
            return {"success": False, "message": "Seeking via Spotify Web API requires Spotify Premium."}

    def set_volume(self, volume_percent: int, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Sets playback volume percentage (0-100)."""
        vol = max(0, min(100, volume_percent))
        device, _ = self.resolve_target_device(device_id)
        params = {"volume_percent": vol}
        if device:
            params["device_id"] = device.id
        try:
            self.client.put("me/player/volume", params=params)
            return {"success": True, "message": f"Spotify volume set to {vol}%."}
        except SpotifyPremiumRequiredError:
            return {"success": False, "message": "Volume adjustment via Spotify Web API requires Spotify Premium."}
        except SpotifyApiError as e:
            return {"success": False, "message": f"Could not set volume: {e}"}

    def set_shuffle(self, state: bool, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Toggles shuffle mode."""
        device, _ = self.resolve_target_device(device_id)
        params = {"state": "true" if state else "false"}
        if device:
            params["device_id"] = device.id
        try:
            self.client.put("me/player/shuffle", params=params)
            return {"success": True, "message": f"Shuffle turned {'on' if state else 'off'}."}
        except SpotifyPremiumRequiredError:
            return {"success": False, "message": "Shuffle control requires Spotify Premium."}

    def set_repeat(self, state: str, device_id: Optional[str] = None) -> Dict[str, Any]:
        """Sets repeat mode: 'track', 'context', or 'off'."""
        clean_state = state.lower().strip()
        if clean_state not in ("track", "context", "off"):
            clean_state = "context"
        device, _ = self.resolve_target_device(device_id)
        params = {"state": clean_state}
        if device:
            params["device_id"] = device.id
        try:
            self.client.put("me/player/repeat", params=params)
            return {"success": True, "message": f"Repeat mode set to {clean_state}."}
        except SpotifyPremiumRequiredError:
            return {"success": False, "message": "Repeat mode control requires Spotify Premium."}

    def transfer_playback(self, device_name_or_id: str, play: bool = False) -> Dict[str, Any]:
        """Transfers active playback to a selected device."""
        device, _ = self.resolve_target_device(device_name_or_id)
        if not device:
            return {"success": False, "message": f"Could not find device '{device_name_or_id}'."}

        payload = {"device_ids": [device.id], "play": play}
        try:
            self.client.put("me/player", json_data=payload)
            self.context.set_active_device(device.id, device.name)
            return {"success": True, "message": f"Playback transferred to {device.name}."}
        except SpotifyPremiumRequiredError:
            return {"success": False, "message": "Transferring playback via Spotify Web API requires Spotify Premium."}

    # =========================================================================
    # Fallback Local Desktop Automation
    # =========================================================================

    @staticmethod
    def _fallback_desktop_media_key(action: str):
        """Sends native Windows media key as an explicitly documented fallback."""
        try:
            import ctypes
            VK_MEDIA_NEXT_TRACK = 0xB0
            VK_MEDIA_PREV_TRACK = 0xB1
            VK_MEDIA_PLAY_PAUSE = 0xB3

            vk = VK_MEDIA_PLAY_PAUSE
            if action == "next":
                vk = VK_MEDIA_NEXT_TRACK
            elif action == "prev":
                vk = VK_MEDIA_PREV_TRACK

            ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
            ctypes.windll.user32.keybd_event(vk, 0, 2, 0)
            logger.info(f"Triggered Windows virtual key {hex(vk)} as fallback.")
        except Exception as e:
            logger.error(f"Fallback media key error: {e}")


# Global singleton service
spotify_service = SpotifyService()
