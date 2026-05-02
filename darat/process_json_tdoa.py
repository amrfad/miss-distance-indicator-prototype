"""
TDOA Processing Module (Refactored)
Perubahan dari versi original:
  - Hapus dead code: find_largest_cluster() dan select_best_cluster() (tidak pernah dipanggil)
  - Clustering logic dikonsolidasi ke _cluster_solutions() helper internal
  - MIC_POSITIONS tetap di sini untuk backward compat dengan process_screen.py
    (juga tersedia di config.py untuk modul baru)
  - SPEED_OF_SOUND tetap sebagai module-level constant (digunakan di beberapa fungsi)
  - Semua proses bisnis identik dengan versi original
"""

import numpy as np
import json
import math
import itertools
from itertools import combinations
import os
import glob
from typing import Iterable, List, Optional, Sequence, Tuple
from scipy.optimize import least_squares

# --- Konfigurasi ---
SPEED_OF_SOUND = 343.0  # m/s

# Posisi mikrofon dalam meter (x, y, z)
MIC_POSITIONS = {
    "mic0": np.array([-1.58, 0.77, 0.09]),
    "mic1": np.array([1.60, 0.77, 0.09]),
    "mic2": np.array([-0.59, -0.92, -0.07]),
    "mic3": np.array([0.59, -0.92, -0.05]),
    "mic4": np.array([-0.5, -0.11, -0.16]),
    "mic5": np.array([0.13, -0.01, -0.17]),
}


class BucherMisraError(ValueError):
    """Dilempar bila kondisi geometri/aritmetika membuat sistem tidak terdefinisi atau nyaris singular."""


def _safe_div(num: float, den: float, name: str, eps: float = 1e-12) -> float:
    if abs(den) < eps:
        raise BucherMisraError(
            f"Penyebut nyaris nol pada '{name}' (|{den}| < {eps}). "
            "Cek konfigurasi stasiun/TDOA agar tidak degenerat."
        )
    return num / den


def bucher_misra_3d(
    stations_xyz: Sequence[Iterable[float]],
    *,
    toas_s: Optional[Sequence[float]] = None,
    ranges_m: Optional[Sequence[float]] = None,
    c_audio: float = 343.0,
    eps: float = 1e-12,
) -> List[Tuple[float, float, float]]:
    if len(stations_xyz) != 4:
        raise ValueError("Dibutuhkan tepat 4 stasiun.")
    (xi, yi, zi), (xj, yj, zj), (xk, yk, zk), (xl, yl, zl) = [
        tuple(map(float, p)) for p in stations_xyz
    ]

    if (toas_s is None) == (ranges_m is None):
        raise ValueError("Berikan tepat salah satu: toas_s ATAU ranges_m.")

    if toas_s is not None:
        if len(toas_s) != 4:
            raise ValueError("toas_s harus berdimensi 4.")
        Ri, Rj, Rk, Rl = [c_audio * float(t) for t in toas_s]
    else:
        if len(ranges_m) != 4:
            raise ValueError("ranges_m harus berdimensi 4.")
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
    A = _safe_div((Rik * xji - Rij * xki), den1, "A_den", eps)
    B = _safe_div((Rik * zji - Rij * zki), den1, "B_den", eps)
    C_num = Rik * (
        Rij**2 + xi**2 - xj**2 + yi**2 - yj**2 + zi**2 - zj**2
    ) - Rij * (Rik**2 + xi**2 - xk**2 + yi**2 - yk**2 + zi**2 - zk**2)
    C_den = 2.0 * den1
    C = _safe_div(C_num, C_den, "C_den", eps)

    den2 = Rkj * ylk - Rkl * yjk
    D = _safe_div((Rkl * xjk - Rkj * xlk), den2, "D_den", eps)
    E = _safe_div((Rkl * zjk - Rkj * zlk), den2, "E_den", eps)
    F_num = Rkl * (
        Rkj**2 + xk**2 - xj**2 + yk**2 - yj**2 + zk**2 - zj**2
    ) - Rkj * (Rkl**2 + xk**2 - xl**2 + yk**2 - yl**2 + zk**2 - zl**2)
    F_den = 2.0 * den2
    F = _safe_div(F_num, F_den, "F_den", eps)

    denom = A - D
    G = _safe_div((E - B), denom, "G_den", eps)
    H = _safe_div((F - C), denom, "H_den", eps)
    I = A * G + B
    J = A * H + C

    K = (
        Rik**2
        + xi**2
        - xk**2
        + yi**2
        - yk**2
        + zi**2
        - zk**2
        + 2.0 * xki * H
        + 2.0 * yki * J
    )
    L = 2.0 * (xki * G + yki * I + zki)

    M = 4.0 * (Rik**2) * (G**2 + I**2 + 1.0) - (L**2)
    N = 8.0 * (Rik**2) * (G * (xi - H) + I * (yi - J) + zi) + 2.0 * L * K
    O = 4.0 * (Rik**2) * ((xi - H) ** 2 + (yi - J) ** 2 + zi**2) - (K**2)

    sols: List[Tuple[float, float, float]] = []

    if abs(M) < 1e-12:
        if abs(N) > 1e-12:
            z_candidates = [O / N]
        else:
            z_candidates = []
    else:
        half = N / (2.0 * M)
        disc = half * half - (O / M)
        if disc >= -1e-14:
            disc = max(0.0, disc)
            rt = math.sqrt(disc)
            z_candidates = [half + rt, half - rt]
        else:
            z_candidates = []

    for z in z_candidates:
        x = G * z + H
        y = I * z + J
        sols.append((float(x), float(y), float(z)))

    uniq: List[Tuple[float, float, float]] = []
    for s in sols:
        if not any(np.linalg.norm(np.array(s) - np.array(u)) < 1e-8 for u in uniq):
            uniq.append(s)
    return uniq


