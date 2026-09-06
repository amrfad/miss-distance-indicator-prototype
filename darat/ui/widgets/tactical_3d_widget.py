# darat/ui/widgets/tactical_3d_widget.py
"""
Tactical3DWidget — Native PySide6 Isometric Spike-Map Display.

v3 — Interactive Edition:
- Mouse drag to rotate (left-click + drag: yaw/pitch)
- Scroll wheel to zoom (continuous, not stepped)
- Perspective projection (true depth perception)
- Hover tooltip showing event coordinates
- Keyboard shortcuts (arrow keys, R, +/-)
- Double-click auto-fit to all events
- Idle auto-rotate animation with toggle button

Koordinat: X=timur(+), Y=utara(+), Z=altitude(+)
"""

import math
import time

from PySide6.QtCore import Qt, QPointF, QSize, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QPolygonF, QFontMetricsF,
    QCursor,
)
from PySide6.QtWidgets import (
    QWidget, QSizePolicy, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGridLayout, QToolTip,
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

_MAX_Z_M      = 15.0
_ZOOM_MIN     = 2.5
_ZOOM_MAX     = 50.0
_ZOOM_STEP    = 2.5

# Idle auto-rotate: mulai setelah N detik tidak ada interaksi
_IDLE_SECONDS = 3.0
_AUTO_ROTATE_DEG_PER_FRAME = 0.35   # °/frame pada 50ms timer

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
    min-width: 52px;
}
QPushButton:hover {
    background-color: #123a12;
    border-color: #33cc33;
}
QPushButton:pressed {
    background-color: #0a250a;
}
QPushButton:checked {
    background-color: #1a5a1a;
    border-color: #55ff55;
    color: #55ff55;
}
QPushButton:disabled {
    color: #1a4a1a;
    border-color: #0f2a0f;
}
"""


def _rotate_point(x: float, y: float, z: float,
                  yaw: float, pitch: float, roll: float) -> tuple[float, float, float]:
    """Rotasi 3D menggunakan sudut Euler (derajat): Yaw (Z), Pitch (X), Roll (Y).

    Urutan rotasi: Yaw → Pitch → Roll
    """
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
    """Canvas QPainter untuk isometric spike-map dengan interaksi penuh.

    Signals
    -------
    range_changed(float)   — dikirim saat range berubah via scroll/double-click
    """

    range_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tactical3DCanvas")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(300, 300)

        # Focus + cursor
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))

        self._events: list[dict] = []

        # Sudut rotasi default — perspektif taktis dari atas-depan
        self._yaw   = 30.0
        self._pitch = 25.0
        self._roll  = 0.0
        self._max_range = 20.0

        # Drag state
        self._drag_active = False
        self._drag_start_pos = QPointF()
        self._drag_start_yaw = 30.0
        self._drag_start_pitch = 25.0

        # Projected event cache untuk hover tooltip
        self._projected_events: list[tuple[QPointF, dict]] = []

        # Idle auto-rotate
        self._last_interaction = time.monotonic()
        self._auto_rotate_enabled = False

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(50)   # 20 fps
        self._anim_timer.timeout.connect(self._on_anim_tick)
        self._anim_timer.start()

        # Mesh pesawat
        self._vertices, self._faces = load_plane_mesh()

        # Mouse tracking untuk tooltip
        self.setMouseTracking(True)

    # ── Public API ───────────────────────────────────────────────────────────

    def set_range(self, max_range_m: float):
        self._max_range = max(float(_ZOOM_MIN), min(float(_ZOOM_MAX), max_range_m))
        self.update()

    def set_data(self, events: list[dict]):
        self._events = [e for e in events if e.get("valid", False)]
        self.update()

    def clear(self):
        self._events = []
        self.update()

    def rotate_yaw(self, delta: float):
        self._yaw = (self._yaw + delta) % 360
        self._touch_interaction()
        self.update()

    def rotate_pitch(self, delta: float):
        self._pitch = max(-89.0, min(89.0, self._pitch + delta))
        self._touch_interaction()
        self.update()

    def rotate_roll(self, delta: float):
        self._roll = (self._roll + delta) % 360
        self._touch_interaction()
        self.update()

    def reset_view(self):
        self._yaw, self._pitch, self._roll = 30.0, 25.0, 0.0
        self._max_range = 20.0
        self._touch_interaction()
        self.range_changed.emit(self._max_range)
        self.update()

    def set_auto_rotate(self, enabled: bool):
        self._auto_rotate_enabled = enabled
        if enabled:
            self._last_interaction = 0.0   # mulai langsung
        else:
            self._last_interaction = time.monotonic()

    # ── Idle auto-rotate ─────────────────────────────────────────────────────

    def _touch_interaction(self):
        """Catat waktu interaksi terakhir (reset idle timer)."""
        self._last_interaction = time.monotonic()

    def _on_anim_tick(self):
        """Dipanggil 20x/detik. Aktifkan auto-rotate bila idle cukup lama."""
        if not self._auto_rotate_enabled:
            return
        idle = time.monotonic() - self._last_interaction
        if idle >= _IDLE_SECONDS:
            self._yaw = (self._yaw + _AUTO_ROTATE_DEG_PER_FRAME) % 360
            self.update()

    # ── Proyeksi ─────────────────────────────────────────────────────────────

    def _project(self, x: float, y: float, z: float) -> QPointF:
        """Rotasi 3D lalu proyeksi perspektif ke layar."""
        cx, cy, scale = self._get_params()
        rx, ry, rz = _rotate_point(x, y, z, self._yaw, self._pitch, self._roll)

        # Proyeksi perspektif: titik jauh tampak lebih kecil
        focal = self._max_range * 2.5
        depth = ry + focal
        if depth < 0.1:
            depth = 0.1

        sx = cx + (rx / depth) * focal * scale
        sy = cy - (rz / depth) * focal * scale
        return QPointF(sx, sy)

    def _get_params(self) -> tuple[float, float, float]:
        """Return (cx, cy, scale)."""
        w, h = self.width(), self.height()
        cx = w * 0.5
        cy = h * 0.52
        scale = min(w, h) * 0.95 / (self._max_range * 2)
        return cx, cy, scale

    # ── Mouse Events ─────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = True
            self._drag_start_pos = event.position()
            self._drag_start_yaw = self._yaw
            self._drag_start_pitch = self._pitch
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
            self._touch_interaction()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_active = False
            self.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
            self._touch_interaction()
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_active:
            delta = event.position() - self._drag_start_pos
            self._yaw   = (self._drag_start_yaw   + delta.x() * 0.45) % 360
            self._pitch = self._drag_start_pitch - delta.y() * 0.30
            self._pitch = max(-89.0, min(89.0, self._pitch))
            self._touch_interaction()
            self.update()
        else:
            # Hover tooltip: cek apakah mouse dekat event
            self._check_hover_tooltip(event)

    def mouseDoubleClickEvent(self, event):
        """Double-click: auto-fit range ke semua event."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._auto_fit()
        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event):
        """Scroll wheel: zoom continuous."""
        delta = event.angleDelta().y()
        if delta > 0:
            self._max_range = max(_ZOOM_MIN, self._max_range - _ZOOM_STEP)
        else:
            self._max_range = min(_ZOOM_MAX, self._max_range + _ZOOM_STEP)
        self._touch_interaction()
        self.range_changed.emit(self._max_range)
        self.update()
        event.accept()

    def keyPressEvent(self, event):
        """Keyboard shortcuts saat canvas focused."""
        key = event.key()
        if key == Qt.Key.Key_Left:
            self.rotate_yaw(-10)
        elif key == Qt.Key.Key_Right:
            self.rotate_yaw(+10)
        elif key == Qt.Key.Key_Up:
            self.rotate_pitch(+10)
        elif key == Qt.Key.Key_Down:
            self.rotate_pitch(-10)
        elif key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal, Qt.Key.Key_BracketRight):
            self._max_range = max(_ZOOM_MIN, self._max_range - _ZOOM_STEP)
            self.range_changed.emit(self._max_range)
            self.update()
        elif key in (Qt.Key.Key_Minus, Qt.Key.Key_BracketLeft):
            self._max_range = min(_ZOOM_MAX, self._max_range + _ZOOM_STEP)
            self.range_changed.emit(self._max_range)
            self.update()
        elif key == Qt.Key.Key_R:
            self.reset_view()
        else:
            super().keyPressEvent(event)

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _auto_fit(self):
        """Hitung bounding box semua event dan set range otomatis."""
        if not self._events:
            return
        dists = [math.hypot(e.get("x", 0), e.get("y", 0)) for e in self._events]
        max_dist = max(dists) if dists else 10.0
        new_range = max(_ZOOM_MIN, min(_ZOOM_MAX, math.ceil(max_dist * 1.3 / 5) * 5))
        self._max_range = new_range
        self._touch_interaction()
        self.range_changed.emit(self._max_range)
        self.update()

    def _check_hover_tooltip(self, event):
        """Tampilkan QToolTip jika mouse dekat event yang diproyeksikan."""
        if not self._projected_events:
            return
        pos = event.position()
        THRESHOLD = 14.0
        for sp, ev in self._projected_events:
            dx = pos.x() - sp.x()
            dy = pos.y() - sp.y()
            if math.hypot(dx, dy) < THRESHOLD:
                x = ev.get("x", 0.0)
                y = ev.get("y", 0.0)
                z = ev.get("z", 0.0)
                num = ev.get("event_number", "?")
                tip = f"E{num}  x={x:.2f}m  y={y:.2f}m  z={z:.2f}m"
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return
        QToolTip.hideText()

    # ── Paint ─────────────────────────────────────────────────────────────────

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
        steps = 64

        # 1. Ring grid dalam (interval 5m) — digambar redup jika di dalam batas luar
        ring_m = 5.0
        while ring_m < self._max_range - 1.0:
            pen = QPen(_C_GRID)
            pen.setWidthF(0.6)
            pen.setStyle(Qt.PenStyle.DotLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)

            pts = []
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
            p.drawText(QPointF(label_pt.x() + 2, label_pt.y()), f"{ring_m:.0f}m")

            ring_m += 5.0

        # 2. Ring terluar batas jangkauan (outer boundary ring) — SELALU menyala solid
        pen = QPen(_C_GRID_MAJ)
        pen.setWidthF(1.2)
        pen.setStyle(Qt.PenStyle.SolidLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        pts = []
        for i in range(steps + 1):
            ang = math.radians(i * 360 / steps)
            wx = self._max_range * math.cos(ang)
            wy = self._max_range * math.sin(ang)
            pts.append(self._project(wx, wy, 0))
        p.drawPolyline(QPolygonF(pts))

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
        # Reset cache setiap frame
        self._projected_events = []

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

        # Z-sort: gambar event yang paling jauh dari kamera lebih dulu
        def depth_key(ev):
            x, y, z = ev.get("x", 0.0), ev.get("y", 0.0), ev.get("z", 0.0)
            _, ry, _ = _rotate_point(x, y, z, self._yaw, self._pitch, self._roll)
            return ry

        sorted_events = sorted(self._events, key=depth_key, reverse=True)

        for ev in sorted_events:
            x, y, z = ev.get("x", 0.0), ev.get("y", 0.0), ev.get("z", 0.0)
            num = ev.get("event_number", "?")
            dist_xy = math.hypot(x, y)
            oob = dist_xy > self._max_range

            if oob:
                factor = (self._max_range - 0.5) / dist_xy
                x_draw, y_draw = x * factor, y * factor
                ev_color = _C_OOB
            else:
                x_draw, y_draw = x, y
                ev_color = _C_EVENT_DOT

            # Depth-based opacity: event lebih jauh → sedikit lebih transparan
            _, ry, _ = _rotate_point(x_draw, y_draw, z, self._yaw, self._pitch, self._roll)
            depth_norm = max(0.0, min(1.0, (ry + self._max_range) / (self._max_range * 2)))
            alpha = int(160 + depth_norm * 95)  # 160–255

            z_clamp = max(0.0, min(z, _MAX_Z_M))

            sp_ground = self._project(x_draw, y_draw, 0)
            sp_3d     = self._project(x_draw, y_draw, z_clamp)

            # Simpan untuk tooltip
            self._projected_events.append((sp_3d, ev))

            # Shadow dot di ground
            shadow = QColor(ev_color)
            shadow.setAlpha(60)
            p.setBrush(QBrush(shadow))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(sp_ground, 3.5, 3.5)

            # Garis spike (ground → 3D)
            spike_color = QColor(_C_SPIKE)
            spike_color.setAlpha(alpha)
            pen_s = QPen(spike_color)
            pen_s.setWidthF(1.5)
            pen_s.setStyle(Qt.PenStyle.DashLine)
            p.setPen(pen_s)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawLine(sp_ground, sp_3d)

            # Diamond marker di titik 3D
            ev_alpha = QColor(ev_color)
            ev_alpha.setAlpha(alpha)
            ds = 5.5
            diamond = QPolygonF([
                QPointF(sp_3d.x(),           sp_3d.y() - ds),
                QPointF(sp_3d.x() + ds * 0.65, sp_3d.y()),
                QPointF(sp_3d.x(),           sp_3d.y() + ds),
                QPointF(sp_3d.x() - ds * 0.65, sp_3d.y()),
            ])
            p.setBrush(QBrush(ev_alpha))
            p.setPen(QPen(ev_alpha.lighter(160), 0.8))
            p.drawPolygon(diamond)

            # Label
            fm = QFontMetricsF(font_ev)
            label_color = QColor(ev_color)
            label_color.setAlpha(alpha)
            p.setPen(label_color)
            label = f"E{num}" + ("!" if oob else "")
            p.setFont(font_ev)
            p.drawText(QPointF(sp_3d.x() + 7, sp_3d.y() - 2), label)
            dim_color = QColor(_C_TEXT_DIM)
            dim_color.setAlpha(max(80, alpha - 40))
            p.setPen(dim_color)
            p.drawText(QPointF(sp_3d.x() + 7, sp_3d.y() + fm.height()), f"z={z:.1f}m")

    def _draw_acft(self, p: QPainter):
        if not self._vertices or not self._faces:
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

        projected_pts = [self._project(v[0], v[1], v[2]) for v in self._vertices]

        pen = QPen(QColor(_C_ACFT.red(), _C_ACFT.green(), _C_ACFT.blue(), 180))
        pen.setWidthF(0.8)
        p.setPen(pen)
        brush = QBrush(QColor(_C_ACFT.red(), _C_ACFT.green(), _C_ACFT.blue(), 15))
        p.setBrush(brush)

        for face in self._faces:
            poly = QPolygonF([projected_pts[idx] for idx in face])
            p.drawPolygon(poly)

        origin = self._project(0, 0, 0)
        p.setBrush(QBrush(_C_ACFT))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(origin, 2.0, 2.0)

    def _draw_hud(self, p: QPainter):
        font = QFont("IBM Plex Mono", 7)
        p.setFont(font)
        p.setPen(_C_TEXT_DIM)
        auto_tag = " ⟳" if self._auto_rotate_enabled else ""
        lines = [
            f"YAW:   {self._yaw:.0f}°{auto_tag}",
            f"PITCH: {self._pitch:.0f}°",
            f"ROLL:  {self._roll:.0f}°",
            f"RANGE: {self._max_range:.1f}m",
        ]
        x, y = 8, 16
        for line in lines:
            p.drawText(QPointF(x, y), line)
            y += 13

        # Hint singkat di pojok kanan bawah
        hint_font = QFont("IBM Plex Mono", 6)
        p.setFont(hint_font)
        hint = "drag=rotate  scroll=zoom  dbl=fit  R=reset"
        fm = QFontMetricsF(hint_font)
        w = self.width()
        h = self.height()
        p.drawText(QPointF(w - fm.horizontalAdvance(hint) - 6, h - 6), hint)


class Tactical3DWidget(QWidget):
    """Kontainer: _IsoCanvas + panel kontrol rotasi + tombol auto-rotate."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("tactical3DWidget")
        self._canvas = _IsoCanvas()
        self._canvas.range_changed.connect(self._on_range_changed)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        root.addWidget(self._canvas, stretch=1)

        # ── Panel kontrol ───────────────────────────────────────────────────
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

        def btn(text, callback, checkable=False):
            b = QPushButton(text)
            b.setStyleSheet(_BTN_STYLE)
            b.setCheckable(checkable)
            b.clicked.connect(callback)
            return b

        # Row 0: headers
        grid.addWidget(lbl("YAW (Z)"),    0, 0, 1, 2)
        grid.addWidget(lbl("PITCH (X)"),  0, 2, 1, 2)
        grid.addWidget(lbl("ROLL (Y)"),   0, 4, 1, 2)
        grid.addWidget(lbl("RANGE"),      0, 6, 1, 1)
        grid.addWidget(lbl("VIEW"),       0, 7, 1, 2)

        # Row 1: buttons
        grid.addWidget(btn("◀ -30°", lambda: self._canvas.rotate_yaw(-30)),   1, 0)
        grid.addWidget(btn("+30° ▶", lambda: self._canvas.rotate_yaw(+30)),   1, 1)
        grid.addWidget(btn("▼ -15°", lambda: self._canvas.rotate_pitch(-15)), 1, 2)
        grid.addWidget(btn("+15° ▲", lambda: self._canvas.rotate_pitch(+15)), 1, 3)
        grid.addWidget(btn("◀ -30°", lambda: self._canvas.rotate_roll(-30)),  1, 4)
        grid.addWidget(btn("+30° ▶", lambda: self._canvas.rotate_roll(+30)),  1, 5)

        # Range label (live)
        self._range_lbl = QLabel(f"{self._canvas._max_range:.0f}m")
        self._range_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._range_lbl.setStyleSheet(
            "color: #33cc33; font-family: 'IBM Plex Mono'; font-size: 9px;"
            "font-weight: bold; background: transparent; border: none;"
        )
        grid.addWidget(self._range_lbl, 1, 6)

        # Reset + Auto-rotate
        reset_btn = btn("⟳ RESET", self._canvas.reset_view)
        grid.addWidget(reset_btn, 1, 7)

        self._auto_btn = btn("⟳ AUTO", self._toggle_auto_rotate, checkable=True)
        self._auto_btn.setToolTip("Toggle idle auto-rotate animation")
        grid.addWidget(self._auto_btn, 1, 8)

        root.addWidget(ctrl)

    def _toggle_auto_rotate(self, checked: bool):
        self._canvas.set_auto_rotate(checked)

    def _on_range_changed(self, new_range: float):
        """Update label range saat scroll atau double-click."""
        self._range_lbl.setText(f"{new_range:.1f}m")

    # ── Public API ───────────────────────────────────────────────────────────

    def set_data(self, events: list[dict]):
        self._canvas.set_data(events)

    def set_range(self, max_range_m: float):
        self._canvas.set_range(max_range_m)
        self._range_lbl.setText(f"{max_range_m:.1f}m")

    def clear(self):
        self._canvas.clear()

    def sizeHint(self) -> QSize:
        return QSize(480, 480)
