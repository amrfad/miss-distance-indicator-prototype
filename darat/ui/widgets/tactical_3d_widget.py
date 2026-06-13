# darat/ui/widgets/tactical_3d_widget.py
"""
Tactical3DWidget — Native PySide6 Isometric Spike-Map Display.

Perbaikan v2:
- Scale diperbesar (fill lebih banyak canvas)
- Rotasi 3 sumbu: Yaw (Z-axis), Pitch (X-axis), Roll (Y-axis)
  → Menggunakan matriks rotasi 3D agar perspektif benar-benar berubah
- Tampilan default: sudut pandang taktis (yaw=30°, pitch=25°)

Koordinat: X=timur(+), Y=utara(+), Z=altitude(+)
"""

import math

from PySide6.QtCore import Qt, QPointF, QSize
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QPolygonF, QFontMetricsF,
)
from PySide6.QtWidgets import (
    QWidget, QSizePolicy, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGridLayout,
)

from .mesh_loader import load_plane_mesh


# ── Palet warna ─────────────────────────────────────────────────────────────
_C_BG         = QColor("#060d06")
_C_GRID       = QColor("#1a4a1a")
_C_GRID_MAJ   = QColor("#236823")
_C_TEXT       = QColor("#33cc33")
_C_TEXT_DIM   = QColor("#1a7a1a")
_C_AXIS_X     = QColor("#cc3333")
_C_AXIS_Y     = QColor("#33cc33")
_C_AXIS_Z     = QColor("#3399ff")
_C_EVENT_DOT  = QColor("#ffff00")
_C_SPIKE      = QColor("#ffcc00")
_C_OOB        = QColor("#ff6600")
_C_ACFT       = QColor("#33cc33")

_RANGE_STEPS  = [5, 10, 15, 20]
_MAX_Z_M      = 15.0

_BTN_STYLE = """
QPushButton {
    background-color: #0a1a0a;
    border: 1px solid #1a4a1a;
    border-radius: 4px;
    color: #33cc33;
    font-family: 'IBM Plex Mono';
    font-size: 9px;
    font-weight: bold;
    padding: 3px 8px;
    min-width: 64px;
}
QPushButton:hover {
    background-color: #123a12;
    border-color: #33cc33;
}
QPushButton:pressed {
    background-color: #0a250a;
}
"""


def _rotate_point(x: float, y: float, z: float,
                  yaw: float, pitch: float, roll: float) -> tuple[float, float, float]:
    """Rotasi 3D menggunakan sudut Euler (derajat): Yaw (Z), Pitch (X), Roll (Y).

    Urutan rotasi: Yaw → Pitch → Roll
    """
    # Konversi ke radian
    ya = math.radians(yaw)
    pa = math.radians(pitch)
    ra = math.radians(roll)

    # Yaw (rotasi di sumbu Z)
    x1 = x * math.cos(ya) - y * math.sin(ya)
    y1 = x * math.sin(ya) + y * math.cos(ya)
    z1 = z

    # Pitch (rotasi di sumbu X)
    x2 = x1
    y2 = y1 * math.cos(pa) - z1 * math.sin(pa)
    z2 = y1 * math.sin(pa) + z1 * math.cos(pa)

    # Roll (rotasi di sumbu Y)
    x3 = x2 * math.cos(ra) + z2 * math.sin(ra)
    y3 = y2
    z3 = -x2 * math.sin(ra) + z2 * math.cos(ra)

    return x3, y3, z3


