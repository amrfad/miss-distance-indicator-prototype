"""
Comb-Notch Filter — Zero-Phase Ego-Noise Harmonic Removal
Mengeliminasi harmonik derau mesin UAV (k * f0) dan membatasi spektrum
ke pita wake turbulensi menggunakan operasi zero-phase di domain frekuensi.
"""

from typing import Dict, Any
import numpy as np

from ..base_filter import BaseAudioFilter


class CombNotchFilter(BaseAudioFilter):
    """
    Filter Comb-Notch dan Bandpass zero-phase untuk meredam kebisingan mesin drone (ego-noise).
    
    Fitur:
      1. Menghitung frekuensi fundamental f0 = 2 * RPM / 60.
      2. Meniadakan harmonik k * f0 selebar notch_bw Hz.
      3. Bandpass ideal ke rentang emisi wake supersonik [f_lo, f_hi] Hz.
      4. Zero-phase FFT memastikan tidak ada distorsi inter-channel time delay.
    """

    def __init__(
        self,
        rpm: float = 4000.0,
        notch_bw: float = 40.0,
        f_lo: float = 1500.0,
        f_hi: float = 6000.0,
        enable_bandpass: bool = True,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.rpm = float(rpm)
        self.notch_bw = float(notch_bw)
        self.f_lo = float(f_lo)
        self.f_hi = float(f_hi)
        self.enable_bandpass = bool(enable_bandpass)

    def apply(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Terapkan comb-notch dan bandpass zero-phase pada sinyal 1D atau multi-channel 2D.
        """
        if len(audio) == 0:
            return audio.copy()

        if audio.ndim == 2:
            filtered = np.zeros_like(audio)
            for ch in range(audio.shape[1]):
                filtered[:, ch] = self._apply_1d(audio[:, ch], sample_rate)
            return filtered
        return self._apply_1d(audio, sample_rate)

    def _apply_1d(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        n = len(audio)
        orig_dtype = audio.dtype
        X = np.fft.rfft(audio.astype(float))
        freqs = np.fft.rfftfreq(n, 1.0 / sample_rate)

        keep_mask = np.ones(len(freqs), dtype=bool)

        # 1. Comb-notch filter untuk harmonik mesin
        if self.rpm > 0 and self.notch_bw > 0:
            f0 = 2.0 * self.rpm / 60.0
            half_bw = self.notch_bw / 2.0
            k = 1
            max_freq = sample_rate / 2.0 - half_bw
            while k * f0 < max_freq:
                harmonic = k * f0
                notch_indices = np.abs(freqs - harmonic) < half_bw
                keep_mask[notch_indices] = False
                k += 1

        # 2. Bandpass filter
        if self.enable_bandpass and self.f_hi > self.f_lo:
            bp_mask = (freqs >= self.f_lo) & (freqs <= self.f_hi)
            keep_mask = keep_mask & bp_mask

        # Nolkan bin yang tidak di-keep
        X[~keep_mask] = 0.0

        filtered = np.fft.irfft(X, n=n)
        return filtered.astype(orig_dtype)

    def get_params(self) -> Dict[str, Any]:
        return {
            "rpm": {
                "value": self.rpm,
                "type": "float",
                "min": 0.0,
                "max": 15000.0,
                "step": 100.0,
                "description": "Putaran mesin drone (RPM) untuk estimasi frekuensi fundamental f0",
            },
            "notch_bw": {
                "value": self.notch_bw,
                "type": "float",
                "min": 5.0,
                "max": 200.0,
                "step": 5.0,
                "description": "Lebar notch tiap harmonik mesin (Hz)",
            },
            "f_lo": {
                "value": self.f_lo,
                "type": "float",
                "min": 100.0,
                "max": 10000.0,
                "step": 100.0,
                "description": "Frekuensi cut-off bawah bandpass (Hz)",
            },
            "f_hi": {
                "value": self.f_hi,
                "type": "float",
                "min": 1000.0,
                "max": 24000.0,
                "step": 200.0,
                "description": "Frekuensi cut-off atas bandpass (Hz)",
            },
            "enable_bandpass": {
                "value": self.enable_bandpass,
                "type": "bool",
                "description": "Aktifkan ideal bandpass [f_lo, f_hi]",
            },
        }

    @staticmethod
    def is_available() -> bool:
        return True

    @classmethod
    def get_display_name(cls) -> str:
        return "Comb-Notch & Wake Bandpass (Zero-Phase)"
