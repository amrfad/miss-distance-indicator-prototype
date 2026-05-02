import os
import datetime
import time
import json
import json
import glob
import traceback
import threading
from tkinter import (
    BOTH,
    END,
    LEFT,
    NORMAL,
    RIGHT,
    Scrollbar,
    Text,
    Tk,
    Y,
    filedialog,
    ttk,
    Listbox,
)
from process_json_tdoa import (
    MIC_POSITIONS,
    process_event_tdoa,
    save_results_to_file,
)
from serial_manager import SerialManager
from visualize_results import parse_results_file, visualize_3d, visualize_2d_projections
import matplotlib

matplotlib.use("TkAgg")  # Backend untuk integrasi dengan Tkinter
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


class EventGUI:
    def __init__(self):
        self.root = Tk()
        self.root.title("Ground Unit")
        self.root.state("zoomed")  # Maximized window on Windows

        # Set protocol untuk handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Configure button styles
        style = ttk.Style()
        style.configure("Orange.TButton", foreground="black", background="#FF8C00")
        style.configure("Green.TButton", foreground="black", background="#28A745")
        style.configure("Red.TButton", foreground="black", background="#DC3545")
        style.configure("LightGreen.TButton", foreground="black", background="#90EE90")
        style.configure("Blue.TButton", foreground="black", background="#007BFF")

        # Initialize commands
        self.STANDBY = "STANDBY"
        self.START_RECORD = "START_REC"
        self.STOP_RECORD = "STOP_REC"
        self.STATUS = "STATUS"
        self.INFO = "INFO"
        self.PROCESS = "PROCESS"
        self.TRANSMIT = "TRANSMIT"

        # Initialize log display
        self.log_text = None
        self.log_buffer = []  # Buffer for messages before GUI is ready

        # Initialize serial manager
        self.serial_manager = SerialManager()
        self.serial_manager.set_callbacks(
            on_message=self.log_message,
            on_status=self.log_message,
            on_data=self.process_received_data,
        )

        # File transfer variables
        self.receiving_file = False
        self.file_buffer = bytearray()
        self.expected_file_size = 0
        self.current_file_name = ""
        self.save_directory = os.getcwd()  # Default to current directory

        # JSON reception control
        self.expecting_json = False
        self.json_buffer = bytearray()

        # Connect to serial port
        if os.name == "nt":
            self.serial_manager.detect_and_connect()
        else:
            self.serial_manager.connect_to_port("/dev/ttyUSB0")

        # Create main container
        self.main_frame = ttk.Frame(self.root, padding=20)
        self.main_frame.pack(fill=BOTH, expand=True)

        # Initialize current screen
        self.current_screen = None

        # Start with pre-event screen
        self.show_process_event()

    def clear_screen(self):
        """Clear all widgets from main frame"""
        for widget in self.main_frame.winfo_children():
            widget.destroy()

    def log_message(self, message):
        """Add message to both console and GUI log display"""
        print(message)
        # Check if log_text exists and is still valid
        if hasattr(self, "log_text") and self.log_text:
            try:
                self.log_text.insert(END, message + "\n")
                self.log_text.see(END)
            except Exception:
                # Widget destroyed or not available, just print to console
                pass
        else:
            # Store message in buffer if GUI not ready
            self.log_buffer.append(message)

    def process_received_data(self, raw_data):
        """
        Process received data - handle both text and file transfers
        """
        try:
            # If expecting JSON, route to JSON buffer instead
            if self.expecting_json:
                self.json_buffer.extend(raw_data)
                return

            # Try to decode as text first
            text_data = raw_data.decode("utf-8")

            # Check for file transfer commands
            text_data_stripped = text_data.strip()
            if text_data_stripped.startswith("START\n:"):
                self.handle_file_start(text_data_stripped)
            elif text_data_stripped == "\nEND\n":
                self.handle_file_end()
            elif self.receiving_file:
                # If we're receiving a file, treat as binary data
                self.file_buffer.extend(raw_data)
                progress = (
                    (len(self.file_buffer) / self.expected_file_size * 100)
                    if self.expected_file_size > 0
                    else 0
                )
                file_ext = os.path.splitext(self.current_file_name)[1].lower()
                file_type = (
                    "Video"
                    if file_ext == ".mp4"
                    else (
                        "Audio"
                        if file_ext == ".wav"
                        else ("Text" if file_ext == ".txt" else "JSON")
                    )
                )
                self.log_message(
                    f"{file_type} data received: {len(raw_data)} bytes (Total: {len(self.file_buffer)}/{self.expected_file_size} - {progress:.1f}%)"
                )
            else:
                # Regular text message
                if text_data.strip():
                    self.log_message(f"Received: {text_data.strip()}")

        except UnicodeDecodeError:
            # Handle binary data when receiving files
            if self.receiving_file:
                self.file_buffer.extend(raw_data)
                progress = (
                    (len(self.file_buffer) / self.expected_file_size * 100)
                    if self.expected_file_size > 0
                    else 0
                )
                file_ext = (
                    os.path.splitext(self.current_file_name)[1].lower()
                    if self.current_file_name
                    else ""
                )
                file_type = (
                    "Video"
                    if file_ext == ".mp4"
                    else (
                        "Audio"
                        if file_ext == ".wav"
                        else "Text" if file_ext == ".txt" else "JSON"
                    )
                )
                self.log_message(
                    f"{file_type} data received: {len(raw_data)} bytes (Total: {len(self.file_buffer)}/{self.expected_file_size} - {progress:.1f}%)"
                )
            else:
                self.log_message(f"Received binary data: {len(raw_data)} bytes")

    def handle_file_start(self, command):
        """Handle file transfer start command for mp4, wav, and txt files"""
        # Expected format: "FILE_START:filename.ext:size_in_bytes"
        try:
            parts = command.split(":")
            if len(parts) >= 3:
                self.current_file_name = parts[1]
                self.expected_file_size = int(parts[2])

                # Validate file extension
                file_ext = os.path.splitext(self.current_file_name)[1].lower()
                if file_ext not in [".mp4", ".wav", ".txt", ".json"]:
                    self.log_message(
                        f"Unsupported file type: {file_ext}. Only .mp4, .wav, .txt, .json are supported."
                    )
                    return

                self.file_buffer = bytearray()
                self.receiving_file = True
                file_type = (
                    "Video"
                    if file_ext == ".mp4"
                    else (
                        "Audio"
                        if file_ext == ".wav"
                        else "Text" if file_ext == ".txt" else "JSON"
                    )
                )
                self.log_message(
                    f"Starting {file_type} file reception: {self.current_file_name} ({self.expected_file_size} bytes)"
                )
            else:
                self.log_message("Invalid file start command format")
        except Exception as e:
            self.log_message(f"Error processing file start: {e}")

    def handle_file_end(self):
        """Handle file transfer completion for mp4, wav, and txt files"""
        if self.receiving_file and self.current_file_name:
            try:
                file_path = os.path.join(self.save_directory, self.current_file_name)
                file_ext = os.path.splitext(self.current_file_name)[1].lower()

                # Write file with appropriate mode
                if file_ext == ".txt":
                    # For text files, decode and save as text
                    try:
                        text_content = self.file_buffer.decode("utf-8")
                        with open(file_path, "w", encoding="utf-8") as f:
                            f.write(text_content)
                    except UnicodeDecodeError:
                        # Fallback to binary if decode fails
                        with open(file_path, "wb") as f:
                            f.write(self.file_buffer)
                else:
                    # For mp4 and wav files, save as binary
                    with open(file_path, "wb") as f:
                        f.write(self.file_buffer)

                file_type = (
                    "Video"
                    if file_ext == ".mp4"
                    else (
                        "Audio"
                        if file_ext == ".wav"
                        else "Text" if file_ext == ".txt" else "JSON"
                    )
                )
                self.log_message(
                    f"{file_type} file saved: {file_path} ({len(self.file_buffer)} bytes)"
                )

                # Validate file size
                if len(self.file_buffer) != self.expected_file_size:
                    self.log_message(
                        f"Warning: File size mismatch! Expected: {self.expected_file_size}, Received: {len(self.file_buffer)}"
                    )

                self.receiving_file = False
                self.file_buffer = bytearray()
                self.current_file_name = ""
                self.expected_file_size = 0

            except Exception as e:
                self.log_message(f"Error saving file: {e}")
        else:
            self.log_message("Received FILE_END but not receiving file")

    def receive_json(self):
        """Menerima file JSON melalui serial port"""
        try:
            if not self.serial_manager.is_connected():
                self.log_message("[ERROR] Serial not connected")
                return False

            # Set flag to route incoming data to json_buffer
            self.expecting_json = True
            self.json_buffer = bytearray()

            buffer = b""
            receiving = False
            start_time = None
            end_detected = False
            end_detected_time = None

            timeout_counter = 0
            max_timeout = 1500  # 15 detik (150 x 0.1s) - increased timeout

            self.log_message("Waiting for JSON data...")

            while timeout_counter < max_timeout:
                # Get data from json_buffer (filled by callback)
                if len(self.json_buffer) > 0:
                    data = bytes(self.json_buffer)
                    buffer += data
                    self.json_buffer = bytearray()  # Clear buffer
                    timeout_counter = 0  # Reset timeout jika ada data

                    # Debug: log received data
                    self.log_message(
                        f"[DEBUG] Received {len(data)} bytes, buffer total: {len(buffer)} bytes"
                    )

                    # Cek START marker
                    if not receiving and b"[START]" in buffer:
                        receiving = True
                        start_time = time.time()
                        # Extract data after [START]\n or [START]
                        start_idx = buffer.find(b"[START]\n")
                        # Skip past [START] and any newlines
                        start_idx += len(b"[START]\n")
                        while (
                            start_idx < len(buffer)
                            and buffer[start_idx : start_idx + 1] == b"\n"
                        ):
                            start_idx += 1
                        buffer = buffer[start_idx:]
                        self.log_message(
                            "[RX] [START] marker detected. Receiving JSON..."
                        )
                        self.log_message(
                            f"[DEBUG] Buffer after START (first 100 bytes): {repr(buffer[:100])}"
                        )

                # Check for END marker if receiving
                if receiving and not end_detected:
                    # Check if we have [END] marker with proper context
                    if (
                        b"\n[END]" in buffer
                        or b"[END]\n" in buffer
                        or b"[END]" in buffer
                        or b"\n[END]\n" in buffer
                    ):
                        # Mark END as detected but don't process yet
                        end_detected = True
                        end_detected_time = time.time()
                        self.log_message(
                            "[DEBUG] [END] marker detected, waiting for remaining data..."
                        )

                # Process JSON only after END detected AND waited for additional data
                if end_detected and end_detected_time:
                    # Wait at least 1.0 seconds after END detected to collect any remaining data
                    time_since_end = time.time() - end_detected_time

                    # Also check if no new data arrived in last 0.3 seconds
                    if time_since_end >= 1.0:
                        # Find the END marker position
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

                            # Remove trailing newlines
                            while json_data.endswith(b"\n"):
                                json_data = json_data[:-1]

                            self.log_message(
                                f"[DEBUG] Processing JSON - [END] marker at position {end_idx}"
                            )
                            self.log_message(
                                f"[DEBUG] Total buffer size: {len(buffer)} bytes"
                            )
                            self.log_message(
                                f"[DEBUG] JSON data length: {len(json_data)} bytes"
                            )
                            self.log_message(
                                f"[DEBUG] JSON preview (first 200 bytes): {repr(json_data[:200])}"
                            )
                            self.log_message(
                                f"[DEBUG] JSON preview (last 200 bytes): {repr(json_data[-200:])}"
                            )

                            end_time = time.time()

                            try:
                                # Parse JSON untuk validasi
                                json_str = json_data.decode("utf-8")

                                # Validate JSON structure before parsing
                                # Count braces to ensure complete JSON
                                open_braces = json_str.count("{")
                                close_braces = json_str.count("}")
                                open_brackets = json_str.count("[")
                                close_brackets = json_str.count("]")

                                if open_braces != close_braces:
                                    self.log_message(
                                        f"[ERROR] Unbalanced braces: {{ {open_braces} vs }} {close_braces}"
                                    )
                                    self.log_message(
                                        "[ERROR] JSON incomplete or corrupted"
                                    )
                                    self.log_message(
                                        f"[DEBUG] Checking for data after [END] marker..."
                                    )

                                    # Check if there's more data after [END]
                                    after_end = buffer[end_idx:]
                                    self.log_message(
                                        f"[DEBUG] Data after [END] ({len(after_end)} bytes): {repr(after_end[:200])}"
                                    )

                                    # Save debug file
                                    debug_file = f"debug_json_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                                    with open(debug_file, "wb") as f:
                                        f.write(json_data)
                                    self.log_message(f"Raw data saved to: {debug_file}")

                                    # Save full buffer too
                                    buffer_file = f"debug_buffer_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                                    with open(buffer_file, "wb") as f:
                                        f.write(buffer)
                                    self.log_message(
                                        f"Full buffer saved to: {buffer_file}"
                                    )
                                    return False

                                if open_brackets != close_brackets:
                                    self.log_message(
                                        f"[ERROR] Unbalanced brackets: [ {open_brackets} vs ] {close_brackets}"
                                    )
                                    self.log_message(
                                        "[ERROR] JSON incomplete or corrupted"
                                    )
                                    self.log_message(
                                        f"[DEBUG] Checking for data after [END] marker..."
                                    )

                                    # Check if there's more data after [END]
                                    after_end = buffer[end_idx:]
                                    self.log_message(
                                        f"[DEBUG] Data after [END] ({len(after_end)} bytes): {repr(after_end[:200])}"
                                    )

                                    # Save debug file
                                    debug_file = f"debug_json_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                                    with open(debug_file, "wb") as f:
                                        f.write(json_data)
                                    self.log_message(f"Raw data saved to: {debug_file}")
                                    return False

                                parsed_json = json.loads(json_str)

                                # Simpan ke file dengan timestamp
                                timestamp = datetime.datetime.now().strftime(
                                    "%Y%m%d_%H%M%S"
                                )
                                filename = f"tdoa_{timestamp}.json"
                                file_path = os.path.join(self.save_directory, filename)

                                with open(file_path, "w", encoding="utf-8") as f:
                                    json.dump(
                                        parsed_json, f, indent=2, ensure_ascii=False
                                    )

                                elapsed = end_time - start_time
                                self.log_message(
                                    f"✓ JSON received and saved to '{filename}'"
                                )
                                self.log_message(
                                    f"  Events: {parsed_json.get('event_count', 0)} | Size: {len(json_data)} bytes"
                                )
                                self.log_message(f"  Time: {elapsed:.2f} seconds")

                                if hasattr(self, "status_label"):
                                    self.status_label.config(
                                        text=f"Status: JSON file received and saved as {filename}"
                                    )

                                return True

                            except json.JSONDecodeError as e:
                                self.log_message(f"✗ Invalid JSON format: {e}")
                                # Save raw data for debugging
                                debug_file = f"debug_json_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                                with open(debug_file, "wb") as f:
                                    f.write(json_data)
                                self.log_message(
                                    f"Raw data saved to: {debug_file} for debugging"
                                )
                                return False

                # Only increment timeout if we're receiving and no data came
                if receiving:
                    time.sleep(0.1)
                    timeout_counter += 1
                else:
                    # Wait longer when not yet receiving (waiting for START)
                    time.sleep(0.1)
                    timeout_counter += 1

            if receiving:
                self.log_message(
                    f"[ERROR] Timeout waiting for [END] marker. Received {len(buffer)} bytes so far."
                )
                self.log_message(f"[DEBUG] Buffer content: {repr(buffer[:200])}")
            else:
                self.log_message("[ERROR] Timeout waiting for [START] marker")

            return False

        except Exception as e:
            self.log_message(f"[ERROR] Failed to receive JSON: {e}")
            self.log_message(f"Traceback: {traceback.format_exc()}")
            return False
        finally:
            # Always reset flag when done
            self.expecting_json = False
            self.json_buffer = bytearray()

    def choose_save_directory(self):
        """Open dialog to choose save directory for mp4, wav, and txt files"""
        directory = filedialog.askdirectory(
            title="Choose directory to save received files",
            initialdir=self.save_directory,
        )
        if directory:
            self.save_directory = directory
            self.log_message(f"Save directory for media files changed to: {directory}")

            return True
        return False

    def show_process_event(self):
        """Display pre-event screen"""
        self.clear_screen()
        self.current_screen = "pre-event"

        # Title
        title_label = ttk.Label(
            self.main_frame, text="COMMAND APPLICATION", font=("Arial", 24, "bold")
        )
        title_label.pack(pady=50)

        # Hello World message
        hello_label = ttk.Label(
            self.main_frame, text="WELCOME TO COMMAND APPLICATION!", font=("Arial", 16)
        )
        hello_label.pack(pady=20)

        # Navigation buttons
        nav_frame = ttk.Frame(self.main_frame)
        nav_frame.pack(pady=50)

        ttk.Button(
            nav_frame,
            text="Go to command page",
            command=self.command_page,
            width=20,
        ).pack(side=LEFT, padx=10)

        ttk.Button(
            nav_frame,
            text="Visualize Results",
            command=self.visualize_page,
            width=20,
        ).pack(side=LEFT, padx=10)

        ttk.Button(nav_frame, text="Exit", command=self.on_closing, width=20).pack(
            side=LEFT, padx=10
        )

    def command_page(self):
        """Display command page screen with 4 buttons"""
        self.clear_screen()
        self.current_screen = "command-page"

        # Title
        title_label = ttk.Label(
            self.main_frame, text="COMMAND PAGE", font=("Arial", 24, "bold")
        )
        title_label.pack(pady=20)

        # Event control buttons
        button_frame = ttk.Frame(self.main_frame)
        button_frame.pack(pady=20)

        # Create 6 buttons in a 3x2 grid
        ttk.Button(
            button_frame,
            text="Status",
            command=self.check_status_action,
            width=20,
            style="Orange.TButton",
        ).grid(row=0, column=0, padx=20, pady=20)

        ttk.Button(
            button_frame,
            text="Info",
            command=self.info_action,
            width=20,
            style="Blue.TButton",
        ).grid(row=0, column=1, padx=20, pady=20)

        ttk.Button(
            button_frame,
            text="Start Record",
            command=self.start_record_action,
            width=20,
            style="Green.TButton",
        ).grid(row=1, column=0, padx=20, pady=20)

        ttk.Button(
            button_frame,
            text="Stop Record",
            command=self.stop_record_action,
            width=20,
            style="Red.TButton",
        ).grid(row=1, column=1, padx=20, pady=20)

        ttk.Button(
            button_frame,
            text="Process",
            command=self.process_page,
            width=20,
            style="LightGreen.TButton",
        ).grid(row=2, column=0, padx=20, pady=20)

        ttk.Button(
            button_frame,
            text="Set Media Save Dir",
            command=self.choose_save_directory,
            width=20,
        ).grid(row=2, column=1, padx=20, pady=20)

        ttk.Button(
            button_frame, text="Back", command=self.show_process_event, width=32
        ).grid(row=3, column=0, columnspan=2, padx=20, pady=20)

        # Log display
        log_frame = ttk.LabelFrame(self.main_frame, text="Terminal Log", padding=10)
        log_frame.pack(pady=10, fill=BOTH, expand=True)

        # Create scrollable text widget for log
        log_scroll = Scrollbar(log_frame)
        log_scroll.pack(side=RIGHT, fill=Y)

        self.log_text = Text(
            log_frame,
            height=8,
            yscrollcommand=log_scroll.set,
            font=("Consolas", 10),
            state=NORMAL,
        )
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True)
        log_scroll.config(command=self.log_text.yview)

        # Status label (moved to bottom)
        serial_status = (
            "Connected" if self.serial_manager.is_connected() else "Disconnected"
        )
        port_info = self.serial_manager.get_port_info()
        port_name = port_info["port"] if port_info else "None"
        file_status = "Receiving File" if self.receiving_file else "Ready"
        self.status_label = ttk.Label(
            self.main_frame,
            text=f"Status: {file_status} | Serial: {serial_status} ({port_name}) | Save Dir: {os.path.basename(self.save_directory)}",
            font=("Arial", 10),
        )
        self.status_label.pack(pady=5)

    def process_page(self):
        """Display process_page screen with JSON file selection and processing"""
        self.clear_screen()
        self.current_screen = "process_page"

        # Title
        title_label = ttk.Label(
            self.main_frame, text="PROCESS PAGE", font=("Arial", 24, "bold")
        )
        title_label.pack(pady=30)

        # Instructions
        instruction_label = ttk.Label(
            self.main_frame,
            text="Select a JSON file to process TDOA estimation",
            font=("Arial", 12),
        )
        instruction_label.pack(pady=10)

        # JSON file selection section
        selection_frame = ttk.LabelFrame(
            self.main_frame, text="JSON File Selection", padding=20
        )
        selection_frame.pack(pady=20, padx=50, fill=BOTH)

        # Display current directory and list JSON files
        current_dir = os.getcwd()
        ttk.Label(selection_frame, text=f"Current Directory: {current_dir}").pack(
            pady=5
        )

        json_files = sorted(glob.glob("*.json"))

        if json_files:
            ttk.Label(
                selection_frame, text=f"Found {len(json_files)} JSON file(s):"
            ).pack(pady=5)

            # Create listbox for file selection
            listbox_frame = ttk.Frame(selection_frame)
            listbox_frame.pack(pady=10, fill=BOTH, expand=True)

            scrollbar = Scrollbar(listbox_frame)
            scrollbar.pack(side=RIGHT, fill=Y)

            self.json_listbox = Listbox(
                listbox_frame,
                yscrollcommand=scrollbar.set,
                height=6,
                font=("Consolas", 10),
            )
            self.json_listbox.pack(side=LEFT, fill=BOTH, expand=True)
            scrollbar.config(command=self.json_listbox.yview)

            # Populate listbox
            for file in json_files:
                file_size = os.path.getsize(file) / 1024  # KB
                self.json_listbox.insert(END, f"{file} ({file_size:.2f} KB)")

        else:
            ttk.Label(
                selection_frame, text="No JSON files found in current directory"
            ).pack(pady=10)

        # Horizontal button frame
        button_frame = ttk.Frame(selection_frame)
        button_frame.pack(pady=10, fill="x")

        # Process button
        if json_files:
            ttk.Button(
                button_frame,
                text="Process Selected File",
                command=self.process_selected_json,
                width=20,
            ).pack(side=LEFT, padx=5)

        # Change directory button
        ttk.Button(
            button_frame,
            text="Change Directory",
            command=self.change_json_directory,
            width=20,
        ).pack(side=LEFT, padx=5)

        # Back button in selection frame
        ttk.Button(
            button_frame,
            text="Back",
            command=self.command_page,
            width=20,
        ).pack(side=LEFT, padx=5)

        # Log display
        log_frame = ttk.LabelFrame(self.main_frame, text="Processing Log", padding=10)
        log_frame.pack(pady=20, padx=50, fill=BOTH, expand=True)

        # Create scrollable text widget for log
        log_scroll = Scrollbar(log_frame)
        log_scroll.pack(side=RIGHT, fill=Y)

        self.log_text = Text(
            log_frame,
            height=8,
            yscrollcommand=log_scroll.set,
            font=("Consolas", 10),
            state=NORMAL,
        )
        self.log_text.pack(side=LEFT, fill=BOTH, expand=True)
        log_scroll.config(command=self.log_text.yview)

    # Event action methods
    def standby_action(self):
        """Handle stand-by button click - sends STANDBY command"""
        self.serial_manager.send_command(self.STANDBY)
        self.status_label.config(
            text=f"Status: Stand-by mode activated ({self.STANDBY} sent)"
        )
        self.log_message("Stand-by activated")

    def check_status_action(self):
        """Handle status checking button click - sends STATUS command"""
        self.serial_manager.send_command(self.STATUS)
        self.status_label.config(
            text=f"Status: Checking status... ({self.STATUS} sent)"
        )
        self.log_message("Checking status")

    def info_action(self):
        """Handle info button click - sends INFO command"""
        self.serial_manager.send_command(self.INFO)
        self.status_label.config(text=f"Status: Retrieving info... ({self.INFO} sent)")
        self.log_message("Retrieving info")

    def start_record_action(self):
        """Handle record button click - sends START_REC command"""
        self.serial_manager.send_command(self.START_RECORD)
        self.status_label.config(
            text=f"Status: Recording... ({self.START_RECORD} sent)"
        )
        self.log_message("Recording started")

    def stop_record_action(self):
        """Handle stop record button click - sends STOP_REC command and expects JSON"""
        self.serial_manager.send_command(self.STOP_RECORD)
        self.status_label.config(
            text=f"Status: Recording stopped, expecting JSON... ({self.STOP_RECORD} sent)"
        )
        self.log_message("Recording stopped - waiting for JSON file")

        # Start JSON reception in background thread
        json_thread = threading.Thread(target=self.receive_json, daemon=True)
        json_thread.start()
        self.log_message("JSON reception thread started...")

    def process_action(self):
        """Handle process button click - sends PROCESS command"""
        self.serial_manager.send_command(self.PROCESS)
        self.status_label.config(
            text=f"Status: Processing data... ({self.PROCESS} sent)"
        )
        self.log_message("Processing data")
        # Note: Removed process() call as it blocks GUI thread
        # Use Process Page instead for JSON processing

    def transmit_action(self):
        """Handle transmit button click - sends TRANSMIT command"""
        self.serial_manager.send_command(self.TRANSMIT)
        self.status_label.config(text=f"Status: Transmitting... ({self.TRANSMIT} sent)")
        self.log_message("Transmitting data")

    def process_selected_json(self):
        """Process the selected JSON file from the listbox"""
        try:
            selection = self.json_listbox.curselection()
            if not selection:
                self.log_message("No file selected. Please select a JSON file first.")
                return

            # Get selected file name (remove size info)
            selected_text = self.json_listbox.get(selection[0])
            filename = selected_text.split(" (")[0]

            self.log_message(f"Processing file: {filename}")
            self.log_message("=" * 80)

            # Import necessary modules for processing

            # Load JSON file
            try:
                with open(filename, "r") as f:
                    data = json.load(f)
            except FileNotFoundError:
                self.log_message(f"Error: File '{filename}' not found.")
                return
            except json.JSONDecodeError as e:
                self.log_message(f"Error: Invalid JSON format - {e}")
                return

            # Display file information
            self.log_message(f"Session ID: {data.get('session_id', 'N/A')}")
            self.log_message(f"Timestamp: {data.get('timestamp', 'N/A')}")
            self.log_message(f"Total Events: {data.get('event_count', 0)}")
            self.log_message("=" * 80)

            # Display microphone positions
            self.log_message("\nMicrophone Positions:")
            for mic_name, pos in MIC_POSITIONS.items():
                self.log_message(
                    f"  {mic_name}: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}] m"
                )

            self.log_message("\n" + "=" * 80)
            self.log_message("PROCESSING RESULTS")
            self.log_message("=" * 80)

            # Process each event
            events = data.get("events", [])
            events_results = []

            for event in events:
                event_num = event.get("event_number", "?")
                self.log_message(f"\n{'─'*80}")
                self.log_message(f"EVENT {event_num}")
                self.log_message(f"{'─'*80}")

                estimated_pos, cluster_size, clusters_info = process_event_tdoa(
                    event, MIC_POSITIONS
                )

                events_results.append(
                    {
                        "event_number": event_num,
                        "estimated_position": estimated_pos,
                        "cluster_size": cluster_size,
                        "clusters_info": clusters_info,
                    }
                )

                if estimated_pos is not None:
                    self.log_message(
                        f"Estimated Position: [{estimated_pos[0]:.2f}, {estimated_pos[1]:.2f}, {estimated_pos[2]:.2f}] m"
                    )
                    self.log_message(
                        f"Cluster Size      : {cluster_size} consistent solutions"
                    )
                else:
                    self.log_message("Estimated Position: FAILED (no valid solution)")

            self.log_message("\n" + "=" * 80)
            self.log_message("PROCESSING COMPLETE")
            self.log_message("=" * 80)

            # Simpan hasil ke file
            output_file = filename.replace(".json", "_results.txt")
            save_results_to_file(data, events_results, MIC_POSITIONS, output_file)
            self.log_message(f"\nResults saved to: {output_file}")

        except Exception as e:
            self.log_message(f"Error processing JSON file: {e}")
            self.log_message(f"Traceback: {traceback.format_exc()}")

    def change_json_directory(self):
        """Change directory for JSON file selection"""
        directory = filedialog.askdirectory(
            title="Choose directory containing JSON files", initialdir=os.getcwd()
        )
        if directory:
            os.chdir(directory)
            self.log_message(f"Changed directory to: {directory}")
            # Refresh the post event screen
            self.process_page()

    def visualize_page(self):
        """Display visualization page with TXT file selection"""
        self.clear_screen()
        self.current_screen = "visualize_page"

        # Title
        title_label = ttk.Label(
            self.main_frame, text="VISUALIZATION PAGE", font=("Arial", 24, "bold")
        )
        title_label.pack(pady=20)

        # Instructions
        instruction_label = ttk.Label(
            self.main_frame,
            text="Select a results file to visualize 3D positions",
            font=("Arial", 12),
        )
        instruction_label.pack(pady=10)

        # Main horizontal container
        main_container = ttk.Frame(self.main_frame)
        main_container.pack(fill=BOTH, expand=True, padx=20, pady=10)

        # LEFT SIDE - File selection
        left_frame = ttk.Frame(main_container)
        left_frame.pack(side=LEFT, fill=BOTH, padx=(0, 10))

        # TXT file selection section
        selection_frame = ttk.LabelFrame(
            left_frame, text="Results File Selection", padding=20
        )
        selection_frame.pack(fill=BOTH, expand=True)

        # Display current directory and list TXT files
        current_dir = os.getcwd()
        ttk.Label(
            selection_frame, text=f"Current Directory:", font=("Arial", 9, "bold")
        ).pack(pady=5, anchor="w")

        dir_label = ttk.Label(
            selection_frame, text=current_dir, font=("Arial", 8), wraplength=250
        )
        dir_label.pack(pady=2, anchor="w")

        txt_files = sorted(glob.glob("*.txt"))

        ttk.Label(
            selection_frame,
            text=f"\nFound {len(txt_files)} result file(s):",
            font=("Arial", 9, "bold"),
        ).pack(pady=5, anchor="w")

        if txt_files:
            # Create listbox for file selection
            listbox_frame = ttk.Frame(selection_frame)
            listbox_frame.pack(pady=10, fill=BOTH, expand=True)

            scrollbar = Scrollbar(listbox_frame)
            scrollbar.pack(side=RIGHT, fill=Y)

            self.txt_listbox = Listbox(
                listbox_frame,
                yscrollcommand=scrollbar.set,
                height=15,
                font=("Consolas", 9),
            )
            self.txt_listbox.pack(side=LEFT, fill=BOTH, expand=True)
            scrollbar.config(command=self.txt_listbox.yview)

            # Populate listbox
            for file in txt_files:
                file_size = os.path.getsize(file) / 1024  # KB
                self.txt_listbox.insert(END, f"{file} ({file_size:.2f} KB)")

        else:
            ttk.Label(
                selection_frame, text="No result files found", foreground="red"
            ).pack(pady=10)

        # Button frame (vertical)
        button_frame = ttk.Frame(selection_frame)
        button_frame.pack(pady=10, fill="x")

        # Visualize button
        if txt_files:
            ttk.Button(
                button_frame,
                text="Visualize Selected File",
                command=self.visualize_selected_file,
            ).pack(fill="x", pady=5)

        # Change directory button
        ttk.Button(
            button_frame,
            text="Change Directory",
            command=self.change_visualize_directory,
        ).pack(fill="x", pady=5)

        # Back button
        ttk.Button(
            button_frame,
            text="Back to Home",
            command=self.show_process_event,
        ).pack(fill="x", pady=5)

        # RIGHT SIDE - Visualization canvas with tabs
        right_frame = ttk.Frame(main_container)
        right_frame.pack(side=RIGHT, fill=BOTH, expand=True, padx=(10, 0))

        # Create notebook (tabs) for visualization
        self.viz_notebook = ttk.Notebook(right_frame)
        self.viz_notebook.pack(fill=BOTH, expand=True)

        # Tab 1: 3D Visualization
        self.viz_frame_3d = ttk.Frame(self.viz_notebook, padding=10)
        self.viz_notebook.add(self.viz_frame_3d, text="3D View")

        # Placeholder label for 3D
        self.viz_placeholder_3d = ttk.Label(
            self.viz_frame_3d,
            text="Select a file and click 'Visualize Selected File'\nto view 3D plot",
            font=("Arial", 12),
            justify="center",
        )
        self.viz_placeholder_3d.pack(expand=True)

        # Tab 2: 2D Projections
        self.viz_frame_2d = ttk.Frame(self.viz_notebook, padding=10)
        self.viz_notebook.add(self.viz_frame_2d, text="2D Projections")

        # Placeholder label for 2D
        self.viz_placeholder_2d = ttk.Label(
            self.viz_frame_2d,
            text="Select a file and click 'Visualize Selected File'\nto view 2D projections",
            font=("Arial", 12),
            justify="center",
        )
        self.viz_placeholder_2d.pack(expand=True)

    def visualize_selected_file(self):
        """Visualize the selected TXT file"""
        try:
            selection = self.txt_listbox.curselection()
            if not selection:
                self.log_message("No file selected. Please select a result file first.")
                return

            # Get selected file name (remove size info)
            selected_text = self.txt_listbox.get(selection[0])
            filename = selected_text.split(" (")[0]

            # Parse file menggunakan fungsi dari visualize_results.py
            events, mic_positions = parse_results_file(filename)

            if not events:
                self.log_message("No events found in file.")
                return

            # Filter valid events
            valid_events = [e for e in events if e["valid"]]

            # Clear previous visualizations in both tabs
            for widget in self.viz_frame_3d.winfo_children():
                widget.destroy()
            for widget in self.viz_frame_2d.winfo_children():
                widget.destroy()

            if not valid_events:
                self.log_message("No valid events to visualize.")
                # Show message in both tabs
                error_label_3d = ttk.Label(
                    self.viz_frame_3d,
                    text=f"⚠ No Valid Events to Visualize\n\n"
                    f"File: {filename}\n"
                    f"Total Events: {len(events)}\n"
                    f"Failed: {len(events)}\n\n"
                    f"All events failed TDOA estimation.\n"
                    f"Please check the quality of recorded data.",
                    font=("Arial", 12),
                    justify="center",
                    foreground="orange",
                )
                error_label_3d.pack(expand=True, pady=50)

                error_label_2d = ttk.Label(
                    self.viz_frame_2d,
                    text=f"⚠ No Valid Events to Visualize\n\n"
                    f"File: {filename}\n"
                    f"Total Events: {len(events)}\n"
                    f"Failed: {len(events)}\n\n"
                    f"All events failed TDOA estimation.\n"
                    f"Please check the quality of recorded data.",
                    font=("Arial", 12),
                    justify="center",
                    foreground="orange",
                )
                error_label_2d.pack(expand=True, pady=50)
                return

            # Generate 3D figure
            fig_3d = visualize_3d(events, filename, mic_positions)

            if fig_3d is None:
                self.log_message("Error generating 3D visualization.")
            else:
                # Embed 3D in Tkinter
                canvas_3d = FigureCanvasTkAgg(fig_3d, master=self.viz_frame_3d)
                canvas_3d.draw()
                canvas_3d.get_tk_widget().pack(fill=BOTH, expand=True)

                # Info message for 3D
                info_text = f"Total: {len(events)} | Valid: {len(valid_events)} | Failed: {len(events) - len(valid_events)}"
                ttk.Label(self.viz_frame_3d, text=info_text, font=("Arial", 10)).pack(
                    pady=5
                )

            # Generate 2D projections figure
            fig_2d = visualize_2d_projections(events, filename, mic_positions)

            if fig_2d is None:
                self.log_message("Error generating 2D projections.")
            else:
                # Embed 2D in Tkinter
                canvas_2d = FigureCanvasTkAgg(fig_2d, master=self.viz_frame_2d)
                canvas_2d.draw()
                canvas_2d.get_tk_widget().pack(fill=BOTH, expand=True)

                # Info message for 2D
                info_text = f"Total: {len(events)} | Valid: {len(valid_events)} | Failed: {len(events) - len(valid_events)}"
                ttk.Label(self.viz_frame_2d, text=info_text, font=("Arial", 10)).pack(
                    pady=5
                )

        except Exception as e:
            self.log_message(f"Error visualizing file: {e}")
            self.log_message(f"Traceback: {traceback.format_exc()}")

    def change_visualize_directory(self):
        """Change directory for visualization file selection"""
        directory = filedialog.askdirectory(
            title="Choose directory containing result files", initialdir=os.getcwd()
        )
        if directory:
            os.chdir(directory)
            self.log_message(f"Changed directory to: {directory}")
            # Refresh the visualize page
            self.visualize_page()

    def on_closing(self):
        """Handle window close event dengan cleanup yang proper"""
        try:
            # Stop serial connection
            if hasattr(self, "serial_manager"):
                self.serial_manager.disconnect()

            # Destroy root window
            self.root.destroy()

            # Force exit untuk memastikan semua threads terminated
            import sys

            sys.exit(0)
        except Exception as e:
            print(f"Error during cleanup: {e}")
            import sys

            sys.exit(0)

    def run(self):
        """Start the GUI main loop"""
        self.root.mainloop()


def main():
    app = EventGUI()
    app.run()


if __name__ == "__main__":
    main()
