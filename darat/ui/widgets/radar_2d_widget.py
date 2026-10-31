# darat/ui/widgets/radar_2d_widget.py
"""
Radar2DWidget — Native PySide6 Tactical Phosphor-Green 2D Radar Display.

Fitur:
- Polar radar rings (concentric range rings) & 12 radial sectors (30°).
- Penanda sumbu kardinal N (+Y), S (-Y), E (+X), W (-X).
- Proyeksi siluet drone 2D top-down (toggleable).
- Posisi geometris 6 mikrofon fisik (toggleable).
- Vektor perlintasan Miss Distance radial dari pusat target (0, 0).
- Penanda khusus PCA (Point of Closest Approach / Miss Distance minimum) berkedip merah.
- Hover tooltip 2D ringkas (X, Y, Miss Distance, Clock Bearing).
- Interaksi zoom (scroll-wheel & tombol +/-), auto-fit, serta highlight event terpilih.
"""

import math
from typing import List, Dict, Any, Optional

from PySide6.QtCore import Qt, QPointF, QSize, Signal
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QRadialGradient,
    QFontMetricsF, QPolygonF,
)
from PySide6.QtWidgets import (
    QWidget, QSizePolicy, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QToolTip, QFrame,
)

from .mesh_loader import load_plane_mesh


# ── Palet warna radar militer (Phosphor Green Tactical) ─────────────────────
_C_BG         = QColor("#060d06")
_C_BG_INNER   = QColor("#0d200d")
_C_GRID       = QColor("#1a4a1a")
_C_GRID_MAJ   = QColor("#236823")
_C_TEXT       = QColor("#33cc33")
_C_TEXT_DIM   = QColor("#1a7a1a")
_C_CROSSHAIR  = QColor("#33cc33")
_C_EVENT      = QColor("#ffff00")
_C_EVENT_PCA  = QColor("#ff3333")
_C_EVENT_OOB  = QColor("#ff6600")
_C_EVENT_HL   = QColor("#00ffff")   # Cyan highlight untuk event terpilih
_C_MIC        = QColor("#3399ff")   # Biru untuk marker mic

_ZOOM_MIN     = 2.5
_ZOOM_MAX     = 60.0
_ZOOM_STEP    = 2.5


