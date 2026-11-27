"""
Metode Pivot Elimination Ensemble

Inti Algoritma:
  Solver Pivot menyelesaikan sistem persamaan TDOA secara analitik melalui
  eliminasi variabel "pivot" (jarak ke mikrofon referensi, d0). Dengan memilih
  komponen d_vec yang paling besar sebagai pivot, persamaan dilinearkan sehingga
  (x, y) dapat dinyatakan sebagai fungsi linear dari z. Substitusi menghasilkan
  persamaan kuadrat dalam z, yang memberikan 0–2 kandidat posisi.

  Keunggulan dibandingkan Chan-Ho:
  - Tidak memerlukan estimasi d0 secara eksplisit di tahap awal.
  - Menghasilkan 2 kandidat per permutasi (ambiguitas diselesaikan dengan clustering).

  Dalam mode ensemble, 360 permutasi P(n,4) diuji dan hasilnya dikumpulkan.
  Kluster dengan residual TDOA terkecil dipilih sebagai estimasi akhir.

Kontrak Fungsi:
  solve(event_data, mic_positions, config) -> (estimated_pos, cluster_size, clusters_info)
"""

import itertools
from typing import List, Optional

import numpy as np

# ── Nama tampilan di UI ────────────────────────────────────────────────────────
DISPLAY_NAME = "Pivot Elimination (Ensemble)"

# ── Konstanta fallback ─────────────────────────────────────────────────────────
_DEFAULT_C = 343.0
_DEFAULT_CLUSTER_EPS = 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# INTI ALGORITMA: PIVOT ELIMINATION
# ═══════════════════════════════════════════════════════════════════════════════

def _solve_pivot_all_sols(stations: np.ndarray, d_vec: np.ndarray) -> List[np.ndarray]:
    """
    Solver Pivot Elimination untuk 4 stasiun.
    Mengembalikan kedua solusi kuadratik (0–2 kandidat posisi 3D).

    Args:
        stations: (4, 3) – posisi stasiun; [0] = referensi
        d_vec:    (3,)   – range difference dalam meter: d_i - d_0 untuk i=1,2,3
                           (positif = sumber lebih jauh dari stasiun i dibanding ref)
    """
    S0 = stations[0]
    S  = stations[1:]

    K0 = np.dot(S0, S0)
    K  = np.sum(S * S, axis=1)

    G = np.zeros((3, 4))
    for i in range(3):
        G[i, :3] = 2.0 * (S[i] - S0)
        G[i, 3]  = -2.0 * d_vec[i]

    h = K - K0 - d_vec**2

    # Pilih baris pivot: indeks dengan |d_vec| terbesar
    p = int(np.argmax(np.abs(d_vec)))
    d0_coef = G[p, 3]
    if abs(d0_coef) < 1e-12:
        return []

    non_p = [i for i in range(3) if i != p]

    A = np.zeros((2, 3))
    bv = np.zeros(2)
    for idx, k in enumerate(non_p):
        ratio = G[k, 3] / d0_coef
        A[idx] = G[k, :3] - ratio * G[p, :3]
        bv[idx] = h[k] - ratio * h[p]

    A_xy = A[:, :2]
    if abs(np.linalg.det(A_xy)) < 1e-12:
        return []

    inv = np.linalg.inv(A_xy)
    beta  = inv @ bv       # [bx, by]
    alpha = inv @ A[:, 2]  # [ax, ay]

    bx, by = beta
    ax, ay = alpha

    H0 = h[p] - G[p, 0] * bx - G[p, 1] * by
    H1 = G[p, 0] * ax + G[p, 1] * ay - G[p, 2]

    p1, p2, z0 = bx - S0[0], by - S0[1], S0[2]

    Ac = (ax**2 + ay**2 + 1.0) - (H1**2 / d0_coef**2)
    Bc = (-2.0 * p1 * ax - 2.0 * p2 * ay - 2.0 * z0) - (2.0 * H0 * H1 / d0_coef**2)
    Cc = (p1**2 + p2**2 + z0**2) - (H0**2 / d0_coef**2)

    disc = Bc**2 - 4.0 * Ac * Cc
    if disc < 0:
        disc = 0.0
    sq = np.sqrt(disc)

    if abs(Ac) < 1e-12:
        z_list = [-Cc / Bc] if abs(Bc) > 1e-12 else []
    else:
        z_list = [(-Bc + sq) / (2.0 * Ac), (-Bc - sq) / (2.0 * Ac)]

    return [np.array([bx - ax * z, by - ay * z, z]) for z in z_list]


def _get_tdoa(tdoa_dict: dict, m_i: str, m_j: str, mic_names) -> Optional[float]:
    """Ambil TDOA (tau_i - tau_j) dengan transitivitas 1-hop."""
    if f"{m_i}-{m_j}" in tdoa_dict:
        return tdoa_dict[f"{m_i}-{m_j}"]
    if f"{m_j}-{m_i}" in tdoa_dict:
        return -tdoa_dict[f"{m_j}-{m_i}"]
    candidates = [f"mic{k}" for k in range(mic_names)] if isinstance(mic_names, int) else list(mic_names)
    for mid in candidates:
        if mid in (m_i, m_j):
            continue
        v1 = tdoa_dict.get(f"{m_i}-{mid}")
        if v1 is None and f"{mid}-{m_i}" in tdoa_dict:
            v1 = -tdoa_dict[f"{mid}-{m_i}"]
        v2 = tdoa_dict.get(f"{m_j}-{mid}")
        if v2 is None and f"{mid}-{m_j}" in tdoa_dict:
            v2 = -tdoa_dict[f"{mid}-{m_j}"]
        if v1 is not None and v2 is not None:
            return v1 - v2
    return None


