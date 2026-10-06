# demo_ground/ssl/ssl_dispatcher.py
"""
SSL Dispatcher — Orchestrator cerdas lokalisasi suara untuk demo_ground.
Mendukung:
- Mode Auto-Adaptive: Mendeteksi apakah array mikrofon datar (koplanar, dz < 2cm)
  atau bertingkat (non-koplanar, dz >= 2cm).
  - Jika bertingkat: mengeksekusi solver 3D (Rotating Multilat 3D / Consensus / Bucher-Misra)
    lalu memproyeksikan [X, Y] ke bidang 2D dan mengekstrak ketinggian Z.
  - Jika datar / jika 3D gagal: mengeksekusi solver 2D murni (Rotating Multilat 2D / Chan-Ho).
- Mode Manual: Mengeksekusi solver spesifik yang dipilih pengguna dengan fallback aman ke 2D.
"""

import math
from typing import Dict, Any, Tuple, Optional, List
import numpy as np

from . import rotating_multilat_3d
from . import bucher_misra_3d
from . import consensus_3d
from . import rotating_multilat_2d
from . import chan_ho_2d

SOLVER_CHOICES = {
    "auto_adaptive": "⭐ Auto-Adaptive (2D/3D Projected - Rekomendasi)",
    "rotating_multilat_3d": "Rotating Multilateration 3D (Projected to 2D)",
    "bucher_misra_3d": "Bucher-Misra 3D (Projected to 2D)",
    "consensus_3d": "Consensus 3D (Projected to 2D)",
    "rotating_multilat_2d": "Rotating Multilateration 2D (Planar Mode)",
    "chan_ho_2d": "Chan-Ho WLS 2D (Planar Mode)",
}

# Ambang batas selisih ketinggian minimum untuk mengaktifkan solver 3D
Z_SPAN_THRESHOLD_M = 0.02  # 2 cm


def get_mic_array_span(mic_positions: dict) -> Tuple[float, float, float]:
    """Hitung rentang sebaran dimensi mikrofon (dx, dy, dz) dalam meter."""
    xs, ys, zs = [], [], []
    for m, p in mic_positions.items():
        if isinstance(p, dict):
            xs.append(float(p.get("x", 0.0)))
            ys.append(float(p.get("y", 0.0)))
            zs.append(float(p.get("z", 0.0)))
        elif isinstance(p, (list, tuple)):
            xs.append(float(p[0]) if len(p) > 0 else 0.0)
            ys.append(float(p[1]) if len(p) > 1 else 0.0)
            zs.append(float(p[2]) if len(p) > 2 else 0.0)

    if not xs:
        return 0.0, 0.0, 0.0

    dx = max(xs) - min(xs)
    dy = max(ys) - min(ys)
    dz = max(zs) - min(zs)
    return dx, dy, dz


def solve_adaptive(event_data: dict, mic_positions: dict, config: dict) -> Optional[Dict[str, Any]]:
    """
    Eksekusi kalkulasi lokalisasi suara secara adaptif:
    - Selalu menghasilkan koordinat horizontal [X, Y] untuk visualisasi Radar 2D.
    - Menyediakan estimasi Z jika solver 3D aktif dan mic non-koplanar.

    Returns:
        Dict berisi {pos_2d, pos_3d, z_val, miss_distance_2d, miss_distance_3d,
                     azimuth_deg, mode_label, solver_name, is_3d, valid}
        atau None jika kalkulasi gagal total.
    """
    method = str(config.get("ssl_method", "auto_adaptive")).lower()
    dx, dy, dz = get_mic_array_span(mic_positions)
    is_non_coplanar = dz >= Z_SPAN_THRESHOLD_M

    # ── 1. Cabang Mode Auto-Adaptive ──
    if method == "auto_adaptive":
        if is_non_coplanar:
            # Mic bertingkat -> coba solver 3D terbaik (Rotating Multilat 3D)
            res_3d = _run_solver_3d(rotating_multilat_3d, event_data, mic_positions, config)
            if res_3d is not None:
                return _format_result(
                    pos_xyz=res_3d,
                    solver_name="Rotating Multilat 3D",
                    mode_label=f"Auto 3D (Non-Coplanar dZ={dz*100:.1f}cm)",
                    is_3d=True
                )

            # Fallback ke Consensus 3D
            res_cons = _run_solver_3d(consensus_3d, event_data, mic_positions, config)
            if res_cons is not None:
                return _format_result(
                    pos_xyz=res_cons,
                    solver_name="Consensus 3D",
                    mode_label=f"Auto 3D Consensus (dZ={dz*100:.1f}cm)",
                    is_3d=True
                )

            # Jika 3D gagal (noise tinggi), fallback aman ke 2D
            res_2d = _run_solver_2d(rotating_multilat_2d, event_data, mic_positions, config)
            if res_2d is not None:
                return _format_result(
                    pos_xyz=[res_2d[0], res_2d[1], None],
                    solver_name="Rotating Multilat 2D",
                    mode_label="Auto 2D (Fallback from 3D)",
                    is_3d=False
                )
        else:
            # Mic datar murni (koplanar) -> gunakan solver 2D murni
            res_2d = _run_solver_2d(rotating_multilat_2d, event_data, mic_positions, config)
            if res_2d is not None:
                return _format_result(
                    pos_xyz=[res_2d[0], res_2d[1], None],
                    solver_name="Rotating Multilat 2D",
                    mode_label="Auto 2D (Planar Array Mode)",
                    is_3d=False
                )

            # Fallback ke Chan-Ho 2D
            res_ch = _run_solver_2d(chan_ho_2d, event_data, mic_positions, config)
            if res_ch is not None:
                return _format_result(
                    pos_xyz=[res_ch[0], res_ch[1], None],
                    solver_name="Chan-Ho WLS 2D",
                    mode_label="Auto 2D (Chan-Ho Planar)",
                    is_3d=False
                )

    # ── 2. Cabang Mode Manual 3D (Projected to 2D) ──
    elif method in ("rotating_multilat_3d", "bucher_misra_3d", "consensus_3d"):
        mod_map = {
            "rotating_multilat_3d": (rotating_multilat_3d, "Rotating Multilat 3D"),
            "bucher_misra_3d": (bucher_misra_3d, "Bucher-Misra 3D"),
            "consensus_3d": (consensus_3d, "Consensus 3D"),
        }
        mod, s_name = mod_map[method]
        res_3d = _run_solver_3d(mod, event_data, mic_positions, config)
        if res_3d is not None:
            return _format_result(
                pos_xyz=res_3d,
                solver_name=s_name,
                mode_label=f"Manual 3D Projected ({s_name})",
                is_3d=True
            )

        # Fallback aman jika mic ternyata koplanar dan 3D singular
        res_2d = _run_solver_2d(rotating_multilat_2d, event_data, mic_positions, config)
        if res_2d is not None:
            return _format_result(
                pos_xyz=[res_2d[0], res_2d[1], None],
                solver_name="Rotating Multilat 2D",
                mode_label=f"2D Fallback ({s_name} singular)",
                is_3d=False
            )

    # ── 3. Cabang Mode Manual 2D Murni ──
    elif method in ("rotating_multilat_2d", "chan_ho_2d"):
        mod = chan_ho_2d if method == "chan_ho_2d" else rotating_multilat_2d
        s_name = "Chan-Ho WLS 2D" if method == "chan_ho_2d" else "Rotating Multilat 2D"
        res_2d = _run_solver_2d(mod, event_data, mic_positions, config)
        if res_2d is not None:
            return _format_result(
                pos_xyz=[res_2d[0], res_2d[1], None],
                solver_name=s_name,
                mode_label=f"Manual 2D Planar ({s_name})",
                is_3d=False
            )

    return None


