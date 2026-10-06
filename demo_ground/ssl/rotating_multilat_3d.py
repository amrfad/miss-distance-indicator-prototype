"""
Metode 5-Mic Leave-One-Out Rotating Multilateration (Supersonic CPA)

Inti Algoritma:
  1. Multilaterasi hiperbolik closed-form linear dengan eliminasi kuadrat.
  2. Membutuhkan minimal 5 mikrofon (m = 5) untuk menghasilkan m - 1 = 4 persamaan linear.
     Sistem berstatus rank penuh (rank 4 untuk px, py, pz, t0), sehingga menyelesaikan
     kelemahan underdetermined rank-3 pada formulasi 4-mikrofon konvensional.
  3. Skema Leave-One-Out (LOO) berotasi:
     - Untuk array 6-mikrofon (M = 6), dibentuk 6 subset 5-mikrofon.
     - Setiap subset mengecualikan mic k dan menetapkan referensi ke (k + 1) % M.
     - Setiap mikrofon menjadi referensi tepat 1 kali.
  4. Outlier Resistance:
     - Satu pasangan TDOA yang rusak hanya mempengaruhi maksimal 2 dari 6 subset.
     - Agregasi median secara sempurna mengeliminasi outlier tersebut.

Kontrak Fungsi:
  solve(event_data, mic_positions, config) -> (estimated_pos, valid_subsets_count, clusters_info)
"""

from typing import List, Optional, Tuple, Dict, Any
from itertools import combinations
import numpy as np

# ── Nama tampilan di UI ────────────────────────────────────────────────────────
DISPLAY_NAME = "Rotating Multilateration (5-Mic LOO)"

# ── Konstanta default ──────────────────────────────────────────────────────────
_DEFAULT_C = 343.0
_DEFAULT_MIN_MICS = 5
_DEFAULT_MAX_NORM = 200.0
_DEFAULT_AGGREGATE = "median"


def _get_tdoa(tdoa_dict: dict, m_i: str, m_j: str, n_mics: int) -> Optional[float]:
    """
    Ambil nilai TDOA tau_ij = t_i - t_j (detik) dengan transitivitas 1-hop.
    Mendukung format key 'micX-micY' maupun tuple (i, j).
    """
    # 1. Cek string 'micX-micY'
    k1 = f"{m_i}-{m_j}"
    if k1 in tdoa_dict:
        return float(tdoa_dict[k1])
    k2 = f"{m_j}-{m_i}"
    if k2 in tdoa_dict:
        return -float(tdoa_dict[k2])

    # 2. Cek tuple integer jika m_i / m_j formatnya 'micX'
    try:
        idx_i = int(m_i.replace("mic", ""))
        idx_j = int(m_j.replace("mic", ""))
        if (idx_i, idx_j) in tdoa_dict:
            return float(tdoa_dict[(idx_i, idx_j)])
        if (idx_j, idx_i) in tdoa_dict:
            return -float(tdoa_dict[(idx_j, idx_i)])
    except ValueError:
        pass

    # 3. Transitivitas 1-hop
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


def multilaterate_subset(
    mic_pos: np.ndarray,
    tdoa_data: dict,
    subset_indices: List[int],
    c: float,
    n_mics: int
) -> Tuple[Optional[np.ndarray], Optional[float]]:
    """
    Closed-form hyperbolic linear multilateration dari subset >= 5 mikrofon.

    Ref = subset_indices[0]. Untuk tiap oi in subset_indices[1:]:
      2*(ro - r0).p - 2*c*tau*w = ||ro||^2 - ||r0||^2 - (c*tau)^2
    dengan w = c*t0, unknown u = [p_x, p_y, p_z, w]^T.

    Returns:
        (pos, t0) atau (None, None) jika rank < 4 atau singular.
    """
    ref = subset_indices[0]
    others = subset_indices[1:]
    r0 = mic_pos[ref]

    A = []
    b = []
    for oi in others:
        tau = _get_tdoa(tdoa_data, f"mic{ref}", f"mic{oi}", n_mics)
        if tau is None:
            return None, None

        ro = mic_pos[oi]
        row = list(2.0 * (ro - r0)) + [-2.0 * c * tau]
        A.append(row)
        b.append(float(np.dot(ro, ro) - np.dot(r0, r0) - (c * tau) ** 2))

    A = np.array(A, dtype=float)
    b_vec = np.array(b, dtype=float)

    # Validasi rank: harus rank 4 (rank penuh untuk unknown px, py, pz, w)
    if np.linalg.matrix_rank(A) < 4:
        return None, None

    try:
        sol, residuals, rank, sv = np.linalg.lstsq(A, b_vec, rcond=None)
    except np.linalg.LinAlgError:
        return None, None

    if not np.all(np.isfinite(sol)):
        return None, None

    pos = sol[:3]
    t0 = sol[3] / c
    return pos, t0


