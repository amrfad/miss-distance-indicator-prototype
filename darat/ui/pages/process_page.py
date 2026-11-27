# darat/ui/pages/process_page.py
"""Process Page — TDOA JSON processing dengan dukungan multi-metode SSL."""

import glob
import json
import os
import shutil
import traceback

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QFrame, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QTextEdit, QFileDialog, QMessageBox,
    QComboBox, QGroupBox,
)
from PySide6.QtCore import Signal, Qt, QThread, QObject
from PySide6.QtGui import QColor

from ...localization.process_json_tdoa import process_event_tdoa, save_results_to_file
from ...core.config_manager import get_global_config_manager
from ...localization import ssl_registry


class _ProcessWorker(QObject):
    """Background worker untuk TDOA processing — jangan blok GUI."""

    finished = Signal(str, list)   # (filename, events_results)
    progress = Signal(str)         # log line
    error    = Signal(str)         # error message

    def __init__(self, filename: str, mic_positions: dict, method_key: str):
        super().__init__()
        self._filename    = filename
        self._mic_positions = mic_positions
        self._method_key  = method_key

    def run(self):
        try:
            with open(self._filename, "r") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            self.error.emit(str(exc))
            return

        entry = ssl_registry.get_method(self._method_key)
        method_display = entry.display_name if entry else self._method_key

        self.progress.emit(f"Method    : {method_display}")
        self.progress.emit(f"Session ID: {data.get('session_id', 'N/A')}")
        self.progress.emit(f"Timestamp : {data.get('timestamp', 'N/A')}")
        self.progress.emit(f"Events    : {data.get('event_count', 0)}")
        self.progress.emit("=" * 60)

        events = data.get("events", [])
        results: list[dict] = []
        for event in events:
            num = event.get("event_number", "?")
            self.progress.emit(f"\nEVENT {num}")
            self.progress.emit("─" * 40)

            active_mics = event.get("active_mics")
            excluded_mics = event.get("excluded_mics")
            if active_mics is not None:
                excl_str = f" | excluded: {excluded_mics}" if excluded_mics else ""
                self.progress.emit(f"Active Mics: {len(active_mics)} ({', '.join(active_mics)}){excl_str}")

            pos, cluster_size, clusters_info = process_event_tdoa(
                event, self._mic_positions, method=self._method_key
            )
            results.append({
                "event_number":      num,
                "estimated_position": pos,
                "cluster_size":      cluster_size,
                "clusters_info":     clusters_info,
            })

            if pos is not None:
                self.progress.emit(
                    (f"Position  : [{pos[0]:.3f}, {pos[1]:.3f}] m" if len(pos) == 2 else f"Position  : [{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}] m")
                )
                if cluster_size is not None:
                    self.progress.emit(f"Cluster   : {cluster_size} consistent solutions")
                if clusters_info:
                    for line in clusters_info:
                        if "DEGRADED" in line:
                            self.progress.emit(f"[WARN] {line}")
            else:
                reason = f" ({clusters_info[0]})" if clusters_info else ""
                self.progress.emit(f"Position  : FAILED{reason}")

        self.progress.emit("\n" + "=" * 60)
        self.progress.emit("PROCESSING COMPLETE")
        self.progress.emit("=" * 60)
        self.finished.emit(self._filename, results)


