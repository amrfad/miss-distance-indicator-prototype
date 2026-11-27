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
        self._buffer_lock = threading.Lock()

        # Continuous mode state
        self._stop_flag = threading.Event()

        # Deduplikasi: tracking interval waktu event unik per session (session_id, abs_start, abs_end)
        self._seen_session_events: list[tuple[str, float, float]] = []  # list of (session_id, abs_start, abs_end)
        self._seen_legacy_keys: set[tuple] = set()                      # fallback for legacy format
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
            self._seen_session_events.clear()
            self._seen_legacy_keys.clear()
        with self._buffer_lock:
            self._json_buffer = bytearray()

    # ------------------------------------------------------------------
    # Internal data router (didaftarkan ke FileTransferManager)
    # ------------------------------------------------------------------

    def _route_data(self, raw_data: bytes):
        """Terima data dari FileTransferManager dan simpan ke buffer internal secara thread-safe."""
        with self._buffer_lock:
            self._json_buffer.extend(raw_data)

    # ------------------------------------------------------------------
    # Deduplikasi helper
    # ------------------------------------------------------------------

    def _filter_duplicate_events(self, parsed_json: dict) -> dict:
        """
        Filter event yang sudah pernah diterima sebelumnya.

        Strategi:
          1. Jika event memiliki rentang waktu 'event_abs_start_sec' dan 'event_abs_end_sec':
             Cek apakah rentang waktu [start, end] beririsan (overlap) dengan event yang
             sudah pernah diterima pada session yang sama (dengan toleransi edge 0.05s).
             Jika beririsan, event dianggap sebagai tembakan yang sama dan dibuang.
          2. Fallback (format lama):
             Kunci deduplikasi: (chunk_timestamp, event_number).

        Args:
            parsed_json: Dict JSON yang sudah di-parse

        Returns:
            Salinan dict dengan field 'events' yang sudah difilter.
        """
        events = parsed_json.get("events")
        if not isinstance(events, list):
            return parsed_json  # Format tidak dikenal, lewati deduplikasi

        session_id_top = parsed_json.get("session_id")
        filtered = []
        new_session_events = []
        new_legacy_keys = []

        with self._seen_lock:
            for ev in events:
                session_id = ev.get("session_id") or session_id_top
                abs_start = ev.get("event_abs_start_sec")
                abs_end = ev.get("event_abs_end_sec")

                if abs_start is not None and session_id:
                    try:
                        start_val = float(abs_start)
                        end_val = float(abs_end) if abs_end is not None else start_val + 0.25

                        # Cek apakah interval [start_val, end_val] beririsan dengan event yang sudah ada
                        TOLERANCE = 0.05
                        is_dup = False
                        for seen_sess, seen_start, seen_end in self._seen_session_events:
                            if seen_sess == session_id:
                                overlap_start = max(seen_start - TOLERANCE, start_val - TOLERANCE)
                                overlap_end = min(seen_end + TOLERANCE, end_val + TOLERANCE)
                                intersection = overlap_end - overlap_start
                                if intersection > 0:
                                    self._log(
                                        f"[DEDUP] Overlap duplicate skipped: session={session_id}, "
                                        f"interval=[{start_val:.3f}s, {end_val:.3f}s] "
                                        f"overlaps with seen=[{seen_start:.3f}s, {seen_end:.3f}s] "
                                        f"(intersection={intersection:.3f}s)"
                                    )
                                    is_dup = True
                                    break

                        if is_dup:
                            continue

                        new_session_events.append((session_id, start_val, end_val))
                        filtered.append(ev)
                    except (ValueError, TypeError):
                        filtered.append(ev)
                else:
                    # Fallback untuk format lama tanpa waktu absolut
                    chunk_ts = ev.get("chunk_timestamp", f"_unique_{id(ev)}")
                    ev_num = ev.get("event_number", "_")
                    key = (chunk_ts, ev_num)

                    if key in self._seen_legacy_keys:
                        self._log(f"[DEDUP] Event duplikat dilewati: chunk={chunk_ts}, event={ev_num}")
                        continue

                    new_legacy_keys.append(key)
                    filtered.append(ev)

            # Daftarkan semua event baru
            self._seen_session_events.extend(new_session_events)
            self._seen_legacy_keys.update(new_legacy_keys)

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
            if self.serial_manager is not None and not self.serial_manager.is_connected():
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
                    # Jika buffer tidak mengandung [START], bersihkan secara thread-safe
                    with self._buffer_lock:
                        if b"[START]" not in self._json_buffer:
                            self._json_buffer = bytearray()

        finally:
            self.file_transfer.clear_json_router()
            with self._buffer_lock:
                self._json_buffer = bytearray()
            self._log("[RX] Continuous JSON receiver stopped.")

        return any_success

    # ------------------------------------------------------------------
    # Single-shot reception (legacy & internal)
    # ------------------------------------------------------------------

    def _receive_once(self, on_saved=None) -> bool:
        """Terima satu paket JSON lalu berhenti."""
        try:
            if self.serial_manager is not None and not self.serial_manager.is_connected():
                self._log("[ERROR] Serial not connected")
                return False

            self.file_transfer.set_json_router(self._route_data)

            return self._receive_once_inner(on_saved)

        except Exception as e:
            self._log(f"[ERROR] Failed to receive JSON: {e}")
            self._log(f"Traceback: {traceback.format_exc()}")
            return False
        finally:
            self.file_transfer.clear_json_router()
            with self._buffer_lock:
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
                # Jika stop diminta saat IDLE (tidak sedang menerima paket), keluar dengan bersih
                if self._stop_flag.is_set() and not receiving:
                    self._log("[RX] Stop requested (idle), exiting wait.")
                    return False

                with self._buffer_lock:
                    if len(self._json_buffer) > 0:
                        data = bytes(self._json_buffer)
                        buffer += data
                        self._json_buffer = bytearray()
                        timeout_counter = 0

                        self._log(
                            f"[DEBUG] Received {len(data)} bytes, buffer total: {len(buffer)} bytes"
                        )

                # Saat belum receiving: pisahkan text lines command response (misal OK:..., ERROR:...)
                if not receiving:
                    while b"\n" in buffer and (b"[START]" not in buffer or buffer.find(b"\n") < buffer.find(b"[START]")):
                        line_bytes, buffer = buffer.split(b"\n", 1)
                        line_str = line_bytes.decode("utf-8", errors="ignore").strip()
                        if line_str:
                            self._log(f"[RX-MSG] {line_str}")
                            # Teruskan ke handler serial_manager agar signal message_received ter-emit ke GUI
                            if hasattr(self.serial_manager, "on_message_received") and self.serial_manager.on_message_received:
                                self.serial_manager.on_message_received(line_str)

                    # Cek START marker
                    if b"[START]\n" in buffer:
                        receiving = True
                        start_time = time.time()
                        start_idx = buffer.find(b"[START]\n")
                        buffer = buffer[start_idx + len(b"[START]\n"):].lstrip(b"\n")
                        self._log("[RX] [START] marker detected. Receiving JSON...")
                        self._log(
                            f"[DEBUG] Buffer after START (first 100 bytes): {repr(buffer[:100])}"
                        )
                    elif b"[START]" in buffer:
                        # Marker belum lengkap dengan newline, tunggu chunk data berikutnya
                        pass

                # Cek END marker jika sedang receiving
                if receiving:
                    end_idx = -1
                    end_marker_len = 0
                    if b"\n[END]\n" in buffer:
                        end_idx = buffer.find(b"\n[END]\n")
                        end_marker_len = len(b"\n[END]\n")
                    elif b"[END]\n" in buffer:
                        end_idx = buffer.find(b"[END]\n")
                        end_marker_len = len(b"[END]\n")
                    elif b"\n[END]" in buffer:
                        end_idx = buffer.find(b"\n[END]")
                        end_marker_len = len(b"\n[END]")
                    elif b"[END]" in buffer:
                        end_idx = buffer.find(b"[END]")
                        end_marker_len = len(b"[END]")

                    if end_idx >= 0:
                        json_data = buffer[:end_idx].rstrip(b"\n")
                        # Simpan sisa data setelah END marker untuk paket berikutnya secara thread-safe
                        trailing_data = buffer[end_idx + end_marker_len:].lstrip(b"\n")
                        if trailing_data:
                            with self._buffer_lock:
                                self._json_buffer = bytearray(trailing_data) + self._json_buffer

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
                                on_saved(file_path)  # path absolut agar caller bisa os.path.exists()

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
        """Simpan raw data ke file debug untuk analisis (disimpan di save_directory)."""
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        debug_file = os.path.join(self.save_directory, f"debug_json_{ts}.txt")
        try:
            os.makedirs(self.save_directory, exist_ok=True)
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
            buffer_file = os.path.join(self.save_directory, f"debug_buffer_{ts}.txt")
            try:
                with open(buffer_file, "wb") as f:
                    f.write(buffer)
                self._log(f"Full buffer saved to: {buffer_file}")
            except Exception:
                pass
