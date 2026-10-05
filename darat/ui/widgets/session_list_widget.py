"""
session_list_widget.py — Widget Tabel Daftar Sesi Kalibrasi.

Menampilkan daftar sesi rekaman kalibrasi yang terkumpul, status validitas data,
dan aksi penghapusan sesi yang tidak diinginkan oleh pengguna.
"""

from typing import List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...localization.calibration_engine import CalibrationSession


class SessionListWidget(QWidget):
    """
    Widget penampil dan pengelola daftar sesi observasi kalibrasi mikrofon.
    """

    session_removed = Signal(int)
    sessions_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._sessions: List[CalibrationSession] = []
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Header Info & Badge
        header_layout = QHBoxLayout()
        self._title_label = QLabel("DAFTAR SESI TERKUMPUL (0 sesi)")
        self._title_label.setObjectName("sectionTitle")
        header_layout.addWidget(self._title_label)

        header_layout.addStretch()

        self._clear_btn = QPushButton("Bersihkan Semua")
        self._clear_btn.setObjectName("btnGhost")
        self._clear_btn.setFixedHeight(26)
        self._clear_btn.clicked.connect(self.clear_sessions)
        header_layout.addWidget(self._clear_btn)

        layout.addLayout(header_layout)

        # Table Widget
        self._table = QTableWidget(0, 5)
        self._table.setObjectName("sessionTable")
        self._table.setHorizontalHeaderLabels([
            "#", "Koordinat Sumber (x, y, z)", "Events", "Status", "Aksi"
        ])
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        # Header sizing
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)

        layout.addWidget(self._table, stretch=1)

        # Status / recommendation label
        self._info_label = QLabel("⚠ Belum ada sesi rekaman. Masukkan koordinat dan mulai rekam.")
        self._info_label.setObjectName("statusHeading")
        layout.addWidget(self._info_label)

        self._update_summary()

    def add_session(self, session: CalibrationSession):
        """Menambahkan satu sesi observasi ke tabel."""
        self._sessions.append(session)
        self._refresh_table()
        self.sessions_changed.emit()

    def remove_session(self, row_idx: int):
        """Menghapus sesi pada indeks tertentu."""
        if 0 <= row_idx < len(self._sessions):
            self._sessions.pop(row_idx)
            self._refresh_table()
            self.session_removed.emit(row_idx)
            self.sessions_changed.emit()

    def clear_sessions(self):
        """Menghapus seluruh sesi."""
        if not self._sessions:
            return
        self._sessions.clear()
        self._refresh_table()
        self.sessions_changed.emit()

    def get_sessions(self) -> List[CalibrationSession]:
        """Mengembalikan salinan seluruh sesi."""
        return list(self._sessions)

    def get_valid_sessions(self) -> List[CalibrationSession]:
        """Mengembalikan sesi yang valid saja (event > 0)."""
        return [s for s in self._sessions if s.is_valid]

    def session_count(self) -> int:
        return len(self._sessions)

    def valid_session_count(self) -> int:
        return len(self.get_valid_sessions())

    def _refresh_table(self):
        """Merender ulang isi tabel."""
        self._table.setRowCount(len(self._sessions))

        for row, s in enumerate(self._sessions):
            # Kolom 0: #
            item_no = QTableWidgetItem(str(row + 1))
            item_no.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 0, item_no)

            # Kolom 1: Koordinat Sumber (x, y, z)
            coord_str = f"({s.source_pos[0]:+.3f}, {s.source_pos[1]:+.3f}, {s.source_pos[2]:+.3f}) m"
            item_coord = QTableWidgetItem(coord_str)
            item_coord.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
            self._table.setItem(row, 1, item_coord)

            # Kolom 2: Events
            item_events = QTableWidgetItem(str(s.n_events))
            item_events.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 2, item_events)

            # Kolom 3: Status
            if s.is_valid:
                item_status = QTableWidgetItem("✓ Valid")
                item_status.setForeground(Qt.GlobalColor.darkGreen)
            else:
                item_status = QTableWidgetItem("⚠ 0 event")
                item_status.setForeground(Qt.GlobalColor.darkYellow)
            item_status.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, 3, item_status)

            # Kolom 4: Tombol Hapus [✕]
            del_btn = QPushButton("✕")
            del_btn.setToolTip("Hapus sesi ini dari perhitungan")
            del_btn.setFixedSize(30, 24)
            del_btn.setStyleSheet(
                "QPushButton { color: #dc2626; font-weight: bold; border: 1px solid #fca5a5; "
                "border-radius: 3px; background-color: #fef2f2; } "
                "QPushButton:hover { background-color: #fee2e2; border-color: #dc2626; }"
            )
            # Menggunakan default arg r=row agar closure menangkap nilai row saat iterasi
            del_btn.clicked.connect(lambda checked=False, r=row: self.remove_session(r))

            cell_widget = QWidget()
            cell_layout = QHBoxLayout(cell_widget)
            cell_layout.setContentsMargins(4, 2, 4, 2)
            cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cell_layout.addWidget(del_btn)
            self._table.setCellWidget(row, 4, cell_widget)

        self._update_summary()

    def _update_summary(self):
        total = len(self._sessions)
        valid = sum(1 for s in self._sessions if s.is_valid)

        self._title_label.setText(f"DAFTAR SESI TERKUMPUL ({total} sesi)")
        self._clear_btn.setEnabled(total > 0)

        if total == 0:
            self._info_label.setText("⚠ Belum ada sesi rekaman. Masukkan koordinat dan mulai rekam.")
            self._info_label.setStyleSheet("color: #64748b; font-weight: 500;")
        elif valid < 8:
            self._info_label.setText(
                f"⚠ Disarankan minimal 8 sesi untuk akurasi optimal. "
                f"Saat ini: {total} sesi ({valid} valid)."
            )
            self._info_label.setStyleSheet("color: #d97706; font-weight: 600;")
        else:
            self._info_label.setText(
                f"✓ Data mencukupi: {total} sesi ({valid} valid). Siap melakukan optimasi."
            )
            self._info_label.setStyleSheet("color: #16a34a; font-weight: 600;")
