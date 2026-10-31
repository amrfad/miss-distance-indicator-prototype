"""
calibration_page.py — Halaman UI Kalibrasi Posisi Mikrofon secara Live.

Memungkinkan ground station merekam data TDOA langsung dari drone pada setiap titik
sumber suara yang posisinya terukur secara manual, mengumpulkan multi-titik sesi,
menghapus sesi yang dianggap invalid, dan mengestimasi koordinat 3D 6 mikrofon
menggunakan nonlinear least-squares solver.
"""

import os
import json
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
from PySide6.QtCore import Qt, QTimer, QThread, Signal, Slot
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QDoubleSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.config import CMD_START_RECORD, CMD_STOP_RECORD
from ...core.session_merger import merge_session_jsons
from ...localization.calibration_engine import (
    CalibrationResult,
    CalibrationSession,
    parse_tdoa_json,
    run_calibration,
)
from ..widgets.session_list_widget import SessionListWidget


class _CalibrationWorker(QThread):
    """Worker thread untuk kalkulasi least-squares agar GUI tidak freeze."""
    result_ready = Signal(object)
    error_occurred = Signal(str)

    def __init__(
        self,
        sessions: List[CalibrationSession],
        initial_pos: Optional[Dict[str, Any]] = None,
        speed_of_sound: float = 343.0,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._sessions = sessions
        self._initial_pos = initial_pos
        self._speed_of_sound = speed_of_sound

    def run(self):
        try:
            result = run_calibration(
                sessions=self._sessions,
                initial_mic_positions=self._initial_pos,
                speed_of_sound=self._speed_of_sound,
            )
            self.result_ready.emit(result)
        except Exception as exc:
            self.error_occurred.emit(str(exc))


class CalibrationPage(QWidget):
    """Halaman antarmuka kalibrasi posisi 3D mikrofon."""

    log_message = Signal(str, str)
    mic_positions_updated = Signal(dict)
    _json_saved_signal = Signal(str)

    def __init__(
        self,
        serial_bridge=None,
        json_receiver=None,
        config_manager=None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._serial = serial_bridge
        self._jr = json_receiver
        self._config_manager = config_manager

        # State
        self._is_recording: bool = False
        self._is_stopping: bool = False
        self._rx_thread: Optional[threading.Thread] = None
        self._session_chunk_files: List[str] = []
        self._current_source_pos: np.ndarray = np.array([0.0, 0.0, 0.0])
        self._recording_duration_sec: int = 0
        self._waiting_elapsed_sec: float = 0.0

        self._last_result: Optional[CalibrationResult] = None
        self._worker: Optional[_CalibrationWorker] = None

        # Timers
        self._recording_timer = QTimer(self)
        self._recording_timer.setInterval(1000)
        self._recording_timer.timeout.connect(self._on_recording_tick)

        self._waiting_timer = QTimer(self)
        self._waiting_timer.setInterval(200)
        self._waiting_timer.timeout.connect(self._on_waiting_tick)

        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setSingleShot(True)
        self._watchdog_timer.timeout.connect(self._on_watchdog_timeout)

        # Wire signal internal untuk thread safety
        self._json_saved_signal.connect(self._on_json_saved_gui)

        self._build_ui()
        self._wire_serial()
        self._update_ui_state()

    def _wire_serial(self):
        if self._serial:
            self._serial.connection_changed.connect(self._on_connection_changed)
            self._serial.message_received.connect(self._on_serial_message)
            if hasattr(self._serial, "json_saved"):
                self._serial.json_saved.connect(self._json_saved_signal.emit)

    def _build_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(12)

        # ── Scroll Area agar muat di semua resolusi ──
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(14)

        # ── Header Bar ──
        header_card = QFrame()
        header_card.setObjectName("card")
        h_layout = QHBoxLayout(header_card)
        h_layout.setContentsMargins(16, 12, 16, 12)

        title_vbox = QVBoxLayout()
        title_lbl = QLabel("🔧 KALIBRASI POSISI MIKROFON (LIVE)")
        title_lbl.setObjectName("sectionTitle")
        sub_lbl = QLabel("Estimasi koordinat 3D mikrofon drone dari observasi TDOA sumber bersuara terukur")
        sub_lbl.setObjectName("statusHeading")
        title_vbox.addWidget(title_lbl)
        title_vbox.addWidget(sub_lbl)
        h_layout.addLayout(title_vbox, stretch=1)

        self._conn_badge = QLabel("○ DISCONNECTED")
        self._conn_badge.setObjectName("statusHeading")
        self._conn_badge.setStyleSheet("color: #dc2626; font-weight: bold; font-size: 13px;")
        h_layout.addWidget(self._conn_badge)

        layout.addWidget(header_card)

        # ── Card 1: Input Titik Sumber & Rekam ──
        card1 = QFrame()
        card1.setObjectName("card")
        c1_layout = QVBoxLayout(card1)
        c1_layout.setContentsMargins(16, 14, 16, 14)
        c1_layout.setSpacing(10)

        c1_title = QLabel("LANGKAH 1: INPUT KOORDINAT SUMBER SUARA & REKAM")
        c1_title.setObjectName("sectionTitle")
        c1_layout.addWidget(c1_title)

        desc_lbl = QLabel(
            "Posisikan sumber suara uji (speaker / tepukan / buzzer) pada koordinat terukur (relatif terhadap pusat array drone).\n"
            "Masukkan nilai X, Y, Z (dalam meter) lalu klik 'MULAI REKAM'."
        )
        desc_lbl.setStyleSheet("color: #475569; font-size: 11px;")
        c1_layout.addWidget(desc_lbl)

        # Input koordinat X, Y, Z
        coord_layout = QHBoxLayout()
        coord_layout.setSpacing(16)

        # X
        x_box = QHBoxLayout()
        x_lbl = QLabel("X (meter):")
        x_lbl.setStyleSheet("font-weight: bold;")
        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-999.0, 999.0)
        self.spin_x.setDecimals(3)
        self.spin_x.setSingleStep(0.05)
        self.spin_x.setValue(0.0)
        self.spin_x.setMinimumWidth(110)
        self.spin_x.setMinimumHeight(32)
        x_box.addWidget(x_lbl)
        x_box.addWidget(self.spin_x)
        coord_layout.addLayout(x_box)

        # Y
        y_box = QHBoxLayout()
        y_lbl = QLabel("Y (meter):")
        y_lbl.setStyleSheet("font-weight: bold;")
        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-999.0, 999.0)
        self.spin_y.setDecimals(3)
        self.spin_y.setSingleStep(0.05)
        self.spin_y.setValue(0.0)
        self.spin_y.setMinimumWidth(110)
        self.spin_y.setMinimumHeight(32)
        y_box.addWidget(y_lbl)
        y_box.addWidget(self.spin_y)
        coord_layout.addLayout(y_box)

        # Z
        z_box = QHBoxLayout()
        z_lbl = QLabel("Z (meter):")
        z_lbl.setStyleSheet("font-weight: bold;")
        self.spin_z = QDoubleSpinBox()
        self.spin_z.setRange(-999.0, 999.0)
        self.spin_z.setDecimals(3)
        self.spin_z.setSingleStep(0.05)
        self.spin_z.setValue(0.0)
        self.spin_z.setMinimumWidth(110)
        self.spin_z.setMinimumHeight(32)
        z_box.addWidget(z_lbl)
        z_box.addWidget(self.spin_z)
        coord_layout.addLayout(z_box)

        coord_layout.addStretch()
        c1_layout.addLayout(coord_layout)

        # Tombol Mulai & Selesai Rekam
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self.btn_start = QPushButton("● MULAI REKAM")
        self.btn_start.setObjectName("btnStart")
        self.btn_start.setMinimumHeight(42)
        self.btn_start.clicked.connect(self._on_start_record)
        btn_row.addWidget(self.btn_start, stretch=1)

        self.btn_stop = QPushButton("■ SELESAI REKAM")
        self.btn_stop.setObjectName("btnStop")
        self.btn_stop.setMinimumHeight(42)
        self.btn_stop.clicked.connect(self._on_stop_record)
        btn_row.addWidget(self.btn_stop, stretch=1)

        c1_layout.addLayout(btn_row)

        # Status Banner (Recording / Waiting indicator)
        self.status_banner = QLabel("Status: Siap merekam titik sumber.")
        self.status_banner.setObjectName("statusHeading")
        self.status_banner.setStyleSheet(
            "background-color: #f1f5f9; padding: 8px 12px; border-radius: 4px; "
            "color: #334155; font-size: 12px; font-weight: 600;"
        )
        c1_layout.addWidget(self.status_banner)

        layout.addWidget(card1)

        # ── Card 2: Daftar Sesi Terkumpul ──
        card2 = QFrame()
        card2.setObjectName("card")
        c2_layout = QVBoxLayout(card2)
        c2_layout.setContentsMargins(16, 14, 16, 14)
        c2_layout.setSpacing(10)

        self.session_list = SessionListWidget()
        self.session_list.sessions_changed.connect(self._update_ui_state)
        c2_layout.addWidget(self.session_list)

        # Tombol Hitung Kalibrasi
        self.btn_calculate = QPushButton("⚡ HITUNG ESTIMASI POSISI MIKROFON (OPTIMASI)")
        self.btn_calculate.setObjectName("btnPrimary")
        self.btn_calculate.setMinimumHeight(44)
        self.btn_calculate.clicked.connect(self._on_run_calibration)
        c2_layout.addWidget(self.btn_calculate)

        layout.addWidget(card2)

        # ── Card 3: Panel Hasil Kalibrasi (Default Hidden) ──
        self.card_result = QFrame()
        self.card_result.setObjectName("card")
        c3_layout = QVBoxLayout(self.card_result)
        c3_layout.setContentsMargins(16, 14, 16, 14)
        c3_layout.setSpacing(10)

        # Header hasil
        res_header = QHBoxLayout()
        res_title = QLabel("HASIL KALIBRASI TERAKHIR")
        res_title.setObjectName("sectionTitle")
        res_header.addWidget(res_title)

        res_header.addStretch()

        self.lbl_rms = QLabel("RMS Residual: -")
        self.lbl_rms.setStyleSheet("color: #2563eb; font-weight: bold; font-size: 13px;")
        res_header.addWidget(self.lbl_rms)

        self.lbl_converged = QLabel("Status: -")
        self.lbl_converged.setStyleSheet("font-weight: bold; font-size: 13px;")
        res_header.addWidget(self.lbl_converged)

        c3_layout.addLayout(res_header)

        # Tabel perbandingan posisi mikrofon
        self.table_result = QTableWidget(6, 5)
        self.table_result.setHorizontalHeaderLabels([
            "Mic", "X Estimasi (m)", "Y Estimasi (m)", "Z Estimasi (m)", "Δ vs Config Saat Ini"
        ])
        self.table_result.verticalHeader().setVisible(False)
        self.table_result.setAlternatingRowColors(True)
        self.table_result.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_result.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        t_header = self.table_result.horizontalHeader()
        t_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        t_header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        t_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        t_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        t_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        self.table_result.setFixedHeight(210)
        c3_layout.addWidget(self.table_result)

        self.lbl_result_info = QLabel("")
        self.lbl_result_info.setStyleSheet("color: #64748b; font-size: 11px;")
        c3_layout.addWidget(self.lbl_result_info)

        # Tombol Aksi Hasil: Buang atau Terapkan
        action_row = QHBoxLayout()
        action_row.setSpacing(12)

        self.btn_discard = QPushButton("✕ Buang Hasil")
        self.btn_discard.setObjectName("btnReset")
        self.btn_discard.setMinimumHeight(40)
        self.btn_discard.clicked.connect(self._on_discard_result)
        action_row.addWidget(self.btn_discard)

        self.btn_apply = QPushButton("✔ TERAPKAN KE KONFIGURASI GROUND STATION")
        self.btn_apply.setObjectName("btnSave")
        self.btn_apply.setMinimumHeight(40)
        self.btn_apply.clicked.connect(self._on_apply_to_config)
        action_row.addWidget(self.btn_apply, stretch=1)

        c3_layout.addLayout(action_row)

        self.card_result.setVisible(False)
        layout.addWidget(self.card_result)

        scroll.setWidget(container)
        main_layout.addWidget(scroll)

    # ── State Updates ─────────────────────────────────────────────

    def _is_connected(self) -> bool:
        if self._serial:
            return bool(self._serial.is_connected())
        return False

    def _on_connection_changed(self, connected: bool, port: str):
        if connected:
            self._conn_badge.setText(f"● CONNECTED ({port})")
            self._conn_badge.setStyleSheet("color: #16a34a; font-weight: bold; font-size: 13px;")
        else:
            self._conn_badge.setText("○ DISCONNECTED")
            self._conn_badge.setStyleSheet("color: #dc2626; font-weight: bold; font-size: 13px;")
        self._update_ui_state()

    def _on_serial_message(self, msg: str):
        """Mendeteksi pesan serial dari drone untuk konfirmasi stop atau data."""
        if not self._is_stopping:
            return

        msg_upper = msg.upper()
        stop_keywords = ["STOPPED", "STOP_ACK", "OK:STOP", "RECORDING STOPPED"]
        if any(sk in msg_upper for sk in stop_keywords) or (msg_upper.startswith("OK:") and "STOP" in msg_upper):
            self._log(f"Konfirmasi stop dari drone diterima: {msg.strip()}", "INFO")
            if self._watchdog_timer.isActive():
                self._watchdog_timer.stop()
            # Beri jeda 500ms agar buffer serial selesai dikuras
            QTimer.singleShot(500, self._finalize_stop_record)

    def _update_ui_state(self):
        connected = bool(self._is_connected())
        valid_sessions = int(self.session_list.valid_session_count())

        if self._is_recording:
            # Mode SEDANG MEREKAM
            self.spin_x.setEnabled(False)
            self.spin_y.setEnabled(False)
            self.spin_z.setEnabled(False)
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(True)
            self.btn_calculate.setEnabled(False)
            self.status_banner.setStyleSheet(
                "background-color: #fee2e2; border: 1px solid #ef4444; padding: 8px 12px; "
                "border-radius: 4px; color: #b91c1c; font-size: 12px; font-weight: bold;"
            )
            mins = self._recording_duration_sec // 60
            secs = self._recording_duration_sec % 60
            self.status_banner.setText(
                f"● SEDANG MEREKAM... Durasi: {mins:02d}:{secs:02d} | "
                f"Sumber: ({self._current_source_pos[0]:+.3f}, {self._current_source_pos[1]:+.3f}, {self._current_source_pos[2]:+.3f}) m"
            )

        elif self._is_stopping:
            # Mode MENUNGGU DATA DARI DRONE
            self.spin_x.setEnabled(False)
            self.spin_y.setEnabled(False)
            self.spin_z.setEnabled(False)
            self.btn_start.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.btn_calculate.setEnabled(False)
            self.status_banner.setStyleSheet(
                "background-color: #e0f2fe; border: 1px solid #38bdf8; padding: 8px 12px; "
                "border-radius: 4px; color: #0369a1; font-size: 12px; font-weight: bold;"
            )
            self.status_banner.setText(
                f"⟳ MENUNGGU DATA DARI DRONE... ({self._waiting_elapsed_sec:.1f} detik) "
                f"Drone sedang memproses dan mengirimkan JSON TDOA."
            )

        else:
            # Mode IDLE / READY TO RECORD
            self.spin_x.setEnabled(True)
            self.spin_y.setEnabled(True)
            self.spin_z.setEnabled(True)
            self.btn_start.setEnabled(bool(connected))
            self.btn_stop.setEnabled(False)
            self.btn_calculate.setEnabled(bool(valid_sessions >= 1))

            if not connected:
                self.status_banner.setStyleSheet(
                    "background-color: #f1f5f9; padding: 8px 12px; border-radius: 4px; "
                    "color: #dc2626; font-size: 12px; font-weight: 600;"
                )
                self.status_banner.setText("⚠ Drone belum terhubung via serial port. Hubungkan perangkat terlebih dahulu.")
            else:
                self.status_banner.setStyleSheet(
                    "background-color: #f0fdf4; border: 1px solid #86efac; padding: 8px 12px; "
                    "border-radius: 4px; color: #15803d; font-size: 12px; font-weight: 600;"
                )
                self.status_banner.setText(
                    f"✓ Siap merekam. Masukkan koordinat sumber lalu klik 'MULAI REKAM'. "
                    f"({valid_sessions} sesi valid terkumpul)"
                )

    # ── Flow Rekam ────────────────────────────────────────────────

    def _on_start_record(self):
        if not self._is_connected():
            QMessageBox.warning(self, "Perangkat Belum Terhubung", "Serial belum terhubung ke drone.")
            return

        if self._is_recording or self._is_stopping:
            return

        x = float(self.spin_x.value())
        y = float(self.spin_y.value())
        z = float(self.spin_z.value())
        self._current_source_pos = np.array([x, y, z], dtype=float)

        self._log(
            f"Memulai rekam kalibrasi untuk sumber di ({x:+.3f}, {y:+.3f}, {z:+.3f}) m",
            "INFO"
        )

        # Kirim START_REC via serial bridge
        if self._serial:
            self._serial.send_command(CMD_START_RECORD)

        # Siapkan receiver
        self._session_chunk_files.clear()
        if hasattr(self._serial, "json_saved"):
            self._log("SDR JSON receiver ready for calibration", "DEBUG")
        elif self._jr:
            self._jr.reset()
            self._rx_thread = threading.Thread(
                target=self._jr.receive_json,
                kwargs={"on_saved": self._json_saved_signal.emit, "continuous": True},
                daemon=True,
                name="CalibrationJsonReceiver",
            )
            self._rx_thread.start()

        self._is_recording = True
        self._is_stopping = False
        self._recording_duration_sec = 0
        self._recording_timer.start()
        self._update_ui_state()

    def _on_recording_tick(self):
        self._recording_duration_sec += 1
        mins = self._recording_duration_sec // 60
        secs = self._recording_duration_sec % 60
        self.status_banner.setText(
            f"● SEDANG MEREKAM... Durasi: {mins:02d}:{secs:02d} | "
            f"Sumber: ({self._current_source_pos[0]:+.3f}, {self._current_source_pos[1]:+.3f}, {self._current_source_pos[2]:+.3f}) m"
        )

    def _on_stop_record(self):
        if not self._is_recording or self._is_stopping:
            return

        self._recording_timer.stop()
        self._is_recording = False
        self._is_stopping = True
        self._waiting_elapsed_sec = 0.0

        self._log("Mengirim perintah STOP_REC ke drone...", "INFO")
        if self._serial:
            self._serial.send_command(CMD_STOP_RECORD)

        self._waiting_timer.start()
        self._watchdog_timer.start(60000)  # 60 detik timeout
        self._update_ui_state()

    def _on_waiting_tick(self):
        self._waiting_elapsed_sec += 0.2
        self.status_banner.setText(
            f"⟳ MENUNGGU DATA DARI DRONE... ({self._waiting_elapsed_sec:.1f} detik) "
            f"Drone sedang memproses dan mengirimkan JSON TDOA."
        )

    def _on_watchdog_timeout(self):
        if self._is_stopping:
            self._log("Watchdog timeout (60 detik) saat menunggu data drone. Menghentikan penerimaan.", "WARNING")
            self._finalize_stop_record()

    def _finalize_stop_record(self):
        if self._watchdog_timer.isActive():
            self._watchdog_timer.stop()
        if self._waiting_timer.isActive():
            self._waiting_timer.stop()

        if self._jr:
            self._jr.stop_continuous()

        self._is_recording = False
        self._is_stopping = False

        self._log("Penerimaan selesai. Memproses berkas rekaman...", "INFO")

        # Proses file yang terkumpul
        if not self._session_chunk_files:
            self._log("Tidak ada data JSON TDOA yang diterima untuk sesi ini.", "WARNING")
            self._update_ui_state()
            return

        final_json_path = None
        if len(self._session_chunk_files) == 1:
            final_json_path = self._session_chunk_files[0]
        else:
            save_dir = getattr(self._jr, "save_directory", os.getcwd())
            try:
                final_json_path = merge_session_jsons(self._session_chunk_files, save_dir)
            except Exception as e:
                self._log(f"Gagal menggabungkan chunk JSON: {e}", "ERROR")

        if not final_json_path or not os.path.isfile(final_json_path):
            self._log("Gagal menemukan file JSON hasil rekaman yang valid.", "ERROR")
            self._update_ui_state()
            return

        # Parsing ke CalibrationSession
        try:
            session = parse_tdoa_json(final_json_path, self._current_source_pos)
            self.session_list.add_session(session)
            status_str = f"{session.n_events} events" if session.is_valid else "0 event (diabaikan saat optimasi)"
            self._log(
                f"✓ Sesi #{self.session_list.session_count()} berhasil ditambahkan "
                f"dari {os.path.basename(final_json_path)} ({status_str})",
                "SUCCESS" if session.is_valid else "WARNING",
            )
        except Exception as exc:
            self._log(f"Gagal mem-parsing data sesi: {exc}", "ERROR")

        self._update_ui_state()

    @Slot(str)
    def _on_json_saved_gui(self, file_path: str):
        """Dipanggil dari signal saat file JSON chunk tersimpan."""
        if file_path not in self._session_chunk_files:
            self._session_chunk_files.append(file_path)
            self._log(f"Menerima chunk TDOA: {os.path.basename(file_path)}", "INFO")

    # ── Flow Optimasi & Kalibrasi ──────────────────────────────────

    def _on_run_calibration(self):
        valid_sessions = self.session_list.get_valid_sessions()
        if not valid_sessions:
            QMessageBox.warning(
                self,
                "Data Belum Cukup",
                "Tidak ada sesi rekaman yang valid (memiliki event suara) untuk dihitung."
            )
            return

        # Dapatkan initial mic positions dan speed_of_sound dari config_manager
        initial_pos = None
        speed_of_sound = 343.0
        if self._config_manager:
            cfg = self._config_manager.get_config()
            initial_pos = cfg.get("mic_positions")
            speed_of_sound = float(cfg.get("speed_of_sound", 343.0))

        self.btn_calculate.setEnabled(False)
        self.btn_calculate.setText("⏳ MENGHITUNG OPTIMASI...")
        self._log(
            f"Memulai kalibrasi least-squares dengan {len(valid_sessions)} sesi valid...",
            "INFO"
        )

        self._worker = _CalibrationWorker(
            sessions=valid_sessions,
            initial_pos=initial_pos,
            speed_of_sound=speed_of_sound,
            parent=self,
        )
        self._worker.result_ready.connect(self._on_calibration_success)
        self._worker.error_occurred.connect(self._on_calibration_error)
        self._worker.start()

    @Slot(object)
    def _on_calibration_success(self, result: CalibrationResult):
        self.btn_calculate.setEnabled(True)
        self.btn_calculate.setText("⚡ HITUNG ESTIMASI POSISI MIKROFON (OPTIMASI)")
        self._last_result = result

        self._log(
            f"Kalibrasi selesai! Konvergensi: {result.converged}, RMS: {result.rms_residual_ms:.4f} ms",
            "SUCCESS" if result.converged else "WARNING"
        )

        self._display_results(result)

    @Slot(str)
    def _on_calibration_error(self, err_msg: str):
        self.btn_calculate.setEnabled(True)
        self.btn_calculate.setText("⚡ HITUNG ESTIMASI POSISI MIKROFON (OPTIMASI)")
        self._log(f"Kalibrasi gagal: {err_msg}", "ERROR")
        QMessageBox.critical(self, "Kesalahan Kalibrasi", f"Proses optimasi gagal:\n{err_msg}")

    def _display_results(self, res: CalibrationResult):
        """Menampilkan data hasil estimasi di tabel perbandingan."""
        self.lbl_rms.setText(f"RMS Residual: {res.rms_residual_ms:.4f} ms")
        if res.converged:
            self.lbl_converged.setText("Status: Konvergen ✓")
            self.lbl_converged.setStyleSheet("color: #16a34a; font-weight: bold; font-size: 13px;")
        else:
            self.lbl_converged.setText("Status: Belum Konvergen ⚠")
            self.lbl_converged.setStyleSheet("color: #d97706; font-weight: bold; font-size: 13px;")

        self.lbl_result_info.setText(
            f"Dihitung dari {res.n_sessions_used} sesi valid ({res.n_events_used} event suara). "
            f"Pesan solver: {res.message}"
        )

        # Ambil posisi mic saat ini dari config
        curr_mics = {}
        if self._config_manager:
            curr_mics = self._config_manager.get_mic_positions_numpy()

        self.table_result.setRowCount(6)
        for idx in range(6):
            mic_key = f"mic{idx}"
            est = res.mic_positions_dict.get(mic_key, {"x": 0.0, "y": 0.0, "z": 0.0})

            # Kolom 0: Mic
            it_mic = QTableWidgetItem(mic_key.upper())
            it_mic.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_result.setItem(idx, 0, it_mic)

            # Kolom 1..3: X, Y, Z
            it_x = QTableWidgetItem(f"{est['x']:+.4f}")
            it_x.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_result.setItem(idx, 1, it_x)

            it_y = QTableWidgetItem(f"{est['y']:+.4f}")
            it_y.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_result.setItem(idx, 2, it_y)

            it_z = QTableWidgetItem(f"{est['z']:+.4f}")
            it_z.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_result.setItem(idx, 3, it_z)

            # Kolom 4: Delta vs Config
            delta_str = "-"
            delta_item = QTableWidgetItem(delta_str)
            if mic_key in curr_mics:
                cur_pos = curr_mics[mic_key]
                if isinstance(cur_pos, np.ndarray) and cur_pos.shape == (3,):
                    est_arr = np.array([est["x"], est["y"], est["z"]])
                    dist = float(np.linalg.norm(est_arr - cur_pos))
                    delta_str = f"±{dist:.3f} m"
                    delta_item.setText(delta_str)

                    if dist < 0.05:
                        delta_item.setForeground(Qt.GlobalColor.darkGreen)
                    elif dist < 0.20:
                        delta_item.setForeground(Qt.GlobalColor.blue)
                    else:
                        delta_item.setForeground(Qt.GlobalColor.darkYellow)

            delta_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.table_result.setItem(idx, 4, delta_item)

        self.card_result.setVisible(True)

    def _on_discard_result(self):
        """Membuang hasil estimasi saat ini."""
        self._last_result = None
        self.card_result.setVisible(False)
        self._log("Hasil kalibrasi dibuang.", "INFO")

    def _on_apply_to_config(self):
        """Menerapkan posisi mikrofon hasil kalibrasi ke konfigurasi ground station."""
        if not self._last_result:
            return

        reply = QMessageBox.question(
            self,
            "Konfirmasi Penerapan Konfigurasi",
            "Apakah Anda yakin ingin menerapkan posisi mikrofon baru ini ke ground_config_override.json?\n"
            "Konfigurasi ini akan langsung aktif untuk proses lokalisasi TDOA berikutnya.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )

        if reply == QMessageBox.StandardButton.Yes:
            new_positions = self._last_result.mic_positions_dict
            if self._config_manager:
                try:
                    self._config_manager.update({"mic_positions": new_positions})
                    self._log("✓ Posisi mikrofon baru berhasil disimpan ke konfigurasi Ground Station!", "SUCCESS")
                except Exception as exc:
                    self._log(f"Gagal memperbarui konfigurasi: {exc}", "ERROR")
                    QMessageBox.critical(self, "Gagal Simpan", f"Error saat menyimpan konfigurasi:\n{exc}")
                    return

            self.mic_positions_updated.emit(new_positions)

            # Perbarui delta di tabel (karena config sudah update, delta sekarang harus ~0)
            self._display_results(self._last_result)
            QMessageBox.information(
                self,
                "Berhasil Diterapkan",
                "Posisi mikrofon berhasil diperbarui ke konfigurasi sistem."
            )

    # ── Logging Helper ─────────────────────────────────────────────

    def _log(self, msg: str, level: str = "INFO"):
        self.log_message.emit(msg, level)
