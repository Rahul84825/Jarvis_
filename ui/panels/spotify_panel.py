"""Santra Spotify Control & Playlist Management Panel.

Native PyQt6 HUD interface conforming to Santra aesthetics:
- Spotify OAuth 2.0 PKCE Connect & Disconnect.
- Account status (Free / Premium product type, country, display name).
- Currently playing track metadata & album art.
- Full playback controls: Play/Pause, Skip Next/Prev, Seek, Shuffle, Repeat.
- Volume control slider.
- Playback device selector & transfer.
- Playlist explorer: Create, Rename, Unfollow/Remove, Add/Remove/Reorder tracks.
- Duplicate tracks analyzer & cleanup.
- Safe confirmation dialogs for destructive actions.
- Asynchronous non-blocking background workers maintaining smooth 60 FPS UI.
"""

import logging
import webbrowser
from typing import Optional, List, Dict, Any

from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QByteArray
from PyQt6.QtGui import QPixmap, QColor, QFont
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QTabWidget, QWidget, QSlider, QProgressBar, QSplitter, QInputDialog
)

from modules.spotify import (
    spotify_service, spotify_oauth, spotify_context,
    SpotifyUser, SpotifyPlaylist, SpotifyTrack, SpotifyDevice, PlaybackState
)
from modules.spotify.client import SpotifyPremiumRequiredError, SpotifyNoActiveDeviceError

logger = logging.getLogger("Jarvis.UI.SpotifyPanel")


class SpotifyAuthWorker(QThread):
    """Background thread running the local OAuth PKCE callback server."""
    finished = pyqtSignal(bool, str)

    def run(self):
        try:
            success, msg = spotify_oauth.start_local_auth_server(timeout_sec=120.0)
            self.finished.emit(success, msg)
        except Exception as e:
            self.finished.emit(False, str(e))


class SpotifyAsyncActionWorker(QThread):
    """General async worker executing Spotify API network calls off the main thread."""
    finished = pyqtSignal(bool, str, object)

    def __init__(self, action_func, *args, **kwargs):
        super().__init__()
        self.action_func = action_func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            res = self.action_func(*self.args, **self.kwargs)
            msg = res.get("message", "Success") if isinstance(res, dict) else "Success"
            success = res.get("success", True) if isinstance(res, dict) else True
            self.finished.emit(success, msg, res)
        except SpotifyPremiumRequiredError:
            self.finished.emit(False, "Spotify Web API playback controls require a Spotify Premium account.", None)
        except SpotifyNoActiveDeviceError:
            self.finished.emit(False, "No active Spotify player detected. Please launch Spotify on your computer or phone.", None)
        except Exception as e:
            logger.error(f"Error in SpotifyAsyncActionWorker: {e}", exc_info=True)
            self.finished.emit(False, str(e), None)


class ImageDownloadWorker(QThread):
    """Downloads track album art asynchronously."""
    image_loaded = pyqtSignal(bytes)

    def __init__(self, url: str):
        super().__init__()
        self.url = url

    def run(self):
        if not self.url:
            return
        try:
            import requests
            resp = requests.get(self.url, timeout=5.0)
            if resp.status_code == 200:
                self.image_loaded.emit(resp.content)
        except Exception:
            pass


