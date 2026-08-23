"""
Tests for darat.ui.services.serial_bridge (SerialBridge) and CommandPage disconnect handling.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from darat.ui.services.serial_bridge import SerialBridge


class TestSerialBridge(unittest.TestCase):

    def setUp(self):
        self.bridge = SerialBridge()

    def test_send_command_returns_false_when_disconnected(self):
        self.bridge._manager = MagicMock()
        self.bridge._manager.is_connected.return_value = False

        logs = []
        self.bridge.message_received.connect(logs.append)

        result = self.bridge.send_command("START_REC")
        self.assertFalse(result)
        self.assertTrue(any("[ERROR]" in log for log in logs))

    def test_send_command_succeeds_when_connected(self):
        self.bridge._manager = MagicMock()
        self.bridge._manager.is_connected.return_value = True
        self.bridge._manager.send_command.return_value = True

        sent_commands = []
        self.bridge.command_sent.connect(sent_commands.append)

        result = self.bridge.send_command("STATUS")
        self.assertTrue(result)
        self.assertEqual(sent_commands, ["STATUS"])

    def test_send_command_catches_serial_exception(self):
        self.bridge._manager = MagicMock()
        self.bridge._manager.is_connected.return_value = True
        self.bridge._manager.send_command.side_effect = Exception("Serial hardware disconnected")

        logs = []
        self.bridge.message_received.connect(logs.append)

        result = self.bridge.send_command("START_REC")
        self.assertFalse(result)
        self.assertTrue(any("Failed to send serial command" in log for log in logs))


if __name__ == "__main__":
    unittest.main()