class ProcessPage(QWidget):
    """Process tab: pilih file JSON, pilih metode SSL, dan jalankan estimasi.

    Signals
    -------
    log_message(str, str)  — shared log panel
    results_saved(str)     — path ke *_results.txt (untuk tab Visualize)
    """

    log_message   = Signal(str, str)
    results_saved = Signal(str)

    def __init__(self, working_dir: str = "", parent=None):
        super().__init__(parent)
        self._working_dir  = working_dir or os.getcwd()
        self._custom_folder = ssl_registry.get_custom_folder()
        self._thread: QThread | None = None
        self._build_ui()
        self._refresh_file_list()
        self._refresh_method_combo()

    def set_working_dir(self, path: str):
        self._working_dir = path
        self._dir_label.setText(path)
        self._refresh_file_list()

    def process_file(self, file_path: str):
        """Pilih dan proses file JSON secara otomatis (dipanggil dari CommandPage / tombol PROCESS DATA)."""
        if not file_path or not os.path.exists(file_path):
            return
        directory = os.path.dirname(file_path)
        if directory:
            self.set_working_dir(directory)

        # Cari item di file list dan pilih item tersebut
        for i in range(self._file_list.count()):
            item = self._file_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == file_path:
                self._file_list.setCurrentItem(item)
                break

        # Jalankan pemrosesan TDOA
        self._process_selected()

    # ─────────────────────────────────────────────────────────────────────────
    # Build UI
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel("TDOA JSON PROCESSING")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        root.addWidget(splitter, stretch=1)

        # ── Panel Kiri: file + method selection ──────────────────────────────
        left = QFrame()
        left.setObjectName("card")
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 10, 10, 10)
        ll.setSpacing(8)

        # Directory
        dir_header = QHBoxLayout()
        dir_header.addWidget(QLabel("Directory:"))
        self._dir_label = QLabel(self._working_dir)
        self._dir_label.setObjectName("statusValue")
        self._dir_label.setWordWrap(True)
        dir_header.addWidget(self._dir_label, stretch=1)
        ll.addLayout(dir_header)

        # File list
        self._file_list = QListWidget()
        self._file_list.setAlternatingRowColors(True)
        ll.addWidget(self._file_list, stretch=1)

        self._file_count = QLabel("No JSON files found")
        self._file_count.setObjectName("statusHeading")
        ll.addWidget(self._file_count)

        # Button row — file navigation
        btn_row = QHBoxLayout()
        self._process_btn = QPushButton("PROCESS SELECTED")
        self._process_btn.setObjectName("btnPrimary")
        self._process_btn.clicked.connect(self._process_selected)
        btn_row.addWidget(self._process_btn)

        change_btn = QPushButton("CHANGE DIR")
        change_btn.clicked.connect(self._change_directory)
        btn_row.addWidget(change_btn)

        refresh_btn = QPushButton("REFRESH")
        refresh_btn.setMinimumWidth(70)
        refresh_btn.clicked.connect(self._refresh_file_list)
        btn_row.addWidget(refresh_btn)
        ll.addLayout(btn_row)

        # ── TDOA Method GroupBox ─────────────────────────────────────────────
        method_group = QGroupBox("TDOA Calculation Method")
        mg_layout = QVBoxLayout(method_group)
        mg_layout.setContentsMargins(8, 8, 8, 8)
        mg_layout.setSpacing(6)

        self._method_combo = QComboBox()
        self._method_combo.setToolTip(
            "Select algorithm to estimate sound source position from TDOA data"
        )
        mg_layout.addWidget(self._method_combo)

        method_btn_row = QHBoxLayout()

        refresh_method_btn = QPushButton("Refresh Methods")
        refresh_method_btn.setToolTip("Reload available calculation methods")
        refresh_method_btn.clicked.connect(self._on_refresh_methods)
        method_btn_row.addWidget(refresh_method_btn)

        add_method_btn = QPushButton("Add Custom Method…")
        add_method_btn.setObjectName("btnSave")
        add_method_btn.setToolTip(
            "Add a .py file implementing solve() as a custom SSL method"
        )
        add_method_btn.clicked.connect(self._on_add_custom_method)
        method_btn_row.addWidget(add_method_btn)

        mg_layout.addLayout(method_btn_row)

        self._custom_folder_lbl = QLabel(f"Custom folder: {self._custom_folder}")
        self._custom_folder_lbl.setObjectName("statusValue")
        self._custom_folder_lbl.setWordWrap(True)
        mg_layout.addWidget(self._custom_folder_lbl)

        ll.addWidget(method_group)
        splitter.addWidget(left)

        # ── Panel Kanan: log output ──────────────────────────────────────────
        right = QFrame()
        right.setObjectName("card")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(10, 10, 10, 10)
        rl.setSpacing(6)

        header_row = QHBoxLayout()
        log_title = QLabel("PROCESSING LOG")
        log_title.setObjectName("sectionTitle")
        header_row.addWidget(log_title)
        header_row.addStretch()
        clr_btn = QPushButton("CLEAR")
        clr_btn.clicked.connect(self._clear_log)
        header_row.addWidget(clr_btn)
        rl.addLayout(header_row)

        self._log_area = QTextEdit()
        self._log_area.setObjectName("logConsole")
        self._log_area.setReadOnly(True)
        rl.addWidget(self._log_area, stretch=1)

        self._view_viz_btn = QPushButton("OPEN IN VISUALIZE")
        self._view_viz_btn.setObjectName("btnSave")
        self._view_viz_btn.setVisible(False)
        self._view_viz_btn.clicked.connect(self._open_in_visualize)
        rl.addWidget(self._view_viz_btn)

        splitter.addWidget(right)
        splitter.setSizes([320, 580])

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _refresh_file_list(self):
        self._file_list.clear()
        files = sorted(glob.glob(os.path.join(self._working_dir, "*.json")))
        for path in files:
            size_kb = os.path.getsize(path) / 1024
            item = QListWidgetItem(f"{os.path.basename(path)}  ({size_kb:.1f} KB)")
            item.setData(Qt.ItemDataRole.UserRole, path)
            self._file_list.addItem(item)
        count = len(files)
        self._file_count.setText(f"{count} JSON file{'s' if count != 1 else ''} found")

    def _refresh_method_combo(self):
        """Isi ulang dropdown metode dari registry."""
        self._method_combo.clear()
        methods = ssl_registry.get_available_methods()
        default_key = ssl_registry.get_default_key()
        default_idx = 0
        for i, (key, display) in enumerate(methods):
            source_tag = ""
            entry = ssl_registry.get_method(key)
            if entry and entry.source == "custom":
                source_tag = " [Custom]"
            self._method_combo.addItem(f"{display}{source_tag}", userData=key)
            if key == default_key:
                default_idx = i
        self._method_combo.setCurrentIndex(default_idx)

    def _get_selected_method_key(self) -> str:
        idx = self._method_combo.currentIndex()
        if idx < 0:
            return ssl_registry.get_default_key()
        return self._method_combo.itemData(idx) or ssl_registry.get_default_key()

    def _get_selected_path(self) -> str | None:
        items = self._file_list.selectedItems()
        if not items:
            return None
        return items[0].data(Qt.ItemDataRole.UserRole)

    def _append_log(self, text: str):
        self._log_area.append(text)
        sb = self._log_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear_log(self):
        self._log_area.clear()
        self._view_viz_btn.setVisible(False)

    # ─────────────────────────────────────────────────────────────────────────
    # Slots
    # ─────────────────────────────────────────────────────────────────────────

    def _process_selected(self):
        path = self._get_selected_path()
        if not path:
            QMessageBox.information(self, "No Selection", "Please select a JSON file first.")
            return

        cfg = get_global_config_manager().get_config()
        mic_positions = cfg.get("mic_positions", {})
        method_key = self._get_selected_method_key()

        entry = ssl_registry.get_method(method_key)
        method_display = entry.display_name if entry else method_key

        self._clear_log()
        self._process_btn.setEnabled(False)
        self.log_message.emit(f"Processing: {os.path.basename(path)} [{method_display}]", "INFO")
        self._append_log(f"File      : {path}")
        self._append_log("=" * 60)
        self._append_log("Microphone Positions:")
        for name, pos_dict in mic_positions.items():
            if isinstance(pos_dict, dict):
                self._append_log(
                    f"  {name}: [{pos_dict['x']:.3f}, {pos_dict['y']:.3f}, {pos_dict['z']:.3f}] m"
                )
            else:
                self._append_log(
                    f"  {name}: [{pos_dict[0]:.3f}, {pos_dict[1]:.3f}, {pos_dict[2]:.3f}] m"
                )
        self._append_log("")

        self._current_file = path
        self._thread = QThread(self)
        self._worker = _ProcessWorker(path, mic_positions, method_key)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._append_log)
        self._worker.error.connect(self._on_process_error)
        self._worker.finished.connect(self._on_process_done)
        self._worker.finished.connect(self._thread.quit)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_process_error(self, msg: str):
        self._append_log(f"ERROR: {msg}")
        self.log_message.emit(f"Process error: {msg}", "ERROR")
        self._process_btn.setEnabled(True)

    def _on_process_done(self, filename: str, results: list):
        self._process_btn.setEnabled(True)
        try:
            cfg = get_global_config_manager().get_config()
            mic_positions = cfg.get("mic_positions", {})
            with open(filename) as f:
                data = json.load(f)
            out_file = filename.replace(".json", "_results.txt")
            save_results_to_file(data, results, mic_positions, out_file)
            self._append_log(f"\nResults saved → {out_file}")
            self.log_message.emit(f"Results saved: {os.path.basename(out_file)}", "INFO")
            self._last_results_file = out_file
            self._view_viz_btn.setVisible(True)
        except Exception as exc:
            self._append_log(f"ERROR saving results: {exc}")
            self.log_message.emit(f"Results save error: {exc}", "ERROR")

    def _change_directory(self):
        d = QFileDialog.getExistingDirectory(
            self, "Choose directory containing JSON files", self._working_dir
        )
        if d:
            self.set_working_dir(d)
            self.log_message.emit(f"Working directory: {d}", "INFO")

    def _open_in_visualize(self):
        self.results_saved.emit(getattr(self, "_last_results_file", ""))

    def _on_refresh_methods(self):
        """Reload custom methods from external folder and refresh dropdown."""
        ssl_registry.reload_custom_methods(self._custom_folder)
        self._refresh_method_combo()
        count = len([k for k, e in ssl_registry._registry.items() if e.source == "custom"])
        self.log_message.emit(f"Methods refreshed: {count} custom method(s) loaded.", "INFO")
        self._append_log(f"[INFO] Registry refreshed. {count} custom method(s) available.")

    def _on_add_custom_method(self):
        """
        Open file dialog, copy selected .py file to custom_ssl_methods folder,
        and refresh registry and dropdown.
        """
        src, _ = QFileDialog.getOpenFileName(
            self,
            "Select Custom SSL Method File",
            os.path.expanduser("~"),
            "Python Files (*.py)",
        )
        if not src:
            return

        dst = os.path.join(self._custom_folder, os.path.basename(src))

        # Confirm if file already exists
        if os.path.exists(dst):
            reply = QMessageBox.question(
                self,
                "File Exists",
                f"File '{os.path.basename(src)}' already exists in custom folder.\n"
                "Overwrite with new file?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        try:
            shutil.copy2(src, dst)
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Copy Failed",
                f"Could not copy file:\n{exc}",
            )
            return

        # Reload registry
        ssl_registry.reload_custom_methods(self._custom_folder)
        self._refresh_method_combo()

        self.log_message.emit(
            f"Custom method '{os.path.basename(src)}' added successfully.", "INFO"
        )
        self._append_log(
            f"[INFO] Custom method copied to: {dst}\n"
            f"       Registry refreshed — select method from dropdown."
        )

        QMessageBox.information(
            self,
            "Success",
            f"Custom method '{os.path.basename(src)}' added successfully!\n\n"
            f"Location: {dst}\n\n"
            "Method is now available in dropdown.",
        )