def _cluster_solutions(solutions, eps=1.0):
    """
    Kelompokkan solusi ke dalam cluster berdasarkan jarak euclidean.
    Menggantikan logika clustering yang sebelumnya terduplikasi di dua tempat.

    Returns:
        list of clusters (tiap cluster adalah list of (x,y,z) tuples), diurutkan desc by size.
    """
    if not solutions:
        return []

    all_clusters = []
    assigned_indices = set()

    for i, sol1 in enumerate(solutions):
        if i in assigned_indices:
            continue
        current_cluster = [sol1]
        assigned_indices.add(i)
        for j, sol2 in enumerate(solutions):
            if j in assigned_indices:
                continue
            is_close = any(
                np.linalg.norm(np.array(sol2) - np.array(member)) < eps
                for member in current_cluster
            )
            if is_close:
                current_cluster.append(sol2)
                assigned_indices.add(j)
        all_clusters.append(current_cluster)

    all_clusters.sort(key=len, reverse=True)
    return all_clusters


def tdoa_residuals(pos, mic_positions_list, tdoa_measurements, c=SPEED_OF_SOUND):
    """
    Fungsi residual untuk least squares optimization.

    Args:
        pos: [x, y, z] posisi sumber yang akan dioptimasi
        mic_positions_list: List posisi mikrofon [[x1,y1,z1], [x2,y2,z2], ...]
        tdoa_measurements: List TDOA dalam detik relatif ke mic pertama
        c: Kecepatan suara

    Returns:
        Array residual (selisih antara TDOA terukur dan terhitung)
    """
    x, y, z = pos
    residuals = []

    mic_ref = np.array(mic_positions_list[0])
    dist_ref = np.linalg.norm(np.array([x, y, z]) - mic_ref)

    for i in range(1, len(mic_positions_list)):
        mic_i = np.array(mic_positions_list[i])
        dist_i = np.linalg.norm(np.array([x, y, z]) - mic_i)
        tdoa_calculated = (dist_i - dist_ref) / c
        tdoa_measured = tdoa_measurements[i - 1]
        residuals.append(tdoa_calculated - tdoa_measured)

    return np.array(residuals)


def solve_tdoa_least_squares(mic_positions, tdoa_data):
    """
    Selesaikan TDOA menggunakan least squares optimization.

    Args:
        mic_positions: Dict posisi mikrofon {'mic0': [x,y,z], ...}
        tdoa_data: Dict TDOA measurements {'mic0-mic1': tdoa, ...}

    Returns:
        (x, y, z) estimasi posisi atau None jika gagal
    """
    mic_names = sorted(mic_positions.keys())
    n_mics = len(mic_names)

    mic_positions_list = [mic_positions[name] for name in mic_names]

    tdoa_measurements = []
    for i in range(1, n_mics):
        mic_pair = f"{mic_names[0]}-{mic_names[i]}"
        mic_pair_inv = f"{mic_names[i]}-{mic_names[0]}"

        if mic_pair in tdoa_data:
            tdoa_measurements.append(tdoa_data[mic_pair])
        elif mic_pair_inv in tdoa_data:
            tdoa_measurements.append(-tdoa_data[mic_pair_inv])
        else:
            return None

    initial_guess = np.mean(mic_positions_list, axis=0)

    try:
        result = least_squares(
            tdoa_residuals,
            initial_guess,
            args=(mic_positions_list, tdoa_measurements, SPEED_OF_SOUND),
            method="lm",
            max_nfev=1000,
        )
        if result.success:
            return tuple(result.x)
        else:
            return None
    except Exception:
        return None


