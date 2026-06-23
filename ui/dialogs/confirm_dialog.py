"""Styled confirmation and alert dialogs, plus convenience helpers."""
from __future__ import annotations

from PyQt5.QtCore import Qt, QRect, QSize, QPoint
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
    QLayout, QLayoutItem, QSizePolicy, QScrollArea,
)
from styles.theme import COLORS, card_shadow, scrollbar_style


class _FlowLayout(QLayout):
    """Layout that wraps items to the next row when the width is exceeded."""

    def __init__(self, parent=None, h_spacing=8, v_spacing=8):
        super().__init__(parent)
        self._h = h_spacing
        self._v = v_spacing
        self._items: list[QLayoutItem] = []

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        s = QSize()
        for item in self._items:
            s = s.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return QSize(s.width() + m.left() + m.right(),
                     s.height() + m.top() + m.bottom())

    def _do_layout(self, rect, test_only=False):
        m = self.contentsMargins()
        effective = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y = effective.x(), effective.y()
        row_h = 0
        for item in self._items:
            sz = item.sizeHint()
            if x + sz.width() > effective.right() + 1 and row_h > 0:
                x = effective.x()
                y += row_h + self._v
                row_h = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), sz))
            x += sz.width() + self._h
            row_h = max(row_h, sz.height())
        return y + row_h - rect.y() + m.bottom()


class ConfirmDialog(QDialog):
    """Styled confirmation dialog — title, body text, Cancel + confirm button."""

    def __init__(self, parent=None, title: str = "", body: str = "",
                 confirm_text: str = "Yes", danger: bool = True):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(380)
        self._setup_ui(title, body, confirm_text, danger)

    def _setup_ui(self, title: str, body: str, confirm_text: str, danger: bool):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setStyleSheet(f"background: {COLORS['bg_card']}; border-radius: 12px;")
        card_shadow(card)
        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 24, 24, 24)
        vl.setSpacing(14)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {COLORS['text_primary']};"
            f" background: transparent;"
        )
        vl.addWidget(title_lbl)

        body_lbl = QLabel(body)
        body_lbl.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_muted']}; background: transparent;"
        )
        body_lbl.setWordWrap(True)
        vl.addWidget(body_lbl)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(38)
        cancel_btn.setMinimumWidth(80)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 13px; font-weight: 600; padding: 0 16px;
            }}
            QPushButton:hover {{ border-color: {COLORS['text_secondary']}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        confirm_bg = COLORS['danger'] if danger else COLORS['accent']
        confirm_hover = "#c53030" if danger else COLORS.get('accent_hover', COLORS['accent'])
        confirm_btn = QPushButton(confirm_text)
        confirm_btn.setFixedHeight(38)
        confirm_btn.setMinimumWidth(80)
        confirm_btn.setCursor(Qt.PointingHandCursor)
        confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background: {confirm_bg}; border: none;
                border-radius: 8px; color: {COLORS['text_on_accent']};
                font-size: 13px; font-weight: 700; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {confirm_hover}; }}
        """)
        confirm_btn.clicked.connect(self.accept)
        btn_row.addWidget(confirm_btn)

        vl.addLayout(btn_row)
        root.addWidget(card)


class AlertDialog(QDialog):
    """Styled alert dialog — title, body text, single OK button."""

    def __init__(self, parent=None, title: str = "", body: str = ""):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(380)
        self._setup_ui(title, body)

    def _setup_ui(self, title: str, body: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setStyleSheet(f"background: {COLORS['bg_card']}; border-radius: 12px;")
        card_shadow(card)
        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 24, 24, 24)
        vl.setSpacing(14)

        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {COLORS['text_primary']};"
            f" background: transparent;"
        )
        vl.addWidget(title_lbl)

        body_lbl = QLabel(body)
        body_lbl.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_muted']}; background: transparent;"
        )
        body_lbl.setWordWrap(True)
        vl.addWidget(body_lbl)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        ok_btn = QPushButton("OK")
        ok_btn.setFixedHeight(38)
        ok_btn.setMinimumWidth(80)
        ok_btn.setCursor(Qt.PointingHandCursor)
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 13px; font-weight: 600; padding: 0 16px;
            }}
            QPushButton:hover {{ border-color: {COLORS['text_secondary']}; }}
        """)
        ok_btn.clicked.connect(self.accept)
        btn_row.addWidget(ok_btn)

        vl.addLayout(btn_row)
        root.addWidget(card)


