"""
Metode Consensus Function

Inti Algoritma:
  Consensus Function adalah metode yang tidak bergantung pada satu solver tunggal.
  Ia mengumpulkan kandidat posisi dari beberapa solver (Bucher-Misra, Chan-Ho,
  dan Pivot Elimination) secara serentak dari 360 permutasi, kemudian untuk setiap
  kandidat menghitung "Consensus Score" — jumlah pasang mikrofon yang TDOA-nya
  konsisten (dalam batas toleransi ε) dengan posisi kandidat tersebut.

  Langkah-langkah:
  1. Kumpulkan ±1080 kandidat (3 solver × 360 permutasi)
  2. Bangun tabel TDOA untuk semua C(n,2) pasang mikrofon
  3. Pilih kandidat dengan Consensus Score tertinggi
  4. Lakukan local grid refinement ±refine_radius di sekitar pemenang
  5. Polish dengan Nelder-Mead untuk akurasi sub-grid

  Keunggulan:
  - Sangat tahan terhadap outlier (hanya butuh mayoritas konsisten)
  - Tidak bergantung pada pilihan mikrofon referensi
  - Menggabungkan kekuatan dari tiga metode sekaligus

Referensi:
  Combinasi Bucher-Misra, Chan-Ho, dan Pivot dengan scoring konsensus.

Kontrak Fungsi:
  solve(event_data, mic_positions, config) -> (estimated_pos, cluster_size, clusters_info)
  (cluster_size dan clusters_info di-set ke None karena metode ini tidak berbasis clustering)
"""

import math
import itertools
from typing import List, Optional, Tuple

import numpy as np
from scipy.optimize import minimize

# ── Nama tampilan di UI ────────────────────────────────────────────────────────
DISPLAY_NAME = "Consensus Function"

# ── Konstanta fallback ─────────────────────────────────────────────────────────
_DEFAULT_C = 343.0
_DEFAULT_EPS_SEC = 0.0005    # toleransi TDOA 0.5 ms
_DEFAULT_REFINE_RADIUS = 0.5  # m
_DEFAULT_REFINE_STEP = 0.1    # m


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITAS TDOA
# ═══════════════════════════════════════════════════════════════════════════════

def _get_tdoa(tdoa_dict: dict, m_i: str, m_j: str, n_mics: int) -> Optional[float]:
    if f"{m_i}-{m_j}" in tdoa_dict:
        return tdoa_dict[f"{m_i}-{m_j}"]
    if f"{m_j}-{m_i}" in tdoa_dict:
        return -tdoa_dict[f"{m_j}-{m_i}"]
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
            return v1 - v2
    return None


def _build_tdoa_table(tdoa_dict: dict, stations: np.ndarray, c: float, n_mics: int):
    """Bangun tabel TDOA: list of (u, v, tdoa_seconds, max_dist, is_valid)."""
    table = []
    for u in range(n_mics):
        for v in range(u + 1, n_mics):
            val = _get_tdoa(tdoa_dict, f"mic{u}", f"mic{v}", n_mics)
            if val is None:
                continue
            measured_m = val * c
            max_d = np.linalg.norm(stations[u] - stations[v])
            is_valid = abs(measured_m) <= max_d + 0.1
            table.append((u, v, val, max_d, is_valid))
    return table


# ═══════════════════════════════════════════════════════════════════════════════
# CONSENSUS SCORING
# ═══════════════════════════════════════════════════════════════════════════════

def _consensus_score(pos: np.ndarray, tdoa_table: list, stations: np.ndarray,
                     c: float, eps_sec: float) -> Tuple[int, float]:
    """
    Hitung Consensus Score dan Weighted Score untuk posisi kandidat.

    Returns:
        (score, weighted_score)
    """
    pos = np.array(pos)
    score = 0
    weighted = 0.0

    for u, v, tdoa_meas, max_d, is_valid in tdoa_table:
        if not is_valid:
            continue
        du = np.linalg.norm(pos - stations[u])
        dv = np.linalg.norm(pos - stations[v])
        tdoa_pred = (du - dv) / c
        res = abs(tdoa_pred - tdoa_meas)
        if res < eps_sec:
            score += 1
        weighted += math.exp(-0.5 * (res / (eps_sec / 2.0)) ** 2)

    return score, weighted


def _consensus_objective(pos, tdoa_table, stations, c, eps_sec):
    _, ws = _consensus_score(pos, tdoa_table, stations, c, eps_sec)
    return -ws


# ═══════════════════════════════════════════════════════════════════════════════
# SUB-SOLVER INTERNAL (versi mini tanpa STATIONS global)
# ═══════════════════════════════════════════════════════════════════════════════

class _BucherMisraError(ValueError):
    pass


