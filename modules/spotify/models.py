"""Data models for Spotify entities in Santra."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class SpotifyTrack:
    id: str
    name: str
    artist: str
    album: str
    duration_ms: int = 0
    uri: str = ""
    is_playable: bool = True
    image_url: str = ""

    @property
    def duration_formatted(self) -> str:
        seconds = int(self.duration_ms / 1000)
        mins = seconds // 60
        secs = seconds % 60
        return f"{mins}:{secs:02d}"

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "SpotifyTrack":
        # Handle track nested inside items[i].track or direct track object
        track_obj = data.get("track", data) if isinstance(data, dict) else {}
        if not track_obj:
            return cls(id="", name="Unknown", artist="Unknown", album="Unknown")

        tid = track_obj.get("id") or ""
        name = track_obj.get("name") or "Unknown Track"
        
        artists = track_obj.get("artists", [])
        artist_name = ", ".join(a.get("name", "") for a in artists if a.get("name")) or "Unknown Artist"
        
        album_obj = track_obj.get("album", {})
        album_name = album_obj.get("name", "Unknown Album") if isinstance(album_obj, dict) else "Unknown Album"
        
        # Get album cover image
        images = album_obj.get("images", []) if isinstance(album_obj, dict) else []
        image_url = images[0].get("url", "") if images else ""

        return cls(
            id=tid,
            name=name,
            artist=artist_name,
            album=album_name,
            duration_ms=track_obj.get("duration_ms", 0),
            uri=track_obj.get("uri") or (f"spotify:track:{tid}" if tid else ""),
            is_playable=track_obj.get("is_playable", True),
            image_url=image_url
        )


@dataclass
class SpotifyPlaylist:
    id: str
    name: str
    description: str = ""
    owner_id: str = ""
    owner_name: str = ""
    is_public: bool = False
    is_collaborative: bool = False
    total_tracks: int = 0
    uri: str = ""
    snapshot_id: str = ""
    image_url: str = ""

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "SpotifyPlaylist":
        if not data:
            return cls(id="", name="Unknown")

        pid = data.get("id") or ""
        name = data.get("name") or "Untitled Playlist"
        desc = data.get("description") or ""
        
        owner = data.get("owner", {}) or {}
        owner_id = owner.get("id") or ""
        owner_name = owner.get("display_name") or owner_id or "Spotify User"
        
        tracks_obj = data.get("tracks", {}) or {}
        total = tracks_obj.get("total", 0) if isinstance(tracks_obj, dict) else 0

        images = data.get("images", []) or []
        image_url = images[0].get("url", "") if images else ""

        return cls(
            id=pid,
            name=name,
            description=desc,
            owner_id=owner_id,
            owner_name=owner_name,
            is_public=bool(data.get("public", False)),
            is_collaborative=bool(data.get("collaborative", False)),
            total_tracks=total,
            uri=data.get("uri") or (f"spotify:playlist:{pid}" if pid else ""),
            snapshot_id=data.get("snapshot_id", ""),
            image_url=image_url
        )


@dataclass
class SpotifyDevice:
    id: str
    name: str
    device_type: str = "Computer"  # Computer, Smartphone, Speaker, etc.
    is_active: bool = False
    is_private_session: bool = False
    is_restricted: bool = False
    volume_percent: int = 100

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "SpotifyDevice":
        if not data:
            return cls(id="", name="Unknown Device")
        return cls(
            id=data.get("id") or "",
            name=data.get("name") or "Unknown Device",
            device_type=data.get("type") or "Computer",
            is_active=bool(data.get("is_active", False)),
            is_private_session=bool(data.get("is_private_session", False)),
            is_restricted=bool(data.get("is_restricted", False)),
            volume_percent=data.get("volume_percent") or 100
        )


@dataclass
class SpotifyUser:
    id: str
    display_name: str
    email: str = ""
    product: str = "free"  # "premium", "free", "open"
    country: str = ""
    uri: str = ""
    image_url: str = ""

    @property
    def is_premium(self) -> bool:
        return self.product.lower() == "premium"

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "SpotifyUser":
        if not data:
            return cls(id="", display_name="Unknown")
        images = data.get("images", []) or []
        image_url = images[0].get("url", "") if images else ""
        return cls(
            id=data.get("id") or "",
            display_name=data.get("display_name") or data.get("id") or "Spotify User",
            email=data.get("email") or "",
            product=data.get("product") or "free",
            country=data.get("country") or "",
            uri=data.get("uri") or "",
            image_url=image_url
        )


@dataclass
class PlaybackState:
    is_playing: bool = False
    progress_ms: int = 0
    shuffle_state: bool = False
    repeat_state: str = "off"  # "off", "track", "context"
    device: Optional[SpotifyDevice] = None
    item: Optional[SpotifyTrack] = None
    timestamp: float = 0.0

    @classmethod
    def from_api(cls, data: Dict[str, Any]) -> "PlaybackState":
        if not data:
            return cls()
        device_data = data.get("device")
        device = SpotifyDevice.from_api(device_data) if device_data else None
        item_data = data.get("item")
        item = SpotifyTrack.from_api(item_data) if item_data else None
        return cls(
            is_playing=bool(data.get("is_playing", False)),
            progress_ms=data.get("progress_ms") or 0,
            shuffle_state=bool(data.get("shuffle_state", False)),
            repeat_state=data.get("repeat_state") or "off",
            device=device,
            item=item,
            timestamp=float(data.get("timestamp") or 0)
        )


@dataclass
class DuplicateGroup:
    track_uri: str
    track_name: str
    artist: str
    positions: List[int] = field(default_factory=list)


@dataclass
class DuplicateReport:
    playlist_id: str
    playlist_name: str
    duplicate_groups: List[DuplicateGroup] = field(default_factory=list)

    @property
    def total_duplicates(self) -> int:
        # Number of surplus occurrences (total occurrences minus 1 for each group)
        return sum(max(0, len(g.positions) - 1) for g in self.duplicate_groups)