def _get_tdoa_residual(pos: np.ndarray, stations: np.ndarray,
                       tdoa_dict: dict, c: float, mic_names) -> float:
    """Hitung total residual TDOA semua pasang mikrofon terhadap posisi kandidat."""
    names = [f"mic{k}" for k in range(mic_names)] if isinstance(mic_names, int) else list(mic_names)
    n_mics = len(names)
    ranges = np.linalg.norm(stations - pos, axis=1)
    res = 0.0
    for u in range(n_mics):
        for v in range(u + 1, n_mics):
            val = _get_tdoa(tdoa_dict, names[u], names[v], names)
            if val is None:
                continue
            measured = val * c
            max_d = np.linalg.norm(stations[u] - stations[v])
            if abs(measured) > max_d + 0.1:
                continue
            res += (measured - (ranges[u] - ranges[v])) ** 2
    return res


def _cluster_solutions(solutions: list, eps: float = 1.0) -> list:
    """Kelompokkan solusi epsilon-neighborhood, desc by size."""
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


# ═══════════════════════════════════════════════════════════════════════════════
# FUNGSI SOLVE (KONTRAK WAJIB)
# ═══════════════════════════════════════════════════════════════════════════════

def solve(event_data: dict, mic_positions: dict, config: dict) -> tuple:
    """
    Estimasi posisi sumber suara menggunakan Pivot Elimination Ensemble.

    Args:
        event_data:    Data event berisi kunci 'tdoa'
        mic_positions: Dict {nama_mic: [x, y, z] atau {'x':..,'y':..,'z':..}}
        config:        Konfigurasi dari config_manager

    Returns:
        (estimated_pos, cluster_size, clusters_info)
    """
    c = config.get("speed_of_sound", _DEFAULT_C)
    cluster_eps = config.get("cluster_eps", _DEFAULT_CLUSTER_EPS)
    tdoa_data = event_data.get("tdoa", {})

    mic_names = sorted(list(mic_positions.keys()))
    n_mics = len(mic_names)

    if n_mics < 4:
        print(f"[ERROR] Pivot membutuhkan minimal 4 mikrofon, ditemukan {n_mics}")
        return None, None, None

    def _pos(m):
        p = mic_positions[m]
        if isinstance(p, dict):
            return [p["x"], p["y"], p["z"]]
        return list(p)

    stations_arr = np.array([_pos(m) for m in mic_names])

    candidates = []

    for perm in itertools.permutations(range(n_mics), 4):
        m0, m1, m2, m3 = perm
        sub_st = stations_arr[list(perm)]

        t1 = _get_tdoa(tdoa_data, mic_names[m0], mic_names[m1], mic_names)
        t2 = _get_tdoa(tdoa_data, mic_names[m0], mic_names[m2], mic_names)
        t3 = _get_tdoa(tdoa_data, mic_names[m0], mic_names[m3], mic_names)

        if any(v is None for v in [t1, t2, t3]):
            continue

        # d_vec = (dist_to_mi) - (dist_to_m0)  →  JSON tau_m0_mi × c, dinegasikan
        d_vec = np.array([-t1 * c, -t2 * c, -t3 * c])

        # Discard outlier fisik
        has_outlier = False
        for idx, sm in enumerate([m1, m2, m3]):
            if abs(d_vec[idx]) > np.linalg.norm(stations_arr[sm] - stations_arr[m0]):
                has_outlier = True
                break
        if has_outlier:
            continue

        for pos in _solve_pivot_all_sols(sub_st, d_vec):
            if np.all(np.abs(pos) < 50.0) and not np.any(np.isnan(pos)):
                candidates.append(pos)

    print(f"[INFO] Pivot: {len(candidates)} kandidat dari permutasi")

    if not candidates:
        print("[ERROR] Pivot: tidak ada solusi yang ditemukan")
        return None, None, None

    all_clusters = _cluster_solutions(candidates, eps=cluster_eps)

    valid = [cl for cl in all_clusters if len(cl) >= 5]
    if not valid:
        valid = all_clusters

    best_cluster, min_res = None, np.inf
    for cl in valid:
        mean_pos = np.mean(cl, axis=0)
        res = _get_tdoa_residual(mean_pos, stations_arr, tdoa_data, c, mic_names)
        if res < min_res:
            min_res = res
            best_cluster = cl

    if best_cluster is None:
        best_cluster = all_clusters[0] if all_clusters else candidates

    final_pos = np.mean(best_cluster, axis=0)

    clusters_info = []
    for idx, cl in enumerate(all_clusters):
        centroid = np.mean(cl, axis=0)
        info = (
            f"Cluster {idx+1}: {len(cl)} solusi, "
            f"centroid=[{centroid[0]:.2f}, {centroid[1]:.2f}, {centroid[2]:.2f}]"
        )
        clusters_info.append(info)

    print(
        f"[INFO] Posisi akhir (Pivot): "
        f"[{final_pos[0]:.2f}, {final_pos[1]:.2f}, {final_pos[2]:.2f}]"
    )
    return list(final_pos), len(best_cluster), clusters_info
