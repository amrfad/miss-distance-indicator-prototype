# darat/ui/widgets/filter_config_panel.py
"""
Filter Config Panel — Dynamic Auto-Generated Form
Merender form parameter filter secara otomatis berdasarkan skema yang
diterima dari drone (via GET /filter-schemas) atau fallback ke schema lokal.

Widget ini:
  1. Menampilkan QComboBox untuk memilih metode filter
  2. Merender QFormLayout yang berisi widget per parameter berdasarkan tipe data:
       float  → QDoubleSpinBox
       int    → QSpinBox
       bool   → QCheckBox
       str    → QLineEdit
  3. Menyediakan get_values() yang mengembalikan dict siap kirim ke drone
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QDoubleSpinBox, QSpinBox, QCheckBox, QLineEdit,
    QLabel, QGroupBox, QScrollArea, QFrame, QPushButton,
)
from PySide6.QtCore import Signal, Qt

# ── Default schemas (fallback jika API belum tersedia) ─────────────────────
_FALLBACK_SCHEMAS = {
    "spectral_gating": {
        "display_name": "Spectral Gating (noisereduce)",
        "params": {
            "prop_decrease": {
                "value": 1.0, "type": "float", "min": 0.0, "max": 1.0, "step": 0.1,
                "description": "Noise reduction ratio (0.0 = none, 1.0 = maximum)",
            },
            "freq_mask_smooth_hz": {
                "value": 100, "type": "int", "min": 10, "max": 2000, "step": 10,
                "description": "Frequency domain smoothing (Hz)",
            },
            "time_mask_smooth_ms": {
                "value": 10, "type": "int", "min": 1, "max": 200, "step": 5,
                "description": "Time domain smoothing (ms)",
            },
            "stationary": {
                "value": False, "type": "bool",
                "description": "Use stationary noise model",
            },
            "normalize": {
                "value": False, "type": "bool",
                "description": "Normalize audio output",
            },
        },
    },
    "wavelet_denoising": {
        "display_name": "Wavelet Denoising (pywt)",
        "params": {
            "wavelet": {
                "value": "db8", "type": "str",
                "description": "Nama wavelet basis (db4, db8, sym8, coif5, dll)",
            },
            "level": {
                "value": 4, "type": "int", "min": 1, "max": 10, "step": 1,
                "description": "Jumlah level dekomposisi DWT",
            },
            "mode": {
                "value": "soft", "type": "str",
                "description": "Mode thresholding: 'soft' atau 'hard'",
            },
            "normalize": {
                "value": False, "type": "bool",
                "description": "Normalisasi output audio",
            },
        },
    },
    "wiener_stft": {
        "display_name": "Wiener STFT (scipy)",
        "params": {
            "n_fft": {
                "value": 1024, "type": "int", "min": 128, "max": 4096, "step": 128,
                "description": "Ukuran FFT window (samples)",
            },
            "hop_length": {
                "value": 256, "type": "int", "min": 64, "max": 1024, "step": 64,
                "description": "Jumlah sample antar frame STFT",
            },
            "noise_frames": {
                "value": 10, "type": "int", "min": 1, "max": 50, "step": 1,
                "description": "Jumlah frame awal untuk estimasi noise",
            },
            "alpha": {
                "value": 0.98, "type": "float", "min": 0.0, "max": 1.0, "step": 0.01,
                "description": "Smoothing factor PSD noise",
            },
            "normalize": {
                "value": False, "type": "bool",
                "description": "Normalisasi output audio",
            },
        },
    },
    "passthrough": {
        "display_name": "Passthrough (no filtering)",
        "params": {},
    },
    "comb_notch": {
        "display_name": "Comb-Notch & Wake Bandpass (Zero-Phase)",
        "params": {
            "rpm": {
                "value": 4000.0, "type": "float", "min": 0.0, "max": 15000.0, "step": 100.0,
                "description": "Putaran mesin drone (RPM) untuk estimasi frekuensi fundamental f0",
            },
            "notch_bw": {
                "value": 40.0, "type": "float", "min": 5.0, "max": 200.0, "step": 5.0,
                "description": "Lebar notch tiap harmonik mesin (Hz)",
            },
            "f_lo": {
                "value": 1500.0, "type": "float", "min": 100.0, "max": 10000.0, "step": 100.0,
                "description": "Frekuensi cut-off bawah bandpass (Hz)",
            },
            "f_hi": {
                "value": 6000.0, "type": "float", "min": 1000.0, "max": 24000.0, "step": 200.0,
                "description": "Frekuensi cut-off atas bandpass (Hz)",
            },
            "enable_bandpass": {
                "value": True, "type": "bool",
                "description": "Aktifkan ideal bandpass [f_lo, f_hi]",
            },
        },
    },
}


class FilterConfigPanel(QWidget):
    """
    Panel konfigurasi filter audio dengan dynamic form generation.

    Signals
    -------
    filter_changed(str, dict)  — (method_key, params_dict) saat user mengubah
                                  dropdown atau nilai parameter.
    """

    filter_changed = Signal(str, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._schemas: dict = dict(_FALLBACK_SCHEMAS)
        self._current_method: str = "spectral_gating"
        self._param_widgets: dict = {}  # {param_name: widget}
        self._build_ui()

    # ── Build UI ──────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        # ── Method Selector ───────────────────────────────────────────
        method_row = QHBoxLayout()
        method_row.setSpacing(8)

        method_label = QLabel("Filter Method:")
        method_label.setFixedWidth(100)
        method_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        method_row.addWidget(method_label)

        self._method_combo = QComboBox()
        self._method_combo.setObjectName("filterMethodCombo")
        self._method_combo.setToolTip("Select noise reduction method for drone audio")
        self._populate_method_combo()
        self._method_combo.currentIndexChanged.connect(self._on_method_changed)
        method_row.addWidget(self._method_combo, stretch=1)

        root.addLayout(method_row)

        # ── Dynamic Parameter Panel ───────────────────────────────────
        self._param_group = QGroupBox("Method Parameters")
        self._param_group.setObjectName("filterParamGroup")
        self._param_layout = QFormLayout(self._param_group)
        self._param_layout.setSpacing(6)
        self._param_layout.setContentsMargins(12, 12, 12, 12)
        self._param_layout.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        root.addWidget(self._param_group)

        # Render params for default method
        self._render_params(self._current_method)

    def _populate_method_combo(self):
        """Populate QComboBox with method list from schemas."""
        self._method_combo.blockSignals(True)
        current_key = self._current_method
        self._method_combo.clear()

        for key, schema in self._schemas.items():
            self._method_combo.addItem(schema.get("display_name", key), userData=key)

        # Restore selection
        idx = self._method_combo.findData(current_key)
        if idx >= 0:
            self._method_combo.setCurrentIndex(idx)
        else:
            self._method_combo.setCurrentIndex(0)

        self._method_combo.blockSignals(False)

    def _render_params(self, method_key: str):
        """Clear old form and render new form for selected method."""
        # Clear old layout
        while self._param_layout.rowCount() > 0:
            self._param_layout.removeRow(0)
        self._param_widgets.clear()

        schema = self._schemas.get(method_key, {})
        params = schema.get("params", {})

        if not params:
            empty_label = QLabel("No additional parameters for this method.")
            empty_label.setStyleSheet("color: #64748b; font-style: italic;")
            self._param_layout.addRow(empty_label)
            self._param_group.setTitle("Method Parameters")
            return

        display_name = schema.get("display_name", method_key)
        self._param_group.setTitle(f"Parameters: {display_name}")

        for param_name, param_info in params.items():
            widget = self._create_widget(param_info)
            if widget is None:
                continue

            # Label dengan tooltip
            label = QLabel(self._format_label(param_name) + ":")
            label.setFixedWidth(140)
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            desc = param_info.get("description", "")
            if desc:
                label.setToolTip(desc)
                widget.setToolTip(desc)

            self._param_layout.addRow(label, widget)
            self._param_widgets[param_name] = widget

            # Connect signal untuk setiap widget
            self._connect_widget_signal(widget)

    @staticmethod
    def _format_label(key: str) -> str:
        """Ubah snake_case ke Title Case untuk label."""
        return key.replace("_", " ").title()

    @staticmethod
    def _create_widget(param_info: dict):
        """Buat widget yang sesuai dengan tipe parameter."""
        ptype = param_info.get("type", "str")
        value = param_info.get("value")

        if ptype == "float":
            w = QDoubleSpinBox()
            w.setRange(param_info.get("min", -1e9), param_info.get("max", 1e9))
            w.setSingleStep(param_info.get("step", 0.01))
            w.setDecimals(3)
            if value is not None:
                w.setValue(float(value))
            return w

        elif ptype == "int":
            w = QSpinBox()
            w.setRange(int(param_info.get("min", -2**31)), int(param_info.get("max", 2**31 - 1)))
            w.setSingleStep(int(param_info.get("step", 1)))
            if value is not None:
                w.setValue(int(value))
            return w

        elif ptype == "bool":
            w = QCheckBox()
            if value is not None:
                w.setChecked(bool(value))
            return w

        elif ptype == "str":
            w = QLineEdit()
            if value is not None:
                w.setText(str(value))
            return w

        return None

    def _connect_widget_signal(self, widget):
        """Connect perubahan widget ke slot _on_param_changed."""
        if isinstance(widget, QDoubleSpinBox):
            widget.valueChanged.connect(lambda _: self._on_param_changed())
        elif isinstance(widget, QSpinBox):
            widget.valueChanged.connect(lambda _: self._on_param_changed())
        elif isinstance(widget, QCheckBox):
            widget.stateChanged.connect(lambda _: self._on_param_changed())
        elif isinstance(widget, QLineEdit):
            widget.textChanged.connect(lambda _: self._on_param_changed())

    # ── Slots ─────────────────────────────────────────────────────────

    def _on_method_changed(self, index: int):
        """User memilih metode baru dari dropdown."""
        key = self._method_combo.currentData()
        if key and key != self._current_method:
            self._current_method = key
            self._render_params(key)
            self._on_param_changed()

    def _on_param_changed(self):
        """Emit signal filter_changed dengan data terkini."""
        self.filter_changed.emit(self._current_method, self.get_params())

    # ── Public API ────────────────────────────────────────────────────

    def get_method_key(self) -> str:
        """Kembalikan key metode filter yang sedang aktif."""
        return self._current_method

    def get_params(self) -> dict:
        """
        Kembalikan dict parameter dari form yang terisi saat ini.
        Format: {param_name: value}
        """
        result = {}
        for param_name, widget in self._param_widgets.items():
            if isinstance(widget, QDoubleSpinBox):
                result[param_name] = widget.value()
            elif isinstance(widget, QSpinBox):
                result[param_name] = widget.value()
            elif isinstance(widget, QCheckBox):
                result[param_name] = widget.isChecked()
            elif isinstance(widget, QLineEdit):
                result[param_name] = widget.text()
        return result

    def get_filter_config_payload(self) -> dict:
        """
        Kembalikan payload siap kirim ke drone:
        {
          "filter_method": "spectral_gating",
          "filter_configs": {
            "spectral_gating": {"prop_decrease": 1.0, ...}
          }
        }
        """
        method = self._current_method
        params = self.get_params()
        return {
            "filter_method": method,
            "filter_configs": {method: params} if params else {},
        }

    def set_config(self, method_key: str, method_params: dict):
        """
        Set nilai form dari konfigurasi yang sudah ada (saat load dari backend).

        Args:
            method_key: Key metode filter (e.g. "spectral_gating")
            method_params: Dict parameter {param_name: value}
        """
        # Set dropdown
        idx = self._method_combo.findData(method_key)
        if idx >= 0:
            self._method_combo.setCurrentIndex(idx)
        self._current_method = method_key
        self._render_params(method_key)

        # Set nilai tiap widget
        for param_name, value in method_params.items():
            widget = self._param_widgets.get(param_name)
            if widget is None:
                continue
            if isinstance(widget, QDoubleSpinBox):
                widget.setValue(float(value))
            elif isinstance(widget, QSpinBox):
                widget.setValue(int(value))
            elif isinstance(widget, QCheckBox):
                widget.setChecked(bool(value))
            elif isinstance(widget, QLineEdit):
                widget.setText(str(value))

    def update_schemas(self, schemas: dict):
        """
        Update skema dari data yang diterima dari drone API (GET /filter-schemas).

        Args:
            schemas: Dict {method_key: {"display_name": str, "params": {...}}}
        """
        if not schemas:
            return
        self._schemas = schemas
        current = self._current_method
        self._populate_method_combo()
        # Re-render params untuk metode yang sedang aktif
        self._render_params(current)
