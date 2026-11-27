"""
Metode Chan-Ho WLS Ensemble (Weighted Least Squares)

Inti Algoritma:
  Metode Chan-Ho menyelesaikan TDOA secara analitik dalam dua tahap WLS:
  1. WLS kasar (linear least squares dengan bias range d0)
  2. WLS berbobot (menambahkan bobot dari estimasi jarak iterasi pertama)
  3. Koreksi kuadratik kecil untuk akurasi sub-meter

  Dalam mode ensemble, metode ini dijalankan pada 360 permutasi P(n,4) mikrofon,
  solusinya dikumpulkan, dikelompokkan, dan kluster terbaik (residual TDOA terkecil)
  dipilih.

Referensi:
  Chan, Y.T.; Ho, K.C. (1994), "A Simple and Efficient Estimator for
  Hyperbolic Location", IEEE Trans. Signal Processing, Vol. 42, No. 8.

Kontrak Fungsi:
  solve(event_data, mic_positions, config) -> (estimated_pos, cluster_size, clusters_info)
"""

import itertools
from typing import Optional

import numpy as np

# ── Nama tampilan di UI ────────────────────────────────────────────────────────
DISPLAY_NAME = "Chan-Ho WLS (Ensemble)"

# ── Konstanta fallback ─────────────────────────────────────────────────────────
_DEFAULT_C = 343.0
_DEFAULT_CLUSTER_EPS = 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# INTI ALGORITMA: CHAN-HO WLS 3D
# ═══════════════════════════════════════════════════════════════════════════════

def _chan_tdoa_3d(mic_positions: np.ndarray, tdoa: np.ndarray, c: float) -> Optional[np.ndarray]:
    """
    Solusi tertutup Chan's method (2-tahap WLS) untuk TDOA 3D.

    Args:
        mic_positions: (N, 3) – posisi mikrofon; indeks 0 = referensi
        tdoa:          (N-1,) – TDOA relatif ke mic_positions[0] (dalam detik)
                       positif berarti sumber lebih dekat ke referensi
        c:             kecepatan suara (m/s)

    Returns:
        estimasi posisi (3,) atau None jika gagal
    """
    s0 = mic_positions[0]
    si = mic_positions[1:]
    dd = tdoa * c  # delta_d dalam meter

    R0 = np.dot(s0, s0)
    Ri = np.sum(si * si, axis=1)

    # Tahap 1: WLS kasar
    G = np.hstack([-2.0 * (si - s0), -2.0 * dd.reshape(-1, 1)])
    h = (dd**2 - Ri + R0).reshape(-1, 1)

    try:
        theta1 = np.linalg.lstsq(G, h, rcond=None)[0].flatten()
    except np.linalg.LinAlgError:
        return s0.copy()

    pos_est = theta1[:3]
    d0_est = theta1[3]

    # Tahap 2: WLS berbobot
    if d0_est > 1e-10:
        di_est = np.linalg.norm(pos_est - si, axis=1)
        var_i = (di_est / c) ** 2 + (d0_est / c) ** 2
        W2 = np.diag(1.0 / (var_i + 1e-10))
        try:
            theta2 = np.linalg.lstsq(W2 @ G, W2 @ h, rcond=None)[0].flatten()
            pos_est = theta2[:3]
            d0_est = theta2[3]
        except np.linalg.LinAlgError:
            pass

    # Tahap 3: Koreksi kuadratik kecil
    d0_check = np.linalg.norm(pos_est - s0)
    if d0_check > 1e-10 and abs(d0_est) > 1e-10:
        corr = (d0_est - d0_check) / 2.0
        direction = (pos_est - s0) / d0_check
        pos_est = pos_est + corr * direction

    return pos_est


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
                continue  # skip outlier fisik
            res += (measured - (ranges[u] - ranges[v])) ** 2
    return res


def _cluster_solutions(solutions: list, eps: float = 1.0) -> list:
    """Kelompokkan solusi ke dalam cluster epsilon-neighborhood, desc by size."""
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
    Estimasi posisi sumber suara menggunakan Chan-Ho WLS Ensemble.

    Args:
        event_data:    Data event berisi kunci 'tdoa'
        mic_positions: Dict {nama_mic: [x, y, z] atau {'x':..,'y':..,'z':..}}
        config:        Konfigurasi dari config_manager

    Returns:
        (estimated_pos, cluster_size, clusters_info)
        - cluster_size = None jika tidak ada clustering
    """
    c = config.get("speed_of_sound", _DEFAULT_C)
    cluster_eps = config.get("cluster_eps", _DEFAULT_CLUSTER_EPS)
    tdoa_data = event_data.get("tdoa", {})

    mic_names = sorted(list(mic_positions.keys()))
    n_mics = len(mic_names)

    if n_mics < 4:
        print(f"[ERROR] Chan-Ho membutuhkan minimal 4 mikrofon, ditemukan {n_mics}")
        return None, None, None

    # Normalisasi posisi → numpy array terindeks sesuai mic_names
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
            # Konvensi Chan: tdoa_input = -(JSON tau_ref_minus_mi)
            tdoa_in = np.array([-t1, -t2, -t3])
            pos = _chan_tdoa_3d(sub_st, tdoa_in, c)
            if pos is not None and np.all(np.abs(pos) < 50.0) and not np.any(np.isnan(pos)):
                candidates.append(pos)
        except Exception:
            pass

    print(f"[INFO] Chan-Ho: {len(candidates)} kandidat dari permutasi")

    if not candidates:
        print("[ERROR] Chan-Ho: tidak ada solusi yang ditemukan")
        return None, None, None

    # Clustering dan pilih kluster terbaik (TDOA residual terkecil)
    all_clusters = _cluster_solutions(candidates, eps=cluster_eps)

    valid = [c_ for c_ in all_clusters if len(c_) >= 5]
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
        f"[INFO] Posisi akhir (Chan-Ho): "
        f"[{final_pos[0]:.2f}, {final_pos[1]:.2f}, {final_pos[2]:.2f}]"
    )
    return list(final_pos), len(best_cluster), clusters_info
