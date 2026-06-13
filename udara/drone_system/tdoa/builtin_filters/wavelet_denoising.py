"""
Wavelet Denoising Filter
Menggunakan Discrete Wavelet Transform (pywt) untuk noise reduction.
"""

import numpy as np
from ..base_filter import BaseAudioFilter

try:
    import pywt
    _PYWT_AVAILABLE = True
except ImportError:
    _PYWT_AVAILABLE = False


class WaveletDenoisingFilter(BaseAudioFilter):
    """
    Noise reduction berbasis Discrete Wavelet Transform (DWT).

    Algoritma:
      1. Decompose sinyal menggunakan DWT ke N level
      2. Estimasi threshold noise menggunakan MAD (Median Absolute Deviation)
         pada koefisien detail level pertama (level 1 = frekuensi tinggi)
      3. Terapkan soft/hard thresholding pada semua koefisien detail
      4. Rekonstruksi sinyal dari koefisien yang sudah di-threshold

    Keunggulan: Tidak ada edge artifacts, komputasi lebih ringan dari spectral gating.
    """

    def __init__(
        self,
        wavelet: str = "db8",
        level: int = 4,
        mode: str = "soft",
        normalize: bool = False,
        **kwargs,
    ):
        """
        Args:
            wavelet (str): Nama wavelet basis (e.g. 'db4', 'db8', 'sym8', 'coif5').
            level (int): Jumlah level dekomposisi DWT.
            mode (str): 'soft' atau 'hard' thresholding.
            normalize (bool): Normalisasi output audio.
        """
        super().__init__(**kwargs)
        self.wavelet = str(wavelet)
        self.level = int(level)
        self.mode = str(mode)
        self.normalize = bool(normalize)

    def apply(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        if not _PYWT_AVAILABLE:
            print("[WaveletDenoising] pywt tidak tersedia, mengembalikan audio asli")
            return audio

        # Decompose
        coeffs = pywt.wavedec(audio, self.wavelet, level=self.level)

        # Estimasi sigma dari koefisien detail level 1 (MAD estimator)
        detail_1 = coeffs[-1]
        sigma = np.median(np.abs(detail_1)) / 0.6745
        # Universal threshold (VisuShrink)
        threshold = sigma * np.sqrt(2 * np.log(len(audio)))

        # Apply thresholding pada semua detail coefficients (bukan approximation)
        new_coeffs = [coeffs[0]]  # approximation tidak di-threshold
        for detail in coeffs[1:]:
            new_coeffs.append(pywt.threshold(detail, value=threshold, mode=self.mode))

        # Reconstruct
        filtered = pywt.waverec(new_coeffs, self.wavelet)

        # Pastikan panjang sama dengan input (waverec bisa menambah 1 sample)
        filtered = filtered[:len(audio)]

        # Optional normalization
        if self.normalize:
            peak = np.max(np.abs(filtered))
            if peak > 0:
                filtered = filtered / peak

        # Clip ke valid range
        filtered = np.clip(filtered, -1.0, 1.0)

        return filtered.astype(audio.dtype)

    def get_params(self) -> dict:
        return {
            "wavelet": {
                "value": self.wavelet,
                "type": "str",
                "description": "Nama wavelet basis (db4, db8, sym8, coif5, dll)",
            },
            "level": {
                "value": self.level,
                "type": "int",
                "min": 1,
                "max": 10,
                "step": 1,
                "description": "Jumlah level dekomposisi DWT (lebih tinggi = lebih banyak noise dihapus)",
            },
            "mode": {
                "value": self.mode,
                "type": "str",
                "description": "Mode thresholding: 'soft' (halus) atau 'hard' (tegas)",
            },
            "normalize": {
                "value": self.normalize,
                "type": "bool",
                "description": "Normalisasi output audio",
            },
        }

    @staticmethod
    def is_available() -> bool:
        return _PYWT_AVAILABLE

    @classmethod
    def get_display_name(cls) -> str:
        return "Wavelet Denoising (pywt)"
