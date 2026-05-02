"""
Ground Unit — Main Entry Point
EventGUI bertindak sebagai koordinator tipis yang mendelegasikan logika
ke modul-modul terpisah: FileTransferManager, JsonReceiver, dan Screen classes.
"""

import os
import sys
import datetime
from tkinter import BOTH, Tk, ttk

from .config import BAUD_RATE, BUTTON_STYLES
from .serial_manager import SerialManager
from .file_transfer import FileTransferManager
from .json_receiver import JsonReceiver
from .screens import HomeScreen, CommandScreen, ProcessScreen, VisualizeScreen
from .config_manager import GroundConfigManager
from .config_api import start_ground_api_thread


class EventGUI:
    """
    Koordinator utama aplikasi Ground Unit.

    Tanggung jawab:
    - Setup window Tkinter
    - Inisialisasi dan wiring modul (serial, file_transfer, json_receiver)
    - Navigasi antar screen
    - Shared log_message() yang digunakan oleh semua screen dan modul
    """

    def __init__(self):
        # ---------------------------------------------------------------
        # Window setup
        # ---------------------------------------------------------------
        self.root = Tk()
        self.root.title("Ground Unit")
        self.root.state("zoomed")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Button styles
        style = ttk.Style()
        for style_name, opts in BUTTON_STYLES.items():
            style.configure(style_name, **opts)

        # ---------------------------------------------------------------
        # Shared state
        # ---------------------------------------------------------------
        self.log_text = None          # Set oleh screen yang aktif
        self.log_buffer = []          # Buffer pesan sebelum log_text siap
        self.working_directory = os.getcwd()  # Menggantikan os.chdir()

        # ---------------------------------------------------------------
        # Ground Config Manager + REST API (daemon thread)
        # ---------------------------------------------------------------
        self.ground_config_manager = GroundConfigManager()
        self.ground_config_manager.apply_to_module()
        start_ground_api_thread(self.ground_config_manager, port=5001)

        # ---------------------------------------------------------------
        # Module initialization
        # ---------------------------------------------------------------
        self.serial_manager = SerialManager(baud_rate=BAUD_RATE)

        self.file_transfer = FileTransferManager(
            log_callback=self.log_message,
            save_directory=self.working_directory,
        )

        self.json_receiver = JsonReceiver(
            serial_manager=self.serial_manager,
            file_transfer=self.file_transfer,
            log_callback=self.log_message,
            save_directory=self.working_directory,
        )

        # Wire serial callbacks
        self.serial_manager.set_callbacks(
            on_message=self.log_message,
            on_status=self.log_message,
            on_data=self.file_transfer.process_incoming_data,
        )

        # Connect to serial port
        if os.name == "nt":
            self.serial_manager.detect_and_connect()
        else:
            from .config import LINUX_SERIAL_PORT
            self.serial_manager.connect_to_port(LINUX_SERIAL_PORT)

        # ---------------------------------------------------------------
        # Root frame & initial screen
        # ---------------------------------------------------------------
        self.main_frame = ttk.Frame(self.root, padding=20)
        self.main_frame.pack(fill=BOTH, expand=True)

        self.current_screen = None
        self.show_home()

    # -------------------------------------------------------------------
    # Screen navigation
    # -------------------------------------------------------------------

    def clear_screen(self):
        """Hancurkan semua widget di main_frame dan reset log_text."""
        for widget in self.main_frame.winfo_children():
            widget.destroy()
        self.log_text = None

    def show_home(self):
        self.clear_screen()
        self.current_screen = "home"
        HomeScreen(self).build()

    def show_command(self):
        self.clear_screen()
        self.current_screen = "command"
        CommandScreen(self).build()

    def show_process(self):
        self.clear_screen()
        self.current_screen = "process"
        ProcessScreen(self).build()

    def show_visualize(self):
        self.clear_screen()
        self.current_screen = "visualize"
        VisualizeScreen(self).build()

    # -------------------------------------------------------------------
    # Shared logging
    # -------------------------------------------------------------------

    def log_message(self, message: str):
        """Tulis pesan ke konsol dan ke Text widget jika tersedia."""
        print(message)
        if self.log_text:
            try:
                from tkinter import END
                self.log_text.insert(END, message + "\n")
                self.log_text.see(END)
            except Exception:
                pass
        else:
            self.log_buffer.append(message)

    # -------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------

    def on_closing(self):
        """Bersihkan resource saat window ditutup."""
        try:
            if hasattr(self, "serial_manager"):
                self.serial_manager.disconnect()
            self.root.destroy()
        except Exception as e:
            print(f"Error during cleanup: {e}")
        finally:
            sys.exit(0)

    def run(self):
        """Mulai Tkinter main loop."""
        self.root.mainloop()


def main():
    app = EventGUI()
    app.run()


if __name__ == "__main__":
    main()
