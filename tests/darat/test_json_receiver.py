"""
Tests for darat.io.json_receiver (JsonReceiver).
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from darat.io.json_receiver import JsonReceiver


class TestJsonReceiver(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.serial_manager = MagicMock()
        self.serial_manager.is_connected.return_value = True
        self.file_transfer = MagicMock()
        self.logs = []
        self.log_cb = lambda msg: self.logs.append(msg)
        self.receiver = JsonReceiver(
            self.serial_manager,
            self.file_transfer,
            self.log_cb,
            save_directory=self.temp_dir
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_deduplication_filters_identical_events(self):
        payload = {
            "events": [
                {"chunk_timestamp": "ts1", "event_number": 1, "tdoa": {}},
                {"chunk_timestamp": "ts1", "event_number": 2, "tdoa": {}},
            ]
        }
        res1 = self.receiver._filter_duplicate_events(payload)
        self.assertEqual(res1["event_count"], 2)

        # Second payload with one duplicate and one new
        payload2 = {
            "events": [
                {"chunk_timestamp": "ts1", "event_number": 1, "tdoa": {}},
                {"chunk_timestamp": "ts2", "event_number": 3, "tdoa": {}},
            ]
        }
        res2 = self.receiver._filter_duplicate_events(payload2)
        self.assertEqual(res2["event_count"], 1)
        self.assertEqual(res2["events"][0]["event_number"], 3)

    def test_reset_clears_dedup_cache(self):
        payload = {
            "events": [
                {"chunk_timestamp": "ts1", "event_number": 1, "tdoa": {}},
            ]
        }
        self.receiver._filter_duplicate_events(payload)
        self.receiver.reset()
        res = self.receiver._filter_duplicate_events(payload)
        self.assertEqual(res["event_count"], 1)

    def test_receive_once_parses_clean_json(self):
        sample_data = {"test": 123, "events": []}
        json_bytes = json.dumps(sample_data).encode("utf-8")
        packet = b"[START]\n" + json_bytes + b"\n[END]\n"

        saved_files = []
        def on_saved(fp):
            saved_files.append(fp)

        self.receiver._route_data(packet)
        ok = self.receiver.receive_json(on_saved=on_saved, continuous=False)
        self.assertTrue(ok)
        self.assertEqual(len(saved_files), 1)
        with open(saved_files[0], "r") as f:
            loaded = json.load(f)
        self.assertEqual(loaded["test"], 123)

    def test_receive_once_handles_split_start_marker(self):
        sample_data = {"test": "split_marker", "events": []}
        json_bytes = json.dumps(sample_data).encode("utf-8")

        saved_files = []
        def on_saved(fp):
            saved_files.append(fp)

        # Send in two parts: first part splits inside START marker
        self.receiver._route_data(b"[START]")
        self.receiver._route_data(b"\n" + json_bytes + b"\n[END]\n")

        ok = self.receiver.receive_json(on_saved=on_saved, continuous=False)
        self.assertTrue(ok)
        self.assertEqual(len(saved_files), 1)
        with open(saved_files[0], "r") as f:
            loaded = json.load(f)
        self.assertEqual(loaded["test"], "split_marker")


if __name__ == "__main__":
    unittest.main()
