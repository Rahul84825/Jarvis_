"""Pronunciation & Wake-Word Intelligence Configuration Dialog for SANTRA PyQt6 UI.

Allows users to:
- View and manage canonical assistant name (SANTRA) and Indian English pronunciation variants
- Adjust wake-word confidence threshold and VAD sensitivity
- Select wake-word verification mode (Two-Stage Verification, Direct, Strict)
- Enable/disable STT vocabulary biasing and background wake-word detection
- Run automated pronunciation diagnostic benchmarks
"""

import logging
from typing import Optional
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QComboBox, QCheckBox, QSlider, QTextEdit, QMessageBox, QGroupBox
)

from config import config
from core.pronunciation_manager import pronunciation_manager

logger = logging.getLogger("Jarvis.PronunciationSettingsDialog")


class PronunciationBenchmarkWorker(QThread):
    """Background worker running local pronunciation intelligence diagnostic tests."""
    test_finished = pyqtSignal(str, bool, str)

    def run(self):
        try:
            from core.wake_word_evaluator import wake_word_evaluator
            report = wake_word_evaluator.run_quick_evaluation()
            summary = (
                f"Recall: {report['recall']:.1%}\n"
                f"Precision: {report['precision']:.1%}\n"
                f"False Acceptance Rate: {report['far']:.1%}\n"
                f"False Rejection Rate: {report['frr']:.1%}\n"
                f"Avg Verification Latency: {report['avg_latency_ms']:.1f}ms"
            )
            self.test_finished.emit("Diagnostic Benchmark Completed", True, summary)
        except Exception as e:
            self.test_finished.emit("Benchmark Failed", False, str(e))


