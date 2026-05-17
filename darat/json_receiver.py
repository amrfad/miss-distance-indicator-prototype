"""
JSON Receiver Module
Mengelola penerimaan file JSON via serial dengan protokol [START]/[END] marker.

Mode baru:
  - continuous=True: Loop terus-menerus menerima paket JSON berulang kali,
    berhenti hanya saat stop_continuous() dipanggil.
  - Deduplikasi: Berdasarkan kombinasi (chunk_timestamp, event_number) dari
    field dalam JSON yang diterima, untuk mencegah event yang sama (yang ada
    dalam overlap) diproses dua kali.
"""

import os
import json
import time
import datetime
import traceback
import threading


class JsonReceiver:
    """
    Menerima JSON melalui serial port menggunakan protokol [START]/[END] marker.

    Dijalankan di thread terpisah (non-blocking terhadap GUI).

    Mode:
        continuous=False (default) — satu kali terima lalu berhenti (legacy)
        continuous=True            — loop terus sampai stop_continuous() dipanggil

    Deduplikasi:
        Event dengan kombinasi (chunk_timestamp, event_number) yang sama tidak
        akan disimpan ulang meski datang lebih dari satu kali (karena overlap).

    Usage (continuous):
        receiver = JsonReceiver(serial_manager, file_transfer, log_callback)
        t = threading.Thread(target=receiver.receive_json, kwargs={"on_saved": cb, "continuous": True})
        t.start()
        # saat ingin berhenti:
        receiver.stop_continuous()
        t.join()
    """

    def __init__(self, serial_manager, file_transfer, log_callback, save_directory: str = None):
        """
        Args:
            serial_manager: Instance SerialManager
            file_transfer:  Instance FileTransferManager (untuk set/clear json router)
            log_callback:   Callable(str) untuk logging
            save_directory: Direktori untuk menyimpan JSON yang diterima
        """
        self.serial_manager = serial_manager
        self.file_transfer = file_transfer
        self._log = log_callback
        self.save_directory = save_directory or os.getcwd()

        # Internal buffer (diisi via _route_data yang didaftarkan ke file_transfer)
        self._json_buffer = bytearray()

        # Continuous mode state
        self._stop_flag = threading.Event()

        # Deduplikasi: set of (chunk_timestamp, event_number) yang sudah pernah disimpan
        self._seen_event_ids: set[tuple] = set()
        self._seen_lock = threading.Lock()

    @property
    def save_directory(self):
        return self._save_directory

    @save_directory.setter
    def save_directory(self, value):
        self._save_directory = value

    # ------------------------------------------------------------------
    # Continuous mode control
    # ------------------------------------------------------------------

    def stop_continuous(self):
        """
        Sinyal agar loop penerimaan berhenti setelah paket JSON saat ini selesai.
        """
        self._stop_flag.set()

    def reset(self):
        """
        Reset state untuk memulai sesi penerimaan baru.
        Bersihkan duplikasi cache dan stop flag.
        """
        self._stop_flag.clear()
        with self._seen_lock:
            self._seen_event_ids.clear()

    # ------------------------------------------------------------------
    # Internal data router (didaftarkan ke FileTransferManager)
    # ------------------------------------------------------------------

    def _route_data(self, raw_data: bytes):
        """Terima data dari FileTransferManager dan simpan ke buffer internal."""
        self._json_buffer.extend(raw_data)

    # ------------------------------------------------------------------
    # Deduplikasi helper
    # ------------------------------------------------------------------

    def _filter_duplicate_events(self, parsed_json: dict) -> dict:
        """
        Filter event yang sudah pernah diterima sebelumnya.

        Kunci deduplikasi: (chunk_timestamp, event_number)
        Jika chunk_timestamp tidak ada di JSON (format lama), gunakan UUID acak
        sehingga selalu dianggap unik.

        Args:
            parsed_json: Dict JSON yang sudah di-parse

        Returns:
            Salinan dict dengan field 'events' yang sudah difilter.
            Mengembalikan dict yang sama jika tidak ada field 'events'.
        """
        events = parsed_json.get("events")
        if not isinstance(events, list):
            return parsed_json  # Format tidak dikenal, lewati deduplikasi

        filtered = []
        new_ids = []

        for ev in events:
            chunk_ts = ev.get("chunk_timestamp", f"_unique_{id(ev)}")
            ev_num = ev.get("event_number", "_")
            key = (chunk_ts, ev_num)

            with self._seen_lock:
                if key in self._seen_event_ids:
                    self._log(f"[DEDUP] Event duplikat dilewati: chunk={chunk_ts}, event={ev_num}")
                    continue
                new_ids.append(key)

            filtered.append(ev)

        # Daftarkan semua ID baru setelah selesai iterasi
        with self._seen_lock:
            for key in new_ids:
                self._seen_event_ids.add(key)

        if len(filtered) < len(events):
            self._log(
                f"[DEDUP] {len(events) - len(filtered)} event duplikat dibuang, "
                f"{len(filtered)} event unik disimpan."
            )

        result = dict(parsed_json)
        result["events"] = filtered
        result["event_count"] = len(filtered)
        return result

    # ------------------------------------------------------------------
    # Public: receive_json (dijalankan di thread)
    # ------------------------------------------------------------------

    def receive_json(self, on_saved=None, continuous: bool = False):
        """
        Tunggu dan terima JSON dari serial port.

        Args:
            on_saved:   Optional Callable(filename: str) dipanggil saat JSON berhasil disimpan.
            continuous: Jika True, loop terus menerus menerima paket JSON
                        sampai stop_continuous() dipanggil.

        Returns:
            bool: True jika minimal satu JSON berhasil diterima.
        """
        if continuous:
            return self._receive_continuous(on_saved)
        else:
            return self._receive_once(on_saved)

    # ------------------------------------------------------------------
    # Continuous loop
    # ------------------------------------------------------------------

    def _receive_continuous(self, on_saved=None) -> bool:
        """Loop terus-menerus sampai stop_continuous() dipanggil."""
        self._log("[RX] Continuous JSON receiver started.")
        any_success = False

        try:
            if not self.serial_manager.is_connected():
                self._log("[ERROR] Serial not connected")
                return False

            self.file_transfer.set_json_router(self._route_data)

            while not self._stop_flag.is_set():
                ok = self._receive_once_inner(on_saved)
                if ok:
                    any_success = True
                # Jika gagal tapi stop belum di-set, tunggu sebentar dan coba lagi
                elif not self._stop_flag.is_set():
                    self._log("[RX] Menunggu paket berikutnya...")
                    # Reset buffer untuk siap menerima transmisi berikutnya
                    self._json_buffer = bytearray()

        finally:
            self.file_transfer.clear_json_router()
            self._json_buffer = bytearray()
            self._log("[RX] Continuous JSON receiver stopped.")

        return any_success

    # ------------------------------------------------------------------
    # Single-shot reception (legacy & internal)
    # ------------------------------------------------------------------

    def _receive_once(self, on_saved=None) -> bool:
        """Terima satu paket JSON lalu berhenti."""
        try:
            if not self.serial_manager.is_connected():
                self._log("[ERROR] Serial not connected")
                return False

            self._json_buffer = bytearray()
            self.file_transfer.set_json_router(self._route_data)

            return self._receive_once_inner(on_saved)

        except Exception as e:
            self._log(f"[ERROR] Failed to receive JSON: {e}")
            self._log(f"Traceback: {traceback.format_exc()}")
            return False
        finally:
            self.file_transfer.clear_json_router()
            self._json_buffer = bytearray()

    def _receive_once_inner(self, on_saved=None) -> bool:
        """
        Inti penerimaan satu paket JSON (digunakan oleh keduanya).
        Buffer harus sudah bersih saat masuk.
        """
        try:
            buffer = b""
            receiving = False
            start_time = None
            end_detected = False
            end_detected_time = None

            timeout_counter = 0
            max_timeout = 1500  # 15 detik (150 × 0.1s)

            self._log("Waiting for JSON data...")

            while timeout_counter < max_timeout:
                # Jika stop diminta di tengah tunggu, keluar
                if self._stop_flag.is_set():
                    self._log("[RX] Stop requested, aborting wait.")
                    return False

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
                                f"[DEBUG] Processing JSON — [END] at position {end_idx}"
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

                                open_braces = json_str.count("{")
                                close_braces = json_str.count("}")
                                open_brackets = json_str.count("[")
                                close_brackets = json_str.count("]")

                                if open_braces != close_braces:
                                    self._log(
                                        f"[ERROR] Unbalanced braces: {{ {open_braces} vs }} {close_braces}"
                                    )
                                    self._log("[ERROR] JSON incomplete or corrupted")
                                    self._save_debug_file(json_data, buffer, end_idx)
                                    return False

                                if open_brackets != close_brackets:
                                    self._log(
                                        f"[ERROR] Unbalanced brackets: [ {open_brackets} vs ] {close_brackets}"
                                    )
                                    self._log("[ERROR] JSON incomplete or corrupted")
                                    self._save_debug_file(json_data, buffer, end_idx)
                                    return False

                                parsed_json = json.loads(json_str)

                                # Deduplikasi event
                                parsed_json = self._filter_duplicate_events(parsed_json)

                                # Jika setelah deduplikasi tidak ada event tersisa,
                                # tetap simpan file agar ground station tahu chunk diterima
                                # (dengan event_count = 0)

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

                                if on_saved:
                                    on_saved(filename)

                                return True

                            except json.JSONDecodeError as e:
                                self._log(f"✗ Invalid JSON format: {e}")
                                self._save_debug_file(json_data, None, None)
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

    # ------------------------------------------------------------------
    # Debug helper
    # ------------------------------------------------------------------

    def _save_debug_file(self, json_data: bytes, buffer: bytes | None, end_idx: int | None):
        """Simpan raw data ke file debug untuk analisis."""
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_file = f"debug_json_{ts}.txt"
        try:
            with open(debug_file, "wb") as f:
                f.write(json_data)
            self._log(f"Raw data saved to: {debug_file}")
        except Exception:
            pass

        if buffer is not None and end_idx is not None:
            after_end = buffer[end_idx:]
            self._log(
                f"[DEBUG] Data after [END] ({len(after_end)} bytes): {repr(after_end[:200])}"
            )
            buffer_file = f"debug_buffer_{ts}.txt"
            try:
                with open(buffer_file, "wb") as f:
                    f.write(buffer)
                self._log(f"Full buffer saved to: {buffer_file}")
            except Exception:
                pass
