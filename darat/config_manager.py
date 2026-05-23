"""
Ground Station Config Manager
Mengelola state konfigurasi ground station secara in-memory dengan
validasi, persistensi (ground_config_override.json), dan schema metadata.

Menggunakan abstraction layer ConfigStore yang sama dengan drone config_manager.
Untuk mengganti backend persistensi, buat class baru yang mengimplementasikan
ConfigStore dan pass ke GroundConfigManager(store=MyStore()).
"""

import json
import threading
import copy
import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import numpy as np


# ─────────────────────────────────────────────
# Re-export persistence layer dari drone package
# (atau definisikan ulang agar darat/ tidak depend on udara/)
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

    def __init__(self, path: str = "ground_config_override.json"):
        import sys, os
        # Mengubah path penyimpanan agar tetap aman saat dijalankan sebagai EXE PyInstaller
        if getattr(sys, 'frozen', False):
            # Jika dicompile jadi EXE, simpan config di sebelah file EXE
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            
        self.path = Path(os.path.join(base_dir, path))

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"[CONFIG GROUND] Warning: gagal load {self.path}: {e}")
            return {}

    def save(self, data: dict) -> None:
        # Serialisasi numpy arrays ke list sebelum simpan
        serializable = _make_serializable(data)
        try:
            self.path.write_text(
                json.dumps(serializable, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError as e:
            print(f"[CONFIG GROUND] Warning: gagal save {self.path}: {e}")


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


# ─────────────────────────────────────────────
# Schema & mappings
# ─────────────────────────────────────────────

_PARAM_SCHEMA = [
    {
        "key": "baud_rate",
        "label": "Baud Rate",
        "description": "Baud rate komunikasi serial; harus cocok dengan drone",
        "type": "integer",
        "default": 230400,
        "enum": [9600, 115200, 230400, 460800],
        "requires_restart": False,
        "unit": "bps",
    },
    {
        "key": "serial_timeout",
        "label": "Serial Timeout",
        "description": "Timeout read serial (detik)",
        "type": "number",
        "default": 1,
        "min": 0.1,
        "max": 30.0,
        "step": 0.1,
        "requires_restart": False,
        "unit": "s",
    },
    {
        "key": "serial_port",
        "label": "Serial Port",
        "description": "Device path/COM port (e.g., COM3, /dev/ttyUSB0)",
        "type": "string",
        "default": "COM3",
        "requires_restart": False,
        "unit": None,
    },
    {
        "key": "use_tcp",
        "label": "Use TCP",
        "description": "Gunakan koneksi TCP alih-alih Serial",
        "type": "boolean",
        "default": False,
        "requires_restart": False,
        "unit": None,
    },
    {
        "key": "raspi_ip",
        "label": "Raspberry Pi IP",
        "description": "IP Address Drone",
        "type": "string",
        "default": "10.99.99.2",
        "requires_restart": False,
        "unit": None,
    },
    {
        "key": "tcp_port",
        "label": "TCP Port",
        "description": "Port TCP",
        "type": "integer",
        "default": 5000,
        "min": 1024,
        "max": 65535,
        "requires_restart": False,
        "unit": None,
    },
    {
        "key": "speed_of_sound",
        "label": "Speed of Sound",
        "description": "Kecepatan suara di udara (sesuaikan dengan suhu/ketinggian)",
        "type": "number",
        "default": 343.0,
        "min": 330.0,
        "max": 360.0,
        "step": 0.1,
        "requires_restart": False,
        "unit": "m/s",
    },
    {
        "key": "cluster_eps",
        "label": "Cluster EPS",
        "description": "Jarak threshold untuk grouping solusi Bucher-Misra",
        "type": "number",
        "default": 1.0,
        "min": 0.1,
        "max": 10.0,
        "step": 0.1,
        "requires_restart": False,
        "unit": "meter",
    },
    {
        "key": "supported_extensions",
        "label": "Supported Extensions",
        "description": "Ekstensi file yang didukung untuk transfer",
        "type": "array",
        "default": [".mp4", ".wav", ".txt", ".json"],
        "requires_restart": False,
        "unit": None,
    },
    {
        "key": "update_interval_s",
        "label": "Update Interval",
        "description": "Interval refresh plot 3D",
        "type": "number",
        "default": 0.1,
        "min": 0.03,
        "max": 2.0,
        "step": 0.01,
        "requires_restart": False,
        "unit": "s",
    },
    {
        "key": "plot_buffer_size",
        "label": "Plot Buffer Size",
        "description": "Kapasitas buffer visualisasi data 2D/3D",
        "type": "integer",
        "default": 1000,
        "min": 100,
        "max": 20000,
        "requires_restart": False,
        "unit": "points",
    },
    {
        "key": "mic_positions",
        "label": "Microphone Positions",
        "description": "Posisi 3D setiap mikrofon dalam koordinat meter",
        "type": "mic_positions",
        "default": {
            "mic0": {"x": -1.58, "y": 0.77, "z": 0.09},
            "mic1": {"x":  1.60, "y": 0.77, "z": 0.09},
            "mic2": {"x": -0.59, "y": -0.92, "z": -0.07},
            "mic3": {"x":  0.59, "y": -0.92, "z": -0.05},
            "mic4": {"x": -0.50, "y": -0.11, "z": -0.16},
            "mic5": {"x":  0.13, "y": -0.01, "z": -0.17},
        },
        "requires_restart": False,
        "unit": None,
    },
]

_ALL_KEYS: set = {s["key"] for s in _PARAM_SCHEMA}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _make_serializable(obj):
    """Konversi numpy types/arrays ke Python native untuk JSON serialization."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, dict):
        return {k: _make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_make_serializable(v) for v in obj]
    return obj


def _mic_positions_to_dict(mic_positions: dict) -> dict:
    """Convert MIC_POSITIONS (values sebagai np.array) ke {mic: {x,y,z}} untuk JSON."""
    result = {}
    for name, pos in mic_positions.items():
        if isinstance(pos, np.ndarray):
            result[name] = {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])}
        elif isinstance(pos, dict):
            result[name] = {"x": float(pos["x"]), "y": float(pos["y"]), "z": float(pos["z"])}
        else:
            result[name] = {"x": float(pos[0]), "y": float(pos[1]), "z": float(pos[2])}
    return result


def _mic_positions_to_numpy(mic_positions: dict) -> dict:
    """Convert {mic: {x,y,z}} ke {mic: np.array} untuk internal use."""
    return {
        name: np.array([float(pos["x"]), float(pos["y"]), float(pos["z"])])
        for name, pos in mic_positions.items()
    }


# ─────────────────────────────────────────────
# Ground Config Manager
# ─────────────────────────────────────────────

class GroundConfigManager:
    """
    Mengelola state konfigurasi ground station secara thread-safe.

    mic_positions disimpan secara internal sebagai {mic: np.array[x,y,z]},
    tapi di-serialize ke {mic: {x,y,z}} saat get_all() / simpan ke JSON.

    Gunakan:
        manager = GroundConfigManager()                      # default JsonFileStore
        manager = GroundConfigManager(store=NullStore())     # in-memory only
    """

    def __init__(self, store: Optional[ConfigStore] = None):
        self._lock = threading.RLock()
        self._store = store if store is not None else JsonFileStore()
        self._config: dict = self._build_defaults()
        # Merge saved overrides
        overrides = self._store.load()
        if overrides:
            print(f"[CONFIG GROUND] Loaded {len(overrides)} override(s) from store")
            self._merge_overrides(overrides)

    def get_config(self) -> dict:
        """Alias for get_all() to maintain consistency across codebase."""
        return self.get_all()

    # ── Public API ────────────────────────────────────────────────────

    def get_all(self) -> dict:
        """
        Return seluruh config sebagai flat dict.
        mic_positions dikembalikan sebagai {mic: {x, y, z}} (JSON-serializable).
        """
        with self._lock:
            result = dict(self._config)
            result["mic_positions"] = _mic_positions_to_dict(
                self._config["mic_positions"]
            )
            return result

    def get(self, key: str) -> Any:
        """Return nilai satu parameter."""
        with self._lock:
            if key not in _ALL_KEYS:
                raise UnknownParamError(key)
            val = self._config[key]
            if key == "mic_positions":
                return _mic_positions_to_dict(val)
            return val

    def get_mic_positions_numpy(self) -> dict:
        """Return mic_positions sebagai {mic: np.array} untuk digunakan oleh TDOA processing."""
        with self._lock:
            return dict(self._config["mic_positions"])

    def update(self, changes: dict) -> dict:
        """
        Validasi dan apply perubahan secara atomic.

        Untuk mic_positions, PATCH bersifat merge: hanya key yang dikirim
        yang diperbarui — key lain tidak dihapus (section 4.1 contract).

        Returns:
            dict dengan keys: updated (list field names), requires_restart, message

        Raises:
            UnknownParamError — key tidak dikenal
            ValidationError   — nilai gagal validasi
        """
        with self._lock:
            for key in changes:
                if key not in _ALL_KEYS:
                    raise UnknownParamError(key)

            updated_fields = []

            for key, value in changes.items():
                if key == "mic_positions":
                    # Merge mic positions (PATCH semantics)
                    if not isinstance(value, dict):
                        raise ValidationError(
                            "mic_positions harus berupa object {mic_name: {x, y, z}}",
                            "mic_positions",
                        )
                    for mic_name, coords in value.items():
                        self._validate_mic_coords(mic_name, coords)
                        self._config["mic_positions"][mic_name] = np.array([
                            float(coords["x"]),
                            float(coords["y"]),
                            float(coords["z"]),
                        ])
                        updated_fields.append(f"mic_positions.{mic_name}")
                else:
                    coerced = self._coerce(key, value)
                    self._config[key] = coerced
                    updated_fields.append(key)

            self._store.save(self.get_all())

            return {
                "updated": updated_fields,
                "requires_restart": False,
                "message": f"{len(updated_fields)} field updated successfully",
            }

    def reset(self, scope: str = "all") -> dict:
        """Reset parameter ke nilai default."""
        with self._lock:
            if scope not in ("all",):
                raise ValidationError(
                    f"scope tidak valid: '{scope}'. Ground station hanya mendukung 'all'",
                    "scope",
                )
            self._config = self._build_defaults()
            self._store.save(self.get_all())
            return {
                "reset_count": len(_ALL_KEYS),
                "requires_restart": False,
                "message": "Ground config reset to defaults",
            }

    def get_schema(self) -> dict:
        """Return schema metadata untuk rendering form UI."""
        return {"params": list(_PARAM_SCHEMA)}

    # ── Internal helpers ──────────────────────────────────────────────

    @staticmethod
    def _build_defaults() -> dict:
        """Build dict default dari schema, termasuk mic_positions sebagai np.array."""
        defaults = {}
        for s in _PARAM_SCHEMA:
            key = s["key"]
            if key == "mic_positions":
                defaults[key] = _mic_positions_to_numpy(s["default"])
            else:
                defaults[key] = s["default"]
        return defaults

    def _merge_overrides(self, overrides: dict) -> None:
        """Merge overrides dari store ke self._config."""
        for key, value in overrides.items():
            if key not in _ALL_KEYS:
                continue
            if key == "mic_positions" and isinstance(value, dict):
                for mic_name, coords in value.items():
                    if isinstance(coords, dict) and all(k in coords for k in ("x", "y", "z")):
                        self._config["mic_positions"][mic_name] = np.array([
                            float(coords["x"]), float(coords["y"]), float(coords["z"])
                        ])
            else:
                try:
                    self._config[key] = self._coerce(key, value)
                except Exception:
                    pass  # Abaikan nilai yang tidak valid dari override

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
            elif typ == "array":
                if isinstance(value, list):
                    return value
                raise ValidationError(f"'{key}' harus berupa array", key)
            else:
                return str(value)
        except (ValueError, TypeError) as e:
            raise ValidationError(
                f"Tipe tidak valid untuk '{key}': expected {typ}, got {type(value).__name__}",
                key,
            ) from e

    @staticmethod
    def _validate_mic_coords(mic_name: str, coords: Any) -> None:
        """Validasi struktur koordinat mikrofon {x, y, z}."""
        if not isinstance(coords, dict):
            raise ValidationError(
                f"Koordinat '{mic_name}' harus berupa object {{x, y, z}}",
                "mic_positions",
            )
        for axis in ("x", "y", "z"):
            if axis not in coords:
                raise ValidationError(
                    f"Koordinat '{mic_name}' missing field '{axis}'",
                    "mic_positions",
                )
            try:
                float(coords[axis])
            except (TypeError, ValueError):
                raise ValidationError(
                    f"Koordinat '{mic_name}.{axis}' harus berupa angka",
                    "mic_positions",
                )

# ── Singleton Pattern ──────────────────────────────────────────────

_GLOBAL_MANAGER = None
_GLOBAL_LOCK = threading.Lock()

def get_global_config_manager() -> GroundConfigManager:
    """Mendapatkan singleton instance dari GroundConfigManager."""
    global _GLOBAL_MANAGER
    with _GLOBAL_LOCK:
        if _GLOBAL_MANAGER is None:
            import sys, os
            # Saat dijalankan sebagai EXE PyInstaller, __file__ menunjuk ke
            # folder temp _MEIxxxxx yang dihapus saat EXE keluar.
            # Gunakan sys.executable agar config tersimpan permanen di sebelah EXE.
            if getattr(sys, 'frozen', False):
                base_dir = os.path.dirname(sys.executable)
            else:
                base_dir = os.path.dirname(os.path.abspath(__file__))
            config_dir = os.path.join(base_dir, "config")
            os.makedirs(config_dir, exist_ok=True)
            store = JsonFileStore(os.path.join(config_dir, "ground_config_override.json"))
            _GLOBAL_MANAGER = GroundConfigManager(store=store)
    return _GLOBAL_MANAGER