class PronunciationSettingsDialog(QDialog):
    """Modal dialog for managing Pronunciation & Wake-Word Intelligence."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("SANTRA — Pronunciation & Wake-Word Intelligence")
        self.setMinimumWidth(680)
        self.setMinimumHeight(520)
        self.setStyleSheet("""
            QDialog {
                background: #0f172a;
                color: #e2e8f0;
                font-family: 'Segoe UI', sans-serif;
            }
            QGroupBox {
                border: 1px solid #334155;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 10px;
                font-weight: bold;
                color: #38bdf8;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
            }
            QLabel {
                color: #cbd5e1;
            }
            QLineEdit, QComboBox, QTextEdit {
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
                padding: 7px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #0369a1;
            }
            QCheckBox {
                color: #f8fafc;
                spacing: 8px;
            }
        """)
        self._worker: Optional[PronunciationBenchmarkWorker] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.setContentsMargins(18, 18, 18, 18)

        # Header Title
        title_label = QLabel("Indian Accent Adaptation & Pronunciation Intelligence")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #38bdf8;")
        layout.addWidget(title_label)

        sub_label = QLabel("Configure how SANTRA recognizes its name across natural Indian English pronunciations without altering your natural accent.")
        sub_label.setWordWrap(True)
        sub_label.setStyleSheet("color: #94a3b8; font-size: 12px;")
        layout.addWidget(sub_label)

        # Group 1: Identity & Phonetic Variants
        grp_identity = QGroupBox("Assistant Identity & Pronunciation Variants")
        layout_id = QVBoxLayout(grp_identity)

        row_canon = QHBoxLayout()
        row_canon.addWidget(QLabel("Canonical Assistant Name:"))
        self.txt_canon = QLineEdit(config.assistant_name)
        self.txt_canon.setReadOnly(True)
        self.txt_canon.setStyleSheet("background: #0f172a; border: 1px solid #475569; color: #38bdf8; font-weight: bold;")
        row_canon.addWidget(self.txt_canon)
        layout_id.addLayout(row_canon)

        layout_id.addWidget(QLabel("Active Pronunciation Variants (comma-separated):"))
        variants_str = ", ".join(getattr(config, "pronunciation_variants", pronunciation_manager.DEFAULT_VARIANTS))
        self.txt_variants = QLineEdit(variants_str)
        layout_id.addWidget(self.txt_variants)

        layout.addWidget(grp_identity)

        # Group 2: Two-Stage Detection & Calibration
        grp_detect = QGroupBox("Two-Stage Detection & Calibration")
        layout_det = QVBoxLayout(grp_detect)

        # Verification mode combo
        row_mode = QHBoxLayout()
        row_mode.addWidget(QLabel("Wake-Word Verification Mode:"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItems([
            "Two-Stage Verification (Recommended - Low Latency & High Accuracy)",
            "Direct ASR Wake (Continuous Acoustic Spotting)",
            "Strict Canonical Only (Reject Variants)"
        ])
        current_mode = getattr(config, "wakeword_verification_mode", "two_stage")
        if current_mode == "direct":
            self.combo_mode.setCurrentIndex(1)
        elif current_mode == "strict":
            self.combo_mode.setCurrentIndex(2)
        else:
            self.combo_mode.setCurrentIndex(0)
        row_mode.addWidget(self.combo_mode)
        layout_det.addLayout(row_mode)

        # Confidence Threshold Slider
        row_conf = QHBoxLayout()
        conf_val = int(getattr(config, "wakeword_min_confidence", 0.45) * 100)
        self.lbl_conf = QLabel(f"Confidence Threshold: {conf_val}%")
        self.slider_conf = QSlider(Qt.Orientation.Horizontal)
        self.slider_conf.setRange(20, 90)
        self.slider_conf.setValue(conf_val)
        self.slider_conf.valueChanged.connect(lambda v: self.lbl_conf.setText(f"Confidence Threshold: {v}%"))
        row_conf.addWidget(self.lbl_conf)
        row_conf.addWidget(self.slider_conf)
        layout_det.addLayout(row_conf)

        # Debounce setting
        row_deb = QHBoxLayout()
        row_deb.addWidget(QLabel("Temporal Debounce (seconds):"))
        self.txt_debounce = QLineEdit(str(getattr(config, "wakeword_debounce_sec", 1.5)))
        self.txt_debounce.setMaximumWidth(80)
        row_deb.addWidget(self.txt_debounce)

        self.chk_stt_bias = QCheckBox("Enable STT Vocabulary Biasing (Faster-Whisper Context Prompt)")
        self.chk_stt_bias.setChecked(getattr(config, "stt_vocabulary_biasing", True))
        row_deb.addWidget(self.chk_stt_bias)
        layout_det.addLayout(row_deb)

        layout.addWidget(grp_detect)

        # Group 3: Diagnostics & Benchmark
        grp_diag = QGroupBox("Diagnostic Tools & Verification")
        layout_diag = QHBoxLayout(grp_diag)

        self.btn_run_benchmark = QPushButton("▶ Run Accent Benchmark")
        self.btn_run_benchmark.clicked.connect(self._run_benchmark)
        layout_diag.addWidget(self.btn_run_benchmark)

        self.lbl_bench_status = QLabel("Ready for test.")
        self.lbl_bench_status.setStyleSheet("color: #94a3b8; font-style: italic;")
        layout_diag.addWidget(self.lbl_bench_status)

        layout.addWidget(grp_diag)

        # Bottom Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()

        self.btn_save = QPushButton("Save & Apply")
        self.btn_save.clicked.connect(self._save_settings)
        btn_box.addWidget(self.btn_save)

        self.btn_cancel = QPushButton("Close")
        self.btn_cancel.setStyleSheet("background: #334155;")
        self.btn_cancel.clicked.connect(self.close)
        btn_box.addWidget(self.btn_cancel)

        layout.addLayout(btn_box)

    def _run_benchmark(self):
        self.btn_run_benchmark.setEnabled(False)
        self.lbl_bench_status.setText("Running acoustic pronunciation benchmark...")
        self._worker = PronunciationBenchmarkWorker()
        self._worker.test_finished.connect(self._on_benchmark_finished)
        self._worker.start()

    def _on_benchmark_finished(self, title: str, success: bool, details: str):
        self.btn_run_benchmark.setEnabled(True)
        if success:
            self.lbl_bench_status.setText("Benchmark completed successfully.")
            QMessageBox.information(self, title, details)
        else:
            self.lbl_bench_status.setText("Benchmark encountered an error.")
            QMessageBox.warning(self, title, f"Details: {details}")

    def _save_settings(self):
        try:
            # Parse variants
            raw_vars = self.txt_variants.text()
            vars_list = [v.strip().lower() for v in raw_vars.split(",") if v.strip()]
            if not vars_list:
                vars_list = pronunciation_manager.DEFAULT_VARIANTS

            config.pronunciation_variants = vars_list
            pronunciation_manager.variants = vars_list
            pronunciation_manager._compile_patterns()

            # Mode
            idx = self.combo_mode.currentIndex()
            mode_map = {0: "two_stage", 1: "direct", 2: "strict"}
            config.wakeword_verification_mode = mode_map.get(idx, "two_stage")

            # Confidence
            conf = self.slider_conf.value() / 100.0
            config.wakeword_min_confidence = conf
            pronunciation_manager.min_confidence = conf

            # Debounce
            try:
                deb = float(self.txt_debounce.text().strip())
                config.wakeword_debounce_sec = max(0.5, min(5.0, deb))
            except ValueError:
                config.wakeword_debounce_sec = 1.5

            config.stt_vocabulary_biasing = self.chk_stt_bias.isChecked()

            # Persist to config.json
            import json
            cfg_path = config.config_path
            data = {}
            if cfg_path.exists():
                with open(cfg_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            data["pronunciation_variants"] = config.pronunciation_variants
            data["wakeword_verification_mode"] = config.wakeword_verification_mode
            data["wakeword_min_confidence"] = config.wakeword_min_confidence
            data["wakeword_debounce_sec"] = config.wakeword_debounce_sec
            data["stt_vocabulary_biasing"] = config.stt_vocabulary_biasing

            with open(cfg_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)

            logger.info("[PRONUNCIATION_SETTINGS] Settings saved and applied successfully.")
            QMessageBox.information(self, "Settings Saved", "Pronunciation and wake-word intelligence settings applied successfully.")
            self.accept()
        except Exception as e:
            logger.error(f"Error saving pronunciation settings: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")
