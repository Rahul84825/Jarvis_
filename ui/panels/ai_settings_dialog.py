"""Secure AI Provider & API Key Configuration Dialog for JARVIS PyQt6 UI.

Allows users to:
- Add or update API keys securely (never logged or exposed)
- Switch models
- Test connectivity with health check
- Configure provider priority ranking
- Enable/disable individual providers
- Toggle Free-Tier Only mode
"""

import logging
from typing import Optional
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)

from core.ai.provider_settings import provider_settings_manager, AIProviderConfig
from core.ai.provider_manager import ProviderManager

logger = logging.getLogger("Jarvis.AISettingsDialog")


class ConnectivityTestWorker(QThread):
    """Background worker testing connectivity to an AI provider."""
    test_finished = pyqtSignal(str, bool, str)

    def __init__(self, provider_id: str):
        super().__init__()
        self.provider_id = provider_id

    def run(self):
        try:
            prov_mgr = ProviderManager()
            prov = prov_mgr.get_provider(self.provider_id)
            if not prov:
                self.test_finished.emit(self.provider_id, False, "Provider not registered.")
                return

            if not prov.is_available():
                self.test_finished.emit(self.provider_id, False, "Missing API key or credentials.")
                return

            ok = prov.health_check()
            if ok:
                self.test_finished.emit(self.provider_id, True, f"Connection to {prov.get_name()} succeeded!")
            else:
                self.test_finished.emit(self.provider_id, False, "Health check failed (endpoint returned error or timeout).")
        except Exception as e:
            self.test_finished.emit(self.provider_id, False, f"Error: {e}")


