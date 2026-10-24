"""Santra Spotify Integration Package."""

from modules.spotify.models import (
    SpotifyTrack, SpotifyPlaylist, SpotifyDevice, SpotifyUser,
    PlaybackState, DuplicateReport, DuplicateGroup
)
from modules.spotify.oauth_manager import SpotifyOAuthManager, spotify_oauth, SecureTokenStorage
from modules.spotify.client import (
    SpotifyClient, spotify_client, SpotifyApiError,
    SpotifyPremiumRequiredError, SpotifyNoActiveDeviceError, SpotifyRateLimitError
)
from modules.spotify.context import SpotifyContext, spotify_context
from modules.spotify.service import SpotifyService, spotify_service

__all__ = [
    "SpotifyTrack",
    "SpotifyPlaylist",
    "SpotifyDevice",
    "SpotifyUser",
    "PlaybackState",
    "DuplicateReport",
    "DuplicateGroup",
    "SpotifyOAuthManager",
    "spotify_oauth",
    "SecureTokenStorage",
    "SpotifyClient",
    "spotify_client",
    "SpotifyApiError",
    "SpotifyPremiumRequiredError",
    "SpotifyNoActiveDeviceError",
    "SpotifyRateLimitError",
    "SpotifyContext",
    "spotify_context",
    "SpotifyService",
    "spotify_service",
]
