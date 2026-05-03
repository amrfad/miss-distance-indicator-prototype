# darat/ui/config_laptop.py
"""Ground Station (Laptop) configuration panel.

Acts purely as a UI view. Reads and writes are handled via signals and REST API.
"""

from PyQt6.QtWidgets import (
    QWidget, QGroupBox, QFormLayout, QVBoxLayout,
    QHBoxLayout, QLineEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QPushButton,
    QCheckBox, QMessageBox, QLabel,
    QGridLayout, QScrollArea, QFrame,
)
from PyQt6.QtCore import pyqtSignal, Qt

_DEFAULT_MIC_POSITIONS = {
    "mic0": {"x": -1.58, "y":  0.77, "z":  0.09},
    "mic1": {"x":  1.60, "y":  0.77, "z":  0.09},
    "mic2": {"x": -0.59, "y": -0.92, "z": -0.07},
    "mic3": {"x":  0.59, "y": -0.92, "z": -0.05},
    "mic4": {"x": -0.50, "y": -0.11, "z": -0.16},
    "mic5": {"x":  0.13, "y": -0.01, "z": -0.17},
}


class LaptopConfigPanel(QWidget):
    """Configuration panel for the Ground Station (laptop/PC)."""

    config_save_requested  = pyqtSignal(dict)
    config_reset_requested = pyqtSignal()

    _DEFAULTS = {
        "serial_port":       "COM3",
        "baud_rate":         230400,
        "serial_timeout":    1.0,
        "use_tcp":           False,
        "raspi_ip":          "192.168.1.100",
        "tcp_port":          5000,
        "speed_of_sound":    343.0,
        "cluster_eps":       1.0,
        "update_interval_s": 0.1,
        "plot_buffer_size":  1000,
        "mic_positions":     _DEFAULT_MIC_POSITIONS,
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

    def _make_form(self, parent: QGroupBox) -> QFormLayout:
        form = QFormLayout(parent)
        form.setSpacing(8)
        form.setContentsMargins(10, 6, 10, 10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        return form

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        outer = QVBoxLayout(inner)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(10)

        outer.addWidget(self._group_serial())
        outer.addWidget(self._group_network())
        outer.addWidget(self._group_processing())
        outer.addWidget(self._group_visualization())
        outer.addWidget(self._group_mic_positions())
        outer.addLayout(self._action_buttons())
        outer.addStretch()

        scroll.setWidget(inner)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def _group_serial(self):
        grp = QGroupBox("SERIAL COMMUNICATION")
        form = self._make_form(grp)

        self.serial_port = QLineEdit()
        self.serial_port.setPlaceholderText("COM3  or  /dev/ttyUSB0")
        form.addRow("Serial Port:", self.serial_port)

        self.baud_rate = QComboBox()
        self.baud_rate.addItems(["9600", "19200", "38400", "57600", "115200", "230400"])
        form.addRow("Baud Rate:", self.baud_rate)

        baud_warn = QLabel("⚠ Must match Raspberry Pi baud rate")
        baud_warn.setStyleSheet("color: #d97706; font-size: 10px;")
        form.addRow("", baud_warn)

        self.serial_timeout = QDoubleSpinBox()
        self.serial_timeout.setRange(0.1, 10.0)
        self.serial_timeout.setSingleStep(0.1)
        self.serial_timeout.setSuffix(" s")
        form.addRow("Timeout:", self.serial_timeout)
        return grp

    def _group_network(self):
        grp = QGroupBox("NETWORK / TCP (ALTERNATIVE)")
        form = self._make_form(grp)

        self.use_tcp = QCheckBox("Use TCP socket instead of serial port")
        form.addRow(self.use_tcp)

        self.raspi_ip = QLineEdit()
        self.raspi_ip.setPlaceholderText("192.168.1.100")
        form.addRow("Drone IP Address:", self.raspi_ip)

        self.tcp_port = QSpinBox()
        self.tcp_port.setRange(1024, 65535)
        form.addRow("TCP Port:", self.tcp_port)
        return grp

    def _group_processing(self):
        grp = QGroupBox("PROCESSING PARAMETERS")
        form = self._make_form(grp)

        self.speed_of_sound = QDoubleSpinBox()
        self.speed_of_sound.setRange(300.0, 380.0)
        self.speed_of_sound.setSingleStep(0.1)
        self.speed_of_sound.setDecimals(1)
        self.speed_of_sound.setSuffix(" m/s")
        form.addRow("Speed of Sound:", self.speed_of_sound)

        self.cluster_eps = QDoubleSpinBox()
        self.cluster_eps.setRange(0.1, 20.0)
        self.cluster_eps.setSingleStep(0.1)
        self.cluster_eps.setDecimals(1)
        self.cluster_eps.setSuffix(" m")
        self.cluster_eps.setToolTip("Bucher-Misra cluster grouping threshold (CLUSTER_EPS)")
        form.addRow("Cluster EPS:", self.cluster_eps)
        return grp

    def _group_visualization(self):
        grp = QGroupBox("VISUALIZATION SETTINGS")
        form = self._make_form(grp)

        self.update_interval = QDoubleSpinBox()
        self.update_interval.setRange(0.033, 2.0)
        self.update_interval.setSingleStep(0.033)
        self.update_interval.setDecimals(3)
        self.update_interval.setSuffix(" s")
        form.addRow("Update Interval:", self.update_interval)

        self.plot_buffer_size = QSpinBox()
        self.plot_buffer_size.setRange(100, 20000)
        self.plot_buffer_size.setSingleStep(100)
        form.addRow("Plot Buffer Size:", self.plot_buffer_size)
        return grp

    def _group_mic_positions(self):
        grp = QGroupBox("MICROPHONE POSITIONS  (3D coordinates in meters)")
        outer = QVBoxLayout(grp)
        outer.setContentsMargins(10, 8, 10, 10)
        outer.setSpacing(6)

        header = QGridLayout()
        header.setSpacing(4)
        for col_idx, text in enumerate(["", "X (m)", "Y (m)", "Z (m)"]):
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size:10px; font-weight:bold; color:#475569;")
            header.addWidget(lbl, 0, col_idx)
        outer.addLayout(header)

        grid = QGridLayout()
        grid.setSpacing(4)
        for row, mic_key in enumerate(f"mic{i}" for i in range(6)):
            lbl = QLabel(mic_key)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet("font-size:11px; font-weight:bold; color:#2563eb; min-width:36px;")
            grid.addWidget(lbl, row, 0)

            for col_idx, axis in enumerate(["x", "y", "z"]):
                sb = QDoubleSpinBox()
                sb.setRange(-20.0, 20.0)
                sb.setSingleStep(0.01)
                sb.setDecimals(3)
                sb.setSuffix(" m")
                sb.setToolTip(f"{mic_key} {axis.upper()} position")
                grid.addWidget(sb, row, col_idx + 1)
                self._mic_spinboxes[f"{mic_key}_{axis}"] = sb

        outer.addLayout(grid)

        reset_mic_btn = QPushButton("Reset Mic Positions to Default")
        reset_mic_btn.setObjectName("btnReset")
        reset_mic_btn.clicked.connect(self._reset_mic_positions)
        outer.addWidget(reset_mic_btn)
        return grp

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

    # ── Data ────────────────────────────────────────────────────────────

    def set_config(self, cfg: dict):
        """Populate UI from a config dictionary (e.g. from REST API)."""
        # Merge with defaults to ensure all keys exist
        merged = dict(self._DEFAULTS)
        merged["mic_positions"] = {k: dict(v) for k, v in _DEFAULT_MIC_POSITIONS.items()}
        merged.update(cfg)
        
        # Handle backend's potential legacy key (if needed)
        if "update_interval_ms" in merged and "update_interval_s" not in merged:
            merged["update_interval_s"] = merged.pop("update_interval_ms") / 1000.0

        self.current_config = merged
        c = self.current_config

        self.serial_port.setText(c.get("serial_port", "COM3"))
        self.baud_rate.setCurrentText(str(c.get("baud_rate", 230400)))
        self.serial_timeout.setValue(c.get("serial_timeout", 1.0))
        self.use_tcp.setChecked(c.get("use_tcp", False))
        self.raspi_ip.setText(c.get("raspi_ip", "192.168.1.100"))
        self.tcp_port.setValue(c.get("tcp_port", 5000))
        self.speed_of_sound.setValue(c.get("speed_of_sound", 343.0))
        self.cluster_eps.setValue(c.get("cluster_eps", 1.0))
        self.update_interval.setValue(c.get("update_interval_s", 0.1))
        self.plot_buffer_size.setValue(c.get("plot_buffer_size", 1000))
        self._populate_mic_positions(c.get("mic_positions", _DEFAULT_MIC_POSITIONS))

    def _populate_mic_positions(self, positions: dict):
        for mic_key, coords in positions.items():
            for axis in ("x", "y", "z"):
                sb_key = f"{mic_key}_{axis}"
                if sb_key in self._mic_spinboxes:
                    self._mic_spinboxes[sb_key].setValue(coords.get(axis, 0.0))

    def _get_values_from_ui(self) -> dict:
        return {
            "serial_port":       self.serial_port.text(),
            "baud_rate":         int(self.baud_rate.currentText()),
            "serial_timeout":    self.serial_timeout.value(),
            "use_tcp":           self.use_tcp.isChecked(),
            "raspi_ip":          self.raspi_ip.text(),
            "tcp_port":          self.tcp_port.value(),
            "speed_of_sound":    self.speed_of_sound.value(),
            "cluster_eps":       self.cluster_eps.value(),
            "update_interval_s": self.update_interval.value(),
            "plot_buffer_size":  self.plot_buffer_size.value(),
            "mic_positions":     self._get_mic_positions_from_ui(),
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

    # ── Slots ────────────────────────────────────────────────────────────

    def _save(self):
        cfg = self._get_values_from_ui()
        # Immediately save it locally as UI state pending server confirmation
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
