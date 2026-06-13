"""
Built-in Filters Package
Berisi metode filtering audio bawaan sistem.
"""

from .spectral_gating import SpectralGatingFilter
from .wavelet_denoising import WaveletDenoisingFilter
from .wiener_stft import WienerStftFilter
from .passthrough import PassthroughFilter

__all__ = [
    "SpectralGatingFilter",
    "WaveletDenoisingFilter",
    "WienerStftFilter",
    "PassthroughFilter",
]

# Registry nama ke class (digunakan oleh filter_registry.py)
BUILTIN_FILTER_MAP = {
    "spectral_gating": SpectralGatingFilter,
    "wavelet_denoising": WaveletDenoisingFilter,
    "wiener_stft": WienerStftFilter,
    "passthrough": PassthroughFilter,
}
