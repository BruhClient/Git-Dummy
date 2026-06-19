from __future__ import annotations
from PyQt5.QtCore import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame,
    QGraphicsOpacityEffect, QPlainTextEdit,
)
from styles.theme import COLORS, scrollbar_style


def _numbered(lines: list, start: int = 1) -> str:
    """Format lines with actual file line numbers as a left-justified gutter."""
    if not lines:
        return "(no content)"
    end = start + len(lines) - 1
    w = len(str(end))
    return "\n".join(f"{str(start + i).rjust(w)}  {line}" for i, line in enumerate(lines))


# ── Conflict resolution dialog ────────────────────────────────────────────────

class _ConflictDialog(QWidget):
    _conflict_choice = pyqtSignal(str, str)   # choice, branch

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(0,0,0,160);")
        self.hide()
        self._branch = ""

        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        self._eff = QGraphicsOpacityEffect(self)
        self._eff.setOpacity(0.0)
        self.setGraphicsEffect(self._eff)
        self._fade_in_anim = QPropertyAnimation(self._eff, b"opacity")
        self._fade_in_anim.setDuration(200)
        self._fade_in_anim.setEasingCurve(QEasingCurve.OutCubic)

        # ── Flat card ─────────────────────────────────────────────────────────
        card = QWidget(self)
        card.setObjectName("conflictCard")
        card.setFixedWidth(440)
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setStyleSheet(f"""
            #conflictCard {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)
        self._card = card
        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 20, 24, 20)
        vl.setSpacing(0)

        # Type badge + branches on one row
        top_row = QHBoxLayout()
        top_row.setSpacing(12)
        top_row.setContentsMargins(0, 0, 0, 0)
        self._type_lbl = QLabel("PUSH CONFLICT")
        self._type_lbl.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 700; font-family: 'Tilt Warp';"
            f" color: {COLORS['warning']}; letter-spacing: 0.08em;"
        )
        top_row.addWidget(self._type_lbl)
        top_row.addStretch()
        vl.addLayout(top_row)
        vl.addSpacing(10)

        # Branches: "local/main  ↔  origin/main"
        self._branch_lbl = QLabel("")
        self._branch_lbl.setStyleSheet(
            f"background: transparent; font-size: 13px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_primary']}; font-family: monospace;"
        )
        vl.addWidget(self._branch_lbl)
        vl.addSpacing(4)

        # Conflicting files (small, muted)
        self._files_lbl = QLabel("")
        self._files_lbl.setWordWrap(True)
        self._files_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; color: {COLORS['text_muted']};"
        )
        vl.addWidget(self._files_lbl)

        # Divider
        def _divider():
            f = QFrame(); f.setFrameShape(QFrame.HLine)
            f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px; border: none;")
            return f

        # Code diff (hidden when no files) — side by side
        from PyQt5.QtWidgets import QPlainTextEdit
        self._code_area = QWidget()
        self._code_area.setStyleSheet("background: transparent;")
        code_vl = QVBoxLayout(self._code_area)
        code_vl.setContentsMargins(0, 0, 0, 0)
        code_vl.setSpacing(6)

        self._diff_file_lbl = QLabel("")
        self._diff_file_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_primary']}; font-family: monospace;"
        )
        code_vl.addWidget(self._diff_file_lbl)

        cols_lbl = QHBoxLayout()
        cols_lbl.setSpacing(8)
        cols_lbl.setContentsMargins(0, 0, 0, 0)
        self._orig_role_lbl = QLabel("")
        self._orig_role_lbl.setStyleSheet(
            f"background: transparent; font-size: 10px; color: {COLORS['text_muted']};"
        )
        self._inc_role_lbl = QLabel("")
        self._inc_role_lbl.setStyleSheet(
            f"background: transparent; font-size: 10px; color: {COLORS['warning']};"
        )
        cols_lbl.addWidget(self._orig_role_lbl, 1)
        cols_lbl.addWidget(self._inc_role_lbl, 1)
        code_vl.addLayout(cols_lbl)

        _te_style = f"""
            QPlainTextEdit {{
                background: {COLORS['bg_secondary']}; border: none;
                border-radius: 6px; color: {COLORS['text_secondary']};
                font-family: monospace; font-size: 11px; padding: 6px;
            }}
        """ + scrollbar_style()
        cols_code = QHBoxLayout()
        cols_code.setSpacing(8)
        cols_code.setContentsMargins(0, 0, 0, 0)
        self._orig_code_te = QPlainTextEdit()
        self._orig_code_te.setReadOnly(True)
        self._orig_code_te.setFixedHeight(110)
        self._orig_code_te.setStyleSheet(_te_style)
        self._inc_code_te = QPlainTextEdit()
        self._inc_code_te.setReadOnly(True)
        self._inc_code_te.setFixedHeight(110)
        self._inc_code_te.setStyleSheet(_te_style)
        cols_code.addWidget(self._orig_code_te, 1)
        cols_code.addWidget(self._inc_code_te, 1)
        code_vl.addLayout(cols_code)
        self._code_area.hide()

        vl.addSpacing(14)
        vl.addWidget(_divider())
        vl.addSpacing(14)
        vl.addWidget(self._code_area)

        vl.addSpacing(14)
        vl.addWidget(_divider())
        vl.addSpacing(16)

        # Buttons side-by-side
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.setContentsMargins(0, 0, 0, 0)

        def _abtn(color, slot):
            b = QPushButton("")
            b.setFixedHeight(38)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: 1px solid {color};
                    border-radius: 8px; color: {color};
                    font-size: 11px; font-weight: 600; font-family: 'Tilt Warp';
                }}
                QPushButton:hover {{ background: {color}; color: {COLORS['text_on_accent']}; }}
            """)
            b.clicked.connect(slot)
            return b

        self._discard_btn = _abtn(COLORS["text_secondary"], self._discard)
        self._keep_btn    = _abtn(COLORS["accent"],         self._keep)
        btn_row.addWidget(self._discard_btn, 1)
        btn_row.addWidget(self._keep_btn, 1)
        vl.addLayout(btn_row)
        vl.addSpacing(8)

        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(28)
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {COLORS['text_muted']}; font-size: 11px;
            }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; }}
        """)
        cancel.clicked.connect(self._cancel)
        vl.addWidget(cancel, 0, Qt.AlignCenter)

    def show_for_branch(self, branch: str, conflict_type: str = "PUSH CONFLICT",
                        conflicting_files: list = None, arrow: str = "→",
                        repo_path: str = "", prefetched_content: dict = None):
        self._branch = branch
        self._type_lbl.setText(conflict_type)
        incoming = f"origin/{branch}" if arrow == "→" else f"local/{branch}"
        original = f"local/{branch}"  if arrow == "→" else f"origin/{branch}"
        self._branch_lbl.setText(f"{original}  ↔  {incoming}")
        self._discard_btn.setText(f"Accept  {incoming}")
        self._keep_btn.setText(f"Accept  {original}")

        files = conflicting_files or []
        self._files_lbl.setText("  ·  ".join(files[:6]) + ("  …" if len(files) > 6 else "") if files else "")
        self._files_lbl.setVisible(bool(files))

        content = prefetched_content or {}
        if files and (content or repo_path):
            try:
                first = files[0]
                if first in content:
                    orig_lines, orig_start, inc_lines, inc_start = content[first]
                else:
                    from core.ops import get_conflict_content
                    orig_lines, orig_start, inc_lines, inc_start = get_conflict_content(repo_path, first)
                self._diff_file_lbl.setText(first)
                self._orig_role_lbl.setText("Original")
                self._inc_role_lbl.setText("Incoming")
                self._orig_code_te.setPlainText(_numbered(orig_lines, orig_start))
                self._inc_code_te.setPlainText(_numbered(inc_lines,  inc_start))
                self._code_area.show()
            except Exception:
                self._code_area.hide()
        else:
            self._code_area.hide()
        self._card.adjustSize()
        self.setGeometry(self.parent().rect())
        cx = (self.width()  - self._card.width())  // 2
        cy = (self.height() - self._card.height()) // 2
        self._card.move(cx, cy)
        self._eff.setOpacity(0.0)
        self.show()
        self.raise_()
        self._fade_in_anim.setStartValue(0.0)
        self._fade_in_anim.setEndValue(1.0)
        self._fade_in_anim.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible():
            cx = (self.width()  - self._card.width())  // 2
            cy = (self.height() - self._card.height()) // 2
            self._card.move(cx, cy)

    def mousePressEvent(self, event):
        if not self._card.geometry().contains(event.pos()):
            self._cancel()
        super().mousePressEvent(event)

    def _discard(self): self._choose("discard")
    def _keep(self):    self._choose("keep")
    def _cancel(self):  self._choose("cancel")

    def _choose(self, choice: str):
        self.hide()
        self._conflict_choice.emit(choice, self._branch)


# ── Pull dirty-state dialog ───────────────────────────────────────────────────

class _PullDirtyDialog(QWidget):
    _pull_dirty_choice = pyqtSignal(str, str)   # choice, branch

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(0,0,0,160);")
        self.hide()
        self._branch = ""

        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        self._eff = QGraphicsOpacityEffect(self)
        self._eff.setOpacity(0.0)
        self.setGraphicsEffect(self._eff)
        self._anim = QPropertyAnimation(self._eff, b"opacity")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        card = QWidget(self)
        card.setObjectName("pdCard")
        card.setFixedWidth(440)
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setStyleSheet(f"""
            #pdCard {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)
        self._card = card
        card_vl = QVBoxLayout(card)
        card_vl.setContentsMargins(0, 0, 0, 0)
        card_vl.setSpacing(0)

        hdr = QWidget()
        hdr.setObjectName("pdHdr")
        hdr.setAttribute(Qt.WA_StyledBackground, True)
        hdr.setStyleSheet(f"""
            #pdHdr {{
                background: {COLORS['bg_secondary']};
                border-bottom: 1px solid {COLORS['border']};
                border-radius: 12px 12px 0 0;
            }}
        """)
        hdr_vl = QVBoxLayout(hdr)
        hdr_vl.setContentsMargins(20, 14, 20, 14)
        hdr_vl.setSpacing(6)

        badge = QLabel("PULL WITH UNSAVED CHANGES")
        badge.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 700; font-family: 'Tilt Warp';"
            f" color: {COLORS['warning']}; letter-spacing: 0.1em;"
        )
        hdr_vl.addWidget(badge)

        self._flow_lbl = QLabel("")
        self._flow_lbl.setStyleSheet(
            f"background: transparent; font-size: 13px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_primary']}; font-family: monospace;"
        )
        hdr_vl.addWidget(self._flow_lbl)
        card_vl.addWidget(hdr)

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        body_vl = QVBoxLayout(body)
        body_vl.setContentsMargins(20, 18, 20, 20)
        body_vl.setSpacing(10)

        desc = QLabel("You have unsaved changes. Choose how to handle them before pulling:")
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_secondary']};"
        )
        body_vl.addWidget(desc)
        body_vl.addSpacing(4)

        def _btn(text, color, slot):
            b = QPushButton(text)
            b.setFixedHeight(40)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: 1px solid {color};
                    border-radius: 8px; color: {color};
                    font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';
                }}
                QPushButton:hover {{ background: {color}; color: {COLORS['text_on_accent']}; }}
            """)
            b.clicked.connect(slot)
            body_vl.addWidget(b)

        _btn("Hold my changes  →  Pull  →  Restore after", COLORS["accent"],       self._stash_pull)
        _btn("Commit my changes  →  Merge updates",       COLORS["text_secondary"], self._save_merge)
        _btn("Discard my changes  →  Pull",               COLORS["danger"],       self._discard_pull)
        _btn("Cancel",                                    COLORS["text_muted"],   self._cancel)
        card_vl.addWidget(body)

    def show_for_branch(self, branch: str):
        self._branch = branch
        self._flow_lbl.setText(f"origin/{branch}  →  local/{branch}")
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible():
            cx = (self.width()  - self._card.width())  // 2
            cy = (self.height() - self._card.height()) // 2
            self._card.move(cx, cy)

    def mousePressEvent(self, event):
        if not self._card.geometry().contains(event.pos()):
            self._cancel()
        super().mousePressEvent(event)

    def _stash_pull(self):  self._choose("stash_pull")
    def _save_merge(self):  self._choose("save_merge")
    def _discard_pull(self): self._choose("discard_pull")
    def _cancel(self):      self._choose("cancel")

    def _choose(self, choice: str):
        self.hide()
        self._pull_dirty_choice.emit(choice, self._branch)


# ── Navigate dirty dialog ─────────────────────────────────────────────────────

class _NavigateDirtyDialog(QWidget):
    """Prompt shown when the user tries to switch snapshots with unsaved changes."""
    _navigate_dirty_choice = pyqtSignal(str, str)   # choice, sha

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(0,0,0,160);")
        self.hide()
        self._sha = ""

        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        self._eff = QGraphicsOpacityEffect(self)
        self._eff.setOpacity(0.0)
        self.setGraphicsEffect(self._eff)
        self._anim = QPropertyAnimation(self._eff, b"opacity")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        card = QWidget(self)
        card.setObjectName("ndCard")
        card.setFixedWidth(420)
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setStyleSheet(f"""
            #ndCard {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)
        self._card = card
        card_vl = QVBoxLayout(card)
        card_vl.setContentsMargins(0, 0, 0, 0)
        card_vl.setSpacing(0)

        hdr = QWidget()
        hdr.setObjectName("ndHdr")
        hdr.setAttribute(Qt.WA_StyledBackground, True)
        hdr.setStyleSheet(f"""
            #ndHdr {{
                background: {COLORS['bg_secondary']};
                border-bottom: 1px solid {COLORS['border']};
                border-radius: 12px 12px 0 0;
            }}
        """)
        hdr_vl = QVBoxLayout(hdr)
        hdr_vl.setContentsMargins(20, 14, 20, 14)
        hdr_vl.setSpacing(4)

        badge = QLabel("NAVIGATE WITH UNSAVED CHANGES")
        badge.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 700; font-family: 'Tilt Warp';"
            f" color: {COLORS['warning']}; letter-spacing: 0.1em;"
        )
        hdr_vl.addWidget(badge)
        card_vl.addWidget(hdr)

        body = QWidget()
        body.setStyleSheet("background: transparent;")
        body_vl = QVBoxLayout(body)
        body_vl.setContentsMargins(20, 18, 20, 20)
        body_vl.setSpacing(10)

        desc = QLabel(
            "You have uncommitted changes. Choose what to do "
            "before switching to this snapshot:"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_secondary']};"
        )
        body_vl.addWidget(desc)
        body_vl.addSpacing(4)

        def _btn(text, color, slot):
            b = QPushButton(text)
            b.setFixedHeight(40)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: 1px solid {color};
                    border-radius: 8px; color: {color};
                    font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';
                }}
                QPushButton:hover {{ background: {color}; color: {COLORS['text_on_accent']}; }}
            """)
            b.clicked.connect(slot)
            body_vl.addWidget(b)

        _btn("Save & Navigate",    COLORS["accent"],        self._save)
        _btn("Discard & Navigate", COLORS["danger"],        self._discard)
        _btn("Cancel",             COLORS["text_muted"],    self._cancel)
        card_vl.addWidget(body)

    def show_for_sha(self, sha: str):
        self._sha = sha
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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible():
            cx = (self.width()  - self._card.width())  // 2
            cy = (self.height() - self._card.height()) // 2
            self._card.move(cx, cy)

    def mousePressEvent(self, event):
        if not self._card.geometry().contains(event.pos()):
            self._cancel()
        super().mousePressEvent(event)

    def _save(self):    self._choose("save")
    def _discard(self): self._choose("discard")
    def _cancel(self):  self._choose("cancel")

    def _choose(self, choice: str):
        self.hide()
        self._navigate_dirty_choice.emit(choice, self._sha)


# ── Merge conflict dialog ─────────────────────────────────────────────────────

class _MergeConflictDialog(QWidget):
    # choice: "decisions" (dict of per-file ours/theirs), source, target
    _merge_conflict_choice = pyqtSignal(object, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("background: rgba(0,0,0,160);")
        self.hide()
        self._source = ""
        self._target = ""
        self._files: list = []
        self._content: dict = {}
        self._decisions: dict = {}
        self._idx: int = 0

        from PyQt5.QtWidgets import QGraphicsOpacityEffect, QPlainTextEdit
        self._eff = QGraphicsOpacityEffect(self)
        self._eff.setOpacity(0.0)
        self.setGraphicsEffect(self._eff)
        self._anim = QPropertyAnimation(self._eff, b"opacity")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        card = QWidget(self)
        card.setObjectName("mcCard")
        card.setFixedWidth(500)
        card.setAttribute(Qt.WA_StyledBackground, True)
        card.setStyleSheet(f"""
            #mcCard {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)
        self._card = card
        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 20, 24, 20)
        vl.setSpacing(0)

        # ── Top row: badge + progress ─────────────────────────────────────────
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        badge = QLabel("MERGE CONFLICT")
        badge.setStyleSheet(
            f"background: transparent; font-size: 10px; font-weight: 700; font-family: 'Tilt Warp';"
            f" color: {COLORS['warning']}; letter-spacing: 0.08em;"
        )
        top.addWidget(badge)
        top.addStretch()
        self._progress_lbl = QLabel("")
        self._progress_lbl.setStyleSheet(
            f"background: transparent; font-size: 10px; color: {COLORS['text_muted']};"
        )
        top.addWidget(self._progress_lbl)
        vl.addLayout(top)
        vl.addSpacing(10)

        self._branch_lbl2 = QLabel("")
        self._branch_lbl2.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_primary']}; font-family: monospace;"
        )
        vl.addWidget(self._branch_lbl2)
        vl.addSpacing(12)

        def _div():
            f = QFrame(); f.setFrameShape(QFrame.HLine)
            f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px; border: none;")
            return f

        vl.addWidget(_div())
        vl.addSpacing(12)

        # ── File name ─────────────────────────────────────────────────────────
        self._file_lbl2 = QLabel("")
        self._file_lbl2.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 700; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_primary']}; font-family: monospace;"
        )
        vl.addWidget(self._file_lbl2)
        vl.addSpacing(6)

        # ── Code labels ───────────────────────────────────────────────────────
        lbl_row = QHBoxLayout()
        lbl_row.setSpacing(8); lbl_row.setContentsMargins(0, 0, 0, 0)
        self._orig_lbl2 = QLabel("")
        self._orig_lbl2.setStyleSheet(f"background: transparent; font-size: 10px; color: {COLORS['text_muted']};")
        self._inc_lbl2  = QLabel("")
        self._inc_lbl2.setStyleSheet(f"background: transparent; font-size: 10px; color: {COLORS['warning']};")
        lbl_row.addWidget(self._orig_lbl2, 1)
        lbl_row.addWidget(self._inc_lbl2, 1)
        vl.addLayout(lbl_row)
        vl.addSpacing(4)

        # ── Side-by-side code ─────────────────────────────────────────────────
        _te_style = f"""
            QPlainTextEdit {{
                background: {COLORS['bg_secondary']}; border: none;
                border-radius: 6px; color: {COLORS['text_secondary']};
                font-family: monospace; font-size: 11px; padding: 6px;
            }}
        """ + scrollbar_style()
        code_row = QHBoxLayout()
        code_row.setSpacing(8); code_row.setContentsMargins(0, 0, 0, 0)
        self._orig_te2 = QPlainTextEdit(); self._orig_te2.setReadOnly(True)
        self._orig_te2.setFixedHeight(120); self._orig_te2.setStyleSheet(_te_style)
        self._inc_te2  = QPlainTextEdit(); self._inc_te2.setReadOnly(True)
        self._inc_te2.setFixedHeight(120);  self._inc_te2.setStyleSheet(_te_style)
        code_row.addWidget(self._orig_te2, 1)
        code_row.addWidget(self._inc_te2, 1)
        vl.addLayout(code_row)
        vl.addSpacing(12)

        # ── Per-file Accept buttons ────────────────────────────────────────────
        acc_row = QHBoxLayout()
        acc_row.setSpacing(8); acc_row.setContentsMargins(0, 0, 0, 0)

        def _abtn(color, slot):
            b = QPushButton("")
            b.setFixedHeight(36)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: 1px solid {color};
                    border-radius: 8px; color: {color};
                    font-size: 11px; font-weight: 600; font-family: 'Tilt Warp';
                }}
                QPushButton:hover {{ background: {color}; color: {COLORS['text_on_accent']}; }}
                QPushButton:disabled {{ border-color: {COLORS['border']}; color: {COLORS['text_muted']}; }}
            """)
            b.clicked.connect(slot)
            return b

        def _nav_btn(text, slot):
            b = QPushButton(text)
            b.setFixedSize(36, 36)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; border: 1px solid {COLORS['border']};
                    border-radius: 8px; color: {COLORS['text_muted']};
                    font-size: 14px; font-weight: 600; font-family: 'Tilt Warp';
                }}
                QPushButton:hover {{ border-color: {COLORS['accent']}; color: {COLORS['accent']}; }}
                QPushButton:disabled {{ color: {COLORS['border']}; border-color: {COLORS['border']}; }}
            """)
            b.clicked.connect(slot)
            return b

        self._prev_btn = _nav_btn("←", self._go_prev)
        self._next_btn = _nav_btn("→", self._go_next)
        self._acc_orig_btn = _abtn(COLORS["text_secondary"], self._accept_original)
        self._acc_inc_btn  = _abtn(COLORS["accent"],         self._accept_incoming)
        acc_row.addWidget(self._prev_btn)
        acc_row.addWidget(self._acc_orig_btn, 1)
        acc_row.addWidget(self._acc_inc_btn, 1)
        acc_row.addWidget(self._next_btn)
        vl.addLayout(acc_row)
        vl.addSpacing(12)
        vl.addWidget(_div())
        vl.addSpacing(12)

        # ── Confirm + Cancel ──────────────────────────────────────────────────
        self._confirm_btn = QPushButton("Confirm Merge")
        self._confirm_btn.setFixedHeight(40)
        self._confirm_btn.setCursor(Qt.PointingHandCursor)
        self._confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none;
                border-radius: 8px; color: {COLORS['text_on_accent']};
                font-size: 12px; font-weight: 700; font-family: 'Tilt Warp';
            }}
            QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
            QPushButton:disabled {{ background: {COLORS['bg_secondary']}; color: {COLORS['text_muted']}; }}
        """)
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.clicked.connect(self._confirm)
        vl.addWidget(self._confirm_btn)
        vl.addSpacing(8)

        cancel = QPushButton("Cancel Merge")
        cancel.setFixedHeight(28); cancel.setCursor(Qt.PointingHandCursor)
        cancel.setStyleSheet(f"""
            QPushButton {{ background: transparent; border: none;
                color: {COLORS['text_muted']}; font-size: 11px; }}
            QPushButton:hover {{ color: {COLORS['text_primary']}; }}
        """)
        cancel.clicked.connect(self._cancel)
        vl.addWidget(cancel, 0, Qt.AlignCenter)

    # ── Public ────────────────────────────────────────────────────────────────

    def show_for_conflict(self, source: str, target: str, conflict_files: list = None,
                          repo_path: str = "", prefetched_content: dict = None):
        self._source  = source
        self._target  = target
        self._content = prefetched_content or {}
        self._decisions = {}
        self._idx = 0
        self._branch_lbl2.setText(f"{target}  ↔  {source}")
        self._acc_orig_btn.setText("Accept Original")
        self._acc_inc_btn.setText("Accept Incoming")
        self._confirm_btn.setEnabled(False)
        self._files = conflict_files or []
        self._show_file(0)
        self._card.adjustSize()
        self.setGeometry(self.parent().rect())
        self._centre()
        self._eff.setOpacity(0.0)
        self.show(); self.raise_()
        self._anim.setStartValue(0.0); self._anim.setEndValue(1.0); self._anim.start()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _show_file(self, idx: int):
        if not self._files:
            return
        self._idx = idx
        f = self._files[idx]
        n = len(self._files)
        resolved = len(self._decisions)
        self._progress_lbl.setText(f"{resolved} of {n} resolved")
        self._file_lbl2.setText(f)
        self._orig_lbl2.setText("Original")
        self._inc_lbl2.setText("Incoming")
        orig, orig_start, inc, inc_start = self._content.get(f, ([], 1, [], 1))
        self._orig_te2.setPlainText(_numbered(orig, orig_start))
        self._inc_te2.setPlainText(_numbered(inc,  inc_start))
        self._prev_btn.setEnabled(idx > 0)
        self._next_btn.setEnabled(idx < n - 1)
        self._update_acc_buttons()

    def _update_acc_buttons(self):
        f = self._files[self._idx] if self._files else ""
        decision = self._decisions.get(f)
        # Original button
        if decision == "ours":
            self._acc_orig_btn.setStyleSheet(f"""
                QPushButton {{ background: {COLORS['text_secondary']}; border: 1px solid {COLORS['text_secondary']};
                    border-radius: 8px; color: {COLORS['text_on_accent']}; font-size: 11px; font-weight: 600; font-family: 'Tilt Warp'; }}
                QPushButton:hover {{ background: {COLORS['text_primary']}; border-color: {COLORS['text_primary']}; }}
            """)
        else:
            self._acc_orig_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: 1px solid {COLORS['text_secondary']};
                    border-radius: 8px; color: {COLORS['text_secondary']}; font-size: 11px; font-weight: 600; font-family: 'Tilt Warp'; }}
                QPushButton:hover {{ background: {COLORS['text_secondary']}; color: {COLORS['text_on_accent']}; }}
            """)
        # Incoming button
        if decision == "theirs":
            self._acc_inc_btn.setStyleSheet(f"""
                QPushButton {{ background: {COLORS['accent']}; border: 1px solid {COLORS['accent']};
                    border-radius: 8px; color: {COLORS['text_on_accent']}; font-size: 11px; font-weight: 600; font-family: 'Tilt Warp'; }}
                QPushButton:hover {{ background: {COLORS['accent_hover']}; }}
            """)
        else:
            self._acc_inc_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; border: 1px solid {COLORS['accent']};
                    border-radius: 8px; color: {COLORS['accent']}; font-size: 11px; font-weight: 600; font-family: 'Tilt Warp'; }}
                QPushButton:hover {{ background: {COLORS['accent']}; color: {COLORS['text_on_accent']}; }}
            """)

    def _toggle(self, choice: str):
        f = self._files[self._idx]
        if self._decisions.get(f) == choice:
            del self._decisions[f]   # deselect
        else:
            self._decisions[f] = choice
        self._progress_lbl.setText(f"{len(self._decisions)} of {len(self._files)} resolved")
        self._confirm_btn.setEnabled(len(self._decisions) == len(self._files))
        self._update_acc_buttons()

    def _accept_original(self): self._toggle("ours")
    def _accept_incoming(self): self._toggle("theirs")
    def _go_prev(self): self._show_file(self._idx - 1)
    def _go_next(self): self._show_file(self._idx + 1)

    def _confirm(self):
        self.hide()
        self._merge_conflict_choice.emit(self._decisions, self._source, self._target)

    def _cancel(self):
        self.hide()
        self._merge_conflict_choice.emit(None, self._source, self._target)

    def _centre(self):
        if self.parent():
            cx = (self.width()  - self._card.width())  // 2
            cy = (self.height() - self._card.height()) // 2
            self._card.move(cx, cy)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isVisible():
            self._centre()

    def mousePressEvent(self, event):
        if not self._card.geometry().contains(event.pos()):
            self._cancel()
        super().mousePressEvent(event)


from core.ops import get_conflict_content  # used lazily inside _ConflictDialog
