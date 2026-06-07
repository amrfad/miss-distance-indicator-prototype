"""
Base Audio Filter — Strategy Pattern Contract
Semua filter (built-in maupun custom) harus mewarisi class ini.
"""

from abc import ABC, abstractmethod
import numpy as np


class BaseAudioFilter(ABC):
    """
    Abstract base class untuk semua metode audio filtering.

    Setiap subclass wajib mengimplementasikan:
        - apply(audio, sample_rate) -> np.ndarray
        - get_params() -> dict
        - is_available() -> bool  (classmethod/staticmethod)

    Contoh penggunaan:
        FilterClass = filter_registry.get_method_class("spectral_gating")
        params = cfg.get("filter_configs", {}).get("spectral_gating", {})
        f = FilterClass(**params)
        filtered = f.apply(audio_1d, sample_rate)
    """

    def __init__(self, **kwargs):
        """
        Menerima konfigurasi unik untuk metode ini sebagai keyword arguments.
        Subclass harus memanggil super().__init__(**kwargs) dan menyimpan
        parameter yang relevan.
        """
        pass

    @abstractmethod
    def apply(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Memproses audio 1D array dan mengembalikan array terfilter.

        Args:
            audio (np.ndarray): Array 1D float32/float64 audio data.
            sample_rate (int): Sample rate audio dalam Hz.

        Returns:
            np.ndarray: Filtered audio array dengan dimensi dan dtype yang sama.
        """

    @abstractmethod
    def get_params(self) -> dict:
        """
        Mengembalikan dictionary parameter default metode ini.
        Format: {param_name: {"value": default_value, "type": "float"|"int"|"bool"|"str",
                               "min": ..., "max": ..., "description": "..."}}

        Digunakan oleh Ground Station untuk merender form UI secara dinamis.
        """

    @staticmethod
    @abstractmethod
    def is_available() -> bool:
        """
        Mengembalikan True jika semua dependensi library filter terpenuhi.
        Digunakan oleh registry untuk memfilter metode yang tidak dapat dijalankan
        di environment saat ini.
        """

    @classmethod
    def get_display_name(cls) -> str:
        """
        Nama tampilan ramah pengguna untuk method ini.
        Override di subclass jika nama berbeda dari class name.
        """
        return cls.__name__
