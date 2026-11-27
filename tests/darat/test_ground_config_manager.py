"""
Tests for darat/config_manager.py

Verifikasi:
1. Load defaults
2. Update parameter standard
3. Update mic_positions (PATCH merge behavior)
4. Invalid mic_positions updates
5. Reset config
6. Schema generation
"""

import sys
import os
import unittest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "."))

from darat.core.config_manager import (
    GroundConfigManager,
    NullStore,
    ValidationError,
    UnknownParamError
)

class TestGroundConfigManager(unittest.TestCase):
    def setUp(self):
        self.manager = GroundConfigManager(store=NullStore())

    def test_load_defaults(self):
        cfg = self.manager.get_all()
        self.assertEqual(cfg["baud_rate"], 230400)
        self.assertEqual(cfg["serial_port"], "AUTO")
        self.assertEqual(cfg["sdr_ipc_host"], "127.0.0.1")
        self.assertEqual(
            cfg["sdr_python_path"],
            os.path.join(os.path.expanduser("~"), "radioconda", "python.exe"),
        )
        self.assertEqual(cfg["speed_of_sound"], 343.0)
        self.assertIn("mic_positions", cfg)
        self.assertIn("mic0", cfg["mic_positions"])
        
        # Check that mic_positions is returned as a dict in get_all
        mic0 = cfg["mic_positions"]["mic0"]
        self.assertIsInstance(mic0, dict)
        self.assertIn("x", mic0)
        self.assertIn("y", mic0)
        self.assertIn("z", mic0)
        
        # Check get_mic_positions_numpy
        numpy_mics = self.manager.get_mic_positions_numpy()
        self.assertIsInstance(numpy_mics["mic0"], np.ndarray)

    def test_update_params(self):
        res = self.manager.update({"speed_of_sound": 340.5, "cluster_eps": 1.5})
        self.assertIn("speed_of_sound", res["updated"])
        self.assertIn("cluster_eps", res["updated"])
        
        cfg = self.manager.get_all()
        self.assertEqual(cfg["speed_of_sound"], 340.5)
        self.assertEqual(cfg["cluster_eps"], 1.5)

    def test_mic_positions_merge(self):
        # Only update mic0 and mic1
        changes = {
            "mic_positions": {
                "mic0": {"x": 10.0, "y": 0.0, "z": 0.0},
                "mic1": {"x": -10.0, "y": 0.0, "z": 0.0}
            }
        }
        res = self.manager.update(changes)
        
        self.assertIn("mic_positions.mic0", res["updated"])
        self.assertIn("mic_positions.mic1", res["updated"])
        
        cfg = self.manager.get_all()
        
        # Check updated mics
        self.assertEqual(cfg["mic_positions"]["mic0"]["x"], 10.0)
        self.assertEqual(cfg["mic_positions"]["mic1"]["x"], -10.0)
        
        # Check that other mics were NOT deleted
        self.assertIn("mic2", cfg["mic_positions"])
        self.assertIn("mic3", cfg["mic_positions"])

    def test_reset(self):
        self.manager.update({"speed_of_sound": 350.0})
        self.manager.reset()
        
        cfg = self.manager.get_all()
        self.assertEqual(cfg["speed_of_sound"], 343.0)

    def test_schema_structure(self):
        schema = self.manager.get_schema()
        self.assertIn("params", schema)
        self.assertIsInstance(schema["params"], list)
        
        first_param = schema["params"][0]
        self.assertIn("key", first_param)
        self.assertIn("label", first_param)

    def test_invalid_mic_update(self):
        # Missing z coordinate
        changes = {
            "mic_positions": {
                "mic0": {"x": 10.0, "y": 0.0}
            }
        }
        with self.assertRaises(ValidationError) as ctx:
            self.manager.update(changes)
        self.assertIn("missing field", str(ctx.exception).lower())

    def test_validation_enum_and_range(self):
        # Valid UI-aligned baud_rate
        self.manager.update({"baud_rate": 57600})
        self.assertEqual(self.manager.get("baud_rate"), 57600)

        # Invalid enum values
        for bad in ({"baud_rate": 1234}, {"comm_backend": "WIFI"}, {"multilat_aggregate": "mode"}):
            with self.assertRaises(ValidationError):
                self.manager.update(bad)

        # Out-of-range numeric values
        for bad in (
            {"speed_of_sound": 300.0},
            {"speed_of_sound": 370.0},
            {"cluster_eps": 0.05},
            {"cluster_eps": 15.0},
            {"serial_timeout": 35.0},
        ):
            with self.assertRaises(ValidationError):
                self.manager.update(bad)

    def test_requires_restart_dynamic(self):
        # Changing comm_backend triggers requires_restart=True
        res_changed = self.manager.update({"comm_backend": "SDR"})
        self.assertTrue(res_changed["requires_restart"])

        # Same value or non-restart param returns requires_restart=False
        res_same = self.manager.update({"comm_backend": "SDR"})
        self.assertFalse(res_same["requires_restart"])

        res_other = self.manager.update({"baud_rate": 115200})
        self.assertFalse(res_other["requires_restart"])

if __name__ == "__main__":
    unittest.main(verbosity=2)
