"""
Drone Config Manager
Mengelola state konfigurasi drone secara in-memory dengan validasi,
persistensi, dan schema metadata untuk Config UI.

Abstraction Layer untuk Persistensi:
  ConfigStore  — Protocol/ABC backend persistensi (mudah diganti)
  JsonFileStore — Implementasi default menggunakan JSON file

Untuk mengganti backend:
  1. Buat class baru yang mengimplementasikan ConfigStore
  2. Pass instance-nya ke ConfigManager(store=MyStore(...))
"""

import json
import threading
import copy
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

# ─────────────────────────────────────────────
# Persistence abstraction layer
# ─────────────────────────────────────────────

class ConfigStore(ABC):
    """Abstract base class untuk backend persistensi konfigurasi."""

    @abstractmethod
    def load(self) -> dict:
        """Load konfigurasi. Return dict kosong jika belum ada."""

    @abstractmethod
    def save(self, data: dict) -> None:
        """Simpan konfigurasi ke backend."""


class JsonFileStore(ConfigStore):
    """Implementasi ConfigStore menggunakan JSON file di filesystem."""

    def __init__(self, path: str = "config_override.json"):
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[CONFIG] Warning: gagal load {self.path}: {e}")
            return {}

    def save(self, data: dict) -> None:
        try:
            self.path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as e:
            print(f"[CONFIG] Warning: gagal save {self.path}: {e}")


class NullStore(ConfigStore):
    """ConfigStore yang tidak menyimpan apapun (in-memory only)."""

    def load(self) -> dict:
        return {}

    def save(self, data: dict) -> None:
        pass


# ─────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────

class ConfigError(Exception):
    """Base exception untuk config errors."""
    def __init__(self, code: str, message: str, field: Optional[str] = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "field": self.field}


class ValidationError(ConfigError):
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__("VALIDATION_ERROR", message, field)


class UnknownParamError(ConfigError):
    def __init__(self, key: str):
        super().__init__("UNKNOWN_PARAM", f"Parameter tidak dikenal: '{key}'", key)


class ReadonlyParamError(ConfigError):
    def __init__(self, key: str):
        super().__init__(
            "READONLY_PARAM",
            f"Parameter '{key}' hanya bisa diubah via REST (ground-only, perlu restart)",
            key,
        )


# ─────────────────────────────────────────────
# Config Manager
# ─────────────────────────────────────────────

