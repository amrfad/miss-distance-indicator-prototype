# darat/ui/config_laptop.py
"""Ground Station (Laptop) configuration panel — Blender/Unity property inspector style vertical layout.

Acts purely as a UI view. Reads and writes are handled via signals and REST API.
"""

import serial
import serial.tools.list_ports
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QVBoxLayout, QHBoxLayout,
    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QPushButton,
    QMessageBox, QLabel, QGridLayout, QScrollArea, QFrame,
    QStackedWidget, QListWidget,
)
from PySide6.QtCore import Signal, Qt, QThread, QTimer

from .widgets.collapsible_section import CollapsibleSection
try:
    from ..io.serial_manager import is_bluetooth_port, is_usb_port, format_port_label
except (ImportError, ValueError):
    from darat.io.serial_manager import is_bluetooth_port, is_usb_port, format_port_label

_DEFAULT_MIC_POSITIONS = {
    "mic0": {"x": -1.58, "y": 0.77, "z": 0.09},
    "mic1": {"x": 1.60, "y": 0.77, "z": 0.09},
    "mic2": {"x": -0.59, "y": -0.92, "z": -0.07},
    "mic3": {"x": 0.59, "y": -0.92, "z": -0.05},
    "mic4": {"x": -0.50, "y": -0.11, "z": -0.16},
    "mic5": {"x": 0.13, "y": -0.01, "z": -0.17},
}


class _PortScanWorker(QThread):
    ports_found = Signal(list, list)

    def run(self):
        try:
            ports = serial.tools.list_ports.comports()
        except Exception:
            ports = []
        valid_ports = [p for p in ports if not is_bluetooth_port(p)]
        usb_ports = [p for p in valid_ports if is_usb_port(p)]
        other_ports = [p for p in valid_ports if not is_usb_port(p)]
        bt_ports = [p for p in ports if is_bluetooth_port(p)]
        self.ports_found.emit(usb_ports + other_ports, bt_ports)


def _make_page(*sections: QWidget) -> QWidget:
    """Bungkus collapsible sections ke dalam satu halaman vertikal."""
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 8, 0)
    layout.setSpacing(12)
    for sec in sections:
        layout.addWidget(sec)
    layout.addStretch()
    return page


