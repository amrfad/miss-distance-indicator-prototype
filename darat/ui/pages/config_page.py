# darat/ui/pages/config_page.py
"""Config Page — wraps RaspiConfigPanel and LaptopConfigPanel in sub-tabs."""

import json

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QFrame, QTextEdit, QPushButton, QLabel, QMessageBox,
    QDialog,  # tambah ini untuk modal dialog
)
from PySide6.QtCore import Signal, Qt 

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

    log_message       = Signal(str, str)
    restart_requested = Signal()
    apply_serial_requested = Signal(dict)

    def __init__(self, rest_client=None, parent=None):
        super().__init__(parent)
        self._rest = rest_client
        self._build_ui()
        self._wire_signals()

        # Delay initial fetch slightly to let daemon APIs start
        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, self._fetch_initial_configs)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # Sub-tabs
        tabs = QTabWidget()
        self.raspi_config = RaspiConfigPanel()
        self.laptop_config = LaptopConfigPanel()
        tabs.addTab(self.raspi_config, "  🔒 RASPBERRY PI  ")
        tabs.addTab(self.laptop_config, "  🖥 GROUND STATION  ")

        self._tabs = tabs
        root.addWidget(tabs, stretch=3)

        # Config preview panel (as button + modal)
        root.addWidget(self._build_preview_panel(), stretch=0)

    def _build_preview_panel(self) -> QFrame:
        """Build config preview as a button that opens modal dialog."""
        frame = QFrame()
        frame.setObjectName("card")
        frame.setStyleSheet("QFrame#card { background: transparent; border: none; }")

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(10)

        # Tombol preview
        self._preview_btn = QPushButton("👁  PREVIEW CONFIG (JSON)")
        self._preview_btn.setObjectName("btnSecondary")
        self._preview_btn.setFixedHeight(32)
        self._preview_btn.setCursor(Qt.CursorShape.PointingHandCursor)  # ← sekarang Qt sudah di-import
        self._preview_btn.clicked.connect(self._show_preview_dialog)
        layout.addWidget(self._preview_btn)

        layout.addStretch()

        # Restart drone button (pindah ke sini biar lebih rapi)
        self._restart_drone_btn = QPushButton("⚠ RESTART DRONE")
        self._restart_drone_btn.setObjectName("btnReset")
        self._restart_drone_btn.setFixedHeight(32)
        self._restart_drone_btn.clicked.connect(self.restart_requested.emit)
        layout.addWidget(self._restart_drone_btn)

        return frame

    def _show_preview_dialog(self):
        """Open modal dialog with JSON config preview."""
        from PySide6.QtWidgets import QTextEdit, QVBoxLayout, QPushButton, QHBoxLayout
        import json

        active_tab = self._tabs.currentIndex()
        if active_tab == 0:
            cfg = self.raspi_config._get_values_from_ui()
            title = "Raspberry Pi Config Preview"
        else:
            cfg = self.laptop_config._get_values_from_ui()
            title = "Ground Station Config Preview"

        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        dialog.setMinimumSize(500, 400)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(10)

        text_edit = QTextEdit()
        text_edit.setFontFamily("Courier New")
        text_edit.setPlainText(json.dumps(cfg, indent=2))
        text_edit.setReadOnly(True)
        layout.addWidget(text_edit)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        copy_btn = QPushButton("📋 COPY TO CLIPBOARD")
        copy_btn.clicked.connect(lambda: self._copy_json_to_clipboard(cfg))
        btn_layout.addWidget(copy_btn)

        close_btn = QPushButton("CLOSE")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)
        dialog.exec()

    def _copy_json_to_clipboard(self, cfg: dict):
        import json
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(json.dumps(cfg, indent=2))
        self.log_message.emit("Config JSON copied to clipboard", "INFO")

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

    def _on_drone_config_loaded(self, cfg: dict):
        self.raspi_config.set_config(cfg)
        self.log_message.emit("[CONFIG] Drone config successfully synced with backend.", "INFO")