# ═══════════════════════════════════════════════════════════════════════════════
# FUNGSI SOLVE (KONTRAK WAJIB SSL REGISTRY)
# ═══════════════════════════════════════════════════════════════════════════════

def solve(event_data: dict, mic_positions: dict, config: dict) -> tuple:
    """
    Estimasi posisi CPA proyektil menggunakan 5-Mic LOO Rotating Multilateration.

    Args:
        event_data:    Data event berisi kunci 'tdoa'
        mic_positions: Dict posisi mikrofon {nama_mic: [x, y, z]}
        config:        Konfigurasi ground (speed_of_sound, dll.)

    Returns:
        (estimated_pos, valid_subsets_count, clusters_info)
    """
    c = float(config.get("speed_of_sound", _DEFAULT_C))
    min_mics = int(config.get("multilat_min_mics", _DEFAULT_MIN_MICS))
    max_norm = float(config.get("multilat_max_norm", _DEFAULT_MAX_NORM))
    aggregate = str(config.get("multilat_aggregate", _DEFAULT_AGGREGATE)).lower()
    tdoa_data = event_data.get("tdoa", {})

    mic_names = list(mic_positions.keys())
    n_mics = len(mic_names)

    if n_mics < min_mics:
        msg = f"[RotatingMultilat] Membutuhkan minimal {min_mics} mikrofon, ditemukan {n_mics}"
        print(f"[ERROR] {msg}")
        return None, 0, [msg]

    def _pos(m):
        p = mic_positions[m]
        if isinstance(p, dict):
            return [p["x"], p["y"], p["z"]]
        return list(p)

    stations_arr = np.array([_pos(f"mic{k}") for k in range(n_mics)], dtype=float)

    # Buat subset mikrofon dengan referensi berotasi
    if min_mics == n_mics - 1:
        # Kasus Leave-One-Out (LOO), contoh M=6 -> 6 subset 5-mikrofon
        subsets = []
        for k in range(n_mics):
            rest = [m for m in range(n_mics) if m != k]
            ref = (k + 1) % n_mics
            rest.remove(ref)
            subsets.append([ref] + rest)
    elif min_mics == n_mics:
        # Tepat min_mics (misal array 5 mik): 1 subset
        subsets = [list(range(n_mics))]
    else:
        # Kombinasi umum C(n_mics, min_mics)
        subsets = [list(s) for s in combinations(range(n_mics), min_mics)]

    pos_list = []
    subsets_info = []

    for idx, sub in enumerate(subsets):
        ref = sub[0]
        pos, t0 = multilaterate_subset(stations_arr, tdoa_data, sub, c=c, n_mics=n_mics)
        if pos is not None and np.all(np.isfinite(pos)):
            norm_val = float(np.linalg.norm(pos))
            if norm_val <= max_norm:
                pos_list.append(pos)
                info = (
                    f"Subset {idx+1} (Ref=mic{ref}, Mics={[f'mic{m}' for m in sub]}): "
                    f"pos=[{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}] m, norm={norm_val:.2f} m"
                )
                subsets_info.append(info)
            else:
                subsets_info.append(
                    f"Subset {idx+1} (Ref=mic{ref}): ditolak (norm={norm_val:.1f} m > {max_norm} m)"
                )
        else:
            subsets_info.append(f"Subset {idx+1} (Ref=mic{ref}): gagal kalkulasi / singular")

    if not pos_list:
        print("[WARN] [RotatingMultilat] Tidak ada subset yang menghasilkan solusi fisik valid.")
        return None, 0, subsets_info

    pos_arr = np.array(pos_list)

    if aggregate == "mean":
        pos_est = np.mean(pos_arr, axis=0)
    elif aggregate == "cluster":
        # Titik yang paling dekat dengan nilai median
        ctr = np.median(pos_arr, axis=0)
        dists = np.linalg.norm(pos_arr - ctr, axis=1)
        pos_est = pos_arr[np.argmin(dists)]
    else:  # default 'median'
        pos_est = np.median(pos_arr, axis=0)

    pos_est = [round(float(v), 4) for v in pos_est]
    print(f"[INFO] Posisi akhir ({DISPLAY_NAME}): {pos_est} (dari {len(pos_list)} subset lulus)")

    return pos_est, len(pos_list), subsets_info
