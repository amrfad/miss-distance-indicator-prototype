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

    def test_overlap_deduplication_filters_duplicate_events(self):
        # Chunk 0 (0-8.25s): Gunshot at [7.0s, 7.4s]
        chunk0_payload = {
            "session_id": "session_20260822_001",
            "events": [
                {
                    "event_number": 1,
                    "chunk_timestamp": "ts_chunk0",
                    "event_start_in_chunk": 7.0,
                    "event_end_in_chunk": 7.4,
                    "event_abs_start_sec": 7.0,
                    "event_abs_end_sec": 7.4,
                    "tdoa": {"mic0-mic1": 0.0001}
                }
            ]
        }
        res0 = self.receiver._filter_duplicate_events(chunk0_payload)
        self.assertEqual(res0["event_count"], 1)

        # Chunk 1 (7.0-15.25s): Same gunshot detected at [0.05s, 0.45s] within chunk (abs range = [7.05s, 7.45s])
        # Plus a new gunshot at [10.0s, 10.3s]
        chunk1_payload = {
            "session_id": "session_20260822_001",
            "events": [
                {
                    "event_number": 1,
                    "chunk_timestamp": "ts_chunk1",  # Different timestamp!
                    "event_start_in_chunk": 0.05,
                    "event_end_in_chunk": 0.45,
                    "event_abs_start_sec": 7.05,      # Overlaps with [7.0, 7.4]
                    "event_abs_end_sec": 7.45,
                    "tdoa": {"mic0-mic1": 0.0001}
                },
                {
                    "event_number": 2,
                    "chunk_timestamp": "ts_chunk1",
                    "event_start_in_chunk": 3.0,
                    "event_end_in_chunk": 3.3,
                    "event_abs_start_sec": 10.0,
                    "event_abs_end_sec": 10.3,
                    "tdoa": {"mic0-mic1": 0.0002}
                }
            ]
        }
        res1 = self.receiver._filter_duplicate_events(chunk1_payload)
        self.assertEqual(res1["event_count"], 1)
        self.assertEqual(res1["events"][0]["event_number"], 2)
        self.assertEqual(res1["events"][0]["event_abs_start_sec"], 10.0)

    def test_rapid_burst_gunshots_not_falsely_deduplicated(self):
        # Two distinct rapid gunshots in close succession: [7.0, 7.2] and [7.35, 7.55]
        payload = {
            "session_id": "session_20260822_burst",
            "events": [
                {
                    "event_number": 1,
                    "event_abs_start_sec": 7.0,
                    "event_abs_end_sec": 7.2,
                    "tdoa": {"mic0-mic1": 0.0001}
                },
                {
                    "event_number": 2,
                    "event_abs_start_sec": 7.35,
                    "event_abs_end_sec": 7.55,
                    "tdoa": {"mic0-mic1": 0.00015}
                }
            ]
        }
        res = self.receiver._filter_duplicate_events(payload)
        self.assertEqual(res["event_count"], 2)
        self.assertEqual(len(res["events"]), 2)

    def test_legacy_deduplication_fallback(self):
        payload1 = {
            "events": [
                {"chunk_timestamp": "ts1", "event_number": 1, "tdoa": {}},
                {"chunk_timestamp": "ts1", "event_number": 2, "tdoa": {}},
            ]
        }
        res1 = self.receiver._filter_duplicate_events(payload1)
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
            "session_id": "session_test",
            "events": [
                {"event_number": 1, "event_abs_start_sec": 5.0, "event_abs_end_sec": 5.3, "tdoa": {}},
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
