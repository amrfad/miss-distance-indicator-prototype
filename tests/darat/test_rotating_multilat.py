"""
Unit Tests for 5-Mic Leave-One-Out Rotating Multilateration SSL Method
(darat/localization/builtin_ssl/rotating_multilat.py)

Pengujian:
1. Akurasi eksak (error ~0.000 m) pada TDOA ideal
2. Kekebalan terhadap outlier TDOA (agregasi median rotasi LOO)
3. Ketahanan terhadap noise Gaussian mikrodetik
4. Penanganan jumlah mikrofon < 5 secara aman
5. Integrasi penuh dengan ssl_registry dan process_event_tdoa()
"""

import os
import sys
import unittest
import numpy as np

# Tambahkan path root ke sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from darat.localization.builtin_ssl import rotating_multilat
from darat.localization import ssl_registry
from darat.localization.process_json_tdoa import process_event_tdoa

# Inisialisasi registry
ssl_registry.initialize()


class TestRotatingMultilat(unittest.TestCase):

    def setUp(self):
        self.c = 343.0
        self.config = {
            "speed_of_sound": self.c,
            "multilat_min_mics": 5,
            "multilat_max_norm": 200.0,
            "multilat_aggregate": "median",
        }
        # 6 mikrofon array prototype
        self.mic_positions = {
            "mic0": [-1.58,  0.77,  0.09],
            "mic1": [ 1.60,  0.77,  0.09],
            "mic2": [-0.59, -0.92, -0.07],
            "mic3": [ 0.59, -0.92, -0.05],
            "mic4": [-0.50, -0.11, -0.16],
            "mic5": [ 0.13, -0.01, -0.17],
        }
        self.mic_arr = np.array([self.mic_positions[f"mic{i}"] for i in range(6)])
        self.p_cpa = np.array([3.0, 5.0, 4.0])

        # Generate ground truth TDOA
        t_arr = np.linalg.norm(self.mic_arr - self.p_cpa, axis=1) / self.c
        self.ideal_tdoa = {}
        for i in range(6):
            for j in range(i + 1, 6):
                self.ideal_tdoa[f"mic{i}-mic{j}"] = float(t_arr[i] - t_arr[j])

    def test_display_name_and_contract(self):
        self.assertTrue(hasattr(rotating_multilat, "DISPLAY_NAME"))
        self.assertEqual(rotating_multilat.DISPLAY_NAME, "Rotating Multilateration (5-Mic LOO)")
        self.assertTrue(callable(rotating_multilat.solve))

    def test_ideal_tdoa_exact_solution(self):
        event_data = {"tdoa": self.ideal_tdoa}
        pos, n_subsets, info = rotating_multilat.solve(event_data, self.mic_positions, self.config)

        self.assertIsNotNone(pos)
        self.assertEqual(len(pos), 3)
        self.assertEqual(n_subsets, 6)  # C(6, 5) = 6 subsets lulus semua
        err = np.linalg.norm(np.array(pos) - self.p_cpa)
        self.assertLess(err, 1e-3, f"Error ideal harus sangat kecil, dapat: {err}")

    def test_outlier_rejection_median(self):
        # Rusak satu pasangan TDOA dengan offset ekstrem (outlier 20 ms)
        corrupted_tdoa = dict(self.ideal_tdoa)
        corrupted_tdoa["mic0-mic1"] += 0.020

        event_data = {"tdoa": corrupted_tdoa}
        pos, n_subsets, info = rotating_multilat.solve(event_data, self.mic_positions, self.config)

        self.assertIsNotNone(pos)
        err = np.linalg.norm(np.array(pos) - self.p_cpa)
        # Median harus mengeliminasi subset yang tercemar mic0 atau mic1
        self.assertLess(err, 0.05, f"Error dengan outlier harus tetap rendah, dapat: {err}")

    def test_gaussian_noise_robustness(self):
        rng = np.random.default_rng(42)
        noisy_tdoa = {}
        # Tambah noise Gaussian 50 mikrodetik
        for k, v in self.ideal_tdoa.items():
            noisy_tdoa[k] = v + float(rng.normal(0, 50e-6))

        event_data = {"tdoa": noisy_tdoa}
        pos, n_subsets, info = rotating_multilat.solve(event_data, self.mic_positions, self.config)

        self.assertIsNotNone(pos)
        err = np.linalg.norm(np.array(pos) - self.p_cpa)
        self.assertLess(err, 5.0, f"Error pada noise 50us harus wajar (< 5.0m), dapat: {err}")

    def test_insufficient_microphones(self):
        # Hanya 4 mikrofon (tidak cukup untuk rank 4 full)
        four_mics = {f"mic{i}": self.mic_positions[f"mic{i}"] for i in range(4)}
        event_data = {"tdoa": self.ideal_tdoa}
        pos, n_subsets, info = rotating_multilat.solve(event_data, four_mics, self.config)

        self.assertIsNone(pos)
        self.assertEqual(n_subsets, 0)
        self.assertTrue(len(info) > 0)

    def test_registry_integration(self):
        methods = ssl_registry.get_available_methods()
        method_keys = [k for k, _ in methods]
        self.assertIn("rotating_multilat", method_keys)

        entry = ssl_registry.get_method("rotating_multilat")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.display_name, "Rotating Multilateration (5-Mic LOO)")

    def test_process_event_tdoa_pipeline(self):
        event_data = {"tdoa": self.ideal_tdoa}
        pos, n_subsets, info = process_event_tdoa(
            event_data, self.mic_positions, method="rotating_multilat"
        )
        self.assertIsNotNone(pos)
        self.assertEqual(len(pos), 3)
        self.assertEqual(n_subsets, 6)
        err = np.linalg.norm(np.array(pos) - self.p_cpa)
        self.assertLess(err, 1e-3)


if __name__ == "__main__":
    unittest.main()