def _bm_solve_4(stations_xyz, ranges_m, eps=1e-12):
    """Bucher-Misra closed-form untuk 4 stasiun."""
    (xi,yi,zi),(xj,yj,zj),(xk,yk,zk),(xl,yl,zl) = [
        tuple(map(float, p)) for p in stations_xyz
    ]
    Ri, Rj, Rk, Rl = [float(r) for r in ranges_m]

    def sd(n, d, name):
        if abs(d) < eps:
            raise _BucherMisraError(f"Zero denom: {name}")
        return n / d

    xji,yji,zji = xj-xi,yj-yi,zj-zi
    xki,yki,zki = xk-xi,yk-yi,zk-zi
    xjk,yjk,zjk = xj-xk,yj-yk,zj-zk
    xlk,ylk,zlk = xl-xk,yl-yk,zl-zk

    Rij,Rik,Rkj,Rkl = Ri-Rj,Ri-Rk,Rk-Rj,Rk-Rl
    d1 = Rij*yki - Rik*yji
    A = sd(Rik*xji-Rij*xki, d1, "A")
    B = sd(Rik*zji-Rij*zki, d1, "B")
    C_ = sd(Rik*(Rij**2+xi**2-xj**2+yi**2-yj**2+zi**2-zj**2)
            - Rij*(Rik**2+xi**2-xk**2+yi**2-yk**2+zi**2-zk**2), 2.0*d1, "C")
    d2 = Rkj*ylk - Rkl*yjk
    D = sd(Rkl*xjk-Rkj*xlk, d2, "D")
    E = sd(Rkl*zjk-Rkj*zlk, d2, "E")
    F_ = sd(Rkl*(Rkj**2+xk**2-xj**2+yk**2-yj**2+zk**2-zj**2)
            - Rkj*(Rkl**2+xk**2-xl**2+yk**2-yl**2+zk**2-zl**2), 2.0*d2, "F")
    G = sd(E-B, A-D, "G"); H = sd(F_-C_, A-D, "H")
    I_ = A*G+B; J_ = A*H+C_
    K = Rik**2+xi**2-xk**2+yi**2-yk**2+zi**2-zk**2+2.0*xki*H+2.0*yki*J_
    L = 2.0*(xki*G+yki*I_+zki)
    M = 4.0*Rik**2*(G**2+I_**2+1.0)-L**2
    N_ = 8.0*Rik**2*(G*(xi-H)+I_*(yi-J_)+zi)+2.0*L*K
    O_ = 4.0*Rik**2*((xi-H)**2+(yi-J_)**2+zi**2)-K**2
    if abs(M) < 1e-12:
        z_c = [O_/N_] if abs(N_) > 1e-12 else []
    else:
        half = N_/(2.0*M)
        disc = half**2 - O_/M
        if disc < -1e-14:
            return []
        rt = math.sqrt(max(0.0, disc))
        z_c = [half+rt, half-rt]
    sols = []
    for z in z_c:
        s = (float(G*z+H), float(I_*z+J_), float(z))
        if not any(np.linalg.norm(np.array(s)-np.array(u)) < 1e-8 for u in sols):
            sols.append(s)
    return sols


def _chan_4(sub_st, tdoa_in, c):
    """Chan-Ho WLS untuk 4 stasiun."""
    s0 = sub_st[0]; si = sub_st[1:]
    dd = tdoa_in * c
    R0 = np.dot(s0, s0); Ri = np.sum(si*si, axis=1)
    G = np.hstack([-2.0*(si-s0), -2.0*dd.reshape(-1,1)])
    h = (dd**2-Ri+R0).reshape(-1,1)
    try:
        th1 = np.linalg.lstsq(G, h, rcond=None)[0].flatten()
    except np.linalg.LinAlgError:
        return s0.copy()
    pe, d0 = th1[:3], th1[3]
    if d0 > 1e-10:
        di = np.linalg.norm(pe-si, axis=1)
        W2 = np.diag(1.0/((di/c)**2+(d0/c)**2+1e-10))
        try:
            th2 = np.linalg.lstsq(W2@G, W2@h, rcond=None)[0].flatten()
            pe, d0 = th2[:3], th2[3]
        except Exception:
            pass
    dc = np.linalg.norm(pe-s0)
    if dc > 1e-10 and abs(d0) > 1e-10:
        pe = pe + ((d0-dc)/2.0)*((pe-s0)/dc)
    return pe