class LaptopConfigPanel(QWidget):
    """Configuration panel for the Ground Station (laptop/PC) — Vertical sidebar & Collapsible sections."""

    config_save_requested = Signal(dict)
    config_reset_requested = Signal()

    _DEFAULTS = {
        "serial_port": "AUTO",
        "baud_rate": 230400,
        "serial_timeout": 1.0,
        "raspi_ip": "10.99.99.2",
        "drone_port": 5000,
        "speed_of_sound": 343.0,
        "cluster_eps": 1.0,
        "mic_positions": _DEFAULT_MIC_POSITIONS,
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_config = dict(self._DEFAULTS)
        self.current_config["mic_positions"] = {
            k: dict(v) for k, v in _DEFAULT_MIC_POSITIONS.items()
        }
        self._mic_spinboxes: dict[str, QDoubleSpinBox] = {}
        self._build_ui()
        self.set_config(self.current_config)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # Main body with QScrollArea wrapping vertical sidebar + stacked widget
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        body_layout = QHBoxLayout(inner)
        body_layout.setContentsMargins(4, 4, 4, 4)
        body_layout.setSpacing(12)

        # Sidebar list
        self._sidebar_list = QListWidget()
        self._sidebar_list.setObjectName("configSidebar")
        self._sidebar_list.setFixedWidth(170)
        self._sidebar_list.addItems(["Connection", "Processing", "Microphone Positions"])
        self._sidebar_list.setCurrentRow(0)

        # Stacked widget for category pages
        self._stacked_widget = QStackedWidget()
        self._stacked_widget.addWidget(_make_page(self._group_serial(), self._group_network()))
        self._stacked_widget.addWidget(_make_page(self._group_processing()))
        self._stacked_widget.addWidget(_make_page(self._group_mic_positions()))

        self._sidebar_list.currentRowChanged.connect(self._stacked_widget.setCurrentIndex)

        body_layout.addWidget(self._sidebar_list, stretch=0)
        body_layout.addWidget(self._stacked_widget, stretch=1)

        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        # Sticky action buttons fixed at root bottom outside scroll area
        action_bar = QWidget()
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(8, 4, 8, 8)
        action_layout.addLayout(self._action_buttons())
        root.addWidget(action_bar, stretch=0)

    def _group_serial(self) -> CollapsibleSection:
        sec = CollapsibleSection("SERIAL COMMUNICATION")

        port_container = QWidget()
        port_layout = QHBoxLayout(port_container)
        port_layout.setContentsMargins(0, 0, 0, 0)
        port_layout.setSpacing(6)

        self.serial_port = QComboBox()
        self.serial_port.setObjectName("monoField")
        self.serial_port.setEditable(True)
        self.serial_port.setToolTip("Select detected COM port or type custom port (e.g. COM3, /dev/ttyUSB0)")

        self.btn_refresh_ports = QPushButton("Detect Ports")
        self.btn_refresh_ports.setObjectName("btnPrimary")
        self.btn_refresh_ports.setFixedHeight(28)
        self.btn_refresh_ports.setToolTip("Scan available serial COM ports on laptop")
        self.btn_refresh_ports.clicked.connect(self.refresh_serial_ports)

        port_layout.addWidget(self.serial_port, stretch=1)
        port_layout.addWidget(self.btn_refresh_ports, stretch=0)

        sec.add_row("Serial Port:", port_container)

        self.baud_rate = QComboBox()
        self.baud_rate.setObjectName("monoField")
        self.baud_rate.addItems(["9600", "19200", "38400", "57600", "115200", "230400"])
        sec.add_row("Baud Rate:", self.baud_rate)

        baud_warn = QLabel("Must match Raspberry Pi baud rate")
        baud_warn.setObjectName("labelRestart")
        baud_warn.setStyleSheet("font-size: 10px; margin-left: 8px; color: #64748b;")
        sec.add_row("", baud_warn)

        self.serial_timeout = QDoubleSpinBox()
        self.serial_timeout.setObjectName("monoField")
        self.serial_timeout.setRange(0.1, 10.0)
        self.serial_timeout.setSingleStep(0.1)
        self.serial_timeout.setSuffix(" s")
        sec.add_row("Timeout:", self.serial_timeout)

        return sec

    def _group_network(self) -> CollapsibleSection:
        sec = CollapsibleSection("NETWORK SETTINGS")

        self.raspi_ip = QLineEdit()
        self.raspi_ip.setObjectName("monoField")
        self.raspi_ip.setPlaceholderText("10.99.99.2")
        sec.add_row("Drone IP Address:", self.raspi_ip)

        self.drone_port = QSpinBox()
        self.drone_port.setObjectName("monoField")
        self.drone_port.setRange(1024, 65535)
        sec.add_row("Drone API Port:", self.drone_port)

        return sec

    def _group_processing(self) -> CollapsibleSection:
        sec = CollapsibleSection("PROCESSING PARAMETERS")

        self.speed_of_sound = QDoubleSpinBox()
        self.speed_of_sound.setObjectName("monoField")
        self.speed_of_sound.setRange(300.0, 380.0)
        self.speed_of_sound.setSingleStep(0.1)
        self.speed_of_sound.setDecimals(1)
        self.speed_of_sound.setSuffix(" m/s")
        sec.add_row("Speed of Sound:", self.speed_of_sound)

        self.cluster_eps = QDoubleSpinBox()
        self.cluster_eps.setObjectName("monoField")
        self.cluster_eps.setRange(0.1, 20.0)
        self.cluster_eps.setSingleStep(0.1)
        self.cluster_eps.setDecimals(1)
        self.cluster_eps.setSuffix(" m")
        self.cluster_eps.setToolTip("Bucher-Misra cluster grouping threshold (CLUSTER_EPS)")
        sec.add_row("Cluster EPS:", self.cluster_eps)

        return sec

    def _group_mic_positions(self) -> CollapsibleSection:
        sec = CollapsibleSection("MICROPHONE POSITIONS (3D coordinates in meters)")

        table_widget = QWidget()
        outer = QVBoxLayout(table_widget)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(12)

        # Single Grid: Row 0 is header, Row 1-6 are mic input spinboxes
        grid = QGridLayout()
        grid.setSpacing(8)

        # Header row
        for col, text in enumerate(["", "X (m)", "Y (m)", "Z (m)"]):
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size:11px; font-weight:bold; color:#475569;")
            grid.addWidget(lbl, 0, col)

        # Grid 6 rows x 3 columns of spinboxes (monoField tagged)
        for row in range(6):
            mic_key = f"mic{row}"

            lbl = QLabel(mic_key.upper())
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet("font-size:11px; font-weight:bold; color:#2563eb; min-width:45px;")
            grid.addWidget(lbl, row + 1, 0)

            for col, axis in enumerate(["x", "y", "z"]):
                sb = QDoubleSpinBox()
                sb.setObjectName("monoField")
                sb.setRange(-5.0, 5.0)
                sb.setSingleStep(0.01)
                sb.setDecimals(3)
                sb.setSuffix(" m")
                sb.setFixedWidth(130)
                sb.setToolTip(f"{mic_key} {axis.upper()} position")
                grid.addWidget(sb, row + 1, col + 1)
                self._mic_spinboxes[f"{mic_key}_{axis}"] = sb

        # Centered container for table grid
        center_layout = QHBoxLayout()
        center_layout.addStretch()
        center_layout.addLayout(grid)
        center_layout.addStretch()
        outer.addLayout(center_layout)

        # Reset button
        reset_mic_btn = QPushButton("Reset Mic Positions to Default")
        reset_mic_btn.setObjectName("btnReset")
        reset_mic_btn.setFixedHeight(30)
        reset_mic_btn.clicked.connect(self._reset_mic_positions)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(reset_mic_btn)
        btn_layout.addStretch()
        outer.addLayout(btn_layout)

        sec.add_widget(table_widget)
        return sec

    def _action_buttons(self):
        row = QHBoxLayout()
        row.setSpacing(8)
        save_btn = QPushButton("SAVE CONFIG")
        save_btn.setObjectName("btnSave")
        save_btn.clicked.connect(self._save)
        row.addWidget(save_btn)

        reset_btn = QPushButton("RESET DEFAULTS")
        reset_btn.setObjectName("btnReset")
        reset_btn.clicked.connect(self._reset)
        row.addWidget(reset_btn)
        row.addStretch()
        return row

    # ── Serial Port Detection ─────────────────────────────────────────────

    def refresh_serial_ports(self):
        """Re-scan available COM ports on laptop asynchronously in background worker."""
        self.btn_refresh_ports.setEnabled(False)
        self.btn_refresh_ports.setText("Scanning...")

        current_val = self._get_serial_port_value()

        self._scan_worker = _PortScanWorker()
        def _on_ports(ordered_ports, bt_ports):
            self._apply_scanned_ports(ordered_ports, bt_ports, current_val)
            self.btn_refresh_ports.setText("Refreshed!")
            QTimer.singleShot(700, _reset_button)

        def _reset_button():
            self.btn_refresh_ports.setText("Detect Ports")
            self.btn_refresh_ports.setEnabled(True)

        self._scan_worker.ports_found.connect(_on_ports)
        self._scan_worker.finished.connect(self._scan_worker.deleteLater)
        self._scan_worker.start()

    def _update_serial_port_selection(self, target_port: str = ""):
        # Fast path: check if target_port is already present in current dropdown items
        if self.serial_port.count() > 0 and target_port:
            idx = self.serial_port.findData(target_port)
            if idx < 0:
                idx = self.serial_port.findText(target_port)
            if idx >= 0:
                self.serial_port.blockSignals(True)
                self.serial_port.setCurrentIndex(idx)
                self.serial_port.blockSignals(False)
                return
            elif self.serial_port.isEditable():
                self.serial_port.blockSignals(True)
                self.serial_port.setCurrentText(target_port)
                self.serial_port.blockSignals(False)
                return

        # Synchronous fallback scan if dropdown empty or unlisted
        try:
            ports = serial.tools.list_ports.comports()
        except Exception:
            ports = []
        valid_ports = [p for p in ports if not is_bluetooth_port(p)]
        usb_ports = [p for p in valid_ports if is_usb_port(p)]
        other_ports = [p for p in valid_ports if not is_usb_port(p)]
        bt_ports = [p for p in ports if is_bluetooth_port(p)]
        self._apply_scanned_ports(usb_ports + other_ports, bt_ports, target_port)

    def _apply_scanned_ports(self, ordered_ports: list, bt_ports: list, target_port: str = ""):
        self.serial_port.blockSignals(True)
        self.serial_port.clear()

        found = False
        for p in ordered_ports:
            dev = p.device
            display_name = format_port_label(p)

            self.serial_port.addItem(display_name, dev)
            if dev == target_port or display_name == target_port:
                found = True

        # Handle target_port if it was unlisted or a bluetooth port
        if target_port and not found:
            matching_bt = [p for p in bt_ports if p.device == target_port]
            if matching_bt:
                bt_p = matching_bt[0]
                display_name = f"{format_port_label(bt_p)} (Bluetooth)"
                self.serial_port.addItem(display_name, target_port)
            else:
                self.serial_port.addItem(target_port, target_port)

        idx = self.serial_port.findData(target_port)
        if idx < 0:
            idx = self.serial_port.findText(target_port)

        if idx >= 0:
            self.serial_port.setCurrentIndex(idx)
        elif target_port:
            self.serial_port.setCurrentText(target_port)
        elif self.serial_port.count() > 0:
            self.serial_port.setCurrentIndex(0)
        else:
            self.serial_port.addItem("AUTO — Auto Detect USB", "AUTO")
            self.serial_port.setCurrentText("AUTO — Auto Detect USB")

        self.serial_port.blockSignals(False)

    def _get_serial_port_value(self) -> str:
        if not hasattr(self, "serial_port"):
            return "AUTO"
        text = self.serial_port.currentText().strip()
        idx = self.serial_port.currentIndex()
        if idx >= 0:
            item_text = self.serial_port.itemText(idx)
            item_data = self.serial_port.itemData(idx)
            if item_text == text and item_data:
                return str(item_data)

        raw = text.strip()
        if " — " in raw:
            raw = raw.split(" — ")[0].strip()
        if " (" in raw:
            raw = raw.split(" (")[0].strip()
        return raw

    # ── Data methods ──────────────────────────────────────────────────────

    def set_config(self, cfg: dict):
        """Populate UI from a config dictionary (e.g. from REST API)."""
        merged = dict(self._DEFAULTS)
        merged["mic_positions"] = {k: dict(v) for k, v in _DEFAULT_MIC_POSITIONS.items()}
        merged.update(cfg)

        self.current_config = merged
        c = self.current_config

        self._update_serial_port_selection(c.get("serial_port", "COM3"))
        self.baud_rate.setCurrentText(str(c.get("baud_rate", 230400)))
        self.serial_timeout.setValue(c.get("serial_timeout", 1.0))
        self.raspi_ip.setText(c.get("raspi_ip", "10.99.99.2"))
        self.drone_port.setValue(c.get("drone_port", 5000))
        self.speed_of_sound.setValue(c.get("speed_of_sound", 343.0))
        self.cluster_eps.setValue(c.get("cluster_eps", 1.0))
        self._populate_mic_positions(c.get("mic_positions", _DEFAULT_MIC_POSITIONS))

    def _populate_mic_positions(self, positions: dict):
        for mic_key, coords in positions.items():
            for axis in ("x", "y", "z"):
                sb_key = f"{mic_key}_{axis}"
                if sb_key in self._mic_spinboxes:
                    self._mic_spinboxes[sb_key].setValue(coords.get(axis, 0.0))

    def _get_values_from_ui(self) -> dict:
        return {
            "serial_port": self._get_serial_port_value(),
            "baud_rate": int(self.baud_rate.currentText()),
            "serial_timeout": self.serial_timeout.value(),
            "raspi_ip": self.raspi_ip.text(),
            "drone_port": self.drone_port.value(),
            "speed_of_sound": self.speed_of_sound.value(),
            "cluster_eps": self.cluster_eps.value(),
            "mic_positions": self._get_mic_positions_from_ui(),
        }

    def _get_mic_positions_from_ui(self) -> dict:
        positions = {}
        for i in range(6):
            mic_key = f"mic{i}"
            positions[mic_key] = {
                axis: self._mic_spinboxes[f"{mic_key}_{axis}"].value()
                for axis in ("x", "y", "z")
            }
        return positions

    # ── Slots ─────────────────────────────────────────────────────────────

    def _save(self):
        cfg = self._get_values_from_ui()
        self.current_config = cfg
        self.config_save_requested.emit(cfg)

    def _reset(self):
        reply = QMessageBox.question(
            self, "Reset to Defaults",
            "Reset all Ground Station config to defaults?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.config_reset_requested.emit()

    def _reset_mic_positions(self):
        self._populate_mic_positions(_DEFAULT_MIC_POSITIONS)