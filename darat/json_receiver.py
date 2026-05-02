"""
JSON Receiver Module
Mengelola penerimaan file JSON via serial dengan protokol [START]/[END] marker.
Diekstrak dari EventGUI.receive_json() di versi original.
"""

import os
import json
import time
import datetime
import traceback


class JsonReceiver:
    """
    Menerima JSON melalui serial port menggunakan protokol [START]/[END] marker.

    Dijalankan di thread terpisah (non-blocking terhadap GUI).

    Usage:
        receiver = JsonReceiver(serial_manager, file_transfer, log_callback)
        # Di thread:
        threading.Thread(target=receiver.receive_json, kwargs={"on_saved": callback}).start()
    """

    def __init__(self, serial_manager, file_transfer, log_callback, save_directory: str = None):
        """
        Args:
            serial_manager: Instance SerialManager
            file_transfer: Instance FileTransferManager (untuk set/clear json router)
            log_callback: Callable(str) untuk logging
            save_directory: Direktori untuk menyimpan JSON yang diterima
        """
        self.serial_manager = serial_manager
        self.file_transfer = file_transfer
        self._log = log_callback
        self.save_directory = save_directory or os.getcwd()

        # Internal buffer (diisi via _route_data yang didaftarkan ke file_transfer)
        self._json_buffer = bytearray()

    @property
    def save_directory(self):
        return self._save_directory

    @save_directory.setter
    def save_directory(self, value):
        self._save_directory = value

    # ------------------------------------------------------------------
    # Internal data router (didaftarkan ke FileTransferManager)
    # ------------------------------------------------------------------

    def _route_data(self, raw_data: bytes):
        """Terima data dari FileTransferManager dan simpan ke buffer internal."""
        self._json_buffer.extend(raw_data)

    # ------------------------------------------------------------------
    # Public: receive_json (dijalankan di thread)
    # ------------------------------------------------------------------

    def receive_json(self, on_saved=None):
        """
        Tunggu dan terima JSON dari serial port.
        Identik secara logika dengan EventGUI.receive_json() di versi original.

        Args:
            on_saved: Optional Callable(filename: str) dipanggil saat JSON berhasil disimpan.

        Returns:
            bool: True jika berhasil, False jika gagal/timeout.
        """
        try:
            if not self.serial_manager.is_connected():
                self._log("[ERROR] Serial not connected")
                return False

            # Daftarkan buffer ke FileTransferManager
            self._json_buffer = bytearray()
            self.file_transfer.set_json_router(self._route_data)

            buffer = b""
            receiving = False
            start_time = None
            end_detected = False
            end_detected_time = None

            timeout_counter = 0
            max_timeout = 1500  # 15 detik (150 x 0.1s)

            self._log("Waiting for JSON data...")

            while timeout_counter < max_timeout:
                # Ambil data dari buffer internal (diisi oleh _route_data)
                if len(self._json_buffer) > 0:
                    data = bytes(self._json_buffer)
                    buffer += data
                    self._json_buffer = bytearray()
                    timeout_counter = 0

                    self._log(
                        f"[DEBUG] Received {len(data)} bytes, buffer total: {len(buffer)} bytes"
                    )

                    # Cek START marker
                    if not receiving and b"[START]" in buffer:
                        receiving = True
                        start_time = time.time()
                        start_idx = buffer.find(b"[START]\n")
                        start_idx += len(b"[START]\n")
                        while start_idx < len(buffer) and buffer[start_idx: start_idx + 1] == b"\n":
                            start_idx += 1
                        buffer = buffer[start_idx:]
                        self._log("[RX] [START] marker detected. Receiving JSON...")
                        self._log(
                            f"[DEBUG] Buffer after START (first 100 bytes): {repr(buffer[:100])}"
                        )

                # Cek END marker
                if receiving and not end_detected:
                    if (
                        b"\n[END]" in buffer
                        or b"[END]\n" in buffer
                        or b"[END]" in buffer
                        or b"\n[END]\n" in buffer
                    ):
                        end_detected = True
                        end_detected_time = time.time()
                        self._log("[DEBUG] [END] marker detected, waiting for remaining data...")

                # Proses JSON setelah END + jeda 1 detik
                if end_detected and end_detected_time:
                    time_since_end = time.time() - end_detected_time
                    if time_since_end >= 1.0:
                        end_idx = -1
                        if b"\n[END]" in buffer:
                            end_idx = buffer.find(b"\n[END]")
                        elif b"[END]\n" in buffer:
                            end_idx = buffer.find(b"[END]\n")
                        elif b"\n[END]\n" in buffer:
                            end_idx = buffer.find(b"\n[END]\n")
                        else:
                            end_idx = buffer.find(b"[END]")

                        if end_idx >= 0:
                            json_data = buffer[:end_idx]
                            while json_data.endswith(b"\n"):
                                json_data = json_data[:-1]

                            self._log(
                                f"[DEBUG] Processing JSON - [END] at position {end_idx}"
                            )
                            self._log(f"[DEBUG] Total buffer size: {len(buffer)} bytes")
                            self._log(f"[DEBUG] JSON data length: {len(json_data)} bytes")
                            self._log(
                                f"[DEBUG] JSON preview (first 200 bytes): {repr(json_data[:200])}"
                            )
                            self._log(
                                f"[DEBUG] JSON preview (last 200 bytes): {repr(json_data[-200:])}"
                            )

                            end_time = time.time()

                            try:
                                json_str = json_data.decode("utf-8")

                                # Validasi struktur JSON (brace counting)
                                open_braces = json_str.count("{")
                                close_braces = json_str.count("}")
                                open_brackets = json_str.count("[")
                                close_brackets = json_str.count("]")

                                if open_braces != close_braces:
                                    self._log(
                                        f"[ERROR] Unbalanced braces: {{ {open_braces} vs }} {close_braces}"
                                    )
                                    self._log("[ERROR] JSON incomplete or corrupted")
                                    after_end = buffer[end_idx:]
                                    self._log(
                                        f"[DEBUG] Data after [END] ({len(after_end)} bytes): {repr(after_end[:200])}"
                                    )
                                    debug_file = f"debug_json_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                                    with open(debug_file, "wb") as f:
                                        f.write(json_data)
                                    self._log(f"Raw data saved to: {debug_file}")
                                    buffer_file = f"debug_buffer_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                                    with open(buffer_file, "wb") as f:
                                        f.write(buffer)
                                    self._log(f"Full buffer saved to: {buffer_file}")
                                    return False

                                if open_brackets != close_brackets:
                                    self._log(
                                        f"[ERROR] Unbalanced brackets: [ {open_brackets} vs ] {close_brackets}"
                                    )
                                    self._log("[ERROR] JSON incomplete or corrupted")
                                    after_end = buffer[end_idx:]
                                    self._log(
                                        f"[DEBUG] Data after [END] ({len(after_end)} bytes): {repr(after_end[:200])}"
                                    )
                                    debug_file = f"debug_json_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                                    with open(debug_file, "wb") as f:
                                        f.write(json_data)
                                    self._log(f"Raw data saved to: {debug_file}")
                                    return False

                                parsed_json = json.loads(json_str)

                                # Simpan ke file dengan timestamp
                                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                filename = f"tdoa_{timestamp}.json"
                                file_path = os.path.join(self.save_directory, filename)

                                with open(file_path, "w", encoding="utf-8") as f:
                                    json.dump(parsed_json, f, indent=2, ensure_ascii=False)

                                elapsed = end_time - start_time
                                self._log(f"✓ JSON received and saved to '{filename}'")
                                self._log(
                                    f"  Events: {parsed_json.get('event_count', 0)} | "
                                    f"Size: {len(json_data)} bytes"
                                )
                                self._log(f"  Time: {elapsed:.2f} seconds")

                                # Panggil callback opsional (misal untuk update status label)
                                if on_saved:
                                    on_saved(filename)

                                return True

                            except json.JSONDecodeError as e:
                                self._log(f"✗ Invalid JSON format: {e}")
                                debug_file = f"debug_json_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                                with open(debug_file, "wb") as f:
                                    f.write(json_data)
                                self._log(f"Raw data saved to: {debug_file} for debugging")
                                return False

                time.sleep(0.1)
                timeout_counter += 1

            if receiving:
                self._log(
                    f"[ERROR] Timeout waiting for [END] marker. "
                    f"Received {len(buffer)} bytes so far."
                )
                self._log(f"[DEBUG] Buffer content: {repr(buffer[:200])}")
            else:
                self._log("[ERROR] Timeout waiting for [START] marker")

            return False

        except Exception as e:
            self._log(f"[ERROR] Failed to receive JSON: {e}")
            self._log(f"Traceback: {traceback.format_exc()}")
            return False
        finally:
            # Selalu bersihkan router saat selesai
            self.file_transfer.clear_json_router()
            self._json_buffer = bytearray()