def process_event_tdoa(event_data, mic_positions, method="bucher-misra"):
    """Memproses satu event TDOA dan mengembalikan estimasi posisi.

    Args:
        event_data: Data event dengan TDOA measurements
        mic_positions: Dict posisi mikrofon
        method: 'bucher-misra' atau 'least-squares'

    Returns:
        (estimated_position, cluster_size/confidence, clusters_info)
    """
    tdoa_data = event_data["tdoa"]

    if method == "least-squares":
        estimated_pos = solve_tdoa_least_squares(mic_positions, tdoa_data)
        if estimated_pos is not None:
            return (estimated_pos, 1, None)
        else:
            return None, 0, None

    # Metode Bucher-Misra dengan Ensemble (kombinasi + permutasi)
    mic_names = list(mic_positions.keys())
    n_mics = len(mic_names)

    if n_mics < 4:
        print(f"[ERROR] Minimal 4 mikrofon diperlukan, ditemukan {n_mics}")
        return None, 0, None

    all_solutions = []
    successful_attempts = 0
    total_attempts = 0

    mic_combinations = list(combinations(mic_names, 4))
    total_combinations = len(mic_combinations)
    print(f"\n[INFO] Total kombinasi 4 mikrofon dari {n_mics}: {total_combinations}")

    for combo_idx, mic_combo in enumerate(mic_combinations, 1):
        mic_permutations = list(itertools.permutations(mic_combo))

        for perm in mic_permutations:
            total_attempts += 1
            m_i, m_j, m_k, m_l = perm
            stations_xyz = [
                mic_positions[m_i],
                mic_positions[m_j],
                mic_positions[m_k],
                mic_positions[m_l],
            ]

            try:
                Rij = tdoa_data.get(f"{m_i}-{m_j}", -tdoa_data.get(f"{m_j}-{m_i}", 0))
                Rik = tdoa_data.get(f"{m_i}-{m_k}", -tdoa_data.get(f"{m_k}-{m_i}", 0))
                Rkj = tdoa_data.get(f"{m_k}-{m_j}", -tdoa_data.get(f"{m_j}-{m_k}", 0))
                Rkl = tdoa_data.get(f"{m_k}-{m_l}", -tdoa_data.get(f"{m_l}-{m_k}", 0))

                d_Rij = Rij * SPEED_OF_SOUND
                d_Rik = Rik * SPEED_OF_SOUND
                d_Rkj = Rkj * SPEED_OF_SOUND
                d_Rkl = Rkl * SPEED_OF_SOUND
                ranges_m = [0.0, -d_Rij, -d_Rik, -d_Rik - d_Rkl]

                solutions = bucher_misra_3d(
                    stations_xyz=stations_xyz, ranges_m=ranges_m, c_audio=SPEED_OF_SOUND
                )
                all_solutions.extend(solutions)
                successful_attempts += 1

            except (KeyError, BucherMisraError, ValueError):
                continue

    print(f"[INFO] Total percobaan: {total_attempts}")
    print(f"[INFO] Percobaan berhasil: {successful_attempts}")
    if total_attempts > 0:
        print(
            f"[INFO] Tingkat keberhasilan: {100*successful_attempts/total_attempts:.1f}%"
        )

    if not all_solutions:
        print("[ERROR] Tidak ada solusi yang ditemukan")
        return None, 0, None

    print(f"[INFO] Total {len(all_solutions)} solusi kandidat ditemukan")

    # Clustering menggunakan helper yang dikonsolidasi
    all_clusters = _cluster_solutions(all_solutions, eps=1.0)

    if not all_clusters:
        print("[ERROR] Tidak ada cluster yang ditemukan")
        return None, 0, None

    print(f"\n[DEBUG] Ditemukan {len(all_clusters)} cluster:")
    clusters_info = []
    for idx, cluster in enumerate(all_clusters):
        centroid = np.mean(cluster, axis=0)
        cluster_line = (
            f"Cluster {idx+1}: {len(cluster)} solusi, "
            f"centroid = [{centroid[0]:.2f}, {centroid[1]:.2f}, {centroid[2]:.2f}]"
        )
        print(f"  {cluster_line}")
        clusters_info.append(cluster_line)

    final_cluster = all_clusters[0]

    if not final_cluster:
        return None, 0, None

    final_solution = np.median(final_cluster, axis=0)
    print(f"[DEBUG] Cluster terpilih: {len(final_cluster)} solusi")
    print(
        f"[DEBUG] Posisi akhir: [{final_solution[0]:.2f}, "
        f"{final_solution[1]:.2f}, {final_solution[2]:.2f}]\n"
    )

    return final_solution, len(final_cluster), clusters_info


