# darat/ui/pages/command_page.py
"""Command Page — serial command control (port of darat/screens/command_screen.py)."""

import os
import threading

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QPushButton, QLabel, QFileDialog,
)
from PyQt6.QtCore import pyqtSignal, Qt

from ...config import (
    CMD_STANDBY, CMD_START_RECORD, CMD_STOP_RECORD,
    CMD_STATUS, CMD_INFO, CMD_PROCESS, CMD_TRANSMIT,
)


class CommandPage(QWidget):
    """Command tab: 7 action buttons + current-status display.

    All button actions route through serial_bridge. JSON reception
    spawns a daemon thread (using existing JsonReceiver logic).

    Signals
    -------
    log_message(str, str)    — (message, level) → shared log panel
    recording_started()      — notify toolbar to update button state
    recording_stopped()      — notify toolbar to update button state
    json_received(str)       — filename of saved JSON
    """

    log_message       = pyqtSignal(str, str)
    recording_started = pyqtSignal()
    recording_stopped = pyqtSignal()
    json_received     = pyqtSignal(str)

    def __init__(self, serial_bridge, file_transfer, json_receiver, parent=None):
        super().__init__(parent)
        self._serial  = serial_bridge
        self._ft      = file_transfer
        self._jr      = json_receiver
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # Page title
        title = QLabel("SERIAL COMMAND CONTROL")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        # Status bar
        self._status_frame = QFrame()
        self._status_frame.setObjectName("card")
        sl = QHBoxLayout(self._status_frame)
        sl.setContentsMargins(12, 8, 12, 8)
        self._status_label = QLabel("Status: Ready")
        self._status_label.setObjectName("statusValue")
        sl.addWidget(self._status_label)
        sl.addStretch()
        self._port_label = QLabel("Serial: Disconnected")
        self._port_label.setObjectName("statusHeading")
        sl.addWidget(self._port_label)
        root.addWidget(self._status_frame)

        # Button grid
        btn_frame = QFrame()
        btn_frame.setObjectName("card")
        grid = QGridLayout(btn_frame)
        grid.setSpacing(10)
        grid.setContentsMargins(16, 16, 16, 16)

        buttons = [
            ("CHECK STATUS",   "btnConnect",  self._check_status,  0, 0),
            ("INFO",           "btnPrimary",  self._info,          0, 1),
            ("START RECORD",   "btnStart",    self._start_record,  1, 0),
            ("STOP RECORD",    "btnStop",     self._stop_record,   1, 1),
            ("PROCESS DATA",   "btnSave",     self._process,       2, 0),
            ("TRANSMIT FILES", "btnPrimary",  self._transmit,      2, 1),
            ("SET SAVE DIR",   "",            self._choose_save_dir, 3, 0),
        ]

        for text, obj_name, slot, row, col in buttons:
            btn = QPushButton(text)
            if obj_name:
                btn.setObjectName(obj_name)
            btn.setMinimumHeight(44)
            btn.clicked.connect(slot)
            grid.addWidget(btn, row, col)

        root.addWidget(btn_frame)
        root.addStretch()

        # Save dir info
        dir_frame = QFrame()
        dir_frame.setObjectName("card")
        dl = QHBoxLayout(dir_frame)
        dl.setContentsMargins(12, 6, 12, 6)
        dl.addWidget(QLabel("Save directory:"))
        self._dir_label = QLabel("—")
        self._dir_label.setObjectName("statusValue")
        dl.addWidget(self._dir_label, stretch=1)
        root.addWidget(dir_frame)

        self._refresh_status()

    # ── Helpers ──────────────────────────────────────────────────────────

    def _refresh_status(self):
        connected = self._serial.is_connected()
        info = self._serial.get_port_info()
        port = info["port"] if info else "—"
        self._port_label.setText(
            f"Serial: {'Connected (' + port + ')' if connected else 'Disconnected'}"
        )
        save_dir = getattr(self._ft, "save_directory", "")
        self._dir_label.setText(os.path.basename(save_dir) or save_dir or "—")

    def _set_status(self, text: str):
        self._status_label.setText(text)

    # ── Command handlers ─────────────────────────────────────────────────

    def _check_status(self):
        self._serial.send_command(CMD_STATUS)
        self._set_status(f"Checking status… ({CMD_STATUS} sent)")
        self.log_message.emit("Sent STATUS command", "INFO")

    def _info(self):
        self._serial.send_command(CMD_INFO)
        self._set_status(f"Retrieving info… ({CMD_INFO} sent)")
        self.log_message.emit("Sent INFO command", "INFO")

    def _start_record(self):
        self._serial.send_command(CMD_START_RECORD)
        self._set_status(f"Recording… ({CMD_START_RECORD} sent)")
        self.log_message.emit("Recording started", "INFO")
        self.recording_started.emit()

    def _stop_record(self):
        self._serial.send_command(CMD_STOP_RECORD)
        self._set_status(f"Recording stopped — waiting for JSON… ({CMD_STOP_RECORD} sent)")
        self.log_message.emit("Recording stopped — waiting for JSON file", "WARNING")
        self.recording_stopped.emit()

        def _on_json_saved(filename: str):
            self._set_status(f"JSON received: {filename}")
            self.log_message.emit(f"JSON file received: {filename}", "INFO")
            self.json_received.emit(filename)

        t = threading.Thread(
            target=self._jr.receive_json,
            kwargs={"on_saved": _on_json_saved},
            daemon=True,
        )
        t.start()
        self.log_message.emit("JSON reception thread started", "DEBUG")

    def _process(self):
        self._serial.send_command(CMD_PROCESS)
        self._set_status(f"Processing… ({CMD_PROCESS} sent)")
        self.log_message.emit("Sent PROCESS command", "INFO")

    def _transmit(self):
        self._serial.send_command(CMD_TRANSMIT)
        self._set_status(f"Transmitting… ({CMD_TRANSMIT} sent)")
        self.log_message.emit("Sent TRANSMIT command", "INFO")

    def _choose_save_dir(self):
        current = getattr(self._ft, "save_directory", "")
        directory = QFileDialog.getExistingDirectory(
            self, "Choose directory to save received files", current
        )
        if directory:
            self._ft.save_directory  = directory
            self._jr.save_directory  = directory
            self._dir_label.setText(os.path.basename(directory))
            self.log_message.emit(f"Save directory changed to: {directory}", "INFO")