class MergeDialog(QDialog):
    """Styled merge dialog — source branch, target selector, Merge/Cancel."""

    def __init__(self, parent=None, source_branch: str = "",
                 branches: list = None, default_branch: str = "main",
                 branch_colors: dict = None):
        super().__init__(parent)
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedWidth(380)
        self._target = ""
        self._branch_colors = branch_colors or {}
        self._setup_ui(source_branch, branches or [], default_branch)

    def _setup_ui(self, source: str, branches: list, default_branch: str):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = QWidget()
        card.setStyleSheet(f"background: {COLORS['bg_card']}; border-radius: 12px;")
        card_shadow(card)
        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 24, 24, 24)
        vl.setSpacing(14)

        title_lbl = QLabel("Merge Branch")
        title_lbl.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {COLORS['text_primary']};"
            f" background: transparent;"
        )
        vl.addWidget(title_lbl)

        body_lbl = QLabel(f"Merge <b>{source}</b> into:")
        body_lbl.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_muted']}; background: transparent;"
        )
        vl.addWidget(body_lbl)

        from PyQt5.QtWidgets import QButtonGroup
        self._branch_btns: list[QPushButton] = []
        self._btn_styles: dict[str, tuple[str, str]] = {}
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)

        flow_widget = QWidget()
        flow_widget.setStyleSheet("background: transparent;")
        flow = _FlowLayout(flow_widget, h_spacing=8, v_spacing=8)

        for b in branches:
            color = self._branch_colors.get(b, COLORS['accent'])
            unsel = (
                f"QPushButton {{ background: transparent; border: 1px solid {color};"
                f" border-radius: 8px; color: {color};"
                f" font-size: 13px; font-weight: 600; font-family: monospace; padding: 8px 16px; }}"
                f"QPushButton:hover {{ background: {color}; color: {COLORS['text_on_accent']}; }}"
            )
            sel = (
                f"QPushButton {{ background: {color}; border: none;"
                f" border-radius: 8px; color: {COLORS['text_on_accent']};"
                f" font-size: 13px; font-weight: 700; font-family: monospace; padding: 8px 16px; }}"
            )
            self._btn_styles[b] = (unsel, sel)
            btn = QPushButton(b)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setCheckable(True)
            btn.setStyleSheet(unsel)
            btn.toggled.connect(self._on_toggle)
            self._btn_group.addButton(btn)
            self._branch_btns.append(btn)
            flow.addWidget(btn)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet(f"QScrollArea {{ background: transparent; border: none; }} {scrollbar_style()}")
        scroll.setMaximumHeight(160)
        scroll.setWidget(flow_widget)
        vl.addWidget(scroll)

        default_btn = next((b for b in self._branch_btns if b.text() == default_branch), None)
        if default_btn:
            default_btn.setChecked(True)
        elif self._branch_btns:
            self._branch_btns[0].setChecked(True)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(38)
        cancel_btn.setMinimumWidth(80)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 13px; font-weight: 600; padding: 0 16px;
            }}
            QPushButton:hover {{ border-color: {COLORS['text_secondary']}; }}
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        merge_btn = QPushButton("Merge")
        merge_btn.setFixedHeight(38)
        merge_btn.setMinimumWidth(80)
        merge_btn.setCursor(Qt.PointingHandCursor)
        merge_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none;
                border-radius: 8px; color: {COLORS['text_on_accent']};
                font-size: 13px; font-weight: 700; padding: 0 16px;
            }}
            QPushButton:hover {{ background: {COLORS.get('accent_hover', COLORS['accent'])}; }}
        """)
        merge_btn.clicked.connect(self._on_merge)
        btn_row.addWidget(merge_btn)

        vl.addLayout(btn_row)
        root.addWidget(card)

    def _on_toggle(self, checked: bool):
        for btn in self._branch_btns:
            unsel, sel = self._btn_styles.get(btn.text(), ("", ""))
            btn.setStyleSheet(sel if btn.isChecked() else unsel)

    def _on_merge(self):
        checked = self._btn_group.checkedButton()
        self._target = checked.text() if checked else ""
        self.accept()

    def get_target(self) -> str:
        return self._target


# ── Convenience functions ──────────────────────────────────────────────────────

def confirm(parent, title: str, body: str,
            confirm_text: str = "Yes", danger: bool = True) -> bool:
    """Show a styled confirmation dialog. Returns True if the user confirmed."""
    dlg = ConfirmDialog(parent, title, body, confirm_text, danger)
    return dlg.exec_() == QDialog.Accepted


def alert(parent, title: str, body: str) -> None:
    """Show a styled alert dialog with a single OK button."""
    AlertDialog(parent, title, body).exec_()