class SpotifyDialog(QDialog):
    """Main Holographic Spotify Management Panel for Santra."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SANTRA // Spotify Intelligence & Playback Control")
        self.resize(920, 680)
        self.setMinimumSize(840, 580)

        self._user_profile: Optional[SpotifyUser] = None
        self._current_playback: Optional[PlaybackState] = None
        self._playlists: List[SpotifyPlaylist] = []
        self._current_tracks: List[SpotifyTrack] = []
        self._selected_playlist: Optional[SpotifyPlaylist] = None
        self._is_seeking = False

        self._auth_worker: Optional[SpotifyAuthWorker] = None
        self._action_worker: Optional[SpotifyAsyncActionWorker] = None
        self._image_worker: Optional[ImageDownloadWorker] = None

        self._apply_styles()
        self._init_ui()

        # State Polling Timer (every 2.5 seconds when dialog is active)
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._on_poll_tick)

        # Initial data load
        self._refresh_all_state()

    def showEvent(self, event):
        super().showEvent(event)
        self._poll_timer.start(2500)

    def hideEvent(self, event):
        super().hideEvent(event)
        self._poll_timer.stop()

    def _apply_styles(self):
        self.setStyleSheet("""
            QDialog {
                background: #01060c;
                color: #e0f7fa;
                font-family: 'Segoe UI', Tahoma, sans-serif;
            }
            QLabel {
                color: #b0bec5;
            }
            QLineEdit, QComboBox {
                background: #061521;
                border: 1px solid rgba(0, 229, 255, 0.4);
                border-radius: 4px;
                padding: 6px 10px;
                color: #ffffff;
                font-size: 13px;
            }
            QLineEdit:focus, QComboBox:focus {
                border: 1px solid #00e5ff;
                background: #092032;
            }
            QPushButton {
                background: rgba(2, 28, 44, 0.9);
                border: 1px solid rgba(0, 229, 255, 0.5);
                border-radius: 4px;
                padding: 7px 16px;
                color: #00e5ff;
                font-weight: bold;
                font-size: 12px;
                letter-spacing: 0.5px;
            }
            QPushButton:hover {
                background: rgba(0, 229, 255, 0.18);
                border: 1px solid #00e5ff;
            }
            QPushButton:disabled {
                border-color: #37474f;
                color: #546e7a;
                background: #051019;
            }
            QPushButton#btnConnect {
                background: #1db954;
                color: #01060c;
                border: 1px solid #1ed760;
                font-weight: 900;
            }
            QPushButton#btnConnect:hover {
                background: #1ed760;
            }
            QPushButton#btnDisconnect {
                background: rgba(255, 82, 82, 0.15);
                color: #ff5252;
                border: 1px solid rgba(255, 82, 82, 0.5);
            }
            QPushButton#btnDisconnect:hover {
                background: rgba(255, 82, 82, 0.3);
                border-color: #ff5252;
            }
            QTabWidget::pane {
                border: 1px solid rgba(0, 229, 255, 0.3);
                background: rgba(2, 12, 20, 0.85);
                border-radius: 6px;
            }
            QTabBar::tab {
                background: #03121c;
                color: #90a4ae;
                padding: 8px 20px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                margin-right: 2px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background: rgba(2, 28, 44, 0.9);
                color: #00e5ff;
                border: 1px solid rgba(0, 229, 255, 0.4);
                border-bottom: none;
            }
            QTableWidget {
                background: #030e17;
                border: 1px solid rgba(0, 229, 255, 0.2);
                color: #eceff1;
                gridline-color: rgba(0, 229, 255, 0.1);
                selection-background-color: rgba(0, 229, 255, 0.25);
                selection-color: #ffffff;
            }
            QHeaderView::section {
                background: #061826;
                color: #00e5ff;
                padding: 6px;
                border: 1px solid rgba(0, 229, 255, 0.15);
                font-weight: bold;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #061b29;
                border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: #1db954;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #ffffff;
                border: 1px solid #1db954;
                width: 14px;
                margin-top: -4px;
                margin-bottom: -4px;
                border-radius: 7px;
            }
        """)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(12)

        # Header bar
        header_bar = QHBoxLayout()

        title_lbl = QLabel("🎵 SANTRA // SPOTIFY SUITE")
        title_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #00e5ff; letter-spacing: 1.5px;")
        header_bar.addWidget(title_lbl)

        header_bar.addStretch()

        self.lbl_user_status = QLabel("Checking connection...")
        self.lbl_user_status.setStyleSheet("font-size: 13px; color: #eceff1;")
        header_bar.addWidget(self.lbl_user_status)

        self.btn_auth = QPushButton("CONNECT SPOTIFY")
        self.btn_auth.setObjectName("btnConnect")
        self.btn_auth.clicked.connect(self._on_auth_clicked)
        header_bar.addWidget(self.btn_auth)

        main_layout.addLayout(header_bar)

        # Client ID configuration row (collapsible/subtle)
        client_id_layout = QHBoxLayout()
        cid_lbl = QLabel("Spotify Client ID:")
        cid_lbl.setStyleSheet("font-size: 11px; color: #78909c;")
        client_id_layout.addWidget(cid_lbl)

        self.input_client_id = QLineEdit()
        self.input_client_id.setPlaceholderText("Enter your Spotify Developer App Client ID (no secret required)")
        self.input_client_id.setText(spotify_oauth.client_id)
        client_id_layout.addWidget(self.input_client_id, stretch=1)

        self.btn_save_client_id = QPushButton("SAVE ID")
        self.btn_save_client_id.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        self.btn_save_client_id.clicked.connect(self._on_save_client_id)
        client_id_layout.addWidget(self.btn_save_client_id)

        btn_dev_portal = QPushButton("🌐 DEV DASHBOARD")
        btn_dev_portal.setStyleSheet("padding: 4px 10px; font-size: 11px;")
        btn_dev_portal.clicked.connect(lambda: webbrowser.open("https://developer.spotify.com/dashboard"))
        client_id_layout.addWidget(btn_dev_portal)

        main_layout.addLayout(client_id_layout)

        # Premium / Active Device Warning Banner (Hidden by default)
        self.banner_warning = QLabel()
        self.banner_warning.setStyleSheet("""
            background: rgba(255, 179, 0, 0.15);
            border: 1px solid #ffb300;
            color: #ffe082;
            padding: 8px 12px;
            border-radius: 4px;
            font-size: 12px;
        """)
        self.banner_warning.hide()
        main_layout.addWidget(self.banner_warning)

        # Tabs: Playback / Devices vs Playlists Management
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs, stretch=1)

        # Tab 1: Playback & Active Player
        self.tab_player = QWidget()
        self._init_player_tab()
        self.tabs.addTab(self.tab_player, "CURRENT PLAYBACK & CONTROLS")

        # Tab 2: Playlists & Library
        self.tab_playlists = QWidget()
        self._init_playlists_tab()
        self.tabs.addTab(self.tab_playlists, "PLAYLIST MANAGEMENT & TRACKS")

    # =========================================================================
    # Tab 1: Playback Controls & Devices UI
    # =========================================================================

    def _init_player_tab(self):
        layout = QVBoxLayout(self.tab_player)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        # Device Selection Bar
        device_row = QHBoxLayout()
        dev_lbl = QLabel("Target Playback Device:")
        dev_lbl.setStyleSheet("font-weight: bold; color: #00e5ff;")
        device_row.addWidget(dev_lbl)

        self.combo_devices = QComboBox()
        device_row.addWidget(self.combo_devices, stretch=1)

        self.btn_transfer = QPushButton("TRANSFER PLAYBACK")
        self.btn_transfer.clicked.connect(self._on_transfer_device)
        device_row.addWidget(self.btn_transfer)

        self.btn_refresh_devs = QPushButton("🔄 REFRESH")
        self.btn_refresh_devs.clicked.connect(self._refresh_devices)
        device_row.addWidget(self.btn_refresh_devs)

        layout.addLayout(device_row)

        # Currently Playing Card (Now Playing Box)
        now_playing_frame = QWidget()
        now_playing_frame.setStyleSheet("""
            QWidget {
                background: rgba(5, 20, 32, 0.7);
                border: 1px solid rgba(0, 229, 255, 0.3);
                border-radius: 6px;
            }
        """)
        np_layout = QHBoxLayout(now_playing_frame)
        np_layout.setContentsMargins(16, 16, 16, 16)
        np_layout.setSpacing(20)

        # Album Art Thumbnail
        self.lbl_album_art = QLabel()
        self.lbl_album_art.setFixedSize(110, 110)
        self.lbl_album_art.setStyleSheet("background: #020910; border: 1px solid #1db954; border-radius: 4px;")
        self.lbl_album_art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_album_art.setText("🎵")
        np_layout.addWidget(self.lbl_album_art)

        # Track Details & Progress
        info_col = QVBoxLayout()
        info_col.setSpacing(6)

        self.lbl_track_title = QLabel("No track currently playing")
        self.lbl_track_title.setStyleSheet("font-size: 16px; font-weight: bold; color: #ffffff;")
        info_col.addWidget(self.lbl_track_title)

        self.lbl_track_artist = QLabel("Open Spotify and play music to start")
        self.lbl_track_artist.setStyleSheet("font-size: 13px; color: #1db954;")
        info_col.addWidget(self.lbl_track_artist)

        self.lbl_track_album = QLabel("")
        self.lbl_track_album.setStyleSheet("font-size: 12px; color: #90a4ae;")
        info_col.addWidget(self.lbl_track_album)

        # Progress bar / Seek scrubber
        time_row = QHBoxLayout()
        self.lbl_time_cur = QLabel("0:00")
        self.lbl_time_cur.setStyleSheet("font-size: 11px; color: #cfd8dc;")
        time_row.addWidget(self.lbl_time_cur)

        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 1000)
        self.seek_slider.sliderPressed.connect(self._on_seek_pressed)
        self.seek_slider.sliderReleased.connect(self._on_seek_released)
        time_row.addWidget(self.seek_slider, stretch=1)

        self.lbl_time_total = QLabel("0:00")
        self.lbl_time_total.setStyleSheet("font-size: 11px; color: #cfd8dc;")
        time_row.addWidget(self.lbl_time_total)

        info_col.addLayout(time_row)
        np_layout.addLayout(info_col, stretch=1)

        layout.addWidget(now_playing_frame)

        # Transport Controls Row
        ctrl_row = QHBoxLayout()
        ctrl_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ctrl_row.setSpacing(14)

        self.btn_shuffle = QPushButton("🔀 SHUFFLE: OFF")
        self.btn_shuffle.clicked.connect(self._on_toggle_shuffle)
        ctrl_row.addWidget(self.btn_shuffle)

        self.btn_prev = QPushButton("⏮ PREV")
        self.btn_prev.clicked.connect(lambda: self._run_async(spotify_service.previous_track))
        ctrl_row.addWidget(self.btn_prev)

        self.btn_play_pause = QPushButton("▶ PLAY")
        self.btn_play_pause.setStyleSheet("padding: 10px 24px; font-size: 14px; background: #1db954; color: #01060c;")
        self.btn_play_pause.clicked.connect(self._on_toggle_play_pause)
        ctrl_row.addWidget(self.btn_play_pause)

        self.btn_next = QPushButton("NEXT ⏭")
        self.btn_next.clicked.connect(lambda: self._run_async(spotify_service.next_track))
        ctrl_row.addWidget(self.btn_next)

        self.btn_repeat = QPushButton("🔁 REPEAT: OFF")
        self.btn_repeat.clicked.connect(self._on_toggle_repeat)
        ctrl_row.addWidget(self.btn_repeat)

        layout.addLayout(ctrl_row)

        # Volume Row
        vol_row = QHBoxLayout()
        vol_lbl = QLabel("Volume:")
        vol_lbl.setStyleSheet("font-weight: bold; color: #00e5ff;")
        vol_row.addWidget(vol_lbl)

        self.slider_volume = QSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 100)
        self.slider_volume.setValue(50)
        self.slider_volume.sliderReleased.connect(self._on_volume_changed)
        vol_row.addWidget(self.slider_volume, stretch=1)

        self.lbl_vol_val = QLabel("50%")
        self.lbl_vol_val.setFixedWidth(40)
        vol_row.addWidget(self.lbl_vol_val)

        layout.addLayout(vol_row)
        layout.addStretch()

    # =========================================================================
    # Tab 2: Playlists Management UI
    # =========================================================================

    def _init_playlists_tab(self):
        layout = QVBoxLayout(self.tab_playlists)
        layout.setContentsMargins(10, 10, 10, 10)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left Column: Playlist List & Buttons
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        p_top_bar = QHBoxLayout()
        p_lbl = QLabel("MY PLAYLISTS")
        p_lbl.setStyleSheet("font-weight: bold; color: #00e5ff;")
        p_top_bar.addWidget(p_lbl)

        self.btn_refresh_playlists = QPushButton("🔄")
        self.btn_refresh_playlists.setFixedWidth(36)
        self.btn_refresh_playlists.clicked.connect(self._refresh_playlists)
        p_top_bar.addWidget(self.btn_refresh_playlists)
        left_layout.addLayout(p_top_bar)

        self.table_playlists = QTableWidget()
        self.table_playlists.setColumnCount(3)
        self.table_playlists.setHorizontalHeaderLabels(["Name", "Tracks", "Visibility"])
        self.table_playlists.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table_playlists.itemSelectionChanged.connect(self._on_playlist_selected)
        left_layout.addWidget(self.table_playlists)

        # Playlist Action Buttons
        p_btn_layout = QHBoxLayout()
        self.btn_new_playlist = QPushButton("➕ NEW")
        self.btn_new_playlist.clicked.connect(self._on_create_playlist_dialog)
        p_btn_layout.addWidget(self.btn_new_playlist)

        self.btn_rename_playlist = QPushButton("✏️ RENAME")
        self.btn_rename_playlist.clicked.connect(self._on_rename_playlist_dialog)
        p_btn_layout.addWidget(self.btn_rename_playlist)

        self.btn_delete_playlist = QPushButton("🗑️ UNFOLLOW")
        self.btn_delete_playlist.setObjectName("btnDisconnect")
        self.btn_delete_playlist.clicked.connect(self._on_unfollow_playlist_dialog)
        p_btn_layout.addWidget(self.btn_delete_playlist)

        left_layout.addLayout(p_btn_layout)

        self.btn_dedup_playlist = QPushButton("🧹 FIND DUPLICATES & CLEAN UP")
        self.btn_dedup_playlist.clicked.connect(self._on_cleanup_duplicates)
        left_layout.addWidget(self.btn_dedup_playlist)

        splitter.addWidget(left_widget)

        # Right Column: Tracks of Selected Playlist
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        t_top_bar = QHBoxLayout()
        self.lbl_selected_playlist = QLabel("Tracks in Playlist")
        self.lbl_selected_playlist.setStyleSheet("font-weight: bold; color: #00e5ff;")
        t_top_bar.addWidget(self.lbl_selected_playlist, stretch=1)

        self.btn_play_this_playlist = QPushButton("▶ PLAY PLAYLIST")
        self.btn_play_this_playlist.clicked.connect(self._on_play_selected_playlist)
        t_top_bar.addWidget(self.btn_play_this_playlist)
        right_layout.addLayout(t_top_bar)

        # Quick Add Search Box
        add_row = QHBoxLayout()
        self.input_search_track = QLineEdit()
        self.input_search_track.setPlaceholderText("Search song or artist to add to this playlist...")
        self.input_search_track.returnPressed.connect(self._on_quick_add_track)
        add_row.addWidget(self.input_search_track, stretch=1)

        self.btn_add_track = QPushButton("ADD SONG")
        self.btn_add_track.clicked.connect(self._on_quick_add_track)
        add_row.addWidget(self.btn_add_track)
        right_layout.addLayout(add_row)

        self.table_tracks = QTableWidget()
        self.table_tracks.setColumnCount(4)
        self.table_tracks.setHorizontalHeaderLabels(["#", "Title", "Artist", "Duration"])
        self.table_tracks.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table_tracks.setColumnWidth(0, 40)
        self.table_tracks.setColumnWidth(3, 70)
        right_layout.addWidget(self.table_tracks)

        # Track actions
        t_action_row = QHBoxLayout()
        self.btn_move_up = QPushButton("⬆ MOVE UP")
        self.btn_move_up.clicked.connect(self._on_move_track_up)
        t_action_row.addWidget(self.btn_move_up)

        self.btn_move_down = QPushButton("⬇ MOVE DOWN")
        self.btn_move_down.clicked.connect(self._on_move_track_down)
        t_action_row.addWidget(self.btn_move_down)

        self.btn_remove_track = QPushButton("❌ REMOVE TRACK")
        self.btn_remove_track.clicked.connect(self._on_remove_selected_track)
        t_action_row.addWidget(self.btn_remove_track)

        right_layout.addLayout(t_action_row)

        splitter.addWidget(right_widget)
        splitter.setSizes([340, 520])
        layout.addWidget(splitter)

    # =========================================================================
    # Async Runner & State Polling
    # =========================================================================

    def _run_async(self, func, *args, on_success_cb=None, **kwargs):
        """Runs a task asynchronously and notifies on completion."""
        worker = SpotifyAsyncActionWorker(func, *args, **kwargs)
        if on_success_cb:
            worker.finished.connect(lambda ok, msg, res: on_success_cb(res) if ok else self._show_error(msg))
        else:
            worker.finished.connect(lambda ok, msg, res: self._refresh_all_state() if ok else self._show_error(msg))
        self._action_worker = worker
        worker.start()

    def _show_error(self, message: str):
        self.banner_warning.setText(f"⚠️ {message}")
        self.banner_warning.show()
        QTimer.singleShot(6000, self.banner_warning.hide)

    def _on_poll_tick(self):
        """Periodic background refresh of playback status & devices."""
        if not spotify_service.is_connected():
            return
        # Run light poll off thread
        threading.Thread(target=self._background_poll, daemon=True).start()

    def _background_poll(self):
        try:
            state = spotify_service.get_current_playback()
            devices = spotify_service.get_devices()
            # Update UI on main thread safely
            QTimer.singleShot(0, lambda: self._update_playback_ui(state))
            QTimer.singleShot(0, lambda: self._update_devices_ui(devices))
        except Exception:
            pass

    def _refresh_all_state(self):
        """Refreshes connection status, user profile, devices, and playlists."""
        if not spotify_service.is_connected():
            self.lbl_user_status.setText("Disconnected")
            self.btn_auth.setText("CONNECT SPOTIFY")
            self.btn_auth.setObjectName("btnConnect")
            self.btn_auth.setStyleSheet("")
            self.table_playlists.setRowCount(0)
            self.table_tracks.setRowCount(0)
            return

        # Connected: fetch user profile
        self.lbl_user_status.setText("Connecting...")
        self._run_async(spotify_service.get_profile, on_success_cb=self._on_profile_loaded)
        self._refresh_devices()
        self._refresh_playlists()

    def _on_profile_loaded(self, user: SpotifyUser):
        self._user_profile = user
        tier_tag = "[PREMIUM]" if user.is_premium else "[FREE]"
        tier_color = "#1db954" if user.is_premium else "#ffb300"
        self.lbl_user_status.setText(
            f"Connected: <b style='color:#ffffff;'>{user.display_name}</b> "
            f"(<span style='color:{tier_color};'>{tier_tag}</span>, {user.country})"
        )
        self.btn_auth.setText("DISCONNECT")
        self.btn_auth.setObjectName("btnDisconnect")
        self.btn_auth.setStyleSheet("")

        if not user.is_premium:
            self.banner_warning.setText("ℹ️ Spotify Free Account: Web API playback controls require Spotify Premium. Santra uses desktop media keys as a fallback.")
            self.banner_warning.show()

    # =========================================================================
    # Auth & Settings Handlers
    # =========================================================================

    def _on_save_client_id(self):
        cid = self.input_client_id.text().strip()
        if not cid:
            QMessageBox.warning(self, "Invalid Client ID", "Please enter a valid Spotify Client ID.")
            return
        spotify_oauth.set_client_id(cid)
        QMessageBox.information(self, "Client ID Saved", "Spotify Client ID securely saved to Windows Credential Manager.")

    def _on_auth_clicked(self):
        if spotify_service.is_connected():
            # Disconnect
            reply = QMessageBox.question(
                self,
                "Disconnect Spotify",
                "Are you sure you want to disconnect your Spotify account from Santra?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                spotify_oauth.disconnect()
                self._user_profile = None
                self._current_playback = None
                self._refresh_all_state()
            return

        # Start PKCE Authorization flow
        cid = self.input_client_id.text().strip()
        if not cid:
            QMessageBox.warning(self, "Missing Client ID", "Please enter your Spotify Developer App Client ID first.")
            return

        spotify_oauth.set_client_id(cid)

        try:
            auth_url, verifier, state = spotify_oauth.generate_authorization_url()
        except Exception as e:
            QMessageBox.critical(self, "Authorization Error", f"Failed to initialize OAuth: {e}")
            return

        # Launch background HTTP redirect server
        self.btn_auth.setEnabled(False)
        self.btn_auth.setText("WAITING FOR BROWSER...")
        self._auth_worker = SpotifyAuthWorker()
        self._auth_worker.finished.connect(self._on_auth_finished)
        self._auth_worker.start()

        # Open Spotify official authorization page in browser
        webbrowser.open(auth_url)

    def _on_auth_finished(self, success: bool, msg: str):
        self.btn_auth.setEnabled(True)
        if success:
            QMessageBox.information(self, "Connected!", "Spotify account connected successfully!")
            self._refresh_all_state()
        else:
            QMessageBox.warning(self, "Authentication Failed", f"Spotify authorization was not completed:\n{msg}")
            self._refresh_all_state()

    # =========================================================================
    # Playback UI Updaters
    # =========================================================================

    def _update_playback_ui(self, state: Optional[PlaybackState]):
        self._current_playback = state
        if not state or not state.item:
            self.lbl_track_title.setText("No track currently playing")
            self.lbl_track_artist.setText("Open Spotify and play music")
            self.lbl_track_album.setText("")
            self.lbl_time_cur.setText("0:00")
            self.lbl_time_total.setText("0:00")
            self.seek_slider.setValue(0)
            self.btn_play_pause.setText("▶ PLAY")
            return

        item = state.item
        self.lbl_track_title.setText(item.name)
        self.lbl_track_artist.setText(item.artist)
        self.lbl_track_album.setText(item.album)

        dur_sec = int(item.duration_ms / 1000)
        prog_sec = int(state.progress_ms / 1000)
        self.lbl_time_total.setText(item.duration_formatted)
        self.lbl_time_cur.setText(f"{prog_sec // 60}:{prog_sec % 60:02d}")

        if not self._is_seeking and dur_sec > 0:
            pct = int((prog_sec / dur_sec) * 1000)
            self.seek_slider.setValue(pct)

        self.btn_play_pause.setText("⏸ PAUSE" if state.is_playing else "▶ PLAY")
        self.btn_shuffle.setText(f"🔀 SHUFFLE: {'ON' if state.shuffle_state else 'OFF'}")
        self.btn_shuffle.setStyleSheet("color: #1db954; font-weight: bold;" if state.shuffle_state else "")

        self.btn_repeat.setText(f"🔁 REPEAT: {state.repeat_state.upper()}")
        self.btn_repeat.setStyleSheet("color: #1db954; font-weight: bold;" if state.repeat_state != "off" else "")

        # Download album art thumbnail asynchronously if changed
        if item.image_url and getattr(self, "_last_image_url", "") != item.image_url:
            self._last_image_url = item.image_url
            self._image_worker = ImageDownloadWorker(item.image_url)
            self._image_worker.image_loaded.connect(self._on_album_art_loaded)
            self._image_worker.start()

    def _on_album_art_loaded(self, img_bytes: bytes):
        pix = QPixmap()
        if pix.loadFromData(img_bytes):
            scaled = pix.scaled(110, 110, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            self.lbl_album_art.setPixmap(scaled)

    def _refresh_devices(self):
        self._run_async(spotify_service.get_devices, on_success_cb=self._update_devices_ui)

    def _update_devices_ui(self, devices: List[SpotifyDevice]):
        self.combo_devices.clear()
        for d in devices:
            active_tag = " [ACTIVE]" if d.is_active else ""
            self.combo_devices.addItem(f"{d.name} ({d.device_type}){active_tag}", d.id)

    def _on_transfer_device(self):
        dev_id = self.combo_devices.currentData()
        if dev_id:
            self._run_async(spotify_service.transfer_playback, dev_id, play=True)

    def _on_toggle_play_pause(self):
        if self._current_playback and self._current_playback.is_playing:
            self._run_async(spotify_service.pause)
        else:
            self._run_async(spotify_service.play)

    def _on_toggle_shuffle(self):
        cur = self._current_playback.shuffle_state if self._current_playback else False
        self._run_async(spotify_service.set_shuffle, not cur)

    def _on_toggle_repeat(self):
        cur = self._current_playback.repeat_state if self._current_playback else "off"
        next_mode = "context" if cur == "off" else ("track" if cur == "context" else "off")
        self._run_async(spotify_service.set_repeat, next_mode)

    def _on_volume_changed(self):
        val = self.slider_volume.value()
        self.lbl_vol_val.setText(f"{val}%")
        self._run_async(spotify_service.set_volume, val)

    def _on_seek_pressed(self):
        self._is_seeking = True

    def _on_seek_released(self):
        self._is_seeking = False
        if not self._current_playback or not self._current_playback.item:
            return
        slider_val = self.seek_slider.value()
        dur = self._current_playback.item.duration_ms
        target_ms = int((slider_val / 1000.0) * dur)
        self._run_async(spotify_service.seek, target_ms)

    # =========================================================================
    # Playlists UI Handlers
    # =========================================================================

    def _refresh_playlists(self):
        self._run_async(spotify_service.list_playlists, on_success_cb=self._on_playlists_loaded)

    def _on_playlists_loaded(self, playlists: List[SpotifyPlaylist]):
        self._playlists = playlists
        self.table_playlists.setRowCount(len(playlists))
        for row, p in enumerate(playlists):
            item_name = QTableWidgetItem(p.name)
            item_tracks = QTableWidgetItem(str(p.total_tracks))
            item_vis = QTableWidgetItem("Public" if p.is_public else "Private")
            self.table_playlists.setItem(row, 0, item_name)
            self.table_playlists.setItem(row, 1, item_tracks)
            self.table_playlists.setItem(row, 2, item_vis)

    def _on_playlist_selected(self):
        rows = self.table_playlists.selectedIndexes()
        if not rows:
            return
        row = rows[0].row()
        if 0 <= row < len(self._playlists):
            self._selected_playlist = self._playlists[row]
            spotify_context.set_active_playlist(self._selected_playlist.id, self._selected_playlist.name)
            self.lbl_selected_playlist.setText(f"Tracks in '{self._selected_playlist.name}'")
            self._run_async(spotify_service.get_playlist_tracks, self._selected_playlist.id, on_success_cb=self._on_tracks_loaded)

    def _on_tracks_loaded(self, tracks: List[SpotifyTrack]):
        self._current_tracks = tracks
        self.table_tracks.setRowCount(len(tracks))
        for row, t in enumerate(tracks):
            self.table_tracks.setItem(row, 0, QTableWidgetItem(str(row + 1)))
            self.table_tracks.setItem(row, 1, QTableWidgetItem(t.name))
            self.table_tracks.setItem(row, 2, QTableWidgetItem(t.artist))
            self.table_tracks.setItem(row, 3, QTableWidgetItem(t.duration_formatted))

    def _on_create_playlist_dialog(self):
        name, ok = QInputDialog.getText(self, "New Spotify Playlist", "Enter playlist name:")
        if ok and name.strip():
            self._run_async(spotify_service.create_playlist, name.strip(), on_success_cb=lambda p: self._refresh_playlists())

    def _on_rename_playlist_dialog(self):
        if not self._selected_playlist:
            QMessageBox.information(self, "Select Playlist", "Please select a playlist to rename.")
            return
        new_name, ok = QInputDialog.getText(self, "Rename Playlist", "Enter new name:", text=self._selected_playlist.name)
        if ok and new_name.strip():
            self._run_async(spotify_service.rename_playlist, self._selected_playlist.id, new_name.strip(), on_success_cb=lambda r: self._refresh_playlists())

    def _on_unfollow_playlist_dialog(self):
        if not self._selected_playlist:
            QMessageBox.information(self, "Select Playlist", "Please select a playlist to remove.")
            return

        p = self._selected_playlist
        # Safe confirmation explaining official unfollow semantics
        msg = (
            f"Are you sure you want to remove '{p.name}'?\n\n"
            "Official Spotify API notice: In accordance with Spotify's Web API, this operation "
            "unfollows the playlist and removes it from your library and profile. "
            "Permanent hard deletion is not supported by Spotify's Web API."
        )
        reply = QMessageBox.warning(
            self,
            "Confirm Playlist Removal",
            msg,
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel
        )
        if reply == QMessageBox.StandardButton.Ok:
            self._run_async(spotify_service.unfollow_playlist, p.id, on_success_cb=lambda r: self._refresh_playlists())

    def _on_cleanup_duplicates(self):
        if not self._selected_playlist:
            QMessageBox.information(self, "Select Playlist", "Please select a playlist to inspect for duplicate tracks.")
            return

        p = self._selected_playlist
        report = spotify_service.find_duplicate_tracks(p.id)
        if report.total_duplicates == 0:
            QMessageBox.information(self, "No Duplicates", f"No duplicate songs found in '{p.name}'.")
            return

        reply = QMessageBox.question(
            self,
            "Clean Duplicates",
            f"Found {report.total_duplicates} duplicate occurrences in '{p.name}'.\n\nWould you like Santra to clean them up?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_async(spotify_service.cleanup_duplicates, p.id, on_success_cb=lambda r: self._refresh_playlists())

    def _on_play_selected_playlist(self):
        if self._selected_playlist:
            self._run_async(spotify_service.play_playlist, self._selected_playlist.id)

    def _on_quick_add_track(self):
        query = self.input_search_track.text().strip()
        if not query:
            return
        if not self._selected_playlist:
            QMessageBox.information(self, "Select Playlist", "Please select a target playlist first.")
            return

        self._run_async(
            spotify_service.add_tracks_by_search,
            self._selected_playlist.id,
            query,
            on_success_cb=lambda r: (self.input_search_track.clear(), self._run_async(spotify_service.get_playlist_tracks, self._selected_playlist.id, on_success_cb=self._on_tracks_loaded))
        )

    def _on_remove_selected_track(self):
        rows = self.table_tracks.selectedIndexes()
        if not rows or not self._selected_playlist:
            return
        pos = rows[0].row()
        if 0 <= pos < len(self._current_tracks):
            track = self._current_tracks[pos]
            reply = QMessageBox.question(
                self,
                "Remove Song",
                f"Remove '{track.name}' by {track.artist} from this playlist?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._run_async(
                    spotify_service.remove_tracks_from_playlist,
                    self._selected_playlist.id,
                    positions=[pos],
                    on_success_cb=lambda r: self._run_async(spotify_service.get_playlist_tracks, self._selected_playlist.id, on_success_cb=self._on_tracks_loaded)
                )

    def _on_move_track_up(self):
        rows = self.table_tracks.selectedIndexes()
        if not rows or not self._selected_playlist:
            return
        pos = rows[0].row()
        if pos > 0:
            self._run_async(
                spotify_service.reorder_playlist_tracks,
                self._selected_playlist.id,
                range_start=pos,
                insert_before=pos - 1,
                on_success_cb=lambda r: self._run_async(spotify_service.get_playlist_tracks, self._selected_playlist.id, on_success_cb=self._on_tracks_loaded)
            )

    def _on_move_track_down(self):
        rows = self.table_tracks.selectedIndexes()
        if not rows or not self._selected_playlist:
            return
        pos = rows[0].row()
        if pos < len(self._current_tracks) - 1:
            self._run_async(
                spotify_service.reorder_playlist_tracks,
                self._selected_playlist.id,
                range_start=pos,
                insert_before=pos + 2,
                on_success_cb=lambda r: self._run_async(spotify_service.get_playlist_tracks, self._selected_playlist.id, on_success_cb=self._on_tracks_loaded)
            )
