# darat/ui/pages/system_check_page.py
"""System Check Page — Pre-Flight / On-Demand Hardware & Software Diagnostics."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


_STATUS_STYLES = {
    "PASS": ("#dcfce7", "#166534", "#86efac"),
    "WARN": ("#fef3c7", "#92400e", "#fcd34d"),
    "FAIL": ("#fee2e2", "#991b1b", "#fca5a5"),
    "SKIP": ("#f1f5f9", "#475569", "#cbd5e1"),
}

_BANNER_TEXT = {
    "UNCHECKED": ("NOT CHECKED", "#f1f5f9", "#475569", "#cbd5e1"),
    "RUNNING":   ("RUNNING CHECKS...", "#dbeafe", "#1d4ed8", "#93c5fd"),
    "PASS":      ("READY (PASS)", "#dcfce7", "#166534", "#86efac"),
    "WARN":      ("READY WITH WARNINGS", "#fef3c7", "#92400e", "#fcd34d"),
    "FAIL":      ("NOT READY (FAIL)", "#fee2e2", "#991b1b", "#fca5a5"),
}


class SystemCheckPage(QWidget):
    """Halaman System Check: Auto-Check hardware/software udara + Live Mic Tap Monitor.

    Signals
    -------
    log_message(str, str)            — kirim log ke shared LogPanel
    check_summary_updated(str, str)  — (overall_status, time_str) untuk badge di CommandPage
    """

    log_message = Signal(str, str)
    check_summary_updated = Signal(str, str)

    def __init__(self, rest_client, serial_bridge=None, parent=None):
        super().__init__(parent)
        self._rest = rest_client
        self._serial = serial_bridge

        self._is_running_auto = False
        self._is_monitoring_mic = False
        self._mic_req_in_flight = False
        self._auto_start_ts: float = 0.0
        self._last_overall_status = "UNCHECKED"
        self._last_run_time = ""

        # Timer untuk Live Mic Tap Monitor (sequential polling, tidak menumpuk request)
        self._mic_poll_timer = QTimer(self)
        self._mic_poll_timer.setSingleShot(True)
        self._mic_poll_timer.timeout.connect(self._request_next_mic_sample)

        self._mic_rows: List[Dict[str, Any]] = []

        self._build_ui()
        self._wire_signals()
        self._set_banner("UNCHECKED")

    # ─────────────────────────────────────────────────────────────────────────
    # UI Construction
    # ─────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        # ── Top Banner Card ──────────────────────────────────────────────────
        header_card = QFrame()
        header_card.setObjectName("card")
        hl = QHBoxLayout(header_card)
        hl.setContentsMargins(16, 12, 16, 12)
        hl.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("SYSTEM CHECK")
        title.setObjectName("sectionTitle")
        title_box.addWidget(title)

        self._last_run_label = QLabel("Last run: Never")
        self._last_run_label.setObjectName("statusHeading")
        title_box.addWidget(self._last_run_label)
        hl.addLayout(title_box)

        self._banner_badge = QLabel("NOT CHECKED")
        self._banner_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._banner_badge.setMinimumWidth(180)
        self._banner_badge.setFixedHeight(32)
        hl.addWidget(self._banner_badge)

        hl.addStretch()

        self._run_btn = QPushButton("RUN AUTO CHECK")
        self._run_btn.setObjectName("btnPrimary")
        self._run_btn.setMinimumHeight(38)
        self._run_btn.setMinimumWidth(150)
        self._run_btn.clicked.connect(self._on_run_auto_check)
        hl.addWidget(self._run_btn)

        self._reset_btn = QPushButton("RESET")
        self._reset_btn.setObjectName("btnReset")
        self._reset_btn.setMinimumHeight(38)
        self._reset_btn.setMinimumWidth(90)
        self._reset_btn.clicked.connect(self._on_reset)
        hl.addWidget(self._reset_btn)

        root.addWidget(header_card)

        # ── Main 2-Column Splitter ───────────────────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(6)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, stretch=1)

        # ── Left Column: Scope & Live Mic Monitor Controls ───────────────────
        left_card = QFrame()
        left_card.setObjectName("card")
        left_card.setMinimumWidth(270)
        left_card.setMaximumWidth(330)
        ll = QVBoxLayout(left_card)
        ll.setContentsMargins(14, 14, 14, 14)
        ll.setSpacing(10)

        scope_title = QLabel("CHECK SCOPE")
        scope_title.setObjectName("statusHeading")
        ll.addWidget(scope_title)

        # Preset buttons (sangat berguna saat mic dilepas vs terpasang)
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        btn_no_mic = QPushButton("Tanpa Mic")
        btn_no_mic.setMinimumHeight(28)
        btn_no_mic.setToolTip("Centang semua cek hardware/pipeline kecuali Mic Signal Health")
        btn_no_mic.clicked.connect(self._apply_preset_no_mic)
        preset_row.addWidget(btn_no_mic)

        btn_full = QPushButton("Lengkap (6 Mic)")
        btn_full.setMinimumHeight(28)
        btn_full.setToolTip("Centang seluruh cek termasuk Mic Signal Health (non-SIYI)")
        btn_full.clicked.connect(self._apply_preset_full)
        preset_row.addWidget(btn_full)
        ll.addLayout(preset_row)

        self._chk_os = QCheckBox("Raspi OS & Power Health")
        self._chk_os.setChecked(True)
        ll.addWidget(self._chk_os)

        self._chk_audio_hw = QCheckBox("Audio Device & HW Params")
        self._chk_audio_hw.setChecked(True)
        ll.addWidget(self._chk_audio_hw)

        self._chk_capture = QCheckBox("Capture & Channel Split (2s)")
        self._chk_capture.setChecked(True)
        ll.addWidget(self._chk_capture)

        self._chk_mic = QCheckBox("Mic Signal Health (mic0–mic5)")
        self._chk_mic.setChecked(True)
        self._chk_mic.setToolTip("Uncheck jika mikrofon fisik sedang dilepas")
        ll.addWidget(self._chk_mic)

        self._chk_pipeline = QCheckBox("DSP & TDOA Budget (RTF)")
        self._chk_pipeline.setChecked(True)
        ll.addWidget(self._chk_pipeline)

        self._chk_serial = QCheckBox("Serial / SIYI Link (Opsional)")
        self._chk_serial.setChecked(False)
        self._chk_serial.setToolTip("Cek koneksi serial ke drone via SerialBridge")
        ll.addWidget(self._chk_serial)

        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("color: #dbe4ee; background-color: #dbe4ee; max-height: 1px;")
        ll.addSpacing(4)
        ll.addWidget(divider)
        ll.addSpacing(4)

        mon_title = QLabel("LIVE MIC TAP MONITOR")
        mon_title.setObjectName("statusHeading")
        ll.addWidget(mon_title)

        mon_desc = QLabel(
            "Aktifkan monitor lalu ketuk fisik mic0–mic5 satu per satu "
            "untuk memverifikasi urutan kabel/channel."
        )
        mon_desc.setWordWrap(True)
        mon_desc.setStyleSheet("color: #475569; font-weight: 400; font-size: 11px;")
        ll.addWidget(mon_desc)

        self._mic_mon_btn = QPushButton("START MIC TAP MONITOR")
        self._mic_mon_btn.setObjectName("btnStart")
        self._mic_mon_btn.setMinimumHeight(40)
        self._mic_mon_btn.clicked.connect(self._toggle_mic_monitor)
        ll.addWidget(self._mic_mon_btn)

        self._loudest_label = QLabel("LOUDEST: --")
        self._loudest_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._loudest_label.setMinimumHeight(34)
        self._loudest_label.setStyleSheet(
            "background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; "
            "color: #334155; font-weight: 700; font-size: 12px;"
        )
        ll.addWidget(self._loudest_label)

        ll.addStretch()

        target_info = QLabel(f"Drone API: {self._rest.drone_base}")
        target_info.setObjectName("statusHeading")
        self._target_info_label = target_info
        ll.addWidget(target_info)

        splitter.addWidget(left_card)

        # ── Right Column: Checklist Table + 6-Channel Mic Meter ──────────────
        right_widget = QWidget()
        rl = QVBoxLayout(right_widget)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(10)

        # 1. Checklist Card
        table_card = QFrame()
        table_card.setObjectName("card")
        tl = QVBoxLayout(table_card)
        tl.setContentsMargins(12, 12, 12, 12)
        tl.setSpacing(8)

        tbl_title = QLabel("DIAGNOSTIC CHECKLIST")
        tbl_title.setObjectName("statusHeading")
        tl.addWidget(tbl_title)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["ID", "Check Item", "Status", "Measured Value", "Detail"])
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setWordWrap(True)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(2, 82)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        tl.addWidget(self._table)
        rl.addWidget(table_card, stretch=3)

        # 2. 6-Channel Mic Meter Card
        mic_card = QFrame()
        mic_card.setObjectName("card")
        ml = QVBoxLayout(mic_card)
        ml.setContentsMargins(12, 12, 12, 12)
        ml.setSpacing(6)

        mic_hdr_row = QHBoxLayout()
        mic_title = QLabel("6-CHANNEL MIC METER (mic0 – mic5)")
        mic_title.setObjectName("statusHeading")
        mic_hdr_row.addWidget(mic_title)
        mic_hdr_row.addStretch()
        self._mic_update_label = QLabel("Idle")
        self._mic_update_label.setObjectName("statusHeading")
        mic_hdr_row.addWidget(self._mic_update_label)
        ml.addLayout(mic_hdr_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        for i in range(6):
            lbl_name = QLabel(f"mic{i}")
            lbl_name.setFixedWidth(72)
            lbl_name.setStyleSheet("font-weight: 700; color: #1e293b;")

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setTextVisible(False)
            bar.setFixedHeight(16)
            bar.setStyleSheet(self._bar_stylesheet("#2563eb"))

            lbl_val = QLabel("-- dBFS | Pk -- | --")
            lbl_val.setFixedWidth(210)
            lbl_val.setStyleSheet("font-family: Consolas, monospace; font-size: 11px; color: #334155;")

            lbl_stat = QLabel("--")
            lbl_stat.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl_stat.setFixedWidth(60)
            lbl_stat.setFixedHeight(20)
            lbl_stat.setStyleSheet(
                "background-color: #f1f5f9; color: #64748b; border-radius: 4px; "
                "font-size: 10px; font-weight: 700;"
            )

            grid.addWidget(lbl_name, i, 0)
            grid.addWidget(bar, i, 1)
            grid.addWidget(lbl_val, i, 2)
            grid.addWidget(lbl_stat, i, 3)

            self._mic_rows.append({
                "name": lbl_name,
                "bar": bar,
                "val": lbl_val,
                "stat": lbl_stat,
            })

        grid.setColumnStretch(1, 1)
        ml.addLayout(grid)
        rl.addWidget(mic_card, stretch=2)

        splitter.addWidget(right_widget)
        splitter.setSizes([290, 760])

    def _wire_signals(self):
        self._rest.diagnostics_received.connect(self._on_diagnostics_received)
        self._rest.diagnostics_error.connect(self._on_diagnostics_error)
        self._rest.mic_sample_received.connect(self._on_mic_sample_received)
        self._rest.mic_sample_error.connect(self._on_mic_sample_error)

    # ─────────────────────────────────────────────────────────────────────────
    # Presets & Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _apply_preset_no_mic(self):
        self._chk_os.setChecked(True)
        self._chk_audio_hw.setChecked(True)
        self._chk_capture.setChecked(True)
        self._chk_mic.setChecked(False)
        self._chk_pipeline.setChecked(True)
        self._chk_serial.setChecked(False)

    def _apply_preset_full(self):
        self._chk_os.setChecked(True)
        self._chk_audio_hw.setChecked(True)
        self._chk_capture.setChecked(True)
        self._chk_mic.setChecked(True)
        self._chk_pipeline.setChecked(True)
        self._chk_serial.setChecked(False)

    @staticmethod
    def _bar_stylesheet(chunk_color: str) -> str:
        return (
            "QProgressBar { background-color: #e2e8f0; border: 1px solid #cbd5e1; border-radius: 4px; } "
            f"QProgressBar::chunk {{ background-color: {chunk_color}; border-radius: 3px; }}"
        )

    def _set_banner(self, state: str):
        text, bg, fg, border = _BANNER_TEXT.get(state, _BANNER_TEXT["UNCHECKED"])
        self._banner_badge.setText(text)
        self._banner_badge.setStyleSheet(
            f"background-color: {bg}; color: {fg}; border: 1px solid {border}; "
            "border-radius: 6px; font-weight: 700; font-size: 12px; padding: 4px 12px;"
        )

    def _refresh_target_label(self):
        self._target_info_label.setText(f"Drone API: {self._rest.drone_base}")

    # ─────────────────────────────────────────────────────────────────────────
    # Auto-Check Workflow
    # ─────────────────────────────────────────────────────────────────────────

    def _on_run_auto_check(self):
        if self._is_running_auto:
            return
        if self._is_monitoring_mic:
            self.stop_mic_monitor()

        self._refresh_target_label()
        self._is_running_auto = True
        self._auto_start_ts = time.perf_counter()
        self._run_btn.setEnabled(False)
        self._mic_mon_btn.setEnabled(False)
        self._set_banner("RUNNING")
        self._table.setRowCount(0)

        options = {
            "check_os": self._chk_os.isChecked(),
            "check_audio_hw": self._chk_audio_hw.isChecked(),
            "check_capture": self._chk_capture.isChecked(),
            "check_mic_health": self._chk_mic.isChecked(),
            "check_pipeline": self._chk_pipeline.isChecked(),
            "sample_duration_sec": 2.0,
        }

        self.log_message.emit(
            f"[SYSTEM CHECK] Running diagnostics on {self._rest.drone_base}...",
            "INFO",
        )
        self._rest.run_diagnostics(options=options, timeout=25.0)

    @Slot(dict)
    def _on_diagnostics_received(self, report: dict):
        if not self._is_running_auto:
            return
        self._is_running_auto = False
        self._run_btn.setEnabled(True)
        self._mic_mon_btn.setEnabled(True)

        latency_ms = round((time.perf_counter() - self._auto_start_ts) * 1000.0)
        now_str = datetime.now().strftime("%H:%M:%S")
        self._last_run_time = now_str
        self._last_run_label.setText(f"Last run: {now_str}")

        checks: List[Dict[str, Any]] = []
        # CHK-01: Drone API & State (diukur dari sisi GCS)
        checks.append({
            "id": "CHK-01",
            "name": "Drone API & State",
            "status": "PASS",
            "measured": f"Reachable ({latency_ms} ms total)",
            "detail": f"Terhubung ke {self._rest.drone_base} dalam kondisi IDLE.",
        })

        # CHK-02..CHK-07 dari response drone
        checks.extend(report.get("checks", []))

        # CHK-08: Serial / SIYI Link (opsional, dicek lokal via SerialBridge)
        checks.append(self._evaluate_serial_check())

        # Hitung overall status gabungan
        statuses = [c.get("status", "SKIP") for c in checks]
        if "FAIL" in statuses:
            overall = "FAIL"
        elif "WARN" in statuses:
            overall = "WARN"
        elif "PASS" in statuses:
            overall = "PASS"
        else:
            overall = "UNCHECKED"

        self._last_overall_status = overall
        self._set_banner(overall)
        self._populate_table(checks)

        mic_metrics = report.get("mic_metrics", [])
        if mic_metrics:
            self._update_mic_meters(mic_metrics, report.get("loudest_mic"), live=False)
            self._mic_update_label.setText(f"Snapshot @ {now_str}")

        self.check_summary_updated.emit(overall, now_str)
        lvl = "ERROR" if overall == "FAIL" else ("WARNING" if overall == "WARN" else "INFO")
        self.log_message.emit(f"[SYSTEM CHECK] Completed: {overall} ({now_str})", lvl)

    @Slot(str)
    def _on_diagnostics_error(self, err_msg: str):
        if not self._is_running_auto:
            return
        self._is_running_auto = False
        self._run_btn.setEnabled(True)
        self._mic_mon_btn.setEnabled(True)

        now_str = datetime.now().strftime("%H:%M:%S")
        self._last_run_time = now_str
        self._last_run_label.setText(f"Last run: {now_str}")
        self._last_overall_status = "FAIL"
        self._set_banner("FAIL")

        checks = [
            {
                "id": "CHK-01",
                "name": "Drone API & State",
                "status": "FAIL",
                "measured": "Unreachable / Busy",
                "detail": err_msg,
            },
            self._evaluate_serial_check(),
        ]
        self._populate_table(checks)
        self.check_summary_updated.emit("FAIL", now_str)
        self.log_message.emit(f"[SYSTEM CHECK] Failed: {err_msg}", "ERROR")

    def _evaluate_serial_check(self) -> Dict[str, Any]:
        if not self._chk_serial.isChecked():
            return {
                "id": "CHK-08",
                "name": "Serial / SIYI Link",
                "status": "SKIP",
                "measured": "-",
                "detail": "Dilewati (opsional / non-SIYI).",
            }
        if self._serial is not None and self._serial.is_connected():
            mgr = getattr(self._serial, "manager", None)
            if mgr is not None:
                port = getattr(mgr, "port", "connected")
                detail = "Koneksi serial ke drone aktif."
            else:
                port = "SDR Link"
                detail = "Koneksi SDR Radio Link ke drone aktif."
            return {
                "id": "CHK-08",
                "name": "Serial / SIYI Link",
                "status": "PASS",
                "measured": str(port),
                "detail": detail,
            }
        return {
            "id": "CHK-08",
            "name": "Serial / SIYI Link",
            "status": "FAIL",
            "measured": "Disconnected",
            "detail": "Serial belum terhubung. Hubungkan lewat tab COMMAND.",
        }

    def _populate_table(self, checks: List[Dict[str, Any]]):
        self._table.setRowCount(len(checks))
        bold_font = QFont()
        bold_font.setBold(True)

        for r, item in enumerate(checks):
            cid = str(item.get("id", ""))
            name = str(item.get("name", ""))
            status = str(item.get("status", "SKIP")).upper()
            measured = str(item.get("measured", ""))
            detail = str(item.get("detail", ""))

            it_id = QTableWidgetItem(cid)
            it_id.setFont(bold_font)
            it_id.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

            it_name = QTableWidgetItem(name)
            it_name.setFont(bold_font)

            it_stat = QTableWidgetItem(status)
            it_stat.setFont(bold_font)
            it_stat.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            bg, fg, _ = _STATUS_STYLES.get(status, _STATUS_STYLES["SKIP"])
            it_stat.setBackground(QColor(bg))
            it_stat.setForeground(QColor(fg))

            it_meas = QTableWidgetItem(measured)
            it_det = QTableWidgetItem(detail)

            self._table.setItem(r, 0, it_id)
            self._table.setItem(r, 1, it_name)
            self._table.setItem(r, 2, it_stat)
            self._table.setItem(r, 3, it_meas)
            self._table.setItem(r, 4, it_det)

        self._table.resizeRowsToContents()

    # ─────────────────────────────────────────────────────────────────────────
    # Live Mic Tap Monitor Workflow
    # ─────────────────────────────────────────────────────────────────────────

    def _toggle_mic_monitor(self):
        if self._is_monitoring_mic:
            self.stop_mic_monitor()
        else:
            self._start_mic_monitor()

    def _start_mic_monitor(self):
        if self._is_running_auto:
            return
        self._refresh_target_label()
        self._is_monitoring_mic = True
        self._mic_req_in_flight = False
        self._run_btn.setEnabled(False)
        self._mic_mon_btn.setText("STOP MIC TAP MONITOR")
        self._mic_mon_btn.setObjectName("btnStop")
        self._mic_mon_btn.style().unpolish(self._mic_mon_btn)
        self._mic_mon_btn.style().polish(self._mic_mon_btn)
        self._mic_update_label.setText("Monitoring live...")
        self.log_message.emit("[SYSTEM CHECK] Live Mic Tap Monitor started.", "INFO")
        self._request_next_mic_sample()

    def stop_mic_monitor(self):
        if not self._is_monitoring_mic:
            return
        self._is_monitoring_mic = False
        self._mic_poll_timer.stop()
        self._run_btn.setEnabled(True)
        self._mic_mon_btn.setText("START MIC TAP MONITOR")
        self._mic_mon_btn.setObjectName("btnStart")
        self._mic_mon_btn.style().unpolish(self._mic_mon_btn)
        self._mic_mon_btn.style().polish(self._mic_mon_btn)
        self._mic_update_label.setText("Stopped")
        self.log_message.emit("[SYSTEM CHECK] Live Mic Tap Monitor stopped.", "INFO")

    def _request_next_mic_sample(self):
        if not self._is_monitoring_mic or self._mic_req_in_flight:
            return
        self._mic_req_in_flight = True
        self._rest.fetch_mic_sample(duration_sec=0.4, timeout=6.0)

    @Slot(dict)
    def _on_mic_sample_received(self, sample: dict):
        self._mic_req_in_flight = False
        if not self._is_monitoring_mic:
            return

        mic_metrics = sample.get("mic_metrics", [])
        loudest = sample.get("loudest_mic")
        self._update_mic_meters(mic_metrics, loudest, live=True)
        self._mic_update_label.setText(f"Live @ {datetime.now().strftime('%H:%M:%S')}")

        # Jadwalkan slice berikutnya setelah jeda singkat agar tidak membebani CPU Raspi
        self._mic_poll_timer.start(250)

    @Slot(str)
    def _on_mic_sample_error(self, err_msg: str):
        self._mic_req_in_flight = False
        if not self._is_monitoring_mic:
            return
        self.log_message.emit(f"[SYSTEM CHECK] Mic monitor error: {err_msg}", "ERROR")
        self.stop_mic_monitor()
        self._mic_update_label.setText("Monitor error (stopped)")

    def _update_mic_meters(
        self,
        mic_metrics: List[Dict[str, Any]],
        loudest_mic: Optional[str],
        live: bool = False,
    ):
        for idx, row in enumerate(self._mic_rows):
            if idx >= len(mic_metrics):
                row["bar"].setValue(0)
                row["val"].setText("-- dBFS | Pk -- | --")
                row["stat"].setText("--")
                continue

            m = mic_metrics[idx]
            mic_name = m.get("mic", f"mic{idx}")
            ch_idx = m.get("channel_index", "-")
            rms_db = float(m.get("rms_db", -120.0))
            peak = float(m.get("peak", 0.0))
            dc = float(m.get("dc_offset", 0.0))
            st = str(m.get("status", "OK")).upper()

            # Map -80 dBFS..0 dBFS -> 0..100%
            pct = int(max(0.0, min(100.0, (rms_db + 80.0) * (100.0 / 80.0))))
            is_loudest = live and (loudest_mic == mic_name)

            row["name"].setText(f"{mic_name} (ch{ch_idx})")
            row["bar"].setValue(pct)
            row["val"].setText(f"{rms_db:6.1f} dBFS | Pk {peak:.3f} | DC {dc:+.3f}")

            if is_loudest:
                row["bar"].setStyleSheet(self._bar_stylesheet("#16a34a"))
                row["stat"].setText("PEAK")
                row["stat"].setStyleSheet(
                    "background-color: #dcfce7; color: #166534; border: 1px solid #86efac; "
                    "border-radius: 4px; font-size: 10px; font-weight: 700;"
                )
            elif st in ("DEAD", "MISSING"):
                row["bar"].setStyleSheet(self._bar_stylesheet("#94a3b8"))
                row["stat"].setText(st)
                row["stat"].setStyleSheet(
                    "background-color: #fee2e2; color: #991b1b; border-radius: 4px; "
                    "font-size: 10px; font-weight: 700;"
                )
            elif st == "CLIP":
                row["bar"].setStyleSheet(self._bar_stylesheet("#dc2626"))
                row["stat"].setText("CLIP")
                row["stat"].setStyleSheet(
                    "background-color: #fee2e2; color: #991b1b; border-radius: 4px; "
                    "font-size: 10px; font-weight: 700;"
                )
            elif st == "WARN":
                row["bar"].setStyleSheet(self._bar_stylesheet("#f59e0b"))
                row["stat"].setText("WARN")
                row["stat"].setStyleSheet(
                    "background-color: #fef3c7; color: #92400e; border-radius: 4px; "
                    "font-size: 10px; font-weight: 700;"
                )
            else:
                row["bar"].setStyleSheet(self._bar_stylesheet("#2563eb"))
                row["stat"].setText("OK")
                row["stat"].setStyleSheet(
                    "background-color: #dcfce7; color: #166534; border-radius: 4px; "
                    "font-size: 10px; font-weight: 700;"
                )

        if loudest_mic:
            self._loudest_label.setText(f"LOUDEST: {loudest_mic.upper()}")
            self._loudest_label.setStyleSheet(
                "background-color: #dcfce7; border: 1px solid #86efac; border-radius: 6px; "
                "color: #166534; font-weight: 700; font-size: 13px;"
            )
        else:
            self._loudest_label.setText("LOUDEST: --")
            self._loudest_label.setStyleSheet(
                "background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; "
                "color: #334155; font-weight: 700; font-size: 12px;"
            )

    def _on_reset(self):
        self.stop_mic_monitor()
        self._table.setRowCount(0)
        self._last_overall_status = "UNCHECKED"
        self._last_run_time = ""
        self._last_run_label.setText("Last run: Never")
        self._set_banner("UNCHECKED")
        self._mic_update_label.setText("Idle")
        self._loudest_label.setText("LOUDEST: --")
        self._loudest_label.setStyleSheet(
            "background-color: #f8fafc; border: 1px solid #cbd5e1; border-radius: 6px; "
            "color: #334155; font-weight: 700; font-size: 12px;"
        )
        for i, row in enumerate(self._mic_rows):
            row["name"].setText(f"mic{i}")
            row["bar"].setValue(0)
            row["bar"].setStyleSheet(self._bar_stylesheet("#2563eb"))
            row["val"].setText("-- dBFS | Pk -- | --")
            row["stat"].setText("--")
            row["stat"].setStyleSheet(
                "background-color: #f1f5f9; color: #64748b; border-radius: 4px; "
                "font-size: 10px; font-weight: 700;"
            )
        self.check_summary_updated.emit("UNCHECKED", "")

    def hideEvent(self, event):
        """Otomatis hentikan Live Mic Tap Monitor saat pindah tab agar arecord tidak terkunci."""
        self.stop_mic_monitor()
        super().hideEvent(event)
