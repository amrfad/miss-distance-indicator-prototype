"""
Median Filter — Contoh Custom Audio Filter (Demo)

File ini adalah contoh implementasi Custom Audio Filter untuk sistem MDI Drone.
Mendemonstrasikan cara membuat filter yang kompatibel dengan filter_registry.

Letakkan file ini di:
  udara/drone_system/custom_filters/median_filter.py

Registry akan otomatis mendaftarkan filter ini dengan key "median_filter".
Filter akan muncul di dropdown "Filter Method" di Ground Station.

Lihat README_CUSTOM_FILTER.md untuk panduan lengkap.
"""

import numpy as np
import sys
import os

# Resolve path ke base_filter.py yang berada satu level di atas custom_filters/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from base_filter import BaseAudioFilter


class MedianFilter(BaseAudioFilter):
    """
    Mengurangi noise impulsif (klik, pop) menggunakan rolling median window.

    Keunggulan:
      - Tidak membutuhkan library eksternal apapun (hanya NumPy)
      - Efektif untuk noise impulsif non-stasioner
      - Tidak mengubah panjang sinyal (no trimming)

    Kekurangan:
      - Tidak optimal untuk Gaussian/broadband noise
      - Komputasi O(n * window_size) — lambat untuk window besar
    """

    def __init__(self, window_size: int = 5, normalize: bool = False, **kwargs):
        """
        Args:
            window_size (int): Ukuran rolling window (harus ganjil, >= 3).
            normalize (bool): Normalisasi output audio setelah filtering.
        """
        super().__init__(**kwargs)
        # Pastikan window_size ganjil dan minimal 3
        self.window_size = max(3, int(window_size) | 1)
        self.normalize = bool(normalize)

    def apply(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Terapkan rolling median filter ke audio 1D.
        """
        from numpy.lib.stride_tricks import sliding_window_view

        half = self.window_size // 2

        # Pad ujung dengan mode 'edge' untuk menghindari boundary artifacts
        padded = np.pad(audio, (half, half), mode='edge')

        # Hitung median per window
        windows = sliding_window_view(padded, self.window_size)
        filtered = np.median(windows, axis=-1)

        # Optional normalization
        if self.normalize:
            peak = np.max(np.abs(filtered))
            if peak > 0:
                filtered = filtered / peak

        # Clip ke valid range dan pertahankan dtype asli
        return np.clip(filtered, -1.0, 1.0).astype(audio.dtype)

    def get_params(self) -> dict:
        return {
            "window_size": {
                "value": self.window_size,
                "type": "int",
                "min": 3,
                "max": 51,
                "step": 2,
                "description": "Ukuran rolling window (ganjil, lebih besar = lebih smooth tapi lebih lambat)",
            },
            "normalize": {
                "value": self.normalize,
                "type": "bool",
                "description": "Normalisasi output audio setelah filtering",
            },
        }

    @staticmethod
    def is_available() -> bool:
        # Hanya butuh NumPy — selalu tersedia
        return True

    @classmethod
    def get_display_name(cls) -> str:
        return "Median Filter (custom demo)"
