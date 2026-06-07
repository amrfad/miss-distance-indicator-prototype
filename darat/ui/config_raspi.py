# darat/ui/config_raspi.py
"""Raspberry Pi configuration panel — Multi-column layout (2 columns)."""

from PySide6.QtWidgets import (
    QWidget, QGroupBox, QGridLayout, QVBoxLayout,
    QHBoxLayout, QLineEdit, QComboBox,
    QSpinBox, QDoubleSpinBox, QPushButton,
    QCheckBox, QMessageBox, QLabel,
    QScrollArea, QFrame,
)
from PySide6.QtCore import Signal, Qt

from .widgets.filter_config_panel import FilterConfigPanel

_LABEL_W = 140
_COLUMN_SPACING = 20

_RESTART_REQUIRED = {
    "operation_mode", "serial_port", "baud_rate", "serial_timeout", "arecord_device",
    "sample_rate", "active_profile", "num_mics_h8", "base_output_dir",
    "is_gcc_phat", "arecord_terminate_timeout",
    "events_csv", "events_json", "tdoa_json",
}


def _lbl(text: str, restart: bool = False, tooltip: str = "") -> QLabel:
    display = f"{text} ⚠" if restart else text
    lbl = QLabel(display)
    lbl.setFixedWidth(_LABEL_W)
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if restart:
        lbl.setToolTip("⚠ Requires drone restart to take effect")
        lbl.setStyleSheet("color: #d97706;")
    if tooltip:
        lbl.setToolTip(tooltip)
    return lbl


