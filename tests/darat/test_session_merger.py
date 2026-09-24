"""
Tests for session_merger.py (darat/core/session_merger.py)
Verifikasi penggabungan JSON sesi TDOA saat STOP:
1. Penggabungan beberapa chunk secara sukses
2. Pengurutan kronologis event berdasarkan waktu absolut
3. Penomoran ulang sekuensial event (1..N)
4. Deduplikasi event overlap antar-chunk
5. Penanganan single chunk dan chunk tanpa event
6. Ketahanan terhadap file korup atau list kosong
"""

import sys
import os
import json
import tempfile
import unittest

# Tambahkan root project ke sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from darat.core.session_merger import merge_session_jsons


class TestSessionMerger(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_dummy_chunk(self, filename: str, events: list, chunk_offset: float = 0.0,
                            session_id: str = "session_test_123") -> str:
        data = {
            "session_id": f"chunk_{filename}",
            "timestamp": "2026-09-06 10:00:00",
            "chunk_offset_sec": chunk_offset,
            "chunk_duration_sec": 5.0,
            "sample_rate": 48000,
            "device_profile": "H8",
            "format": "S24_3LE",
            "channels": 12,
            "num_mics": 6,
            "num_tdoa_pairs": 15,
            "event_count": len(events),
            "events": events,
        }
        filepath = os.path.join(self.temp_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return filepath

    def test_merge_multiple_chunks_success(self):
        """Uji penggabungan beberapa chunk dengan urutan waktu dan renumbering benar."""
        # Chunk 1: event pada t=1.2s dan t=3.5s
        c1_events = [
            {
                "event_number": 1,
                "session_id": "session_flight_01",
                "event_abs_start_sec": 1.2,
                "event_abs_end_sec": 1.6,
                "tdoa": {"mic0-mic1": 0.001}
            },
            {
                "event_number": 2,
                "session_id": "session_flight_01",
                "event_abs_start_sec": 3.5,
                "event_abs_end_sec": 4.0,
                "tdoa": {"mic0-mic1": 0.002}
            }
        ]
        # Chunk 2: event pada t=6.1s dan t=8.0s
        c2_events = [
            {
                "event_number": 1,  # perhatikan: di chunk 2 nomor mulai dari 1 lagi
                "session_id": "session_flight_01",
                "event_abs_start_sec": 6.1,
                "event_abs_end_sec": 6.5,
                "tdoa": {"mic0-mic1": 0.003}
            },
            {
                "event_number": 2,
                "session_id": "session_flight_01",
                "event_abs_start_sec": 8.0,
                "event_abs_end_sec": 8.4,
                "tdoa": {"mic0-mic1": 0.004}
            }
        ]

        p1 = self._create_dummy_chunk("chunk_1.json", c1_events, chunk_offset=0.0)
        p2 = self._create_dummy_chunk("chunk_2.json", c2_events, chunk_offset=5.0)

        out_dir = os.path.join(self.temp_dir, "output")
        merged_file = merge_session_jsons([p1, p2], out_dir)

        self.assertIsNotNone(merged_file)
        self.assertTrue(os.path.isfile(merged_file))

        with open(merged_file, "r", encoding="utf-8") as f:
            merged = json.load(f)

        self.assertEqual(merged["session_id"], "session_flight_01")
        self.assertEqual(merged["event_count"], 4)
        self.assertEqual(merged["chunk_count"], 2)
        self.assertEqual(merged["sample_rate"], 48000)
        self.assertEqual(merged["device_profile"], "H8")

        events = merged["events"]
        self.assertEqual(len(events), 4)

        # Verifikasi nomor sekuensial 1..4
        for idx, ev in enumerate(events, start=1):
            self.assertEqual(ev["event_number"], idx)

        # Verifikasi urutan waktu naik
        starts = [ev["event_abs_start_sec"] for ev in events]
        self.assertEqual(starts, [1.2, 3.5, 6.1, 8.0])

    def test_merge_with_overlap_deduplication(self):
        """Uji pembuangan event overlap antar-chunk yang sama."""
        # Chunk 1 memiliki event di t=4.5s
        c1_events = [
            {
                "event_number": 1,
                "session_id": "session_dup_test",
                "event_abs_start_sec": 4.5,
                "event_abs_end_sec": 4.9,
                "tdoa": {"mic0-mic1": 0.001}
            }
        ]
        # Chunk 2 mendeteksi letupan yang sama di area overlap (t=4.52s)
        c2_events = [
            {
                "event_number": 1,
                "session_id": "session_dup_test",
                "event_abs_start_sec": 4.52,  # overlap dengan toleransi 0.05s
                "event_abs_end_sec": 4.92,
                "tdoa": {"mic0-mic1": 0.001}
            },
            {
                "event_number": 2,
                "session_id": "session_dup_test",
                "event_abs_start_sec": 7.0,
                "event_abs_end_sec": 7.4,
                "tdoa": {"mic0-mic1": 0.002}
            }
        ]

        p1 = self._create_dummy_chunk("chunk_a.json", c1_events)
        p2 = self._create_dummy_chunk("chunk_b.json", c2_events)

        out_dir = os.path.join(self.temp_dir, "output")
        merged_file = merge_session_jsons([p1, p2], out_dir, tolerance_sec=0.05)

        with open(merged_file, "r", encoding="utf-8") as f:
            merged = json.load(f)

        # Event duplikat harus dibuang, menyisakan 2 event unik
        self.assertEqual(merged["event_count"], 2)
        events = merged["events"]
        self.assertEqual(events[0]["event_number"], 1)
        self.assertEqual(events[1]["event_number"], 2)
        self.assertAlmostEqual(events[0]["event_abs_start_sec"], 4.5)
        self.assertAlmostEqual(events[1]["event_abs_start_sec"], 7.0)

    def test_merge_single_chunk(self):
        """Uji penggabungan jika hanya 1 chunk yang diterima."""
        c_events = [
            {
                "event_number": 1,
                "session_id": "session_single",
                "event_abs_start_sec": 2.0,
                "event_abs_end_sec": 2.5,
                "tdoa": {"mic0-mic1": 0.001}
            }
        ]
        p = self._create_dummy_chunk("chunk_single.json", c_events)
        out_dir = os.path.join(self.temp_dir, "output")
        merged_file = merge_session_jsons([p], out_dir)

        self.assertIsNotNone(merged_file)
        with open(merged_file, "r", encoding="utf-8") as f:
            merged = json.load(f)
        self.assertEqual(merged["event_count"], 1)
        self.assertEqual(merged["chunk_count"], 1)

    def test_merge_empty_events(self):
        """Uji penggabungan chunk yang tidak memiliki event sama sekali."""
        p1 = self._create_dummy_chunk("chunk_empty1.json", [])
        p2 = self._create_dummy_chunk("chunk_empty2.json", [])
        out_dir = os.path.join(self.temp_dir, "output")
        merged_file = merge_session_jsons([p1, p2], out_dir)

        self.assertIsNotNone(merged_file)
        with open(merged_file, "r", encoding="utf-8") as f:
            merged = json.load(f)
        self.assertEqual(merged["event_count"], 0)
        self.assertEqual(merged["chunk_count"], 2)
        self.assertEqual(merged["events"], [])

    def test_merge_empty_file_list(self):
        """Uji jika list file kosong atau None."""
        self.assertIsNone(merge_session_jsons([], self.temp_dir))
        self.assertIsNone(merge_session_jsons(None, self.temp_dir))

    def test_merge_non_existent_and_corrupt(self):
        """Uji ketahanan jika ada file hilang atau korup."""
        p_corrupt = os.path.join(self.temp_dir, "corrupt.json")
        with open(p_corrupt, "w") as f:
            f.write("{invalid_json: true")

        p_missing = os.path.join(self.temp_dir, "missing.json")

        valid_events = [{
            "event_number": 1,
            "session_id": "sess_ok",
            "event_abs_start_sec": 1.0,
            "event_abs_end_sec": 1.5,
            "tdoa": {"mic0-mic1": 0.001}
        }]
        p_valid = self._create_dummy_chunk("valid.json", valid_events)

        out_dir = os.path.join(self.temp_dir, "output")
        # List berisi missing, corrupt, dan valid
        merged_file = merge_session_jsons([p_missing, p_corrupt, p_valid], out_dir)

        self.assertIsNotNone(merged_file)
        with open(merged_file, "r", encoding="utf-8") as f:
            merged = json.load(f)
        self.assertEqual(merged["event_count"], 1)
        self.assertEqual(merged["chunk_count"], 1)


if __name__ == "__main__":
    unittest.main()