# Parameter schema lengkap (sesuai communication contract section 3.3)
_PARAM_SCHEMA = [
    # ── Ground-only (🔒) ──────────────────────────────────────────────
    {
        "key": "operation_mode", "label": "Operation Mode",
        "description": "ONLINE menerima command via serial; OFFLINE via keyboard",
        "type": "string", "default": "OFFLINE", "enum": ["ONLINE", "OFFLINE"],
        "category": "ground_only", "requires_restart": True, "unit": None,
    },
    {
        "key": "serial_port", "label": "Serial Port",
        "description": "Device path serial port",
        "type": "string", "default": "/dev/ttyUSB0",
        "category": "ground_only", "requires_restart": True, "unit": None,
    },
    {
        "key": "baud_rate", "label": "Baud Rate",
        "description": "Baud rate komunikasi serial; harus konsisten dengan ground station",
        "type": "integer", "default": 230400, "enum": [9600, 115200, 230400, 460800],
        "category": "ground_only", "requires_restart": True, "unit": "bps",
    },
    {
        "key": "serial_timeout", "label": "Serial Timeout",
        "description": "Timeout read serial (detik)",
        "type": "number", "default": 5, "min": 1, "max": 30, "step": 1,
        "category": "ground_only", "requires_restart": True, "unit": "s",
    },
    {
        "key": "arecord_device", "label": "Audio Device",
        "description": "ALSA device untuk recording (contoh: hw:2,0)",
        "type": "string", "default": "hw:2,0",
        "category": "ground_only", "requires_restart": True, "unit": None,
    },
    {
        "key": "sample_rate", "label": "Sample Rate",
        "description": "Frekuensi sampling audio recording",
        "type": "integer", "default": 48000, "enum": [44100, 48000, 96000],
        "category": "ground_only", "requires_restart": True, "unit": "Hz",
    },
    {
        "key": "active_profile", "label": "Device Profile",
        "description": "Profil perangkat audio (H8 atau H6E)",
        "type": "string", "default": "H8", "enum": ["H8", "H6E"],
        "category": "ground_only", "requires_restart": True, "unit": None,
    },
    {
        "key": "num_mics_h8", "label": "Num Mics (H8)",
        "description": "Jumlah mikrofon untuk profil H8 (4 atau 6)",
        "type": "integer", "default": 6, "enum": [4, 6],
        "category": "ground_only", "requires_restart": True, "unit": None,
    },
    {
        "key": "base_output_dir", "label": "Output Directory",
        "description": "Base directory untuk menyimpan recording",
        "type": "string", "default": "drone_recordings",
        "category": "ground_only", "requires_restart": True, "unit": None,
    },
    {
        "key": "is_gcc_phat", "label": "Use GCC-PHAT",
        "description": "Gunakan GCC-PHAT untuk TDOA calculation",
        "type": "boolean", "default": True,
        "category": "ground_only", "requires_restart": True, "unit": None,
    },
    {
        "key": "arecord_terminate_timeout", "label": "arecord Terminate Timeout",
        "description": "Timeout terminate proses arecord (detik)",
        "type": "number", "default": 3, "min": 1, "max": 30, "step": 1,
        "category": "ground_only", "requires_restart": True, "unit": "s",
    },
    {
        "key": "events_csv", "label": "Events CSV Filename",
        "description": "Nama file CSV untuk detected events",
        "type": "string", "default": "detected_events.csv",
        "category": "ground_only", "requires_restart": True, "unit": None,
    },
    {
        "key": "events_json", "label": "Events JSON Filename",
        "description": "Nama file JSON untuk session events",
        "type": "string", "default": "session_events.json",
        "category": "ground_only", "requires_restart": True, "unit": None,
    },
    {
        "key": "tdoa_json", "label": "TDOA JSON Filename",
        "description": "Nama file JSON untuk TDOA results",
        "type": "string", "default": "session_tdoa.json",
        "category": "ground_only", "requires_restart": True, "unit": None,
    },
    {
        "key": "api_host", "label": "API Host",
        "description": "Host binding untuk REST API server. '0.0.0.0' untuk IPv4, '::' untuk IPv6 dual-stack",
        "type": "string", "default": "0.0.0.0",
        "category": "ground_only", "requires_restart": True, "unit": None,
    },
    {
        "key": "api_port", "label": "API Port",
        "description": "Port untuk REST API server",
        "type": "integer", "default": 5000, "min": 1, "max": 65535, "step": 1,
        "category": "ground_only", "requires_restart": True, "unit": None,
    },
    # ── Runtime / Dual (🔄) ───────────────────────────────────────────
    {
        "key": "min_duration", "label": "Min Event Duration",
        "description": "Durasi minimal event yang valid",
        "type": "number", "default": 0.25, "min": 0.01, "max": 10.0, "step": 0.01,
        "category": "runtime", "requires_restart": False, "unit": "s",
    },
    {
        "key": "max_gap", "label": "Max Event Gap",
        "description": "Gap maksimal antar event untuk di-merge",
        "type": "number", "default": 0.1, "min": 0.01, "max": 5.0, "step": 0.01,
        "category": "runtime", "requires_restart": False, "unit": "s",
    },
    {
        "key": "detect_ratio", "label": "Detect Ratio",
        "description": "Threshold deteksi awal event (relatif thd max energy)",
        "type": "number", "default": 0.20, "min": 0.0, "max": 1.0, "step": 0.01,
        "category": "runtime", "requires_restart": False, "unit": None,
    },
    {
        "key": "filter_ratio", "label": "Filter Ratio",
        "description": "Threshold filter event final; harus ≥ detect_ratio",
        "type": "number", "default": 0.40, "min": 0.0, "max": 1.0, "step": 0.01,
        "category": "runtime", "requires_restart": False, "unit": None,
    },
    {
        "key": "ignore_time", "label": "Ignore Time",
        "description": "Abaikan deteksi di awal recording (menghindari startup noise)",
        "type": "number", "default": 0.5, "min": 0.0, "max": 10.0, "step": 0.1,
        "category": "runtime", "requires_restart": False, "unit": "s",
    },
    {
        "key": "prop_decrease", "label": "Prop Decrease",
        "description": "Proporsi pengurangan noise (0=off, 1=maksimal)",
        "type": "number", "default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05,
        "category": "runtime", "requires_restart": False, "unit": None,
    },
    {
        "key": "stationary", "label": "Stationary Noise",
        "description": "Gunakan mode stationary noise reduction",
        "type": "boolean", "default": False,
        "category": "runtime", "requires_restart": False, "unit": None,
    },
    {
        "key": "normalize", "label": "Normalize",
        "description": "Normalisasi output audio setelah filtering",
        "type": "boolean", "default": False,
        "category": "runtime", "requires_restart": False, "unit": None,
    },
    {
        "key": "freq_mask_smooth_hz", "label": "Freq Mask Smooth",
        "description": "Smoothing di domain frekuensi",
        "type": "integer", "default": 100, "min": 1, "max": 1000, "step": 10,
        "category": "runtime", "requires_restart": False, "unit": "Hz",
    },
    {
        "key": "time_mask_smooth_ms", "label": "Time Mask Smooth",
        "description": "Smoothing di domain waktu",
        "type": "integer", "default": 10, "min": 1, "max": 500, "step": 5,
        "category": "runtime", "requires_restart": False, "unit": "ms",
    },
    {
        "key": "hop_length", "label": "Hop Length",
        "description": "Librosa hop length (harus kelipatan 2)",
        "type": "integer", "default": 512, "min": 64, "max": 4096, "step": 64,
        "category": "runtime", "requires_restart": False, "unit": "samples",
    },
    {
        "key": "frame_length", "label": "Frame Length",
        "description": "Librosa frame length (harus ≥ hop_length)",
        "type": "integer", "default": 1024, "min": 64, "max": 8192, "step": 64,
        "category": "runtime", "requires_restart": False, "unit": "samples",
    },
    {
        "key": "normalization_percentile", "label": "Normalization Percentile",
        "description": "Percentile untuk normalisasi RMS (menghindari outlier)",
        "type": "number", "default": 99.9, "min": 0.1, "max": 100.0, "step": 0.1,
        "category": "runtime", "requires_restart": False, "unit": "%",
    },
    {
        "key": "event_padding_sec", "label": "Event Padding",
        "description": "Padding audio di sekitar event (sebelum dan sesudah)",
        "type": "number", "default": 0.3, "min": 0.0, "max": 5.0, "step": 0.05,
        "category": "runtime", "requires_restart": False, "unit": "s",
    },
    {
        "key": "post_recording_delay", "label": "Post Recording Delay",
        "description": "Delay setelah stop recording sebelum proses",
        "type": "number", "default": 0.5, "min": 0.0, "max": 10.0, "step": 0.1,
        "category": "runtime", "requires_restart": False, "unit": "s",
    },
    {
        "key": "main_loop_delay", "label": "Main Loop Delay",
        "description": "Delay di main loop (mengurangi CPU usage)",
        "type": "number", "default": 0.1, "min": 0.01, "max": 1.0, "step": 0.01,
        "category": "runtime", "requires_restart": False, "unit": "s",
    },
    # ── Streaming / Chunk Processing ──────────────────────────────────
    {
        "key": "chunk_duration_sec", "label": "Chunk Duration",
        "description": "Durasi utama setiap chunk audio yang diproses dan dikirim ke ground (detik)",
        "type": "number", "default": 5.0, "min": 1.0, "max": 60.0, "step": 0.5,
        "category": "ground_only", "requires_restart": True, "unit": "s",
    },
    {
        "key": "chunk_overlap_sec", "label": "Chunk Overlap",
        "description": "Durasi overlap dengan chunk sebelumnya untuk menangani event di perbatasan chunk",
        "type": "number", "default": 1.0, "min": 0.0, "max": 10.0, "step": 0.25,
        "category": "ground_only", "requires_restart": True, "unit": "s",
    },
    {
        "key": "keep_audio_files", "label": "Keep Audio Files",
        "description": "Simpan file WAV chunk setelah TDOA dihitung. False = hapus otomatis untuk hemat storage",
        "type": "boolean", "default": True,
        "category": "ground_only", "requires_restart": False, "unit": None,
    },
    # ── Filter Method (Strategy Pattern) ────────────────────────────
    {
        "key": "filter_method", "label": "Filter Method",
        "description": "Metode noise reduction yang digunakan (key dari filter_registry)",
        "type": "string", "default": "spectral_gating",
        "enum": ["spectral_gating", "wavelet_denoising", "wiener_stft", "passthrough"],
        "category": "runtime", "requires_restart": False, "unit": None,
    },
    {
        "key": "filter_configs", "label": "Filter Configs",
        "description": "Parameter nested per metode filter: {method_key: {param: value, ...}}",
        "type": "object", "default": {},
        "category": "runtime", "requires_restart": False, "unit": None,
    },
]

