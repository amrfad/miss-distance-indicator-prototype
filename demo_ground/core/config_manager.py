"""
Config Manager Module (Standalone for Demo Ground Station)
Mengelola konfigurasi sederhana berbasis JSON file untuk demo ground station.
"""

import json
import os
import copy
from pathlib import Path
from typing import Dict, Any, Optional

DEFAULT_CONFIG: Dict[str, Any] = {
    "serial_port": "COM3",
    "baud_rate": 230400,
    "serial_timeout": 1.0,
    "speed_of_sound": 343.0,
    "cluster_eps": 1.0,
    "ssl_method": "auto_adaptive",
    "mic_positions": {
        "mic0": {"x": -1.58, "y":  0.77, "z": 0.0},
        "mic1": {"x":  1.60, "y":  0.77, "z": 0.0},
        "mic2": {"x": -0.59, "y": -0.92, "z": 0.0},
        "mic3": {"x":  0.59, "y": -0.92, "z": 0.0},
        "mic4": {"x": -0.50, "y": -0.11, "z": 0.0},
        "mic5": {"x":  0.13, "y": -0.01, "z": 0.0},
    },
}


class ConfigManager:
    """Pengelola konfigurasi JSON untuk demo ground station."""

    def __init__(self, config_path: Optional[str] = None):
        if config_path:
            self.config_path = Path(config_path)
        else:
            base_dir = Path(os.path.dirname(os.path.abspath(__file__))).parent
            self.config_path = base_dir / "config.json"

        self._config: Dict[str, Any] = copy.deepcopy(DEFAULT_CONFIG)
        self.load()

    def get_all(self) -> Dict[str, Any]:
        """Ambil salinan seluruh konfigurasi."""
        return copy.deepcopy(self._config)

    def get(self, key: str, default: Any = None) -> Any:
        """Ambil nilai konfigurasi tertentu."""
        return self._config.get(key, default)

    def set(self, key: str, value: Any):
        """Set satu nilai konfigurasi."""
        self._config[key] = value

    def update(self, new_data: Dict[str, Any]):
        """Update beberapa konfigurasi sekaligus."""
        self._config.update(new_data)

    def load(self) -> Dict[str, Any]:
        """Muat konfigurasi dari file JSON jika ada."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    # Merge with default to guarantee all keys exist
                    for k, v in loaded.items():
                        self._config[k] = v
            except Exception as e:
                print(f"[ConfigManager] Gagal membaca {self.config_path}: {e}")
        return self.get_all()

    def save(self) -> bool:
        """Simpan konfigurasi ke file JSON."""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"[ConfigManager] Gagal menyimpan ke {self.config_path}: {e}")
            return False

    def reset_to_default(self):
        """Kembalikan ke default."""
        self._config = copy.deepcopy(DEFAULT_CONFIG)
        self.save()
