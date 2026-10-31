# darat/ui/pages/visualize_page.py
"""Visualize Page — Native PySide6 Tactical 2D Radar (XY Plane) & Telemetry HUD.

Menggantikan visualisasi isometrik 3D dengan tampilan 2D bidang horizontal (XY)
berbasis radar polar taktis yang seragam, intuitif, dan responsif:
- Radar polar cincin konsentris (range rings) & 12 sektor arah kardinal (N/S/E/W).
- Titik kejadian (Miss Distance event points) dengan garis vektor radial ke pusat target (0,0).
- Penandaan khusus untuk kejadian dengan jarak luput terdekat (Point of Closest Approach / PCA).
- Siluet 2D pesawat tampak atas dan letak 6 mikrofon fisik (toggleable).
- HUD Telemetry Card: Ringkasan PCA, Clock Bearing, Total Events, Valid/Failed.
- Tabel Telemetry Event interaktif dengan penyorotan dua arah (klik baris tabel <-> blip radar).
"""

import glob
import math
import os
from typing import List, Dict, Any, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QFrame, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QMessageBox, QTableWidget, QTableWidgetItem,
    QHeaderView,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont, QColor

from ..widgets.radar_2d_widget import Radar2DWidget, _calc_clock_bearing
from ...visualize_results import parse_results_file


