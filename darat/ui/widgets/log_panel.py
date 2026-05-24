# darat/ui/widgets/log_panel.py
"""Scrollable system log dengan tombol collapse/expand.

Fitur baru:
- Tombol ▲/▼ untuk collapse/expand panel
- Signal `visibility_changed` untuk notify parent
- Method `set_collapsed(bool)` untuk kontrol dari luar (mis. auto-collapse di tab Visualize)
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel, QFrame,
)
from PySide6.QtCore import QDateTime, Qt, Signal


class LogPanel(QWidget):
    """Scrollable system log with colour-coded severity levels.

    Usage::
        log_panel.log("Serial connected", level="INFO")
        log_panel.log("Baud mismatch detected", level="WARNING")
        log_panel.log("Serial port not found", level="ERROR")
        log_panel.log("SET_CONFIG dispatched", level="DEBUG")

    Collapsible::
        log_panel.set_collapsed(True)   # sembunyikan console, hanya header
        log_panel.set_collapsed(False)  # tampilkan kembali
    """

    _COLORS = {
        "INFO":    "#16a34a",
        "WARNING": "#d97706",
        "ERROR":   "#dc2626",
        "DEBUG":   "#2563eb",
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._collapsed = False
        self._pending_count = 0  # hitung pesan saat collapsed
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header bar (selalu visible) ────────────────────────────────
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

        # ── Console (collapsible) ─────────────────────────────────────
        self._console = QTextEdit()
        self._console.setObjectName("logConsole")
        self._console.setReadOnly(True)
        layout.addWidget(self._console)

    # ── Public API ──────────────────────────────────────────────────────

    def log(self, message: str, level: str = "INFO"):
        ts = QDateTime.currentDateTime().toString("hh:mm:ss")
        color = self._COLORS.get(level, "#64748b")
        line = (
            f'<span style="color:#94a3b8">[{ts}]</span> '
            f'<span style="color:{color};font-weight:bold">[{level}]</span> '
            f'<span style="color:#1e293b">{message}</span>'
        )
        self._console.append(line)
        sb = self._console.verticalScrollBar()
        sb.setValue(sb.maximum())

        if self._collapsed:
            self._pending_count += 1
            self._pending_lbl.setText(f"({self._pending_count} new)")

    def clear(self):
        self._console.clear()

    def set_collapsed(self, collapsed: bool):
        """Collapse (True) atau expand (False) panel log secara programatik."""
        if self._collapsed == collapsed:
            return
        self._collapsed = collapsed
        self._console.setVisible(not collapsed)
        if collapsed:
            self._toggle_btn.setText("SHOW")
            self._pending_count = 0
            self._pending_lbl.setText("")
        else:
            self._toggle_btn.setText("HIDE")
            self._pending_count = 0
            self._pending_lbl.setText("")

    def is_collapsed(self) -> bool:
        return self._collapsed

    # ── Private ─────────────────────────────────────────────────────────

    def _toggle_collapse(self):
        self.set_collapsed(not self._collapsed)
