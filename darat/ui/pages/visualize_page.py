# darat/ui/pages/visualize_page.py
"""Visualize Page — Native PySide6 Tactical 2D Radar (XY Plane) & Telemetry HUD.

Menampilkan visualisasi 2D bidang horizontal (XY) berbasis radar polar taktis:
- Radar polar cincin konsentris (range rings) & 12 sektor arah kardinal (N/S/E/W).
- Titik kejadian (Miss Distance event points) dengan garis vektor radial ke pusat target (0,0).
- Visualisasi seragam titik event & ringkasan statistik telemetri.
- Siluet 2D pesawat tampak atas dan letak 6 mikrofon fisik (toggleable).
- HUD Telemetry Panel & Event Table di sebelah KANAN radar secara horizontal.
- Sinkronisasi dua arah (klik baris tabel <-> sorotan blip radar).
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

from ..widgets.radar_2d_widget import Radar2DWidget
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

        # ── KIRI: File selection ─────────────────────────────────────────
        left = QFrame()
        left.setObjectName("card")
        left.setFixedWidth(240)
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

        # ── KANAN: Radar 2D (kiri) & Telemetry/Tabel (kanan) ──────────────
        viz_splitter = QSplitter(Qt.Orientation.Horizontal)
        viz_splitter.setHandleWidth(4)
        viz_splitter.setChildrenCollapsible(False)

        # 1. Canvas Radar 2D Taktis
        radar_container = QFrame()
        radar_container.setObjectName("card")
        radar_layout = QVBoxLayout(radar_container)
        radar_layout.setContentsMargins(6, 6, 6, 6)
        radar_layout.setSpacing(4)

        self._radar = Radar2DWidget()
        self._radar.event_selected.connect(self._on_radar_event_selected)
        radar_layout.addWidget(self._radar)
        viz_splitter.addWidget(radar_container)

        # 2. Panel Telemetri & Tabel Event (di sebelah KANAN radar)
        telemetry_panel = QFrame()
        telemetry_panel.setObjectName("card")
        telemetry_panel.setMinimumWidth(330)
        tl = QVBoxLayout(telemetry_panel)
        tl.setContentsMargins(8, 8, 8, 8)
        tl.setSpacing(8)

        panel_title = QLabel("TACTICAL TELEMETRY")
        panel_title.setStyleSheet(
            "color: #33cc33; font-family: 'IBM Plex Mono'; font-weight: bold; font-size: 11px;"
        )
        tl.addWidget(panel_title)

        # Telemetry Stat Cards
        chip_style = (
            "background-color: #0d200d; border: 1px solid #1a4a1a; border-radius: 4px; "
            "padding: 5px 8px; font-family: 'IBM Plex Mono'; font-size: 10px; font-weight: bold;"
        )

        stat_row1 = QHBoxLayout()
        stat_row1.setSpacing(6)
        self._chip_total = QLabel("TOTAL: --")
        self._chip_total.setStyleSheet(chip_style + " color: #88cc88;")
        stat_row1.addWidget(self._chip_total)

        self._chip_valid = QLabel("VALID: --")
        self._chip_valid.setStyleSheet(chip_style + " color: #33cc33;")
        stat_row1.addWidget(self._chip_valid)

        self._chip_failed = QLabel("FAILED: --")
        self._chip_failed.setStyleSheet(chip_style + " color: #cc6633;")
        stat_row1.addWidget(self._chip_failed)
        tl.addLayout(stat_row1)

        # Tabel Event Telemetry (Hanya metrik 2D)
        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels([
            "Event", "X (m)", "Y (m)", "Miss Dist (m)", "Status"
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
            "font-weight: bold; font-size: 9px; border: 1px solid #1a4a1a; padding: 4px; }"
        )
        self._table.itemSelectionChanged.connect(self._on_table_selection_changed)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        tl.addWidget(self._table, stretch=1)

        # Petunjuk di bawah tabel
        hint_lbl = QLabel("Hint: Klik baris tabel untuk menyorot event di radar.")
        hint_lbl.setStyleSheet(
            "color: #1a7a1a; font-family: 'IBM Plex Mono'; font-size: 9px; border: none;"
        )
        tl.addWidget(hint_lbl)

        viz_splitter.addWidget(telemetry_panel)
        viz_splitter.setSizes([560, 380])

        main_splitter.addWidget(viz_splitter)
        main_splitter.setSizes([240, 940])

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

        # 2. Update Metric Chips
        self._chip_total.setText(f"TOTAL: {len(events)}")
        self._chip_valid.setText(f"VALID: {len(valid)}")
        self._chip_failed.setText(f"FAILED: {failed_count}")

        # 3. Isi Tabel Event (5 kolom 2D murni)
        self._table.blockSignals(True)
        self._table.setRowCount(len(events))

        mono_font = QFont("IBM Plex Mono", 9)

        for row, ev in enumerate(events):
            num = ev.get("event_number", row + 1)
            is_valid = ev.get("valid", False)

            if is_valid:
                x = float(ev.get("x", 0.0))
                y = float(ev.get("y", 0.0))
                r_miss = math.hypot(x, y)

                col_texts = [
                    f"E{num}",
                    f"{x:+.3f}",
                    f"{y:+.3f}",
                    f"{r_miss:.3f}",
                    "VALID",
                ]
            else:
                col_texts = [f"E{num}", "—", "—", "—", "FAILED"]

            for col, text in enumerate(col_texts):
                item = QTableWidgetItem(text)
                item.setFont(mono_font)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

                if is_valid:
                    item.setForeground(QColor("#88ee88"))
                else:
                    item.setForeground(QColor("#ff7733"))

                self._table.setItem(row, col, item)

        self._table.blockSignals(False)

        self.log_message.emit(
            f"Visualization updated: {name} ({len(valid)} valid events)",
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
