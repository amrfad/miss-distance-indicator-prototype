"""
Tests for udara/drone_system/io/air_sdr_link.py

AirSdrLink is the drone-side IPC client for the headless SDR Air daemon. These
tests use a fake in-process TCP server so they never need radioconda, a USRP,
or the real daemon.
"""

import json
import os
import socket
import sys
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "udara"))

from drone_system.io.air_sdr_link import AirSdrLink


class FakeDaemon:
    """Minimal stand-in for air_unit_headless.py's IpcServer.

    Accepts any number of connections because ``AirSdrLink.connect`` first
    probes the port with a short-lived connection before opening the real one.
    """

    def __init__(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(5)
        self.port = self._sock.getsockname()[1]
        self.received: list[dict] = []
        self._clients: list[socket.socket] = []
        self._lock = threading.Lock()
        self._running = True
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self):
        while self._running:
            try:
                client, _ = self._sock.accept()
            except OSError:
                break
            with self._lock:
                self._clients.append(client)
            threading.Thread(
                target=self._serve, args=(client,), daemon=True
            ).start()

    def _serve(self, client: socket.socket):
        client.settimeout(0.5)
        buffer = ""
        while self._running:
            try:
                data = client.recv(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data:
                break
            buffer += data.decode("utf-8", errors="replace")
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                if not line.strip():
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                self.received.append(message)
                self._reply(client, message)
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)
        try:
            client.close()
        except OSError:
            pass

    def _reply(self, client: socket.socket, message: dict) -> None:
        action = message.get("action")
        if action == "CONNECT":
            self._send(client, {"event": "CONNECTED", "port": "Mock SDR (Air)"})
        elif action == "SOURCE":
            self._send(client, {"event": "SOURCE_SET", "path": message.get("path", "")})
        elif action == "STATUS":
            self._send(
                client,
                {"event": "STATUS", "state": "IDLE", "recording": False},
            )
        elif action == "DISCONNECT":
            self._send(client, {"event": "DISCONNECTED"})

    @staticmethod
    def _send(client: socket.socket, event: dict) -> None:
        try:
            client.sendall((json.dumps(event) + "\n").encode("utf-8"))
        except OSError:
            pass

    def push(self, event: dict) -> None:
        """Simulate an unsolicited daemon event (e.g. START_REC from RF)."""
        with self._lock:
            clients = list(self._clients)
        for client in clients:
            self._send(client, event)

    def stop(self):
        self._running = False
        with self._lock:
            for client in self._clients:
                try:
                    client.close()
                except OSError:
                    pass
            self._clients.clear()
        try:
            self._sock.close()
        except OSError:
            pass


class TestAirSdrLink(unittest.TestCase):

    def setUp(self):
        self.daemon = FakeDaemon()
        # Keep the config patch active for the whole test: AirSdrLink re-reads
        # the config inside connect(), not only in __init__.
        self._patcher = patch(
            "drone_system.io.air_sdr_link.get_global_config_manager"
        )
        manager = self._patcher.start()
        manager.return_value.get_config.return_value = {
            "sdr_ipc_host": "127.0.0.1",
            "sdr_air_ipc_port": self.daemon.port,
            "sdr_mock_mode": True,
            "sdr_python_path": "",
            "base_output_dir": "/tmp/drone_recordings",
            "sdr_air_input_file": "",
        }
        self.link: AirSdrLink | None = None

    def tearDown(self):
        if self.link is not None:
            self.link.disconnect()
        self._patcher.stop()
        self.daemon.stop()

    def _make_link(self, on_start=None, on_stop=None) -> AirSdrLink:
        self.link = AirSdrLink(
            on_start=on_start, on_stop=on_stop, log=lambda *_: None
        )
        return self.link

    def test_connect_sends_connect_and_source(self):
        link = self._make_link()
        self.assertTrue(link.connect())
        self.assertTrue(link.is_connected())

        actions = [m.get("action") for m in self.daemon.received]
        self.assertIn("CONNECT", actions)
        self.assertIn("SOURCE", actions)

    def test_status_request(self):
        link = self._make_link()
        link.connect()
        link.request_status()
        time.sleep(0.3)
        self.assertIn("STATUS", [m.get("action") for m in self.daemon.received])

    def test_start_rec_event_fires_callback(self):
        fired = []
        link = self._make_link(on_start=lambda: fired.append("start"))
        link.connect()
        self.daemon.push({"event": "START_REC"})
        time.sleep(0.4)
        self.assertEqual(fired, ["start"])

    def test_stop_rec_event_fires_callback(self):
        fired = []
        link = self._make_link(on_stop=lambda: fired.append("stop"))
        link.connect()
        self.daemon.push({"event": "STOP_REC"})
        time.sleep(0.4)
        self.assertEqual(fired, ["stop"])

    def test_unknown_event_does_not_crash(self):
        link = self._make_link()
        link.connect()
        self.daemon.push({"event": "SOMETHING_ELSE", "detail": 1})
        self.daemon.push({"event": "LOG", "message": "hello"})
        time.sleep(0.3)
        self.assertTrue(link.is_connected())


if __name__ == "__main__":
    unittest.main()
