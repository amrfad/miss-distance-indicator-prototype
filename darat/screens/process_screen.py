"""
Process Screen
Halaman pemilihan dan pemrosesan file JSON TDOA.
"""

import os
import glob
import json
import traceback
from tkinter import BOTH, END, LEFT, NORMAL, RIGHT, Scrollbar, Text, Y, filedialog, ttk, Listbox

from ..process_json_tdoa import MIC_POSITIONS, process_event_tdoa, save_results_to_file


class ProcessScreen:
    """
    Halaman untuk memilih file JSON dari direktori dan memproses TDOA.
    Menggantikan EventGUI.process_page() + process_selected_json() + change_json_directory().
    """

    def __init__(self, app):
        self.app = app
        self.json_listbox = None  # Di-set oleh build()

    def build(self):
        app = self.app
        frame = app.main_frame

        ttk.Label(frame, text="PROCESS PAGE", font=("Arial", 24, "bold")).pack(pady=30)

        ttk.Label(
            frame,
            text="Select a JSON file to process TDOA estimation",
            font=("Arial", 12),
        ).pack(pady=10)

        # JSON file selection
        selection_frame = ttk.LabelFrame(frame, text="JSON File Selection", padding=20)
        selection_frame.pack(pady=20, padx=50, fill=BOTH)

        current_dir = app.working_directory
        ttk.Label(selection_frame, text=f"Current Directory: {current_dir}").pack(pady=5)

        json_files = sorted(glob.glob(os.path.join(current_dir, "*.json")))

        if json_files:
            ttk.Label(
                selection_frame, text=f"Found {len(json_files)} JSON file(s):"
            ).pack(pady=5)

            listbox_frame = ttk.Frame(selection_frame)
            listbox_frame.pack(pady=10, fill=BOTH, expand=True)

            scrollbar = Scrollbar(listbox_frame)
            scrollbar.pack(side=RIGHT, fill=Y)

            self.json_listbox = Listbox(
                listbox_frame, yscrollcommand=scrollbar.set, height=6, font=("Consolas", 10)
            )
            self.json_listbox.pack(side=LEFT, fill=BOTH, expand=True)
            scrollbar.config(command=self.json_listbox.yview)

            for file in json_files:
                file_size = os.path.getsize(file) / 1024
                self.json_listbox.insert(END, f"{os.path.basename(file)} ({file_size:.2f} KB)")
        else:
            ttk.Label(
                selection_frame, text="No JSON files found in current directory"
            ).pack(pady=10)

        # Buttons
        button_frame = ttk.Frame(selection_frame)
        button_frame.pack(pady=10, fill="x")

        if json_files:
            ttk.Button(
                button_frame, text="Process Selected File",
                command=self._process_selected, width=20,
            ).pack(side=LEFT, padx=5)

        ttk.Button(
            button_frame, text="Change Directory",
            command=self._change_directory, width=20,
        ).pack(side=LEFT, padx=5)

        ttk.Button(
            button_frame, text="Back",
            command=app.show_command, width=20,
        ).pack(side=LEFT, padx=5)

        # Log display
        log_frame = ttk.LabelFrame(frame, text="Processing Log", padding=10)
        log_frame.pack(pady=20, padx=50, fill=BOTH, expand=True)

        log_scroll = Scrollbar(log_frame)
        log_scroll.pack(side=RIGHT, fill=Y)

        app.log_text = Text(
            log_frame, height=8, yscrollcommand=log_scroll.set,
            font=("Consolas", 10), state=NORMAL,
        )
        app.log_text.pack(side=LEFT, fill=BOTH, expand=True)
        log_scroll.config(command=app.log_text.yview)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _process_selected(self):
        """Proses file JSON yang dipilih. Identik dengan EventGUI.process_selected_json()."""
        app = self.app
        try:
            if not self.json_listbox:
                return
            selection = self.json_listbox.curselection()
            if not selection:
                app.log_message("No file selected. Please select a JSON file first.")
                return

            # Ambil nama file (hilangkan size info)
            selected_text = self.json_listbox.get(selection[0])
            basename = selected_text.split(" (")[0]
            filename = os.path.join(app.working_directory, basename)

            app.log_message(f"Processing file: {filename}")
            app.log_message("=" * 80)

            try:
                with open(filename, "r") as f:
                    data = json.load(f)
            except FileNotFoundError:
                app.log_message(f"Error: File '{filename}' not found.")
                return
            except json.JSONDecodeError as e:
                app.log_message(f"Error: Invalid JSON format - {e}")
                return

            app.log_message(f"Session ID: {data.get('session_id', 'N/A')}")
            app.log_message(f"Timestamp: {data.get('timestamp', 'N/A')}")
            app.log_message(f"Total Events: {data.get('event_count', 0)}")
            app.log_message("=" * 80)

            app.log_message("\nMicrophone Positions:")
            for mic_name, pos in MIC_POSITIONS.items():
                app.log_message(f"  {mic_name}: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}] m")

            app.log_message("\n" + "=" * 80)
            app.log_message("PROCESSING RESULTS")
            app.log_message("=" * 80)

            events = data.get("events", [])
            events_results = []

            for event in events:
                event_num = event.get("event_number", "?")
                app.log_message(f"\n{'─'*80}")
                app.log_message(f"EVENT {event_num}")
                app.log_message(f"{'─'*80}")

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
                    app.log_message(
                        f"Estimated Position: [{estimated_pos[0]:.2f}, "
                        f"{estimated_pos[1]:.2f}, {estimated_pos[2]:.2f}] m"
                    )
                    app.log_message(f"Cluster Size      : {cluster_size} consistent solutions")
                else:
                    app.log_message("Estimated Position: FAILED (no valid solution)")

            app.log_message("\n" + "=" * 80)
            app.log_message("PROCESSING COMPLETE")
            app.log_message("=" * 80)

            output_file = filename.replace(".json", "_results.txt")
            save_results_to_file(data, events_results, MIC_POSITIONS, output_file)
            app.log_message(f"\nResults saved to: {output_file}")

        except Exception as e:
            app.log_message(f"Error processing JSON file: {e}")
            app.log_message(f"Traceback: {traceback.format_exc()}")

    def _change_directory(self):
        """Ganti working directory dan refresh layar."""
        app = self.app
        directory = filedialog.askdirectory(
            title="Choose directory containing JSON files",
            initialdir=app.working_directory,
        )
        if directory:
            app.working_directory = directory
            app.log_message(f"Changed directory to: {directory}")
            app.show_process()