def _pivot_4(sub_st, d_vec):
    """Pivot Elimination untuk 4 stasiun → 0–2 kandidat."""
    S0 = sub_st[0]; S = sub_st[1:]
    K0 = np.dot(S0,S0); K = np.sum(S*S, axis=1)
    G = np.zeros((3,4))
    for i in range(3):
        G[i,:3] = 2.0*(S[i]-S0)
        G[i,3] = -2.0*d_vec[i]
    h = K - K0 - d_vec**2
    p = int(np.argmax(np.abs(d_vec)))
    dc = G[p,3]
    if abs(dc) < 1e-12:
        return []
    non_p = [i for i in range(3) if i != p]
    A = np.zeros((2,3)); bv = np.zeros(2)
    for idx, k in enumerate(non_p):
        r = G[k,3]/dc
        A[idx] = G[k,:3] - r*G[p,:3]
        bv[idx] = h[k] - r*h[p]
    Axy = A[:,:2]
    if abs(np.linalg.det(Axy)) < 1e-12:
        return []
    inv = np.linalg.inv(Axy)
    beta = inv@bv; alpha = inv@A[:,2]
    bx,by = beta; ax,ay = alpha
    H0 = h[p]-G[p,0]*bx-G[p,1]*by
    H1 = G[p,0]*ax+G[p,1]*ay-G[p,2]
    p1,p2,z0 = bx-S0[0],by-S0[1],S0[2]
    Ac = (ax**2+ay**2+1.0)-(H1**2/dc**2)
    Bc = (-2.0*p1*ax-2.0*p2*ay-2.0*z0)-(2.0*H0*H1/dc**2)
    Cc = (p1**2+p2**2+z0**2)-(H0**2/dc**2)
    disc = Bc**2-4.0*Ac*Cc
    if disc < 0: disc = 0.0
    sq = math.sqrt(disc)
    if abs(Ac) < 1e-12:
        zl = [-Cc/Bc] if abs(Bc) > 1e-12 else []
    else:
        zl = [(-Bc+sq)/(2.0*Ac), (-Bc-sq)/(2.0*Ac)]
    return [np.array([bx-ax*z, by-ay*z, z]) for z in zl]


# ═══════════════════════════════════════════════════════════════════════════════
# PENGUMPULAN KANDIDAT MULTI-SOLVER
# ═══════════════════════════════════════════════════════════════════════════════

def _collect_candidates(tdoa_dict: dict, stations: np.ndarray,
                        c: float, n_mics: int) -> List[np.ndarray]:
    """Kumpulkan kandidat dari 3 solver × P(n_mics,4) permutasi."""
    candidates = []

    for perm in itertools.permutations(range(n_mics), 4):
        mi, mj, mk, ml = perm
        sub_st = stations[list(perm)]

        # ── Bucher-Misra ──
        Rij = _get_tdoa(tdoa_dict, f"mic{mi}", f"mic{mj}", n_mics)
        Rik = _get_tdoa(tdoa_dict, f"mic{mi}", f"mic{mk}", n_mics)
        Rkl = _get_tdoa(tdoa_dict, f"mic{mk}", f"mic{ml}", n_mics)
        if not any(v is None for v in [Rij, Rik, Rkl]):
            d_Rij, d_Rik, d_Rkl = Rij*c, Rik*c, Rkl*c
            max_ij = np.linalg.norm(stations[mj]-stations[mi])
            max_ik = np.linalg.norm(stations[mk]-stations[mi])
            max_kl = np.linalg.norm(stations[ml]-stations[mk])
            if abs(d_Rij) <= max_ij and abs(d_Rik) <= max_ik and abs(d_Rkl) <= max_kl:
                try:
                    for s in _bm_solve_4(sub_st, [0.0, -d_Rij, -d_Rik, -d_Rik-d_Rkl]):
                        pos = np.array(s)
                        if np.all(np.abs(pos) < 50.0) and not np.any(np.isnan(pos)):
                            candidates.append(pos)
                except (_BucherMisraError, ValueError, ZeroDivisionError):
                    pass

        # ── Chan-Ho & Pivot (butuh 3 TDOA) ──
        t1 = _get_tdoa(tdoa_dict, f"mic{mi}", f"mic{mj}", n_mics)
        t2 = _get_tdoa(tdoa_dict, f"mic{mi}", f"mic{mk}", n_mics)
        t3 = _get_tdoa(tdoa_dict, f"mic{mi}", f"mic{ml}", n_mics)

        if not any(v is None for v in [t1, t2, t3]):
            d_vec = np.array([-t1*c, -t2*c, -t3*c])
            # outlier check
            has_outlier = any(
                abs(d_vec[idx]) > np.linalg.norm(stations[sm] - stations[mi])
                for idx, sm in enumerate([mj, mk, ml])
            )
            if not has_outlier:
                # Chan-Ho
                try:
                    pos = _chan_4(sub_st, np.array([-t1, -t2, -t3]), c)
                    if pos is not None and np.all(np.abs(pos) < 50.0) and not np.any(np.isnan(pos)):
                        candidates.append(pos)
                except Exception:
                    pass

                # Pivot
                for pos in _pivot_4(sub_st, d_vec):
                    if np.all(np.abs(pos) < 50.0) and not np.any(np.isnan(pos)):
                        candidates.append(pos)

    return candidates


