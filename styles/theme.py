FONT_FAMILY   = "Urbanist, Inter, Segoe UI, system-ui, sans-serif"
DISPLAY_FONT  = "Urbanist, Inter, Segoe UI, system-ui, sans-serif"
LOGO_FONT     = "'Tilt Warp', system-ui, sans-serif"

COLORS: dict[str, str] = {
    "bg_primary":    "#141414",
    "bg_secondary":  "#1c1c1c",
    "bg_card":       "#202020",
    "bg_hover":      "#2a2a2a",
    "bg_sidebar":    "#121212",
    "border":        "#303030",
    "text_primary":  "#e8e6e3",
    "text_secondary":"#a3a09c",
    "text_muted":    "#6b6865",
    "text_on_accent":"#ffffff",
    "danger":        "#d65d5d",
    "danger_dim":    "#2d1919",
    "danger_border": "#4a2424",
    "warning":       "#c9a044",
    "warning_dim":   "#2d2414",
    "info":          "#5a9fd4",
    "commit_line":   "#303030",
    "border_focus":  "#d4775c",
    "accent":        "#d4775c",
    "accent_hover":  "#c06a52",
    "accent_dim":    "#2e1f1a",
    "commit_node":   "#d4775c",
    "tag_bg":        "#2e1f1a",
    "tag_text":      "#d4775c",
}


def scrollbar_style() -> str:
    """Unified scrollbar stylesheet fragment — apply to any QScrollArea."""
    return f"""
        QScrollBar:vertical {{
            background: transparent; width: 6px; margin: 0; border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {COLORS['border']}; border-radius: 3px; min-height: 24px;
        }}
        QScrollBar::handle:vertical:hover {{ background: {COLORS['text_muted']}; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QScrollBar:horizontal {{
            background: transparent; height: 6px; margin: 0; border: none;
        }}
        QScrollBar::handle:horizontal {{
            background: {COLORS['border']}; border-radius: 3px; min-width: 24px;
        }}
        QScrollBar::handle:horizontal:hover {{ background: {COLORS['text_muted']}; }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
    """


def make_global_style() -> str:
    return f"""
* {{
    font-family: {FONT_FAMILY};
    color: {COLORS['text_primary']};
}}

QMainWindow, QWidget#root {{
    background-color: {COLORS['bg_primary']};
}}

QWidget {{
    background-color: transparent;
}}

QLabel {{
    background: transparent;
}}

QFrame {{
    background: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    border-radius: 3px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {COLORS['border']};
    border-radius: 3px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background: {COLORS['text_muted']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 6px;
    border-radius: 3px;
}}

QScrollBar::handle:horizontal {{
    background: {COLORS['border']};
    border-radius: 3px;
    min-width: 24px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {COLORS['text_muted']};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}

QToolTip {{
    background-color: {COLORS['bg_card']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
}}

QPushButton {{
    font-family: {DISPLAY_FONT};
}}
"""


GLOBAL_STYLE = make_global_style()

SIDEBAR_STYLE = f"""
QWidget#sidebar {{
    background-color: {COLORS['bg_sidebar']};
    border-right: 1px solid {COLORS['border']};
}}
"""

CARD_STYLE = f"""
QWidget#card {{
    background-color: {COLORS['bg_card']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
}}
"""

BTN_PRIMARY = f"""
QPushButton {{
    background-color: {COLORS['accent']};
    color: {COLORS['text_on_accent']};
    border: none;
    border-radius: 8px;
    padding: 11px 22px;
    font-size: 14px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {COLORS['accent_hover']};
}}
QPushButton:pressed {{
    background-color: {COLORS['accent_hover']};
    opacity: 0.9;
}}
QPushButton:disabled {{
    background-color: {COLORS['bg_hover']};
    color: {COLORS['text_muted']};
}}
"""

BTN_SECONDARY = f"""
QPushButton {{
    background-color: transparent;
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 11px 22px;
    font-size: 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {COLORS['bg_hover']};
    border-color: {COLORS['text_muted']};
}}
QPushButton:pressed {{
    background-color: {COLORS['bg_hover']};
}}
"""

BTN_GHOST = f"""
QPushButton {{
    background-color: transparent;
    color: {COLORS['text_secondary']};
    border: none;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    font-weight: 500;
    text-align: left;
}}
QPushButton:hover {{
    background-color: {COLORS['bg_hover']};
    color: {COLORS['text_primary']};
}}
QPushButton:checked {{
    background-color: {COLORS['accent_dim']};
    color: {COLORS['accent']};
}}
"""

INPUT_STYLE = f"""
QLineEdit {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 11px 16px;
    font-size: 14px;
}}
QLineEdit:focus {{
    border-color: {COLORS['border_focus']};
    outline: none;
}}
QLineEdit::placeholder {{
    color: {COLORS['text_muted']};
}}
"""

TABLE_STYLE = f"""
QTableWidget {{
    background-color: transparent;
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    gridline-color: {COLORS['border']};
    outline: none;
}}
QTableWidget::item {{
    padding: 12px 16px;
    border-bottom: 1px solid {COLORS['border']};
    color: {COLORS['text_primary']};
    font-size: 13px;
}}
QTableWidget::item:selected {{
    background-color: {COLORS['accent_dim']};
    color: {COLORS['text_primary']};
}}
QTableWidget::item:hover {{
    background-color: {COLORS['bg_hover']};
}}
QHeaderView::section {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['text_muted']};
    border: none;
    border-bottom: 1px solid {COLORS['border']};
    padding: 10px 16px;
    font-size: 12px;
    font-weight: 600;
}}
QHeaderView::section:first {{
    border-top-left-radius: 8px;
}}
QHeaderView::section:last {{
    border-top-right-radius: 8px;
}}
"""


def heading_style(size: int, weight: int = 700, color: str = "") -> str:
    c = color or COLORS["text_primary"]
    return (
        f"font-family: {DISPLAY_FONT}; font-size: {size}px; "
        f"font-weight: {weight}; color: {c}; background: transparent;"
    )


AVATAR_PALETTE = [
    "#7c83db",  "#d4a24e",  "#c86a6a",  "#9a7fd1",  "#4fb8c9",
    "#d48a54",  "#c97ba3",  "#54b09e",  "#8fb85c",  "#a994d4",
]


def hash_color(text: str, palette: list | None = None) -> str:
    import hashlib
    p = palette or AVATAR_PALETTE
    return p[int(hashlib.md5(text.encode()).hexdigest(), 16) % len(p)]


def card_shadow(widget, blur: int = 16, offset_y: int = 2, alpha: int = 40):
    from PyQt5.QtWidgets import QGraphicsDropShadowEffect
    from PyQt5.QtGui import QColor as _QColor
    shadow = QGraphicsDropShadowEffect(widget)
    c = _QColor("#000000")
    c.setAlpha(alpha)
    shadow.setColor(c)
    shadow.setBlurRadius(blur)
    shadow.setOffset(0, offset_y)
    widget.setGraphicsEffect(shadow)
