"""
Tests for file_transfer.py (refactored)

Verifikasi:
1. get_file_type() mapping extensi → string
2. FileTransferManager.handle_file_start() parse command dengan benar
3. FileTransferManager.handle_file_end() simpan file ke disk
4. process_incoming_data() routing ke json_router jika aktif
5. _get_file_type helper tidak ada duplikasi (satu fungsi untuk semua)

Jalankan: python -m pytest tests/darat/test_file_transfer.py -v
Atau:      python tests/darat/test_file_transfer.py
"""

import sys
import os
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "."))

from darat.core.file_transfer import FileTransferManager, get_file_type


class TestGetFileType(unittest.TestCase):
    """Tests untuk helper get_file_type()."""

    def test_mp4(self):
        self.assertEqual(get_file_type(".mp4"), "Video")

    def test_wav(self):
        self.assertEqual(get_file_type(".wav"), "Audio")

    def test_txt(self):
        self.assertEqual(get_file_type(".txt"), "Text")

    def test_json(self):
        self.assertEqual(get_file_type(".json"), "JSON")

    def test_unknown(self):
        self.assertEqual(get_file_type(".xyz"), "Unknown")

    def test_case_insensitive_handled_by_caller(self):
        # get_file_type menerima ext lowercase (normalisasi dilakukan di caller)
        self.assertEqual(get_file_type(".MP4".lower()), "Video")


class TestFileTransferManager(unittest.TestCase):
    """Tests untuk FileTransferManager state machine."""

    def setUp(self):
        self.log_messages = []
        self.ft = FileTransferManager(
            log_callback=lambda msg: self.log_messages.append(msg),
            save_directory=tempfile.gettempdir(),
        )

    def test_initial_state_is_idle(self):
        self.assertFalse(self.ft.receiving_file)
        self.assertEqual(self.ft.current_file_name, "")
        self.assertEqual(self.ft.expected_file_size, 0)

    def test_handle_file_start_sets_state(self):
        self.ft.handle_file_start("START\n:test_audio.wav:1024")
        self.assertTrue(self.ft.receiving_file)
        self.assertEqual(self.ft.current_file_name, "test_audio.wav")
        self.assertEqual(self.ft.expected_file_size, 1024)

    def test_handle_file_start_invalid_format(self):
        self.ft.handle_file_start("INVALID")
        self.assertFalse(self.ft.receiving_file)
        self.assertTrue(any("Invalid" in m for m in self.log_messages))

    def test_handle_file_start_unsupported_extension(self):
        self.ft.handle_file_start("START\n:malware.exe:999")
        self.assertFalse(self.ft.receiving_file)
        self.assertTrue(any("Unsupported" in m for m in self.log_messages))

    def test_handle_file_end_without_start(self):
        self.ft.handle_file_end()
        self.assertTrue(any("not receiving file" in m for m in self.log_messages))

    def test_handle_file_end_saves_binary_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ft = FileTransferManager(
                log_callback=lambda msg: None,
                save_directory=tmpdir,
            )
            test_data = b"RIFF....WAVEfmt "  # Fake WAV header
            ft.handle_file_start(f"START\n:recording.wav:{len(test_data)}")
            ft.file_buffer.extend(test_data)
            ft.handle_file_end()

            saved_path = os.path.join(tmpdir, "recording.wav")
            self.assertTrue(os.path.exists(saved_path))
            with open(saved_path, "rb") as f:
                self.assertEqual(f.read(), test_data)

    def test_handle_file_end_saves_text_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ft = FileTransferManager(log_callback=lambda msg: None, save_directory=tmpdir)
            text = "Hello, world!"
            data = text.encode("utf-8")
            ft.handle_file_start(f"START\n:output.txt:{len(data)}")
            ft.file_buffer.extend(data)
            ft.handle_file_end()

            saved_path = os.path.join(tmpdir, "output.txt")
            with open(saved_path) as f:
                self.assertEqual(f.read(), text)

    def test_state_resets_after_file_end(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ft = FileTransferManager(log_callback=lambda msg: None, save_directory=tmpdir)
            ft.handle_file_start("START\n:data.json:10")
            ft.file_buffer.extend(b'{"a": 1}  ')
            ft.handle_file_end()

            self.assertFalse(ft.receiving_file)
            self.assertEqual(ft.current_file_name, "")
            self.assertEqual(ft.expected_file_size, 0)
            self.assertEqual(len(ft.file_buffer), 0)

    def test_json_router_intercepts_data(self):
        routed = []
        self.ft.set_json_router(lambda d: routed.append(d))

        test_data = b'{"hello": "world"}'
        self.ft.process_incoming_data(test_data)

        self.assertEqual(len(routed), 1)
        self.assertEqual(routed[0], test_data)

    def test_clear_json_router_restores_normal_routing(self):
        self.ft.set_json_router(lambda d: None)
        self.ft.clear_json_router()
        self.assertIsNone(self.ft._json_router)

    def test_process_incoming_data_text(self):
        self.ft.process_incoming_data(b"Hello from drone\n")
        self.assertTrue(any("Received:" in m for m in self.log_messages))

    def test_process_incoming_data_file_append(self):
        self.ft.handle_file_start("START\n:test.wav:100")
        self.ft.process_incoming_data(b"\x00" * 50)
        self.assertEqual(len(self.ft.file_buffer), 50)


if __name__ == "__main__":
    unittest.main(verbosity=2)
