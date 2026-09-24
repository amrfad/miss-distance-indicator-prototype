# darat/ui/config_raspi.py
"""Raspberry Pi configuration panel — Blender/Unity property inspector style vertical layout."""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QLineEdit, QComboBox,
    QStackedWidget, QListWidget, QSpinBox, QDoubleSpinBox,
    QPushButton, QCheckBox, QMessageBox, QLabel, QScrollArea, QFrame,
)
from PySide6.QtCore import Signal, Qt

from .widgets.filter_config_panel import FilterConfigPanel
from .widgets.collapsible_section import CollapsibleSection

_LABEL_W = 150

_RESTART_REQUIRED = {
    "operation_mode", "serial_port", "baud_rate", "serial_timeout", "arecord_device",
    "sample_rate", "active_profile", "num_mics_h8", "base_output_dir",
    "tdoa_method", "drone_rpm", "env_smooth_ms", "env_decimation", "do_closure_tuning",
    "arecord_terminate_timeout",
    "events_csv", "events_json", "tdoa_json",
    "chunk_duration_sec", "chunk_overlap_sec",
}


def _lbl(text: str, restart: bool = False, tooltip: str = "") -> QLabel:
    """Label field netral dengan fixed width ~150px dan alignment kanan."""
    lbl = QLabel(text)
    lbl.setObjectName("formLabel")
    lbl.setFixedWidth(_LABEL_W)
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    if restart:
        lbl.setToolTip("Requires drone restart to take effect")
    if tooltip:
        lbl.setToolTip(tooltip)
    return lbl


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


