# darat/ui/pages/config_page.py
"""Config Page — wraps RaspiConfigPanel and LaptopConfigPanel in sub-tabs."""

import json

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QFrame, QTextEdit, QPushButton, QLabel, QMessageBox,
)
from PyQt6.QtCore import pyqtSignal

from ..config_raspi import RaspiConfigPanel
from ..config_laptop import LaptopConfigPanel


class ConfigPage(QWidget):
    """Config tab: Raspberry Pi and Ground Station config sub-tabs.

    Signals
    -------
    log_message(str, str)   — (message, level) for the shared log panel
    restart_requested()     — user wants to restart the drone process
    apply_serial_requested(dict) — runtime params ready to send via serial
    """

    log_message       = pyqtSignal(str, str)
    restart_requested = pyqtSignal()
    apply_serial_requested = pyqtSignal(dict)

    def __init__(self, rest_client=None, parent=None):
        super().__init__(parent)
        self._rest = rest_client
        self._build_ui()
        self._wire_signals()

        # Delay initial fetch slightly to let daemon APIs start
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(500, self._fetch_initial_configs)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # Sub-tabs
        tabs = QTabWidget()
        self.raspi_config  = RaspiConfigPanel()
        self.laptop_config = LaptopConfigPanel()
        tabs.addTab(self.raspi_config,  "  🔒 RASPBERRY PI  ")
        tabs.addTab(self.laptop_config, "  🖥 GROUND STATION  ")

        self._tabs = tabs
        root.addWidget(tabs, stretch=3)

        # Config preview panel
        root.addWidget(self._build_preview_panel(), stretch=1)

    def _build_preview_panel(self) -> QFrame:
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

        self._preview = QTextEdit()
        self._preview.setObjectName("logConsole")
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText("// config preview will appear here...")
        self._preview.setMaximumHeight(160)
        layout.addWidget(self._preview)
        return frame

    def _wire_signals(self):
        """Connect UI signals to REST client and vice versa."""
        if not self._rest:
            return

        # 1. UI -> REST API (Save / Reset)
        self.laptop_config.config_save_requested.connect(self._do_patch_ground)
        self.laptop_config.config_reset_requested.connect(
            lambda: self._rest.reset_ground_config()
        )
        
        self.raspi_config.config_save_requested.connect(self._do_patch_drone)
        self.raspi_config.config_reset_requested.connect(
            lambda: self.log_message.emit("Drone config reset not fully implemented in API", "WARNING")
            # lambda: self._rest.reset_drone_config() # (if implemented in Drone API)
        )
        self.raspi_config.restart_drone_requested.connect(
            lambda: self._rest.restart_drone()
        )

        # 2. REST API -> UI (Load / Update Confirmation)
        self._rest.ground_config_received.connect(self._on_ground_config_loaded)
        self._rest.ground_config_updated.connect(self._on_ground_config_loaded)
        self._rest.ground_config_reset.connect(self._on_ground_config_loaded)

        self._rest.drone_config_received.connect(self._on_drone_config_loaded)
        self._rest.drone_config_updated.connect(self._on_drone_config_loaded)
        self._rest.drone_restarted.connect(
            lambda _: self.log_message.emit("Drone restart command accepted", "INFO")
        )

        # 3. Errors
        self._rest.error.connect(self._show_error)

    def _show_error(self, msg: str):
        self.log_message.emit(f"[CONFIG] REST API Error: {msg}", "ERROR")

    # ── Public ───────────────────────────────────────────────────────────

    def get_runtime_config(self) -> dict:
        """Return only 🔄 runtime params from the Raspi panel."""
        return self.raspi_config.get_runtime_config()

    # ── Slots ─────────────────────────────────────────────────────────────

    def _do_patch_ground(self, cfg: dict):
        self.log_message.emit("[CONFIG] Attempting to save Ground Station config to backend...", "INFO")
        self._rest.patch_ground_config(cfg)

    def _do_patch_drone(self, cfg: dict):
        self.log_message.emit("[CONFIG] Attempting to save Drone config to backend...", "INFO")
        self._rest.patch_drone_config(cfg)

    def _fetch_initial_configs(self):
        if self._rest:
            self.log_message.emit("[CONFIG] Fetching initial configs from backends...", "DEBUG")
            self._rest.get_ground_config()
            self._rest.get_drone_config()

    def _on_ground_config_loaded(self, cfg: dict):
        self.laptop_config.set_config(cfg)
        self.log_message.emit("[CONFIG] Ground config successfully synced with backend.", "INFO")
        self._refresh_preview()

    def _on_drone_config_loaded(self, cfg: dict):
        self.raspi_config.set_config(cfg)
        self.log_message.emit("[CONFIG] Drone config successfully synced with backend.", "INFO")
        self._refresh_preview()

    def _refresh_preview(self):
        active = self._tabs.currentIndex()
        panel = self.raspi_config if active == 0 else self.laptop_config
        try:
            cfg = panel._get_values_from_ui()
            self._preview.setPlainText(json.dumps(cfg, indent=2))
        except Exception as exc:
            self._preview.setPlainText(f"// Error reading config:\n// {exc}")
