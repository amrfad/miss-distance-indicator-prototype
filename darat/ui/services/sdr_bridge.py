# darat/ui/services/sdr_bridge.py
"""
SdrBridge — Service bridge between MDI PySide6 GUI and headless SDR ground daemon.
Drop-in replacement for SerialBridge when operating via Software Defined Radio (USRP B210).
Communicates with sdr-mdi/ground_unit_headless.py via local TCP IPC on 127.0.0.1:5005.
"""

import json
import os
import socket
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QThread, QProcess

from ...core.config_manager import get_global_config_manager


class _SdrConnectWorker(QThread):
    finished_signal = Signal(bool, str)

    def __init__(self, bridge: "SdrBridge"):
        super().__init__()
        self._bridge = bridge

    def run(self):
        success, port = self._bridge.connect_auto()
        self.finished_signal.emit(success, port)


class SdrBridge(QObject):
    """
    SDR communication bridge providing the exact same Qt signal/slot interface
    as SerialBridge, but routing commands and TDOA records through the headless
    SDR daemon over local IPC.
    """

    # Identical signals to SerialBridge
    connection_changed = Signal(bool, str)  # (connected: bool, port_name: str)
    message_received   = Signal(str)        # Log or status message
    data_received      = Signal(bytes)      # Raw data bytes (if needed by file router)
    command_sent       = Signal(str)        # Command echo
    json_saved         = Signal(str)        # Absolute path to received JSON

    def __init__(self, parent=None):
        super().__init__(parent)
        self._connected = False
        self._port_name = "USRP B210 (1.4 GHz)"
        self._socket: socket.socket | None = None
        self._socket_lock = threading.Lock()
        self._rx_thread: threading.Thread | None = None
        self._rx_running = False
        self._connect_thread: _SdrConnectWorker | None = None
        self._daemon_process: QProcess | None = None

        cfg = get_global_config_manager().get_config()
        self._ipc_host = cfg.get("sdr_ipc_host", "127.0.0.1")
        self._ipc_port = int(cfg.get("sdr_ipc_port", 5005))

    # ── Public API (100% compatible with SerialBridge) ──────────────────────────

    def is_connected(self) -> bool:
        return self._connected

    def get_available_ports(self) -> list[dict]:
        return [
            {
                "port": "SDR:USRP_B210",
                "description": "Software Defined Radio Link (USRP B210)",
                "hwid": "SDR",
            }
        ]

    def get_port_info(self) -> dict | None:
        if self._connected:
            return {
                "port": self._port_name,
                "description": "Full-Duplex LoRa SDR Link",
                "baud_rate": "125kHz LoRa",
            }
        return None

    def connect_auto(self) -> tuple[bool, str]:
        """Synchronous connect to the SDR Ground daemon."""
        if self._connected:
            return True, self._port_name

        cfg = get_global_config_manager().get_config()
        self._ipc_host = cfg.get("sdr_ipc_host", "127.0.0.1")
        self._ipc_port = int(cfg.get("sdr_ipc_port", 5005))

        # 1. Check if daemon is already running; if not, spawn it
        if not self._check_ipc_open():
            self.message_received.emit("[SDR] Spawning background SDR Ground daemon...")
            spawned = self._spawn_daemon()
            if not spawned:
                self.message_received.emit("[SDR] Failed to spawn SDR Ground daemon")
                return False, ""
            # Wait for socket to become available
            ready = False
            for _ in range(15):
                time.sleep(0.3)
                if self._check_ipc_open():
                    ready = True
                    break
            if not ready:
                self.message_received.emit("[SDR] Timeout waiting for SDR IPC server")
                return False, ""

        # 2. Connect to IPC socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((self._ipc_host, self._ipc_port))
            self._socket = s
        except Exception as exc:
            self.message_received.emit(f"[SDR] Failed to connect to IPC socket: {exc}")
            return False, ""

        # 3. Start receiver thread
        self._rx_running = True
        self._rx_thread = threading.Thread(
            target=self._ipc_receive_loop,
            daemon=True,
            name="SdrBridge-IPC-Receiver",
        )
        self._rx_thread.start()

        # 4. Send CONNECT command
        self._send_ipc_message({"action": "CONNECT"})

        # Wait briefly for response
        for _ in range(20):
            time.sleep(0.1)
            if self._connected:
                break

        if self._connected:
            self.connection_changed.emit(True, self._port_name)
            return True, self._port_name
        else:
            self.disconnect()
            return False, ""

    def connect_auto_async(self, callback=None):
        """Asynchronous connect worker."""
        if self._connect_thread is not None:
            try:
                if self._connect_thread.isRunning():
                    return
            except RuntimeError:
                self._connect_thread = None

        thread = _SdrConnectWorker(self)
        self._connect_thread = thread

        def _cleanup():
            if self._connect_thread is thread:
                self._connect_thread = None
            thread.deleteLater()

        if callback:
            thread.finished_signal.connect(callback)
        thread.finished.connect(_cleanup)
        thread.start()

    def connect_to_port(self, port: str) -> bool:
        success, _ = self.connect_auto()
        return success

    def connect_to_port_async(self, port: str, callback=None):
        self.connect_auto_async(callback=callback)

    def disconnect(self):
        """Disconnect and stop SDR radio endpoint."""
        if self._connected and self._socket:
            self._send_ipc_message({"action": "DISCONNECT"})

        self._rx_running = False
        with self._socket_lock:
            if self._socket:
                try:
                    self._socket.close()
                except Exception:
                    pass
                self._socket = None

        self._connected = False
        self.connection_changed.emit(False, "")
        self.message_received.emit("[SDR] Disconnected from SDR Radio Link.")

    def send_command(self, command: str) -> bool:
        """Translate MDI text command to SDR action."""
        cmd = command.strip().upper()
        if not self._connected:
            self.message_received.emit("[ERROR] SDR not connected — cannot send command")
            return False

        if cmd == "START_REC":
            self.message_received.emit("[SDR] Transmitting START command to Air Unit...")
            self._send_ipc_message({"action": "START"})
            self.command_sent.emit("START_REC")
            return True

        elif cmd == "STOP_REC":
            self.message_received.emit("[SDR] Transmitting STOP command to Air Unit...")
            self._send_ipc_message({"action": "STOP"})
            self.command_sent.emit("STOP_REC")
            return True

        elif cmd == "STATUS":
            self.message_received.emit("[SDR] Requesting system status...")
            self._send_ipc_message({"action": "STATUS"})
            self.command_sent.emit("STATUS")
            return True

        elif cmd == "RESTART":
            self.message_received.emit("[SDR] Restart not supported directly via RF, stopping active session...")
            self._send_ipc_message({"action": "STOP"})
            self.command_sent.emit("RESTART")
            return True

        else:
            self.message_received.emit(f"[SDR WARN] Unknown command: {command}")
            return False

    def send_set_config(self, runtime_config: dict) -> bool:
        """SET_CONFIG: In SDR mode, warn that RF does not support 1.5KB dumps."""
        self.message_received.emit(
            "[SDR NOTICE] System configuration should be applied via REST API (LAN/WiFi) "
            "prior to flight, as SDR RF bandwidth is reserved for telemetry & commands."
        )
        return True

    # ── Daemon Process & IPC Management ─────────────────────────────────────────

    def _check_ipc_open(self) -> bool:
        try:
            with socket.create_connection((self._ipc_host, self._ipc_port), timeout=0.2):
                return True
        except (OSError, socket.timeout):
            return False

    def _spawn_daemon(self) -> bool:
        """Spawn ground_unit_headless.py in a separate background process."""
        cfg = get_global_config_manager().get_config()
        # Find Python executable
        python_bin = cfg.get("sdr_python_path", "")
        if not python_bin or not os.path.exists(python_bin):
            python_bin = sys.executable

        # Find ground_unit_headless.py
        root_dir = Path(__file__).resolve().parent.parent.parent.parent
        script_path = root_dir / "sdr-mdi" / "ground_unit_headless.py"
        output_dir = root_dir / "drone_recordings"

        if not script_path.exists():
            self.message_received.emit(f"[SDR ERROR] Script not found: {script_path}")
            return False

        args = [
            str(script_path),
            "--ipc-host", str(self._ipc_host),
            "--ipc-port", str(self._ipc_port),
            "--output-dir", str(output_dir),
        ]

        if cfg.get("sdr_mock_mode", False):
            args.append("--mock")

        self.message_received.emit(f"[SDR] Launching: {python_bin} {script_path.name}")
        self._daemon_process = QProcess(self)
        self._daemon_process.start(python_bin, args)
        return True

    def _send_ipc_message(self, msg: dict) -> bool:
        with self._socket_lock:
            if not self._socket:
                return False
            try:
                line = (json.dumps(msg) + "\n").encode("utf-8")
                self._socket.sendall(line)
                return True
            except Exception as exc:
                self.message_received.emit(f"[SDR IPC] Send error: {exc}")
                return False

    def _ipc_receive_loop(self) -> None:
        buf = ""
        while self._rx_running and self._socket:
            try:
                data = self._socket.recv(4096)
                if not data:
                    break
                buf += data.decode("utf-8", errors="replace")
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._handle_ipc_incoming(line)
            except socket.timeout:
                continue
            except (OSError, ConnectionResetError):
                break

        if self._connected:
            self._connected = False
            self.connection_changed.emit(False, "")
            self.message_received.emit("[SDR] IPC connection closed by daemon.")

    def _handle_ipc_incoming(self, raw_line: str) -> None:
        try:
            event_data = json.loads(raw_line)
        except json.JSONDecodeError:
            return

        ev_type = event_data.get("event", "")

        if ev_type == "CONNECTED":
            self._connected = True
            self._port_name = event_data.get("port", "USRP B210 (1.4 GHz)")
            self.connection_changed.emit(True, self._port_name)
            self.message_received.emit(f"[SDR] Connected: {self._port_name}")

        elif ev_type == "CONNECT_FAILED":
            self._connected = False
            msg = event_data.get("message", "Unknown error")
            self.connection_changed.emit(False, "")
            self.message_received.emit(f"[SDR ERROR] Connect failed: {msg}")

        elif ev_type == "DISCONNECTED":
            self._connected = False
            self.connection_changed.emit(False, "")
            self.message_received.emit("[SDR] Radio link disconnected")

        elif ev_type == "DATA_RECEIVED":
            path = event_data.get("path", "")
            summary = event_data.get("summary", "")
            self.message_received.emit(f"[SDR RX] Data received: {os.path.basename(path)} ({summary})")
            if path and os.path.exists(path):
                self.json_saved.emit(path)
                try:
                    with open(path, "rb") as f:
                        raw = f.read()
                        # Also emit as start/end marker bytes for backward compatibility
                        self.data_received.emit(b"[START]\n" + raw + b"\n[END]\n")
                except Exception:
                    pass

        elif ev_type == "STATE_CHANGED":
            state = event_data.get("state", "UNKNOWN")
            self.message_received.emit(f"[SDR STATUS] Drone state changed to: {state}")

        elif ev_type == "LOG":
            msg = event_data.get("message", "")
            self.message_received.emit(f"[SDR] {msg}")

        elif ev_type == "STATUS":
            des = event_data.get("desired_state", "")
            obs = event_data.get("observed_state", "")
            sess = event_data.get("session_id", "")
            self.message_received.emit(f"[SDR STATUS] Desired: {des} | Observed: {obs} | Session: {sess}")

