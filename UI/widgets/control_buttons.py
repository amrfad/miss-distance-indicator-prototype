# UI/widgets/control_buttons.py
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QFrame
from PyQt6.QtCore import pyqtSignal, Qt


class ControlButtons(QWidget):
    """Top toolbar with primary operation buttons.

    Signals
    -------
    connect_clicked        — user pressed Connect
    start_clicked          — user pressed Start Recording
    stop_clicked           — user pressed Stop Recording
    apply_serial_clicked   — user pressed Apply Config via Serial (in-flight)
    """

    connect_clicked      = pyqtSignal()
    start_clicked        = pyqtSignal()
    stop_clicked         = pyqtSignal()
    apply_serial_clicked = pyqtSignal()   # NEW: trigger SET_CONFIG via serial

    def __init__(self):
        super().__init__()
        self._is_connected = False
        self._is_recording = False
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # ── Primary operation buttons ────────────────────────
        self.connect_btn = QPushButton("⬡  CONNECT DRONE")
        self.connect_btn.setObjectName("btnConnect")
        self.connect_btn.setMinimumWidth(150)
        self.connect_btn.clicked.connect(self.connect_clicked.emit)
        layout.addWidget(self.connect_btn)

        self.start_btn = QPushButton("▶  START RECORDING")
        self.start_btn.setObjectName("btnStart")
        self.start_btn.setMinimumWidth(150)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start_clicked.emit)
        layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("■  STOP RECORDING")
        self.stop_btn.setObjectName("btnStop")
        self.stop_btn.setMinimumWidth(150)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_clicked.emit)
        layout.addWidget(self.stop_btn)

        # ── Separator ────────────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setFixedWidth(2)
        layout.addWidget(sep)

        # ── Apply Config via Serial (in-flight 🔄 params) ────
        self.apply_serial_btn = QPushButton("📡  APPLY CONFIG (SERIAL)")
        self.apply_serial_btn.setObjectName("btnPrimary")
        self.apply_serial_btn.setMinimumWidth(190)
        self.apply_serial_btn.setEnabled(False)
        self.apply_serial_btn.setToolTip(
            "Send runtime parameters via SET_CONFIG serial command.\n"
            "Only 🔄 runtime params will be sent — restart-required params are excluded."
        )
        self.apply_serial_btn.clicked.connect(self.apply_serial_clicked.emit)
        layout.addWidget(self.apply_serial_btn)

        layout.addStretch()

        # ── Connection indicator ──────────────────────────────
        self._conn_dot = QLabel("●")
        self._conn_dot.setObjectName("statusError")
        self._conn_dot.setToolTip("Connection status")
        layout.addWidget(self._conn_dot)

        self._conn_label = QLabel("NOT CONNECTED")
        self._conn_label.setObjectName("statusHeading")
        layout.addWidget(self._conn_label)

    # ──────────────────────────────────────────────────────────
    # PUBLIC API
    # ──────────────────────────────────────────────────────────

    def set_connected(self, connected: bool):
        """Update button states and indicator based on connection."""
        self._is_connected = connected
        self.connect_btn.setEnabled(not connected)
        self.start_btn.setEnabled(connected and not self._is_recording)
        # Apply serial: enabled when connected and NOT recording
        self.apply_serial_btn.setEnabled(connected and not self._is_recording)

        if connected:
            self._conn_dot.setObjectName("statusOk")
            self._conn_label.setText("CONNECTED")
        else:
            self._conn_dot.setObjectName("statusError")
            self._conn_label.setText("NOT CONNECTED")
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.apply_serial_btn.setEnabled(False)

        # Force QSS re-polish on dynamic objectName change
        for w in (self._conn_dot, self._conn_label):
            w.style().unpolish(w)
            w.style().polish(w)

    def set_recording(self, recording: bool):
        """Update button states based on recording status."""
        self._is_recording = recording
        self.start_btn.setEnabled(not recording and self._is_connected)
        self.stop_btn.setEnabled(recording)
        # Disable serial config apply while recording (DRONE_BUSY)
        self.apply_serial_btn.setEnabled(not recording and self._is_connected)
        if recording:
            self.apply_serial_btn.setToolTip(
                "⛔ Cannot apply config while recording is active (DRONE_BUSY).\n"
                "Stop recording first."
            )
        else:
            self.apply_serial_btn.setToolTip(
                "Send runtime parameters via SET_CONFIG serial command.\n"
                "Only 🔄 runtime params will be sent — restart-required params are excluded."
            )
