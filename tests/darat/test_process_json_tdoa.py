"""
Tests for process_json_tdoa.py (refactored version)

Verifikasi:
1. bucher_misra_3d() menghasilkan solusi valid
2. _cluster_solutions() mengelompokkan titik dengan benar
3. process_event_tdoa() memproses event dari fixture JSON
4. save_results_to_file() menghasilkan file dengan format yang benar
5. Dead code (find_largest_cluster, select_best_cluster) tidak ada di refactored

Jalankan: python -m pytest tests/darat/test_process_json_tdoa.py -v
Atau:      python tests/darat/test_process_json_tdoa.py
"""

import sys
import os
import json
import tempfile
import unittest

# Tambahkan path refactored ke sys.path agar bisa import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "."))

from darat.process_json_tdoa import (
    bucher_misra_3d,
    _cluster_solutions,
    process_event_tdoa,
    save_results_to_file,
    MIC_POSITIONS,
    SPEED_OF_SOUND,
    BucherMisraError,
)

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


class TestBucherMisra3D(unittest.TestCase):
    """Unit tests untuk solver Bucher-Misra."""

    def test_returns_list(self):
        stations = [
            [-1.58, 0.77, 0.09],
            [1.60, 0.77, 0.09],
            [-0.59, -0.92, -0.07],
            [0.59, -0.92, -0.05],
        ]
        ranges = [0.0, 0.5, -0.3, 0.2]
        result = bucher_misra_3d(stations_xyz=stations, ranges_m=ranges)
        self.assertIsInstance(result, list)

    def test_requires_exactly_4_stations(self):
        with self.assertRaises(ValueError):
            bucher_misra_3d(stations_xyz=[[0, 0, 0], [1, 0, 0]], ranges_m=[0, 0])

    def test_toas_xor_ranges(self):
        stations = [
            [0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]
        ]
        with self.assertRaises(ValueError):
            # Both provided — harus error
            bucher_misra_3d(stations_xyz=stations, toas_s=[0]*4, ranges_m=[0]*4)

    def test_solutions_are_tuples_of_3(self):
        stations = [
            [-1.58, 0.77, 0.09],
            [1.60, 0.77, 0.09],
            [-0.59, -0.92, -0.07],
            [0.59, -0.92, -0.05],
        ]
        result = bucher_misra_3d(stations_xyz=stations, ranges_m=[0.0, 1.0, -0.5, 0.3])
        for sol in result:
            self.assertEqual(len(sol), 3)
            for coord in sol:
                self.assertIsInstance(coord, float)


class TestClusterSolutions(unittest.TestCase):
    """Unit tests untuk _cluster_solutions() yang menggantikan dead code."""

    def test_empty_input(self):
        self.assertEqual(_cluster_solutions([]), [])

    def test_single_point(self):
        result = _cluster_solutions([(1.0, 2.0, 3.0)])
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 1)

    def test_two_close_points_merge(self):
        p1 = (0.0, 0.0, 0.0)
        p2 = (0.5, 0.0, 0.0)  # jarak 0.5 < eps=1.0
        result = _cluster_solutions([p1, p2], eps=1.0)
        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]), 2)

    def test_two_far_points_separate(self):
        p1 = (0.0, 0.0, 0.0)
        p2 = (5.0, 0.0, 0.0)  # jarak 5.0 > eps=1.0
        result = _cluster_solutions([p1, p2], eps=1.0)
        self.assertEqual(len(result), 2)

    def test_sorted_by_size_descending(self):
        # Cluster besar: 3 titik dekat
        big = [(0.0, 0.0, 0.0), (0.1, 0.0, 0.0), (0.2, 0.0, 0.0)]
        # Cluster kecil: 1 titik jauh
        small = [(10.0, 0.0, 0.0)]
        result = _cluster_solutions(big + small, eps=1.0)
        self.assertGreaterEqual(len(result[0]), len(result[-1]))

    def test_dead_code_not_present(self):
        """Pastikan fungsi dead code tidak ada di modul refactored."""
        import darat.process_json_tdoa as m
        self.assertFalse(hasattr(m, "find_largest_cluster"),
                         "find_largest_cluster() harus sudah dihapus (dead code)")
        self.assertFalse(hasattr(m, "select_best_cluster"),
                         "select_best_cluster() harus sudah dihapus (dead code)")


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
        event = self.events[0]
        result = process_event_tdoa(event, MIC_POSITIONS)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 3)

    def test_process_least_squares_method(self):
        event = self.events[0]
        pos, conf, info = process_event_tdoa(event, MIC_POSITIONS, method="least-squares")
        # least-squares boleh gagal tapi harus return tuple
        self.assertIsInstance(conf, int)

    def test_all_events_dont_crash(self):
        """Semua event di fixture harus bisa diproses tanpa exception."""
        for event in self.events:
            try:
                pos, size, info = process_event_tdoa(event, MIC_POSITIONS)
            except Exception as e:
                self.fail(f"process_event_tdoa raised exception: {e}")


class TestSaveResultsToFile(unittest.TestCase):
    """Tests untuk save_results_to_file()."""

    def test_saves_file(self):
        events_results = [
            {
                "event_number": 1,
                "estimated_position": [1.0, 2.0, 3.0],
                "cluster_size": 5,
                "clusters_info": ["Cluster 1: 5 solusi, centroid = [1.00, 2.00, 3.00]"],
            }
        ]
        data = {"session_id": "test", "timestamp": "2025-01-01"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            output_path = f.name

        try:
            save_results_to_file(data, events_results, MIC_POSITIONS, output_path)
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
        data = {}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            output_path = f.name

        try:
            save_results_to_file(data, events_results, MIC_POSITIONS, output_path)
            with open(output_path) as f:
                content = f.read()
            self.assertIn("e1 = FAILED", content)
        finally:
            os.unlink(output_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