def _calc_clock_bearing(x: float, y: float) -> tuple[str, float]:
    """Hitung sudut jarum jam (clock bearing) dan derajat azimuth (0-360) dari arah utara (+Y)."""
    # math.atan2(y, x): 0 di +X (kanan), 90 di +Y (atas)
    # Azimuth dari Utara (+Y) searah jarum jam:
    deg_cw = (90.0 - math.degrees(math.atan2(y, x))) % 360.0
    hour = int(deg_cw // 30)
    if hour == 0:
        hour = 12
    minute = int((deg_cw % 30) * 2)
    return f"{hour:02d}:{minute:02d}", deg_cw


class _RadarCanvas2D(QWidget):
    """Canvas polar radar 2D native berbasis QPainter."""

    range_changed = Signal(float)
    event_selected = Signal(int)    # (event_number)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("radarCanvas2D")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 320)

        self._events: List[Dict[str, Any]] = []
        self._mic_positions: Dict[str, Any] = {}
        self._max_range: float = 15.0

        self._show_airframe: bool = True
        self._show_mics: bool = True
        self._highlighted_event_num: Optional[int] = None

        # Mesh data
        self._vertices, self._faces, self._normals, self._face_types, self._centroids = load_plane_mesh()

        # Cache event terproyeksi untuk tooltip & klik
        self._projected_events: List[tuple[QPointF, dict]] = []
        self.setMouseTracking(True)

    # ── Public API ──────────────────────────────────────────────────────────

    def set_data(self, events: List[Dict[str, Any]], mic_positions: Optional[Dict[str, Any]] = None):
        self._events = [e for e in events if e.get("valid", False)]
        self._mic_positions = mic_positions or {}
        self.update()

    def clear(self):
        self._events = []
        self._mic_positions = {}
        self._highlighted_event_num = None
        self.update()

    def set_range(self, max_range_m: float):
        self._max_range = max(_ZOOM_MIN, min(_ZOOM_MAX, max_range_m))
        self.update()

    def get_range(self) -> float:
        return self._max_range

    def set_show_airframe(self, show: bool):
        self._show_airframe = show
        self.update()

    def set_show_mics(self, show: bool):
        self._show_mics = show
        self.update()

    def highlight_event(self, event_num: Optional[int]):
        self._highlighted_event_num = event_num
        self.update()

    # ── Mouse & Wheel Events ────────────────────────────────────────────────

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta > 0:
            self._max_range = max(_ZOOM_MIN, self._max_range - _ZOOM_STEP)
        else:
            self._max_range = min(_ZOOM_MAX, self._max_range + _ZOOM_STEP)
        self.range_changed.emit(self._max_range)
        self.update()
        event.accept()

    def mouseMoveEvent(self, event):
        if not self._projected_events:
            return
        pos = event.position()
        THRESHOLD = 14.0
        for sp, ev in self._projected_events:
            dx = pos.x() - sp.x()
            dy = pos.y() - sp.y()
            if math.hypot(dx, dy) < THRESHOLD:
                x = float(ev.get("x", 0.0))
                y = float(ev.get("y", 0.0))
                num = ev.get("event_number", "?")
                r_miss = math.hypot(x, y)
                clock, deg = _calc_clock_bearing(x, y)

                tip = (
                    f"EVENT #{num}\n"
                    f"X = {x:+.2f} m\n"
                    f"Y = {y:+.2f} m\n"
                    f"Miss Distance = {r_miss:.2f} m\n"
                    f"Bearing = {clock} o'clock ({deg:.1f}°)"
                )
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return
        QToolTip.hideText()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._projected_events:
            pos = event.position()
            THRESHOLD = 14.0
            for sp, ev in self._projected_events:
                if math.hypot(pos.x() - sp.x(), pos.y() - sp.y()) < THRESHOLD:
                    num = ev.get("event_number")
                    if num is not None:
                        self.highlight_event(num)
                        self.event_selected.emit(num)
                        return
        super().mousePressEvent(event)

    # ── Transformasi Geometri ────────────────────────────────────────────────

    def _plot_rect(self) -> tuple[QPointF, float]:
        w, h = self.width(), self.height()
        margin = 38
        r = (min(w, h) - margin * 2) / 2
        return QPointF(w / 2, h / 2), max(10.0, r)

    def _world_to_screen(self, x: float, y: float, center: QPointF, radius_px: float) -> QPointF:
        """Konversi meter dunia → piksel layar (+X ke kanan, +Y ke atas)."""
        sx = center.x() + (x / self._max_range) * radius_px
        sy = center.y() - (y / self._max_range) * radius_px
        return QPointF(sx, sy)

    # ── Paint Event ─────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        center, radius = self._plot_rect()

        self._draw_background(p, center, radius)
        self._draw_rings(p, center, radius)
        self._draw_sectors(p, center, radius)

        if self._show_airframe:
            self._draw_aircraft_topdown(p, center, radius)

        if self._show_mics:
            self._draw_microphones(p, center, radius)

        self._draw_crosshair(p, center)
        self._draw_events(p, center, radius)

        p.end()

    def _draw_background(self, p: QPainter, center: QPointF, radius: float):
        p.fillRect(self.rect(), _C_BG)
        grad = QRadialGradient(center, radius)
        grad.setColorAt(0.0, _C_BG_INNER)
        grad.setColorAt(0.85, _C_BG)
        grad.setColorAt(1.0, _C_BG)
        p.setBrush(QBrush(grad))
        p.setPen(QPen(_C_GRID_MAJ, 1.5))
        p.drawEllipse(center, radius, radius)

    def _draw_rings(self, p: QPainter, center: QPointF, radius: float):
        """Gambar 4 cincin konsentris dengan label jarak terdistribusi."""
        num_rings = 4
        ring_step = self._max_range / num_rings
        font = QFont("IBM Plex Mono", 8)
        p.setFont(font)

        for i in range(1, num_rings + 1):
            r_px = (i / num_rings) * radius
            is_outer = (i == num_rings)
            p.setPen(QPen(
                _C_GRID_MAJ if is_outer else _C_GRID,
                1.2 if is_outer else 0.8,
                Qt.PenStyle.SolidLine if is_outer else Qt.PenStyle.DashLine,
            ))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(center, r_px, r_px)

            # Label jarak di sepanjang sumbu Utara (+Y)
            dist_m = i * ring_step
            p.setPen(_C_TEXT_DIM)
            p.drawText(int(center.x() + 5), int(center.y() - r_px + 12), f"{dist_m:.1f}m")

    def _draw_sectors(self, p: QPainter, center: QPointF, radius: float):
        """Gambar 12 sektor radial (30°) dan penanda arah kardinal N, S, E, W."""
        for s in range(12):
            angle_rad = math.radians(s * 30)
            p1 = center
            p2 = QPointF(
                center.x() + radius * math.cos(angle_rad),
                center.y() - radius * math.sin(angle_rad)
            )
            is_cardinal = (s % 3 == 0)
            p.setPen(QPen(
                _C_GRID_MAJ if is_cardinal else _C_GRID,
                1.0 if not is_cardinal else 1.2,
                Qt.PenStyle.SolidLine
            ))
            p.drawLine(p1, p2)

        # Label Kardinal
        p.setPen(_C_TEXT)
        font_card = QFont("IBM Plex Mono", 9, QFont.Weight.Bold)
        p.setFont(font_card)
        p.drawText(int(center.x() - 18), int(center.y() - radius - 8), "N (+Y)")
        p.drawText(int(center.x() - 18), int(center.y() + radius + 18), "S (-Y)")
        p.drawText(int(center.x() + radius + 8), int(center.y() + 4), "E (+X)")
        p.drawText(int(center.x() - radius - 48), int(center.y() + 4), "W (-X)")

    def _draw_crosshair(self, p: QPainter, center: QPointF):
        p.setPen(QPen(_C_CROSSHAIR, 1.2))
        s = 7.0
        p.drawLine(QPointF(center.x() - s, center.y()), QPointF(center.x() + s, center.y()))
        p.drawLine(QPointF(center.x(), center.y() - s), QPointF(center.x(), center.y() + s))
        p.drawEllipse(center, 2.5, 2.5)

    def _draw_aircraft_topdown(self, p: QPainter, center: QPointF, radius: float):
        """Proyeksikan siluet 3D pesawat ke bidang 2D tampak atas (X-Y)."""
        if not self._vertices or not self._faces:
            return

        projected_pts = [
            self._world_to_screen(v[0], v[1], center, radius)
            for v in self._vertices
        ]

        faces_sorted = sorted(
            enumerate(self._faces),
            key=lambda item: self._centroids[item[0]][2]
        )

        for face_idx, face in faces_sorted:
            poly = QPolygonF([projected_pts[idx] for idx in face])
            ftype = self._face_types[face_idx]

            if ftype == "canopy":
                fill_c = QColor(10, 180, 230, 140)
                edge_c = QColor(60, 230, 255, 180)
            elif ftype == "exhaust":
                fill_c = QColor(220, 130, 25, 140)
                edge_c = QColor(255, 170, 40, 180)
            elif ftype == "wings":
                fill_c = QColor(15, 75, 20, 120)
                edge_c = QColor(40, 150, 50, 120)
            else:
                fill_c = QColor(12, 60, 16, 130)
                edge_c = QColor(30, 120, 40, 110)

            p.setBrush(QBrush(fill_c))
            p.setPen(QPen(edge_c, 0.6))
            p.drawPolygon(poly)

    def _draw_microphones(self, p: QPainter, center: QPointF, radius: float):
        """Gambar posisi geometris 6 mikrofon sebagai segitiga biru pada bidang XY."""
        if not self._mic_positions:
            return

        font_mic = QFont("IBM Plex Mono", 7, QFont.Weight.Bold)
        p.setFont(font_mic)

        for mic_name, pos in self._mic_positions.items():
            if not isinstance(pos, (list, tuple)) or len(pos) < 2:
                continue
            x, y = float(pos[0]), float(pos[1])
            pt = self._world_to_screen(x, y, center, radius)

            tri = QPolygonF([
                QPointF(pt.x(), pt.y() - 4.5),
                QPointF(pt.x() - 3.5, pt.y() + 3.0),
                QPointF(pt.x() + 3.5, pt.y() + 3.0),
            ])
            p.setBrush(QBrush(_C_MIC))
            p.setPen(QPen(_C_MIC.lighter(130), 0.8))
            p.drawPolygon(tri)

            p.setPen(_C_MIC)
            p.drawText(int(pt.x() + 5), int(pt.y() - 2), mic_name)

    def _draw_events(self, p: QPainter, center: QPointF, radius: float):
        self._projected_events.clear()
        if not self._events:
            p.setFont(QFont("IBM Plex Mono", 10))
            p.setPen(_C_TEXT_DIM)
            msg = "STANDBY — NO DETECTIONS"
            fm = QFontMetricsF(p.font())
            p.drawText(int(center.x() - fm.horizontalAdvance(msg) / 2),
                       int(center.y() + radius * 0.15), msg)
            return

        p.setFont(QFont("IBM Plex Mono", 8, QFont.Weight.Bold))

        # Cari event dengan jarak miss terdekat (PCA: Point of Closest Approach) di bidang 2D
        valid_evs = [e for e in self._events if e.get("valid", False)]
        pca_event_num = None
        if valid_evs:
            min_ev = min(valid_evs, key=lambda e: math.hypot(e.get("x", 0.0), e.get("y", 0.0)))
            pca_event_num = min_ev.get("event_number")

        for ev in valid_evs:
            x = float(ev.get("x", 0.0))
            y = float(ev.get("y", 0.0))
            num = ev.get("event_number", "?")
            is_pca = (num == pca_event_num)
            is_highlighted = (num == self._highlighted_event_num)

            r_miss = math.hypot(x, y)
            oob = r_miss > self._max_range

            if oob:
                scale = (self._max_range * 0.96) / r_miss
                draw_x, draw_y = x * scale, y * scale
            else:
                draw_x, draw_y = x, y

            pt = self._world_to_screen(draw_x, draw_y, center, radius)
            self._projected_events.append((pt, ev))

            # Garis vektor radial ke pusat target (0,0)
            if is_pca:
                p.setPen(QPen(_C_EVENT_PCA, 1.2, Qt.PenStyle.DashLine))
            elif is_highlighted:
                p.setPen(QPen(_C_EVENT_HL, 1.0, Qt.PenStyle.DashLine))
            else:
                p.setPen(QPen(_C_EVENT, 0.7, Qt.PenStyle.DotLine))
            p.drawLine(center, pt)

            # Render Blip Titik Kejadian
            if is_pca:
                glow = QColor(_C_EVENT_PCA)
                glow.setAlpha(60)
                p.setBrush(QBrush(glow))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(pt, 12, 12)

                p.setPen(QPen(_C_EVENT_PCA, 2.0))
                p.setBrush(QBrush(QColor(255, 50, 50, 200)))
                p.drawEllipse(pt, 6, 6)

                p.setPen(_C_EVENT_PCA)
                label = f"E{num} ({r_miss:.2f}m) [PCA]"
                p.drawText(int(pt.x() + 10), int(pt.y() + 4), label)
            elif is_highlighted:
                glow = QColor(_C_EVENT_HL)
                glow.setAlpha(80)
                p.setBrush(QBrush(glow))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(pt, 10, 10)

                p.setPen(QPen(_C_EVENT_HL, 2.0))
                p.setBrush(QBrush(_C_EVENT_HL))
                p.drawEllipse(pt, 5, 5)

                p.setPen(_C_EVENT_HL)
                p.drawText(int(pt.x() + 8), int(pt.y() - 3), f"E{num} (SEL)")
            else:
                color = _C_EVENT_OOB if oob else _C_EVENT
                glow = QColor(color)
                glow.setAlpha(40)
                p.setBrush(QBrush(glow))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(pt, 8, 8)

                p.setPen(QPen(color.lighter(130), 1.0))
                p.setBrush(QBrush(color))
                p.drawEllipse(pt, 4, 4)

                p.setPen(color)
                label = f"E{num}" + ("!" if oob else "")
                p.drawText(int(pt.x() + 7), int(pt.y() - 3), label)


class Radar2DWidget(QWidget):
    """Widget kontainer Radar 2D lengkap dengan toolbar kontrol taktis."""

    event_selected = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("radar2DWidget")
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(4)

        # ── Toolbar Kontrol Atas ─────────────────────────────────────────────
        bar = QFrame()
        bar.setStyleSheet(
            "background-color: #060d06; border-bottom: 1px solid #1a4a1a; padding: 2px;"
        )
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(8, 3, 8, 3)
        bl.setSpacing(8)

        title = QLabel("RADAR 2D — TACTICAL XY CPA DISPLAY")
        title.setStyleSheet(
            "color: #33cc33; font-family: 'IBM Plex Mono'; font-weight: bold; font-size: 11px;"
        )
        bl.addWidget(title)

        bl.addStretch()

        self.lbl_range = QLabel("RANGE: 15.0m")
        self.lbl_range.setStyleSheet(
            "color: #33cc33; font-family: 'IBM Plex Mono'; font-weight: bold; font-size: 11px;"
        )
        bl.addWidget(self.lbl_range)

        btn_style = (
            "QPushButton { background-color: #0a1a0a; border: 1px solid #1a4a1a; "
            "color: #33cc33; font-family: 'IBM Plex Mono'; font-size: 10px; font-weight: bold; "
            "padding: 2px 8px; border-radius: 3px; min-width: 24px; } "
            "QPushButton:hover { background-color: #123a12; border-color: #33cc33; } "
            "QPushButton:checked { background-color: #1a5a1a; color: #55ff55; border-color: #55ff55; } "
            "QPushButton:pressed { background-color: #0a250a; }"
        )

        self._btn_in = QPushButton("+")
        self._btn_in.setStyleSheet(btn_style)
        self._btn_in.setToolTip("Zoom In (turunkan range)")
        self._btn_in.clicked.connect(self._zoom_in)
        bl.addWidget(self._btn_in)

        self._btn_out = QPushButton("−")
        self._btn_out.setStyleSheet(btn_style)
        self._btn_out.setToolTip("Zoom Out (naikkan range)")
        self._btn_out.clicked.connect(self._zoom_out)
        bl.addWidget(self._btn_out)

        self._btn_autofit = QPushButton("FIT")
        self._btn_autofit.setStyleSheet(btn_style)
        self._btn_autofit.setToolTip("Auto-fit range ke event terjauh")
        self._btn_autofit.clicked.connect(self.auto_fit)
        bl.addWidget(self._btn_autofit)

        # Toggle Drone Airframe
        self._btn_airframe = QPushButton("✈ PLANE")
        self._btn_airframe.setCheckable(True)
        self._btn_airframe.setChecked(True)
        self._btn_airframe.setStyleSheet(btn_style)
        self._btn_airframe.setToolTip("Tampilkan/sembunyikan siluet bodi drone")
        self._btn_airframe.toggled.connect(self._on_toggle_airframe)
        bl.addWidget(self._btn_airframe)

        # Toggle Mics
        self._btn_mics = QPushButton("▲ MICS")
        self._btn_mics.setCheckable(True)
        self._btn_mics.setChecked(True)
        self._btn_mics.setStyleSheet(btn_style)
        self._btn_mics.setToolTip("Tampilkan/sembunyikan posisi 6 mikrofon")
        self._btn_mics.toggled.connect(self._on_toggle_mics)
        bl.addWidget(self._btn_mics)

        root.addWidget(bar)

        # ── Radar Canvas ─────────────────────────────────────────────────────
        self.canvas = _RadarCanvas2D()
        self.canvas.range_changed.connect(self._on_range_changed)
        self.canvas.event_selected.connect(self.event_selected)
        root.addWidget(self.canvas, stretch=1)

    # ── Public API ──────────────────────────────────────────────────────────

    def set_data(self, events: List[Dict[str, Any]], mic_positions: Optional[Dict[str, Any]] = None):
        self.canvas.set_data(events, mic_positions)

    def set_range(self, max_range_m: float):
        self.canvas.set_range(max_range_m)
        self._on_range_changed(self.canvas.get_range())

    def clear(self):
        self.canvas.clear()

    def highlight_event(self, event_num: Optional[int]):
        self.canvas.highlight_event(event_num)

    def auto_fit(self):
        """Hitung jangkauan otomatis dengan margin 25% dari event terjauh."""
        valid_evs = [e for e in self.canvas._events if e.get("valid", False)]
        if not valid_evs:
            self.set_range(15.0)
            return

        dists = [math.hypot(e.get("x", 0.0), e.get("y", 0.0)) for e in valid_evs]
        max_d = max(dists) if dists else 10.0
        fit_r = max(_ZOOM_MIN, math.ceil(max_d * 1.25 / 2.5) * 2.5)
        self.set_range(fit_r)

    # ── Internal Slots ──────────────────────────────────────────────────────

    def _on_range_changed(self, r: float):
        self.lbl_range.setText(f"RANGE: {r:.1f}m")

    def _zoom_in(self):
        r = max(_ZOOM_MIN, self.canvas.get_range() - _ZOOM_STEP)
        self.set_range(r)

    def _zoom_out(self):
        r = min(_ZOOM_MAX, self.canvas.get_range() + _ZOOM_STEP)
        self.set_range(r)

    def _on_toggle_airframe(self, checked: bool):
        self.canvas.set_show_airframe(checked)

    def _on_toggle_mics(self, checked: bool):
        self.canvas.set_show_mics(checked)

    def sizeHint(self) -> QSize:
        return QSize(500, 520)
