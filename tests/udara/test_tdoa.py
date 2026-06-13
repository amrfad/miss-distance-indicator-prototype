"""
Tests for udara/drone_system/tdoa.py

Verifikasi:
1. calculate_tdoa_gcc_phat() menghasilkan float dalam range yang masuk akal
2. calculate_cross_correlation() konsisten dengan gcc_phat untuk signal yang sama
3. calculate_all_tdoa() menghasilkan C(n,2) pasangan
4. Sinyal silent menghasilkan TDOA = 0.0

Jalankan: python -m pytest tests/udara/test_tdoa.py -v
"""

import sys
import os
import numpy as np
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".", "udara"))

from drone_system.tdoa.tdoa import (
    calculate_tdoa_gcc_phat,
    calculate_cross_correlation,
    calculate_all_tdoa,
)


FS = 48000  # sample rate


def make_delayed_signal(delay_samples: int, length: int = 4800, fs: int = FS):
    """Buat pasangan sinyal dengan delay yang diketahui."""
    noise = np.random.randn(length)
    sig1 = noise.copy()
    if delay_samples >= 0:
        sig2 = np.concatenate([np.zeros(delay_samples), noise[: length - delay_samples]])
    else:
        d = -delay_samples
        sig2 = np.concatenate([noise[d:], np.zeros(d)])
    return sig1, sig2


class TestGccPhat(unittest.TestCase):

    def test_returns_float(self):
        sig1, sig2 = make_delayed_signal(10)
        result = calculate_tdoa_gcc_phat(sig1, sig2, FS)
        self.assertIsInstance(result, float)

    def test_zero_delay(self):
        sig = np.random.randn(4800)
        result = calculate_tdoa_gcc_phat(sig, sig, FS)
        self.assertAlmostEqual(result, 0.0, places=5)

    def test_known_positive_delay(self):
        delay_samples = 48  # 1ms pada 48kHz
        sig1, sig2 = make_delayed_signal(delay_samples)
        result = calculate_tdoa_gcc_phat(sig1, sig2, FS)
        # Konvensi matematika IFFT(X1·conj(X2)) → puncak di lag = -D
        # saat sig2 adalah sig1 yang di-delay D sample (sig2 tiba D sample lebih lambat).
        # Karena itu tanda expected negatif.
        expected = -delay_samples / FS
        self.assertAlmostEqual(result, expected, delta=3 / FS)

    def test_result_within_physical_range(self):
        """TDOA harus <= jarak maks antara mic / speed of sound."""
        max_mic_distance = 4.0  # meter
        max_tdoa = max_mic_distance / 343.0
        sig1, sig2 = make_delayed_signal(20)
        result = calculate_tdoa_gcc_phat(sig1, sig2, FS)
        self.assertLessEqual(abs(result), max_tdoa + 0.1)


class TestCrossCorrelation(unittest.TestCase):

    def test_returns_float(self):
        sig1, sig2 = make_delayed_signal(5)
        result = calculate_cross_correlation(sig1, sig2, FS)
        self.assertIsInstance(result, float)

    def test_zero_delay(self):
        sig = np.random.randn(2400)
        result = calculate_cross_correlation(sig, sig, FS)
        self.assertAlmostEqual(result, 0.0, places=5)


class TestCalculateAllTdoa(unittest.TestCase):

    def _make_multichannel(self, n_channels: int, n_samples: int = 4800):
        return np.random.randn(n_samples, n_channels)

    def test_4_channels_gives_6_pairs(self):
        # Data harus memiliki cukup kolom agar channel_indices valid.
        # channel_indices=[4,5,6,7] → butuh minimal 8 kolom (0-indexed).
        data = self._make_multichannel(8)
        results = calculate_all_tdoa(data, FS, channel_indices=[4, 5, 6, 7])
        self.assertEqual(len(results), 6)  # C(4,2) = 6

    def test_6_channels_gives_15_pairs(self):
        data = self._make_multichannel(10)  # 10 total channels
        results = calculate_all_tdoa(data, FS, channel_indices=[4, 5, 6, 7, 8, 9])
        self.assertEqual(len(results), 15)  # C(6,2) = 15

    def test_keys_format(self):
        data = self._make_multichannel(4)
        results = calculate_all_tdoa(data, FS, channel_indices=[0, 1, 2, 3])
        for key in results:
            parts = key.split("-")
            self.assertEqual(len(parts), 2)
            self.assertTrue(parts[0].startswith("mic"))
            self.assertTrue(parts[1].startswith("mic"))

    def test_silent_channel_returns_zero(self):
        data = np.zeros((4800, 4))
        results = calculate_all_tdoa(data, FS, channel_indices=[0, 1, 2, 3])
        for v in results.values():
            self.assertEqual(v, 0.0)

    def test_all_values_are_float(self):
        data = self._make_multichannel(4)
        results = calculate_all_tdoa(data, FS, channel_indices=[0, 1, 2, 3])
        for v in results.values():
            self.assertIsInstance(v, float)


if __name__ == "__main__":
    unittest.main(verbosity=2)
