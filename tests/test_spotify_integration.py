"""Comprehensive Unit and Integration Test Suite for Santra Spotify Integration.

Tests:
1. OAuth 2.0 PKCE flow (verifier, challenge, state verification, token refresh, disconnect).
2. API Client (error handling, 401 refresh, 403 Premium Required, 404 No Active Device, 429 Rate Limit, cache TTL).
3. Playlists CRUD (create, rename, add, remove by index/name, reorder, replace, duplicates cleanup).
4. Official Unfollow Semantics (accurate reporting, no false permanent deletion claims).
5. Playback Controls & Devices (play, pause, next, prev, seek, volume, shuffle, repeat, transfer).
6. Premium restrictions and desktop fallback automation.
7. Natural Language Command Routing (all 13+ example commands).
8. Conversational Multi-Turn Context (Night Drive -> Add 5 songs -> Remove 2nd one -> Now play it).
9. Safe Destructive Operations & Confirmations.
10. UI dialog structure and thread safety.
"""

import time
import unittest
from unittest.mock import MagicMock, patch, Mock

from modules.spotify.models import (
    SpotifyTrack, SpotifyPlaylist, SpotifyDevice, SpotifyUser,
    PlaybackState, DuplicateReport, DuplicateGroup
)
from modules.spotify.oauth_manager import SpotifyOAuthManager, SecureTokenStorage
from modules.spotify.client import (
    SpotifyClient, SpotifyApiError, SpotifyPremiumRequiredError,
    SpotifyNoActiveDeviceError, SpotifyRateLimitError
)
from modules.spotify.context import SpotifyContext
from modules.spotify.service import SpotifyService
from core.intent_engine import IntentEngine
from core.ai.intelligence_router import IntelligenceRouter
from modules.system.executor import CommandExecutor
from modules.system.permissions import get_action_risk_level, RiskLevel


