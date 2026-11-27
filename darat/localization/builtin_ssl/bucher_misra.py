"""
Metode Bucher-Misra 3D Ensemble (Metode Built-in Default)

Inti Algoritma:
  Menyelesaikan persamaan hyperboloid dari 4 stasiun secara analitik (closed-form).
  Untuk mendapatkan estimasi yang robust, metode ini dijalankan dalam mode ensemble:
  seluruh kombinasi 4-permutasi mikrofon diuji, kandidat solusi yang dihasilkan
  dikumpulkan, lalu dikelompokkan (clustering). Kluster terbesar (paling konsisten)
  dipilih sebagai hasil akhir.

  Keunggulan:
  - Solusi analitik eksak, bukan iteratif.
  - Tahan terhadap konfigurasi singular melalui mode ensemble.

Referensi:
  Bucher & Misra (2002), "A Simplifed Recursive Algorithm for Ambiguity Resolution..."

Kontrak Fungsi:
  solve(event_data, mic_positions, config) -> (estimated_pos, cluster_size, clusters_info)
"""

import math
import itertools
from itertools import combinations
from typing import Iterable, List, Optional, Sequence, Tuple

import numpy as np

# ── Nama tampilan di UI ────────────────────────────────────────────────────────
DISPLAY_NAME = "Bucher-Misra (Ensemble)"

# ── Konstanta fallback ─────────────────────────────────────────────────────────
_DEFAULT_C = 343.0
_DEFAULT_CLUSTER_EPS = 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# INTI ALGORITMA
# ═══════════════════════════════════════════════════════════════════════════════

class BucherMisraError(ValueError):
    """Dilempar bila kondisi geometri membuat sistem singular/tidak terdefinisi."""


def _safe_div(num: float, den: float, name: str, eps: float = 1e-12) -> float:
    if abs(den) < eps:
        raise BucherMisraError(f"Penyebut nyaris nol pada '{name}'")
    return num / den


def _solve_4station(
    stations_xyz: Sequence[Iterable[float]],
    ranges_m: Sequence[float],
    eps: float = 1e-12,
) -> List[Tuple[float, float, float]]:
    """
    Solusi tertutup Bucher-Misra 3D untuk tepat 4 stasiun dan 4 range.
    Mengembalikan 0–2 kandidat posisi (x, y, z).
    """
    (xi, yi, zi), (xj, yj, zj), (xk, yk, zk), (xl, yl, zl) = [
        tuple(map(float, p)) for p in stations_xyz
    ]
    Ri, Rj, Rk, Rl = [float(r) for r in ranges_m]

    xji, yji, zji = xj - xi, yj - yi, zj - zi
    xki, yki, zki = xk - xi, yk - yi, zk - zi
    xjk, yjk, zjk = xj - xk, yj - yk, zj - zk
    xlk, ylk, zlk = xl - xk, yl - yk, zl - zk

    Rij = Ri - Rj
    Rik = Ri - Rk
    Rkj = Rk - Rj
    Rkl = Rk - Rl

    den1 = Rij * yki - Rik * yji
    A = _safe_div(Rik * xji - Rij * xki, den1, "A")
    B = _safe_div(Rik * zji - Rij * zki, den1, "B")
    C_num = (
        Rik * (Rij**2 + xi**2 - xj**2 + yi**2 - yj**2 + zi**2 - zj**2)
        - Rij * (Rik**2 + xi**2 - xk**2 + yi**2 - yk**2 + zi**2 - zk**2)
    )
    C_ = _safe_div(C_num, 2.0 * den1, "C")

    den2 = Rkj * ylk - Rkl * yjk
    D = _safe_div(Rkl * xjk - Rkj * xlk, den2, "D")
    E = _safe_div(Rkl * zjk - Rkj * zlk, den2, "E")
    F_num = (
        Rkl * (Rkj**2 + xk**2 - xj**2 + yk**2 - yj**2 + zk**2 - zj**2)
        - Rkj * (Rkl**2 + xk**2 - xl**2 + yk**2 - yl**2 + zk**2 - zl**2)
    )
    F_ = _safe_div(F_num, 2.0 * den2, "F")

    G = _safe_div(E - B, A - D, "G")
    H = _safe_div(F_ - C_, A - D, "H")
    I_ = A * G + B
    J_ = A * H + C_

    K = (
        Rik**2 + xi**2 - xk**2 + yi**2 - yk**2 + zi**2 - zk**2
        + 2.0 * xki * H + 2.0 * yki * J_
    )
    L = 2.0 * (xki * G + yki * I_ + zki)

    M = 4.0 * Rik**2 * (G**2 + I_**2 + 1.0) - L**2
    N_ = 8.0 * Rik**2 * (G * (xi - H) + I_ * (yi - J_) + zi) + 2.0 * L * K
    O_ = 4.0 * Rik**2 * ((xi - H) ** 2 + (yi - J_) ** 2 + zi**2) - K**2

    if abs(M) < 1e-12:
        z_cands = [O_ / N_] if abs(N_) > 1e-12 else []
    else:
        half = N_ / (2.0 * M)
        disc = half**2 - O_ / M
        if disc < -1e-14:
            return []
        rt = math.sqrt(max(0.0, disc))
        z_cands = [half + rt, half - rt]

    sols = []
    for z in z_cands:
        sols.append((float(G * z + H), float(I_ * z + J_), float(z)))

    # Deduplikasi
    uniq: List[Tuple[float, float, float]] = []
    for s in sols:
        if not any(np.linalg.norm(np.array(s) - np.array(u)) < 1e-8 for u in uniq):
            uniq.append(s)
    return uniq


