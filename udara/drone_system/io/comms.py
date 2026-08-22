"""
Comms Module — Kompatibilitas wrapper untuk SerialHandler.
Mencegah duplikasi driver serial dan memusatkan operasi I/O ke SerialHandler.
"""

from .serial_handler import SerialHandler, START_MARKER, END_MARKER, CHUNK_SIZE
from ..core.config_manager import get_global_config_manager


class SerialCommunicator(SerialHandler):
    """
    Wrapper kompatibilitas untuk SerialHandler.
    Mewarisi seluruh fungsi koneksi, command handling, dan file transfer.
    """

    def __init__(self, port=None, baudrate=None, timeout=None):
        cfg = get_global_config_manager().get_config()
        port = port if port is not None else cfg.get("serial_port", "/dev/ttyUSB0")
        baudrate = baudrate if baudrate is not None else cfg.get("baud_rate", 230400)
        timeout = timeout if timeout is not None else cfg.get("serial_timeout", 5)
        super().__init__(port=port, baudrate=baudrate, timeout=timeout)

