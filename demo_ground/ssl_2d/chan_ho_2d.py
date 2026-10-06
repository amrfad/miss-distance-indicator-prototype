"""
Chan-Ho WLS 2D (Ensemble)
Metode analitik Two-Stage Weighted Least Squares yang diadaptasi khusus untuk bidang 2D (X, Y).
"""

import itertools
from typing import List, Optional, Tuple, Dict, Any
import numpy as np

DISPLAY_NAME = "Chan-Ho WLS 2D"

_DEFAULT_C = 343.0
_DEFAULT_CLUSTER_EPS = 1.0


def _chan_tdoa_2d(mic_positions: np.ndarray, tdoa: np.ndarray, c: float) -> Optional[np.ndarray]:
    """
    Solusi analitik Chan's method (2-tahap WLS) untuk TDOA 2D.

    Args:
        mic_positions: (N, 2) – posisi mikrofon (2D); indeks 0 = referensi
        tdoa:          (N-1,) – TDOA relatif ke mic_positions[0] (detik)
        c:             kecepatan suara (m/s)

    Returns:
        estimasi posisi (2,) [x, y] atau None jika gagal
    """
    s0 = mic_positions[0]
    si = mic_positions[1:]
    dd = tdoa * c  # delta_d dalam meter (d_i - d_0)

    R0 = np.dot(s0, s0)
    Ri = np.sum(si * si, axis=1)

    # Tahap 1: WLS Kasar (Unknown: [x, y, d0])
    G = np.hstack([-2.0 * (si - s0), -2.0 * dd.reshape(-1, 1)])
    h = (dd**2 - Ri + R0).reshape(-1, 1)

    try:
        theta1 = np.linalg.lstsq(G, h, rcond=None)[0].flatten()
    except np.linalg.LinAlgError:
        return s0.copy()

    pos_est = theta1[:2]
    d0_est = theta1[2]

    # Tahap 2: WLS Berbobot
    if d0_est > 1e-6:
        di_est = np.linalg.norm(pos_est - si, axis=1)
        var_i = (di_est / c) ** 2 + (d0_est / c) ** 2
        W = np.diag(1.0 / (var_i + 1e-10))
        try:
            WG = W @ G
            Wh = W @ h
            theta2 = np.linalg.lstsq(WG, Wh, rcond=None)[0].flatten()
            pos_est = theta2[:2]
            d0_est = theta2[2]
        except np.linalg.LinAlgError:
            pass

    # Tahap 1 & Tahap 2 secara analitik memecahkan [x, y, d0] di mana d0 menyerap
    # jarak 3D r0 = sqrt((x-x0)^2 + (y-y0)^2 + z^2). Dengan demikian, pos_est [:2]
    # adalah koordinat horizontal [x, y] murni yang kebal terhadap beda elevasi z.
    return pos_est


def _get_tdoa(tdoa_dict: dict, m_i: str, m_j: str, n_mics: int) -> Optional[float]:
    """Ambil TDOA (tau_i - tau_j) dengan transitivitas 1-hop."""
    if f"{m_i}-{m_j}" in tdoa_dict:
        return float(tdoa_dict[f"{m_i}-{m_j}"])
    if f"{m_j}-{m_i}" in tdoa_dict:
        return -float(tdoa_dict[f"{m_j}-{m_i}"])
    for k in range(n_mics):
        mid = f"mic{k}"
        if mid in (m_i, m_j):
            continue
        v1 = tdoa_dict.get(f"{m_i}-{mid}") or (
            -tdoa_dict[f"{mid}-{m_i}"] if f"{mid}-{m_i}" in tdoa_dict else None
        )
        v2 = tdoa_dict.get(f"{m_j}-{mid}") or (
            -tdoa_dict[f"{mid}-{m_j}"] if f"{mid}-{m_j}" in tdoa_dict else None
        )
        if v1 is not None and v2 is not None:
            return float(v1) - float(v2)
    return None


def _get_tdoa_residual(
    pos: np.ndarray, stations: np.ndarray, tdoa_dict: dict, c: float, n_mics: int
) -> float:
    """Hitung total residual TDOA semua pasang mikrofon terhadap posisi kandidat 2D."""
    ranges = np.linalg.norm(stations - pos, axis=1)
    res = 0.0
    for u in range(n_mics):
        for v in range(u + 1, n_mics):
            val = _get_tdoa(tdoa_dict, f"mic{u}", f"mic{v}", n_mics)
            if val is None:
                continue
            measured = val * c
            max_d = np.linalg.norm(stations[u] - stations[v])
            if abs(measured) > max_d + 0.1:
                continue
            res += (measured - (ranges[u] - ranges[v])) ** 2
    return res


