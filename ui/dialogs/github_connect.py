"""Full-screen overlay dialog for connecting a local repo to GitHub."""
from __future__ import annotations

import os

import qtawesome as qta

from PyQt5.QtCore import Qt, QSize, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QGraphicsOpacityEffect,
)

from styles.theme import COLORS


class _GitHubConnectDialog(QWidget):
    """Full-screen overlay dialog for connecting a local repo to GitHub."""
    _connect_choice = pyqtSignal(str, bool)   # name, is_private

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(0,0,0,160);")
        self.hide()
        self._is_private = True

        self._eff = QGraphicsOpacityEffect(self)
        self._eff.setOpacity(0.0)
        self.setGraphicsEffect(self._eff)
        self._anim = QPropertyAnimation(self._eff, b"opacity")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        card = QWidget(self)
        card.setObjectName("ghCard")
        card.setFixedWidth(420)
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setStyleSheet(f"""
            #ghCard {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)
        self._card = card
        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 20, 24, 20)
        vl.setSpacing(14)

        title = QLabel("Connect to GitHub")
        title.setStyleSheet(
            f"background: transparent; font-size: 15px; font-weight: 700; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_primary']};"
        )
        vl.addWidget(title)

        sub = QLabel("Create a GitHub repository and upload this project.")
        sub.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};"
        )
        vl.addWidget(sub)

        self._name_input = QLineEdit()
        self._name_input.setFixedHeight(38)
        self._name_input.setPlaceholderText("Repository name")
        self._name_input.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['bg_primary']}; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_primary']};
                font-size: 13px; padding: 0 12px;
            }}
            QLineEdit:focus {{ border-color: {COLORS['accent']}; }}
        """)
        self._name_input.returnPressed.connect(self._submit)
        vl.addWidget(self._name_input)

        _ON  = (f"QPushButton {{ background: {COLORS['accent']}; border: 1px solid {COLORS['accent']};"
                f" border-radius: 6px; color: white; font-size: 12px;"
                f" font-weight: 600; font-family: 'Tilt Warp'; padding: 4px 16px; }}")
        _OFF = (f"QPushButton {{ background: transparent; border: 1px solid {COLORS['border']};"
                f" border-radius: 6px; color: {COLORS['text_muted']}; font-size: 12px;"
                f" padding: 4px 16px; }}"
                f"QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['accent']}; }}")
        self._priv_btn = QPushButton("Private")
        self._pub_btn  = QPushButton("Public")
        for btn in (self._priv_btn, self._pub_btn):
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedHeight(32)
        self._priv_btn.setStyleSheet(_ON)
        self._pub_btn.setStyleSheet(_OFF)
        self._priv_btn.clicked.connect(lambda: self._set_private(True))
        self._pub_btn.clicked.connect(lambda: self._set_private(False))
        self._on_style  = _ON
        self._off_style = _OFF
        vis_row = QHBoxLayout()
        vis_row.setSpacing(8)
        vis_row.setContentsMargins(0, 0, 0, 0)
        vis_row.addWidget(self._priv_btn)
        vis_row.addWidget(self._pub_btn)
        vis_row.addStretch()
        vl.addLayout(vis_row)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(40)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 8px; color: {COLORS['text_secondary']};
                font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';
            }}
            QPushButton:hover {{ border-color: {COLORS['text_secondary']}; }}
        """)
        cancel_btn.clicked.connect(self.hide)

        upload_btn = QPushButton("Upload to GitHub")
        upload_btn.setIcon(qta.icon("fa5s.cloud-upload-alt", color="#ffffff"))
        upload_btn.setIconSize(QSize(14, 14))
        upload_btn.setFixedHeight(40)
        upload_btn.setCursor(Qt.PointingHandCursor)
        upload_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none;
                border-radius: 8px; color: white;
                font-size: 12px; font-weight: 700; font-family: 'Tilt Warp';
            }}
            QPushButton:hover {{ background: {COLORS.get('accent_hover', COLORS['accent'])}; }}
        """)
        upload_btn.clicked.connect(self._submit)

        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(upload_btn)
        vl.addLayout(btn_row)

    def _set_private(self, priv: bool):
        self._is_private = priv
        self._priv_btn.setStyleSheet(self._on_style  if priv else self._off_style)
        self._pub_btn.setStyleSheet (self._off_style if priv else self._on_style)

    def show_near(self, repo_path: str):
        """Show the dialog centred over the parent."""
        self._name_input.setText(os.path.basename(repo_path))
        self._set_private(True)
        self._card.adjustSize()
        self.setGeometry(self.parent().rect())
        cx = (self.width()  - self._card.width())  // 2
        cy = (self.height() - self._card.height()) // 2
        self._card.move(cx, cy)
        self._eff.setOpacity(0.0)
        self.show()
        self.raise_()
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._name_input.selectAll()
        self._name_input.setFocus()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible():
            cx = (self.width()  - self._card.width())  // 2
            cy = (self.height() - self._card.height()) // 2
            self._card.move(cx, cy)

    def mousePressEvent(self, event):
        if not self._card.geometry().contains(event.pos()):
            self.hide()
        super().mousePressEvent(event)

    def _submit(self):
        name = self._name_input.text().strip()
        if name:
            self.hide()
            self._connect_choice.emit(name, self._is_private)
