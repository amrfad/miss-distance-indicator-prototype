"""
Tests for udara/drone_system/config_manager.py

Verifikasi:
1. Load defaults
2. Update runtime params dan ground-only params
3. Proteksi READONLY_PARAM ketika via serial
4. Validasi antar-parameter (Section 6 contract)
5. Reset berdasarkan scope
6. Schema generation
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "."))

from udara.drone_system.core.config_manager import (
    ConfigManager,
    NullStore,
    ValidationError,
    UnknownParamError,
    ReadonlyParamError
)

class TestDroneConfigManager(unittest.TestCase):
    def setUp(self):
        self.manager = ConfigManager(store=NullStore())

    def test_load_defaults(self):
        cfg = self.manager.get_all()
        self.assertEqual(cfg["operation_mode"], "OFFLINE")
        self.assertEqual(cfg["sample_rate"], 48000)
        self.assertEqual(cfg["detect_ratio"], 0.20)
        self.assertEqual(cfg["min_duration"], 0.25)

    def test_update_runtime_params(self):
        res = self.manager.update({"detect_ratio": 0.25, "filter_ratio": 0.50}, source="rest")
        self.assertFalse(res["requires_restart"])
        self.assertIn("detect_ratio", res["updated"])
        
        cfg = self.manager.get_all()
        self.assertEqual(cfg["detect_ratio"], 0.25)
        self.assertEqual(cfg["filter_ratio"], 0.50)

    def test_update_ground_only_params(self):
        res = self.manager.update({"operation_mode": "ONLINE", "sample_rate": 44100}, source="rest")
        self.assertTrue(res["requires_restart"])
        self.assertIn("operation_mode", res["restart_params"])
        self.assertIn("sample_rate", res["restart_params"])
        
        cfg = self.manager.get_all()
        self.assertEqual(cfg["operation_mode"], "ONLINE")
        self.assertEqual(cfg["sample_rate"], 44100)

    def test_reject_ground_only_via_serial(self):
        with self.assertRaises(ReadonlyParamError):
            self.manager.update({"operation_mode": "ONLINE"}, source="serial")

    # --- Validation Rules (Section 6) ---
    def test_validation_filter_ge_detect(self):
        with self.assertRaises(ValidationError) as ctx:
            self.manager.update({"detect_ratio": 0.5, "filter_ratio": 0.4})
        self.assertIn("filter_ratio >= detect_ratio", str(ctx.exception))

    def test_validation_chunk_duration_ge_overlap(self):
        with self.assertRaises(ValidationError) as ctx:
            self.manager.update({"chunk_duration_sec": 5.0, "chunk_overlap_sec": 6.0})
        self.assertIn("chunk_duration_sec > chunk_overlap_sec", str(ctx.exception))

    def test_validation_detect_ratio_range(self):
        with self.assertRaises(ValidationError):
            self.manager.update({"detect_ratio": -0.1})
        with self.assertRaises(ValidationError):
            self.manager.update({"detect_ratio": 1.1})

    def test_validation_filter_ratio_range(self):
        with self.assertRaises(ValidationError):
            self.manager.update({"filter_ratio": -0.1})
        with self.assertRaises(ValidationError):
            self.manager.update({"filter_ratio": 1.1})

    def test_validation_prop_decrease_range(self):
        with self.assertRaises(ValidationError):
            self.manager.update({"prop_decrease": -0.1})
        with self.assertRaises(ValidationError):
            self.manager.update({"prop_decrease": 1.1})

    def test_validation_min_duration_positive(self):
        with self.assertRaises(ValidationError):
            self.manager.update({"min_duration": 0})
        with self.assertRaises(ValidationError):
            self.manager.update({"min_duration": -1})

    def test_validation_max_gap_positive(self):
        with self.assertRaises(ValidationError):
            self.manager.update({"max_gap": 0})

    def test_validation_num_mics_h8(self):
        with self.assertRaises(ValidationError):
            self.manager.update({"num_mics_h8": 5})
        self.manager.update({"num_mics_h8": 4})
        self.manager.update({"num_mics_h8": 6})

    def test_validation_sample_rate(self):
        with self.assertRaises(ValidationError):
            self.manager.update({"sample_rate": 8000})
        self.manager.update({"sample_rate": 96000})

    def test_validation_hop_length_power_of_2(self):
        with self.assertRaises(ValidationError):
            self.manager.update({"hop_length": 500})
        with self.assertRaises(ValidationError):
            self.manager.update({"hop_length": 0})
        self.manager.update({"hop_length": 256})

    def test_validation_frame_length_ge_hop_length(self):
        with self.assertRaises(ValidationError):
            self.manager.update({"hop_length": 1024, "frame_length": 512})

    def test_validation_normalization_percentile(self):
        with self.assertRaises(ValidationError):
            self.manager.update({"normalization_percentile": 0})
        with self.assertRaises(ValidationError):
            self.manager.update({"normalization_percentile": 100.1})

    def test_validation_active_profile(self):
        with self.assertRaises(ValidationError):
            self.manager.update({"active_profile": "H4"})
        self.manager.update({"active_profile": "H6E"})

    def test_validation_operation_mode(self):
        with self.assertRaises(ValidationError):
            self.manager.update({"operation_mode": "TEST"})
        self.manager.update({"operation_mode": "ONLINE"})

    # --- Resets ---
    def test_reset_all(self):
        self.manager.update({"detect_ratio": 0.3, "operation_mode": "ONLINE"})
        res = self.manager.reset("all")
        self.assertTrue(res["requires_restart"])
        cfg = self.manager.get_all()
        self.assertEqual(cfg["detect_ratio"], 0.20)
        self.assertEqual(cfg["operation_mode"], "OFFLINE")

    def test_reset_runtime_only(self):
        self.manager.update({"detect_ratio": 0.3, "operation_mode": "ONLINE"})
        res = self.manager.reset("runtime_only")
        self.assertFalse(res["requires_restart"])
        cfg = self.manager.get_all()
        self.assertEqual(cfg["detect_ratio"], 0.20)
        self.assertEqual(cfg["operation_mode"], "ONLINE")

    def test_reset_ground_only(self):
        self.manager.update({"detect_ratio": 0.3, "operation_mode": "ONLINE"})
        res = self.manager.reset("ground_only")
        self.assertTrue(res["requires_restart"])
        cfg = self.manager.get_all()
        self.assertEqual(cfg["detect_ratio"], 0.3)
        self.assertEqual(cfg["operation_mode"], "OFFLINE")

    # --- Schema and Unknown ---
    def test_schema_structure(self):
        schema = self.manager.get_schema()
        self.assertIn("params", schema)
        self.assertIsInstance(schema["params"], list)
        self.assertGreater(len(schema["params"]), 0)
        
        first_param = schema["params"][0]
        self.assertIn("key", first_param)
        self.assertIn("label", first_param)
        self.assertIn("type", first_param)
        self.assertIn("category", first_param)

    def test_unknown_param(self):
        with self.assertRaises(UnknownParamError):
            self.manager.update({"not_a_real_param": 123})


if __name__ == "__main__":
    unittest.main(verbosity=2)