def _run_solver_3d(mod, event_data: dict, mic_positions: dict, config: dict) -> Optional[List[float]]:
    try:
        # Pastikan format mic_positions memiliki komponen [x, y, z]
        mics_3d = {}
        for m, p in mic_positions.items():
            if isinstance(p, dict):
                mics_3d[m] = [float(p.get("x", 0.0)), float(p.get("y", 0.0)), float(p.get("z", 0.0))]
            elif isinstance(p, (list, tuple)):
                mics_3d[m] = [
                    float(p[0]) if len(p) > 0 else 0.0,
                    float(p[1]) if len(p) > 1 else 0.0,
                    float(p[2]) if len(p) > 2 else 0.0,
                ]

        pos, _, _ = mod.solve(event_data, mics_3d, config)
        if pos is not None and len(pos) >= 3 and np.all(np.isfinite(pos)):
            return [float(pos[0]), float(pos[1]), float(pos[2])]
    except Exception as e:
        print(f"[WARN] [SSL-Dispatcher] Solver 3D '{getattr(mod, 'DISPLAY_NAME', '3D')}' error: {e}")
    return None


def _run_solver_2d(mod, event_data: dict, mic_positions: dict, config: dict) -> Optional[List[float]]:
    try:
        mics_2d = {}
        for m, p in mic_positions.items():
            if isinstance(p, dict):
                mics_2d[m] = {"x": float(p.get("x", 0.0)), "y": float(p.get("y", 0.0))}
            elif isinstance(p, (list, tuple)):
                mics_2d[m] = {"x": float(p[0]), "y": float(p[1])}

        pos, _, _ = mod.solve(event_data, mics_2d, config)
        if pos is not None and len(pos) >= 2 and np.all(np.isfinite(pos)):
            return [float(pos[0]), float(pos[1])]
    except Exception as e:
        print(f"[WARN] [SSL-Dispatcher] Solver 2D '{getattr(mod, 'DISPLAY_NAME', '2D')}' error: {e}")
    return None


def _format_result(pos_xyz: list, solver_name: str, mode_label: str, is_3d: bool) -> Dict[str, Any]:
    x = float(pos_xyz[0])
    y = float(pos_xyz[1])
    z = float(pos_xyz[2]) if (is_3d and pos_xyz[2] is not None) else None

    miss_2d = math.hypot(x, y)
    miss_3d = math.sqrt(x**2 + y**2 + (z**2 if z is not None else 0.0))
    azimuth = (math.degrees(math.atan2(x, y)) + 360.0) % 360.0

    return {
        "pos_2d": [x, y],
        "pos_3d": [x, y, z] if z is not None else None,
        "x": x,
        "y": y,
        "z_val": z,
        "miss_distance_2d": miss_2d,
        "miss_distance_3d": miss_3d if is_3d else miss_2d,
        "azimuth_deg": azimuth,
        "solver_name": solver_name,
        "mode_label": mode_label,
        "is_3d": is_3d,
        "valid": True,
    }