class RaspiConfigPanel(QWidget):
    """Configuration panel for the Drone (Raspberry Pi) — 2 column layout."""

    config_save_requested = Signal(dict)
    config_reset_requested = Signal()
    restart_drone_requested = Signal()

    _DEFAULTS = {
        "operation_mode": "OFFLINE",
        "serial_port": "/dev/ttyUSB0",
        "baud_rate": 230400,
        "serial_timeout": 5.0,
        "arecord_device": "hw:2,0",
        "sample_rate": 48000,
        "active_profile": "H8",
        "num_mics_h8": 6,
        "base_output_dir": "drone_recordings",
        "is_gcc_phat": True,
        "arecord_terminate_timeout": 3.0,
        "events_csv": "detected_events.csv",
        "events_json": "session_events.json",
        "tdoa_json": "session_tdoa.json",
        "min_duration": 0.25,
        "max_gap": 0.1,
        "detect_ratio": 0.20,
        "filter_ratio": 0.40,
        "ignore_time": 0.5,
        "prop_decrease": 1.0,
        "stationary": False,
        "normalize": False,
        "freq_mask_smooth_hz": 100,
        "time_mask_smooth_ms": 10,
        "hop_length": 512,
        "frame_length": 1024,
        "normalization_percentile": 99.9,
        "event_padding_sec": 0.3,
        "post_recording_delay": 0.5,
        "main_loop_delay": 0.1,
        # Filter Strategy Pattern
        "filter_method": "spectral_gating",
        "filter_configs": {},
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_config = dict(self._DEFAULTS)
        self._pending_restart_params: list[str] = []
        self._build_ui()
        self.set_config(self.current_config)

    def _build_ui(self):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        outer = QVBoxLayout(inner)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(10)

        # Restart banner
        self._restart_banner = self._build_restart_banner()
        outer.addWidget(self._restart_banner)

        # Legend
        legend = QLabel(
            "⚠ = Requires restart  ·  "
            "<span style='color:#16a34a'>🔄 Runtime (live)</span>"
        )
        legend.setTextFormat(Qt.TextFormat.RichText)
        legend.setStyleSheet("font-size:10px; color:#64748b; padding:2px 4px;")
        outer.addWidget(legend)

        # === 2 COLUMN LAYOUT ===
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(_COLUMN_SPACING)

        # Column 1
        col1 = QVBoxLayout()
        col1.setSpacing(10)
        col1.addWidget(self._group_operation())
        col1.addWidget(self._group_audio())
        col1.addWidget(self._group_tdoa())
        col1.addWidget(self._group_output_files())
        col1.addStretch()

        # Column 2
        col2 = QVBoxLayout()
        col2.setSpacing(10)
        col2.addWidget(self._group_detection())
        col2.addWidget(self._group_noise_reduction())
        col2.addWidget(self._group_filter_method())
        col2.addWidget(self._group_timing())
        col2.addStretch()

        columns_layout.addLayout(col1, stretch=1)
        columns_layout.addLayout(col2, stretch=1)

        outer.addLayout(columns_layout)
        outer.addLayout(self._action_buttons())
        outer.addStretch()

        scroll.setWidget(inner)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(scroll)

    def _build_restart_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("cardAccent")
        banner.setStyleSheet(
            "QFrame#cardAccent { background-color: #fff7ed; border: 1px solid #f97316; border-radius: 6px; }"
        )
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(12, 8, 12, 8)

        icon = QLabel("⚠")
        icon.setStyleSheet("font-size:16px; color:#d97706;")
        layout.addWidget(icon)

        self._restart_msg = QLabel("Some parameters require a drone restart to take effect.")
        self._restart_msg.setStyleSheet("color:#9a3412; font-size:11px;")
        self._restart_msg.setWordWrap(True)
        layout.addWidget(self._restart_msg, stretch=1)

        self._restart_btn = QPushButton("RESTART")
        self._restart_btn.setObjectName("btnReset")
        self._restart_btn.setFixedWidth(140)
        self._restart_btn.clicked.connect(self._request_restart)
        layout.addWidget(self._restart_btn)

        banner.setVisible(False)
        return banner

    def _group_operation(self):
        grp = QGroupBox("🔒 OPERATION MODE")
        g = QGridLayout(grp)
        g.setSpacing(8)
        g.setContentsMargins(12, 12, 12, 12)

        self.operation_mode = QComboBox()
        self.operation_mode.addItems(["OFFLINE", "ONLINE"])
        g.addWidget(_lbl("Operation Mode:", restart=True), 0, 0)
        g.addWidget(self.operation_mode, 0, 1)

        self.active_profile = QComboBox()
        self.active_profile.addItems(["H8", "H6E"])
        g.addWidget(_lbl("Device Profile:", restart=True), 1, 0)
        g.addWidget(self.active_profile, 1, 1)

        self.base_output_dir = QLineEdit()
        self.base_output_dir.setPlaceholderText("drone_recordings")
        g.addWidget(_lbl("Output Directory:", restart=True), 2, 0)
        g.addWidget(self.base_output_dir, 2, 1)

        return grp

    def _group_audio(self):
        grp = QGroupBox("🔒 AUDIO CONFIGURATION")
        g = QGridLayout(grp)
        g.setSpacing(8)
        g.setContentsMargins(12, 12, 12, 12)

        self.sample_rate = QComboBox()
        self.sample_rate.addItems(["44100", "48000", "96000"])
        g.addWidget(_lbl("Sample Rate (Hz):", restart=True), 0, 0)
        g.addWidget(self.sample_rate, 0, 1)

        self.num_mics_h8 = QSpinBox()
        self.num_mics_h8.setRange(4, 6)
        self.num_mics_h8.setSingleStep(2)
        g.addWidget(_lbl("Mic Count:", restart=True), 1, 0)
        g.addWidget(self.num_mics_h8, 1, 1)

        self.arecord_device = QLineEdit()
        self.arecord_device.setPlaceholderText("hw:2,0")
        g.addWidget(_lbl("Audio Device:", restart=True), 2, 0)
        g.addWidget(self.arecord_device, 2, 1)

        self.arecord_terminate_timeout = QDoubleSpinBox()
        self.arecord_terminate_timeout.setRange(1.0, 30.0)
        self.arecord_terminate_timeout.setSingleStep(0.5)
        self.arecord_terminate_timeout.setSuffix(" s")
        g.addWidget(_lbl("Terminate Timeout:", restart=True), 3, 0)
        g.addWidget(self.arecord_terminate_timeout, 3, 1)

        return grp

    def _group_detection(self):
        grp = QGroupBox("🔄 EVENT DETECTION")
        g = QGridLayout(grp)
        g.setSpacing(8)
        g.setContentsMargins(12, 12, 12, 12)

        self.detect_ratio = QDoubleSpinBox()
        self.detect_ratio.setRange(0.01, 1.0)
        self.detect_ratio.setSingleStep(0.01)
        self.detect_ratio.setDecimals(2)
        g.addWidget(_lbl("Detect Ratio:"), 0, 0)
        g.addWidget(self.detect_ratio, 0, 1)

        self.filter_ratio = QDoubleSpinBox()
        self.filter_ratio.setRange(0.01, 1.0)
        self.filter_ratio.setSingleStep(0.01)
        self.filter_ratio.setDecimals(2)
        g.addWidget(_lbl("Filter Ratio:"), 1, 0)
        g.addWidget(self.filter_ratio, 1, 1)

        self.min_duration = QDoubleSpinBox()
        self.min_duration.setRange(0.01, 5.0)
        self.min_duration.setSingleStep(0.05)
        self.min_duration.setDecimals(2)
        self.min_duration.setSuffix(" s")
        g.addWidget(_lbl("Min Duration:"), 2, 0)
        g.addWidget(self.min_duration, 2, 1)

        self.max_gap = QDoubleSpinBox()
        self.max_gap.setRange(0.01, 5.0)
        self.max_gap.setSingleStep(0.01)
        self.max_gap.setDecimals(2)
        self.max_gap.setSuffix(" s")
        g.addWidget(_lbl("Max Gap:"), 3, 0)
        g.addWidget(self.max_gap, 3, 1)

        self.ignore_time = QDoubleSpinBox()
        self.ignore_time.setRange(0.0, 10.0)
        self.ignore_time.setSingleStep(0.1)
        self.ignore_time.setDecimals(1)
        self.ignore_time.setSuffix(" s")
        g.addWidget(_lbl("Ignore Time:"), 4, 0)
        g.addWidget(self.ignore_time, 4, 1)

        return grp

    def _group_noise_reduction(self):
        grp = QGroupBox("🔄 NOISE REDUCTION")
        g = QGridLayout(grp)
        g.setSpacing(8)
        g.setContentsMargins(12, 12, 12, 12)

        self.prop_decrease = QDoubleSpinBox()
        self.prop_decrease.setRange(0.0, 1.0)
        self.prop_decrease.setSingleStep(0.1)
        self.prop_decrease.setDecimals(1)
        g.addWidget(_lbl("Prop. Decrease:"), 0, 0)
        g.addWidget(self.prop_decrease, 0, 1)

        self.normalization_percentile = QDoubleSpinBox()
        self.normalization_percentile.setRange(0.1, 100.0)
        self.normalization_percentile.setSingleStep(0.1)
        self.normalization_percentile.setDecimals(1)
        self.normalization_percentile.setSuffix(" %")
        g.addWidget(_lbl("Norm. Percentile:"), 1, 0)
        g.addWidget(self.normalization_percentile, 1, 1)

        self.stationary = QCheckBox("Stationary noise mode")
        g.addWidget(_lbl("Stationary:"), 2, 0)
        g.addWidget(self.stationary, 2, 1)

        self.normalize = QCheckBox("Normalize output audio")
        g.addWidget(_lbl("Normalize:"), 3, 0)
        g.addWidget(self.normalize, 3, 1)

        self.freq_mask_smooth_hz = QSpinBox()
        self.freq_mask_smooth_hz.setRange(10, 2000)
        self.freq_mask_smooth_hz.setSingleStep(10)
        self.freq_mask_smooth_hz.setSuffix(" Hz")
        g.addWidget(_lbl("Freq Mask Smooth:"), 4, 0)
        g.addWidget(self.freq_mask_smooth_hz, 4, 1)

        self.time_mask_smooth_ms = QSpinBox()
        self.time_mask_smooth_ms.setRange(1, 200)
        self.time_mask_smooth_ms.setSingleStep(5)
        self.time_mask_smooth_ms.setSuffix(" ms")
        g.addWidget(_lbl("Time Mask Smooth:"), 5, 0)
        g.addWidget(self.time_mask_smooth_ms, 5, 1)

        return grp

    def _group_filter_method(self):
        grp = QGroupBox("🔄 FILTER METHOD")
        g = QVBoxLayout(grp)
        g.setSpacing(8)
        g.setContentsMargins(12, 12, 12, 12)

        # Keterangan singkat
        info = QLabel(
            "Pilih metode noise reduction. Parameter diadaptasi secara dinamis "
            "dari skema yang dikirim drone via API."
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 10px; color: #64748b;")
        g.addWidget(info)

        self.filter_panel = FilterConfigPanel()
        self.filter_panel.filter_changed.connect(self._on_filter_changed)
        g.addWidget(self.filter_panel)

        return grp

    def _on_filter_changed(self, method_key: str, params: dict):
        """Dipanggil saat user mengubah metode atau parameter filter."""
        # Tidak langsung save; menunggu tombol SAVE CONFIG
        pass

    def update_filter_schemas(self, schemas: dict):
        """
        Update dropdown dan form berdasarkan skema yang diterima dari drone.
        Dipanggil dari ConfigPage setelah REST call GET /filter-schemas berhasil.
        """
        if hasattr(self, 'filter_panel'):
            self.filter_panel.update_schemas(schemas)

    def _group_tdoa(self):
        grp = QGroupBox("🔒 TDOA / GCC-PHAT")
        g = QGridLayout(grp)
        g.setSpacing(8)
        g.setContentsMargins(12, 12, 12, 12)

        self.is_gcc_phat = QCheckBox("Enable GCC-PHAT algorithm")
        g.addWidget(_lbl("GCC-PHAT:", restart=True), 0, 0)
        g.addWidget(self.is_gcc_phat, 0, 1)

        self.hop_length = QSpinBox()
        self.hop_length.setRange(64, 4096)
        self.hop_length.setSingleStep(64)
        g.addWidget(_lbl("Hop Length:"), 1, 0)
        g.addWidget(self.hop_length, 1, 1)

        self.frame_length = QSpinBox()
        self.frame_length.setRange(128, 8192)
        self.frame_length.setSingleStep(128)
        g.addWidget(_lbl("Frame Length:"), 2, 0)
        g.addWidget(self.frame_length, 2, 1)

        return grp

    def _group_timing(self):
        grp = QGroupBox("🔄 TIMING / DELAYS")
        g = QGridLayout(grp)
        g.setSpacing(8)
        g.setContentsMargins(12, 12, 12, 12)

        self.event_padding = QDoubleSpinBox()
        self.event_padding.setRange(0.0, 2.0)
        self.event_padding.setSingleStep(0.1)
        self.event_padding.setDecimals(2)
        self.event_padding.setSuffix(" s")
        g.addWidget(_lbl("Event Padding:"), 0, 0)
        g.addWidget(self.event_padding, 0, 1)

        self.post_recording_delay = QDoubleSpinBox()
        self.post_recording_delay.setRange(0.0, 10.0)
        self.post_recording_delay.setSingleStep(0.1)
        self.post_recording_delay.setDecimals(1)
        self.post_recording_delay.setSuffix(" s")
        g.addWidget(_lbl("Post-Rec Delay:"), 1, 0)
        g.addWidget(self.post_recording_delay, 1, 1)

        self.main_loop_delay = QDoubleSpinBox()
        self.main_loop_delay.setRange(0.01, 5.0)
        self.main_loop_delay.setSingleStep(0.05)
        self.main_loop_delay.setDecimals(2)
        self.main_loop_delay.setSuffix(" s")
        g.addWidget(_lbl("Main Loop Delay:"), 2, 0)
        g.addWidget(self.main_loop_delay, 2, 1)

        return grp

    def _group_output_files(self):
        grp = QGroupBox("🔒 SERIAL & OUTPUT FILES")
        g = QGridLayout(grp)
        g.setSpacing(8)
        g.setContentsMargins(12, 12, 12, 12)

        self.serial_port = QLineEdit()
        self.serial_port.setPlaceholderText("/dev/ttyUSB0")
        g.addWidget(_lbl("Serial Port:", restart=True), 0, 0)
        g.addWidget(self.serial_port, 0, 1)

        self.baud_rate = QComboBox()
        self.baud_rate.addItems(["9600", "19200", "38400", "57600", "115200", "230400"])
        g.addWidget(_lbl("Baud Rate:", restart=True), 1, 0)
        g.addWidget(self.baud_rate, 1, 1)

        self.serial_timeout = QDoubleSpinBox()
        self.serial_timeout.setRange(1.0, 30.0)
        self.serial_timeout.setSuffix(" s")
        g.addWidget(_lbl("Serial Timeout:", restart=True), 2, 0)
        g.addWidget(self.serial_timeout, 2, 1)

        self.events_csv = QLineEdit()
        self.events_csv.setPlaceholderText("detected_events.csv")
        g.addWidget(_lbl("Events CSV:", restart=True), 3, 0)
        g.addWidget(self.events_csv, 3, 1)

        self.events_json = QLineEdit()
        self.events_json.setPlaceholderText("session_events.json")
        g.addWidget(_lbl("Events JSON:", restart=True), 4, 0)
        g.addWidget(self.events_json, 4, 1)

        self.tdoa_json = QLineEdit()
        self.tdoa_json.setPlaceholderText("session_tdoa.json")
        g.addWidget(_lbl("TDOA JSON:", restart=True), 5, 0)
        g.addWidget(self.tdoa_json, 5, 1)

        return grp

    def _action_buttons(self):
        row = QHBoxLayout()
        row.setSpacing(8)
        save_btn = QPushButton("💾 SAVE CONFIG")
        save_btn.setObjectName("btnSave")
        save_btn.clicked.connect(self._save)
        row.addWidget(save_btn)

        reset_btn = QPushButton("↺ RESET DEFAULTS")
        reset_btn.setObjectName("btnReset")
        reset_btn.clicked.connect(self._reset)
        row.addWidget(reset_btn)
        row.addStretch()
        return row

    # ── Data methods (sama seperti sebelumnya, tidak berubah) ──
    def set_config(self, cfg: dict):
        merged = dict(self._DEFAULTS)
        merged.update(cfg)
        self.current_config = merged
        c = self.current_config

        self.operation_mode.setCurrentText(c.get("operation_mode", "OFFLINE"))
        self.active_profile.setCurrentText(c.get("active_profile", "H8"))
        self.base_output_dir.setText(c.get("base_output_dir", "drone_recordings"))
        self.sample_rate.setCurrentText(str(c.get("sample_rate", 48000)))
        self.num_mics_h8.setValue(c.get("num_mics_h8", 6))
        self.arecord_device.setText(c.get("arecord_device", "hw:2,0"))
        self.arecord_terminate_timeout.setValue(c.get("arecord_terminate_timeout", 3.0))
        self.is_gcc_phat.setChecked(c.get("is_gcc_phat", True))
        self.serial_port.setText(c.get("serial_port", "/dev/ttyUSB0"))
        self.baud_rate.setCurrentText(str(c.get("baud_rate", 230400)))
        self.serial_timeout.setValue(c.get("serial_timeout", 5.0))
        self.events_csv.setText(c.get("events_csv", "detected_events.csv"))
        self.events_json.setText(c.get("events_json", "session_events.json"))
        self.tdoa_json.setText(c.get("tdoa_json", "session_tdoa.json"))
        self.detect_ratio.setValue(c.get("detect_ratio", 0.20))
        self.filter_ratio.setValue(c.get("filter_ratio", 0.40))
        self.min_duration.setValue(c.get("min_duration", 0.25))
        self.max_gap.setValue(c.get("max_gap", 0.1))
        self.ignore_time.setValue(c.get("ignore_time", 0.5))
        self.event_padding.setValue(c.get("event_padding_sec", 0.3))
        self.prop_decrease.setValue(c.get("prop_decrease", 1.0))
        self.stationary.setChecked(c.get("stationary", False))
        self.normalize.setChecked(c.get("normalize", False))
        self.freq_mask_smooth_hz.setValue(c.get("freq_mask_smooth_hz", 100))
        self.time_mask_smooth_ms.setValue(c.get("time_mask_smooth_ms", 10))
        self.hop_length.setValue(c.get("hop_length", 512))
        self.frame_length.setValue(c.get("frame_length", 1024))
        self.normalization_percentile.setValue(c.get("normalization_percentile", 99.9))
        self.post_recording_delay.setValue(c.get("post_recording_delay", 0.5))
        self.main_loop_delay.setValue(c.get("main_loop_delay", 0.1))

        # Update filter panel
        method = c.get("filter_method", "spectral_gating")
        filter_configs = c.get("filter_configs", {})
        method_params = filter_configs.get(method, {}) if isinstance(filter_configs, dict) else {}
        if hasattr(self, 'filter_panel'):
            self.filter_panel.set_config(method, method_params)

        self._restart_banner.setVisible(False)

    def _get_values_from_ui(self) -> dict:
        base = {
            "operation_mode": self.operation_mode.currentText(),
            "active_profile": self.active_profile.currentText(),
            "base_output_dir": self.base_output_dir.text(),
            "sample_rate": int(self.sample_rate.currentText()),
            "num_mics_h8": self.num_mics_h8.value(),
            "arecord_device": self.arecord_device.text(),
            "arecord_terminate_timeout": self.arecord_terminate_timeout.value(),
            "is_gcc_phat": self.is_gcc_phat.isChecked(),
            "serial_port": self.serial_port.text(),
            "baud_rate": int(self.baud_rate.currentText()),
            "serial_timeout": self.serial_timeout.value(),
            "events_csv": self.events_csv.text(),
            "events_json": self.events_json.text(),
            "tdoa_json": self.tdoa_json.text(),
            "detect_ratio": self.detect_ratio.value(),
            "filter_ratio": self.filter_ratio.value(),
            "min_duration": self.min_duration.value(),
            "max_gap": self.max_gap.value(),
            "ignore_time": self.ignore_time.value(),
            "event_padding_sec": self.event_padding.value(),
            "prop_decrease": self.prop_decrease.value(),
            "stationary": self.stationary.isChecked(),
            "normalize": self.normalize.isChecked(),
            "freq_mask_smooth_hz": self.freq_mask_smooth_hz.value(),
            "time_mask_smooth_ms": self.time_mask_smooth_ms.value(),
            "hop_length": self.hop_length.value(),
            "frame_length": self.frame_length.value(),
            "normalization_percentile": self.normalization_percentile.value(),
            "post_recording_delay": self.post_recording_delay.value(),
            "main_loop_delay": self.main_loop_delay.value(),
        }
        # Tambahkan filter payload dari FilterConfigPanel
        if hasattr(self, 'filter_panel'):
            filter_payload = self.filter_panel.get_filter_config_payload()
            base.update(filter_payload)
        return base

    def get_runtime_config(self) -> dict:
        all_cfg = self._get_values_from_ui()
        return {k: v for k, v in all_cfg.items() if k not in _RESTART_REQUIRED}

    def _validate(self, cfg: dict) -> str | None:
        if cfg["filter_ratio"] < cfg["detect_ratio"]:
            return "filter_ratio must be ≥ detect_ratio"
        if cfg["frame_length"] < cfg["hop_length"]:
            return "frame_length must be ≥ hop_length"
        if cfg["min_duration"] <= 0:
            return "min_duration must be > 0"
        if cfg["max_gap"] <= 0:
            return "max_gap must be > 0"
        if cfg["num_mics_h8"] not in (4, 6):
            return "num_mics_h8 must be 4 or 6"
        return None

    def _save(self):
        cfg = self._get_values_from_ui()
        err = self._validate(cfg)
        if err:
            QMessageBox.warning(self, "Validation Error", err)
            return

        if cfg.get("baud_rate") != self.current_config.get("baud_rate"):
            QMessageBox.warning(
                self, "Baud Rate Changed",
                "⚠ baud_rate changed on drone.\nMake sure Ground Station baud_rate matches!"
            )

        restart_params = [
            k for k in _RESTART_REQUIRED
            if k in cfg and cfg[k] != self.current_config.get(k)
        ]

        self.current_config = cfg
        self.config_save_requested.emit(cfg)

        if restart_params:
            names = ", ".join(restart_params[:3])
            if len(restart_params) > 3:
                names += f" +{len(restart_params)-3} more"
            self._restart_msg.setText(f"⚠ Restart required: {names}")
            self._restart_banner.setVisible(True)
        else:
            self._restart_banner.setVisible(False)

    def _reset(self):
        reply = QMessageBox.question(
            self, "Reset to Defaults",
            "Reset all Raspberry Pi config to defaults via API?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.config_reset_requested.emit()

    def _request_restart(self):
        reply = QMessageBox.question(
            self, "Restart",
            "Send restart command ?\n\nThis will restart the Python process.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.restart_drone_requested.emit()
            self._restart_banner.setVisible(False)