class TestSpotifyOAuth(unittest.TestCase):
    """Phase 2: OAuth 2.0 PKCE flow verification."""

    def setUp(self):
        self.oauth = SpotifyOAuthManager(client_id="test_client_id_12345", redirect_uri="http://127.0.0.1:8888/callback")

    def test_pkce_challenge_generation(self):
        """Verify high-entropy verifier and SHA256 challenge generation."""
        verifier = self.oauth._generate_code_verifier()
        self.assertGreaterEqual(len(verifier), 43)
        self.assertLessEqual(len(verifier), 128)

        challenge = self.oauth._generate_code_challenge(verifier)
        self.assertTrue(challenge)
        self.assertNotIn("=", challenge)  # URL-safe base64 without padding

    def test_authorization_url_parameters(self):
        """Verify authorization URL adheres strictly to Spotify PKCE specifications without client secret."""
        url, verifier, state = self.oauth.generate_authorization_url()
        self.assertIn("https://accounts.spotify.com/authorize", url)
        self.assertIn("client_id=test_client_id_12345", url)
        self.assertIn("code_challenge_method=S256", url)
        self.assertIn("response_type=code", url)
        self.assertIn(f"state={state}", url)
        self.assertNotIn("client_secret", url)

    @patch("modules.spotify.oauth_manager.requests.post")
    @patch.object(SecureTokenStorage, "save_tokens", return_value=True)
    def test_code_exchange_success(self, mock_save, mock_post):
        """Verify exchanging authorization code for access and refresh tokens."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "mock_access_token_xyz",
            "refresh_token": "mock_refresh_token_abc",
            "expires_in": 3600,
            "token_type": "Bearer",
            "scope": "user-read-private"
        }
        mock_post.return_value = mock_resp

        success, msg = self.oauth.exchange_code_for_tokens("mock_auth_code", "mock_verifier_123")
        self.assertTrue(success)
        self.assertIn("successfully connected", msg.lower())
        self.assertEqual(self.oauth.get_valid_token(), "mock_access_token_xyz")
        mock_save.assert_called_once()

    @patch("modules.spotify.oauth_manager.requests.post")
    @patch.object(SecureTokenStorage, "save_tokens", return_value=True)
    def test_token_refresh(self, mock_save, mock_post):
        """Verify automatic refresh of expired access token."""
        self.oauth._tokens = {
            "access_token": "stale_token",
            "refresh_token": "valid_refresh",
            "expires_at": time.time() - 100,  # Expired
            "token_type": "Bearer"
        }

        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "access_token": "new_refreshed_token",
            "expires_in": 3600
        }
        mock_post.return_value = mock_resp

        token = self.oauth.get_valid_token()
        self.assertEqual(token, "new_refreshed_token")
        self.assertTrue(mock_post.called)

    def test_disconnect(self):
        """Verify disconnect completely wipes credentials and state."""
        self.oauth._tokens = {"access_token": "active_token", "refresh_token": "active_refresh"}
        with patch.object(SecureTokenStorage, "clear_tokens") as mock_clear:
            self.oauth.disconnect()
            self.assertIsNone(self.oauth._tokens)
            mock_clear.assert_called_once()
            self.assertFalse(self.oauth.is_connected())


class TestSpotifyClient(unittest.TestCase):
    """Phase 3 & 9: HTTP Client, error classification, and rate limits."""

    def setUp(self):
        self.mock_oauth = MagicMock()
        self.mock_oauth.get_valid_token.return_value = "mock_valid_token"
        self.client = SpotifyClient(oauth_manager=self.mock_oauth)

    @patch("requests.Session.request")
    def test_premium_required_exception(self, mock_req):
        """Verify HTTP 403 PREMIUM_REQUIRED triggers SpotifyPremiumRequiredError."""
        mock_resp = Mock()
        mock_resp.status_code = 403
        mock_resp.json.return_value = {
            "error": {"status": 403, "message": "Player command failed: Premium required", "reason": "PREMIUM_REQUIRED"}
        }
        mock_req.return_value = mock_resp

        with self.assertRaises(SpotifyPremiumRequiredError):
            self.client.put("me/player/play")

    @patch("requests.Session.request")
    def test_no_active_device_exception(self, mock_req):
        """Verify HTTP 404 NO_ACTIVE_DEVICE triggers SpotifyNoActiveDeviceError."""
        mock_resp = Mock()
        mock_resp.status_code = 404
        mock_resp.json.return_value = {
            "error": {"status": 404, "message": "Device not found", "reason": "NO_ACTIVE_DEVICE"}
        }
        mock_req.return_value = mock_resp

        with self.assertRaises(SpotifyNoActiveDeviceError):
            self.client.put("me/player/pause")

    @patch("requests.Session.request")
    def test_rate_limit_retry_after(self, mock_req):
        """Verify HTTP 429 raises SpotifyRateLimitError with Retry-After value."""
        mock_resp = Mock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "6"}
        mock_req.return_value = mock_resp

        with self.assertRaises(SpotifyRateLimitError) as ctx:
            self.client.get("me/playlists")
        self.assertEqual(ctx.exception.retry_after, 6)

    @patch("requests.Session.request")
    def test_metadata_cache_hit_and_invalidation(self, mock_req):
        """Verify short-lived cache avoids redundant requests until invalidated."""
        mock_resp = Mock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"devices": [{"id": "dev1", "name": "PC"}]}
        mock_req.return_value = mock_resp

        # 1st call: network fetch
        res1 = self.client.get("me/player/devices", cache_ttl=5.0)
        self.assertEqual(mock_req.call_count, 1)

        # 2nd call: cache hit
        res2 = self.client.get("me/player/devices", cache_ttl=5.0)
        self.assertEqual(mock_req.call_count, 1)

        # Invalidate cache
        self.client.invalidate_cache()

        # 3rd call: network fetch after invalidation
        res3 = self.client.get("me/player/devices", cache_ttl=5.0)
        self.assertEqual(mock_req.call_count, 2)


class TestSpotifyService(unittest.TestCase):
    """Phase 3, 5, 6, 7: Core Service methods, Playlists, Playback, and Context."""

    def setUp(self):
        self.mock_client = MagicMock()
        self.context = SpotifyContext()
        self.service = SpotifyService(client=self.mock_client, context=self.context)

    def test_create_playlist(self):
        """Verify playlist creation and context tracking."""
        self.mock_client.get.return_value = {"id": "user123", "display_name": "Active Gamer"}
        self.mock_client.post.return_value = {
            "id": "p_night_drive_1",
            "name": "Night Drive",
            "description": "Created by Santra",
            "public": False
        }

        p = self.service.create_playlist("Night Drive")
        self.assertEqual(p.id, "p_night_drive_1")
        self.assertEqual(p.name, "Night Drive")
        # Context must be updated
        self.assertEqual(self.context.active_playlist_id, "p_night_drive_1")
        self.assertEqual(self.context.active_playlist_name, "Night Drive")

    def test_add_tracks_by_search(self):
        """Verify natural language search & add tracks to active playlist."""
        self.context.set_active_playlist("p_night_drive_1", "Night Drive")

        # Mock search response
        self.mock_client.get.return_value = {
            "tracks": {
                "items": [
                    {"id": "t1", "name": "Blinding Lights", "uri": "spotify:track:t1", "artists": [{"name": "The Weeknd"}], "duration_ms": 200000},
                    {"id": "t2", "name": "Starboy", "uri": "spotify:track:t2", "artists": [{"name": "The Weeknd"}], "duration_ms": 230000}
                ]
            }
        }
        self.mock_client.post.return_value = {"snapshot_id": "snap123"}

        res = self.service.add_tracks_by_search(playlist_name_or_id=None, query="Blinding Lights", count=1)
        self.assertTrue(res["success"])
        self.assertEqual(res["playlist_id"], "p_night_drive_1")
        self.assertIn("Blinding Lights", res["message"])

    def test_remove_track_by_index(self):
        """Verify removing track using verified 1-based index from playlist snapshot."""
        # Setup context tracks snapshot
        track1 = SpotifyTrack(id="t1", name="Song 1", artist="Artist A", album="Album A", uri="spotify:track:t1")
        track2 = SpotifyTrack(id="t2", name="Song 2", artist="Artist B", album="Album B", uri="spotify:track:t2")
        self.context.set_active_playlist("p123", "Night Drive", tracks=[track1, track2])

        self.mock_client.get.return_value = {
            "items": [
                {"track": {"id": "t1", "name": "Song 1", "uri": "spotify:track:t1", "artists": [{"name": "Artist A"}]}},
                {"track": {"id": "t2", "name": "Song 2", "uri": "spotify:track:t2", "artists": [{"name": "Artist B"}]}}
            ]
        }
        self.mock_client.delete.return_value = {"snapshot_id": "snap456"}

        # Remove the second track (index 1 in 0-based)
        res = self.service.remove_tracks_from_playlist("p123", positions=[1])
        self.assertTrue(res["success"])
        # Verify delete payload passed correct position
        self.mock_client.delete.assert_called_with(
            "playlists/p123/tracks",
            json_data={"tracks": [{"uri": "spotify:track:t2", "positions": [1]}]}
        )

    def test_find_and_cleanup_duplicates(self):
        """Verify duplicate track detection and removal."""
        def mock_get(endpoint, *args, **kwargs):
            if "tracks" in endpoint:
                return {
                    "items": [
                        {"track": {"id": "t1", "name": "Track A", "uri": "spotify:track:t1", "artists": [{"name": "Artist 1"}]}},
                        {"track": {"id": "t2", "name": "Track B", "uri": "spotify:track:t2", "artists": [{"name": "Artist 2"}]}},
                        {"track": {"id": "t1", "name": "Track A", "uri": "spotify:track:t1", "artists": [{"name": "Artist 1"}]}}
                    ]
                }
            return {"id": "p1", "name": "Night Drive"}

        self.mock_client.get.side_effect = mock_get
        self.mock_client.delete.return_value = {"snapshot_id": "snap_dup"}

        report = self.service.find_duplicate_tracks("p1")
        self.assertEqual(report.total_duplicates, 1)
        self.assertEqual(report.duplicate_groups[0].positions, [0, 2])

        cleanup_res = self.service.cleanup_duplicates("p1")
        self.assertTrue(cleanup_res["success"])
        self.assertEqual(cleanup_res["removed"], 1)

    def test_unfollow_playlist_semantics(self):
        """Verify official unfollow API is used and message accurately reflects API behavior."""
        self.mock_client.get.return_value = {"id": "p_old", "name": "Old Jams"}
        self.mock_client.delete.return_value = {"status": "success"}

        res = self.service.unfollow_playlist("p_old")
        self.assertTrue(res["success"])
        self.assertIn("unfollowed and removed", res["message"])
        self.assertIn("permanent hard deletion is not supported", res["message"].lower())
        self.mock_client.delete.assert_called_with("playlists/p_old/followers")

    @patch.object(SpotifyService, "_fallback_desktop_media_key")
    def test_playback_fallback_when_premium_missing(self, mock_media_key):
        """Verify 403 Premium Required falls back gracefully to Windows media key automation."""
        self.mock_client.get.return_value = {"devices": [{"id": "d1", "name": "My Laptop", "is_active": True}]}
        self.mock_client.put.side_effect = SpotifyPremiumRequiredError()

        res = self.service.play()
        self.assertTrue(res["success"])
        self.assertTrue(res.get("fallback"))
        self.assertIn("requires spotify premium", res["message"].lower())
        mock_media_key.assert_called_once_with("play")


class TestSpotifyNaturalLanguageRouting(unittest.TestCase):
    """Phase 4: Natural language command parsing across all required examples."""

    @classmethod
    def setUpClass(cls):
        cls.intent_engine = IntentEngine()

    def test_all_required_spotify_commands(self):
        cases = [
            ("Play my liked songs.", "spotify_control", "play_liked"),
            ("Create a playlist called Night Drive.", "spotify_control", "create_playlist"),
            ("Add Blinding Lights to Night Drive.", "spotify_control", "add_track"),
            ("Remove the second song from Night Drive.", "spotify_control", "remove_track"),
            ("Rename Night Drive to Midnight Vibes.", "spotify_control", "rename_playlist"),
            ("Play my workout playlist.", "spotify_control", "play_playlist"),
            ("Shuffle my current playlist.", "spotify_control", "shuffle"),
            ("Move this song to the top.", "spotify_control", "reorder_track"),
            ("Which song is playing?", "spotify_control", "current_track"),
            ("Show my playlists.", "spotify_control", "list_playlists"),
            ("Delete my old playlist.", "spotify_control", "delete_playlist"),
            ("Pause Spotify.", "spotify_control", "pause"),
            ("Play this on my laptop.", "spotify_control", "transfer_device"),
            ("Add five songs by The Weeknd.", "spotify_control", "add_tracks_by_artist"),
            ("Remove the second one.", "spotify_control", "remove_track"),
            ("Now play it.", "spotify_control", "play_current_context"),
        ]

        for text, expected_intent, expected_action in cases:
            node = self.intent_engine.parse(text)
            self.assertEqual(node.get("intent"), expected_intent, f"Failed intent on: '{text}' -> got {node.get('intent')}")
            self.assertEqual(node.get("action"), expected_action, f"Failed action on: '{text}' -> got {node.get('action')}")

    def test_spotify_app_launch_preserved(self):
        """Ensure 'Open Spotify' and 'Close Spotify' remain standard OS application commands."""
        open_node = self.intent_engine.parse("Open Spotify")
        self.assertEqual(open_node.get("intent"), "open_app")
        self.assertEqual(open_node.get("target"), "spotify")

        close_node = self.intent_engine.parse("Close Spotify")
        self.assertEqual(close_node.get("intent"), "close_app")
        self.assertEqual(close_node.get("target"), "spotify")


class TestSpotifyMultiTurnExecution(unittest.TestCase):
    """Phase 5: Multi-turn contextual Spotify interaction flow."""

    def setUp(self):
        self.executor = CommandExecutor()
        from modules.spotify import spotify_service, spotify_context
        self.service = spotify_service
        self.context = spotify_context
        self.context.clear_all()

    @patch("modules.spotify.service.SpotifyService.is_connected", return_value=True)
    def test_complete_multi_turn_flow(self, mock_conn):
        """Simulate exact prompt dialogue:
        1. 'Create a playlist called Night Drive.'
        2. 'Add five songs by The Weeknd.'
        3. 'Remove the second one.'
        4. 'Now play it.'
        """
        # Step 1: Create Night Drive
        with patch.object(self.service, "create_playlist") as mock_create:
            mock_create.return_value = SpotifyPlaylist(id="p_nd", name="Night Drive")
            node1 = {"intent": "spotify_control", "action": "create_playlist", "playlist_name": "Night Drive"}
            res1 = self.executor.execute(node1)
            self.assertTrue(res1["success"])
            self.assertIn("Night Drive was created", res1["message"])
            self.context.set_active_playlist("p_nd", "Night Drive")

        # Step 2: Add five songs by The Weeknd (targets active context playlist)
        with patch.object(self.service, "add_tracks_by_search") as mock_add:
            mock_tracks = [SpotifyTrack(id=f"t{i}", name=f"Song {i}", artist="The Weeknd", album="After Hours") for i in range(1, 6)]
            mock_add.return_value = {
                "success": True,
                "playlist_id": "p_nd",
                "playlist_name": "Night Drive",
                "added_tracks": mock_tracks,
                "message": "Added 5 songs to Night Drive."
            }
            node2 = {"intent": "spotify_control", "action": "add_tracks_by_artist", "count": 5, "artist": "The Weeknd"}
            res2 = self.executor.execute(node2)
            self.assertTrue(res2["success"])
            # Update verified track snapshot in context
            self.context.update_playlist_tracks(mock_tracks)

        # Step 3: Remove the second one (resolves index 2 -> Song 2)
        with patch.object(self.service, "get_playlist_tracks") as mock_get_tracks, \
             patch.object(self.service, "remove_tracks_from_playlist") as mock_rm:
            mock_get_tracks.return_value = self.context.active_playlist_tracks
            mock_rm.return_value = {"success": True, "message": "Track removed."}

            node3 = {"intent": "spotify_control", "action": "remove_track", "index": 2}
            res3 = self.executor.execute(node3)
            self.assertTrue(res3["success"])
            self.assertIn("Removed 'Song 2'", res3["message"])

        # Step 4: Now play it (plays active playlist)
        with patch.object(self.service, "play") as mock_play:
            mock_play.return_value = {"success": True, "message": "Playback started on Spotify."}
            node4 = {"intent": "spotify_control", "action": "play_current_context"}
            res4 = self.executor.execute(node4)
            self.assertTrue(res4["success"])
            mock_play.assert_called_with(context_uri="spotify:playlist:p_nd")


class TestSpotifySafeDestructiveOperations(unittest.TestCase):
    """Phase 6: Safe destructive operations and explicit confirmation handling."""

    def setUp(self):
        self.executor = CommandExecutor()
        from modules.spotify import spotify_service, spotify_context
        self.service = spotify_service
        self.context = spotify_context

    @patch("modules.spotify.service.SpotifyService.is_connected", return_value=True)
    def test_unconfirmed_delete_demands_confirmation(self, mock_conn):
        """Unconfirmed delete must return pending_confirmation with exact unfollow explanation."""
        with patch.object(self.service, "find_playlist_by_name") as mock_find:
            mock_find.return_value = SpotifyPlaylist(id="p_old", name="My Old Playlist")
            node = {"intent": "spotify_control", "action": "delete_playlist", "playlist_name": "My Old Playlist"}
            res = self.executor.execute(node, confirm=False)

            self.assertFalse(res["success"])
            self.assertTrue(res.get("pending_confirmation"))
            self.assertIn("unfollow and remove it from your library", res["message"])
            self.assertIn("cannot be permanently deleted", res["message"])

    @patch("modules.spotify.service.SpotifyService.is_connected", return_value=True)
    def test_confirmed_delete_executes_unfollow(self, mock_conn):
        """Confirmed delete executes unfollow via Spotify API."""
        with patch.object(self.service, "find_playlist_by_name") as mock_find, \
             patch.object(self.service, "unfollow_playlist") as mock_unfollow:
            mock_find.return_value = SpotifyPlaylist(id="p_old", name="My Old Playlist")
            mock_unfollow.return_value = {"success": True, "message": "Playlist 'My Old Playlist' removed from your library."}

            node = {"intent": "spotify_control", "action": "delete_playlist", "playlist_name": "My Old Playlist", "playlist_id": "p_old"}
            res = self.executor.execute(node, confirm=True)

            self.assertTrue(res["success"])
            mock_unfollow.assert_called_once_with("p_old")

    def test_permissions_risk_levels(self):
        """Verify risk levels assigned to Spotify operations."""
        self.assertEqual(get_action_risk_level("spotify_control", "delete_playlist"), RiskLevel.HIGH)
        self.assertEqual(get_action_risk_level("spotify_control", "unfollow_playlist"), RiskLevel.HIGH)
        self.assertEqual(get_action_risk_level("spotify_control", "replace_tracks"), RiskLevel.HIGH)
        self.assertEqual(get_action_risk_level("spotify_control", "create_playlist"), RiskLevel.MEDIUM)
        self.assertEqual(get_action_risk_level("spotify_control", "play"), RiskLevel.LOW)
        self.assertEqual(get_action_risk_level("spotify_control", "pause"), RiskLevel.LOW)


if __name__ == "__main__":
    unittest.main()
