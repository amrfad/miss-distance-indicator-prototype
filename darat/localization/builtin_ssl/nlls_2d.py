"""
Nonlinear Least Squares 2D (Multi-Start)
Solver TDOA 2D berbasis optimasi Levenberg-Marquardt yang mengunci jarak Euclidean secara langsung.

Keunggulan:
  - Mendukung 3, 4, 5, hingga 6+ mikrofon secara seragam (termasuk mode darurat 3 mikrofon).
  - Agnostik terhadap nama mikrofon non-sekuensial (mis. mic0, mic1, mic3, mic5).
  - Multi-start (pusat array + 4 kuadran) untuk menghindari local minimum.
"""

from itertools import combinations
from typing import List, Optional, Sequence, Tuple

import numpy as np
from scipy.optimize import least_squares

DISPLAY_NAME = "Nonlinear Least Squares 2D"

_DEFAULT_C = 343.0
_DEFAULT_MAX_NORM = 150.0


def _get_tdoa(tdoa_dict: dict, m_i: str, m_j: str, mic_names: Sequence[str]) -> Optional[float]:
    """Ambil nilai TDOA tau_ij = t_i - t_j (detik) dengan transitivitas 1-hop."""
    k1 = f"{m_i}-{m_j}"
    if k1 in tdoa_dict:
        return float(tdoa_dict[k1])
    k2 = f"{m_j}-{m_i}"
    if k2 in tdoa_dict:
        return -float(tdoa_dict[k2])

    for mid in mic_names:
        if mid in (m_i, m_j):
            continue
        v1 = tdoa_dict.get(f"{m_i}-{mid}")
        if v1 is None and f"{mid}-{m_i}" in tdoa_dict:
            v1 = -float(tdoa_dict[f"{mid}-{m_i}"])
        v2 = tdoa_dict.get(f"{m_j}-{mid}")
        if v2 is None and f"{mid}-{m_j}" in tdoa_dict:
            v2 = -float(tdoa_dict[f"{mid}-{m_j}"])
        if v1 is not None and v2 is not None:
            return float(v1) - float(v2)
    return None


def solve(
    event_data: dict,
    mic_positions: dict,
    config: dict,
) -> Tuple[Optional[List[float]], Optional[int], Optional[List[str]]]:
    """
    Estimasi posisi 2D [x, y] menggunakan Nonlinear Least Squares multi-start.

    Mendukung minimal 3 mikrofon (mode darurat 3 mic ditandai low confidence).
    """
    c = float(config.get("speed_of_sound", _DEFAULT_C))
    max_norm = float(config.get("multilat_max_norm", _DEFAULT_MAX_NORM))
    tdoa_data = event_data.get("tdoa", {})

    mic_names = sorted(mic_positions.keys())
    n_mics = len(mic_names)
    if n_mics < 3:
        return None, 0, [f"NLLS 2D membutuhkan minimal 3 mikrofon, ditemukan {n_mics}"]

    def _pos2d(m: str) -> List[float]:
        p = mic_positions[m]
        if isinstance(p, dict):
            return [float(p["x"]), float(p["y"])]
        return [float(p[0]), float(p[1])]

    stations = np.array([_pos2d(m) for m in mic_names], dtype=float)

    valid_pairs = []
    meas_taus = []
    for u, v in combinations(range(n_mics), 2):
        val = _get_tdoa(tdoa_data, mic_names[u], mic_names[v], mic_names)
        if val is None or not np.isfinite(val):
            continue
        valid_pairs.append((u, v))
        meas_taus.append(float(val))

    if len(valid_pairs) < 2:
        return None, 0, ["Pasangan TDOA valid tidak mencukupi untuk NLLS 2D (minimal 2 pasang)"]

    u_idx = np.array([p[0] for p in valid_pairs], dtype=int)
    v_idx = np.array([p[1] for p in valid_pairs], dtype=int)
    meas_arr = np.array(meas_taus, dtype=float)

    def residuals(xy: np.ndarray) -> np.ndarray:
        dists = np.linalg.norm(stations - xy, axis=1)
        return ((dists[u_idx] - dists[v_idx]) / c) - meas_arr

    center = np.mean(stations, axis=0)
    starts = [center]
    for ang in np.linspace(0.0, 2.0 * np.pi, 4, endpoint=False):
        starts.append(center + 6.0 * np.array([np.cos(ang), np.sin(ang)]))

    best_x: Optional[np.ndarray] = None
    best_cost = np.inf

    for x0 in starts:
        try:
            sol = least_squares(residuals, x0, method="lm", max_nfev=150)
            if np.all(np.isfinite(sol.x)) and np.linalg.norm(sol.x) <= max_norm:
                if sol.cost < best_cost:
                    best_cost = float(sol.cost)
                    best_x = sol.x.copy()
        except Exception:
            continue

    if best_x is None:
        return None, 0, ["NLLS 2D gagal konvergen dalam batas jarak fisik"]

    rms_res_ms = float(np.sqrt(np.mean(residuals(best_x) ** 2)) * 1000.0)
    info = [
        f"NLLS 2D ({n_mics} mics, {len(valid_pairs)} pairs): "
        f"[{best_x[0]:.2f}, {best_x[1]:.2f}] m (RMS residual={rms_res_ms:.3f} ms)"
    ]
    if n_mics == 3:
        info.append("DEGRADED MODE (3 mics): akurasi rendah / low confidence")

    return [float(best_x[0]), float(best_x[1])], len(valid_pairs), info
