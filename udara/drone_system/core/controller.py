"""
Main System Controller
Mengkoordinasi semua module untuk sistem drone audio detection.

Arsitektur continuous streaming:
  - arecord mengeluarkan raw PCM bytes ke stdout pipe
  - _stream_processor_thread membaca byte stream, membangun window overlap,
    dan memproses setiap chunk secara periodik
  - Setiap chunk disimpan ke subfolder chunks/ dan dikirim via serial
"""

import os
import io
import time
import uuid
import threading
import queue
import shutil
import numpy as np
import soundfile as sf
from datetime import datetime

from ..audio.recorder import AudioRecorder
from ..audio.processor import AudioProcessor
from ..audio.detector import EventDetector
from ..audio.logger import DataLogger
from ..audio.mic_health import assess_chunk_mic_health
from ..tdoa.tdoa import calculate_all_tdoa
from ..io.comms import SerialCommunicator
from .config import (
    EVENT_PADDING_SEC,
    TIMESTAMP_FORMAT,
    LOG_TIMESTAMP_FORMAT,
    POST_RECORDING_DELAY,
    DEVICE_PROFILES
)
from .config_manager import get_global_config_manager


class DroneAudioSystem:
    """Sistem utama yang mengkoordinasi semua module dengan continuous streaming."""

    def __init__(self, comms=None):
        """Initialize sistem dengan semua module yang diperlukan."""
        self.recorder = AudioRecorder()

        rec_status = self.recorder.get_status()
        output_format = rec_status.get("format", "S24_3LE")
        self.processor = AudioProcessor(output_format=output_format)

        self.detector = EventDetector()
        self.comms = comms if comms is not None else SerialCommunicator()

        self.current_session_id = None
        self.current_session_dir = None
        self.chunks_dir = None
        self.recording_start_time = None

        # Threading state
        self._stream_thread: threading.Thread | None = None
        self._worker_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self.chunk_queue = queue.Queue(maxsize=10) # Queue untuk membatasi worker thread

        cfg = get_global_config_manager().get_config()
        self.base_output_dir = cfg.get("base_output_dir", "drone_recordings")
        os.makedirs(self.base_output_dir, exist_ok=True)

        print(f"[SYSTEM] DroneAudioSystem initialized (format: {output_format})")

    def set_comms(self, comms):
        """Set shared serial handler/communicator instance."""
        self.comms = comms

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_recording(self):
        """
        Mulai recording session baru dengan continuous chunk processing.

        Returns:
            tuple: (success: bool, message: str)
        """
        if self.recorder.is_recording():
            return False, "Recording sudah berjalan"

        # Buat session folder
        timestamp = datetime.now().strftime(TIMESTAMP_FORMAT)
        uid = uuid.uuid4().hex[:6]
        session_id = f"session_{timestamp}_{uid}"
        self.current_session_id = session_id
        self.current_session_dir = os.path.join(self.base_output_dir, session_id)
        self.chunks_dir = os.path.join(self.current_session_dir, "chunks")
        os.makedirs(self.chunks_dir, exist_ok=True)

        # Mulai recording (streaming ke stdout pipe)
        success = self.recorder.start_recording()
        if not success:
            return False, "Failed to start recording"

        self.recording_start_time = time.time()
        self._stop_event.clear()
        
        # Bersihkan sisa queue dari sesi sebelumnya jika ada
        while not self.chunk_queue.empty():
            try:
                self.chunk_queue.get_nowait()
            except queue.Empty:
                break

        # Jalankan thread pemrosesan streaming (Producer)
        self._stream_thread = threading.Thread(
            target=self._stream_processor_thread,
            daemon=True,
            name="StreamProcessor"
        )
        self._stream_thread.start()
        
        # Jalankan thread worker (Consumer)
        self._worker_thread = threading.Thread(
            target=self._chunk_worker_loop,
            daemon=True,
            name="ChunkWorker"
        )
        self._worker_thread.start()

        return True, f"Recording started: {session_id}"

    def stop_and_process(self):
        """
        Stop recording. Thread streaming akan otomatis menyelesaikan
        sisa buffer sebagai chunk terakhir sebelum keluar.

        Returns:
            tuple: (success: bool, message: str, events: list | None)
        """
        if not self.recorder.is_recording():
            return False, "Tidak ada recording aktif", None

        # Sinyal thread untuk berhenti setelah selesai memproses sisa buffer
        self._stop_event.set()

        # Hentikan arecord (akan menutup stdout pipe, sehingga read() di thread return)
        self.recorder.stop_recording()
        time.sleep(POST_RECORDING_DELAY)

        # Tunggu thread selesai memproses sisa data (max 60 detik)
        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=60)
            
        # Sinyal worker thread untuk tutup buku (Sentinel)
        self.chunk_queue.put(None)
        
        # Tunggu worker thread memproses sisa antrian (max 60 detik)
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=60)

        self._reset_state()
        return True, "Recording stopped and processed", None

    def get_status(self):
        """
        Dapatkan status sistem.

        Returns:
            tuple: (success: bool, status_message: str, data: dict | None)
        """
        if self.recorder.is_recording():
            elapsed = time.time() - self.recording_start_time if self.recording_start_time else 0
            return True, f"RECORDING ({elapsed:.1f}s)", {"elapsed": elapsed}
        else:
            return True, "IDLE", None

    def get_system_info(self):
        """
        Dapatkan informasi lengkap sistem.

        Returns:
            dict: Dictionary berisi informasi sistem
        """
        cfg = get_global_config_manager().get_config()
        return {
            "recorder": self.recorder.get_status(),
            "processor_features": self.processor.get_available_features(),
            "output_directory": cfg.get("base_output_dir", "drone_recordings"),
            "current_session": self.current_session_dir,
        }

    # ------------------------------------------------------------------
    # Streaming thread
    # ------------------------------------------------------------------

    def _stream_processor_thread(self):
        """
        Thread utama yang membaca raw PCM dari stdout arecord.

        Algoritma:
          - Baca bytes secara continous ke dalam ring_buffer (bytearray)
          - Setiap kali ring_buffer >= bytes untuk (chunk_duration + overlap),
            ambil window terbaru, proses, kirim, lalu pertahankan 'overlap'
            bytes terakhir sebagai awal buffer berikutnya.
          - Saat stop_event di-set, proses sisa buffer sebagai chunk terakhir.
        """
        cfg = get_global_config_manager().get_config()
        chunk_dur = cfg.get("chunk_duration_sec", 5.0)
        overlap_dur = cfg.get("chunk_overlap_sec", 1.0)
        sample_rate = cfg.get("sample_rate", 48000)

        bpf = self.recorder.bytes_per_frame  # bytes per frame (all channels)
        chunk_bytes = self.recorder.bytes_for_duration(chunk_dur)
        overlap_bytes = self.recorder.bytes_for_duration(overlap_dur)
        window_bytes = chunk_bytes + overlap_bytes

        print(f"[STREAM] Chunk: {chunk_dur}s + {overlap_dur}s overlap = {window_bytes} bytes/window")

        ring_buffer = bytearray()
        READ_SIZE = 4096  # bytes per read call
        chunk_index = 0

        while True:
            data = self.recorder.read_raw_bytes(READ_SIZE)

            if data:
                ring_buffer.extend(data)
            elif not self.recorder.is_recording():
                # pipe EOF → arecord sudah berhenti
                break

            # Cek apakah sudah cukup untuk satu window chunk
            if len(ring_buffer) >= window_bytes:
                # Ambil window: overlap lama + chunk baru
                window = bytes(ring_buffer[:window_bytes])
                # Pertahankan overlap_bytes terakhir untuk window berikutnya
                ring_buffer = bytearray(ring_buffer[chunk_bytes:])

                chunk_offset_sec = round(chunk_index * chunk_dur, 3)
                # Masukkan ke antrian non-blocking. Jika queue penuh, buang chunk
                try:
                    self.chunk_queue.put_nowait((window, bpf, sample_rate, chunk_index, chunk_offset_sec))
                    chunk_index += 1
                except queue.Full:
                    print("[WARNING] Worker queue is FULL (Max 10). Dropping chunk ini agar streamer tidak freeze.")

            # Jika stop_event aktif, selesaikan sisa buffer lalu keluar
            if self._stop_event.is_set() and not data:
                break

        # Proses sisa buffer (chunk terakhir, bisa < 5 detik)
        if len(ring_buffer) > 0:
            min_bytes = self.recorder.bytes_for_duration(0.5)  # minimal 0.5 detik
            if len(ring_buffer) >= min_bytes:
                chunk_offset_sec = round(chunk_index * chunk_dur, 3)
                print(f"[STREAM] Processing final chunk ({len(ring_buffer)} bytes, offset: {chunk_offset_sec}s)")
                try:
                    self.chunk_queue.put_nowait((bytes(ring_buffer), bpf, sample_rate, chunk_index, chunk_offset_sec))
                except queue.Full:
                    print("[WARNING] Worker queue is FULL. Dropping final chunk.")
            else:
                print(f"[STREAM] Sisa buffer terlalu kecil ({len(ring_buffer)} bytes), diabaikan.")

        print("[STREAM] Stream processor thread selesai.")

    # ------------------------------------------------------------------
    # Chunk processing (Worker Thread)
    # ------------------------------------------------------------------
    
    def _chunk_worker_loop(self):
        """
        Consumer Thread: Mengambil item dari queue dan memprosesnya secara sinkron berurutan.
        Berhenti ketika menerima item `None` (Sentinel value).
        """
        while True:
            item = self.chunk_queue.get()
            if item is None:
                # Sentinel diterima, tutup buku
                print("[WORKER] Sentinel diterima, chunk worker thread selesai.")
                self.chunk_queue.task_done()
                break
                
            if len(item) == 5:
                window, bpf, sample_rate, chunk_idx, chunk_offset_sec = item
            else:
                window, bpf, sample_rate = item[:3]
                chunk_idx = 0
                chunk_offset_sec = 0.0

            try:
                # Disini jalankan pemrosesan chunk 
                self._process_chunk_bytes(
                    window, bpf, sample_rate,
                    chunk_idx=chunk_idx,
                    chunk_offset_sec=chunk_offset_sec
                )
            except Exception as e:
                print(f"[WORKER] Error pada chunk_worker_loop: {e}")
            finally:
                self.chunk_queue.task_done()

    def _process_chunk_bytes(self, raw_bytes: bytes, bpf: int, sample_rate: int, chunk_idx: int = 0, chunk_offset_sec: float = 0.0):
        """
        Konversi raw PCM bytes → proses audio → hitung TDOA → kirim JSON.

        Args:
            raw_bytes:        Byte string raw PCM (interleaved, semua channel)
            bpf:              Bytes per frame (bytes_per_sample × num_channels)
            sample_rate:      Sample rate dalam Hz
            chunk_idx:        Index urutan chunk dalam session (0, 1, 2, ...)
            chunk_offset_sec: Waktu awal chunk relatif terhadap awal sesi rekaman (detik)
        """
        cfg = get_global_config_manager().get_config()
        active_indices = self.recorder.get_active_take_indices()
        keep_audio = cfg.get("keep_audio_files", True)

        # Buat subfolder chunk dengan timestamp
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        chunk_name = f"chunk_{ts}"
        chunk_dir = os.path.join(self.chunks_dir, chunk_name)
        os.makedirs(chunk_dir, exist_ok=True)

        chunk_wav_path = os.path.join(chunk_dir, "raw.wav")

        try:
            # 1. Konversi raw bytes → numpy array → WAV
            data_np = self._raw_bytes_to_ndarray(raw_bytes, bpf, self.recorder.active_channels)
            if data_np is None or data_np.shape[0] == 0:
                print(f"[CHUNK] Konversi bytes gagal, skip chunk {chunk_name}")
                shutil.rmtree(chunk_dir, ignore_errors=True)
                return

            self._write_wav(chunk_wav_path, data_np, sample_rate)
            duration = data_np.shape[0] / sample_rate
            print(f"\n[CHUNK #{chunk_idx}] Processing {chunk_name} (offset: {chunk_offset_sec:.2f}s, dur: {duration:.2f}s)")

            # 1b. Per-chunk mic health detection (method-agnostic, isolasi sebelum DSP)
            health = assess_chunk_mic_health(data_np, active_indices)
            healthy_indices = health.healthy_indices
            healthy_names = health.healthy_names
            excluded_mics = health.excluded_mics

            if excluded_mics:
                print(
                    f"[MIC HEALTH] Chunk #{chunk_idx}: {len(healthy_names)}/{len(active_indices)} mic sehat "
                    f"| excluded={excluded_mics}"
                )

            if not healthy_indices:
                print(f"[MIC HEALTH] Tidak ada mic sehat pada chunk #{chunk_idx}, skip DSP.")
                if not keep_audio:
                    shutil.rmtree(chunk_dir, ignore_errors=True)
                return

            # 2. Extract & filter channels (HANYA mic sehat, pertahankan nama mic asli)
            original_files, data, sr, actual_duration = self.processor.extract_channels(
                chunk_wav_path,
                chunk_dir,
                sr_override=sample_rate,
                channel_indices=healthy_indices,
                mic_names=healthy_names,
            )
            if not original_files:
                print(f"[CHUNK] Ekstraksi channel gagal: {chunk_name}")
                if not keep_audio:
                    shutil.rmtree(chunk_dir, ignore_errors=True)
                return

            filtered_files, filtered_data = self.processor.filter_channels(
                data, sr, chunk_dir, channel_indices=healthy_indices, mic_names=healthy_names
            )

            # 3. Detect events (hanya dari file *_filtered.wav milik mic sehat)
            events = self.detector.detect_events(chunk_dir)

            # 4. Cut event clips
            processed_events = self.processor.save_event_clips(
                filtered_data, sr, events, chunk_dir,
                padding=cfg.get("event_padding_sec", EVENT_PADDING_SEC),
                channel_indices=healthy_indices,
                mic_names=healthy_names,
            )

            # 5. Calculate TDOA (hanya jika >= 3 mic sehat; jika 1-2 mic tetap lapor event-only)
            tdoa_results = []
            for event in processed_events:
                if len(healthy_indices) >= 3:
                    start_sample = max(0, int(event["padded_start"] * sr))
                    end_sample = min(filtered_data.shape[0], int(event["padded_end"] * sr))
                    event_audio = filtered_data[start_sample:end_sample, :]
                    event_tdoa = calculate_all_tdoa(
                        event_audio,
                        sr,
                        channel_indices=healthy_indices,
                        mic_names=healthy_names,
                    )
                    degraded_reason = None
                else:
                    event_tdoa = {}
                    degraded_reason = "INSUFFICIENT_MICS"

                orig_start = event.get("original_start", 0.0)
                orig_end = event.get("original_end", 0.0)
                abs_start = round(chunk_offset_sec + orig_start, 3)
                abs_end = round(chunk_offset_sec + orig_end, 3)

                ev_entry = {
                    "event_number": event["event_number"],
                    "session_id": self.current_session_id or "unknown_session",
                    "chunk_index": chunk_idx,
                    "chunk_offset_sec": chunk_offset_sec,
                    "chunk_timestamp": ts,
                    "event_start_in_chunk": orig_start,
                    "event_end_in_chunk": orig_end,
                    "event_abs_start_sec": abs_start,
                    "event_abs_end_sec": abs_end,
                    "active_mics": list(healthy_names),
                    "excluded_mics": dict(excluded_mics),
                    "tdoa": event_tdoa,
                }
                if degraded_reason:
                    ev_entry["degraded_reason"] = degraded_reason
                tdoa_results.append(ev_entry)

            # 6. Simpan TDOA JSON
            rec_status = self.recorder.get_status()
            profile_name = rec_status.get("profile", "Unknown")
            num_mics = len(healthy_names)
            num_tdoa_pairs = num_mics * (num_mics - 1) // 2 if num_mics >= 3 else 0

            extra_info = {
                "type": "TDOA_RESULTS",
                "chunk_name": chunk_name,
                "chunk_duration_sec": duration,
                "device_profile": profile_name,
                "format": rec_status.get("format", "Unknown"),
                "channels": rec_status.get("channels", 0),
                "num_mics": num_mics,
                "num_tdoa_pairs": num_tdoa_pairs,
                "active_mics": list(healthy_names),
                "excluded_mics": dict(excluded_mics),
            }

            tdoa_json_path = os.path.join(chunk_dir, "tdoa.json")
            log_ts = datetime.now().strftime(LOG_TIMESTAMP_FORMAT)
            DataLogger.save_events_json(
                tdoa_json_path,
                chunk_name,
                log_ts,
                tdoa_results,
                duration,
                sr,
                extra_info=extra_info
            )

            print(f"[CHUNK] {len(events)} event(s), TDOA saved to {tdoa_json_path}")

            # 7. Kirim ke ground
            op_mode = cfg.get("operation_mode", "OFFLINE")
            if op_mode == "ONLINE":
                if self.comms and self.comms.send_file(tdoa_json_path):
                    print(f"[CHUNK] TDOA sent successfully.")
                else:
                    print(f"[CHUNK] Failed to send TDOA (comms unavailable or send error).")
            elif op_mode == "SDR":
                print(f"[CHUNK] SDR mode — TDOA saved to {tdoa_json_path} for SDR broadcast")
            else:
                print(f"[CHUNK] OFFLINE mode — skip serial transmission")

            # 8. Hapus file audio jika dikonfigurasi
            if not keep_audio:
                self._cleanup_audio_files(chunk_dir, tdoa_json_path)

        except Exception as e:
            import traceback
            print(f"[ERROR] Chunk processing failed: {e}")
            traceback.print_exc()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _raw_bytes_to_ndarray(raw_bytes: bytes, bpf: int, n_channels: int) -> np.ndarray | None:
        """
        Konversi raw PCM bytes (interleaved, semua channel) ke numpy float32 array.

        Mendukung format:
          - S24_3LE (3 bytes per sample) → sign-extend ke int32 → float32
          - S16_LE  (2 bytes per sample) → int16 → float32
          - S32_LE / FLOAT_LE (4 bytes per sample)
        """
        try:
            bps = bpf // n_channels  # bytes per sample per channel

            if bps == 3:
                # S24_3LE: pad ke 4 bytes (little-endian sign extension)
                n_frames = len(raw_bytes) // bpf
                usable = n_frames * bpf
                arr = np.frombuffer(raw_bytes[:usable], dtype=np.uint8)
                arr = arr[: n_frames * n_channels * 3].reshape(n_frames * n_channels, 3)
                # Sign-extend: [[b0, b1, b2]] → int32 little-endian
                padded = np.zeros((n_frames * n_channels, 4), dtype=np.uint8)
                padded[:, :3] = arr
                # Salin sign byte (MSB dari S24)
                padded[:, 3] = np.where(arr[:, 2] >= 0x80, 0xFF, 0x00).astype(np.uint8)
                samples_i32 = padded.view(np.int32).reshape(-1)
                data = samples_i32.reshape(n_frames, n_channels).astype(np.float32) / (2**23)
            elif bps == 2:
                n_frames = len(raw_bytes) // bpf
                usable = n_frames * bpf
                data = np.frombuffer(raw_bytes[:usable], dtype=np.int16).reshape(n_frames, n_channels).astype(np.float32) / 32768.0
            elif bps == 4:
                n_frames = len(raw_bytes) // bpf
                usable = n_frames * bpf
                raw = np.frombuffer(raw_bytes[:usable], dtype=np.int32).reshape(n_frames, n_channels)
                data = raw.astype(np.float32) / 2**31
            else:
                print(f"[WARN] Format tidak dikenal (bps={bps}), skip")
                return None

            return data
        except Exception as e:
            print(f"[ERROR] _raw_bytes_to_ndarray: {e}")
            return None

    @staticmethod
    def _write_wav(path: str, data: np.ndarray, sr: int):
        """Simpan numpy float32 array ke file WAV."""
        sf.write(path, data, sr, subtype="FLOAT")

    @staticmethod
    def _cleanup_audio_files(chunk_dir: str, keep_file: str):
        """
        Hapus semua file di chunk_dir kecuali keep_file (TDOA JSON).

        Args:
            chunk_dir:  Path folder chunk
            keep_file:  Absolute path file yang tidak akan dihapus
        """
        try:
            for root, dirs, files in os.walk(chunk_dir, topdown=False):
                for fname in files:
                    fpath = os.path.join(root, fname)
                    if os.path.abspath(fpath) != os.path.abspath(keep_file):
                        os.remove(fpath)
                for d in dirs:
                    dpath = os.path.join(root, d)
                    try:
                        os.rmdir(dpath)
                    except OSError:
                        pass  # direktori tidak kosong (event clips masih ada)
            print(f"[CLEANUP] Audio files removed from {os.path.basename(chunk_dir)}")
        except Exception as e:
            print(f"[CLEANUP] Error: {e}")

    def _reset_state(self):
        """Reset internal state setelah session selesai."""
        self.current_session_id = None
        self.current_session_dir = None
        self.chunks_dir = None
        self.recording_start_time = None
        self._stream_thread = None
        self._stop_event.clear()
