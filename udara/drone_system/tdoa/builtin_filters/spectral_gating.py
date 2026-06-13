"""
Spectral Gating Filter (DEFAULT)
Mengadaptasi logika orisinal dari processor.py:
  - Trimming 0.8s awal dan akhir untuk menghindari spectral gating artifacts
  - Clipping ke [-1.0, 1.0]
  - Optional normalization
"""

import os
import ctypes
from contextlib import redirect_stderr

import numpy as np

from ..base_filter import BaseAudioFilter


# ── Mute ALSA warnings (Linux) ─────────────────────────────────────
try:
    _asound = ctypes.CDLL('libasound.so.2')
    try:
        _asound.snd_lib_error_set_handler(ctypes.c_void_p(0))
    except Exception:
        pass
except Exception:
    pass

# ── Import noisereduce dengan muted stderr ──────────────────────────
try:
    with open(os.devnull, "w") as _d:
        with redirect_stderr(_d):
            import noisereduce as nr
    _NOISEREDUCE_AVAILABLE = True
except Exception:
    _NOISEREDUCE_AVAILABLE = False


class SpectralGatingFilter(BaseAudioFilter):
    """
    Spectral Gating noise reduction menggunakan library noisereduce.

    Ini adalah metode DEFAULT sistem. Logika diadaptasi persis dari
    AudioProcessor.filter_channels() di processor.py termasuk:
      - trimming 0.8s untuk menghindari spectral gating artifacts
      - clipping [-1.0, 1.0]
      - optional normalization
    """

    TRIM_DURATION = 0.8  # seconds — sesuai dengan processor.py

    def __init__(
        self,
        prop_decrease: float = 1.0,
        freq_mask_smooth_hz: int = 100,
        time_mask_smooth_ms: int = 10,
        stationary: bool = False,
        normalize: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.prop_decrease = float(prop_decrease)
        self.freq_mask_smooth_hz = int(freq_mask_smooth_hz)
        self.time_mask_smooth_ms = int(time_mask_smooth_ms)
        self.stationary = bool(stationary)
        self.normalize = bool(normalize)

    def apply(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Terapkan spectral gating ke audio 1D.

        Mengikuti presisi logika di processor.py:
        1. Jalankan noisereduce.reduce_noise pada audio penuh
        2. Trim 0.8s dari awal dan akhir (menghilangkan artifact)
        3. Normalisasi jika diminta
        4. Clip ke [-1.0, 1.0]
        """
        if not _NOISEREDUCE_AVAILABLE:
            print("[SpectralGating] noisereduce tidak tersedia, mengembalikan audio asli")
            return audio

        trim_samples = int(self.TRIM_DURATION * sample_rate)
        n_samples = len(audio)

        # Jalankan noise reduction pada audio penuh
        filtered = nr.reduce_noise(
            y=audio,
            sr=sample_rate,
            stationary=self.stationary,
            prop_decrease=self.prop_decrease,
            freq_mask_smooth_hz=self.freq_mask_smooth_hz,
            time_mask_smooth_ms=self.time_mask_smooth_ms,
        )

        # Trim awal dan akhir untuk menghilangkan spectral gating artifacts
        if n_samples > 2 * trim_samples:
            filtered = filtered[trim_samples:-trim_samples]
        # else: audio terlalu pendek, kembalikan tanpa trim

        # Optional normalization
        if self.normalize:
            peak = np.max(np.abs(filtered))
            if peak > 0:
                filtered = filtered / peak

        # Clip ke valid range
        filtered = np.clip(filtered, -1.0, 1.0)

        return filtered

    def get_params(self) -> dict:
        return {
            "prop_decrease": {
                "value": self.prop_decrease,
                "type": "float",
                "min": 0.0,
                "max": 1.0,
                "step": 0.1,
                "description": "Proporsi pengurangan noise (0.0 = none, 1.0 = maximum)",
            },
            "freq_mask_smooth_hz": {
                "value": self.freq_mask_smooth_hz,
                "type": "int",
                "min": 10,
                "max": 2000,
                "step": 10,
                "description": "Smoothing di domain frekuensi (Hz)",
            },
            "time_mask_smooth_ms": {
                "value": self.time_mask_smooth_ms,
                "type": "int",
                "min": 1,
                "max": 200,
                "step": 5,
                "description": "Smoothing di domain waktu (ms)",
            },
            "stationary": {
                "value": self.stationary,
                "type": "bool",
                "description": "Gunakan model noise stasioner (lebih cepat, kurang fleksibel)",
            },
            "normalize": {
                "value": self.normalize,
                "type": "bool",
                "description": "Normalisasi output audio",
            },
        }

    @staticmethod
    def is_available() -> bool:
        return _NOISEREDUCE_AVAILABLE

    @classmethod
    def get_display_name(cls) -> str:
        return "Spectral Gating (noisereduce)"
