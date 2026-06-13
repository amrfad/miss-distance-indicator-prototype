# darat/ui/widgets/radar_widget.py
"""
RadarWidget — Native PySide6 2D Radar Display dengan 3 bidang (XY, XZ, YZ).

Semua bidang menggunakan satu kelas canvas seragam:
- 12 sektor (30° per sektor)
- 4 ring konsentris dengan jarak proporsional
- Label hanya pada 4 arah utama: sumbu positif dan negatif
- Zoom bersama (XY/XZ/YZ sinkron): max_range 20 → 15 → 10 → 5 → 20m
- Event: titik lingkaran kuning dengan label nomor
- Gaya: hijau phosphor militer
"""

import math

from PySide6.QtCore import Qt, QPointF, QSize
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QRadialGradient, QFontMetricsF,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QWidget, QSizePolicy, QVBoxLayout, QHBoxLayout, QTabWidget,
    QPushButton, QLabel,
)

from .mesh_loader import load_plane_mesh


# ── Palet warna radar militer (phosphor green) ─────────────────────────────
_C_BG         = QColor("#060d06")
_C_BG_INNER   = QColor("#0d200d")
_C_GRID       = QColor("#1a4a1a")
_C_GRID_MAJ   = QColor("#236823")
_C_TEXT       = QColor("#33cc33")
_C_TEXT_DIM   = QColor("#1a7a1a")
_C_CROSSHAIR  = QColor("#33cc33")
_C_EVENT      = QColor("#ffff00")
_C_EVENT_OOB  = QColor("#ff6600")

# Range steps untuk zoom (meter)
_RANGE_STEPS  = [5, 10, 15, 20]   # zoom in → index turun, zoom out → naik
_RING_STEP_M  = 5.0                # jarak antar ring selalu 5m
_NUM_SECTORS  = 12

_TAB_STYLE = """
QTabWidget::pane {
    background-color: #060d06;
    border: none;
    border-radius: 0px;
}
QTabBar::tab {
    background-color: #0a1a0a;
    color: #1a7a1a;
    border: 1px solid #1a4a1a;
    border-bottom: none;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
    padding: 4px 14px;
    font-family: 'IBM Plex Mono';
    font-size: 10px;
    font-weight: bold;
}
QTabBar::tab:selected {
    background-color: #123a12;
    color: #33cc33;
    border-color: #33cc33;
}
QTabBar::tab:hover {
    background-color: #0d250d;
    color: #26a026;
}
"""

_BTN_STYLE = """
QPushButton {
    background-color: #0a1a0a;
    border: 1px solid #1a4a1a;
    border-radius: 4px;
    color: #33cc33;
    font-family: 'IBM Plex Mono';
    font-size: 11px;
    font-weight: bold;
    padding: 2px 14px;
    min-width: 36px;
}
QPushButton:hover {
    background-color: #123a12;
    border-color: #33cc33;
}
QPushButton:pressed {
    background-color: #0a250a;
}
QPushButton:disabled {
    color: #1a4a1a;
    border-color: #0f2a0f;
}
"""


# ── Canvas Radar Terpadu ─────────────────────────────────────────────────────

