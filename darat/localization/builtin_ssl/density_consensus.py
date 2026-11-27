"""
Metode Density-Consensus Hybrid

Inti Algoritma:
  Hybrid Density-Consensus menggabungkan pencarian analitik dengan pemfilteran kerapatan (density filtering) dan konsensus.
  1. Kumpulkan kandidat posisi analitik (ratusan titik) dari kombinasi & permutasi mikrofon.
  2. Filter kandidat: hanya simpan X% (default: 70%) kandidat terdekat ke nilai median (center)
     untuk membuang outlier ekstrim sebelum proses voting konsensus.
  3. Hitung Consensus Score untuk setiap kandidat terfilter.
  4. Pilih kandidat dengan Consensus Score tertinggi sebagai pemenang awal.
  5. Lakukan local grid refinement di sekitar pemenang.
  6. Polish menggunakan Nelder-Mead.
"""

import numpy as np
from scipy.optimize import minimize

from .consensus import (
    _build_tdoa_table,
    _consensus_score,
    _consensus_objective,
    _collect_candidates,
)

# ── Nama tampilan di UI ────────────────────────────────────────────────────────
DISPLAY_NAME = "Density-Consensus Hybrid"

# ── Konstanta default ──────────────────────────────────────────────────────────
_DEFAULT_C = 343.0
_DEFAULT_EPS_SEC = 0.0005        # toleransi TDOA 0.5 ms
_DEFAULT_PERCENTILE = 70.0       # default filter 70% dari yang mengumpul
_DEFAULT_REFINE_RADIUS = 0.5      # m
_DEFAULT_REFINE_STEP = 0.1        # m


def solve(event_data: dict, mic_positions: dict, config: dict) -> tuple:
    """
    Estimasi posisi sumber suara menggunakan Density-Consensus Hybrid.

    Args:
        event_data:    Data event berisi kunci 'tdoa'
        mic_positions: Dict {nama_mic: [x, y, z] atau {'x':..,'y':..,'z':..}}
        config:        Konfigurasi dari config_manager

    Returns:
        (estimated_pos, None, None)
        Metode ini tidak berbasis kluster standar, sehingga cluster_size dan
        clusters_info di-return None.
    """
    c = config.get("speed_of_sound", _DEFAULT_C)
    eps_sec = config.get("consensus_eps_sec", _DEFAULT_EPS_SEC)
    percentile = config.get("density_percentile", _DEFAULT_PERCENTILE)
    refine_radius = config.get("consensus_refine_radius", _DEFAULT_REFINE_RADIUS)
    refine_step = config.get("consensus_refine_step", _DEFAULT_REFINE_STEP)
    tdoa_data = event_data.get("tdoa", {})

    mic_names = sorted(list(mic_positions.keys()))
    n_mics = len(mic_names)

    if n_mics < 4:
        print(f"[ERROR] Density-Consensus membutuhkan minimal 4 mikrofon, ditemukan {n_mics}")
        return None, None, None

    def _pos(m):
        p = mic_positions[m]
        if isinstance(p, dict):
            return [p["x"], p["y"], p["z"]]
        return list(p)

    stations_arr = np.array([_pos(m) for m in mic_names])

    # Langkah 1: Kumpulkan kandidat
    candidates = _collect_candidates(tdoa_data, stations_arr, c, mic_names)
    if not candidates:
        print("[ERROR] Density-Consensus: tidak ada kandidat terkumpul")
        return None, None, None

    # Langkah 2: Bangun tabel TDOA
    tdoa_table = _build_tdoa_table(tdoa_data, stations_arr, c, mic_names)
    if not tdoa_table:
        return None, None, None

    n_valid_pairs = sum(1 for t in tdoa_table if t[4])

    # Langkah 3: Density filtering (ambil percentile% terdekat ke median)
    arr = np.array(candidates)
    center = np.median(arr, axis=0)
    dists = np.linalg.norm(arr - center, axis=1)
    threshold = np.percentile(dists, percentile)
    mask = dists <= threshold
    filtered_candidates = arr[mask]
    if len(filtered_candidates) == 0:
        filtered_candidates = arr

    print(
        f"[INFO] Density-Consensus: total kandidat={len(candidates)}, "
        f"setelah density filter {percentile}%={len(filtered_candidates)}"
    )

    # Langkah 4: Pilih kandidat terfilter dengan consensus score tertinggi
    best_pos, best_score, best_ws = None, -1, -np.inf
    for cand in filtered_candidates:
        score, ws = _consensus_score(cand, tdoa_table, stations_arr, c, eps_sec)
        if score > best_score or (score == best_score and ws > best_ws):
            best_score, best_ws, best_pos = score, ws, cand.copy()

    if best_pos is None:
        return None, None, None

    print(f"[INFO] Consensus awal (density-filtered): score={best_score}/{n_valid_pairs}")

    # Langkah 5: Local grid refinement
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

    # Langkah 6: Nelder-Mead polish
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
        f"[INFO] Posisi akhir (Density-Consensus): "
        f"[{best_pos[0]:.2f}, {best_pos[1]:.2f}, {best_pos[2]:.2f}], "
        f"score={best_score}/{n_valid_pairs}"
    )
    return list(best_pos), None, None