def _cluster_solutions(solutions: list, eps: float = 1.0) -> list:
    """Kelompokkan solusi 2D ke dalam cluster epsilon-neighborhood."""
    if not solutions:
        return []
    all_clusters = []
    assigned = set()
    arr = [np.array(s) for s in solutions]
    for i, s1 in enumerate(arr):
        if i in assigned:
            continue
        cluster = [s1]
        assigned.add(i)
        for j, s2 in enumerate(arr):
            if j in assigned:
                continue
            if any(np.linalg.norm(s2 - m) < eps for m in cluster):
                cluster.append(s2)
                assigned.add(j)
        all_clusters.append(cluster)
    all_clusters.sort(key=len, reverse=True)
    return all_clusters


def solve(event_data: dict, mic_positions: dict, config: dict) -> Tuple[Optional[List[float]], Optional[int], Optional[List[str]]]:
    """
    Estimasi posisi sumber suara 2D [x, y] menggunakan Chan-Ho WLS Ensemble.

    Args:
        event_data:    Data event berisi kunci 'tdoa'
        mic_positions: Dict {nama_mic: {'x':.., 'y':..}}
        config:        Konfigurasi ground (speed_of_sound, cluster_eps)

    Returns:
        (estimated_pos_2d, cluster_size, clusters_info)
    """
    c = float(config.get("speed_of_sound", _DEFAULT_C))
    cluster_eps = float(config.get("cluster_eps", _DEFAULT_CLUSTER_EPS))
    tdoa_data = event_data.get("tdoa", {})

    mic_names = sorted(list(mic_positions.keys()))
    n_mics = len(mic_names)

    if n_mics < 4:
        return None, None, ["Chan-Ho 2D membutuhkan minimal 4 mikrofon"]

    def _pos2d(m):
        p = mic_positions[m]
        if isinstance(p, dict):
            return [float(p["x"]), float(p["y"])]
        return [float(p[0]), float(p[1])]

    stations_arr = np.array([_pos2d(f"mic{k}") for k in range(n_mics)])

    candidates = []

    # Permutasi 4 mikrofon untuk ensemble
    for perm in itertools.permutations(range(n_mics), 4):
        m0, m1, m2, m3 = perm
        sub_st = stations_arr[list(perm)]

        t1 = _get_tdoa(tdoa_data, f"mic{m0}", f"mic{m1}", n_mics)
        t2 = _get_tdoa(tdoa_data, f"mic{m0}", f"mic{m2}", n_mics)
        t3 = _get_tdoa(tdoa_data, f"mic{m0}", f"mic{m3}", n_mics)

        if any(v is None for v in [t1, t2, t3]):
            continue

        # Discard outlier fisik
        d_vec = np.array([-t1 * c, -t2 * c, -t3 * c])
        has_outlier = False
        for idx, sm in enumerate([m1, m2, m3]):
            if abs(d_vec[idx]) > np.linalg.norm(stations_arr[sm] - stations_arr[m0]):
                has_outlier = True
                break
        if has_outlier:
            continue

        try:
            tdoa_in = np.array([-t1, -t2, -t3])
            pos = _chan_tdoa_2d(sub_st, tdoa_in, c)
            if pos is not None and np.all(np.abs(pos) < 100.0) and not np.any(np.isnan(pos)):
                candidates.append(pos)
        except Exception:
            pass

    if not candidates:
        return None, None, ["Tidak ada kandidat posisi Chan-Ho 2D yang konvergen"]

    all_clusters = _cluster_solutions(candidates, eps=cluster_eps)
    valid = [cl for cl in all_clusters if len(cl) >= 4]
    if not valid:
        valid = all_clusters

    best_cluster = None
    min_res = np.inf
    for cl in valid:
        mean_pos = np.mean(cl, axis=0)
        res = _get_tdoa_residual(mean_pos, stations_arr, tdoa_data, c, n_mics)
        if res < min_res:
            min_res = res
            best_cluster = cl

    if best_cluster is None:
        best_cluster = all_clusters[0] if all_clusters else candidates

    final_pos = np.mean(best_cluster, axis=0)
    clusters_info = [
        f"Chan-Ho 2D: {len(candidates)} kandidat, {len(all_clusters)} cluster, terpilih cluster size {len(best_cluster)}"
    ]

    return [float(final_pos[0]), float(final_pos[1])], len(best_cluster), clusters_info