class _RadarCanvas(QWidget):
    """Canvas radar polar seragam untuk satu bidang proyeksi.

    Parameters
    ----------
    horiz_label : str   label sumbu horizontal (mis. "X")
    horiz_key   : str   key dict event untuk sumbu horizontal (mis. "x")
    vert_label  : str   label sumbu vertikal (mis. "Y")
    vert_key    : str   key dict event untuk sumbu vertikal (mis. "y")
    """

    def __init__(self, horiz_label: str, horiz_key: str,
                 vert_label: str, vert_key: str, parent=None):
        super().__init__(parent)
        self.setObjectName("radarCanvas")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(280, 280)

        self._horiz_label = horiz_label
        self._horiz_key   = horiz_key
        self._vert_label  = vert_label
        self._vert_key    = vert_key

        self._events: list[dict] = []
        self._max_range: float   = 20.0   # diatur dari luar via set_range()
        self._vertices, self._faces = load_plane_mesh()

    # ── Public API ─────────────────────────────────────────────────────────

    def set_data(self, events: list[dict]):
        self._events = [e for e in events if e.get("valid", False)]
        self.update()

    def clear(self):
        self._events = []
        self.update()

    def set_range(self, max_range_m: float):
        self._max_range = max_range_m
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(460, 460)

    # ── Geometri ────────────────────────────────────────────────────────────

    def _plot_rect(self) -> tuple[QPointF, float]:
        """Return (center, radius_px) dengan margin untuk label sumbu."""
        w, h = self.width(), self.height()
        margin = 46
        r = (min(w, h) - margin * 2) / 2
        return QPointF(w / 2, h / 2), r

    def _world_to_screen(self, h_val: float, v_val: float,
                         center: QPointF, radius_px: float) -> QPointF:
        """Konversi koordinat dunia → layar.

        Konvensi:
        - Sumbu horizontal positif → kanan
        - Sumbu vertikal positif → atas (y layar dibalik)
        """
        sx = center.x() + (h_val / self._max_range) * radius_px
        sy = center.y() - (v_val / self._max_range) * radius_px
        return QPointF(sx, sy)

    # ── Paint ───────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        center, radius = self._plot_rect()

        self._draw_background(p, center, radius)
        self._draw_rings(p, center, radius)
        self._draw_sectors(p, center, radius)
        self._draw_aircraft_mesh(p, center, radius)
        self._draw_crosshair(p, center)
        self._draw_events(p, center, radius)

        p.end()

    def _draw_background(self, p: QPainter, center: QPointF, radius: float):
        p.fillRect(self.rect(), _C_BG)
        grad = QRadialGradient(center, radius)
        grad.setColorAt(0.0, _C_BG_INNER)
        grad.setColorAt(1.0, _C_BG)
        p.setBrush(QBrush(grad))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(center, radius, radius)

    def _draw_rings(self, p: QPainter, center: QPointF, radius: float):
        """Gambar ring konsentris dengan jarak 5m, hingga max_range."""
        font = QFont("IBM Plex Mono", 7)
        p.setFont(font)

        ring_m = _RING_STEP_M
        while ring_m <= self._max_range + 0.01:
            r_px = (ring_m / self._max_range) * radius
            is_outer = abs(ring_m - self._max_range) < 0.01

            pen = QPen(_C_GRID_MAJ if is_outer else _C_GRID)
            pen.setWidthF(1.2 if is_outer else 0.7)
            pen.setStyle(Qt.PenStyle.SolidLine if is_outer else Qt.PenStyle.DotLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(center, r_px, r_px)

            # Label jarak di arah 45° (kanan atas)
            angle = math.radians(45)
            lx = center.x() + r_px * math.cos(angle) + 2
            ly = center.y() - r_px * math.sin(angle) - 2
            p.setPen(_C_TEXT_DIM)
            p.drawText(QPointF(lx, ly), f"{ring_m:.0f}m")

            ring_m += _RING_STEP_M

    def _draw_sectors(self, p: QPainter, center: QPointF, radius: float):
        """Gambar 12 garis sektor dan label 4 sumbu (+H, -H, +V, -V)."""
        font = QFont("IBM Plex Mono", 8)
        font.setBold(True)
        p.setFont(font)
        fm = QFontMetricsF(font)

        sector_deg = 360.0 / _NUM_SECTORS

        for i in range(_NUM_SECTORS):
            # Sudut: 0° = kanan (+H), 90° = atas (+V), searah jarum jam mundur
            angle_deg = i * sector_deg
            screen_angle = math.radians(angle_deg)  # langsung (Qt: +x=kanan, +y=bawah)

            x_end = center.x() + radius * math.cos(screen_angle)
            y_end = center.y() - radius * math.sin(screen_angle)

            # Tentukan apakah ini sumbu utama (0°/90°/180°/270°)
            is_cardinal = (i % 3 == 0)
            pen = QPen(_C_GRID_MAJ if is_cardinal else _C_GRID)
            pen.setWidthF(0.8 if is_cardinal else 0.5)
            p.setPen(pen)
            p.drawLine(center, QPointF(x_end, y_end))

            # Label hanya pada 4 sumbu utama (0°, 90°, 180°, 270°)
            if i % 3 == 0:
                label_idx = i // 3  # 0=+H, 1=+V, 2=-H, 3=-V (dengan 4 cardinal)
                # Kita punya 4 cardinal: i=0(0°), i=3(90°), i=6(180°), i=9(270°)
                pass

        # Gambar label 4 arah kardinal di luar ring
        label_r = radius + 16
        cardinals = [
            (0,   f"+{self._horiz_label}", _C_TEXT),    # kanan = +H
            (90,  f"+{self._vert_label}",  _C_TEXT),    # atas  = +V
            (180, f"-{self._horiz_label}", _C_TEXT_DIM),# kiri  = -H
            (270, f"-{self._vert_label}",  _C_TEXT_DIM),# bawah = -V
        ]
        for ang_deg, label, color in cardinals:
            ang = math.radians(ang_deg)
            lx = center.x() + label_r * math.cos(ang)
            ly = center.y() - label_r * math.sin(ang)
            bw = fm.horizontalAdvance(label)
            bh = fm.height()
            p.setPen(color)
            p.drawText(QPointF(lx - bw / 2, ly + bh / 4), label)

    def _draw_crosshair(self, p: QPainter, center: QPointF):
        pen = QPen(_C_CROSSHAIR)
        pen.setWidthF(1.0)
        p.setPen(pen)
        s = 5
        p.drawLine(QPointF(center.x() - s, center.y()), QPointF(center.x() + s, center.y()))
        p.drawLine(QPointF(center.x(), center.y() - s), QPointF(center.x(), center.y() + s))

    def _draw_aircraft_mesh(self, p: QPainter, center: QPointF, radius: float):
        """Draw the projected plane mesh wireframe on this 2D canvas."""
        if not self._vertices or not self._faces:
            return

        def get_val(v, key):
            if key == "x":
                return v[0]
            elif key == "y":
                return v[1]
            elif key == "z":
                return v[2]
            return 0.0

        projected_pts = []
        for v in self._vertices:
            h_val = get_val(v, self._horiz_key)
            v_val = get_val(v, self._vert_key)
            sp = self._world_to_screen(h_val, v_val, center, radius)
            projected_pts.append(sp)

        # Draw wireframe faces
        pen = QPen(QColor(_C_CROSSHAIR.red(), _C_CROSSHAIR.green(), _C_CROSSHAIR.blue(), 180))
        pen.setWidthF(0.8)
        p.setPen(pen)

        brush = QBrush(QColor(_C_CROSSHAIR.red(), _C_CROSSHAIR.green(), _C_CROSSHAIR.blue(), 15))
        p.setBrush(brush)

        for face in self._faces:
            poly = QPolygonF([projected_pts[idx] for idx in face])
            p.drawPolygon(poly)

    def _draw_events(self, p: QPainter, center: QPointF, radius: float):
        if not self._events:
            font = QFont("IBM Plex Mono", 10)
            p.setFont(font)
            p.setPen(_C_TEXT_DIM)
            msg = "NO DATA"
            fm = QFontMetricsF(font)
            p.drawText(QPointF(center.x() - fm.horizontalAdvance(msg) / 2,
                               center.y() + radius * 0.15), msg)
            return

        font_ev = QFont("IBM Plex Mono", 7)
        font_ev.setBold(True)
        fm = QFontMetricsF(font_ev)

        for ev in self._events:
            h = ev.get(self._horiz_key, 0.0)
            v = ev.get(self._vert_key,  0.0)
            num = ev.get("event_number", "?")

            # Cek apakah di luar range saat ini
            dist = math.hypot(h, v)
            oob  = dist > self._max_range

            if oob:
                # Clamp ke tepi dengan sedikit margin
                scale = (self._max_range - self._max_range * 0.03) / dist
                h_draw, v_draw = h * scale, v * scale
                color = _C_EVENT_OOB
            else:
                h_draw, v_draw = h, v
                color = _C_EVENT

            sp = self._world_to_screen(h_draw, v_draw, center, radius)

            # Halo glow
            glow = QColor(color)
            glow.setAlpha(50)
            p.setBrush(QBrush(glow))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(sp, 10.0, 10.0)

            # Dot utama
            p.setBrush(QBrush(color))
            p.setPen(QPen(color.lighter(150), 0.8))
            p.drawEllipse(sp, 4.0, 4.0)

            # Label
            p.setFont(font_ev)
            p.setPen(color)
            label = f"E{num}" + ("!" if oob else "")
            p.drawText(QPointF(sp.x() + 6, sp.y() + fm.height() / 4), label)


# ── RadarWidget Kontainer ─────────────────────────────────────────────────────

class RadarWidget(QWidget):
    """Widget radar 2D dengan sub-tab XY / XZ / YZ dan kontrol zoom bersama."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("radarWidget")
        self._range_idx = len(_RANGE_STEPS) - 1   # mulai dari 20m (index terakhir)
        self._events: list[dict] = []
        self._build_ui()

    # ── Build UI ────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(_TAB_STYLE)

        self._canvas_xy = _RadarCanvas("X", "x", "Y", "y")
        self._canvas_xz = _RadarCanvas("X", "x", "Z", "z")
        self._canvas_yz = _RadarCanvas("Y", "y", "Z", "z")

        self._tabs.addTab(self._canvas_xy, "  ◉ XY  ")
        self._tabs.addTab(self._canvas_xz, "  ◈ XZ  ")
        self._tabs.addTab(self._canvas_yz, "  ◈ YZ  ")

        root.addWidget(self._tabs, stretch=1)

        # ── Zoom bar ───────────────────────────────────────────────────────
        zoom_bar = QWidget()
        zoom_bar.setStyleSheet(
            "background-color: #060d06; border-top: 1px solid #1a4a1a;"
        )
        zl = QHBoxLayout(zoom_bar)
        zl.setContentsMargins(8, 3, 8, 5)
        zl.setSpacing(6)

        lbl_range = QLabel("RANGE:")
        lbl_range.setStyleSheet(
            "color: #1a7a1a; font-family: 'IBM Plex Mono'; font-size: 9px; border: none;"
        )
        zl.addWidget(lbl_range)

        self._range_lbl = QLabel(f"{_RANGE_STEPS[self._range_idx]:.0f} m")
        self._range_lbl.setStyleSheet(
            "color: #33cc33; font-family: 'IBM Plex Mono'; font-size: 10px;"
            "font-weight: bold; min-width: 36px; border: none;"
        )
        self._range_lbl.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        zl.addWidget(self._range_lbl)

        zl.addStretch()

        self._btn_zout = QPushButton("−")
        self._btn_zout.setStyleSheet(_BTN_STYLE)
        self._btn_zout.setToolTip("Zoom Out (naikkan range)")
        self._btn_zout.clicked.connect(self._zoom_out)
        zl.addWidget(self._btn_zout)

        self._btn_zin = QPushButton("+")
        self._btn_zin.setStyleSheet(_BTN_STYLE)
        self._btn_zin.setToolTip("Zoom In (turunkan range)")
        self._btn_zin.clicked.connect(self._zoom_in)
        zl.addWidget(self._btn_zin)

        root.addWidget(zoom_bar)

        self._apply_range()

    # ── Zoom logic ──────────────────────────────────────────────────────────

    def _zoom_in(self):
        """Perkecil range (zoom in): 20→15→10→5."""
        if self._range_idx > 0:
            self._range_idx -= 1
            self._apply_range()

    def _zoom_out(self):
        """Perbesar range (zoom out): 5→10→15→20."""
        if self._range_idx < len(_RANGE_STEPS) - 1:
            self._range_idx += 1
            self._apply_range()

    def _apply_range(self):
        max_r = _RANGE_STEPS[self._range_idx]
        self._range_lbl.setText(f"{max_r:.0f} m")
        for canvas in (self._canvas_xy, self._canvas_xz, self._canvas_yz):
            canvas.set_range(max_r)
        # Update tombol state
        self._btn_zin.setEnabled(self._range_idx > 0)
        self._btn_zout.setEnabled(self._range_idx < len(_RANGE_STEPS) - 1)

    # ── Public API ──────────────────────────────────────────────────────────

    def set_data(self, events: list[dict]):
        self._events = events
        for canvas in (self._canvas_xy, self._canvas_xz, self._canvas_yz):
            canvas.set_data(events)

    def clear(self):
        self._events = []
        for canvas in (self._canvas_xy, self._canvas_xz, self._canvas_yz):
            canvas.clear()

    def sizeHint(self) -> QSize:
        return QSize(480, 500)
