"""
Tests for udara/drone_system/io/serial_handler.py and comms.py
"""

import os
import sys
import tempfile
import unittest
import threading
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "udara"))

from drone_system.io.serial_handler import SerialHandler, START_MARKER, END_MARKER
from drone_system.io.comms import SerialCommunicator


class TestSerialHandler(unittest.TestCase):

    def setUp(self):
        self.handler = SerialHandler(port="/dev/test_port", baudrate=115200)

    @patch("serial.Serial")
    def test_connect_and_close(self, mock_serial_cls):
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_serial_cls.return_value = mock_ser

        ok = self.handler.connect()
        self.assertTrue(ok)
        self.assertTrue(self.handler.is_connected())

        self.handler.close()
        mock_ser.close.assert_called_once()

    @patch("serial.Serial")
    def test_read_command(self, mock_serial_cls):
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_ser.readline.return_value = b"START_REC\n"
        mock_serial_cls.return_value = mock_ser

        self.handler.connect()
        cmd = self.handler.read_command()
        self.assertEqual(cmd, "START_REC")

    @patch("serial.Serial")
    def test_send_response(self, mock_serial_cls):
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_serial_cls.return_value = mock_ser

        self.handler.connect()
        ok = self.handler.send_response("OK:Ready")
        self.assertTrue(ok)
        mock_ser.write.assert_called_with(b"OK:Ready\n")
        mock_ser.flush.assert_called()

    @patch("serial.Serial")
    def test_send_file(self, mock_serial_cls):
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_serial_cls.return_value = mock_ser

        self.handler.connect()

        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as f:
            f.write(b'{"status": "ok", "events": []}')
            temp_path = f.name

        try:
            ok = self.handler.send_file(temp_path)
            self.assertTrue(ok)
            # Verify START marker, payload, and END marker written
            writes = [call[0][0] for call in mock_ser.write.call_args_list]
            self.assertIn(START_MARKER, writes)
            self.assertIn(b'{"status": "ok", "events": []}', writes)
            self.assertIn(END_MARKER, writes)
            mock_ser.flush.assert_called()
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)

    @patch("serial.Serial")
    def test_serial_communicator_subclass(self, mock_serial_cls):
        mock_ser = MagicMock()
        mock_ser.is_open = True
        mock_serial_cls.return_value = mock_ser

        comm = SerialCommunicator()
        self.assertIsInstance(comm, SerialHandler)


if __name__ == "__main__":
    unittest.main(verbosity=2)
