"""
Visualize Screen
Halaman visualisasi 3D dan 2D proyeksi dari hasil TDOA.
"""

import os
import glob
import traceback
from tkinter import BOTH, END, LEFT, NORMAL, RIGHT, Scrollbar, Text, Y, filedialog, ttk, Listbox

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from ..visualize_results import parse_results_file, visualize_3d, visualize_2d_projections


class VisualizeScreen:
    """
    Halaman visualisasi hasil TDOA (3D + 2D projections) dengan notebook tab.
    Menggantikan EventGUI.visualize_page() + visualize_selected_file() +
    change_visualize_directory().
    """

    def __init__(self, app):
        self.app = app
        self.txt_listbox = None
        self.viz_frame_3d = None
        self.viz_frame_2d = None
        self.viz_notebook = None

    def build(self):
        app = self.app
        frame = app.main_frame

        ttk.Label(
            frame, text="VISUALIZATION PAGE", font=("Arial", 24, "bold")
        ).pack(pady=20)

        ttk.Label(
            frame,
            text="Select a results file to visualize 3D positions",
            font=("Arial", 12),
        ).pack(pady=10)

        # Main horizontal container
        main_container = ttk.Frame(frame)
        main_container.pack(fill=BOTH, expand=True, padx=20, pady=10)

        # LEFT: File selection
        left_frame = ttk.Frame(main_container)
        left_frame.pack(side=LEFT, fill=BOTH, padx=(0, 10))

        selection_frame = ttk.LabelFrame(left_frame, text="Results File Selection", padding=20)
        selection_frame.pack(fill=BOTH, expand=True)

        current_dir = app.working_directory
        ttk.Label(
            selection_frame, text="Current Directory:", font=("Arial", 9, "bold")
        ).pack(pady=5, anchor="w")
        ttk.Label(
            selection_frame, text=current_dir, font=("Arial", 8), wraplength=250
        ).pack(pady=2, anchor="w")

        txt_files = sorted(glob.glob(os.path.join(current_dir, "*.txt")))

        ttk.Label(
            selection_frame,
            text=f"\nFound {len(txt_files)} result file(s):",
            font=("Arial", 9, "bold"),
        ).pack(pady=5, anchor="w")

        if txt_files:
            listbox_frame = ttk.Frame(selection_frame)
            listbox_frame.pack(pady=10, fill=BOTH, expand=True)

            scrollbar = Scrollbar(listbox_frame)
            scrollbar.pack(side=RIGHT, fill=Y)

            self.txt_listbox = Listbox(
                listbox_frame, yscrollcommand=scrollbar.set, height=15, font=("Consolas", 9)
            )
            self.txt_listbox.pack(side=LEFT, fill=BOTH, expand=True)
            scrollbar.config(command=self.txt_listbox.yview)

            for file in txt_files:
                file_size = os.path.getsize(file) / 1024
                self.txt_listbox.insert(END, f"{os.path.basename(file)} ({file_size:.2f} KB)")
        else:
            ttk.Label(
                selection_frame, text="No result files found", foreground="red"
            ).pack(pady=10)

        # Buttons
        button_frame = ttk.Frame(selection_frame)
        button_frame.pack(pady=10, fill="x")

        if txt_files:
            ttk.Button(
                button_frame, text="Visualize Selected File",
                command=self._visualize_selected,
            ).pack(fill="x", pady=5)

        ttk.Button(
            button_frame, text="Change Directory",
            command=self._change_directory,
        ).pack(fill="x", pady=5)

        ttk.Button(
            button_frame, text="Back to Home",
            command=app.show_home,
        ).pack(fill="x", pady=5)

        # RIGHT: Visualization canvas with notebook tabs
        right_frame = ttk.Frame(main_container)
        right_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(10, 0))

        self.viz_notebook = ttk.Notebook(right_frame)
        self.viz_notebook.pack(fill=BOTH, expand=True)

        self.viz_frame_3d = ttk.Frame(self.viz_notebook, padding=10)
        self.viz_notebook.add(self.viz_frame_3d, text="3D View")

        ttk.Label(
            self.viz_frame_3d,
            text="Select a file and click 'Visualize Selected File'\nto view 3D plot",
            font=("Arial", 12), justify="center",
        ).pack(expand=True)

        self.viz_frame_2d = ttk.Frame(self.viz_notebook, padding=10)
        self.viz_notebook.add(self.viz_frame_2d, text="2D Projections")

        ttk.Label(
            self.viz_frame_2d,
            text="Select a file and click 'Visualize Selected File'\nto view 2D projections",
            font=("Arial", 12), justify="center",
        ).pack(expand=True)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _visualize_selected(self):
        """Visualisasi file TXT yang dipilih. Identik dengan EventGUI.visualize_selected_file()."""
        app = self.app
        try:
            if not self.txt_listbox:
                return
            selection = self.txt_listbox.curselection()
            if not selection:
                app.log_message("No file selected. Please select a result file first.")
                return

            selected_text = self.txt_listbox.get(selection[0])
            basename = selected_text.split(" (")[0]
            filename = os.path.join(app.working_directory, basename)

            events, mic_positions = parse_results_file(filename)

            if not events:
                app.log_message("No events found in file.")
                return

            valid_events = [e for e in events if e["valid"]]

            # Clear tabs
            for widget in self.viz_frame_3d.winfo_children():
                widget.destroy()
            for widget in self.viz_frame_2d.winfo_children():
                widget.destroy()

            if not valid_events:
                app.log_message("No valid events to visualize.")
                error_msg = (
                    f"⚠ No Valid Events to Visualize\n\n"
                    f"File: {filename}\n"
                    f"Total Events: {len(events)}\n"
                    f"Failed: {len(events)}\n\n"
                    f"All events failed TDOA estimation.\n"
                    f"Please check the quality of recorded data."
                )
                for tab_frame in (self.viz_frame_3d, self.viz_frame_2d):
                    ttk.Label(
                        tab_frame, text=error_msg, font=("Arial", 12),
                        justify="center", foreground="orange",
                    ).pack(expand=True, pady=50)
                return

            # 3D figure
            fig_3d = visualize_3d(events, filename, mic_positions)
            if fig_3d is None:
                app.log_message("Error generating 3D visualization.")
            else:
                canvas_3d = FigureCanvasTkAgg(fig_3d, master=self.viz_frame_3d)
                canvas_3d.draw()
                canvas_3d.get_tk_widget().pack(fill=BOTH, expand=True)
                info_text = (
                    f"Total: {len(events)} | Valid: {len(valid_events)} "
                    f"| Failed: {len(events) - len(valid_events)}"
                )
                ttk.Label(self.viz_frame_3d, text=info_text, font=("Arial", 10)).pack(pady=5)

            # 2D figure
            fig_2d = visualize_2d_projections(events, filename, mic_positions)
            if fig_2d is None:
                app.log_message("Error generating 2D projections.")
            else:
                canvas_2d = FigureCanvasTkAgg(fig_2d, master=self.viz_frame_2d)
                canvas_2d.draw()
                canvas_2d.get_tk_widget().pack(fill=BOTH, expand=True)
                info_text = (
                    f"Total: {len(events)} | Valid: {len(valid_events)} "
                    f"| Failed: {len(events) - len(valid_events)}"
                )
                ttk.Label(self.viz_frame_2d, text=info_text, font=("Arial", 10)).pack(pady=5)

        except Exception as e:
            app.log_message(f"Error visualizing file: {e}")
            app.log_message(f"Traceback: {traceback.format_exc()}")

    def _change_directory(self):
        """Ganti working directory dan refresh layar."""
        app = self.app
        directory = filedialog.askdirectory(
            title="Choose directory containing result files",
            initialdir=app.working_directory,
        )
        if directory:
            app.working_directory = directory
            app.log_message(f"Changed directory to: {directory}")
            app.show_visualize()
