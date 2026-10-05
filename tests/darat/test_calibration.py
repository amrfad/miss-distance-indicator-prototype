"""
test_calibration.py — Unit test untuk modul kalibrasi posisi mikrofon ground unit.

Menjalankan pengujian:
1. Parameter packing & unpacking (free_18 & pin_origin_15)
2. Parsing file JSON TDOA drone (parse_tdoa_json)
3. Evaluasi residual TDOA (compute_tdoa_residuals)
4. Optimasi least-squares kalibrasi posisi 3D (run_calibration)
5. Robustness handling (sesi kosong, 0-event, argumen invalid)
6. Widget sesi kalibrasi (SessionListWidget)
"""

import json
import os
import sys
import tempfile
import unittest
import numpy as np

# Pastikan root workspace ada di sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from darat.localization.calibration_engine import (
    CalibrationResult,
    CalibrationSession,
    NUM_MICS,
    TDOA_PAIRS,
    calibrate_mic_array,
    compute_tdoa_residuals,
    pack_params,
    parse_tdoa_json,
    run_calibration,
    unpack_params,
)


class TestCalibrationMath(unittest.TestCase):
    """Test parameter packing, residual calculation, and optimizer convergence."""

    def setUp(self):
        # Matriks ground truth simulasi untuk 6 mikrofon
        self.gt_mics = np.array([
            [-1.58,  0.77,  0.09],
            [ 1.60,  0.77,  0.09],
            [-0.59, -0.92, -0.07],
            [ 0.59, -0.92, -0.05],
            [-0.50, -0.11, -0.16],
            [ 0.13, -0.01, -0.17],
        ], dtype=float)
        self.c = 343.0

    def test_pack_unpack_free18(self):
        packed = pack_params(self.gt_mics, mode="free_18")
        self.assertEqual(len(packed), 18)
        unpacked = unpack_params(packed, mode="free_18")
        np.testing.assert_allclose(unpacked, self.gt_mics, atol=1e-12)

    def test_pack_unpack_pin15(self):
        packed = pack_params(self.gt_mics, mode="pin_origin_15")
        self.assertEqual(len(packed), 15)
        unpacked = unpack_params(packed, mode="pin_origin_15")
        self.assertEqual(unpacked.shape, (6, 3))
        np.testing.assert_allclose(unpacked[1], [0.0, 0.0, 0.0])

    def test_zero_residual_on_ground_truth(self):
        # Buat observasi sintesis sempurna dari GT
        sources = [
            np.array([-3.75, 0.37, -0.47]),
            np.array([ 2.50, 1.80,  0.60]),
            np.array([ 0.00, -2.50, 1.00]),
            np.array([-1.50, 3.00, -1.20]),
        ]

        obs_list = []
        for S in sources:
            tdoa_map = {}
            for i, j in TDOA_PAIRS:
                di = np.linalg.norm(S - self.gt_mics[i])
                dj = np.linalg.norm(S - self.gt_mics[j])
                tdoa_map[f"mic{i}-mic{j}"] = float((di - dj) / self.c)
            obs_list.append({"source_pos": S, "tdoa_median": tdoa_map})

        params = pack_params(self.gt_mics, mode="free_18")
        residuals = compute_tdoa_residuals(params, obs_list, speed_of_sound=self.c, mode="free_18")

        # Residual teoritis terhadap data tanpa noise harus mendekati 0
        np.testing.assert_allclose(residuals, 0.0, atol=1e-10)

    def test_optimizer_convergence_synthetic(self):
        # 10 titik sumber terdistribusi di ruang 3D
        rng = np.random.default_rng(123)
        sources = [
            np.array([rng.uniform(-5, 5), rng.uniform(-5, 5), rng.uniform(-2, 3)])
            for _ in range(12)
        ]

        sessions = []
        for idx, S in enumerate(sources):
            tdoa_map = {}
            for i, j in TDOA_PAIRS:
                di = np.linalg.norm(S - self.gt_mics[i])
                dj = np.linalg.norm(S - self.gt_mics[j])
                tdoa_map[f"mic{i}-mic{j}"] = float((di - dj) / self.c)

            sess = CalibrationSession(
                session_id=f"syn_{idx}",
                file_path=f"dummy_{idx}.json",
                source_pos=S,
                tdoa_median=tdoa_map,
                n_events=5,
            )
            sessions.append(sess)

        # Berikan initial guess dengan sedikit noise (misal 10 cm)
        x0_noisy = self.gt_mics + rng.normal(0, 0.10, size=self.gt_mics.shape)

        res = run_calibration(
            sessions=sessions,
            initial_mic_positions=x0_noisy,
            speed_of_sound=self.c,
            mode="free_18",
            loss="linear",
        )

        self.assertTrue(res.converged)
        self.assertLess(res.rms_residual_ms, 0.05)  # RMS residual sangat kecil
        # Posisi estimasi harus kembali sangat dekat dengan GT (error < 2 cm)
        np.testing.assert_allclose(res.mic_positions_array, self.gt_mics, atol=0.02)


class TestCalibrationParsing(unittest.TestCase):
    """Test parsing data JSON rekaman TDOA."""

    def test_parse_fixture_json(self):
        fixture_path = os.path.join(os.path.dirname(__file__), "fixtures", "sample_tdoa.json")
        self.assertTrue(os.path.exists(fixture_path), "Fixture sample_tdoa.json harus ada")

        src = np.array([1.5, -2.0, 0.5])
        sess = parse_tdoa_json(fixture_path, src)

        self.assertEqual(sess.session_id, "test_session_20250101_000000_abc123")
        self.assertTrue(sess.is_valid)
        self.assertEqual(sess.n_events, 2)
        self.assertEqual(len(sess.tdoa_median), 15)  # C(6,2) = 15 pairs
        np.testing.assert_allclose(sess.source_pos, src)

        # Cek median salah satu pair: mic0-mic1 punya -0.00215 dan 0.00310
        expected_median = float(np.median([-0.00215, 0.00310]))
        self.assertAlmostEqual(sess.tdoa_median["mic0-mic1"], expected_median, places=6)

    def test_parse_zero_events_json(self):
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".json") as f:
            json.dump({"session_id": "empty_sess", "events": []}, f)
            temp_path = f.name

        try:
            sess = parse_tdoa_json(temp_path, [0.0, 0.0, 0.0])
            self.assertEqual(sess.session_id, "empty_sess")
            self.assertEqual(sess.n_events, 0)
            self.assertFalse(sess.is_valid)
            self.assertEqual(len(sess.tdoa_median), 0)
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_run_calibration_empty_raises(self):
        sess = CalibrationSession(
            session_id="invalid",
            file_path="foo.json",
            source_pos=np.array([0, 0, 0]),
            tdoa_median={},
            n_events=0,
        )
        with self.assertRaises(ValueError):
            run_calibration([sess])


if __name__ == "__main__":
    unittest.main()
