"""
Command Screen
Halaman kontrol perintah serial ke drone: status, record, process, dsb.
"""

import os
import threading
from tkinter import BOTH, END, LEFT, NORMAL, RIGHT, Scrollbar, Text, Y, filedialog, ttk

from ..config import (
    CMD_STANDBY,
    CMD_START_RECORD,
    CMD_STOP_RECORD,
    CMD_STATUS,
    CMD_INFO,
    CMD_PROCESS,
    CMD_TRANSMIT,
)


class CommandScreen:
    """
    Halaman perintah dengan 6 tombol aksi dan terminal log.
    Menggantikan EventGUI.command_page() + semua *_action() methods.
    """

    def __init__(self, app):
        self.app = app
        self.status_label = None  # Di-set oleh build()

    def build(self):
        app = self.app
        frame = app.main_frame

        # Title
        ttk.Label(frame, text="COMMAND PAGE", font=("Arial", 24, "bold")).pack(pady=20)

        # Button grid (6 tombol, 3x2)
        button_frame = ttk.Frame(frame)
        button_frame.pack(pady=20)

        ttk.Button(
            button_frame, text="Status", command=self._check_status,
            width=20, style="Orange.TButton",
        ).grid(row=0, column=0, padx=20, pady=20)

        ttk.Button(
            button_frame, text="Info", command=self._info,
            width=20, style="Blue.TButton",
        ).grid(row=0, column=1, padx=20, pady=20)

        ttk.Button(
            button_frame, text="Start Record", command=self._start_record,
            width=20, style="Green.TButton",
        ).grid(row=1, column=0, padx=20, pady=20)

        ttk.Button(
            button_frame, text="Stop Record", command=self._stop_record,
            width=20, style="Red.TButton",
        ).grid(row=1, column=1, padx=20, pady=20)

        ttk.Button(
            button_frame, text="Process", command=self._process,
            width=20, style="LightGreen.TButton",
        ).grid(row=2, column=0, padx=20, pady=20)

        ttk.Button(
            button_frame, text="Set Media Save Dir", command=self._choose_save_dir,
            width=20,
        ).grid(row=2, column=1, padx=20, pady=20)

        ttk.Button(
            button_frame, text="Back", command=app.show_home, width=32,
        ).grid(row=3, column=0, columnspan=2, padx=20, pady=20)

        # Log display
        log_frame = ttk.LabelFrame(frame, text="Terminal Log", padding=10)
        log_frame.pack(pady=10, fill=BOTH, expand=True)

        log_scroll = Scrollbar(log_frame)
        log_scroll.pack(side=RIGHT, fill=Y)

        app.log_text = Text(
            log_frame, height=8, yscrollcommand=log_scroll.set,
            font=("Consolas", 10), state=NORMAL,
        )
        app.log_text.pack(side=LEFT, fill=BOTH, expand=True)
        log_scroll.config(command=app.log_text.yview)

        # Status bar
        serial_status = "Connected" if app.serial_manager.is_connected() else "Disconnected"
        port_info = app.serial_manager.get_port_info()
        port_name = port_info["port"] if port_info else "None"
        file_status = "Receiving File" if app.file_transfer.receiving_file else "Ready"
        save_dir = os.path.basename(app.file_transfer.save_directory)

        self.status_label = ttk.Label(
            frame,
            text=(
                f"Status: {file_status} | Serial: {serial_status} ({port_name}) "
                f"| Save Dir: {save_dir}"
            ),
            font=("Arial", 10),
        )
        self.status_label.pack(pady=5)

    # ------------------------------------------------------------------
    # Action handlers (identik dengan *_action methods di versi original)
    # ------------------------------------------------------------------

    def _update_status(self, text: str):
        if self.status_label:
            self.status_label.config(text=text)

    def _check_status(self):
        self.app.serial_manager.send_command(CMD_STATUS)
        self._update_status(f"Status: Checking status... ({CMD_STATUS} sent)")
        self.app.log_message("Checking status")

    def _info(self):
        self.app.serial_manager.send_command(CMD_INFO)
        self._update_status(f"Status: Retrieving info... ({CMD_INFO} sent)")
        self.app.log_message("Retrieving info")

    def _start_record(self):
        self.app.serial_manager.send_command(CMD_START_RECORD)
        self._update_status(f"Status: Recording... ({CMD_START_RECORD} sent)")
        self.app.log_message("Recording started")

    def _stop_record(self):
        self.app.serial_manager.send_command(CMD_STOP_RECORD)
        self._update_status(
            f"Status: Recording stopped, expecting JSON... ({CMD_STOP_RECORD} sent)"
        )
        self.app.log_message("Recording stopped - waiting for JSON file")

        # Callback untuk update status label saat JSON diterima
        def _on_json_saved(filename: str):
            self._update_status(f"Status: JSON file received and saved as {filename}")

        json_thread = threading.Thread(
            target=self.app.json_receiver.receive_json,
            kwargs={"on_saved": _on_json_saved},
            daemon=True,
        )
        json_thread.start()
        self.app.log_message("JSON reception thread started...")

    def _process(self):
        self.app.serial_manager.send_command(CMD_PROCESS)
        self._update_status(f"Status: Processing data... ({CMD_PROCESS} sent)")
        self.app.log_message("Processing data")

    def _choose_save_dir(self):
        directory = filedialog.askdirectory(
            title="Choose directory to save received files",
            initialdir=self.app.file_transfer.save_directory,
        )
        if directory:
            self.app.file_transfer.save_directory = directory
            self.app.json_receiver.save_directory = directory
            self.app.log_message(f"Save directory for media files changed to: {directory}")