class VisualizePage(QWidget):
    """Visualize tab: tampilan radar polar 2D taktis (XY) dan tabel telemetri event.

    Signals
    -------
    log_message(str, str)   — shared log panel (pesan, level)
    """

    log_message = Signal(str, str)

    def __init__(self, working_dir: str = "", parent=None):
        super().__init__(parent)
        self._working_dir = working_dir or os.getcwd()
        self._events_cache: List[Dict[str, Any]] = []
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

        title = QLabel("TDOA POSITION VISUALIZATION (2D TACTICAL XY)")
        title.setObjectName("sectionTitle")
        root.addWidget(title)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setHandleWidth(4)
        root.addWidget(main_splitter, stretch=1)

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
        self._file_list.currentItemChanged.connect(self._on_file_selection_changed)
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

        main_splitter.addWidget(left)

        # ── RIGHT: visualisasi 2D & Telemetry HUD ─────────────────────────
        right = QFrame()
        right.setObjectName("card")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 6, 6, 6)
        rl.setSpacing(6)

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setHandleWidth(4)
        right_splitter.setChildrenCollapsible(False)

        # 1. Canvas Radar 2D Taktis
        self._radar = Radar2DWidget()
        self._radar.event_selected.connect(self._on_radar_event_selected)
        right_splitter.addWidget(self._radar)

        # 2. Panel Telemetri & Event Table
        telemetry_panel = QFrame()
        telemetry_panel.setStyleSheet(
            "background-color: #060d06; border: 1px solid #1a4a1a; border-radius: 6px;"
        )
        tl = QVBoxLayout(telemetry_panel)
        tl.setContentsMargins(8, 8, 8, 8)
        tl.setSpacing(6)

        # Telemetry Stat Bar / Metric Chips
        metric_row = QHBoxLayout()
        metric_row.setSpacing(8)

        chip_style = (
            "background-color: #0d200d; border: 1px solid #1a4a1a; border-radius: 4px; "
            "padding: 4px 8px; font-family: 'IBM Plex Mono'; font-size: 10px; font-weight: bold;"
        )

        self._chip_total = QLabel("TOTAL: --")
        self._chip_total.setStyleSheet(chip_style + " color: #88cc88;")
        metric_row.addWidget(self._chip_total)

        self._chip_valid = QLabel("VALID: --")
        self._chip_valid.setStyleSheet(chip_style + " color: #33cc33;")
        metric_row.addWidget(self._chip_valid)

        self._chip_failed = QLabel("FAILED: --")
        self._chip_failed.setStyleSheet(chip_style + " color: #cc6633;")
        metric_row.addWidget(self._chip_failed)

        self._chip_pca = QLabel("PCA: --")
        self._chip_pca.setStyleSheet(
            chip_style + " color: #ff3333; border-color: #aa2222; background-color: #200d0d;"
        )
        metric_row.addWidget(self._chip_pca)

        self._chip_bearing = QLabel("BEARING: --")
        self._chip_bearing.setStyleSheet(chip_style + " color: #33bbff;")
        metric_row.addWidget(self._chip_bearing)

        metric_row.addStretch()
        tl.addLayout(metric_row)

        # Tabel Event Telemetry
        self._table = QTableWidget()
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels([
            "Event", "X (m)", "Y (m)", "Z (m)", "Miss 2D (m)", "Miss 3D (m)", "Bearing", "Status"
        ])
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setStyleSheet(
            "QTableWidget { background-color: #071107; alternate-background-color: #0b1a0b; "
            "color: #99dd99; gridline-color: #143514; font-family: 'IBM Plex Mono'; font-size: 10px; "
            "border: 1px solid #1a4a1a; selection-background-color: #1a4d2e; selection-color: #ffffff; } "
            "QHeaderView::section { background-color: #0d200d; color: #33cc33; font-family: 'IBM Plex Mono'; "
            "font-weight: bold; font-size: 9px; border: 1px solid #1a4a1a; padding: 3px; }"
        )
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(7, QHeaderView.ResizeMode.ResizeToContents)

        right_splitter.addWidget(telemetry_panel)
        right_splitter.setSizes([460, 200])

        rl.addWidget(right_splitter)
        tl.addWidget(self._table, stretch=1)

        main_splitter.addWidget(right)
        main_splitter.setSizes([260, 920])

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

    def _get_selected_path(self) -> Optional[str]:
        items = self._file_list.selectedItems()
        return items[0].data(Qt.ItemDataRole.UserRole) if items else None

    def _clear_telemetry(self):
        self._chip_total.setText("TOTAL: --")
        self._chip_valid.setText("VALID: --")
        self._chip_failed.setText("FAILED: --")
        self._chip_pca.setText("PCA: --")
        self._chip_bearing.setText("BEARING: --")
        self._table.setRowCount(0)
        self._events_cache = []

    # ── Slots ─────────────────────────────────────────────────────────────

    def _on_file_selection_changed(self, current, _previous):
        if current is not None:
            self._visualize_selected()

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
            self._radar.clear()
            self._clear_telemetry()
            return

        self._events_cache = events
        valid = [e for e in events if e.get("valid", False)]
        failed_count = len(events) - len(valid)

        if not valid:
            self._radar.clear()
            self._clear_telemetry()
            self._chip_total.setText(f"TOTAL: {len(events)}")
            self._chip_valid.setText("VALID: 0")
            self._chip_failed.setText(f"FAILED: {failed_count}")
            self.log_message.emit("No valid events to visualize", "WARNING")
            return

        name = os.path.basename(path)

        # 1. Update Radar 2D
        self._radar.set_data(events, mic_positions)
        self._radar.auto_fit()

        # 2. Hitung Metrik & PCA (Point of Closest Approach)
        pca_ev = min(valid, key=lambda e: math.hypot(e.get("x", 0.0), e.get("y", 0.0), e.get("z", 0.0)))
        pca_num = pca_ev.get("event_number", "?")
        pca_x = float(pca_ev.get("x", 0.0))
        pca_y = float(pca_ev.get("y", 0.0))
        pca_z = float(pca_ev.get("z", 0.0))
        pca_r2d = math.hypot(pca_x, pca_y)
        pca_r3d = math.hypot(pca_r2d, pca_z)
        pca_clock, pca_deg = _calc_clock_bearing(pca_x, pca_y)

        # 3. Update Metric Chips
        self._chip_total.setText(f"TOTAL: {len(events)}")
        self._chip_valid.setText(f"VALID: {len(valid)}")
        self._chip_failed.setText(f"FAILED: {failed_count}")
        self._chip_pca.setText(f"PCA: {pca_r2d:.2f}m (E{pca_num})")
        self._chip_bearing.setText(f"BEARING: {pca_clock} ({pca_deg:.0f}°)")

        # 4. Isi Tabel Event
        self._table.blockSignals(True)
        self._table.setRowCount(len(events))

        mono_font = QFont("IBM Plex Mono", 9)

        for row, ev in enumerate(events):
            num = ev.get("event_number", row + 1)
            is_valid = ev.get("valid", False)
            is_pca = (num == pca_num and is_valid)

            if is_valid:
                x = float(ev.get("x", 0.0))
                y = float(ev.get("y", 0.0))
                z = float(ev.get("z", 0.0))
                r2d = math.hypot(x, y)
                r3d = math.hypot(r2d, z)
                clock, deg = _calc_clock_bearing(x, y)

                col_texts = [
                    f"E{num}",
                    f"{x:+.3f}",
                    f"{y:+.3f}",
                    f"{z:+.3f}",
                    f"{r2d:.3f}",
                    f"{r3d:.3f}",
                    f"{clock} ({deg:.0f}°)",
                    "VALID [PCA]" if is_pca else "VALID",
                ]
            else:
                col_texts = [f"E{num}", "—", "—", "—", "—", "—", "—", "FAILED"]

            for col, text in enumerate(col_texts):
                item = QTableWidgetItem(text)
                item.setFont(mono_font)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                # Custom color coding
                if is_pca:
                    item.setForeground(QColor("#ff5555"))
                elif is_valid:
                    item.setForeground(QColor("#88ee88"))
                else:
                    item.setForeground(QColor("#ff7733"))

                self._table.setItem(row, col, item)

        self._table.blockSignals(False)

        self.log_message.emit(
            f"Visualization updated: {name} ({len(valid)} valid events, PCA: {pca_r2d:.2f}m @ E{pca_num})",
            "INFO"
        )

    def _on_table_selection_changed(self):
        """Saat user memilih baris di tabel, sorot titik event pada radar 2D."""
        selected_rows = self._table.selectionModel().selectedRows()
        if not selected_rows or not self._events_cache:
            self._radar.highlight_event(None)
            return

        row = selected_rows[0].row()
        if 0 <= row < len(self._events_cache):
            ev = self._events_cache[row]
            num = ev.get("event_number")
            self._radar.highlight_event(num)

    def _on_radar_event_selected(self, event_num: int):
        """Saat user mengklik event di radar, pilih baris terkait di tabel."""
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item and item.text() == f"E{event_num}":
                self._table.blockSignals(True)
                self._table.selectRow(row)
                self._table.scrollToItem(item)
                self._table.blockSignals(False)
                break

    def _change_directory(self):
        from PySide6.QtWidgets import QFileDialog
        d = QFileDialog.getExistingDirectory(
            self, "Choose directory containing result files", self._working_dir
        )
        if d:
            self.set_working_dir(d)
            self.log_message.emit(f"Visualize directory: {d}", "INFO")