# Mapping: key (snake_case) → nama variabel di config.py (UPPER_CASE)
_KEY_TO_CONFIG_VAR = {
    "operation_mode": "OPERATION_MODE",
    "serial_port": "SERIAL_PORT",
    "baud_rate": "BAUD_RATE",
    "serial_timeout": "SERIAL_TIMEOUT",
    "arecord_device": "ARECORD_DEVICE",
    "sample_rate": "SAMPLE_RATE",
    "active_profile": "ACTIVE_PROFILE",
    "num_mics_h8": "NUM_MICS_H8",
    "base_output_dir": "BASE_OUTPUT_DIR",
    "is_gcc_phat": "IS_GCC_PHAT",
    "arecord_terminate_timeout": "ARECORD_TERMINATE_TIMEOUT",
    "events_csv": "EVENTS_CSV",
    "events_json": "EVENTS_JSON",
    "tdoa_json": "TDOA_JSON",
    "api_host": "API_HOST",
    "api_port": "API_PORT",
    "min_duration": "MIN_DURATION",
    "max_gap": "MAX_GAP",
    "detect_ratio": "DETECT_RATIO",
    "filter_ratio": "FILTER_RATIO",
    "ignore_time": "IGNORE_TIME",
    "prop_decrease": "PROP_DECREASE",
    "stationary": "STATIONARY",
    "normalize": "NORMALIZE",
    "freq_mask_smooth_hz": "FREQ_MASK_SMOOTH_HZ",
    "time_mask_smooth_ms": "TIME_MASK_SMOOTH_MS",
    "hop_length": "HOP_LENGTH",
    "frame_length": "FRAME_LENGTH",
    "normalization_percentile": "NORMALIZATION_PERCENTILE",
    "event_padding_sec": "EVENT_PADDING_SEC",
    "post_recording_delay": "POST_RECORDING_DELAY",
    "main_loop_delay": "MAIN_LOOP_DELAY",
    "chunk_duration_sec": "CHUNK_DURATION_SEC",
    "chunk_overlap_sec": "CHUNK_OVERLAP_SEC",
    "keep_audio_files": "KEEP_AUDIO_FILES",
    "filter_method": "FILTER_METHOD",
    "filter_configs": "FILTER_CONFIGS",
}

