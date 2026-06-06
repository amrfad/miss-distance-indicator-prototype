"""
Tests for process_json_tdoa.py + builtin_ssl (refactored dengan plugin system)

Verifikasi:
1. ssl_registry dapat memuat semua built-in methods
2. bucher_misra._solve_4station() menghasilkan solusi valid
3. bucher_misra._cluster_solutions() mengelompokkan titik dengan benar
4. process_event_tdoa() memproses event dari fixture JSON menggunakan registry
5. save_results_to_file() menghasilkan file dengan format yang benar
6. Backward compat: proses_event_tdoa tetap menerima method key baru

Jalankan: python -m pytest tests/darat/test_process_json_tdoa.py -v
Atau:      python tests/darat/test_process_json_tdoa.py
"""

import sys
import os
import json
import tempfile
import unittest

# Tambahkan root project ke sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "."))

# Inisialisasi registry sebelum semua test (satu kali)
from darat import ssl_registry as _registry_module
_registry_module.initialize()

from darat.process_json_tdoa import (
    process_event_tdoa,
    save_results_to_file,
)
from darat.builtin_ssl import bucher_misra as _bm
from darat.config_manager import get_global_config_manager

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")

# Ambil mic_positions dari config (atau fallback ke fixture)
_cfg = get_global_config_manager().get_config()
MIC_POSITIONS = _cfg.get("mic_positions", {})


class TestSSLRegistry(unittest.TestCase):
    """Verifikasi bahwa ssl_registry berhasil memuat semua built-in methods."""

    def test_builtin_methods_loaded(self):
        methods = _registry_module.get_available_methods()
        keys = [k for k, _ in methods]
        self.assertIn("bucher_misra", keys, "Bucher-Misra harus terdaftar")
        self.assertIn("chan_ho", keys, "Chan-Ho harus terdaftar")
        self.assertIn("pivot", keys, "Pivot harus terdaftar")
        self.assertIn("consensus", keys, "Consensus harus terdaftar")

    def test_default_key_is_bucher_misra(self):
        self.assertEqual(_registry_module.get_default_key(), "bucher_misra")

    def test_get_method_returns_entry(self):
        entry = _registry_module.get_method("bucher_misra")
        self.assertIsNotNone(entry)
        self.assertTrue(callable(entry.solve))

    def test_get_nonexistent_method_returns_none(self):
        entry = _registry_module.get_method("method_yang_tidak_ada_xyz")
        self.assertIsNone(entry)

    def test_all_builtins_have_display_name(self):
        for key in ["bucher_misra", "chan_ho", "pivot", "consensus"]:
            entry = _registry_module.get_method(key)
            self.assertIsNotNone(entry)
            self.assertIsInstance(entry.display_name, str)
            self.assertGreater(len(entry.display_name), 0)


class TestBucherMisraSolver(unittest.TestCase):
    """Unit tests untuk solver Bucher-Misra (dari builtin_ssl)."""

    def test_solve_4station_returns_list(self):
        stations = [
            [-1.58, 0.77, 0.09],
            [1.60,  0.77, 0.09],
            [-0.59, -0.92, -0.07],
            [0.59,  -0.92, -0.05],
        ]
        ranges = [0.0, 0.5, -0.3, 0.2]
        result = _bm._solve_4station(stations, ranges)
        self.assertIsInstance(result, list)

    def test_solve_4station_returns_3d_tuples(self):
        stations = [
            [-1.58, 0.77, 0.09],
            [1.60,  0.77, 0.09],
            [-0.59, -0.92, -0.07],
            [0.59,  -0.92, -0.05],
        ]
        result = _bm._solve_4station(stations, [0.0, 1.0, -0.5, 0.3])
        for sol in result:
            self.assertEqual(len(sol), 3)
            for coord in sol:
                self.assertIsInstance(coord, float)

    def test_cluster_solutions_empty(self):
        self.assertEqual(_bm._cluster_solutions([]), [])

    def test_cluster_solutions_single_point(self):
        result = _bm._cluster_solutions([(1.0, 2.0, 3.0)])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 1)

    def test_cluster_close_points_merge(self):
        p1 = (0.0, 0.0, 0.0)
        p2 = (0.5, 0.0, 0.0)  # jarak 0.5 < eps=1.0
        result = _bm._cluster_solutions([p1, p2], eps=1.0)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 2)

    def test_cluster_far_points_separate(self):
        p1 = (0.0, 0.0, 0.0)
        p2 = (5.0, 0.0, 0.0)  # jarak 5.0 > eps=1.0
        result = _bm._cluster_solutions([p1, p2], eps=1.0)
        self.assertEqual(len(result), 2)

    def test_cluster_sorted_by_size_descending(self):
        big   = [(0.0, 0.0, 0.0), (0.1, 0.0, 0.0), (0.2, 0.0, 0.0)]
        small = [(10.0, 0.0, 0.0)]
        result = _bm._cluster_solutions(big + small, eps=1.0)
        self.assertGreaterEqual(len(result[0]), len(result[-1]))


