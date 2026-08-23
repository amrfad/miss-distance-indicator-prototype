# darat/ui/pages/command_page.py
"""Command Page — Serial command control with status response panel."""

import os
import threading
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QPushButton, QLabel, QTextEdit, QMessageBox,
    QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Signal, Qt, QTimer

from ...core.config import CMD_START_RECORD, CMD_STOP_RECORD, CMD_STATUS, CMD_RESTART


class CommandPage(QWidget):
    """Command tab: Connect, Disconnect, Start/Stop Rec, Status, Process Data."""

    log_message = Signal(str, str)  # (message, level)
    json_saved  = Signal(str)       # (file_path)

    def __init__(self, serial_bridge, file_transfer, json_receiver,
                 log_callback=None, navigate_callback=None, parent=None):
        super().__init__(parent)
        self._serial = serial_bridge
        self._ft = file_transfer
        self._jr = json_receiver
        self._log_callback = log_callback
        self._navigate = navigate_callback
        self._rx_thread: threading.Thread | None = None
        self._is_recording = False
        self._is_stopping = False
        self._is_connecting = False
        self._last_json_file = None
        self._received_json_files: list[str] = []

        # Watchdog timer jika drone tidak merespon STOP_REC
        self._stop_watchdog_timer = QTimer(self)
        self._stop_watchdog_timer.setSingleShot(True)
        self._stop_watchdog_timer.timeout.connect(self._on_stop_watchdog_timeout)

        self._build_ui()
        self._update_ui_state()

        # Timer untuk polling status koneksi & UI
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._poll)
        self._poll_timer.start(1000)

        # Hubungkan sinyal dari serial_bridge untuk menangkap balasan STATUS & konfirmasi STOP_REC
        self._serial.message_received.connect(self._on_serial_message)

        # Hubungkan signal internal untuk memproses hasil JSON secara thread-safe
        self.json_saved.connect(self._on_json_saved_gui)

    def _log(self, msg, level="INFO"):
        if self._log_callback:
            self._log_callback(msg, level)
        self.log_message.emit(msg, level)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(16)

        # ── 1. Status bar (koneksi + recording) ──
        status_bar = QFrame()
        status_bar.setObjectName("card")
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(16, 10, 16, 10)
        status_layout.setSpacing(16)

        self.conn_indicator = QLabel("● DISCONNECTED")
        self.conn_indicator.setObjectName("statusError")
        status_layout.addWidget(self.conn_indicator)

        self.rec_indicator = QLabel("○ IDLE")
        self.rec_indicator.setObjectName("statusHeading")
        status_layout.addWidget(self.rec_indicator)

        status_layout.addStretch()
        root.addWidget(status_bar)

        # ── Middle Section: Buttons (Left) & Status Response (Right) ──
        middle_layout = QHBoxLayout()
        middle_layout.setSpacing(16)

        # ── 2. Tombol grid 2x4 (Left) ──
        btn_group = QFrame()
        btn_group.setObjectName("card")
        btn_layout = QGridLayout(btn_group)
        btn_layout.setContentsMargins(16, 16, 16, 16)
        btn_layout.setSpacing(12)

        self.connect_btn = QPushButton("CONNECT")
        self.connect_btn.setObjectName("btnConnect")
        self.connect_btn.setMinimumHeight(44)
        self.connect_btn.clicked.connect(self._on_connect)

        self.disconnect_btn = QPushButton("DISCONNECT")
        self.disconnect_btn.setObjectName("btnStop")
        self.disconnect_btn.setMinimumHeight(44)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.clicked.connect(self._on_disconnect)

        self.start_rec_btn = QPushButton("● START REC")
        self.start_rec_btn.setObjectName("btnStart")
        self.start_rec_btn.setMinimumHeight(44)
        self.start_rec_btn.clicked.connect(self._on_start_record)

        self.stop_rec_btn = QPushButton("■ STOP REC")
        self.stop_rec_btn.setObjectName("btnStop")
        self.stop_rec_btn.setMinimumHeight(44)
        self.stop_rec_btn.clicked.connect(self._on_stop_record)

        self.status_btn = QPushButton("STATUS")
        self.status_btn.setObjectName("btnPrimary")
        self.status_btn.setMinimumHeight(44)
        self.status_btn.clicked.connect(self._on_check_status)

        self.process_btn = QPushButton("PROCESS DATA")
        self.process_btn.setObjectName("btnSave")
        self.process_btn.setMinimumHeight(44)
        self.process_btn.clicked.connect(self._on_process_data)

        self.restart_drone_btn = QPushButton("RESTART DRONE")
        self.restart_drone_btn.setObjectName("btnReset")
        self.restart_drone_btn.setMinimumHeight(44)
        self.restart_drone_btn.clicked.connect(self._on_restart_drone)

        # Susun di grid 3x2
        btn_layout.addWidget(self.connect_btn, 0, 0)
        btn_layout.addWidget(self.disconnect_btn, 0, 1)
        btn_layout.addWidget(self.start_rec_btn, 1, 0)
        btn_layout.addWidget(self.stop_rec_btn, 1, 1)
        btn_layout.addWidget(self.status_btn, 2, 0)
        btn_layout.addWidget(self.process_btn, 2, 1)
        btn_layout.addWidget(self.restart_drone_btn, 3, 0, 1, 2)

        middle_layout.addWidget(btn_group, stretch=1)

        # ── 3. Panel STATUS RESPONSE (Right) ──
        resp_group = QFrame()
        resp_group.setObjectName("card")
        resp_layout = QVBoxLayout(resp_group)
        resp_layout.setContentsMargins(16, 12, 16, 12)
        resp_layout.setSpacing(8)

        resp_title = QLabel("STATUS RESPONSE")
        resp_title.setObjectName("statusHeading")
        resp_layout.addWidget(resp_title)

        self.status_response_text = QTextEdit()
        self.status_response_text.setObjectName("logConsole")
        self.status_response_text.setReadOnly(True)
        self.status_response_text.setPlaceholderText("Press 'STATUS' to get system health report...")
        resp_layout.addWidget(self.status_response_text, stretch=1)

        middle_layout.addWidget(resp_group, stretch=1)

        root.addLayout(middle_layout)

        # ── 4. LAST JSON RECEIVED (N) ──
        last_group = QFrame()
        last_group.setObjectName("card")
        last_layout = QVBoxLayout(last_group)
        last_layout.setContentsMargins(16, 12, 16, 12)
        last_layout.setSpacing(8)

        self.last_json_header = QLabel("LAST JSON RECEIVED (0):")
        self.last_json_header.setObjectName("statusHeading")
        last_layout.addWidget(self.last_json_header)

        self.json_list_widget = QListWidget()
        self.json_list_widget.setObjectName("logConsole")
        self.json_list_widget.setMinimumHeight(120)
        self.json_list_widget.setMaximumHeight(220)
        self.json_list_widget.itemClicked.connect(self._on_json_item_clicked)
        last_layout.addWidget(self.json_list_widget)

        root.addWidget(last_group)

        root.addStretch()

    def _update_ui_state(self):
        raw = self._serial.is_connected()
        connected = bool(raw) if raw is not None else False

        self.connect_btn.setEnabled(not connected and not self._is_connecting)
        if not self._is_connecting:
            self.connect_btn.setText("CONNECT")

        self.disconnect_btn.setEnabled(connected)
        self.status_btn.setEnabled(True)
        self.start_rec_btn.setEnabled(not self._is_recording and not self._is_stopping)
        self.stop_rec_btn.setEnabled(self._is_recording and not self._is_stopping)
        self.restart_drone_btn.setEnabled(True)

        has_json = self._last_json_file is not None and os.path.exists(self._last_json_file)
        self.process_btn.setEnabled(has_json and not self._is_stopping)

        # Update status bar
        if connected:
            info = self._serial.get_port_info()
            port = info.get("port", "—") if info else "—"
            self.conn_indicator.setText(f"● CONNECTED ({port})")
            self.conn_indicator.setObjectName("statusOk")
        else:
            self.conn_indicator.setText("● DISCONNECTED")
            self.conn_indicator.setObjectName("statusError")

        if self._is_stopping:
            self.rec_indicator.setText("● STOPPING (Draining...)")
            self.rec_indicator.setObjectName("statusWarn")
        elif self._is_recording:
            self.rec_indicator.setText("● RECORDING")
            self.rec_indicator.setObjectName("statusOk")
        else:
            self.rec_indicator.setText("○ IDLE")
            self.rec_indicator.setObjectName("statusHeading")

        # Refresh style
        for w in (self.conn_indicator, self.rec_indicator):
            w.style().unpolish(w)
            w.style().polish(w)

    def _poll(self):
        self._update_ui_state()

    def _check_device_connected(self) -> bool:
        """Check if serial port is connected. If not, display warning modal."""
        if not self._serial.is_connected():
            QMessageBox.warning(
                self,
                "Device Disconnected",
                "Serial device is not connected.\n\nPlease connect the USB/Serial cable and click CONNECT.",
                QMessageBox.StandardButton.Ok
            )
            return False
        return True

    def _on_serial_message(self, msg: str):
        """Handle incoming drone status messages and STOP_REC confirmation."""
        if not msg:
            return

        msg_upper = msg.upper()
        keywords = ["MIC", "SDR", "ZOOM", "OK:", "ERROR:", "IDLE", "RECORDING", "STATUS:"]
        if any(kw in msg_upper for kw in keywords):
            self.status_response_text.append(f"> {msg.strip()}")
            self.status_response_text.ensureCursorVisible()

        if self._is_stopping:
            stop_keywords = ["RECORDING STOPPED", "STOPPED AND PROCESSED", "TIDAK ADA RECORDING AKTIF"]
            if any(sk in msg_upper for sk in stop_keywords) or (msg_upper.startswith("OK:") and "STOP" in msg_upper):
                self._log(f"Drone confirmation received: {msg.strip()}", "INFO")
                if self._stop_watchdog_timer.isActive():
                    self._stop_watchdog_timer.stop()
                QTimer.singleShot(500, self._finalize_stop_record)

    def _on_connect(self):
        if self._is_connecting:
            return
        self._is_connecting = True
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("CONNECTING...")
        self._log("Connecting to serial port...", "INFO")

        parent = self.window()
        if hasattr(parent, '_do_connect_command'):
            parent._do_connect_command(callback=self._on_connect_finished)
        else:
            self._serial.connect_auto_async(callback=self._on_connect_finished)

    def _on_connect_finished(self, success: bool, port: str):
        self._is_connecting = False
        self.connect_btn.setText("CONNECT")
        if success:
            self._log(f"Connected to serial port ({port})", "INFO")
        else:
            self._log("Connection failed: No serial device found", "ERROR")
            QMessageBox.warning(
                self,
                "Connection Failed",
                "No serial device detected.\n\nPlease check the cable connection and driver.",
                QMessageBox.StandardButton.Ok
            )
        self._update_ui_state()

    def _on_disconnect(self):
        parent = self.window()
        if hasattr(parent, '_do_disconnect_command'):
            parent._do_disconnect_command()
        if self._stop_watchdog_timer.isActive():
            self._stop_watchdog_timer.stop()
        if self._rx_thread and self._rx_thread.is_alive():
            self._jr.stop_continuous()
            self._rx_thread.join(timeout=0.5)
        self._is_recording = False
        self._is_stopping = False
        self._update_ui_state()

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

    def _on_check_status(self):
        if not self._check_device_connected():
            return

        self._log("Sending STATUS command to drone...", "INFO")
        self.status_response_text.clear()
        self.status_response_text.append("Requesting system status...")
        self._serial.send_command(CMD_STATUS)

    def _on_start_record(self):
        if not self._check_device_connected():
            return

        if self._is_recording or self._is_stopping:
            self._log("Already recording or stopping", "WARNING")
            return

        parent = self.window()
        if hasattr(parent, '_do_start_record_command'):
            parent._do_start_record_command()

        self._is_recording = True
        self._is_stopping = False
        self._jr.reset()
        self._last_json_file = None
        self._received_json_files.clear()
        self.json_list_widget.clear()
        self.last_json_header.setText("LAST JSON RECEIVED (0):")

        self._rx_thread = threading.Thread(
            target=self._jr.receive_json,
            kwargs={"on_saved": self.json_saved.emit, "continuous": True},
            daemon=True,
            name="JsonReceiver-Continuous",
        )
        self._rx_thread.start()
        self._log("Continuous JSON receiver started", "DEBUG")
        self._update_ui_state()

    def _on_json_saved_gui(self, filename: str):
        """Called on GUI thread when JSON file is saved successfully."""
        parent = self.window()
        self._last_json_file = filename

        if filename not in self._received_json_files:
            self._received_json_files.insert(0, filename)

        basename = os.path.basename(filename)
        timestamp_str = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem(f"📄  [{timestamp_str}]  {basename}")
        item.setData(Qt.ItemDataRole.UserRole, filename)
        self.json_list_widget.insertItem(0, item)
        self.json_list_widget.scrollToTop()

        count = len(self._received_json_files)
        self.last_json_header.setText(f"LAST JSON RECEIVED ({count}):")

        self._log(f"JSON received ({count}): {basename} at {timestamp_str}", "INFO")
        self._update_ui_state()
        if hasattr(parent, '_on_json_received'):
            parent._on_json_received(filename)

    def _on_json_item_clicked(self, item: QListWidgetItem):
        filename = item.data(Qt.ItemDataRole.UserRole)
        if filename and os.path.exists(filename):
            self._last_json_file = filename
            self._log(f"Selected JSON for processing: {os.path.basename(filename)}", "INFO")
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

        parent = self.window()
        if hasattr(parent, '_do_stop_record_command'):
            parent._do_stop_record_command()

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
        self._update_ui_state()

    def _on_process_data(self):
        if not self._last_json_file or not os.path.exists(self._last_json_file):
            QMessageBox.warning(
                self,
                "Data Unavailable",
                "No recorded JSON file available for processing.",
                QMessageBox.StandardButton.Ok
            )
            return

        self._log(f"Processing: {os.path.basename(self._last_json_file)}", "INFO")
        if self._navigate:
            self._navigate(2)

        parent = self.window()
        if hasattr(parent, '_page_process'):
            process_page = parent._page_process
            process_page.set_working_dir(os.path.dirname(self._last_json_file))
            if hasattr(process_page, 'process_file'):
                process_page.process_file(self._last_json_file)
            else:
                self._log("ProcessPage has no 'process_file' method", "ERROR")
        else:
            self._log("Process page not found", "ERROR")