class AISettingsDialog(QDialog):
    """Modal dialog for managing AI providers and credentials."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SANTRA — AI Provider & API Key Management")
        self.setMinimumWidth(650)
        self.setMinimumHeight(450)
        self.setStyleSheet("""
            QDialog {
                background: #0f172a;
                color: #e2e8f0;
                font-family: 'Segoe UI', sans-serif;
            }
            QLabel {
                color: #cbd5e1;
            }
            QLineEdit, QComboBox {
                background: #1e293b;
                border: 1px solid #38bdf8;
                border-radius: 4px;
                padding: 6px;
                color: #f8fafc;
            }
            QPushButton {
                background: #0284c7;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 6px 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #0369a1;
            }
            QTableWidget {
                background: #1e293b;
                border: 1px solid #334155;
                color: #f8fafc;
                gridline-color: #334155;
            }
        """)
        self._test_worker: Optional[ConnectivityTestWorker] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("AI PROVIDER & MULTI-API ENGINE CONFIGURATION")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title)

        # Free tier toggle
        self.chk_free_only = QCheckBox("Enforce Free-Tier Only Mode (Never route to paid models)")
        self.chk_free_only.setChecked(provider_settings_manager.free_only_mode)
        self.chk_free_only.stateChanged.connect(self._on_free_tier_toggled)
        layout.addWidget(self.chk_free_only)

        # Providers Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Provider", "Model", "Priority", "Key Status", "Enabled"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # Edit Section
        edit_layout = QHBoxLayout()
        self.cmb_provider = QComboBox()
        for p in provider_settings_manager.list_providers_summary():
            self.cmb_provider.addItem(p["name"], p["provider_id"])
        self.cmb_provider.currentIndexChanged.connect(self._on_provider_selected)
        edit_layout.addWidget(QLabel("Selected:"))
        edit_layout.addWidget(self.cmb_provider)

        self.txt_key = QLineEdit()
        self.txt_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.txt_key.setPlaceholderText("Paste API key here...")
        edit_layout.addWidget(self.txt_key)

        self.btn_save_key = QPushButton("Save Key")
        self.btn_save_key.clicked.connect(self._save_key)
        edit_layout.addWidget(self.btn_save_key)

        self.btn_test = QPushButton("Test Connection")
        self.btn_test.clicked.connect(self._test_connection)
        edit_layout.addWidget(self.btn_test)

        layout.addLayout(edit_layout)

        # -------------------------------------------------------------
        # Multi-Layer Caching & Cost Optimization Section (Section 10)
        # -------------------------------------------------------------
        from core.ai.caching import nemotron_cache
        from PyQt6.QtWidgets import QGroupBox
        cache_box = QGroupBox("INTELLIGENT AI CACHING & COST OPTIMIZATION")
        cache_box.setStyleSheet("QGroupBox { font-weight: bold; color: #38bdf8; border: 1px solid #334155; margin-top: 10px; padding: 10px; border-radius: 4px; }")
        cache_layout = QVBoxLayout(cache_box)

        toggles_layout = QHBoxLayout()
        self.chk_cache = QCheckBox("Enable AI Cache (Exact, Knowledge & Task Layers)")
        self.chk_cache.setChecked(nemotron_cache.is_enabled)
        self.chk_cache.stateChanged.connect(self._on_cache_toggled)
        toggles_layout.addWidget(self.chk_cache)

        self.chk_semantic = QCheckBox("Enable Layer B Semantic Caching")
        self.chk_semantic.setChecked(nemotron_cache.is_semantic_enabled)
        self.chk_semantic.stateChanged.connect(self._on_semantic_toggled)
        toggles_layout.addWidget(self.chk_semantic)
        cache_layout.addLayout(toggles_layout)

        # Cache Stats Display
        self.lbl_cache_stats = QLabel()
        self.lbl_cache_stats.setStyleSheet("color: #e2e8f0; font-family: monospace; font-size: 11px;")
        cache_layout.addWidget(self.lbl_cache_stats)

        cache_btn_layout = QHBoxLayout()
        self.btn_refresh_stats = QPushButton("Refresh Cache Stats")
        self.btn_refresh_stats.clicked.connect(self._refresh_cache_stats)
        cache_btn_layout.addWidget(self.btn_refresh_stats)

        self.btn_clear_cache = QPushButton("Clear Cache")
        self.btn_clear_cache.setStyleSheet("background: #dc2626;")
        self.btn_clear_cache.clicked.connect(self._clear_cache)
        cache_btn_layout.addWidget(self.btn_clear_cache)
        cache_layout.addLayout(cache_btn_layout)

        layout.addWidget(cache_box)

        # Status output
        self.lbl_status = QLabel("Ready.")
        self.lbl_status.setStyleSheet("color: #94a3b8; font-style: italic;")
        layout.addWidget(self.lbl_status)

        # Bottom Close button
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

        self._refresh_table()
        self._refresh_cache_stats()

    def _refresh_table(self):
        provs = provider_settings_manager.list_providers_summary()
        self.table.setRowCount(len(provs))
        for row, p in enumerate(provs):
            self.table.setItem(row, 0, QTableWidgetItem(p["name"]))
            self.table.setItem(row, 1, QTableWidgetItem(p["model"]))
            self.table.setItem(row, 2, QTableWidgetItem(str(p["priority"])))
            key_stat = "Configured" if p.get("api_key") else "Missing Key"
            self.table.setItem(row, 3, QTableWidgetItem(key_stat))
            enabled_str = "Yes" if p["enabled"] else "No"
            self.table.setItem(row, 4, QTableWidgetItem(enabled_str))

    def _on_free_tier_toggled(self, state):
        provider_settings_manager.set_free_only_mode(state == Qt.CheckState.Checked.value)
        self.lbl_status.setText("Free-tier mode updated.")

    def _on_provider_selected(self, index):
        self.txt_key.clear()
        self.lbl_status.setText("Ready.")

    def _save_key(self):
        pid = self.cmb_provider.currentData()
        key_val = self.txt_key.text().strip()
        if key_val:
            provider_settings_manager.update_provider_key(pid, key_val)
            self.txt_key.clear()
            self._refresh_table()
            self.lbl_status.setText(f"API key updated successfully for {self.cmb_provider.currentText()}.")
        else:
            self.lbl_status.setText("Please enter an API key.")

    def _test_connection(self):
        pid = self.cmb_provider.currentData()
        self.lbl_status.setText(f"Testing connectivity to {self.cmb_provider.currentText()}...")
        self.btn_test.setEnabled(False)

        self._test_worker = ConnectivityTestWorker(pid)
        self._test_worker.test_finished.connect(self._on_test_finished)
        self._test_worker.start()

    def _on_test_finished(self, pid: str, success: bool, message: str):
        self.btn_test.setEnabled(True)
        if success:
            self.lbl_status.setStyleSheet("color: #4ade80; font-weight: bold;")
            self.lbl_status.setText(f"SUCCESS: {message}")
        else:
            self.lbl_status.setStyleSheet("color: #f87171; font-weight: bold;")
            self.lbl_status.setText(f"FAILED: {message}")

    def _on_cache_toggled(self, state):
        from core.ai.caching import nemotron_cache
        nemotron_cache.is_enabled = (state == Qt.CheckState.Checked.value)
        status_msg = "AI Caching enabled." if nemotron_cache.is_enabled else "AI Caching disabled (All calls bypass cache)."
        self.lbl_status.setText(status_msg)

    def _on_semantic_toggled(self, state):
        from core.ai.caching import nemotron_cache
        nemotron_cache.is_semantic_enabled = (state == Qt.CheckState.Checked.value)
        status_msg = "Semantic Caching enabled." if nemotron_cache.is_semantic_enabled else "Semantic Caching disabled."
        self.lbl_status.setText(status_msg)

    def _refresh_cache_stats(self):
        from core.ai.caching import nemotron_cache
        stats = nemotron_cache.get_stats()
        text = (
            f"Hits: {stats.total_hits} (Exact: {stats.exact_hits}, Semantic: {stats.semantic_hits}, "
            f"Knowledge: {stats.knowledge_hits}) | Misses: {stats.misses} | "
            f"Bypasses: {stats.bypasses} | Saved API Calls: {stats.api_calls_saved} | "
            f"Hit Rate: {stats.hit_rate_pct:.1f}%"
        )
        self.lbl_cache_stats.setText(text)

    def _clear_cache(self):
        from core.ai.caching import nemotron_cache
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Confirm Clear Cache",
            "Are you sure you want to clear all cached AI responses?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            cleared = nemotron_cache.clear()
            self._refresh_cache_stats()
            self.lbl_status.setText(f"Cleared {cleared} entries from the cache.")
