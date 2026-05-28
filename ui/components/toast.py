"""Transient toast notification widget."""
from __future__ import annotations

from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QPoint
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel

from styles.theme import COLORS


class _Toast(QWidget):
    _STYLES = {
        "loading": (COLORS["warning"],   "⏳"),
        "success": (COLORS["accent"],    "✓"),
        "error":   (COLORS["danger"],    "✕"),
        "info":    (COLORS["text_muted"], "ℹ"),
    }
    _MARGIN = 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("toastWidget")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setMaximumWidth(340)
        self.hide()

        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        self._opacity = QGraphicsOpacityEffect(self)
        self._opacity.setOpacity(1.0)
        self.setGraphicsEffect(self._opacity)

        self._slide = QPropertyAnimation(self, b"pos")
        self._slide.setDuration(260)
        self._slide.setEasingCurve(QEasingCurve.OutCubic)

        self._fade = QPropertyAnimation(self._opacity, b"opacity")
        self._fade.setDuration(220)
        self._fade.setEasingCurve(QEasingCurve.InCubic)
        self._fade.finished.connect(self.hide)

        self._timer = QTimer()
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._dismiss)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(10)

        self._icon_lbl = QLabel("")
        self._icon_lbl.setStyleSheet("background: transparent; font-size: 14px;")
        layout.addWidget(self._icon_lbl)

        self._msg = QLabel("")
        self._msg.setWordWrap(True)
        self._msg.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_primary']};"
        )
        layout.addWidget(self._msg)

    def show_message(self, text: str, kind: str = "info", duration_ms: int = 4000):
        color, icon = self._STYLES.get(kind, self._STYLES["info"])
        self._icon_lbl.setText(icon)
        self._icon_lbl.setStyleSheet(f"background: transparent; font-size: 14px; color: {color};")
        self._msg.setText(text)
        self.setStyleSheet(f"""
            #toastWidget {{
                background: {COLORS['bg_card']};
                border: 1px solid {color}60;
                border-radius: 10px;
            }}
        """)
        self.adjustSize()
        self._position_target()
        self._opacity.setOpacity(1.0)
        self._fade.stop()
        self._slide.stop()

        if self.parent():
            p = self.parent()
            off_x = p.width()
            target = self._target_pos()
            self.move(off_x, target.y())
            self.raise_()
            self.show()
            self._slide.setStartValue(self.pos())
            self._slide.setEndValue(target)
            self._slide.start()

        self._timer.stop()
        if duration_ms > 0:
            self._timer.start(duration_ms)

    def _target_pos(self) -> QPoint:
        if not self.parent():
            return QPoint(0, 0)
        p = self.parent()
        return QPoint(p.width() - self.width() - self._MARGIN,
                      p.height() - self.height() - self._MARGIN)

    def _position_target(self):
        if self.isVisible():
            self.move(self._target_pos())

    def _dismiss(self):
        self._fade.setStartValue(1.0)
        self._fade.setEndValue(0.0)
        self._fade.start()

    def reposition(self):
        if self.isVisible():
            self.move(self._target_pos())
