# darat/ui/widgets/status_panel.py
"""Compact live device-status — 1 row horizontal layout."""

from PyQt6.QtWidgets import QWidget, QHBoxLayout, QFrame, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt


class StatusPanel(QWidget):
    """Compact live device-status strip (1 row, 6 cards)."""

    _ITEMS = [
        ("ZOOM", "zoom"),
        ("RASPI", "raspi"),
        ("SDR", "sdr"),
        ("MICS", "mic_count"),
        ("HIT", "last_detection"),
        ("SESSION", "session"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value_labels: dict[str, QLabel] = {}
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(2)

        for heading_text, key in self._ITEMS:
            card = QFrame()
            card.setObjectName("statusCard")
            card.setFixedHeight(44)
            card.setStyleSheet("""
                QFrame#statusCard {
                    background-color: #f8fafc;
                    border: 1px solid #e2e8f0;
                    border-radius: 6px;
                }
            """)

            card_layout = QHBoxLayout(card)
            card_layout.setContentsMargins(8, 4, 8, 4)
            card_layout.setSpacing(6)

            heading = QLabel(heading_text)
            heading.setObjectName("statusHeading")
            heading.setStyleSheet("font-size:9px; font-weight:bold; color:#475569;")
            heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(heading)

            value = QLabel("—")
            value.setObjectName("statusValue")
            value.setStyleSheet("font-size:11px; font-weight:bold; color:#1e293b;")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value.setMinimumWidth(40)
            card_layout.addWidget(value)

            layout.addWidget(card, stretch=1)
            self._value_labels[key] = value

    def update_status(self, status: dict):
        """Push new status values. Unknown keys are silently ignored."""
        for key, text in status.items():
            if key in self._value_labels:
                self._value_labels[key].setText(str(text))