class TestProcessEventTdoa(unittest.TestCase):
    """Integration tests untuk process_event_tdoa() dengan fixture JSON."""

    @classmethod
    def setUpClass(cls):
        fixture_path = os.path.join(FIXTURES_DIR, "sample_tdoa.json")
        with open(fixture_path) as f:
            cls.data = json.load(f)
        cls.events = cls.data.get("events", [])

    def test_fixture_loaded(self):
        self.assertGreater(len(self.events), 0, "Fixture harus memiliki minimal 1 event")

    def test_process_returns_tuple_of_3(self):
        if not self.events or not MIC_POSITIONS:
            self.skipTest("Tidak ada event atau mic_positions untuk diuji")
        event = self.events[0]
        result = process_event_tdoa(event, MIC_POSITIONS)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_process_with_bucher_misra(self):
        if not self.events or not MIC_POSITIONS:
            self.skipTest("Tidak ada event atau mic_positions untuk diuji")
        event = self.events[0]
        pos, cluster_size, info = process_event_tdoa(
            event, MIC_POSITIONS, method="bucher_misra"
        )
        # pos boleh None jika fixture tidak cocok, tapi tidak boleh crash
        self.assertTrue(pos is None or isinstance(pos, (list, tuple)))

    def test_process_with_chan_ho(self):
        if not self.events or not MIC_POSITIONS:
            self.skipTest("Tidak ada event atau mic_positions untuk diuji")
        event = self.events[0]
        pos, cluster_size, info = process_event_tdoa(
            event, MIC_POSITIONS, method="chan_ho"
        )
        self.assertTrue(pos is None or isinstance(pos, (list, tuple)))

    def test_process_unknown_method_fallback(self):
        """Metode tidak dikenal harus fallback ke default (tidak crash)."""
        if not self.events or not MIC_POSITIONS:
            self.skipTest("Tidak ada event atau mic_positions untuk diuji")
        event = self.events[0]
        # Tidak boleh raise exception, boleh return None
        try:
            result = process_event_tdoa(event, MIC_POSITIONS, method="metode_xyz_tidak_ada")
            self.assertIsInstance(result, tuple)
            self.assertEqual(len(result), 3)
        except Exception as e:
            self.fail(f"Seharusnya tidak raise exception: {e}")

    def test_all_events_dont_crash(self):
        """Semua event di fixture harus bisa diproses tanpa exception."""
        if not MIC_POSITIONS:
            self.skipTest("Tidak ada mic_positions untuk diuji")
        for event in self.events:
            try:
                pos, size, info = process_event_tdoa(event, MIC_POSITIONS)
            except Exception as e:
                self.fail(f"process_event_tdoa raised exception: {e}")

    def test_dead_code_not_in_process_module(self):
        """Pastikan simbol lama yang dipindah tidak ada di process_json_tdoa."""
        import darat.process_json_tdoa as m
        self.assertFalse(
            hasattr(m, "bucher_misra_3d"),
            "bucher_misra_3d harus sudah dipindah ke builtin_ssl.bucher_misra"
        )
        self.assertFalse(
            hasattr(m, "_cluster_solutions"),
            "_cluster_solutions harus sudah dipindah ke builtin_ssl"
        )
        self.assertFalse(
            hasattr(m, "BucherMisraError"),
            "BucherMisraError harus sudah dipindah ke builtin_ssl.bucher_misra"
        )


class TestSaveResultsToFile(unittest.TestCase):
    """Tests untuk save_results_to_file()."""

    _MIC_POS = {
        "mic0": {"x": 0.0, "y": 0.0, "z": 0.0},
        "mic1": {"x": 1.0, "y": 0.0, "z": 0.0},
    }

    def test_saves_file(self):
        events_results = [
            {
                "event_number": 1,
                "estimated_position": [1.0, 2.0, 3.0],
                "cluster_size": 5,
                "clusters_info": ["Cluster 1: 5 solusi, centroid=[1.00, 2.00, 3.00]"],
            }
        ]
        data = {"session_id": "test", "timestamp": "2025-01-01"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            output_path = f.name

        try:
            save_results_to_file(data, events_results, self._MIC_POS, output_path)
            self.assertTrue(os.path.exists(output_path))

            with open(output_path) as f:
                content = f.read()

            self.assertIn("MICROPHONE POSITIONS", content)
            self.assertIn("EVENT POSITIONS", content)
            self.assertIn("e1 = [1.00, 2.00, 3.00]", content)
            self.assertIn("mic0", content)
        finally:
            os.unlink(output_path)

    def test_saves_failed_event(self):
        events_results = [
            {
                "event_number": 1,
                "estimated_position": None,
                "cluster_size": 0,
                "clusters_info": None,
            }
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            output_path = f.name

        try:
            save_results_to_file({}, events_results, self._MIC_POS, output_path)
            with open(output_path) as f:
                content = f.read()
            self.assertIn("e1 = FAILED", content)
        finally:
            os.unlink(output_path)

    def test_saves_event_without_cluster_info(self):
        """Metode yang return cluster_size=None tidak boleh crash saat disimpan."""
        events_results = [
            {
                "event_number": 1,
                "estimated_position": [4.0, 5.0, 6.0],
                "cluster_size": None,
                "clusters_info": None,
            }
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            output_path = f.name

        try:
            save_results_to_file({}, events_results, self._MIC_POS, output_path)
            with open(output_path) as f:
                content = f.read()
            self.assertIn("e1 = [4.00, 5.00, 6.00]", content)
        finally:
            os.unlink(output_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