_GROUND_ONLY_KEYS: set[str] = {
    s["key"] for s in _PARAM_SCHEMA if s["category"] == "ground_only"
}
_RUNTIME_KEYS: set[str] = {
    s["key"] for s in _PARAM_SCHEMA if s["category"] == "runtime"
}
_ALL_KEYS: set[str] = _GROUND_ONLY_KEYS | _RUNTIME_KEYS

# Validation rules (section 6 communication contract)
_VALIDATION_RULES: list[tuple[str, Any, Optional[str]]] = [
    ("filter_ratio >= detect_ratio",
     lambda c: c["filter_ratio"] >= c["detect_ratio"],
     "filter_ratio"),
    ("detect_ratio ∈ [0.0, 1.0]",
     lambda c: 0.0 <= c["detect_ratio"] <= 1.0,
     "detect_ratio"),
    ("filter_ratio ∈ [0.0, 1.0]",
     lambda c: 0.0 <= c["filter_ratio"] <= 1.0,
     "filter_ratio"),
    ("prop_decrease ∈ [0.0, 1.0]",
     lambda c: 0.0 <= c["prop_decrease"] <= 1.0,
     "prop_decrease"),
    ("min_duration > 0",
     lambda c: c["min_duration"] > 0,
     "min_duration"),
    ("max_gap > 0",
     lambda c: c["max_gap"] > 0,
     "max_gap"),
    ("num_mics_h8 ∈ {4, 6}",
     lambda c: c["num_mics_h8"] in {4, 6},
     "num_mics_h8"),
    ("sample_rate ∈ {44100, 48000, 96000}",
     lambda c: c["sample_rate"] in {44100, 48000, 96000},
     "sample_rate"),
    ("hop_length > 0 dan kelipatan 2",
     lambda c: c["hop_length"] > 0 and (c["hop_length"] & (c["hop_length"] - 1)) == 0,
     "hop_length"),
    ("frame_length >= hop_length",
     lambda c: c["frame_length"] >= c["hop_length"],
     "frame_length"),
    ("normalization_percentile ∈ (0, 100]",
     lambda c: 0 < c["normalization_percentile"] <= 100,
     "normalization_percentile"),
    ("active_profile ∈ {H8, H6E}",
     lambda c: c["active_profile"] in {"H8", "H6E"},
     "active_profile"),
    ("operation_mode ∈ {ONLINE, OFFLINE}",
     lambda c: c["operation_mode"] in {"ONLINE", "OFFLINE"},
     "operation_mode"),
    ("chunk_duration_sec > chunk_overlap_sec",
     lambda c: c["chunk_duration_sec"] > c["chunk_overlap_sec"],
     "chunk_duration_sec"),
]


