"""
Jarvis Cyber-HUD Theme System.
Provides colors, gradients, fonts, and stylesheets faithfully matching the Jarvis 2.0 reference interface.
"""

from PyQt6.QtGui import QColor

class HUDColors:
    # Jarvis 2.0 Core Color Palette
    INTERFACE = QColor(0, 229, 255)         # --interface: #00e5ff
    BG = QColor(1, 6, 12)                   # --bg: #01060c
    BG_TOOL = QColor(2, 10, 12, 210)        # Tool badge backdrop
    BG_INPUT = QColor(2, 10, 15, 230)       # Input field backdrop

    # Accents & Overlays
    ACCENT_CYAN = QColor(0, 229, 255)
    ACCENT_CYAN_DIM = QColor(0, 229, 255, 110)
    ACCENT_CYAN_GLOW = QColor(0, 229, 255, 55)
    
    # State Accents
    STANDBY_CYAN = QColor(0, 229, 255)
    LISTENING_CYAN = QColor(0, 245, 255)
    THINKING_GOLD = QColor(255, 184, 0)
    SPEAKING_TEAL = QColor(0, 255, 179)
    ERROR_CORAL = QColor(255, 107, 107)

    # Aliases & State Colors
    CYAN_PRIMARY = QColor(0, 229, 255)
    CYAN_GLOW = QColor(0, 229, 255, 60)
    CYAN_DIM = QColor(0, 229, 255, 110)
    
    AMBER_STANDBY = QColor(255, 184, 0)
    AMBER_GLOW = QColor(255, 184, 0, 75)
    
    VIOLET_THINKING = QColor(157, 78, 221)
    VIOLET_GLOW = QColor(157, 78, 221, 85)
    
    TEAL_SPEAKING = QColor(0, 255, 179)
    TEAL_GLOW = QColor(0, 255, 179, 75)
    
    CRIMSON_ERROR = QColor(255, 107, 107)
    CRIMSON_GLOW = QColor(255, 107, 107, 85)

    # Backgrounds
    BG_VOID = QColor(1, 6, 12)
    BG_PANEL = QColor(2, 10, 15, 220)
    BG_CARD = QColor(4, 14, 22, 190)

    # Text & Details
    TEXT_BRIGHT = QColor(240, 246, 252)
    TEXT_JARVIS = QColor(234, 249, 255)     # #eaf9ff (Glowing Jarvis response)
    TEXT_USER = QColor(255, 255, 255, 133)  # Opacity 0.52
    TEXT_DIM = QColor(255, 255, 255, 95)    # Rail items / hints
    TEXT_MUTED = QColor(0, 229, 255, 150)
    
    # Borders & Reticles
    BORDER_CYAN = QColor(0, 229, 255, 95)
    BORDER_DIM = QColor(0, 229, 255, 45)
    BORDER_GLOW = QColor(0, 229, 255, 160)
    BORDER_MUTED = QColor(0, 229, 255, 30)

def get_hud_stylesheet() -> str:
    """Master stylesheet for the Jarvis 2.0 Holographic HUD."""
    return """
    QMainWindow {
        background-color: #01060c;
    }
    QWidget {
        color: #00e5ff;
        font-family: 'Chakra Petch', 'Segoe UI', 'Inter', system-ui, sans-serif;
    }
    
    /* Command Input Line */
    QLineEdit.cyberInput {
        background-color: rgba(2, 10, 15, 230);
        border: 1px solid rgba(0, 229, 255, 75);
        border-radius: 4px;
        color: #ffffff;
        font-family: 'Chakra Petch', 'Segoe UI', sans-serif;
        font-size: 13px;
        letter-spacing: 0.05em;
        padding: 9px 16px;
    }
    QLineEdit.cyberInput:focus {
        border: 1px solid #00e5ff;
        background-color: rgba(3, 15, 24, 250);
        color: #eaf9ff;
    }
    QLineEdit.cyberInput::placeholder {
        color: rgba(0, 229, 255, 90);
        letter-spacing: 0.08em;
    }
    
    /* Cyber Button */
    QPushButton.cyberButton {
        background-color: rgba(0, 229, 255, 25);
        border: 1px solid rgba(0, 229, 255, 90);
        border-radius: 3px;
        color: #00e5ff;
        padding: 8px 18px;
        font-family: 'Chakra Petch', 'Segoe UI', sans-serif;
        font-weight: 600;
        font-size: 11px;
        letter-spacing: 0.18em;
        text-transform: uppercase;
    }
    QPushButton.cyberButton:hover {
        background-color: rgba(0, 229, 255, 55);
        border: 1px solid #00e5ff;
        color: #ffffff;
    }
    QPushButton.cyberButton:pressed {
        background-color: rgba(0, 229, 255, 95);
    }
    
    /* Scrollbars */
    QScrollBar:vertical {
        background: transparent;
        width: 4px;
        margin: 0px;
    }
    QScrollBar::handle:vertical {
        background: rgba(0, 229, 255, 60);
        min-height: 20px;
        border-radius: 2px;
    }
    QScrollBar::handle:vertical:hover {
        background: #00e5ff;
    }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
        height: 0px;
    }
    """