class RaspiConfigPanel(QWidget):
    """Configuration panel for the Drone (Raspberry Pi) — Vertical sidebar & Collapsible sections."""

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
        "tdoa_method": "eccct",
        "drone_rpm": 4000.0,
        "env_smooth_ms": 2.0,
        "env_decimation": 10,
        "do_closure_tuning": True,
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
        "chunk_duration_sec": 5.0,
        "chunk_overlap_sec": 1.0,
        "keep_audio_files": True,
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
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # 1. Restart banner
        self._restart_banner = self._build_restart_banner()
        root.addWidget(self._restart_banner)

        # 3. Main body with QScrollArea wrapping vertical sidebar + stacked widget
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
        self._sidebar_list.addItems(["General", "Audio", "Detection", "Filter", "Timing"])
        self._sidebar_list.setCurrentRow(0)

        # Stacked widget for category pages
        self._stacked_widget = QStackedWidget()
        self._stacked_widget.addWidget(_make_page(self._group_operation(), self._group_output_files()))
        self._stacked_widget.addWidget(_make_page(self._group_audio(), self._group_streaming()))
        self._stacked_widget.addWidget(_make_page(self._group_tdoa(), self._group_detection()))
        self._stacked_widget.addWidget(_make_page(self._group_filter_method()))
        self._stacked_widget.addWidget(_make_page(self._group_timing()))

        self._sidebar_list.currentRowChanged.connect(self._stacked_widget.setCurrentIndex)

        body_layout.addWidget(self._sidebar_list, stretch=0)
        body_layout.addWidget(self._stacked_widget, stretch=1)

        scroll.setWidget(inner)
        root.addWidget(scroll, stretch=1)

        # 4. Sticky action buttons
        action_bar = QWidget()
        action_layout = QHBoxLayout(action_bar)
        action_layout.setContentsMargins(8, 4, 8, 8)
        action_layout.addLayout(self._action_buttons())
        root.addWidget(action_bar, stretch=0)

    def _build_restart_banner(self) -> QFrame:
        banner = QFrame()
        banner.setObjectName("cardAccent")
        banner.setStyleSheet(
            "QFrame#cardAccent { background-color: #fff7ed; border: 1px solid #f97316; border-radius: 4px; }"
        )
        layout = QHBoxLayout(banner)
        layout.setContentsMargins(12, 8, 12, 8)

        self._restart_msg = QLabel("Some parameters require a drone restart to take effect.")
        self._restart_msg.setStyleSheet("color:#9a3412; font-size:11px; font-weight:600;")
        self._restart_msg.setWordWrap(True)
        layout.addWidget(self._restart_msg, stretch=1)

        self._restart_btn = QPushButton("RESTART")
        self._restart_btn.setObjectName("btnReset")
        self._restart_btn.setFixedWidth(140)
        self._restart_btn.clicked.connect(self._request_restart)
        layout.addWidget(self._restart_btn)

        banner.setVisible(False)
        return banner

    def _group_operation(self) -> CollapsibleSection:
        sec = CollapsibleSection("OPERATION MODE")

        self.operation_mode = QComboBox()
        self.operation_mode.addItems(["OFFLINE", "ONLINE"])
        sec.add_row(_lbl("Operation Mode:", restart=True), self.operation_mode)

        self.active_profile = QComboBox()
        self.active_profile.addItems(["H8", "H6E"])
        sec.add_row(_lbl("Device Profile:", restart=True), self.active_profile)

        self.base_output_dir = QLineEdit()
        self.base_output_dir.setPlaceholderText("drone_recordings")
        sec.add_row(_lbl("Output Directory:", restart=True), self.base_output_dir)

        return sec

    def _group_output_files(self) -> CollapsibleSection:
        sec = CollapsibleSection("SERIAL && OUTPUT FILES")

        self.serial_port = QLineEdit()
        self.serial_port.setPlaceholderText("/dev/ttyUSB0")
        sec.add_row(_lbl("Serial Port:", restart=True), self.serial_port)

        self.baud_rate = QComboBox()
        self.baud_rate.setObjectName("monoField")
        self.baud_rate.addItems(["9600", "19200", "38400", "57600", "115200", "230400"])
        sec.add_row(_lbl("Baud Rate:", restart=True), self.baud_rate)

        self.serial_timeout = QDoubleSpinBox()
        self.serial_timeout.setObjectName("monoField")
        self.serial_timeout.setRange(1.0, 30.0)
        self.serial_timeout.setSuffix(" s")
        sec.add_row(_lbl("Serial Timeout:", restart=True), self.serial_timeout)

        self.events_csv = QLineEdit()
        self.events_csv.setPlaceholderText("detected_events.csv")
        sec.add_row(_lbl("Events CSV:", restart=True), self.events_csv)

        self.events_json = QLineEdit()
        self.events_json.setPlaceholderText("session_events.json")
        sec.add_row(_lbl("Events JSON:", restart=True), self.events_json)

        self.tdoa_json = QLineEdit()
        self.tdoa_json.setPlaceholderText("session_tdoa.json")
        sec.add_row(_lbl("TDOA JSON:", restart=True), self.tdoa_json)

        return sec

    def _group_audio(self) -> CollapsibleSection:
        sec = CollapsibleSection("AUDIO CONFIGURATION")

        self.sample_rate = QComboBox()
        self.sample_rate.setObjectName("monoField")
        self.sample_rate.addItems(["44100", "48000", "96000"])
        sec.add_row(_lbl("Sample Rate (Hz):", restart=True), self.sample_rate)

        self.num_mics_h8 = QSpinBox()
        self.num_mics_h8.setObjectName("monoField")
        self.num_mics_h8.setRange(4, 6)
        self.num_mics_h8.setSingleStep(2)
        sec.add_row(_lbl("Mic Count:", restart=True), self.num_mics_h8)

        self.arecord_device = QLineEdit()
        self.arecord_device.setPlaceholderText("hw:2,0")
        sec.add_row(_lbl("Audio Device:", restart=True), self.arecord_device)

        self.arecord_terminate_timeout = QDoubleSpinBox()
        self.arecord_terminate_timeout.setObjectName("monoField")
        self.arecord_terminate_timeout.setRange(1.0, 30.0)
        self.arecord_terminate_timeout.setSingleStep(0.5)
        self.arecord_terminate_timeout.setSuffix(" s")
        sec.add_row(_lbl("Terminate Timeout:", restart=True), self.arecord_terminate_timeout)

        return sec

    def _group_streaming(self) -> CollapsibleSection:
        sec = CollapsibleSection("STREAMING && CHUNKING")

        self.chunk_duration_sec = QDoubleSpinBox()
        self.chunk_duration_sec.setObjectName("monoField")
        self.chunk_duration_sec.setRange(1.0, 60.0)
        self.chunk_duration_sec.setSingleStep(0.5)
        self.chunk_duration_sec.setDecimals(1)
        self.chunk_duration_sec.setSuffix(" s")
        sec.add_row(_lbl("Chunk Duration:", restart=True), self.chunk_duration_sec)

        self.chunk_overlap_sec = QDoubleSpinBox()
        self.chunk_overlap_sec.setObjectName("monoField")
        self.chunk_overlap_sec.setRange(0.0, 10.0)
        self.chunk_overlap_sec.setSingleStep(0.25)
        self.chunk_overlap_sec.setDecimals(2)
        self.chunk_overlap_sec.setSuffix(" s")
        sec.add_row(_lbl("Chunk Overlap:", restart=True), self.chunk_overlap_sec)

        self.keep_audio_files = QCheckBox("Keep WAV chunk files on drone")
        sec.add_row(_lbl("Keep Audio:"), self.keep_audio_files)

        return sec

    def _group_tdoa(self) -> CollapsibleSection:
        sec = CollapsibleSection("TDOA ESTIMATION CONFIGURATION")

        self.tdoa_method = QComboBox()
        self.tdoa_method.setObjectName("monoField")
        self.tdoa_method.addItem("ECCCT (Supersonic Envelope)", "eccct")
        self.tdoa_method.addItem("GCC-PHAT (Classic)", "gcc_phat")
        self.tdoa_method.addItem("Cross-Correlation (Standard)", "cross_correlation")
        sec.add_row(_lbl("TDOA Method:", restart=True), self.tdoa_method)

        # ── Parameter Khusus ECCCT (hanya muncul saat ECCCT dipilih) ──
        self._eccct_container = QWidget()
        eccct_layout = QFormLayout(self._eccct_container)
        eccct_layout.setContentsMargins(0, 0, 0, 0)
        eccct_layout.setSpacing(8)
        eccct_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        eccct_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.drone_rpm = QDoubleSpinBox()
        self.drone_rpm.setObjectName("monoField")
        self.drone_rpm.setRange(0.0, 15000.0)
        self.drone_rpm.setSingleStep(100.0)
        self.drone_rpm.setSuffix(" RPM")
        eccct_layout.addRow(_lbl("Drone RPM:", restart=True, tooltip="Perkiraan RPM mesin drone untuk filter comb-notch"), self.drone_rpm)

        self.env_smooth_ms = QDoubleSpinBox()
        self.env_smooth_ms.setObjectName("monoField")
        self.env_smooth_ms.setRange(0.5, 20.0)
        self.env_smooth_ms.setSingleStep(0.5)
        self.env_smooth_ms.setSuffix(" ms")
        eccct_layout.addRow(_lbl("Envelope Smooth:", restart=True, tooltip="Lebar smoothing boxcar power envelope"), self.env_smooth_ms)

        self.env_decimation = QSpinBox()
        self.env_decimation.setObjectName("monoField")
        self.env_decimation.setRange(1, 40)
        self.env_decimation.setSingleStep(1)
        self.env_decimation.setSuffix(" x")
        eccct_layout.addRow(_lbl("Decimation:", restart=True, tooltip="Faktor desimasi kurva envelope (contoh: 10x: 48kHz -> 4.8kHz)"), self.env_decimation)

        self.do_closure_tuning = QCheckBox("Enforce geometric closure consistency (Gauss-Seidel)")
        eccct_layout.addRow(_lbl("Closure Tuning:", restart=True), self.do_closure_tuning)

        sec.add_widget(self._eccct_container)

        # ── Parameter Khusus GCC-PHAT (hanya muncul saat GCC-PHAT dipilih) ──
        self._gcc_container = QWidget()
        gcc_layout = QFormLayout(self._gcc_container)
        gcc_layout.setContentsMargins(0, 0, 0, 0)
        gcc_layout.setSpacing(8)
        gcc_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        gcc_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        self.hop_length = QSpinBox()
        self.hop_length.setObjectName("monoField")
        self.hop_length.setRange(64, 4096)
        self.hop_length.setSingleStep(64)
        gcc_layout.addRow(_lbl("Hop Length:"), self.hop_length)

        self.frame_length = QSpinBox()
        self.frame_length.setObjectName("monoField")
        self.frame_length.setRange(128, 8192)
        self.frame_length.setSingleStep(128)
        gcc_layout.addRow(_lbl("Frame Length:"), self.frame_length)

        sec.add_widget(self._gcc_container)

        # Hubungkan dynamic visibility saat pilihan TDOA berubah
        self.tdoa_method.currentIndexChanged.connect(self._on_tdoa_method_changed)
        self._on_tdoa_method_changed()

        return sec

    def _on_tdoa_method_changed(self):
        method = self.tdoa_method.currentData()
        self._eccct_container.setVisible(method == "eccct")
        self._gcc_container.setVisible(method == "gcc_phat")

    def _group_detection(self) -> CollapsibleSection:
        sec = CollapsibleSection("EVENT DETECTION")

        self.detect_ratio = QDoubleSpinBox()
        self.detect_ratio.setObjectName("monoField")
        self.detect_ratio.setRange(0.01, 1.0)
        self.detect_ratio.setSingleStep(0.01)
        self.detect_ratio.setDecimals(2)
        sec.add_row(_lbl("Detect Ratio:"), self.detect_ratio)

        self.filter_ratio = QDoubleSpinBox()
        self.filter_ratio.setObjectName("monoField")
        self.filter_ratio.setRange(0.01, 1.0)
        self.filter_ratio.setSingleStep(0.01)
        self.filter_ratio.setDecimals(2)
        sec.add_row(_lbl("Filter Ratio:"), self.filter_ratio)

        self.min_duration = QDoubleSpinBox()
        self.min_duration.setObjectName("monoField")
        self.min_duration.setRange(0.01, 5.0)
        self.min_duration.setSingleStep(0.05)
        self.min_duration.setDecimals(2)
        self.min_duration.setSuffix(" s")
        sec.add_row(_lbl("Min Duration:"), self.min_duration)

        self.max_gap = QDoubleSpinBox()
        self.max_gap.setObjectName("monoField")
        self.max_gap.setRange(0.01, 5.0)
        self.max_gap.setSingleStep(0.01)
        self.max_gap.setDecimals(2)
        self.max_gap.setSuffix(" s")
        sec.add_row(_lbl("Max Gap:"), self.max_gap)

        self.ignore_time = QDoubleSpinBox()
        self.ignore_time.setObjectName("monoField")
        self.ignore_time.setRange(0.0, 10.0)
        self.ignore_time.setSingleStep(0.1)
        self.ignore_time.setDecimals(1)
        self.ignore_time.setSuffix(" s")
        sec.add_row(_lbl("Ignore Time:"), self.ignore_time)

        return sec

    def _group_filter_method(self) -> CollapsibleSection:
        sec = CollapsibleSection("FILTER METHOD")

        info = QLabel(
            "Pilih metode noise reduction. Parameter diadaptasi secara dinamis "
            "dari skema yang dikirim drone via API."
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 11px; color: #64748b; padding-bottom: 4px;")
        sec.add_widget(info)

        self.filter_panel = FilterConfigPanel()
        self.filter_panel.filter_changed.connect(self._on_filter_changed)
        sec.add_widget(self.filter_panel)

        return sec

    def _on_filter_changed(self, method_key: str, params: dict):
        """Dipanggil saat user mengubah metode atau parameter filter."""
        pass

    def update_filter_schemas(self, schemas: dict):
        """
        Update dropdown dan form berdasarkan skema yang diterima dari drone.
        Dipanggil dari ConfigPage setelah REST call GET /filter-schemas berhasil.
        """
        if hasattr(self, 'filter_panel'):
            self.filter_panel.update_schemas(schemas)

    def _group_timing(self) -> CollapsibleSection:
        sec = CollapsibleSection("TIMING / DELAYS")

        self.event_padding = QDoubleSpinBox()
        self.event_padding.setObjectName("monoField")
        self.event_padding.setRange(0.0, 2.0)
        self.event_padding.setSingleStep(0.1)
        self.event_padding.setDecimals(2)
        self.event_padding.setSuffix(" s")
        sec.add_row(_lbl("Event Padding:"), self.event_padding)

        self.post_recording_delay = QDoubleSpinBox()
        self.post_recording_delay.setObjectName("monoField")
        self.post_recording_delay.setRange(0.0, 10.0)
        self.post_recording_delay.setSingleStep(0.1)
        self.post_recording_delay.setDecimals(1)
        self.post_recording_delay.setSuffix(" s")
        sec.add_row(_lbl("Post-Rec Delay:"), self.post_recording_delay)

        self.main_loop_delay = QDoubleSpinBox()
        self.main_loop_delay.setObjectName("monoField")
        self.main_loop_delay.setRange(0.01, 5.0)
        self.main_loop_delay.setSingleStep(0.05)
        self.main_loop_delay.setDecimals(2)
        self.main_loop_delay.setSuffix(" s")
        sec.add_row(_lbl("Main Loop Delay:"), self.main_loop_delay)

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

    # ── Data methods ──────────────────────────────────────────────────────
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

        # TDOA settings
        t_method = c.get("tdoa_method", "eccct")
        idx = self.tdoa_method.findData(t_method)
        if idx >= 0:
            self.tdoa_method.setCurrentIndex(idx)
        else:
            self.tdoa_method.setCurrentIndex(0)

        self.drone_rpm.setValue(float(c.get("drone_rpm", 4000.0)))
        self.env_smooth_ms.setValue(float(c.get("env_smooth_ms", 2.0)))
        self.env_decimation.setValue(int(c.get("env_decimation", 10)))
        self.do_closure_tuning.setChecked(bool(c.get("do_closure_tuning", True)))
        self._on_tdoa_method_changed()

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
        self.hop_length.setValue(c.get("hop_length", 512))
        self.frame_length.setValue(c.get("frame_length", 1024))
        self.post_recording_delay.setValue(c.get("post_recording_delay", 0.5))
        self.main_loop_delay.setValue(c.get("main_loop_delay", 0.1))
        self.chunk_duration_sec.setValue(c.get("chunk_duration_sec", 5.0))
        self.chunk_overlap_sec.setValue(c.get("chunk_overlap_sec", 1.0))
        self.keep_audio_files.setChecked(c.get("keep_audio_files", True))

        method = c.get("filter_method", "spectral_gating")
        filter_configs = c.get("filter_configs", {})
        method_params = filter_configs.get(method, {}) if isinstance(filter_configs, dict) else {}
        if hasattr(self, 'filter_panel'):
            self.filter_panel.set_config(method, method_params)

        self._restart_banner.setVisible(False)

    def _get_values_from_ui(self) -> dict:
        chosen_tdoa_method = self.tdoa_method.currentData()
        base = {
            "operation_mode": self.operation_mode.currentText(),
            "active_profile": self.active_profile.currentText(),
            "base_output_dir": self.base_output_dir.text(),
            "sample_rate": int(self.sample_rate.currentText()),
            "num_mics_h8": self.num_mics_h8.value(),
            "arecord_device": self.arecord_device.text(),
            "arecord_terminate_timeout": self.arecord_terminate_timeout.value(),
            "tdoa_method": chosen_tdoa_method,
            "drone_rpm": self.drone_rpm.value(),
            "env_smooth_ms": self.env_smooth_ms.value(),
            "env_decimation": self.env_decimation.value(),
            "do_closure_tuning": self.do_closure_tuning.isChecked(),
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
            "hop_length": self.hop_length.value(),
            "frame_length": self.frame_length.value(),
            "post_recording_delay": self.post_recording_delay.value(),
            "main_loop_delay": self.main_loop_delay.value(),
            "chunk_duration_sec": self.chunk_duration_sec.value(),
            "chunk_overlap_sec": self.chunk_overlap_sec.value(),
            "keep_audio_files": self.keep_audio_files.isChecked(),
        }
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
        if cfg["chunk_duration_sec"] <= cfg["chunk_overlap_sec"]:
            return "chunk_duration_sec must be > chunk_overlap_sec"
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
                "baud_rate changed on drone.\nMake sure Ground Station baud_rate matches!"
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
            self._restart_msg.setText(f"Restart required: {names}")
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