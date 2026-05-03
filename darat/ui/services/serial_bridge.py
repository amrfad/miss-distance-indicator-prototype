"""
SerialBridge — Qt-native wrapper around SerialManager.

Wraps darat.serial_manager.SerialManager to emit Qt signals from
background threads, enabling thread-safe UI updates.
"""

import json

from PyQt6.QtCore import QObject, pyqtSignal

from ...serial_manager import SerialManager
from ...config import (
    CMD_SET_CONFIG, CONFIG_TX_START_MARKER, CONFIG_TX_END_MARKER,
)
from ...config_manager import get_global_config_manager


class SerialBridge(QObject):
    """Qt signal bridge for SerialManager.

    Signals are emitted from SerialManager's internal listener thread.
    Qt auto-queues cross-thread signal-slot connections, so UI slots
    connected here are always called on the GUI thread.
    """

    # Emitted when connection status changes (connected, port_name)
    connection_changed = pyqtSignal(bool, str)
    # Emitted for every log/status message from the serial layer
    message_received   = pyqtSignal(str)
    # Emitted when raw bytes arrive (forwarded to FileTransferManager)
    data_received      = pyqtSignal(bytes)
    # Emitted after a command is successfully written
    command_sent       = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        cfg = get_global_config_manager().get_config()
        self._manager = SerialManager(baud_rate=cfg.get("baud_rate", 230400))
        self._connected = False

        self._manager.set_callbacks(
            on_message=self._on_message,
            on_status=self._on_status,
            on_data=self._on_data,
        )

    # ── Public API ──────────────────────────────────────────────────────

    @property
    def manager(self) -> SerialManager:
        """Underlying SerialManager (for JsonReceiver / FileTransfer wiring)."""
        return self._manager

    def is_connected(self) -> bool:
        return self._manager.is_connected()

    def get_available_ports(self) -> list[dict]:
        return self._manager.get_available_ports()

    def get_port_info(self) -> dict | None:
        return self._manager.get_port_info()

    def connect_auto(self) -> bool:
        """Connect using the configured port and baud rate."""
        cfg = get_global_config_manager().get_config()
        
        # Sync manager parameters with latest config
        self._manager.baud_rate = cfg.get("baud_rate", 230400)
        self._manager.timeout = cfg.get("serial_timeout", 1)
        
        # Try to connect to configured port
        port_to_try = cfg.get("serial_port", "COM3")  # This is the universal serial_port now
        success = self._manager.connect_to_port(port_to_try)
        
        # Fallback to auto-detect only if configured port fails
        if not success:
            success = self._manager.detect_and_connect()
            
        info = self._manager.get_port_info()
        port = info["port"] if info else ""
        self.connection_changed.emit(success, port)
        return success

    def connect_to_port(self, port: str) -> bool:
        cfg = get_global_config_manager().get_config()
        self._manager.baud_rate = cfg.get("baud_rate", 230400)
        self._manager.timeout = cfg.get("serial_timeout", 1)
        
        success = self._manager.connect_to_port(port)
        info = self._manager.get_port_info()
        port_name = info["port"] if info else port
        self.connection_changed.emit(success, port_name if success else "")
        return success

    def disconnect(self):
        self._manager.disconnect()
        self.connection_changed.emit(False, "")

    def send_command(self, command: str) -> bool:
        """Send a plain text command (e.g. 'START_REC') to the drone."""
        result = self._manager.send_command(command)
        if result:
            self.command_sent.emit(command)
        return result

    def send_set_config(self, runtime_config: dict) -> bool:
        """Send SET_CONFIG payload via serial (Communication Contract § 5).

        Format:
            SET_CONFIG\\n
            [CONFIG_START]\\n
            {json}\\n
            [CONFIG_END]\\n
        """
        if not self._manager.is_connected():
            self.message_received.emit(
                "[ERROR] Serial not connected — cannot send SET_CONFIG"
            )
            return False

        sp = self._manager.serial_port
        if sp is None or not sp.is_open:
            self.message_received.emit("[ERROR] Serial port not open")
            return False

        try:
            payload = json.dumps(runtime_config, ensure_ascii=False)
            lines = [
                f"{CMD_SET_CONFIG}\n",
                f"{CONFIG_TX_START_MARKER}\n",
                f"{payload}\n",
                f"{CONFIG_TX_END_MARKER}\n",
            ]
            for line in lines:
                sp.write(line.encode("utf-8"))

            self.command_sent.emit(f"SET_CONFIG ({len(runtime_config)} params)")
            self.message_received.emit(
                f"[SET_CONFIG] Sent {len(runtime_config)} runtime params via serial"
            )
            return True

        except Exception as exc:
            self.message_received.emit(f"[ERROR] SET_CONFIG failed: {exc}")
            return False

    # ── Private callbacks (called from SerialManager's thread) ──────────

    def _on_message(self, msg: str):
        self.message_received.emit(msg)

    def _on_status(self, msg: str):
        self.message_received.emit(msg)

    def _on_data(self, data: bytes):
        self.data_received.emit(data)
