# darat/ui/widgets/control_buttons.py
from PyQt6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QFrame
from PyQt6.QtCore import pyqtSignal


class ControlButtons(QWidget):
    """Top toolbar with primary operation buttons.

    Signals
    -------
    connect_clicked        — user pressed Connect
    disconnect_clicked     — user pressed Disconnect
    start_clicked          — user pressed Start Recording
    stop_clicked           — user pressed Stop Recording
    apply_serial_clicked   — user pressed Apply Config via Serial (in-flight)
    """

    connect_clicked      = pyqtSignal()
    disconnect_clicked   = pyqtSignal()
    start_clicked        = pyqtSignal()
    stop_clicked         = pyqtSignal()
    apply_serial_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._is_connected = False
        self._is_recording = False
        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        self.connect_btn = QPushButton("⬡  CONNECT")
        self.connect_btn.setObjectName("btnConnect")
        self.connect_btn.setMinimumWidth(130)
        self.connect_btn.clicked.connect(self.connect_clicked.emit)
        layout.addWidget(self.connect_btn)

        self.disconnect_btn = QPushButton("⊗  DISCONNECT")
        self.disconnect_btn.setObjectName("btnStop")
        self.disconnect_btn.setMinimumWidth(130)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.clicked.connect(self.disconnect_clicked.emit)
        layout.addWidget(self.disconnect_btn)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFrameShadow(QFrame.Shadow.Sunken)
        sep.setFixedWidth(2)
        layout.addWidget(sep)

        self.start_btn = QPushButton("▶  START REC")
        self.start_btn.setObjectName("btnStart")
        self.start_btn.setMinimumWidth(130)
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self.start_clicked.emit)
        layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("■  STOP REC")
        self.stop_btn.setObjectName("btnStop")
        self.stop_btn.setMinimumWidth(130)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.stop_clicked.emit)
        layout.addWidget(self.stop_btn)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setFrameShadow(QFrame.Shadow.Sunken)
        sep2.setFixedWidth(2)
        layout.addWidget(sep2)

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

        self._conn_dot = QLabel("●")
        self._conn_dot.setObjectName("statusError")
        layout.addWidget(self._conn_dot)

        self._conn_label = QLabel("NOT CONNECTED")
        self._conn_label.setObjectName("statusHeading")
        layout.addWidget(self._conn_label)

    # ── Public API ──────────────────────────────────────────────────────

    def set_connected(self, connected: bool, port: str = ""):
        self._is_connected = connected
        self.connect_btn.setEnabled(not connected)
        self.disconnect_btn.setEnabled(connected)
        self.start_btn.setEnabled(connected and not self._is_recording)
        self.apply_serial_btn.setEnabled(connected and not self._is_recording)

        if connected:
            self._conn_dot.setObjectName("statusOk")
            self._conn_label.setText(f"CONNECTED  {port}")
        else:
            self._conn_dot.setObjectName("statusError")
            self._conn_label.setText("NOT CONNECTED")
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(False)
            self.apply_serial_btn.setEnabled(False)

        for w in (self._conn_dot, self._conn_label):
            w.style().unpolish(w)
            w.style().polish(w)

    def set_recording(self, recording: bool):
        self._is_recording = recording
        self.start_btn.setEnabled(not recording and self._is_connected)
        self.stop_btn.setEnabled(recording)
        self.apply_serial_btn.setEnabled(not recording and self._is_connected)
        if recording:
            self.apply_serial_btn.setToolTip(
                "⛔ Cannot apply config while recording is active (DRONE_BUSY).\n"
                "Stop recording first."
            )
        else:
            self.apply_serial_btn.setToolTip(
                "Send runtime parameters via SET_CONFIG serial command.\n"
                "Only 🔄 runtime params will be sent."
            )
