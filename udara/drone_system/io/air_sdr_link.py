"""
AirSdrLink — drone-side client for the headless SDR Air daemon.

The drone process runs in its own virtual environment (no Qt, no GNU Radio),
while the Air radio daemon runs inside radioconda. They are therefore separate
processes that talk over a local TCP IPC socket.

Two directions are involved and they must not be confused:

* **Daemon control (this link).** CONNECT / SOURCE / STATUS / QUIT and the
  ``START_REC`` / ``STOP_REC`` / ``STATE_CHANGED`` notifications. These never
  leave the drone host.
* **Operational commands (radio).** START / STOP originate from the Ground
  station over the RF uplink. The daemon relays them here as notifications so
  the drone knows when to record and when to finalize.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from ..core.config_manager import get_global_config_manager


class AirSdrLink:
    """IPC client plus daemon lifecycle manager for SDR mode."""

    def __init__(self, on_start: Callable[[], None] | None = None,
                 on_stop: Callable[[], None] | None = None,
                 log: Callable[[str], None] | None = None):
        self._on_start = on_start
        self._on_stop = on_stop
        self._log = log or (lambda message: print(f"[SDR] {message}"))

        cfg = get_global_config_manager().get_config()
        self._ipc_host = cfg.get("sdr_ipc_host", "127.0.0.1")
        self._ipc_port = int(cfg.get("sdr_air_ipc_port", 5006))
        self._mock = bool(cfg.get("sdr_mock_mode", False))

        self._socket: socket.socket | None = None
        self._socket_lock = threading.Lock()
        self._rx_thread: threading.Thread | None = None
        self._rx_running = False
        self._connected = False
        self._daemon: subprocess.Popen | None = None

    # ── public API ───────────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> bool:
        if self._connected:
            return True

        cfg = get_global_config_manager().get_config()
        self._ipc_host = cfg.get("sdr_ipc_host", "127.0.0.1")
        self._ipc_port = int(cfg.get("sdr_air_ipc_port", 5006))

        if not self._probe():
            self._log("spawning background SDR Air daemon...")
            if not self._spawn_daemon():
                return False
            ready = False
            probe_timeout = float(cfg.get("sdr_probe_timeout", 10.0))
            probe_iters = max(1, int(probe_timeout / 0.3))
            for _ in range(probe_iters):
                time.sleep(0.3)
                if self._probe():
                    ready = True
                    break
            if not ready:
                self._log("timeout waiting for SDR Air IPC server")
                return False

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((self._ipc_host, self._ipc_port))
            self._socket = sock
        except Exception as exc:
            self._log(f"failed to connect IPC socket: {exc}")
            return False

        self._rx_running = True
        self._rx_thread = threading.Thread(
            target=self._receive_loop, daemon=True, name="AirSdrLink-RX"
        )
        self._rx_thread.start()

        self._send({"action": "CONNECT"})

        # Point the daemon at the drone's own recording directory.
        source = cfg.get("base_output_dir", "drone_recordings")
        if source:
            self._send({"action": "SOURCE", "path": os.path.abspath(source)})

        connect_timeout = float(cfg.get("sdr_connect_timeout", 30.0))
        connect_iters = max(1, int(connect_timeout / 0.2))
        for _ in range(connect_iters):
            time.sleep(0.2)
            if self._connected:
                break

        if not self._connected:
            self._log("daemon did not confirm CONNECT")
            self.disconnect()
            return False

        self._log(f"connected to SDR Air daemon at {self._ipc_host}:{self._ipc_port}")
        return True

    def disconnect(self) -> None:
        if self._connected:
            self._send({"action": "DISCONNECT"})

        self._rx_running = False
        with self._socket_lock:
            if self._socket is not None:
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None
        self._connected = False

    def request_status(self) -> None:
        self._send({"action": "STATUS"})

    def set_source(self, directory: str) -> bool:
        """Select only the current recording session's JSON chunks."""
        return self._send({"action": "SOURCE", "path": os.path.abspath(directory)})

    def shutdown(self) -> None:
        self.disconnect()
        if self._daemon is not None and self._daemon.poll() is None:
            self._daemon.terminate()
            try:
                self._daemon.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._daemon.kill()
        self._daemon = None

    # ── daemon spawn ─────────────────────────────────────────────────────────

    def _probe(self) -> bool:
        try:
            with socket.create_connection((self._ipc_host, self._ipc_port), timeout=0.2):
                return True
        except (OSError, socket.timeout):
            return False

    def _spawn_daemon(self) -> bool:
        cfg = get_global_config_manager().get_config()
        python_bin = cfg.get("sdr_python_path", "")
        if not python_bin or not os.path.isfile(python_bin):
            self._log("configure sdr_python_path to the radioconda Python executable")
            return False

        repo_root = Path(__file__).resolve().parents[3]
        script = repo_root / "sdr-mdi" / "air_unit_headless.py"
        if not script.exists():
            self._log(f"daemon script not found: {script}")
            return False

        source_dir = cfg.get("base_output_dir", "drone_recordings")
        args = [
            str(script),
            "--ipc-host", str(self._ipc_host),
            "--ipc-port", str(self._ipc_port),
            "--input-dir", os.path.abspath(source_dir),
            "--metrics-dir", os.path.join(os.path.abspath(source_dir), "sdr_metrics"),
        ]
        if self._mock:
            args.append("--mock")
        if cfg.get("sdr_air_input_file"):
            args += ["--input-file", str(cfg.get("sdr_air_input_file"))]

        self._log(f"launching {python_bin} {script.name}")
        try:
            self._daemon = subprocess.Popen(
                [python_bin, *args],
                stdout=None,
                stderr=None,
                cwd=str(repo_root / "sdr-mdi"),
            )
        except Exception as exc:
            self._log(f"failed to spawn daemon: {exc}")
            return False
        return True

    # ── IPC plumbing ─────────────────────────────────────────────────────────

    def _send(self, message: dict) -> bool:
        with self._socket_lock:
            if self._socket is None:
                return False
            try:
                self._socket.sendall((json.dumps(message) + "\n").encode("utf-8"))
                return True
            except Exception as exc:
                self._log(f"IPC send error: {exc}")
                return False

    def _receive_loop(self) -> None:
        buffer = ""
        while self._rx_running and self._socket is not None:
            try:
                data = self._socket.recv(4096)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="replace")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._handle_event(line)
            except socket.timeout:
                continue
            except (OSError, ConnectionResetError):
                break

        if self._connected:
            self._connected = False
            self._log("IPC connection closed by daemon")

    def _handle_event(self, raw_line: str) -> None:
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            return

        kind = event.get("event", "")

        if kind == "CONNECTED":
            self._connected = True
            self._log(f"connected: {event.get('port', 'SDR')}")

        elif kind == "CONNECT_FAILED":
            self._log(f"connect failed: {event.get('message', 'unknown error')}")

        elif kind == "DISCONNECTED":
            self._connected = False

        elif kind == "START_REC":
            self._log("ground START received — beginning recording")
            if self._on_start is not None:
                self._on_start()

        elif kind == "STOP_REC":
            self._log("ground STOP received — finalizing recording")
            # stop_and_process() may wait up to 120 seconds for both audio
            # workers. Do not block the IPC reader while it runs.
            threading.Thread(
                target=self._finalize_recording,
                daemon=True,
                name="AirSdrLink-Finalize",
            ).start()

        elif kind == "STATE_CHANGED":
            self._log(f"air state: {event.get('state')}")

        elif kind == "SOURCE_SET":
            self._log(f"source directory: {event.get('path')}")

        elif kind == "STATUS":
            self._log(
                f"status state={event.get('state')} "
                f"recording={event.get('recording')}"
            )

        elif kind in ("LOG", "ERROR"):
            self._log(f"{kind}: {event.get('message', '')}")

    def _finalize_recording(self) -> None:
        try:
            if self._on_stop is not None:
                self._on_stop()
        except Exception as exc:
            self._log(f"recording finalization failed: {exc}")
        finally:
            # Air stays STOPPING until the final chunk has been written and
            # broadcast. This is local IPC, not a data ACK over RF.
            self._send({"action": "SOURCE_READY"})
