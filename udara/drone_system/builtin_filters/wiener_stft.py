"""
Wiener STFT Filter
Menggunakan Wiener filtering berbasis Short-Time Fourier Transform (scipy.signal).
"""

import numpy as np
from ..base_filter import BaseAudioFilter

try:
    from scipy import signal as scipy_signal
    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False


class WienerStftFilter(BaseAudioFilter):
    """
    Noise reduction berbasis Wiener filtering + STFT.

    Algoritma:
      1. Hitung STFT dari sinyal input
      2. Estimasi power spectral density (PSD) noise dari frame awal
         (asumsi: frame pertama berisi noise dominan)
      3. Hitung Wiener filter gain: G(f) = S_signal / (S_signal + S_noise)
      4. Terapkan gain pada setiap frame STFT
      5. Rekonstruksi sinyal via ISTFT

    Keunggulan: Optimal secara MSE untuk Gaussian noise stasioner.
    Kekurangan: Sensitif terhadap estimasi noise; kurang efektif untuk non-stasioner.
    """

    def __init__(
        self,
        n_fft: int = 1024,
        hop_length: int = 256,
        noise_frames: int = 10,
        alpha: float = 0.98,
        normalize: bool = False,
        **kwargs,
    ):
        """
        Args:
            n_fft (int): Ukuran FFT window.
            hop_length (int): Jumlah sample antar frame STFT.
            noise_frames (int): Jumlah frame awal yang digunakan sebagai estimasi noise.
            alpha (float): Smoothing factor untuk PSD noise (0=no smooth, 1=full smooth).
            normalize (bool): Normalisasi output audio.
        """
        super().__init__(**kwargs)
        self.n_fft = int(n_fft)
        self.hop_length = int(hop_length)
        self.noise_frames = int(noise_frames)
        self.alpha = float(alpha)
        self.normalize = bool(normalize)

    def apply(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        if not _SCIPY_AVAILABLE:
            print("[WienerStft] scipy tidak tersedia, mengembalikan audio asli")
            return audio

        # STFT
        freqs, times, Zxx = scipy_signal.stft(
            audio,
            fs=sample_rate,
            nperseg=self.n_fft,
            noverlap=self.n_fft - self.hop_length,
        )

        magnitude = np.abs(Zxx)
        phase = np.angle(Zxx)

        # Estimasi PSD noise dari frame awal
        n_frames = magnitude.shape[1]
        n_noise = min(self.noise_frames, n_frames)
        noise_psd = np.mean(magnitude[:, :n_noise] ** 2, axis=1, keepdims=True)

        # Signal PSD estimation dengan smoothing
        signal_psd = magnitude ** 2
        # Smoothed over time (running average)
        smoothed_signal_psd = np.zeros_like(signal_psd)
        smoothed_signal_psd[:, 0] = signal_psd[:, 0]
        for t in range(1, n_frames):
            smoothed_signal_psd[:, t] = (
                self.alpha * smoothed_signal_psd[:, t - 1]
                + (1 - self.alpha) * signal_psd[:, t]
            )

        # Wiener gain: G = max(0, 1 - noise_psd / signal_psd)
        gain = np.maximum(0.0, 1.0 - noise_psd / (smoothed_signal_psd + 1e-10))

        # Terapkan gain
        Zxx_filtered = gain * magnitude * np.exp(1j * phase)

        # ISTFT
        _, filtered = scipy_signal.istft(
            Zxx_filtered,
            fs=sample_rate,
            nperseg=self.n_fft,
            noverlap=self.n_fft - self.hop_length,
        )

        # Pastikan panjang sama dengan input
        filtered = filtered[:len(audio)]
        if len(filtered) < len(audio):
            filtered = np.pad(filtered, (0, len(audio) - len(filtered)))

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
            "n_fft": {
                "value": self.n_fft,
                "type": "int",
                "min": 128,
                "max": 4096,
                "step": 128,
                "description": "Ukuran FFT window (samples)",
            },
            "hop_length": {
                "value": self.hop_length,
                "type": "int",
                "min": 64,
                "max": 1024,
                "step": 64,
                "description": "Jumlah sample antar frame STFT",
            },
            "noise_frames": {
                "value": self.noise_frames,
                "type": "int",
                "min": 1,
                "max": 50,
                "step": 1,
                "description": "Jumlah frame awal untuk estimasi noise",
            },
            "alpha": {
                "value": self.alpha,
                "type": "float",
                "min": 0.0,
                "max": 1.0,
                "step": 0.01,
                "description": "Smoothing factor PSD noise (0=none, 1=full)",
            },
            "normalize": {
                "value": self.normalize,
                "type": "bool",
                "description": "Normalisasi output audio",
            },
        }

    @staticmethod
    def is_available() -> bool:
        return _SCIPY_AVAILABLE

    @classmethod
    def get_display_name(cls) -> str:
        return "Wiener STFT (scipy)"
