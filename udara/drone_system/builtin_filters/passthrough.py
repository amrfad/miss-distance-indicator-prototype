"""
Passthrough Filter — Dummy / Bypass
Mengembalikan audio asli tanpa perubahan apapun.
Berguna untuk debugging dan baseline comparison.
"""

import numpy as np
from ..base_filter import BaseAudioFilter


class PassthroughFilter(BaseAudioFilter):
    """
    Filter dummy yang mengembalikan audio asli tanpa modifikasi.

    Berguna untuk:
      - Debugging pipeline tanpa filtering
      - Baseline comparison terhadap metode lain
      - Testing registry dan UI form
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def apply(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """Kembalikan audio asli tanpa perubahan."""
        return audio.copy()

    def get_params(self) -> dict:
        return {}  # Tidak ada parameter yang perlu dikonfigurasi

    @staticmethod
    def is_available() -> bool:
        return True  # Selalu tersedia, tidak butuh dependensi eksternal

    @classmethod
    def get_display_name(cls) -> str:
        return "Passthrough (no filtering)"