class ConfigManager:
    """
    Mengelola state konfigurasi drone secara thread-safe.

    Gunakan:
        manager = ConfigManager()                      # default: JsonFileStore
        manager = ConfigManager(store=NullStore())     # in-memory only
        manager = ConfigManager(store=MyCustomStore()) # custom backend
    """

    def __init__(self, store: Optional[ConfigStore] = None):
        self._lock = threading.RLock()
        self._store = store if store is not None else JsonFileStore()
        self._config: dict = self._build_defaults()
        # Merge saved overrides on top of defaults
        overrides = self._store.load()
        if overrides:
            print(f"[CONFIG] Loaded {len(overrides)} override(s) from store")
            self._config.update(
                {k: v for k, v in overrides.items() if k in _ALL_KEYS}
            )

    def get_config(self) -> dict:
        """Alias for get_all() to maintain consistency across codebase."""
        return self.get_all()

    # ── Public API ────────────────────────────────────────────────────

    def get_all(self) -> dict:
        """Return seluruh config sebagai flat dict (snake_case keys)."""
        with self._lock:
            return dict(self._config)

    def get(self, key: str) -> Any:
        """Return nilai satu parameter."""
        with self._lock:
            if key not in _ALL_KEYS:
                raise UnknownParamError(key)
            return self._config[key]

    def update(self, changes: dict, source: str = "rest") -> dict:
        """
        Validasi dan apply perubahan secara atomic.

        Args:
            changes: Dict parameter yang ingin diubah {key: value}
            source:  "rest"   — semua param boleh diubah (🔒 dan 🔄)
                     "serial" — hanya 🔄 runtime params yang boleh diubah

        Returns:
            dict dengan keys: updated, requires_restart, restart_params, message

        Raises:
            UnknownParamError  — key tidak dikenal
            ReadonlyParamError — param 🔒 dikirim via serial
            ValidationError    — nilai gagal validasi
        """
        with self._lock:
            # 1. Validasi keys
            for key in changes:
                if key not in _ALL_KEYS:
                    raise UnknownParamError(key)
                if source == "serial" and key in _GROUND_ONLY_KEYS:
                    raise ReadonlyParamError(key)

            # 2. Type coercion + tentative merge
            coerced = {k: self._coerce(k, v) for k, v in changes.items()}
            merged = {**self._config, **coerced}

            # 3. Cross-parameter validation
            self._validate(merged)

            # 4. Apply
            self._config.update(coerced)
            self._store.save(self._config)

            # 5. Build result
            restart_params = [k for k in coerced if k in _GROUND_ONLY_KEYS]
            return {
                "updated": coerced,
                "requires_restart": bool(restart_params),
                "restart_params": restart_params,
                "message": (
                    f"{len(coerced)} parameter updated successfully"
                    if not restart_params
                    else (
                        f"{len(coerced)} parameter updated. "
                        f"RESTART REQUIRED untuk params: {', '.join(restart_params)}"
                    )
                ),
            }

    def reset(self, scope: str = "all") -> dict:
        """
        Reset parameter ke nilai default.

        Args:
            scope: "all" | "runtime_only" | "ground_only"
        """
        with self._lock:
            defaults = self._build_defaults()
            if scope == "all":
                keys_to_reset = _ALL_KEYS
            elif scope == "runtime_only":
                keys_to_reset = _RUNTIME_KEYS
            elif scope == "ground_only":
                keys_to_reset = _GROUND_ONLY_KEYS
            else:
                raise ValidationError(
                    f"scope tidak valid: '{scope}'. Gunakan: all | runtime_only | ground_only",
                    "scope",
                )

            for k in keys_to_reset:
                self._config[k] = defaults[k]
            self._store.save(self._config)

            has_restart = scope in ("all", "ground_only")
            return {
                "reset_count": len(keys_to_reset),
                "requires_restart": has_restart,
                "message": "Config reset to defaults",
            }

    def get_schema(self) -> dict:
        """Return schema metadata lengkap untuk rendering form UI."""
        return {"params": list(_PARAM_SCHEMA)}

    def apply_to_runtime_objects(self, detector=None, processor=None) -> None:
        """
        Update runtime objects (EventDetector, AudioProcessor) dengan
        nilai config terkini. Panggil setelah update() untuk params 🔄.

        Args:
            detector: EventDetector instance (optional)
            processor: AudioProcessor instance (optional)
        """
        with self._lock:
            if detector is not None and hasattr(detector, "update_parameters"):
                runtime_detect_params = {
                    "min_duration": self._config["min_duration"],
                    "max_gap": self._config["max_gap"],
                    "detect_ratio": self._config["detect_ratio"],
                    "filter_ratio": self._config["filter_ratio"],
                    "ignore_time": self._config["ignore_time"],
                    "hop_length": self._config["hop_length"],
                    "frame_length": self._config["frame_length"],
                }
                detector.update_parameters(**runtime_detect_params)

    # ── Internal helpers ──────────────────────────────────────────────

    @staticmethod
    def _build_defaults() -> dict:
        """Build dict default dari _PARAM_SCHEMA."""
        return {s["key"]: s["default"] for s in _PARAM_SCHEMA}

    @staticmethod
    def _coerce(key: str, value: Any) -> Any:
        """Coerce value ke tipe yang benar berdasarkan schema."""
        schema = next((s for s in _PARAM_SCHEMA if s["key"] == key), None)
        if schema is None:
            return value
        typ = schema["type"]
        try:
            if typ == "integer":
                return int(value)
            elif typ == "number":
                return float(value)
            elif typ == "boolean":
                if isinstance(value, bool):
                    return value
                return str(value).lower() in ("true", "1", "yes")
            elif typ == "object":
                if isinstance(value, dict):
                    return value
                raise ValidationError(f"'{key}' harus berupa object/dict", key)
            else:
                return str(value)
        except (ValueError, TypeError) as e:
            raise ValidationError(
                f"Tipe tidak valid untuk '{key}': expected {typ}, got {type(value).__name__}",
                key,
            ) from e

    @staticmethod
    def _validate(config: dict) -> None:
        """Validasi semua cross-parameter rules (section 6 contract)."""
        for rule_desc, rule_fn, field in _VALIDATION_RULES:
            try:
                if not rule_fn(config):
                    raise ValidationError(
                        f"Validasi gagal: {rule_desc}", field
                    )
            except (KeyError, TypeError, ZeroDivisionError):
                pass  # Skip rule jika key tidak ada (partial update)

# ── Singleton Pattern ──────────────────────────────────────────────

_GLOBAL_MANAGER = None
_GLOBAL_LOCK = threading.Lock()

def get_global_config_manager() -> ConfigManager:
    """Mendapatkan singleton instance dari ConfigManager drone."""
    global _GLOBAL_MANAGER
    with _GLOBAL_LOCK:
        if _GLOBAL_MANAGER is None:
            # Setup default path
            import os
            import sys
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            config_dir = os.path.join(base_dir, "config")
            os.makedirs(config_dir, exist_ok=True)
            store = JsonFileStore(os.path.join(config_dir, "drone_config_override.json"))
            _GLOBAL_MANAGER = ConfigManager(store=store)
    return _GLOBAL_MANAGER
