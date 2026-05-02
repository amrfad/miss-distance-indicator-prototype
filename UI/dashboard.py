# UI/dashboard.py
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QStatusBar, QFrame, QTabWidget,
    QTextEdit, QPushButton, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, QDateTime
from PyQt6.QtGui import QFont

from UI.config_raspi import RaspiConfigPanel
from UI.config_laptop import LaptopConfigPanel
from UI.widgets.status_panel import StatusPanel
from UI.widgets.log_panel import LogPanel
from UI.widgets.control_buttons import ControlButtons


class MainDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MDI — Miss Distance Indicator")
        self.setMinimumSize(1400, 820)
        self._build_ui()
        self._setup_status_bar()
        self._setup_timers()

    # ──────────────────────────────────────────────────────────
    # UI BUILD
    # ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("rootWidget")
        self.setCentralWidget(root)

        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._build_header())
        root_layout.addWidget(self._build_toolbar())

        content = QWidget()
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(12, 12, 12, 12)
        content_layout.setSpacing(12)

        content_layout.addWidget(self._build_left_panel(), stretch=6)
        content_layout.addWidget(self._build_right_panel(), stretch=4)

        root_layout.addWidget(content, stretch=1)
        root_layout.addWidget(self._build_bottom_bar())

    # ── Header ────────────────────────────────────────────────

    def _build_header(self):
        panel = QWidget()
        panel.setObjectName("headerPanel")
        panel.setFixedHeight(64)

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(20, 0, 20, 0)

        title_block = QVBoxLayout()
        title_block.setSpacing(0)

        title = QLabel("◈ MISS DISTANCE INDICATOR")
        title.setObjectName("appTitle")
        title_block.addWidget(title)

        subtitle = QLabel("GROUND CONTROL STATION  ·  MDI PROTOTYPE")
        subtitle.setObjectName("appSubtitle")
        title_block.addWidget(subtitle)

        layout.addLayout(title_block)
        layout.addStretch()

        self.clock_label = QLabel()
        self.clock_label.setObjectName("statusValue")
        self.clock_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._refresh_clock()
        layout.addWidget(self.clock_label)

        return panel

    # ── Toolbar (control buttons) ──────────────────────────────
    # FIX: was QWidget — must be QFrame so QSS #card selector applies

    def _build_toolbar(self):
        wrapper = QFrame()                    # ← FIX: QFrame not QWidget
        wrapper.setObjectName("card")
        wrapper.setFixedHeight(52)

        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(8)

        self.control_buttons = ControlButtons()
        # Wire signals
        self.control_buttons.apply_serial_clicked.connect(self._on_apply_serial)
        layout.addWidget(self.control_buttons)

        return wrapper

    # ── Left panel: config tabs ────────────────────────────────

    def _build_left_panel(self):
        self.tab_widget = QTabWidget()
        self.raspi_config = RaspiConfigPanel()
        self.laptop_config = LaptopConfigPanel()

        self.tab_widget.addTab(self.raspi_config, "  RASPBERRY PI  ")
        self.tab_widget.addTab(self.laptop_config, "  GROUND STATION  ")

        self.raspi_config.config_changed.connect(
            lambda cfg: self._on_config_saved("Raspberry Pi", cfg)
        )
        self.laptop_config.config_changed.connect(
            lambda cfg: self._on_config_saved("Ground Station", cfg)
        )

        return self.tab_widget

    # ── Right panel: status + preview + log ───────────────────

    def _build_right_panel(self):
        right = QWidget()
        layout = QVBoxLayout(right)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.status_panel = StatusPanel()
        layout.addWidget(self.status_panel)

        layout.addWidget(self._build_preview_panel(), stretch=2)

        self.log_panel = LogPanel()
        layout.addWidget(self.log_panel, stretch=2)

        return right

    def _build_preview_panel(self):
        frame = QFrame()
        frame.setObjectName("card")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 8, 10, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel("CONFIG PREVIEW (JSON)")
        title.setObjectName("sectionTitle")
        header.addWidget(title)
        header.addStretch()

        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedSize(26, 26)
        refresh_btn.setToolTip("Refresh preview")
        refresh_btn.clicked.connect(self._refresh_preview)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        self.preview_text = QTextEdit()
        self.preview_text.setObjectName("logConsole")
        self.preview_text.setReadOnly(True)
        self.preview_text.setPlaceholderText("// config preview will appear here...")
        layout.addWidget(self.preview_text)

        return frame

    # ── Bottom bar ─────────────────────────────────────────────

    def _build_bottom_bar(self):
        bar = QFrame()
        bar.setObjectName("bottomBar")
        bar.setFixedHeight(32)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)

        self.system_status_label = QLabel("● SYSTEM READY")
        self.system_status_label.setObjectName("statusOk")
        layout.addWidget(self.system_status_label)

        layout.addStretch()

        self.mode_label = QLabel("MODE: STANDBY")
        self.mode_label.setObjectName("statusHeading")
        layout.addWidget(self.mode_label)

        sep = QLabel(" | ")
        sep.setObjectName("statusHeading")
        layout.addWidget(sep)

        self.session_label = QLabel("SESSION: —")
        self.session_label.setObjectName("statusHeading")
        layout.addWidget(self.session_label)

        return bar

    # ──────────────────────────────────────────────────────────
    # STATUS BAR & TIMERS
    # ──────────────────────────────────────────────────────────

    def _setup_status_bar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("MDI Ground Control — Ready")

    def _setup_timers(self):
        clock_timer = QTimer(self)
        clock_timer.timeout.connect(self._refresh_clock)
        clock_timer.start(1000)

        status_timer = QTimer(self)
        status_timer.timeout.connect(self._poll_status)
        status_timer.start(2000)

    # ──────────────────────────────────────────────────────────
    # SLOTS / CALLBACKS
    # ──────────────────────────────────────────────────────────

    def _refresh_clock(self):
        ts = QDateTime.currentDateTime().toString("yyyy-MM-dd  hh:mm:ss")
        self.clock_label.setText(ts)

    def _poll_status(self):
        """Replace with real serial/REST polling."""
        dummy = {
            "zoom":           "Connected",
            "raspi":          "Online",
            "sdr":            "Active",
            "mic_count":      "6/6",
            "last_detection": "—",
            "session":        "—",      # FIX: was missing → status cell stayed "—" forever
        }
        self.status_panel.update_status(dummy)

    def _refresh_preview(self):
        import json
        active = self.tab_widget.currentIndex()
        panel = self.raspi_config if active == 0 else self.laptop_config
        try:
            cfg = panel._get_values_from_ui()
            self.preview_text.setPlainText(json.dumps(cfg, indent=2))
        except Exception as e:
            self.preview_text.setPlainText(f"// Error reading config:\n// {e}")

    def _on_config_saved(self, device: str, cfg: dict):
        import json

        # Internal action from RaspiConfigPanel (e.g. restart request)
        if cfg.get("_action") == "restart_drone":
            self._handle_drone_restart()
            return

        self.log_panel.log(f"Config saved [{device}] — {len(cfg)} params", level="INFO")
        self.preview_text.setPlainText(json.dumps(cfg, indent=2))

    def _on_apply_serial(self):
        """Send 🔄 runtime params via SET_CONFIG serial command (in-flight flow)."""
        try:
            runtime_cfg = self.raspi_config.get_runtime_config()
        except Exception as e:
            self.log_panel.log(f"Failed to read runtime config: {e}", level="ERROR")
            return

        if not runtime_cfg:
            self.log_panel.log("No runtime params to send", level="WARNING")
            return

        import json
        param_count = len(runtime_cfg)
        self.log_panel.log(
            f"Sending {param_count} runtime params via SET_CONFIG serial...",
            level="INFO"
        )
        self.preview_text.setPlainText(
            f"// SET_CONFIG payload ({param_count} runtime params):\n"
            + json.dumps(runtime_cfg, indent=2)
        )

        # TODO: wire to actual serial_manager.send_set_config(runtime_cfg)
        # Format per Communication Contract § 5.1:
        # "SET_CONFIG\n[CONFIG_START]\n{json}\n[CONFIG_END]\n"
        self.log_panel.log(
            "SET_CONFIG dispatched (stub — connect to serial_manager)",
            level="WARNING"
        )
        self.status_bar.showMessage(f"SET_CONFIG sent — {param_count} params", 3000)

    def _handle_drone_restart(self):
        """Handle POST /system/restart flow."""
        self.log_panel.log("Drone restart requested", level="WARNING")
        self.status_bar.showMessage("Sending restart command to drone...", 3000)
        # TODO: wire to REST client → POST http://<drone-ip>:5000/system/restart
        QMessageBox.information(
            self,
            "Drone Restart",
            "Restart command sent to drone.\n\n"
            "The drone Python process will restart in ~2 seconds.\n"
            "Wait for reconnection before sending new commands."
        )

    # ──────────────────────────────────────────────────────────
    # PUBLIC API (for external integration)
    # ──────────────────────────────────────────────────────────

    def set_connection_state(self, connected: bool):
        self.control_buttons.set_connected(connected)
        if connected:
            self.system_status_label.setText("● CONNECTED")
            self.system_status_label.setObjectName("statusOk")
            self.log_panel.log("Drone connection established", level="INFO")
        else:
            self.system_status_label.setText("● DISCONNECTED")
            self.system_status_label.setObjectName("statusError")
            self.log_panel.log("Drone disconnected", level="WARNING")
        self._repolish(self.system_status_label)

    def set_recording_state(self, recording: bool):
        self.control_buttons.set_recording(recording)
        mode = "RECORDING" if recording else "STANDBY"
        self.mode_label.setText(f"MODE: {mode}")
        level = "WARNING" if recording else "INFO"
        self.log_panel.log(f"Recording {'started' if recording else 'stopped'}", level=level)

    def set_session_name(self, name: str):
        """Update session label in bottom bar and status panel."""
        self.session_label.setText(f"SESSION: {name}")
        self.status_panel.update_status({"session": name})

    # ──────────────────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────────────────

    def _repolish(self, widget):
        widget.style().unpolish(widget)
        widget.style().polish(widget)
