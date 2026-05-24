# darat/ui/pages/visualize_page.py
"""Visualize Page — Native PySide6 radar (2D) + tactical isometric (3D) display.

Menggantikan implementasi berbasis Matplotlib dengan widget QPainter native.
Parser data tetap menggunakan parse_results_file() dari visualize_results.py.
"""

import glob
import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QFrame, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QTabWidget, QMessageBox,
)
from PySide6.QtCore import Signal, Qt

from ..widgets.radar_widget import RadarWidget
from ..widgets.tactical_3d_widget import Tactical3DWidget
from ...visualize_results import parse_results_file


class VisualizePage(QWidget):
    """Visualize tab: tampilan radar polar 2D dan spike-map isometrik 3D.

    Signals
    -------
    log_message(str, str)   — shared log panel
    """

    log_message = Signal(str, str)

    def __init__(self, working_dir: str = "", parent=None):
        super().__init__(parent)
        self._working_dir = working_dir or os.getcwd()
        self._build_ui()
        self._refresh_file_list()

    def set_working_dir(self, path: str):
        self._working_dir = path
        self._dir_label.setText(path)
        self._refresh_file_list()

    def highlight_file(self, path: str):
        """Auto-select a results file (called from ProcessPage via dashboard)."""
        for i in range(self._file_list.count()):
            item = self._file_list.item(i)
            if item.data(Qt.ItemDataRole.UserRole) == path:
                self._file_list.setCurrentItem(item)
                break

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        title = QLabel("TDOA POSITION VISUALIZATION")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)
        root.addWidget(splitter, stretch=1)

        # ── LEFT: file selection ─────────────────────────────────────────
        left = QFrame()
        left.setObjectName("card")
        left.setFixedWidth(260)
        ll = QVBoxLayout(left)
        ll.setContentsMargins(10, 10, 10, 10)
        ll.setSpacing(8)

        ll.addWidget(QLabel("Directory:"))
        self._dir_label = QLabel(self._working_dir)
        self._dir_label.setObjectName("statusValue")
        self._dir_label.setWordWrap(True)
        ll.addWidget(self._dir_label)

        self._file_list = QListWidget()
        self._file_list.setAlternatingRowColors(True)
        ll.addWidget(self._file_list, stretch=1)

        self._file_count = QLabel("No result files found")
        self._file_count.setObjectName("statusHeading")
        ll.addWidget(self._file_count)

        viz_btn = QPushButton("▶  VISUALIZE SELECTED")
        viz_btn.setObjectName("btnPrimary")
        viz_btn.clicked.connect(self._visualize_selected)
        ll.addWidget(viz_btn)

        change_btn = QPushButton("📁  CHANGE DIR")
        change_btn.clicked.connect(self._change_directory)
        ll.addWidget(change_btn)

        refresh_btn = QPushButton("↻  REFRESH LIST")
        refresh_btn.clicked.connect(self._refresh_file_list)
        ll.addWidget(refresh_btn)

        splitter.addWidget(left)

        # ── RIGHT: plot area ─────────────────────────────────────────────
        right = QFrame()
        right.setObjectName("card")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(8, 8, 8, 8)
        rl.setSpacing(4)

        self._plot_tabs = QTabWidget()

        # Widget visualisasi native
        self._canvas_3d = Tactical3DWidget()
        self._canvas_2d = RadarWidget()

        self._plot_tabs.addTab(self._canvas_3d, "  ◈ 3D TACTICAL  ")
        self._plot_tabs.addTab(self._canvas_2d, "  ◉ 2D RADAR  ")
        rl.addWidget(self._plot_tabs)

        self._info_label = QLabel("")
        self._info_label.setObjectName("statusHeading")
        self._info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rl.addWidget(self._info_label)

        splitter.addWidget(right)
        splitter.setSizes([260, 900])

    # ── Helpers ──────────────────────────────────────────────────────────

    def _refresh_file_list(self):
        self._file_list.clear()
        files = sorted(glob.glob(os.path.join(self._working_dir, "*.txt")))
        for path in files:
            size_kb = os.path.getsize(path) / 1024
            item = QListWidgetItem(
                f"{os.path.basename(path)}  ({size_kb:.1f} KB)"
            )
            item.setData(Qt.ItemDataRole.UserRole, path)
            self._file_list.addItem(item)
        count = len(files)
        self._file_count.setText(
            f"{count} result file{'s' if count != 1 else ''} found"
        )

    def _get_selected_path(self) -> str | None:
        items = self._file_list.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    # ── Slots ─────────────────────────────────────────────────────────────

    def _visualize_selected(self):
        path = self._get_selected_path()
        if not path:
            QMessageBox.information(self, "No Selection", "Please select a results file first.")
            return

        try:
            events, mic_positions = parse_results_file(path)
        except Exception as exc:
            self.log_message.emit(f"Parse error: {exc}", "ERROR")
            return

        if not events:
            self.log_message.emit("No events found in file", "WARNING")
            return

        valid = [e for e in events if e.get("valid", False)]
        if not valid:
            self._canvas_3d.clear()
            self._canvas_2d.clear()
            self._info_label.setText(
                f"⚠ No valid events | Total: {len(events)} | All FAILED"
            )
            self.log_message.emit("No valid events to visualize", "WARNING")
            return

        name = os.path.basename(path)

        # Kirim data ke kedua widget native
        self._canvas_3d.set_data(events)
        self._canvas_2d.set_data(events)

        self._info_label.setText(
            f"Total: {len(events)}  |  Valid: {len(valid)}  |  Failed: {len(events) - len(valid)}"
        )
        self.log_message.emit(
            f"Visualization updated: {name}  ({len(valid)} valid events)", "INFO"
        )

    def _change_directory(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(
            self, "Choose directory containing result files", self._working_dir
        )
        if d:
            self.set_working_dir(d)
            self.log_message.emit(f"Visualize directory: {d}", "INFO")
