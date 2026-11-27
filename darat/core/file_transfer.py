"""
File Transfer Module
Mengelola penerimaan file via serial (protokol START/END marker).
Diekstrak dari EventGUI.process_received_data / handle_file_start / handle_file_end.
"""

import os
from .config_manager import get_global_config_manager


def get_file_type(ext: str) -> str:
    """Return human-readable file type string dari ekstensi file."""
    mapping = {
        ".mp4": "Video",
        ".wav": "Audio",
        ".txt": "Text",
        ".json": "JSON",
    }
    return mapping.get(ext.lower(), "Unknown")


class FileTransferManager:
    """
    State machine untuk penerimaan file via serial.

    State transitions:
        idle → receiving (saat START marker diterima)
        receiving → idle (saat END marker diterima / error)

    Usage:
        ft = FileTransferManager(log_callback=..., save_directory=...)
        # Hubungkan ke SerialManager:
        serial_manager.set_callbacks(on_data=ft.process_incoming_data)
    """

    def __init__(self, log_callback, save_directory: str = None):
        """
        Args:
            log_callback: Callable(str) untuk logging pesan
            save_directory: Direktori default untuk menyimpan file
        """
        self._log = log_callback
        self.save_directory = save_directory or os.getcwd()

        # State
        self.receiving_file = False
        self.file_buffer = bytearray()
        self.expected_file_size = 0
        self.current_file_name = ""

        # Optional router untuk JSON (set oleh JsonReceiver saat aktif)
        self._json_router = None

    # ------------------------------------------------------------------
    # JSON Router (digunakan oleh JsonReceiver untuk mengambil alih data)
    # ------------------------------------------------------------------

    def set_json_router(self, callback):
        """Arahkan incoming data ke callback (misal JsonReceiver). Dipanggil oleh JsonReceiver."""
        self._json_router = callback

    def clear_json_router(self):
        """Kembalikan routing ke file transfer normal."""
        self._json_router = None

    # ------------------------------------------------------------------
    # Entry point: dipanggil oleh SerialManager callback
    # ------------------------------------------------------------------

    def process_incoming_data(self, raw_data: bytes):
        """
        Proses data mentah dari serial port.
        Identik dengan EventGUI.process_received_data() di versi original.
        """
        try:
            # Jika JSON receiver aktif, alihkan semua data ke sana
            if self._json_router is not None:
                self._json_router(raw_data)
                return

            # Coba decode sebagai teks
            text_data = raw_data.decode("utf-8")
            text_data_stripped = text_data.strip()

            if text_data_stripped.startswith("START\n:"):
                self.handle_file_start(text_data_stripped)
            elif text_data_stripped == "\nEND\n":
                self.handle_file_end()
            elif self.receiving_file:
                self._append_file_data(raw_data)
            else:
                if text_data.strip():
                    self._log(f"Received: {text_data.strip()}")

        except UnicodeDecodeError:
            # Data binary — hanya valid saat menerima file
            if self.receiving_file:
                self._append_file_data(raw_data)
            else:
                self._log(f"Received binary data: {len(raw_data)} bytes")

    # ------------------------------------------------------------------
    # File transfer handlers
    # ------------------------------------------------------------------

    def handle_file_start(self, command: str):
        """
        Parse dan validasi perintah START file transfer.
        Format: 'START\\n:filename.ext:size_in_bytes'
        """
        try:
            parts = command.split(":")
            if len(parts) >= 3:
                self.current_file_name = parts[1]
                self.expected_file_size = int(parts[2])

                file_ext = os.path.splitext(self.current_file_name)[1].lower()
                supported_exts = [
                    ext.lower()
                    for ext in get_global_config_manager().get("supported_extensions")
                ]
                if file_ext not in supported_exts:
                    self._log(
                        f"Unsupported file type: {file_ext}. "
                        f"Only {', '.join(supported_exts)} are supported."
                    )
                    return

                self.file_buffer = bytearray()
                self.receiving_file = True
                file_type = get_file_type(file_ext)
                self._log(
                    f"Starting {file_type} file reception: "
                    f"{self.current_file_name} ({self.expected_file_size} bytes)"
                )
            else:
                self._log("Invalid file start command format")
        except Exception as e:
            self._log(f"Error processing file start: {e}")

    def handle_file_end(self):
        """Simpan file yang sudah diterima ke disk."""
        if not (self.receiving_file and self.current_file_name):
            self._log("Received FILE_END but not receiving file")
            return

        try:
            file_path = os.path.join(self.save_directory, self.current_file_name)
            file_ext = os.path.splitext(self.current_file_name)[1].lower()

            if file_ext == ".txt":
                try:
                    text_content = self.file_buffer.decode("utf-8")
                    with open(file_path, "w", encoding="utf-8") as f:
                        f.write(text_content)
                except UnicodeDecodeError:
                    with open(file_path, "wb") as f:
                        f.write(self.file_buffer)
            else:
                with open(file_path, "wb") as f:
                    f.write(self.file_buffer)

            file_type = get_file_type(file_ext)
            self._log(f"{file_type} file saved: {file_path} ({len(self.file_buffer)} bytes)")

            if len(self.file_buffer) != self.expected_file_size:
                self._log(
                    f"Warning: File size mismatch! "
                    f"Expected: {self.expected_file_size}, Received: {len(self.file_buffer)}"
                )

        except Exception as e:
            self._log(f"Error saving file: {e}")
        finally:
            self._reset_state()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _append_file_data(self, raw_data: bytes):
        self.file_buffer.extend(raw_data)
        progress = (
            (len(self.file_buffer) / self.expected_file_size * 100)
            if self.expected_file_size > 0
            else 0
        )
        file_ext = (
            os.path.splitext(self.current_file_name)[1].lower()
            if self.current_file_name
            else ""
        )
        file_type = get_file_type(file_ext)
        self._log(
            f"{file_type} data received: {len(raw_data)} bytes "
            f"(Total: {len(self.file_buffer)}/{self.expected_file_size} - {progress:.1f}%)"
        )

    def _reset_state(self):
        self.receiving_file = False
        self.file_buffer = bytearray()
        self.current_file_name = ""
        self.expected_file_size = 0