def _get_tdoa(tdoa_dict: dict, m_i: str, m_j: str, mic_names) -> Optional[float]:
    """Ambil nilai TDOA (tau_i - tau_j) dengan transitivitas 1-hop."""
    if f"{m_i}-{m_j}" in tdoa_dict:
        return tdoa_dict[f"{m_i}-{m_j}"]
    if f"{m_j}-{m_i}" in tdoa_dict:
        return -tdoa_dict[f"{m_j}-{m_i}"]
    # Transitivitas
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


def _cluster_solutions(
    solutions: list, eps: float = 1.0
) -> List[List[Tuple[float, float, float]]]:
    """
    Kelompokkan solusi ke dalam cluster epsilon-neighborhood.
    Returns: list of clusters diurutkan desc by size.
    """
    if not solutions:
        return []

    all_clusters = []
    assigned = set()

    for i, s1 in enumerate(solutions):
        if i in assigned:
            continue
        cluster = [s1]
        assigned.add(i)
        for j, s2 in enumerate(solutions):
            if j in assigned:
                continue
            if any(np.linalg.norm(np.array(s2) - np.array(m)) < eps for m in cluster):
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
    Estimasi posisi sumber suara menggunakan Bucher-Misra Ensemble.

    Args:
        event_data:    Data event berisi kunci 'tdoa' (dict pasangan mic → detik)
        mic_positions: Dict {nama_mic: [x, y, z] atau {'x':..,'y':..,'z':..}}
        config:        Konfigurasi dari config_manager (speed_of_sound, cluster_eps, dll.)

    Returns:
        (estimated_pos, cluster_size, clusters_info)
        - estimated_pos: list/tuple [x, y, z] atau None
        - cluster_size : int (jumlah solusi dalam kluster terpilih) atau None
        - clusters_info: list of str (deskripsi tiap kluster) atau None
    """
    c = config.get("speed_of_sound", _DEFAULT_C)
    cluster_eps = config.get("cluster_eps", _DEFAULT_CLUSTER_EPS)
    tdoa_data = event_data.get("tdoa", {})

    mic_names = list(mic_positions.keys())
    n_mics = len(mic_names)

    if n_mics < 4:
        print(f"[ERROR] Bucher-Misra membutuhkan minimal 4 mikrofon, ditemukan {n_mics}")
        return None, 0, None

    # Normalisasi format posisi mikrofon
    def _pos(m):
        p = mic_positions[m]
        if isinstance(p, dict):
            return [p["x"], p["y"], p["z"]]
        return list(p)

    all_solutions = []
    total_attempts = 0
    successful_attempts = 0

    mic_combinations = list(combinations(mic_names, 4))
    print(f"\n[INFO] Bucher-Misra: {len(mic_combinations)} kombinasi × permutasi")

    for combo in mic_combinations:
        for perm in itertools.permutations(combo):
            m_i, m_j, m_k, m_l = perm
            total_attempts += 1

            stations = [_pos(m) for m in (m_i, m_j, m_k, m_l)]

            try:
                Rij = _get_tdoa(tdoa_data, m_i, m_j, mic_names)
                Rik = _get_tdoa(tdoa_data, m_i, m_k, mic_names)
                Rkl = _get_tdoa(tdoa_data, m_k, m_l, mic_names)

                if any(v is None for v in [Rij, Rik, Rkl]):
                    continue

                d_Rij = Rij * c
                d_Rik = Rik * c
                d_Rkl = Rkl * c

                # Discard outlier fisik
                max_ij = np.linalg.norm(np.array(stations[1]) - np.array(stations[0]))
                max_ik = np.linalg.norm(np.array(stations[2]) - np.array(stations[0]))
                max_kl = np.linalg.norm(np.array(stations[3]) - np.array(stations[2]))
                if abs(d_Rij) > max_ij or abs(d_Rik) > max_ik or abs(d_Rkl) > max_kl:
                    continue

                ranges_m = [0.0, -d_Rij, -d_Rik, -d_Rik - d_Rkl]
                sols = _solve_4station(stations, ranges_m)

                for s in sols:
                    pos = np.array(s)
                    if np.all(np.abs(pos) < 50.0) and not np.any(np.isnan(pos)):
                        all_solutions.append(s)
                        successful_attempts += 1

            except (BucherMisraError, ValueError, ZeroDivisionError):
                continue

    print(f"[INFO] Percobaan: {total_attempts}, Berhasil: {successful_attempts}")

    if not all_solutions:
        print("[ERROR] Bucher-Misra: tidak ada solusi yang ditemukan")
        return None, 0, None

    print(f"[INFO] {len(all_solutions)} kandidat solusi terkumpul")

    all_clusters = _cluster_solutions(all_solutions, eps=cluster_eps)
    if not all_clusters:
        return None, 0, None

    clusters_info = []
    for idx, cluster in enumerate(all_clusters):
        centroid = np.mean(cluster, axis=0)
        info = (
            f"Cluster {idx+1}: {len(cluster)} solusi, "
            f"centroid=[{centroid[0]:.2f}, {centroid[1]:.2f}, {centroid[2]:.2f}]"
        )
        print(f"  {info}")
        clusters_info.append(info)

    final_cluster = all_clusters[0]
    final_pos = np.median(final_cluster, axis=0)

    print(
        f"[INFO] Posisi akhir (Bucher-Misra): "
        f"[{final_pos[0]:.2f}, {final_pos[1]:.2f}, {final_pos[2]:.2f}]"
    )
    return list(final_pos), len(final_cluster), clusters_info