def save_results_to_file(data, events_results, mic_positions, output_file):
    """Simpan hasil estimasi posisi ke file teks dalam format sederhana."""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# MICROPHONE POSITIONS\n")
        for mic_name, pos in mic_positions.items():
            f.write(f"{mic_name} = [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}]\n")
        f.write("\n# EVENT POSITIONS\n")

        for result in events_results:
            event_num = result["event_number"]
            estimated_pos = result["estimated_position"]
            clusters_info = result.get("clusters_info", None)

            if estimated_pos is not None:
                f.write(
                    f"e{event_num} = [{estimated_pos[0]:.2f}, "
                    f"{estimated_pos[1]:.2f}, {estimated_pos[2]:.2f}]\n"
                )
                if clusters_info:
                    for cluster_line in clusters_info:
                        f.write(f"  {cluster_line}\n")
            else:
                f.write(f"e{event_num} = FAILED\n")


def main():
    print("=" * 80)
    print("PROGRAM ESTIMASI POSISI DARI FILE JSON TDOA")
    print("=" * 80)

    mic_positions = MIC_POSITIONS

    print(f"\nPosisi Mikrofon:")
    for mic_name, pos in mic_positions.items():
        print(f"  {mic_name}: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}]")

    json_files = glob.glob("*.json") + glob.glob("received_*.json")
    json_files = sorted(list(set(json_files)))

    if json_files:
        print(f"\n{'='*80}")
        print(f"File JSON yang tersedia ({len(json_files)} file):")
        print(f"{'='*80}")
        for i, file in enumerate(json_files, 1):
            file_size = os.path.getsize(file) / 1024
            print(f"  {i}. {file:<50} ({file_size:.2f} KB)")
        print(f"{'='*80}")
    else:
        print("\n[INFO] Tidak ada file JSON ditemukan di direktori ini.")

    json_file = input(
        "\nMasukkan nama file JSON (contoh: received_20251128_155300.json): "
    ).strip()

    try:
        with open(json_file, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File '{json_file}' tidak ditemukan.")
        return
    except json.JSONDecodeError as e:
        print(f"Error: File JSON tidak valid - {e}")
        return

    print("\n" + "=" * 80)
    print(f"HASIL ESTIMASI POSISI")
    print(f"Session ID: {data.get('session_id', 'N/A')}")
    print(f"Timestamp: {data.get('timestamp', 'N/A')}")
    print(f"Total Events: {data.get('event_count', 0)}")
    print("=" * 80)

    events = data.get("events", [])
    events_results = []

    for event in events:
        event_num = event.get("event_number", "?")
        print(f"\n{'─'*80}")
        print(f"EVENT {event_num}")
        print(f"{'─'*80}")

        estimated_pos, cluster_size, clusters_info = process_event_tdoa(
            event, mic_positions
        )

        events_results.append(
            {
                "event_number": event_num,
                "estimated_position": estimated_pos,
                "cluster_size": cluster_size,
                "clusters_info": clusters_info,
            }
        )

        if estimated_pos is not None:
            print(
                f"Estimasi Posisi: [{estimated_pos[0]:.2f}, "
                f"{estimated_pos[1]:.2f}, {estimated_pos[2]:.2f}] m"
            )
            print(f"Cluster Size   : {cluster_size} solusi konsisten")
        else:
            print("Estimasi Posisi: GAGAL (tidak ada solusi valid)")

    print("\n" + "=" * 80)
    print("PROSES SELESAI")
    print("=" * 80)

    output_file = json_file.replace(".json", "_results.txt")
    save_results_to_file(data, events_results, mic_positions, output_file)
    print(f"\nHasil disimpan ke: {output_file}")


if __name__ == "__main__":
    main()
