# tests/darat/test_sdr_bridge.py
"""
Unit tests for SdrBridge and ground_unit_headless IPC communication.
"""

import json
import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

# Add project root to sys.path
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

RADIOCONDA_PYTHON = r"D:\Software\Radioconda\python.exe"


class TestSdrHeadlessIpc(unittest.TestCase):
    """Test IPC communication with ground_unit_headless.py in mock mode."""

    @classmethod
    def setUpClass(cls):
        cls.test_port = 5099
        cls.script = _ROOT / "sdr-mdi" / "ground_unit_headless.py"
        cls.out_dir = _ROOT / "drone_recordings"

        if not os.path.exists(RADIOCONDA_PYTHON):
            cls.python_exe = sys.executable
        else:
            cls.python_exe = RADIOCONDA_PYTHON

        # Spawn headless daemon in mock mode
        cls.proc = subprocess.Popen(
            [
                cls.python_exe,
                str(cls.script),
                "--ipc-port", str(cls.test_port),
                "--output-dir", str(cls.out_dir),
                "--mock",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        time.sleep(1.5)

    @classmethod
    def tearDownClass(cls):
        if cls.proc.poll() is None:
            cls.proc.terminate()
            cls.proc.wait(timeout=2.0)

    def _send_cmd(self, sock: socket.socket, action_dict: dict) -> list[dict]:
        payload = (json.dumps(action_dict) + "\n").encode("utf-8")
        sock.sendall(payload)
        time.sleep(0.3)
        sock.settimeout(0.5)
        responses = []
        try:
            raw = sock.recv(4096).decode("utf-8")
            for line in raw.split("\n"):
                line = line.strip()
                if line:
                    responses.append(json.loads(line))
        except socket.timeout:
            pass
        return responses

    def test_01_ping_pong(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", self.test_port))
        resps = self._send_cmd(s, {"action": "PING"})
        s.close()
        events = [r.get("event") for r in resps]
        self.assertIn("PONG", events)

    def test_02_connect_command(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect(("127.0.0.1", self.test_port))
        resps = self._send_cmd(s, {"action": "CONNECT"})
        events = [r.get("event") for r in resps]
        self.assertIn("CONNECTED", events)

        # Send START
        resps2 = self._send_cmd(s, {"action": "START"})
        events2 = [r.get("event") for r in resps2]
        self.assertIn("START_SENT", events2)

        # Send STOP
        resps3 = self._send_cmd(s, {"action": "STOP"})
        events3 = [r.get("event") for r in resps3]
        self.assertIn("STOP_SENT", events3)

        # Send DISCONNECT
        resps4 = self._send_cmd(s, {"action": "DISCONNECT"})
        events4 = [r.get("event") for r in resps4]
        self.assertIn("DISCONNECTED", events4)
        s.close()


if __name__ == "__main__":
    unittest.main()

