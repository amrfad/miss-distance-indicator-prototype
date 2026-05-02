# UI/widgets/log_panel.py
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QTextEdit, QPushButton, QLabel
)
from PyQt6.QtCore import QDateTime, Qt


class LogPanel(QWidget):
    """Scrollable system log with colour-coded severity levels.

    Usage::
        log_panel.log("Serial connected", level="INFO")
        log_panel.log("Baud mismatch detected", level="WARNING")
        log_panel.log("Serial port not found", level="ERROR")
        log_panel.log("SET_CONFIG dispatched", level="DEBUG")
    """

    _COLORS = {
        "INFO":    "#16a34a",   # green  (matches statusOk)
        "WARNING": "#d97706",   # amber  (matches statusWarn)
        "ERROR":   "#dc2626",   # red    (matches statusError)
        "DEBUG":   "#2563eb",   # blue   (matches statusValue)
    }

    def __init__(self):
        super().__init__()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        title = QLabel("SYSTEM LOG")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch()

        self._clear_btn = QPushButton("CLEAR")
        self._clear_btn.setFixedSize(56, 24)
        self._clear_btn.clicked.connect(self.clear)
        header.addWidget(self._clear_btn)

        layout.addLayout(header)

        # Console
        self._console = QTextEdit()
        self._console.setObjectName("logConsole")
        self._console.setReadOnly(True)
        layout.addWidget(self._console)

    # ──────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────

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

    def clear(self):
        self._console.clear()
