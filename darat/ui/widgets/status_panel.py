# darat/ui/widgets/status_panel.py
from PyQt6.QtWidgets import QWidget, QGridLayout, QLabel, QFrame, QVBoxLayout
from PyQt6.QtCore import Qt


class StatusPanel(QWidget):
    """Compact live device-status grid (2 rows × 3 cols).

    Call ``update_status(dict)`` to push new values. Expected keys:
        zoom, raspi, sdr, mic_count, last_detection, session
    """

    _ITEMS = [
        ("ZOOM CAM",     "zoom",           0, 0),
        ("RASPBERRY PI", "raspi",          0, 1),
        ("SDR RADIO",    "sdr",            0, 2),
        ("MICS ACTIVE",  "mic_count",      1, 0),
        ("LAST HIT",     "last_detection", 1, 1),
        ("SESSION",      "session",        1, 2),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value_labels: dict[str, QLabel] = {}
        self._build_ui()

    def _build_ui(self):
        grid = QGridLayout(self)
        grid.setSpacing(6)
        grid.setContentsMargins(0, 0, 0, 0)

        for heading_text, key, row, col in self._ITEMS:
            cell = QFrame()
            cell.setObjectName("card")

            cell_layout = QVBoxLayout(cell)
            cell_layout.setSpacing(2)
            cell_layout.setContentsMargins(8, 6, 8, 6)

            heading = QLabel(heading_text)
            heading.setObjectName("statusHeading")
            heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.addWidget(heading)

            value = QLabel("—")
            value.setObjectName("statusValue")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.addWidget(value)

            grid.addWidget(cell, row, col)
            self._value_labels[key] = value

    def update_status(self, status: dict):
        """Push new status values. Unknown keys are silently ignored."""
        for key, text in status.items():
            if key in self._value_labels:
                self._value_labels[key].setText(str(text))
