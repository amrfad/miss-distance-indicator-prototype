# demo_ground/ui/widgets/radar_2d_widget.py
"""
Radar2DWidget — Native PySide6 Tactical Phosphor-Green 2D Radar Display.
Menampilkan polar radar rings, crosshairs, dan estimasi Miss Distance target proyektil.
(Tanpa ilustrasi pesawat dan tanpa marker posisi mic).
"""

import math
from typing import List, Dict, Any, Optional

from PySide6.QtCore import Qt, QPointF, QSize, Signal
from PySide6.QtGui import (
    QColor, QFont, QPainter, QPen, QBrush, QRadialGradient,
)
from PySide6.QtWidgets import (
    QWidget, QSizePolicy, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QToolTip, QFrame,
)

# Tactical phosphor palette
_C_BG         = QColor("#060d06")
_C_BG_INNER   = QColor("#0d200d")
_C_GRID       = QColor("#1a4a1a")
_C_GRID_MAJ   = QColor("#236823")
_C_TEXT       = QColor("#33cc33")
_C_TEXT_DIM   = QColor("#1a7a1a")
_C_CROSSHAIR  = QColor("#33cc33")
_C_EVENT      = QColor("#ffff00")
_C_EVENT_LAST = QColor("#ff3333")

_ZOOM_MIN     = 2.5
_ZOOM_MAX     = 60.0
_ZOOM_STEP    = 2.5


