"""
Tests for ECCCT Module and Comb-Notch Filter (Phase 1 Integration)

Verifikasi:
1. extract_envelope_curves() menghasilkan dimensi ter-decimasi dan ternormalisasi global.
2. cross_correlation_envelope_tdoa() mengestimasi delay dengan refinemen sub-bin parabolik.
3. closure_tune() mengurangi atau mempertahankan residual inkonsistensi segitiga (r1 <= r0).
4. calculate_all_tdoa_eccct() menghasilkan C(N, 2) pasangan dengan format yang identik.
5. CombNotchFilter meredam frekuensi harmonik mesin secara zero-phase.
"""

import os
import sys
import unittest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "udara"))

from drone_system.tdoa.eccct import (
    extract_envelope_curves,
    cross_correlation_envelope_tdoa,
    closure_tune,
    boxcar_smooth,
)
from drone_system.tdoa.tdoa import (
    calculate_all_tdoa_eccct,
    calculate_all_tdoa,
)
from drone_system.tdoa.builtin_filters.comb_notch import CombNotchFilter
from drone_system.core.config_manager import get_global_config_manager

FS = 48000


class TestEccctCore(unittest.TestCase):

    def test_boxcar_smooth(self):
        x = np.ones(100)
        smoothed = boxcar_smooth(x, width_s=0.002, fs=FS)
        self.assertEqual(len(smoothed), 100)
        self.assertAlmostEqual(smoothed[50], 1.0, places=5)

    def test_extract_envelope_curves(self):
        n_samples = 4800  # 100 ms pada 48 kHz
        n_channels = 6
        dec = 10
        # Buat sinyal pulsa sederhana pada channel 0
        signals = np.zeros((n_samples, n_channels))
        signals[1000:1500, 0] = 1.0
        signals[1020:1520, 1] = 0.8

        E = extract_envelope_curves(signals, fs=FS, smooth_ms=2.0, dec=dec)
        
        # Dimensi harus (n_channels, ceil(n_samples / dec))
        expected_len = len(signals[::dec, 0])
        self.assertEqual(E.shape, (n_channels, expected_len))
        # Nilai maksimum global harus <= 1.0
        self.assertLessEqual(np.max(E), 1.000001)
        self.assertGreater(np.max(E[0]), np.max(E[1]))

    def test_cross_correlation_subbin_accuracy(self):
        # Buat kurva gaussian dengan delay sub-sampel
        dec = 10
        t = np.arange(-200, 200, dtype=float)
        # Pulse 1 di t = 0
        e1 = np.exp(-0.5 * (t / 15.0) ** 2)
        # Pulse 2 di t = 5.25 sampel ter-decimasi
        delay_dec_samples = 5.25
        e2 = np.exp(-0.5 * ((t - delay_dec_samples) / 15.0) ** 2)

        # e1 lebih awal dari e2 -> t_e1 - t_e2 < 0
        tau, peak = cross_correlation_envelope_tdoa(e1, e2, fs=FS, dec=dec)
        expected_tau = -delay_dec_samples * dec / FS
        self.assertAlmostEqual(tau, expected_tau, delta=0.5 * dec / FS)

    def test_closure_tuning_reduces_residual(self):
        # Buat segitiga TDOA yang inkonsisten secara sengaja
        # Seharusnya tau_01 + tau_12 = tau_02
        # Misal: tau_01 = 0.001, tau_12 = 0.002, tapi tau_02 diukur 0.004 (inkonsisten 0.001)
        noisy_tdoa = {
            (0, 1): 0.0010,
            (0, 2): 0.0040,
            (1, 2): 0.0020,
            (0, 3): 0.0015,
            (1, 3): 0.0005,
            (2, 3): -0.0015,
        }
        tuned, r0, r1 = closure_tune(noisy_tdoa, num_mics=4, max_iter=50)
        self.assertLessEqual(r1, r0)
        self.assertLess(r1, 1e-4)


class TestCalculateAllTdoaEccct(unittest.TestCase):

    def test_output_format_and_pair_count(self):
        n_samples = 4800
        n_channels = 8
        active_indices = [2, 3, 4, 5, 6, 7]  # 6 mic
        data = np.random.randn(n_samples, n_channels) * 0.1

        results = calculate_all_tdoa_eccct(data, FS, channel_indices=active_indices)
        # C(6, 2) = 15 pairs
        self.assertEqual(len(results), 15)
        for i in range(6):
            for j in range(i + 1, 6):
                key = f"mic{i}-mic{j}"
                self.assertIn(key, results)
                self.assertIsInstance(results[key], float)

    def test_config_routing_eccct(self):
        data = np.random.randn(2400, 6)
        cm = get_global_config_manager()
        
        # Test mode eccct
        cm.update({"tdoa_method": "eccct"}, source="rest")
        res_eccct = calculate_all_tdoa(data, FS)
        self.assertEqual(len(res_eccct), 15)


class TestCombNotchFilter(unittest.TestCase):

    def test_filter_removes_harmonic(self):
        sample_rate = 48000
        duration = 0.5
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        
        # RPM = 6000 -> f0 = 2 * 6000 / 60 = 200 Hz
        # Buat sinyal dengan komponen mesin di 2000 Hz (harmonik ke-10) dan target di 3500 Hz
        engine_tone = np.sin(2 * np.pi * 2000.0 * t)
        target_tone = np.sin(2 * np.pi * 3500.0 * t)
        combined = engine_tone + target_tone
        
        filt = CombNotchFilter(rpm=6000.0, notch_bw=40.0, f_lo=1500.0, f_hi=6000.0)
        filtered = filt.apply(combined, sample_rate)
        
        # Spektrum FFT
        fft_orig = np.abs(np.fft.rfft(combined))
        fft_filt = np.abs(np.fft.rfft(filtered))
        freqs = np.fft.rfftfreq(len(combined), 1.0 / sample_rate)
        
        idx_2000 = np.argmin(np.abs(freqs - 2000.0))
        idx_3500 = np.argmin(np.abs(freqs - 3500.0))
        
        # Harmonik mesin harus tertekan drastis (> 99%)
        self.assertLess(fft_filt[idx_2000], 0.01 * fft_orig[idx_2000])
        # Frekuensi target di 3500 Hz harus tetap utuh (~ 100%)
        self.assertAlmostEqual(fft_filt[idx_3500] / fft_orig[idx_3500], 1.0, delta=0.05)

    def test_filter_multichannel_2d(self):
        sample_rate = 48000
        data_2d = np.random.randn(2400, 6)
        filt = CombNotchFilter(rpm=4000.0)
        filtered = filt.apply(data_2d, sample_rate)
        self.assertEqual(filtered.shape, (2400, 6))
        self.assertEqual(filtered.dtype, data_2d.dtype)


if __name__ == "__main__":
    unittest.main()