# ═══════════════════════════════════════════════════════════════════════════════
# FUNGSI SOLVE (KONTRAK WAJIB)
# ═══════════════════════════════════════════════════════════════════════════════

def solve(event_data: dict, mic_positions: dict, config: dict) -> tuple:
    """
    Estimasi posisi sumber suara menggunakan Consensus Function.

    Args:
        event_data:    Data event berisi kunci 'tdoa'
        mic_positions: Dict {nama_mic: [x, y, z] atau {'x':..,'y':..,'z':..}}
        config:        Konfigurasi dari config_manager

    Returns:
        (estimated_pos, None, None)
        Metode ini tidak menggunakan clustering berbasis kluster,
        sehingga cluster_size dan clusters_info di-return None.
    """
    c = config.get("speed_of_sound", _DEFAULT_C)
    eps_sec = config.get("consensus_eps_sec", _DEFAULT_EPS_SEC)
    refine_radius = config.get("consensus_refine_radius", _DEFAULT_REFINE_RADIUS)
    refine_step = config.get("consensus_refine_step", _DEFAULT_REFINE_STEP)
    tdoa_data = event_data.get("tdoa", {})

    mic_names = list(mic_positions.keys())
    n_mics = len(mic_names)

    if n_mics < 4:
        print(f"[ERROR] Consensus membutuhkan minimal 4 mikrofon, ditemukan {n_mics}")
        return None, None, None

    def _pos(m):
        p = mic_positions[m]
        if isinstance(p, dict):
            return [p["x"], p["y"], p["z"]]
        return list(p)

    stations_arr = np.array([_pos(f"mic{k}") for k in range(n_mics)])

    # Langkah 1: Kumpulkan kandidat
    candidates = _collect_candidates(tdoa_data, stations_arr, c, n_mics)
    if not candidates:
        print("[ERROR] Consensus: tidak ada kandidat terkumpul")
        return None, None, None

    print(f"[INFO] Consensus: {len(candidates)} kandidat dari 3 solver × permutasi")

    # Langkah 2: Bangun tabel TDOA
    tdoa_table = _build_tdoa_table(tdoa_data, stations_arr, c, n_mics)
    if not tdoa_table:
        return None, None, None

    n_valid_pairs = sum(1 for t in tdoa_table if t[4])

    # Langkah 3: Pilih kandidat dengan consensus score tertinggi
    best_pos, best_score, best_ws = None, -1, -np.inf
    for cand in candidates:
        score, ws = _consensus_score(cand, tdoa_table, stations_arr, c, eps_sec)
        if score > best_score or (score == best_score and ws > best_ws):
            best_score, best_ws, best_pos = score, ws, cand.copy()

    if best_pos is None:
        return None, None, None

    print(f"[INFO] Consensus awal: score={best_score}/{n_valid_pairs}")

    # Langkah 4: Local grid refinement
    if refine_radius > 0 and refine_step > 0:
        offsets = np.arange(-refine_radius, refine_radius + refine_step / 2, refine_step)
        for dx in offsets:
            for dy in offsets:
                for dz in offsets:
                    pt = best_pos + np.array([dx, dy, dz])
                    score, ws = _consensus_score(pt, tdoa_table, stations_arr, c, eps_sec)
                    if score > best_score or (score == best_score and ws > best_ws):
                        best_score, best_ws, best_pos = score, ws, pt.copy()

        print(f"[INFO] Setelah grid refinement: score={best_score}/{n_valid_pairs}")

    # Langkah 5: Nelder-Mead polish
    try:
        result = minimize(
            _consensus_objective,
            best_pos,
            args=(tdoa_table, stations_arr, c, eps_sec),
            method="Nelder-Mead",
            options={"maxiter": 500, "xatol": 1e-6, "fatol": 1e-8},
        )
        refined = result.x
        if np.all(np.abs(refined) < 50.0) and not np.any(np.isnan(refined)):
            r_score, r_ws = _consensus_score(refined, tdoa_table, stations_arr, c, eps_sec)
            if r_score >= best_score - 1:
                best_pos, best_score, best_ws = refined.copy(), r_score, r_ws
    except Exception:
        pass

    print(
        f"[INFO] Posisi akhir (Consensus): "
        f"[{best_pos[0]:.2f}, {best_pos[1]:.2f}, {best_pos[2]:.2f}], "
        f"score={best_score}/{n_valid_pairs}"
    )
    return list(best_pos), None, None
