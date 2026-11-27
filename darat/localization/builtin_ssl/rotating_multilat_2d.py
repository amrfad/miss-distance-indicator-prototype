"""
Rotating Multilateration 2D (5-Mic LOO)
Metode Linear Least Squares hiperbolik 2D dengan rotasi subset Leave-One-Out (LOO) dan agregasi median.
"""

from typing import List, Optional, Tuple, Dict, Any
from itertools import combinations
import numpy as np

DISPLAY_NAME = "Rotating Multilateration 2D"

_DEFAULT_C = 343.0
_DEFAULT_MIN_MICS = 4
_DEFAULT_MAX_NORM = 150.0


def _get_tdoa(tdoa_dict: dict, m_i: str, m_j: str, mic_names: List[str]) -> Optional[float]:
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


def multilaterate_subset_2d(
    mic_pos: np.ndarray,
    tdoa_data: dict,
    subset_indices: List[int],
    c: float,
    mic_names: List[str],
) -> Optional[np.ndarray]:
    """
    Closed-form hyperbolic linear multilateration 2D dari subset >= 4 mikrofon.

    Unknown: u = [p_x, p_y, w]^T dengan w = d0 = c*t0.
    Persamaan:
      2*(s_i - s_0).p - 2*c*tau*w = ||s_i||^2 - ||s_0||^2 - (c*tau)^2
    """
    ref = subset_indices[0]
    others = subset_indices[1:]
    s0 = mic_pos[ref]
    ref_name = mic_names[ref]

    A = []
    b = []
    for oi in others:
        tau = _get_tdoa(tdoa_data, ref_name, mic_names[oi], mic_names)
        if tau is None:
            return None

        so = mic_pos[oi]
        row = [2.0 * (so[0] - s0[0]), 2.0 * (so[1] - s0[1]), -2.0 * c * tau]
        A.append(row)
        b.append(float(np.dot(so, so) - np.dot(s0, s0) - (c * tau) ** 2))

    A_mat = np.array(A, dtype=float)
    b_vec = np.array(b, dtype=float)

    # Validasi rank: harus rank 3 (penuh untuk unknown px, py, w)
    if np.linalg.matrix_rank(A_mat) < 3:
        return None

    try:
        sol = np.linalg.lstsq(A_mat, b_vec, rcond=None)[0]
    except np.linalg.LinAlgError:
        return None

    if not np.all(np.isfinite(sol)):
        return None

    return sol[:2]  # [p_x, p_y]


def solve(event_data: dict, mic_positions: dict, config: dict) -> Tuple[Optional[List[float]], Optional[int], Optional[List[str]]]:
    """
    Estimasi posisi 2D [x, y] menggunakan Rotating Multilateration (LOO Median).

    Args:
        event_data:    Data event berisi kunci 'tdoa'
        mic_positions: Dict posisi mikrofon {nama_mic: {'x':.., 'y':..}}
        config:        Konfigurasi ground (speed_of_sound, dll.)

    Returns:
        (estimated_pos_2d, valid_subsets_count, clusters_info)
    """
    c = float(config.get("speed_of_sound", _DEFAULT_C))
    max_norm = float(config.get("multilat_max_norm", _DEFAULT_MAX_NORM))
    tdoa_data = event_data.get("tdoa", {})

    mic_names = sorted(list(mic_positions.keys()))
    n_mics = len(mic_names)

    if n_mics < 4:
        return None, 0, ["Rotating Multilat 2D membutuhkan minimal 4 mikrofon"]

    def _pos2d(m):
        p = mic_positions[m]
        if isinstance(p, dict):
            return [float(p["x"]), float(p["y"])]
        return [float(p[0]), float(p[1])]

    stations_arr = np.array([_pos2d(m) for m in mic_names], dtype=float)

    # Bangun subset Leave-One-Out (LOO) dengan rotasi referensi
    subsets = []
    if n_mics >= 5:
        # Jika M=6 -> 6 subset @ 5 mic; jika M=5 -> 5 subset @ 4 mic
        for k in range(n_mics):
            rest = [m for m in range(n_mics) if m != k]
            ref = (k + 1) % n_mics
            rest.remove(ref)
            subsets.append([ref] + rest)
    else:
        # Jika tepat 4 mikrofon, buat subset dengan tiap mikrofon sebagai referensi
        for ref in range(n_mics):
            others = [m for m in range(n_mics) if m != ref]
            subsets.append([ref] + others)

    pos_list = []
    for sub in subsets:
        pos2d = multilaterate_subset_2d(stations_arr, tdoa_data, sub, c=c, mic_names=mic_names)
        if pos2d is not None and np.all(np.isfinite(pos2d)):
            if np.linalg.norm(pos2d) <= max_norm:
                pos_list.append(pos2d)

    if not pos_list:
        return None, 0, ["Tidak ada subset multilaterasi yang menghasilkan solusi fisik valid"]

    # Agregasi Median untuk mengeliminasi outlier pasangan TDOA
    median_pos = np.median(pos_list, axis=0)

    info = [
        f"Rotating Multilat 2D: {len(pos_list)}/{len(subsets)} subset valid. Agregasi median: [{median_pos[0]:.2f}, {median_pos[1]:.2f}]"
    ]

    return [float(median_pos[0]), float(median_pos[1])], len(pos_list), info

