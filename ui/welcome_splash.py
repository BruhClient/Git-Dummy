"""Branded welcome splash — plays once on app launch, then hands off to AuthPage."""
from __future__ import annotations

import os

from PyQt5.QtCore import Qt, QEasingCurve, pyqtSignal, pyqtProperty
from PyQt5.QtCore import QPropertyAnimation, QParallelAnimationGroup, QSequentialAnimationGroup, QPauseAnimation
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPainterPath
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QGraphicsOpacityEffect, QSizePolicy

from styles.theme import COLORS, LOGO_FONT


def _tinted_logo_pixmap(size: int) -> QPixmap:
    from utils import resource_path
    logo_path = resource_path(os.path.join("logo", "logo.png"))
    src = QPixmap(logo_path).scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    tinted = QPixmap(src.size())
    tinted.fill(Qt.transparent)
    tp = QPainter(tinted)
    tp.drawPixmap(0, 0, src)
    tp.setCompositionMode(QPainter.CompositionMode_SourceIn)
    tp.fillRect(tinted.rect(), QColor(COLORS["accent"]))
    tp.end()

    radius = max(8, size // 5)
    rounded = QPixmap(size, size)
    rounded.fill(Qt.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addRoundedRect(0, 0, size, size, radius, radius)
    painter.setClipPath(clip)
    painter.drawPixmap(0, 0, tinted)
    painter.end()
    return rounded


class _AnimatedLogo(QWidget):
    """Draws the logo pixmap itself with its own opacity/scale, entirely via
    paintEvent — no QGraphicsEffect and no layout-managed geometry animation,
    since combining those two on the same widget is what caused Qt's
    "paint device can only be painted by one painter at a time" errors."""

    def __init__(self, pixmap: QPixmap, size: int, parent=None):
        super().__init__(parent)
        self._pixmap = pixmap
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self._opacity = 0.0
        self._scale = 0.7

    def _get_opacity(self) -> float:
        return self._opacity

    def _set_opacity(self, value: float):
        self._opacity = value
        self.update()

    opacity = pyqtProperty(float, _get_opacity, _set_opacity)

    def _get_scale(self) -> float:
        return self._scale

    def _set_scale(self, value: float):
        self._scale = value
        self.update()

    scale = pyqtProperty(float, _get_scale, _set_scale)

    def paintEvent(self, event):
        if self._opacity <= 0.0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setOpacity(self._opacity)
        center = self.rect().center()
        painter.translate(center)
        painter.scale(self._scale, self._scale)
        painter.translate(-center)
        painter.drawPixmap(0, 0, self._pixmap)
        painter.end()


class WelcomeSplash(QWidget):
    """Full-page branded intro animation shown once at startup, inside the
    app's QStackedWidget. Click or any keypress skips straight to the end."""

    finished = pyqtSignal()

    _LOGO_SIZE = 96

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background-color: {COLORS['bg_primary']};")
        self.setFocusPolicy(Qt.StrongFocus)
        self._already_finished = False

        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignCenter)
        root.setSpacing(0)

        self._logo = _AnimatedLogo(_tinted_logo_pixmap(self._LOGO_SIZE), self._LOGO_SIZE)
        root.addWidget(self._logo, alignment=Qt.AlignCenter)

        root.addSpacing(20)

        text_wrap = QWidget()
        text_wrap.setStyleSheet("background: transparent;")
        text_wrap.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        text_layout = QVBoxLayout(text_wrap)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(8)
        text_layout.setAlignment(Qt.AlignCenter)

        wordmark = QLabel("Git Dummy")
        wordmark.setAlignment(Qt.AlignCenter)
        wordmark.setStyleSheet(
            f"background: transparent; font-size: 32px; font-weight: 700; "
            f"font-family: {LOGO_FONT}; color: {COLORS['text_primary']};"
        )
        text_layout.addWidget(wordmark)

        tagline = QLabel("Every change you've made, beautifully visualised.")
        tagline.setAlignment(Qt.AlignCenter)
        tagline.setStyleSheet(
            f"background: transparent; font-size: 13px; color: {COLORS['text_secondary']};"
        )
        text_layout.addWidget(tagline)

        root.addWidget(text_wrap, alignment=Qt.AlignCenter)

        self._text_wrap = text_wrap

        # Single, non-nested QGraphicsOpacityEffect — safe because nothing
        # above or below it in the widget tree also carries an effect.
        self._text_opacity = QGraphicsOpacityEffect(text_wrap)
        self._text_opacity.setOpacity(0.0)
        text_wrap.setGraphicsEffect(self._text_opacity)

        self._sequence = self._build_sequence()
        self._sequence.finished.connect(self._on_sequence_finished)

    def _build_sequence(self) -> QSequentialAnimationGroup:
        seq = QSequentialAnimationGroup(self)

        logo_fade_in = QPropertyAnimation(self._logo, b"opacity", self)
        logo_fade_in.setDuration(480)
        logo_fade_in.setStartValue(0.0)
        logo_fade_in.setEndValue(1.0)
        logo_fade_in.setEasingCurve(QEasingCurve.OutCubic)

        logo_grow = QPropertyAnimation(self._logo, b"scale", self)
        logo_grow.setDuration(520)
        logo_grow.setStartValue(0.7)
        logo_grow.setEndValue(1.0)
        logo_grow.setEasingCurve(QEasingCurve.OutCubic)

        logo_group = QParallelAnimationGroup(self)
        logo_group.addAnimation(logo_fade_in)
        logo_group.addAnimation(logo_grow)
        seq.addAnimation(logo_group)

        seq.addAnimation(QPauseAnimation(160, self))

        text_fade_in = QPropertyAnimation(self._text_opacity, b"opacity", self)
        text_fade_in.setDuration(440)
        text_fade_in.setStartValue(0.0)
        text_fade_in.setEndValue(1.0)
        text_fade_in.setEasingCurve(QEasingCurve.OutCubic)
        seq.addAnimation(text_fade_in)

        seq.addAnimation(QPauseAnimation(900, self))

        logo_fade_out = QPropertyAnimation(self._logo, b"opacity", self)
        logo_fade_out.setDuration(440)
        logo_fade_out.setStartValue(1.0)
        logo_fade_out.setEndValue(0.0)
        logo_fade_out.setEasingCurve(QEasingCurve.InCubic)

        text_fade_out = QPropertyAnimation(self._text_opacity, b"opacity", self)
        text_fade_out.setDuration(440)
        text_fade_out.setStartValue(1.0)
        text_fade_out.setEndValue(0.0)
        text_fade_out.setEasingCurve(QEasingCurve.InCubic)

        fade_out_group = QParallelAnimationGroup(self)
        fade_out_group.addAnimation(logo_fade_out)
        fade_out_group.addAnimation(text_fade_out)
        seq.addAnimation(fade_out_group)

        return seq

    def play(self):
        self.setFocus()
        self._sequence.start()

    def skip(self):
        if self._already_finished:
            return
        self._sequence.stop()
        self._logo.opacity = 0.0
        self._text_opacity.setOpacity(0.0)
        self._on_sequence_finished()

    def _on_sequence_finished(self):
        if self._already_finished:
            return
        self._already_finished = True
        self.finished.emit()

    def mousePressEvent(self, event):
        self.skip()
        event.accept()

    def keyPressEvent(self, event):
        self.skip()
        event.accept()