class _IsoCanvas(QWidget):
    """Canvas QPainter untuk isometric spike-map."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tactical3DCanvas")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(300, 300)
        self._events: list[dict] = []

        # Sudut rotasi default — perspektif taktis dari atas-depan
        self._yaw   = 30.0    # rotasi horizontal
        self._pitch = 25.0    # elevasi dari bidang datar
        self._roll  = 0.0     # roll (biasanya 0)
        self._vertices, self._faces = load_plane_mesh()
        self._max_range = 20.0    # default range

    def set_range(self, max_range_m: float):
        self._max_range = max_range_m
        self.update()

    def set_data(self, events: list[dict]):
        self._events = [e for e in events if e.get("valid", False)]
        self.update()

    def clear(self):
        self._events = []
        self.update()

    def rotate_yaw(self, delta: float):
        self._yaw = (self._yaw + delta) % 360
        self.update()

    def rotate_pitch(self, delta: float):
        self._pitch = max(-89.0, min(89.0, self._pitch + delta))
        self.update()

    def rotate_roll(self, delta: float):
        self._roll = (self._roll + delta) % 360
        self.update()

    def reset_view(self):
        self._yaw, self._pitch, self._roll = 30.0, 25.0, 0.0
        self.update()

    # ── Proyeksi ────────────────────────────────────────────────────────────

    def _project(self, x: float, y: float, z: float) -> QPointF:
        """Rotasi 3D lalu proyeksi ortogonal ke layar."""
        cx, cy, scale = self._get_params()
        rx, ry, rz = _rotate_point(x, y, z, self._yaw, self._pitch, self._roll)
        # Proyeksi ortogonal sederhana: ambil rx dan rz sebagai screen x,y
        sx = cx + rx * scale
        sy = cy - rz * scale
        return QPointF(sx, sy)

    def _get_params(self) -> tuple[float, float, float]:
        """Return (cx, cy, scale)."""
        w, h = self.width(), self.height()
        cx = w * 0.5
        cy = h * 0.52
        # Scale: isi ~100% lebar/tinggi minimum
        scale = min(w, h) * 1.00 / (self._max_range * 2)
        return cx, cy, scale

    # ── Paint ────────────────────────────────────────────────────────────────

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), _C_BG)
        self._draw_ground_rings(p)
        self._draw_ground_radials(p)
        self._draw_axes(p)
        self._draw_events(p)
        self._draw_acft(p)
        self._draw_hud(p)
        p.end()

    def _draw_ground_rings(self, p: QPainter):
        """Ring elips di bidang XY (z=0) setelah dirotasi."""
        ring_m = 5.0
        while ring_m <= self._max_range + 0.01:
            is_outer = abs(ring_m - self._max_range) < 0.01
            pen = QPen(_C_GRID_MAJ if is_outer else _C_GRID)
            pen.setWidthF(1.0 if is_outer else 0.6)
            pen.setStyle(Qt.PenStyle.SolidLine if is_outer else Qt.PenStyle.DotLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)

            pts = []
            steps = 64
            for i in range(steps + 1):
                ang = math.radians(i * 360 / steps)
                wx = ring_m * math.cos(ang)
                wy = ring_m * math.sin(ang)
                pts.append(self._project(wx, wy, 0))
            p.drawPolyline(QPolygonF(pts))

            # Label jarak di titik timur ring
            label_pt = self._project(ring_m, 0, 0)
            p.setPen(_C_TEXT_DIM)
            font = QFont("IBM Plex Mono", 6)
            p.setFont(font)
            if ring_m < self._max_range:
                p.drawText(QPointF(label_pt.x() + 2, label_pt.y()), f"{ring_m:.0f}m")

            ring_m += 5.0

    def _draw_ground_radials(self, p: QPainter):
        """Garis radial dari pusat ke tepi di bidang XY."""
        origin = self._project(0, 0, 0)
        pen = QPen(_C_GRID)
        pen.setWidthF(0.4)
        pen.setStyle(Qt.PenStyle.DotLine)
        p.setPen(pen)
        for ang_deg in range(0, 360, 30):
            ang = math.radians(ang_deg)
            tip = self._project(
                self._max_range * math.cos(ang),
                self._max_range * math.sin(ang),
                0,
            )
            p.drawLine(origin, tip)

    def _draw_axes(self, p: QPainter):
        """Sumbu X (merah), Y (hijau), Z (biru)."""
        origin = self._project(0, 0, 0)
        ax_len = self._max_range * 0.40

        font = QFont("IBM Plex Mono", 7)
        font.setBold(True)
        p.setFont(font)

        for ax, ay, az, color, lbl in [
            (ax_len, 0, 0, _C_AXIS_X, "X"),
            (0, ax_len, 0, _C_AXIS_Y, "Y"),
            (0, 0, ax_len, _C_AXIS_Z, "Z"),
        ]:
            tip = self._project(ax, ay, az)
            pen = QPen(color)
            pen.setWidthF(1.8)
            p.setPen(pen)
            p.drawLine(origin, tip)

            # Arrowhead
            dx, dy = tip.x() - origin.x(), tip.y() - origin.y()
            length = math.hypot(dx, dy)
            if length > 0:
                nx, ny = dx / length, dy / length
                perp_x, perp_y = -ny * 3, nx * 3
                arrow = QPolygonF([
                    tip,
                    QPointF(tip.x() - nx * 8 + perp_x, tip.y() - ny * 8 + perp_y),
                    QPointF(tip.x() - nx * 8 - perp_x, tip.y() - ny * 8 - perp_y),
                ])
                p.setBrush(QBrush(color))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawPolygon(arrow)

            p.setPen(color)
            p.drawText(QPointF(tip.x() + 4, tip.y() + 4), lbl)

    def _draw_events(self, p: QPainter):
        if not self._events:
            cx, cy, _ = self._get_params()
            font = QFont("IBM Plex Mono", 10)
            p.setFont(font)
            p.setPen(_C_TEXT_DIM)
            msg = "NO DATA"
            fm = QFontMetricsF(font)
            p.drawText(QPointF(cx - fm.horizontalAdvance(msg) / 2, cy + 40), msg)
            return

        font_ev = QFont("IBM Plex Mono", 7)
        font_ev.setBold(True)
        p.setFont(font_ev)

        for ev in self._events:
            x, y, z = ev.get("x", 0.0), ev.get("y", 0.0), ev.get("z", 0.0)
            num = ev.get("event_number", "?")
            dist_xy = math.hypot(x, y)
            oob = dist_xy > self._max_range

            if oob:
                factor = (self._max_range - 0.5) / dist_xy
                x, y = x * factor, y * factor
                ev_color = _C_OOB
            else:
                ev_color = _C_EVENT_DOT

            z_clamp = max(0.0, min(z, _MAX_Z_M))

            sp_ground = self._project(x, y, 0)
            sp_3d     = self._project(x, y, z_clamp)

            # Shadow dot di ground
            shadow = QColor(ev_color)
            shadow.setAlpha(70)
            p.setBrush(QBrush(shadow))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(sp_ground, 3.5, 3.5)

            # Garis spike (ground → 3D)
            pen_s = QPen(_C_SPIKE)
            pen_s.setWidthF(1.5)
            pen_s.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen_s)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(sp_ground, sp_3d)

            # Diamond marker di titik 3D
            ds = 5.5
            diamond = QPolygonF([
                QPointF(sp_3d.x(),      sp_3d.y() - ds),
                QPointF(sp_3d.x() + ds * 0.65, sp_3d.y()),
                QPointF(sp_3d.x(),      sp_3d.y() + ds),
                QPointF(sp_3d.x() - ds * 0.65, sp_3d.y()),
            ])
            p.setBrush(QBrush(ev_color))
            p.setPen(QPen(ev_color.lighter(160), 0.8))
            p.drawPolygon(diamond)

            # Label
            fm = QFontMetricsF(font_ev)
            p.setPen(ev_color)
            label = f"E{num}" + ("!" if oob else "")
            p.setFont(font_ev)
            p.drawText(QPointF(sp_3d.x() + 7, sp_3d.y() - 2), label)
            p.setPen(_C_TEXT_DIM)
            p.drawText(QPointF(sp_3d.x() + 7, sp_3d.y() + fm.height()), f"z={z:.1f}m")

    def _draw_acft(self, p: QPainter):
        if not self._vertices or not self._faces:
            # Fallback to simple crosshair if mesh is not loaded
            origin = self._project(0, 0, 0)
            pen = QPen(_C_ACFT)
            pen.setWidthF(1.2)
            p.setPen(pen)
            s = 5
            p.drawLine(QPointF(origin.x() - s, origin.y()), QPointF(origin.x() + s, origin.y()))
            p.drawLine(QPointF(origin.x(), origin.y() - s), QPointF(origin.x(), origin.y() + s))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(origin, 3.5, 3.5)
            return

        # Project all 3D vertices using self._project
        # Note: v is (xw, yw, zw) where:
        # xw is widget x
        # yw is widget y
        # zw is widget z
        projected_pts = [self._project(v[0], v[1], v[2]) for v in self._vertices]

        # Draw wireframe faces
        pen = QPen(QColor(_C_ACFT.red(), _C_ACFT.green(), _C_ACFT.blue(), 180))
        pen.setWidthF(0.8)
        p.setPen(pen)

        brush = QBrush(QColor(_C_ACFT.red(), _C_ACFT.green(), _C_ACFT.blue(), 15))
        p.setBrush(brush)

        for face in self._faces:
            poly = QPolygonF([projected_pts[idx] for idx in face])
            p.drawPolygon(poly)

        # Draw a small center indicator dot at (0, 0, 0)
        origin = self._project(0, 0, 0)
        p.setBrush(QBrush(_C_ACFT))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(origin, 2.0, 2.0)

    def _draw_hud(self, p: QPainter):
        font = QFont("IBM Plex Mono", 7)
        p.setFont(font)
        p.setPen(_C_TEXT_DIM)
        lines = [
            f"YAW:   {self._yaw:.0f}°",
            f"PITCH: {self._pitch:.0f}°",
            f"ROLL:  {self._roll:.0f}°",
            f"RANGE: {self._max_range:.0f}m",
        ]
        x, y = 8, 16
        for line in lines:
            p.drawText(QPointF(x, y), line)
            y += 13


class Tactical3DWidget(QWidget):
    """Kontainer: _IsoCanvas + panel kontrol rotasi 3 sumbu."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tactical3DWidget")
        self._canvas = _IsoCanvas()
        self._range_idx = len(_RANGE_STEPS) - 1   # default to 20m (last index)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        root.addWidget(self._canvas, stretch=1)

        # ── Panel kontrol rotasi & zoom ───────────────────────────────────
        ctrl = QWidget()
        ctrl.setStyleSheet("background-color: #060d06; border-top: 1px solid #1a4a1a;")
        grid = QGridLayout(ctrl)
        grid.setContentsMargins(8, 4, 8, 6)
        grid.setSpacing(4)

        def lbl(text):
            l = QLabel(text)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setStyleSheet(
                "color: #1a7a1a; font-family: 'IBM Plex Mono';"
                "font-size: 8px; background: transparent; border: none;"
            )
            return l

        def btn(text, callback):
            b = QPushButton(text)
            b.setStyleSheet(_BTN_STYLE)
            b.clicked.connect(callback)
            return b

        # Row 0: headers
        grid.addWidget(lbl("YAW (Z-axis)"),   0, 0, 1, 2)
        grid.addWidget(lbl("PITCH (X-axis)"),  0, 2, 1, 2)
        grid.addWidget(lbl("ROLL (Y-axis)"),   0, 4, 1, 2)
        grid.addWidget(lbl("ZOOM"),            0, 6, 1, 2)
        grid.addWidget(lbl("VIEW"),            0, 8, 1, 1)

        # Row 1: buttons
        grid.addWidget(btn("◀ -30°", lambda: self._canvas.rotate_yaw(-30)),   1, 0)
        grid.addWidget(btn("+30° ▶", lambda: self._canvas.rotate_yaw(+30)),   1, 1)
        grid.addWidget(btn("▼ -15°", lambda: self._canvas.rotate_pitch(-15)), 1, 2)
        grid.addWidget(btn("+15° ▲", lambda: self._canvas.rotate_pitch(+15)), 1, 3)
        grid.addWidget(btn("◀ -30°", lambda: self._canvas.rotate_roll(-30)),  1, 4)
        grid.addWidget(btn("+30° ▶", lambda: self._canvas.rotate_roll(+30)),  1, 5)

        # Zoom buttons
        self._btn_zout = btn("−", self._zoom_out)
        self._btn_zout.setToolTip("Zoom Out")
        self._btn_zin = btn("+", self._zoom_in)
        self._btn_zin.setToolTip("Zoom In")
        grid.addWidget(self._btn_zout, 1, 6)
        grid.addWidget(self._btn_zin, 1, 7)

        # Reset button
        reset_btn = QPushButton("⟳ RESET")
        reset_btn.setStyleSheet(_BTN_STYLE)
        reset_btn.clicked.connect(self._canvas.reset_view)
        grid.addWidget(reset_btn, 1, 8)

        root.addWidget(ctrl)
        self._apply_range()

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
        self._canvas.set_range(max_r)
        self._btn_zin.setEnabled(self._range_idx > 0)
        self._btn_zout.setEnabled(self._range_idx < len(_RANGE_STEPS) - 1)

    def set_data(self, events: list[dict]):
        self._canvas.set_data(events)

    def clear(self):
        self._canvas.clear()

    def sizeHint(self) -> QSize:
        return QSize(480, 480)
