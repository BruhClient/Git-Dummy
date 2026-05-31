FONT_FAMILY = "Inter, Segoe UI, system-ui, sans-serif"

COLORS: dict[str, str] = {
    "bg_primary":    "#0f0f0f",
    "bg_secondary":  "#1a1a1a",
    "bg_card":       "#1c1c1c",
    "bg_hover":      "#2a2a2a",
    "bg_sidebar":    "#111111",
    "border":        "#2e2e2e",
    "text_primary":  "#ededed",
    "text_secondary":"#a1a1a1",
    "text_muted":    "#666666",
    "text_on_accent":"#ffffff",
    "danger":        "#e53e3e",
    "warning":       "#d69e2e",
    "info":          "#3182ce",
    "commit_line":   "#2e2e2e",
    "border_focus":  "#e05535",
    "accent":        "#e05535",
    "accent_hover":  "#c44828",
    "accent_dim":    "#3d1a0e",
    "commit_node":   "#e05535",
    "tag_bg":        "#3d1a0e",
    "tag_text":      "#e05535",
}


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
    background: {COLORS['bg_secondary']};
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {COLORS['border']};
    border-radius: 4px;
    min-height: 30px;
}}

QScrollBar::handle:vertical:hover {{
    background: {COLORS['text_muted']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: {COLORS['bg_secondary']};
    height: 8px;
    border-radius: 4px;
}}

QScrollBar::handle:horizontal {{
    background: {COLORS['border']};
    border-radius: 4px;
    min-width: 30px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {COLORS['text_muted']};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QToolTip {{
    background-color: {COLORS['bg_card']};
    color: {COLORS['text_primary']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
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
    border-radius: 6px;
    padding: 10px 20px;
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
    border-radius: 6px;
    padding: 10px 20px;
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
    border-radius: 6px;
    padding: 10px 14px;
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
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
QHeaderView::section:first {{
    border-top-left-radius: 8px;
}}
QHeaderView::section:last {{
    border-top-right-radius: 8px;
}}
"""