class _RadarCanvas2D(QWidget):
    """Canvas radar polar native 2D."""

    range_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("radarCanvas")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(320, 320)

        self._events: List[Dict[str, Any]] = []
        self._max_range: float = 15.0

        self._projected_events: List[tuple[QPointF, dict]] = []
        self.setMouseTracking(True)

    def set_data(self, events: List[Dict[str, Any]], mic_positions: Optional[Dict[str, Any]] = None):
        self._events = events
        self.update()

    def clear(self):
        self._events = []
        self.update()

    def set_range(self, max_range_m: float):
        self._max_range = max(_ZOOM_MIN, min(_ZOOM_MAX, max_range_m))
        self.update()

    def get_range(self) -> float:
        return self._max_range

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
                x = ev.get("x", 0.0)
                y = ev.get("y", 0.0)
                num = ev.get("event_number", "?")
                r = math.hypot(x, y)
                tip = f"Event #{num}\nX = {x:+.2f} m\nY = {y:+.2f} m\nMiss Distance = {r:.2f} m"
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
                return
        QToolTip.hideText()

    def _plot_rect(self) -> tuple[QPointF, float]:
        w, h = self.width(), self.height()
        margin = 40
        r = (min(w, h) - margin * 2) / 2
        return QPointF(w / 2, h / 2), max(10.0, r)

    def _world_to_screen(self, x: float, y: float, center: QPointF, radius_px: float) -> QPointF:
        sx = center.x() + (x / self._max_range) * radius_px
        sy = center.y() - (y / self._max_range) * radius_px
        return QPointF(sx, sy)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        center, radius = self._plot_rect()

        # 1. Background
        p.fillRect(self.rect(), _C_BG)
        grad = QRadialGradient(center, radius)
        grad.setColorAt(0.0, _C_BG_INNER)
        grad.setColorAt(0.85, _C_BG)
        grad.setColorAt(1.0, _C_BG)
        p.setBrush(QBrush(grad))
        p.setPen(QPen(_C_GRID_MAJ, 1.5))
        p.drawEllipse(center, radius, radius)

        # 2. Concentric Range Rings
        num_rings = 4
        ring_step = self._max_range / num_rings
        font = QFont("Consolas", 8)
        p.setFont(font)

        for i in range(1, num_rings + 1):
            r_px = (i / num_rings) * radius
            is_outer = (i == num_rings)
            p.setPen(QPen(_C_GRID_MAJ if is_outer else _C_GRID, 1.0, Qt.PenStyle.DashLine if not is_outer else Qt.PenStyle.SolidLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(center, r_px, r_px)

            # Label jarak di sumbu North (+Y)
            dist_m = i * ring_step
            p.setPen(_C_TEXT_DIM)
            p.drawText(int(center.x() + 4), int(center.y() - r_px + 12), f"{dist_m:.1f}m")

        # 3. Radial Rays (12 sectors = 30 deg)
        for s in range(12):
            angle_rad = math.radians(s * 30)
            p1 = center
            p2 = QPointF(center.x() + radius * math.cos(angle_rad), center.y() - radius * math.sin(angle_rad))
            is_cardinal = (s % 3 == 0)
            p.setPen(QPen(_C_GRID_MAJ if is_cardinal else _C_GRID, 1.0 if not is_cardinal else 1.2))
            p.drawLine(p1, p2)

        # 4. Cardinal Direction Labels
        p.setPen(_C_TEXT)
        font_card = QFont("Inter", 9, QFont.Weight.Bold)
        p.setFont(font_card)
        p.drawText(int(center.x() - 5), int(center.y() - radius - 8), "N (+Y)")
        p.drawText(int(center.x() - 5), int(center.y() + radius + 18), "S (-Y)")
        p.drawText(int(center.x() + radius + 8), int(center.y() + 4), "E (+X)")
        p.drawText(int(center.x() - radius - 44), int(center.y() + 4), "W (-X)")

        # 5. Clean Center Reticle (0, 0)
        p.setPen(QPen(_C_CROSSHAIR, 1.5))
        reticle_len = 8.0
        p.drawLine(QPointF(center.x() - reticle_len, center.y()), QPointF(center.x() + reticle_len, center.y()))
        p.drawLine(QPointF(center.x(), center.y() - reticle_len), QPointF(center.x(), center.y() + reticle_len))
        p.drawEllipse(center, 3, 3)

        # 6. Events (Miss Distance targets)
        self._draw_events(p, center, radius)

    def _draw_events(self, p: QPainter, center: QPointF, radius: float):
        self._projected_events.clear()
        if not self._events:
            return

        p.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        n_ev = len(self._events)

        for idx, ev in enumerate(self._events):
            x = float(ev.get("x", 0.0))
            y = float(ev.get("y", 0.0))
            num = ev.get("event_number", idx + 1)
            is_last = (idx == n_ev - 1)

            pt = self._world_to_screen(x, y, center, radius)
            self._projected_events.append((pt, ev))

            # Line to center (CPA Miss Distance)
            if is_last:
                p.setPen(QPen(_C_EVENT_LAST, 1.2, Qt.PenStyle.DashLine))
            else:
                p.setPen(QPen(_C_EVENT, 0.8, Qt.PenStyle.DotLine))
            p.drawLine(center, pt)

            # Target Blip
            if is_last:
                # Pulsing / larger blip for latest
                p.setPen(QPen(_C_EVENT_LAST, 2.0))
                p.setBrush(QBrush(QColor(255, 50, 50, 180)))
                p.drawEllipse(pt, 7, 7)
                p.drawEllipse(pt, 11, 11)

                p.setPen(_C_EVENT_LAST)
                r_dist = math.hypot(x, y)
                p.drawText(int(pt.x() + 12), int(pt.y() + 4), f"E{num} ({r_dist:.2f}m)")
            else:
                p.setPen(QPen(_C_EVENT, 1.5))
                p.setBrush(QBrush(QColor(255, 255, 0, 180)))
                p.drawEllipse(pt, 4.5, 4.5)

                p.setPen(_C_TEXT)
                p.drawText(int(pt.x() + 7), int(pt.y() - 3), f"E{num}")


class Radar2DWidget(QWidget):
    """Container untuk Radar Canvas dengan zoom controls dan legend."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header bar dengan range indicator dan zoom buttons
        bar = QFrame()
        bar.setStyleSheet("background-color: #060d06; border-bottom: 1px solid #1a4a1a; padding: 2px;")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(8, 2, 8, 2)

        title = QLabel("RADAR 2D — TACTICAL CPA MONITOR")
        title.setStyleSheet("color: #33cc33; font-family: 'Inter'; font-weight: bold; font-size: 11px;")
        bar_layout.addWidget(title)

        bar_layout.addStretch()

        self.lbl_range = QLabel("RANGE: 15.0m")
        self.lbl_range.setStyleSheet("color: #33cc33; font-family: 'Consolas'; font-weight: bold; font-size: 11px;")
        bar_layout.addWidget(self.lbl_range)

        btn_style = (
            "QPushButton { background-color: #0d200d; border: 1px solid #236823; color: #33cc33; "
            "font-family: Consolas; font-weight: bold; font-size: 12px; padding: 2px 8px; border-radius: 3px; } "
            "QPushButton:hover { background-color: #1a4a1a; } "
            "QPushButton:pressed { background-color: #060d06; }"
        )

        btn_in = QPushButton("+")
        btn_in.setStyleSheet(btn_style)
        btn_in.clicked.connect(self._zoom_in)
        bar_layout.addWidget(btn_in)

        btn_out = QPushButton("-")
        btn_out.setStyleSheet(btn_style)
        btn_out.clicked.connect(self._zoom_out)
        bar_layout.addWidget(btn_out)

        layout.addWidget(bar)

        self.canvas = _RadarCanvas2D()
        self.canvas.range_changed.connect(self._on_range_changed)
        layout.addWidget(self.canvas, stretch=1)

    def set_data(self, events: List[Dict[str, Any]], mic_positions: Optional[Dict[str, Any]] = None):
        self.canvas.set_data(events, mic_positions)

    def clear(self):
        self.canvas.clear()

    def _on_range_changed(self, r: float):
        self.lbl_range.setText(f"RANGE: {r:.1f}m")

    def _zoom_in(self):
        r = max(_ZOOM_MIN, self.canvas.get_range() - _ZOOM_STEP)
        self.canvas.set_range(r)
        self._on_range_changed(r)

    def _zoom_out(self):
        r = min(_ZOOM_MAX, self.canvas.get_range() + _ZOOM_STEP)
        self.canvas.set_range(r)
        self._on_range_changed(r)
