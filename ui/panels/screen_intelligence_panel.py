"""Screen Intelligence & Explanation HUD Panel for JARVIS PyQt6 UI.

Provides non-blocking one-click triggers for:
- Analyze Screen
- Explain Again / Follow-up
- Simplify Explanation
- Show Important Points
- Copy Explanation to Clipboard
- Save Explanation to Markdown File
"""

import logging
from typing import Optional, Callable
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QApplication
)

from ui.widgets.hud_frame import HUDFrame
from core.vision.explain_engine import explain_engine, ExplanationStyle
from core.vision.screen_understanding import screen_understanding_engine
from core.files.file_creator import file_creator

logger = logging.getLogger("Jarvis.ScreenIntelligencePanel")


class ScreenAnalysisWorker(QThread):
    """Background worker executing screen understanding without freezing PyQt6 UI."""
    analysis_completed = pyqtSignal(dict)
    analysis_failed = pyqtSignal(str)

    def __init__(self, query: str = "Explain what is visible on my screen.", provider_manager: Optional[Any] = None, explain_engine: Optional[Any] = None):
        super().__init__()
        self.query = query
        self.provider_manager = provider_manager
        self._custom_explain_engine = explain_engine

    def run(self):
        try:
            active_engine = self._custom_explain_engine or explain_engine
            explanation = active_engine.explain(self.query, provider_manager=self.provider_manager)
            self.analysis_completed.emit({
                "summary": explanation.summary,
                "important_points": explanation.important_points,
                "full_text": explanation.detailed_text,
                "style": explanation.style.value if hasattr(explanation.style, "value") else str(explanation.style),
                "model_used": explanation.model_used
            })
        except Exception as e:
            logger.error(f"Screen analysis worker error: {e}", exc_info=True)
            self.analysis_failed.emit(str(e))


class ScreenIntelligencePanel(HUDFrame):
    """Futuristic holographic panel for desktop visual intelligence."""

    def __init__(self, parent=None, on_speech_output_cb: Optional[Callable[[str], None]] = None, provider_manager: Optional[Any] = None):
        super().__init__(parent)
        self.on_speech_output_cb = on_speech_output_cb
        self.provider_manager = provider_manager
        self._current_explanation_text = ""
        self._worker: Optional[ScreenAnalysisWorker] = None
        self._init_ui()

    def _init_ui(self):
        hdr = QLabel("SCREEN INTELLIGENCE & EXPLAIN ENGINE")
        hdr.setProperty("class", "hudSectionTitle")
        self.layout.addWidget(hdr)

        self.status_label = QLabel("Status: Ready | No screen analyzed")
        self.status_label.setStyleSheet("color: rgba(148, 163, 184, 0.9); font-size: 11px;")
        self.layout.addWidget(self.status_label)

        # Action Buttons Layout (Grid / Flow)
        btn_layout_1 = QHBoxLayout()
        self.btn_analyze = QPushButton("🔍 Analyze Screen")
        self.btn_analyze.clicked.connect(lambda: self.trigger_analysis("Explain what is on my screen in simple terms."))
        btn_layout_1.addWidget(self.btn_analyze)

        self.btn_points = QPushButton("📌 Key Points")
        self.btn_points.clicked.connect(lambda: self.trigger_analysis("What are the important points here?"))
        btn_layout_1.addWidget(self.btn_points)
        self.layout.addLayout(btn_layout_1)

        btn_layout_2 = QHBoxLayout()
        self.btn_simplify = QPushButton("💡 Simplify")
        self.btn_simplify.clicked.connect(lambda: self.trigger_analysis("I still don't understand. Explain it with an example in simple language."))
        btn_layout_2.addWidget(self.btn_simplify)

        self.btn_technical = QPushButton("⚙️ Technical")
        self.btn_technical.clicked.connect(lambda: self.trigger_analysis("Explain the technical architecture and code line by line."))
        btn_layout_2.addWidget(self.btn_technical)
        self.layout.addLayout(btn_layout_2)

        # Output preview text box
        self.text_preview = QTextEdit()
        self.text_preview.setReadOnly(True)
        self.text_preview.setPlaceholderText("Explanation output will appear here...")
        self.text_preview.setStyleSheet("""
            QTextEdit {
                background: rgba(15, 23, 42, 0.7);
                border: 1px solid rgba(56, 189, 248, 0.3);
                border-radius: 4px;
                color: #e2e8f0;
                font-family: Consolas, monospace;
                font-size: 11px;
            }
        """)
        self.layout.addWidget(self.text_preview)

        # Action Utility Row (Copy / Save)
        util_layout = QHBoxLayout()
        self.btn_copy = QPushButton("📋 Copy Text")
        self.btn_copy.clicked.connect(self._copy_to_clipboard)
        util_layout.addWidget(self.btn_copy)

        self.btn_save = QPushButton("💾 Save to File")
        self.btn_save.clicked.connect(self._save_to_file)
        util_layout.addWidget(self.btn_save)

        self.layout.addLayout(util_layout)

    def trigger_analysis(self, prompt: str):
        """Starts asynchronous screen analysis."""
        self.status_label.setText("Status: Analyzing screen...")
        self.btn_analyze.setEnabled(False)
        self.text_preview.setPlainText("Capturing screen and analyzing context...")

        self._worker = ScreenAnalysisWorker(query=prompt, provider_manager=self.provider_manager)
        self._worker.analysis_completed.connect(self._on_analysis_completed)
        self._worker.analysis_failed.connect(self._on_analysis_failed)
        self._worker.start()

    def _on_analysis_completed(self, data: dict):
        self.btn_analyze.setEnabled(True)
        self.status_label.setText(f"Status: Analysis Complete (Style: {data.get('style', 'default')})")
        full_text = data.get("full_text", "") or data.get("summary", "")
        self._current_explanation_text = full_text
        self.text_preview.setPlainText(full_text)

        if self.on_speech_output_cb and full_text:
            # Speak the high-level summary
            summary = data.get("summary", "") or full_text.split("\n\n")[0]
            self.on_speech_output_cb(summary[:300])

    def _on_analysis_failed(self, error_msg: str):
        self.btn_analyze.setEnabled(True)
        self.status_label.setText(f"Status: Error: {error_msg}")
        self.text_preview.setPlainText(f"Failed to analyze screen:\n{error_msg}")

    def _copy_to_clipboard(self):
        """Copies current explanation to system clipboard."""
        if self._current_explanation_text:
            QApplication.clipboard().setText(self._current_explanation_text)
            self.status_label.setText("Status: Copied explanation to clipboard!")

    def _save_to_file(self):
        """Saves current explanation to a timestamped Markdown file on Desktop."""
        if not self._current_explanation_text:
            return
        res = file_creator.create_file(
            filename="Screen_Explanation.md",
            destination="Desktop",
            content=self._current_explanation_text,
            language="markdown",
            allow_overwrite=False
        )
        if res.success:
            self.status_label.setText(f"Status: Saved to {res.filename} on Desktop!")
        else:
            self.status_label.setText(f"Status: {res.message}")
