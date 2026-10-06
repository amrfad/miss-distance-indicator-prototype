# demo_ground/ui/widgets/log_panel.py
"""Scrollable system log dengan tombol collapse/expand dan pewarnaan level log."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QFrame,
)
from PySide6.QtCore import QDateTime, Qt, Signal


class LogPanel(QWidget):
    """Scrollable system log with colour-coded severity levels."""

    _COLORS = {
        "INFO":    "#16a34a",
        "WARNING": "#d97706",
        "ERROR":   "#dc2626",
        "DEBUG":   "#2563eb",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._collapsed = False
        self._pending_count = 0
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header bar (selalu visible)
        header_bar = QFrame()
        header_bar.setObjectName("logHeaderBar")
        header_bar.setFixedHeight(32)
        header_bar.setStyleSheet(
            "QFrame#logHeaderBar {"
            "  background-color: #f8fafc;"
            "  border-top: 1px solid #dbe4ee;"
            "  border-bottom: 1px solid #dbe4ee;"
            "}"
        )
        hh = QHBoxLayout(header_bar)
        hh.setContentsMargins(10, 0, 8, 0)
        hh.setSpacing(8)

        self._title_lbl = QLabel("▪ SYSTEM LOG")
        self._title_lbl.setObjectName("sectionTitle")
        hh.addWidget(self._title_lbl)

        self._pending_lbl = QLabel("")
        self._pending_lbl.setObjectName("statusHeading")
        self._pending_lbl.setStyleSheet("color: #d97706; font-size: 10px;")
        hh.addWidget(self._pending_lbl)

        hh.addStretch()

        self._clear_btn = QPushButton("CLEAR")
        self._clear_btn.clicked.connect(self.clear)
        hh.addWidget(self._clear_btn)

        self._toggle_btn = QPushButton("HIDE")
        self._toggle_btn.clicked.connect(self._toggle_collapse)
        hh.addWidget(self._toggle_btn)

        layout.addWidget(header_bar)

        # Console area
        self._console = QTextEdit()
        self._console.setObjectName("logConsole")
        self._console.setReadOnly(True)
        self._console.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._console.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(self._console)

    def log(self, message: str, level: str = "INFO"):
        ts = QDateTime.currentDateTime().toString("hh:mm:ss")
        color = self._COLORS.get(level, "#64748b")
        line = (
            f'<span style="color:#94a3b8">[{ts}]</span> '
            f'<span style="color:{color};font-weight:bold">[{level}]</span> '
            f'<span style="color:#1e293b">{message}</span>'
        )
        self._console.append(line)

        if self._collapsed:
            self._pending_count += 1
            self._pending_lbl.setText(f"({self._pending_count} new)")

    def clear(self):
        self._console.clear()
        self._pending_count = 0
        self._pending_lbl.setText("")

    def _toggle_collapse(self):
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool):
        self._collapsed = collapsed
        self._console.setVisible(not collapsed)
        self._toggle_btn.setText("SHOW" if collapsed else "HIDE")
        if not collapsed:
            self._pending_count = 0
            self._pending_lbl.setText("")
