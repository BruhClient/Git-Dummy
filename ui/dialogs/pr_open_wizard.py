"""PR Open Wizard — 2-step modal overlay: Push → Open PR."""
from __future__ import annotations

import re

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QLineEdit, QFrame,
)
from styles.theme import COLORS


def _branch_to_title(branch: str) -> str:
    """Convert 'feature/add-login' → 'Add login'."""
    name = branch.split("/")[-1]
    name = re.sub(r"[-_]", " ", name)
    return name.capitalize()


def _btn(text: str, accent: bool = True) -> QPushButton:
    b = QPushButton(text)
    b.setFixedHeight(36)
    b.setCursor(Qt.PointingHandCursor)
    if accent:
        b.setStyleSheet(f"""
            QPushButton {{
                background: {COLORS['accent']}; border: none;
                border-radius: 8px; font-size: 13px; font-weight: 600; font-family: 'Tilt Warp';
                color: {COLORS['text_on_accent']}; padding: 0 20px;
            }}
            QPushButton:hover {{ background: {COLORS['accent_hover'] if 'accent_hover' in COLORS else COLORS['accent']}; }}
            QPushButton:disabled {{ background: {COLORS['bg_hover']}; color: {COLORS['text_muted']}; }}
        """)
    else:
        b.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {COLORS['border']};
                border-radius: 8px; font-size: 13px; font-weight: 500;
                color: {COLORS['text_muted']}; padding: 0 20px;
            }}
            QPushButton:hover {{ border-color: {COLORS['text_secondary']}; color: {COLORS['text_primary']}; }}
        """)
    return b


def _divider() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.HLine)
    f.setStyleSheet(f"background: {COLORS['border']}; max-height: 1px; border: none;")
    return f


# ── Wizard ────────────────────────────────────────────────────────────────────

class PROpenWizard(QWidget):
    """
    Full-screen modal overlay guiding the user through:
      Step 1 — Push branch to remote
      Step 2 — Fill in PR title/description and submit

    Signals emitted to commit_view:
      push_requested(branch)             — wizard needs the branch pushed
      pr_submitted(branch, title, body, base_branch) — ready to call GitHub API
      cancelled()                        — user cancelled at any step
    """

    push_requested = pyqtSignal(str)               # branch
    pr_submitted   = pyqtSignal(str, str, str, str)  # branch, title, body, base
    cancelled      = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(f"background: rgba(0,0,0,0.55);")
        self.hide()

        self._branch      = ""
        self._base_branch = "main"
        self._step        = 1

        # ── Card ──────────────────────────────────────────────────────────────
        self._card = QWidget(self)
        self._card.setObjectName("wizCard")
        self._card.setAttribute(Qt.WA_StyledBackground, True)
        self._card.setStyleSheet(f"""
            #wizCard {{
                background: {COLORS['bg_card']};
                border: 1px solid {COLORS['border']};
                border-radius: 12px;
            }}
        """)
        self._card.setFixedWidth(480)

        card_vl = QVBoxLayout(self._card)
        card_vl.setContentsMargins(28, 24, 28, 24)
        card_vl.setSpacing(16)

        # Step indicator
        self._step_lbl = QLabel("")
        self._step_lbl.setStyleSheet(
            f"background: transparent; font-size: 11px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_muted']}; letter-spacing: 0.06em;"
        )
        card_vl.addWidget(self._step_lbl)

        # Step title
        self._title_lbl = QLabel("")
        self._title_lbl.setStyleSheet(
            f"background: transparent; font-size: 18px; font-weight: 700; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_primary']};"
        )
        card_vl.addWidget(self._title_lbl)

        card_vl.addWidget(_divider())

        # ── Step 1 body: Push ─────────────────────────────────────────────────
        self._step1_body = QWidget()
        self._step1_body.setStyleSheet("background: transparent;")
        s1 = QVBoxLayout(self._step1_body)
        s1.setContentsMargins(0, 0, 0, 0)
        s1.setSpacing(12)

        self._push_desc = QLabel("")
        self._push_desc.setStyleSheet(
            f"background: transparent; font-size: 13px; color: {COLORS['text_secondary']};"
        )
        s1.addWidget(self._push_desc)

        self._push_status = QLabel("Uploading…")
        self._push_status.setAlignment(Qt.AlignCenter)
        self._push_status.setStyleSheet(
            f"background: transparent; font-size: 13px; color: {COLORS['text_muted']};"
        )
        s1.addWidget(self._push_status)

        btns1 = QHBoxLayout()
        self._cancel_s1 = _btn("Cancel", accent=False)
        self._cancel_s1.clicked.connect(self._cancel)
        btns1.addStretch()
        btns1.addWidget(self._cancel_s1)
        s1.addLayout(btns1)
        card_vl.addWidget(self._step1_body)

        # ── Step 2 body: PR form ──────────────────────────────────────────────
        self._step2_body = QWidget()
        self._step2_body.setStyleSheet("background: transparent;")
        s2 = QVBoxLayout(self._step2_body)
        s2.setContentsMargins(0, 0, 0, 0)
        s2.setSpacing(12)

        title_label = QLabel("Title")
        title_label.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_secondary']};"
        )
        s2.addWidget(title_label)

        self._pr_title = QLineEdit()
        self._pr_title.setFixedHeight(36)
        self._pr_title.setStyleSheet(f"""
            QLineEdit {{
                background: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']};
                border-radius: 6px; font-size: 13px; color: {COLORS['text_primary']};
                padding: 0 10px;
            }}
            QLineEdit:focus {{ border-color: {COLORS['accent']}; }}
        """)
        s2.addWidget(self._pr_title)

        desc_label = QLabel("Description  (optional)")
        desc_label.setStyleSheet(
            f"background: transparent; font-size: 12px; font-weight: 600; font-family: 'Tilt Warp';"
            f" color: {COLORS['text_secondary']};"
        )
        s2.addWidget(desc_label)

        self._pr_body = QTextEdit()
        self._pr_body.setFixedHeight(100)
        self._pr_body.setPlaceholderText("What does this PR do?")
        self._pr_body.setStyleSheet(f"""
            QTextEdit {{
                background: {COLORS['bg_secondary']}; border: 1px solid {COLORS['border']};
                border-radius: 6px; font-size: 13px; color: {COLORS['text_primary']};
                padding: 8px 10px;
            }}
            QTextEdit:focus {{ border-color: {COLORS['accent']}; }}
        """)
        s2.addWidget(self._pr_body)

        self._flow_lbl = QLabel("")
        self._flow_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};"
            f" font-family: monospace;"
        )
        s2.addWidget(self._flow_lbl)

        self._submit_status = QLabel("")
        self._submit_status.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {COLORS['text_muted']};"
        )
        self._submit_status.hide()
        s2.addWidget(self._submit_status)

        btns2 = QHBoxLayout()
        btns2.setSpacing(8)
        self._open_pr_btn = _btn("Open Pull Request", accent=True)
        self._cancel_s2   = _btn("Cancel", accent=False)
        self._open_pr_btn.clicked.connect(self._on_submit)
        self._cancel_s2.clicked.connect(self._cancel)
        btns2.addStretch()
        btns2.addWidget(self._cancel_s2)
        btns2.addWidget(self._open_pr_btn)
        s2.addLayout(btns2)
        card_vl.addWidget(self._step2_body)

    # ── Public ────────────────────────────────────────────────────────────────

    def start(self, branch: str, base_branch: str, already_pushed: bool = False):
        """
        Launch the wizard.
        - branch: the feature branch being PR'd
        - base_branch: the target (usually 'main')
        - already_pushed: True if branch is already up to date on remote
        """
        self._branch      = branch
        self._base_branch = base_branch

        self._go_to_step(2 if already_pushed else 1)

        self.show()
        self.raise_()
        self._centre()

    def notify_push_done(self, ok: bool, err: str = ""):
        """Call from commit_view after push completes."""
        if ok:
            self._go_to_step(2)
        else:
            self._push_status.setText("Push failed — check your connection and try again.")

    def notify_pr_created(self, ok: bool, err: str = ""):
        """Call from commit_view after GitHub API PR creation."""
        if ok:
            self._submit_status.setText("Pull request opened!")
            self._submit_status.show()
            self._open_pr_btn.setEnabled(False)
            QTimer.singleShot(1200, self._finish)
        else:
            self._submit_status.setText("Couldn't open the pull request — try again.")
            self._submit_status.show()
            self._open_pr_btn.setEnabled(True)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _go_to_step(self, step: int):
        self._step = step
        self._step_lbl.setText(f"STEP {step} OF 2")

        self._step1_body.setVisible(step == 1)
        self._step2_body.setVisible(step == 2)

        if step == 1:
            self._title_lbl.setText("Push Branch")
            self._push_desc.setText(f"Uploading  '{self._branch}'  to GitHub…")
            self._push_status.setText("Uploading…")
            QTimer.singleShot(0, lambda: self.push_requested.emit(self._branch))

        elif step == 2:
            self._title_lbl.setText("Open Pull Request")
            self._pr_title.setText(_branch_to_title(self._branch))
            self._pr_body.clear()
            self._flow_lbl.setText(f"{self._branch}  →  {self._base_branch}")
            self._submit_status.hide()
            self._open_pr_btn.setEnabled(True)
            self._pr_title.setFocus()

        self._card.adjustSize()
        self._centre()

    def _on_submit(self):
        title = self._pr_title.text().strip()
        if not title:
            self._pr_title.setFocus()
            return
        body = self._pr_body.toPlainText().strip()
        self._open_pr_btn.setEnabled(False)
        self._submit_status.setText("Opening pull request…")
        self._submit_status.show()
        self.pr_submitted.emit(self._branch, title, body, self._base_branch)

    def _cancel(self):
        self.hide()
        self.cancelled.emit()

    def _finish(self):
        self.hide()

    def _centre(self):
        if self.parent():
            pw, ph = self.parent().width(), self.parent().height()
            cw = self._card.width()
            ch = self._card.sizeHint().height()
            self._card.setGeometry((pw - cw) // 2, max(40, (ph - ch) // 2), cw, ch)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.setGeometry(self.parent().rect() if self.parent() else self.rect())
        self._centre()

    def showEvent(self, event):
        super().showEvent(event)
        if self.parent():
            self.setGeometry(self.parent().rect())
        self._centre()
