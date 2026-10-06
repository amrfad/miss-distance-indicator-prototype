# demo_ground/ui/pages/live_page.py
"""
Live & Radar 2D Page — Operasional drone dan visualisasi radar taktis 2D.
Arsitektur komunikasi SIYI (SerialBridge, FileTransfer, JsonReceiver, State Machine)
identik 1:1 dengan darat/ (command_page.py).
"""

import os
import json
import math
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QLabel, QPushButton, QComboBox, QFileDialog,
    QSplitter, QMessageBox, QTextEdit, QListWidget, QListWidgetItem,
    QScrollArea,
)
from PySide6.QtCore import Signal, Slot, Qt, QTimer
from PySide6.QtGui import QFont

from ..widgets.radar_2d_widget import Radar2DWidget
from ...ssl_2d import chan_ho_2d, rotating_multilat_2d
from ...core.config import (
    CMD_START_RECORD, CMD_STOP_RECORD, CMD_STATUS, CMD_STANDBY, CMD_RESTART
)
from ...core.session_merger import merge_session_jsons


class LivePage(QWidget):
    """
    Layar utama demonstrasi:
    - State machine kontrol serial SIYI identik 100% dengan darat/command_page.py
    - Streaming JSON receiver dengan thread continuous dan deduplikasi overlap
    - Penggabungan multi-chunk session otomatis saat STOP_REC
    - Pemrosesan lokalisasi 2D real-time (Rotating Multilateration 2D / Chan-Ho 2D)
    - Tampilan Radar Taktis 2D murni (tanpa siluet pesawat dan tanpa titik mic)
    """

    json_saved = Signal(str)           # (file_path_absolut)
    log_message = Signal(str, str)     # (pesan, level)
    status_changed = Signal(str, bool) # (status_text, is_connected)

    def __init__(
        self,
        serial_bridge,
        file_transfer,
        json_receiver,
        config_manager,
        drone_save_dir: str,
        log_callback=None,
        parent=None,
    ):
        super().__init__(parent)
        self._serial = serial_bridge
        self._ft = file_transfer
        self._jr = json_receiver
        self._config_manager = config_manager
        self._drone_save_dir = drone_save_dir
        self._custom_log = log_callback

        # State machine komunikasi identik darat/
        self._is_recording = False
        self._is_stopping = False
        self._is_connecting = False
        self._rx_thread: Optional[threading.Thread] = None

        # Session tracking
        self._last_json_file: Optional[str] = None
        self._received_json_files: List[str] = []
        self._session_chunk_files: List[str] = []
        self._events: List[Dict[str, Any]] = []

        # Timers
        self._stop_watchdog_timer = QTimer(self)
        self._stop_watchdog_timer.setSingleShot(True)
        self._stop_watchdog_timer.timeout.connect(self._on_stop_watchdog_timeout)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(500)
        self._poll_timer.timeout.connect(self._update_ui_state)

        self._build_ui()
        self._wire_signals()
        self._update_ui_state()
        self._poll_timer.start()

    def _log(self, message: str, level: str = "INFO"):
        self.log_message.emit(message, level)
        if self._custom_log:
            try:
                self._custom_log(message, level)
            except TypeError:
                self._custom_log(message)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        # ── 1. Top Telemetry & Status Bar ──
        status_bar = QFrame()
        status_bar.setObjectName("card")
        sb_layout = QHBoxLayout(status_bar)
        sb_layout.setContentsMargins(16, 10, 16, 10)
        sb_layout.setSpacing(18)

        # Status pills
        self.conn_indicator = QLabel("● DISCONNECTED")
        self.conn_indicator.setObjectName("statusError")
        sb_layout.addWidget(self.conn_indicator)

        self.rec_indicator = QLabel("○ IDLE")
        self.rec_indicator.setObjectName("statusHeading")
        sb_layout.addWidget(self.rec_indicator)

        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setFixedWidth(1)
        sb_layout.addWidget(sep1)

        # Telemetry metrics
        sb_layout.addWidget(QLabel("METHOD:"))
        self.lbl_method_val = QLabel("Auto (Adaptive)")
        self.lbl_method_val.setObjectName("statusValue")
        sb_layout.addWidget(self.lbl_method_val)

        sb_layout.addWidget(QLabel("EVENTS:"))
        self.lbl_ev_count = QLabel("0")
        self.lbl_ev_count.setObjectName("statusValue")
        sb_layout.addWidget(self.lbl_ev_count)

        sb_layout.addWidget(QLabel("LAST CPA [X, Y]:"))
        self.lbl_last_coord = QLabel("---")
        self.lbl_last_coord.setObjectName("statusValue")
        sb_layout.addWidget(self.lbl_last_coord)

        sb_layout.addWidget(QLabel("ALTITUDE (Z):"))
        self.lbl_alt_val = QLabel("N/A (Planar)")
        self.lbl_alt_val.setObjectName("statusValue")
        sb_layout.addWidget(self.lbl_alt_val)

        sb_layout.addWidget(QLabel("MISS DISTANCE:"))
        self.lbl_miss_val = QLabel("--- m")
        self.lbl_miss_val.setObjectName("statusValue")
        self.lbl_miss_val.setStyleSheet("font-size: 15px; font-weight: 700; color: #3b82f6;")
        sb_layout.addWidget(self.lbl_miss_val)

        sb_layout.addStretch()
        root.addWidget(status_bar)

        # ── 2. Middle: Left Controls + Right Radar Display ──
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        # Left control container (scrollable vertically only)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        left_scroll.setMinimumWidth(320)
        left_scroll.setMaximumWidth(360)

        left_widget = QWidget()
        left_widget.setMinimumWidth(0)
        lw_layout = QVBoxLayout(left_widget)
        lw_layout.setContentsMargins(0, 0, 4, 0)
        lw_layout.setSpacing(12)

        # Card 1: Serial & Drone Control
        card_ctrl = QFrame()
        card_ctrl.setObjectName("card")
        card_ctrl.setMinimumWidth(0)
        cc_layout = QVBoxLayout(card_ctrl)
        cc_layout.setContentsMargins(12, 12, 12, 12)
        cc_layout.setSpacing(10)

        title_ctrl = QLabel("SERIAL & DRONE CONTROL (SIYI)")
        title_ctrl.setObjectName("sectionTitle")
        cc_layout.addWidget(title_ctrl)

        # Port selector
        port_row = QHBoxLayout()
        port_row.setSpacing(6)
        self.port_combo = QComboBox()
        self.port_combo.setMinimumHeight(32)
        self.port_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.port_combo.setMinimumContentsLength(10)
        port_row.addWidget(self.port_combo, stretch=1)

        self.btn_refresh_ports = QPushButton("↻")
        self.btn_refresh_ports.setToolTip("Refresh COM ports")
        self.btn_refresh_ports.setFixedSize(32, 32)
        self.btn_refresh_ports.clicked.connect(self._refresh_ports)
        port_row.addWidget(self.btn_refresh_ports)
        cc_layout.addLayout(port_row)

        # Grid buttons (identik darat/command_page.py)
        grid = QGridLayout()
        grid.setSpacing(8)

        self.btn_connect = QPushButton("CONNECT")
        self.btn_connect.setObjectName("btnConnect")
        self.btn_connect.setMinimumHeight(40)
        self.btn_connect.clicked.connect(self._on_connect)
        grid.addWidget(self.btn_connect, 0, 0)

        self.btn_disconnect = QPushButton("DISCONNECT")
        self.btn_disconnect.setObjectName("btnStop")
        self.btn_disconnect.setMinimumHeight(40)
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.clicked.connect(self._on_disconnect)
        grid.addWidget(self.btn_disconnect, 0, 1)

        self.btn_start_rec = QPushButton("● START REC")
        self.btn_start_rec.setObjectName("btnStart")
        self.btn_start_rec.setMinimumHeight(40)
        self.btn_start_rec.clicked.connect(self._on_start_record)
        grid.addWidget(self.btn_start_rec, 1, 0)

        self.btn_stop_rec = QPushButton("■ STOP REC")
        self.btn_stop_rec.setObjectName("btnStop")
        self.btn_stop_rec.setMinimumHeight(40)
        self.btn_stop_rec.setEnabled(False)
        self.btn_stop_rec.clicked.connect(self._on_stop_record)
        grid.addWidget(self.btn_stop_rec, 1, 1)

        self.btn_status = QPushButton("STATUS")
        self.btn_status.setObjectName("btnPrimary")
        self.btn_status.setMinimumHeight(36)
        self.btn_status.clicked.connect(self._on_check_status)
        grid.addWidget(self.btn_status, 2, 0)

        self.btn_standby = QPushButton("STANDBY")
        self.btn_standby.setObjectName("btnPrimary")
        self.btn_standby.setMinimumHeight(36)
        self.btn_standby.clicked.connect(self._on_standby)
        grid.addWidget(self.btn_standby, 2, 1)

        self.btn_restart_drone = QPushButton("RESTART DRONE")
        self.btn_restart_drone.setObjectName("btnReset")
        self.btn_restart_drone.setMinimumHeight(36)
        self.btn_restart_drone.clicked.connect(self._on_restart_drone)
        grid.addWidget(self.btn_restart_drone, 3, 0, 1, 2)

        cc_layout.addLayout(grid)

        # Status response console
        resp_title = QLabel("STATUS RESPONSE")
        resp_title.setObjectName("statusHeading")
        cc_layout.addWidget(resp_title)

        self.status_response_text = QTextEdit()
        self.status_response_text.setObjectName("logConsole")
        self.status_response_text.setReadOnly(True)
        self.status_response_text.setFixedHeight(85)
        self.status_response_text.setFont(QFont("Consolas", 8))
        self.status_response_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.status_response_text.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        cc_layout.addWidget(self.status_response_text)

        lw_layout.addWidget(card_ctrl)

        # Card 2: Received Files & Utilities
        card_data = QFrame()
        card_data.setObjectName("card")
        card_data.setMinimumWidth(0)
        cd_layout = QVBoxLayout(card_data)
        cd_layout.setContentsMargins(12, 12, 12, 12)
        cd_layout.setSpacing(8)

        self.last_json_header = QLabel("LAST JSON RECEIVED (0):")
        self.last_json_header.setObjectName("statusHeading")
        cd_layout.addWidget(self.last_json_header)

        self.json_list_widget = QListWidget()
        self.json_list_widget.setFixedHeight(110)
        self.json_list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.json_list_widget.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.json_list_widget.itemClicked.connect(self._on_json_item_clicked)
        cd_layout.addWidget(self.json_list_widget)

        # Replay & Clear buttons
        util_row = QHBoxLayout()
        util_row.setSpacing(8)

        self.btn_replay = QPushButton("📂 REPLAY JSON...")
        self.btn_replay.setObjectName("btnPrimary")
        self.btn_replay.setMinimumHeight(34)
        self.btn_replay.clicked.connect(self._on_replay_json)
        util_row.addWidget(self.btn_replay)

        self.btn_clear = QPushButton("🗑 CLEAR")
        self.btn_clear.setObjectName("btnReset")
        self.btn_clear.setMinimumHeight(34)
        self.btn_clear.clicked.connect(self._on_clear_radar)
        util_row.addWidget(self.btn_clear)

        cd_layout.addLayout(util_row)
        lw_layout.addWidget(card_data)
        lw_layout.addStretch()

        left_scroll.setWidget(left_widget)
        splitter.addWidget(left_scroll)

        # Right Tactical Radar Display
        right_frame = QFrame()
        right_frame.setObjectName("card")
        rf_layout = QVBoxLayout(right_frame)
        rf_layout.setContentsMargins(6, 6, 6, 6)

        self.radar = Radar2DWidget()
        rf_layout.addWidget(self.radar)
        splitter.addWidget(right_frame)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        root.addWidget(splitter, stretch=1)

    def _wire_signals(self):
        # Serial and JSON signals
        self._serial.connection_changed.connect(self._on_connection_changed)
        self._serial.message_received.connect(self._on_serial_message)
        self.json_saved.connect(self._on_json_saved_gui)

        self._refresh_ports()

    def _refresh_ports(self):
        curr = self.port_combo.currentData() or self._config_manager.get("serial_port", "COM3")
        self.port_combo.clear()

        manager = getattr(self._serial, "manager", None)
        ports = manager.get_available_ports() if manager and hasattr(manager, "get_available_ports") else []
        idx_to_select = 0
        for i, p in enumerate(ports):
            self.port_combo.addItem(p["display_label"], p["device"])
            if p["device"] == curr:
                idx_to_select = i
        if self.port_combo.count() == 0:
            self.port_combo.addItem("COM3 (Virtual)", "COM3")
        else:
            self.port_combo.setCurrentIndex(idx_to_select)

    def _check_device_connected(self) -> bool:
        if not self._serial.is_connected():
            QMessageBox.warning(
                self,
                "Device Disconnected",
                "Serial device is not connected.\n\nPlease connect the SIYI/USB cable and click CONNECT.",
                QMessageBox.StandardButton.Ok
            )
            return False
        return True

    def _update_ui_state(self):
        connected = self._serial.is_connected()

        self.btn_connect.setEnabled(not connected and not self._is_connecting)
        if not self._is_connecting:
            self.btn_connect.setText("CONNECT")

        self.btn_disconnect.setEnabled(connected)
        self.btn_start_rec.setEnabled(connected and not self._is_recording and not self._is_stopping)
        self.btn_stop_rec.setEnabled(connected and self._is_recording and not self._is_stopping)
        self.btn_status.setEnabled(connected)
        self.btn_standby.setEnabled(connected)
        self.btn_restart_drone.setEnabled(connected)

        # Connection Indicator
        if connected:
            info = self._serial.get_port_info()
            port = info.get("port", "—") if info else "—"
            self.conn_indicator.setText(f"● CONNECTED ({port})")
            self.conn_indicator.setObjectName("statusOk")
        else:
            self.conn_indicator.setText("● DISCONNECTED")
            self.conn_indicator.setObjectName("statusError")

        # Recording Indicator
        if self._is_stopping:
            self.rec_indicator.setText("● STOPPING (Draining...)")
            self.rec_indicator.setObjectName("statusWarn")
        elif self._is_recording:
            self.rec_indicator.setText("● RECORDING")
            self.rec_indicator.setObjectName("statusOk")
        else:
            self.rec_indicator.setText("○ IDLE")
            self.rec_indicator.setObjectName("statusHeading")

        for w in (self.conn_indicator, self.rec_indicator):
            w.style().unpolish(w)
            w.style().polish(w)

    # ── Connection Handling ──

    def _on_connect(self):
        if self._is_connecting:
            return
        self._is_connecting = True
        self.btn_connect.setEnabled(False)
        self.btn_connect.setText("CONNECTING...")
        self._log("Connecting to serial port...", "INFO")

        port = self.port_combo.currentData() or self.port_combo.currentText()
        if port and port.upper() != "AUTO":
            self._serial.connect_to_port_async(port, callback=self._on_connect_finished)
        else:
            self._serial.connect_auto_async(callback=self._on_connect_finished)

    def _on_connect_finished(self, success: bool, port: str):
        self._is_connecting = False
        self.btn_connect.setText("CONNECT")
        if success:
            self._log(f"Connected to serial port ({port})", "INFO")
            self.status_changed.emit(f"CONNECTED ({port})", True)
        else:
            self._log("Connection failed: No serial device found", "ERROR")
            self.status_changed.emit("NOT CONNECTED", False)
            QMessageBox.warning(
                self,
                "Connection Failed",
                "No serial device detected.\n\nPlease check the SIYI HM30 USB connection and driver.",
                QMessageBox.StandardButton.Ok
            )
        self._update_ui_state()

    def _on_disconnect(self):
        if self._stop_watchdog_timer.isActive():
            self._stop_watchdog_timer.stop()
        if self._rx_thread and self._rx_thread.is_alive():
            self._jr.stop_continuous()
            self._rx_thread.join(timeout=0.5)

        self._serial.disconnect()
        self._is_recording = False
        self._is_stopping = False
        self.status_changed.emit("NOT CONNECTED", False)
        self._log("Serial disconnected.", "INFO")
        self._update_ui_state()

    @Slot(bool, str)
    def _on_connection_changed(self, connected: bool, port: str):
        self._update_ui_state()

    # ── Serial Messages & Commands ──

    @Slot(str)
    def _on_serial_message(self, msg: str):
        """Handle incoming drone telemetry responses and STOP_REC confirmation."""
        if not msg:
            return

        msg_upper = msg.upper()
        keywords = ["MIC", "SDR", "ZOOM", "OK:", "ERROR:", "IDLE", "RECORDING", "STATUS:"]
        if any(kw in msg_upper for kw in keywords):
            self.status_response_text.append(f"> {msg.strip()}")
            self.status_response_text.ensureCursorVisible()

        # Handle STOP_REC confirmation
        if self._is_stopping:
            stop_keywords = ["RECORDING STOPPED", "STOPPED AND PROCESSED", "TIDAK ADA RECORDING AKTIF"]
            if any(sk in msg_upper for sk in stop_keywords) or (msg_upper.startswith("OK:") and "STOP" in msg_upper):
                self._log(f"Drone confirmation received: {msg.strip()}", "INFO")
                if self._stop_watchdog_timer.isActive():
                    self._stop_watchdog_timer.stop()
                QTimer.singleShot(500, self._finalize_stop_record)

    def _on_check_status(self):
        if not self._check_device_connected():
            return
        self._log("Sending STATUS command to drone...", "INFO")
        self.status_response_text.clear()
        self.status_response_text.append("Requesting system status...")
        self._serial.send_command(CMD_STATUS)

    def _on_standby(self):
        if not self._check_device_connected():
            return
        self._log("Sending STANDBY command to drone...", "INFO")
        self._serial.send_command(CMD_STANDBY)

    def _on_restart_drone(self):
        if not self._check_device_connected():
            return
        reply = QMessageBox.question(
            self,
            "Restart Drone",
            "Are you sure you want to restart the drone software?\nActive recording will be stopped.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._log("Sending RESTART command to drone via serial...", "WARNING")
            self._serial.send_command(CMD_RESTART)

    # ── Recording State Machine (START / STOP) ──

    def _on_start_record(self):
        if not self._check_device_connected():
            return

        if self._is_recording or self._is_stopping:
            self._log("Already recording or stopping", "WARNING")
            return

        self._is_recording = True
        self._is_stopping = False
        self._jr.reset()
        self._last_json_file = None
        self._received_json_files.clear()
        self._session_chunk_files.clear()
        self.json_list_widget.clear()
        self.last_json_header.setText("LAST JSON RECEIVED (0):")

        # Start continuous JSON receiver thread (identik darat/)
        self._rx_thread = threading.Thread(
            target=self._jr.receive_json,
            kwargs={"on_saved": self.json_saved.emit, "continuous": True},
            daemon=True,
            name="JsonReceiver-Continuous",
        )
        self._rx_thread.start()
        self._log("Continuous JSON receiver started", "DEBUG")

        self._serial.send_command(CMD_START_RECORD)
        self._log("Recording start command sent (START_REC)", "INFO")
        self._update_ui_state()

    def _on_stop_record(self):
        if not self._check_device_connected():
            return

        if not self._is_recording:
            self._log("Not recording", "WARNING")
            return

        if self._is_stopping:
            self._log("Already stopping, awaiting drone confirmation...", "WARNING")
            return

        self._is_stopping = True
        self._update_ui_state()

        self._serial.send_command(CMD_STOP_RECORD)
        self._log("STOP_REC sent — awaiting drone confirmation and data...", "INFO")
        self._stop_watchdog_timer.start(60000)

    def _on_stop_watchdog_timeout(self):
        if self._is_stopping:
            self._log("[WARNING] STOP_REC watchdog timeout (60s). Drone confirmation not received, forcing stop.", "WARNING")
            self._finalize_stop_record()

    def _finalize_stop_record(self):
        if self._stop_watchdog_timer.isActive():
            self._stop_watchdog_timer.stop()
        self._jr.stop_continuous()
        self._is_recording = False
        self._is_stopping = False
        self._log("Recording stopped (receiver finished draining)", "INFO")

        # Gabungkan semua chunk yang diterima selama sesi rekaman
        if self._session_chunk_files:
            save_dir = getattr(self._jr, "save_directory", None) or self._drone_save_dir
            try:
                merged_path = merge_session_jsons(self._session_chunk_files, save_dir)
                if merged_path and os.path.exists(merged_path):
                    self._last_json_file = merged_path
                    if merged_path not in self._received_json_files:
                        self._received_json_files.insert(0, merged_path)

                    basename = os.path.basename(merged_path)
                    ts = datetime.now().strftime("%H:%M:%S")
                    item = QListWidgetItem(f"📦 [{ts}] {basename} (MERGED)")
                    item.setData(Qt.ItemDataRole.UserRole, merged_path)
                    self.json_list_widget.insertItem(0, item)
                    self.json_list_widget.scrollToTop()

                    self._log(f"Session chunks merged successfully: {basename}", "INFO")
                    # Proses ulang merged file untuk memastikan semua event ter-cover
                    self._process_json_file(merged_path, is_replay=False)
            except Exception as e:
                self._log(f"Failed to merge session chunks: {e}", "ERROR")

        self._update_ui_state()

    # ── JSON Processing & 2D Localization ──

    @Slot(str)
    def _on_json_saved_gui(self, filename: str):
        """Dipanggil di thread GUI ketika paket JSON berhasil disimpan."""
        self._last_json_file = filename

        if filename not in self._received_json_files:
            self._received_json_files.insert(0, filename)
        if filename not in self._session_chunk_files:
            self._session_chunk_files.append(filename)

        basename = os.path.basename(filename)
        timestamp_str = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem(f"📄 [{timestamp_str}] {basename}")
        item.setData(Qt.ItemDataRole.UserRole, filename)
        self.json_list_widget.insertItem(0, item)
        self.json_list_widget.scrollToTop()

        count = len(self._received_json_files)
        self.last_json_header.setText(f"LAST JSON RECEIVED ({count}):")
        self._log(f"JSON chunk received ({count}): {basename} at {timestamp_str}", "INFO")

        # Jalankan kalkulasi lokalisasi 2D untuk data baru ini
        self._process_json_file(filename, is_replay=False)
        self._update_ui_state()

    def _on_json_item_clicked(self, item: QListWidgetItem):
        filename = item.data(Qt.ItemDataRole.UserRole)
        if filename and os.path.exists(filename):
            self._last_json_file = filename
            self._log(f"Selected JSON: {os.path.basename(filename)}", "INFO")

    def _process_json_file(self, file_path: str, is_replay: bool = False):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self._log(f"Failed to read JSON file '{file_path}': {e}", "ERROR")
            return

        events = data.get("events", [])
        if not events:
            self._log(f"No acoustic events found in {os.path.basename(file_path)}", "DEBUG")
            return

        cfg = self._config_manager.get_all()
        mic_positions = cfg.get("mic_positions", {})

        from ...ssl.ssl_dispatcher import solve_adaptive

        new_events_calculated = 0
        for ev in events:
            ev_num = ev.get("event_number", len(self._events) + 1)
            # Hindari duplikasi jika event_number sudah dihitung dalam sesi saat ini
            if not is_replay and any(e.get("event_number") == ev_num for e in self._events):
                continue

            res = solve_adaptive(ev, mic_positions, cfg)
            if res is not None and res.get("valid"):
                x = res["x"]
                y = res["y"]
                z = res.get("z_val")
                miss_2d = res["miss_distance_2d"]
                miss_3d = res["miss_distance_3d"]
                azimuth_deg = res["azimuth_deg"]
                solver_name = res["solver_name"]
                mode_label = res["mode_label"]

                ev_record = {
                    "event_number": ev_num,
                    "x": x,
                    "y": y,
                    "z": z,
                    "miss_distance": miss_2d,
                    "miss_distance_3d": miss_3d,
                    "azimuth_deg": azimuth_deg,
                    "mode_label": mode_label,
                    "valid": True,
                }
                self._events.append(ev_record)
                new_events_calculated += 1

                z_str = f" | Alt Z={z:+.2f}m" if z is not None else ""
                self._log(
                    f"[SSL] Event #{ev_num} → CPA X={x:+.2f}m, Y={y:+.2f}m{z_str} | "
                    f"Miss Dist={miss_2d:.2f}m | Azimuth={azimuth_deg:.1f}° ({mode_label})",
                    "INFO"
                )

        if new_events_calculated > 0 or is_replay:
            self.refresh_display()

    def _on_replay_json(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open TDOA JSON Recording", self._drone_save_dir, "JSON Files (*.json)"
        )
        if not file_path:
            return

        self._log(f"Replaying record file: {os.path.basename(file_path)}", "INFO")
        self._process_json_file(file_path, is_replay=True)

    def _on_clear_radar(self):
        self._events.clear()
        self.lbl_last_coord.setText("---")
        self.lbl_miss_val.setText("--- m")
        self.lbl_alt_val.setText("N/A (Planar)")
        self.lbl_ev_count.setText("0")
        self.radar.clear()
        self.refresh_display()
        self._log("Radar display and event list cleared.", "INFO")

    def refresh_display(self):
        cfg = self._config_manager.get_all()
        method_key = cfg.get("ssl_method", "auto_adaptive")
        from ...ssl.ssl_dispatcher import SOLVER_CHOICES, get_mic_array_span
        method_name = SOLVER_CHOICES.get(method_key, method_key)
        if method_key == "auto_adaptive":
            _, _, dz = get_mic_array_span(cfg.get("mic_positions", {}))
            mode_tag = f"3D Proj ({dz*100:.0f}cm)" if dz >= 0.02 else "Planar 2D"
            self.lbl_method_val.setText(f"Auto ({mode_tag})")
        else:
            self.lbl_method_val.setText(method_name.split("(")[0].strip())

        self.lbl_ev_count.setText(str(len(self._events)))
        if self._events:
            last = self._events[-1]
            x, y = last["x"], last["y"]
            z = last.get("z")
            miss = last["miss_distance"]
            self.lbl_last_coord.setText(f"[{x:+.2f}, {y:+.2f}] m")
            self.lbl_miss_val.setText(f"{miss:.2f} m")
            if z is not None:
                self.lbl_alt_val.setText(f"{z:+.2f} m")
            else:
                self.lbl_alt_val.setText("N/A (Planar)")
        else:
            self.lbl_last_coord.setText("---")
            self.lbl_miss_val.setText("--- m")
            self.lbl_alt_val.setText("N/A (Planar)")

        self.radar.set_data(self._events)
