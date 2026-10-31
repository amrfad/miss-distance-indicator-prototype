"""
TDOA Processing Module (Refactored — Plugin-based SSL)

Perubahan dari versi sebelumnya:
  - Logika metode individual (Bucher-Misra, dll.) dipindah ke darat/builtin_ssl/
  - process_event_tdoa() kini mendelegasikan kalkulasi ke ssl_registry
  - Mendukung metode baru secara otomatis tanpa modifikasi file ini
  - Untuk backward compat, fungsi solve_tdoa_least_squares dan tdoa_residuals
    dipertahankan sebagai legacy helpers
"""

import json
import glob
import os
from typing import Optional, Tuple, List

import numpy as np
from scipy.optimize import least_squares

from ..core.config_manager import get_global_config_manager
from . import ssl_registry


# ─────────────────────────────────────────────────────────────────────────────
# Legacy helpers (dipertahankan untuk backward compatibility)
# ─────────────────────────────────────────────────────────────────────────────

def tdoa_residuals(pos, mic_positions_list, tdoa_measurements, c=None):
    """
    Fungsi residual untuk least squares optimization.

    Args:
        pos: [x, y, z] posisi sumber yang akan dioptimasi
        mic_positions_list: List posisi mikrofon [[x1,y1,z1], [x2,y2,z2], ...]
        tdoa_measurements: List TDOA dalam detik relatif ke mic pertama
        c: Kecepatan suara

    Returns:
        Array residual
    """
    if c is None:
        c = get_global_config_manager().get_config().get("speed_of_sound", 343.0)
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


def solve_tdoa_least_squares(mic_positions: dict, tdoa_data: dict) -> Optional[tuple]:
    """
    Selesaikan TDOA menggunakan least squares optimization.

    Args:
        mic_positions: Dict posisi mikrofon {'mic0': [x,y,z], ...}
        tdoa_data: Dict TDOA measurements {'mic0-mic1': tdoa, ...}

    Returns:
        (x, y, z) estimasi posisi atau None jika gagal
    """
    cfg = get_global_config_manager().get_config()
    c = cfg.get("speed_of_sound", 343.0)

    mic_names = sorted(mic_positions.keys())
    n_mics = len(mic_names)

    mic_positions_list = []
    for name in mic_names:
        pos = mic_positions[name]
        if isinstance(pos, dict):
            mic_positions_list.append([pos["x"], pos["y"], pos["z"]])
        else:
            mic_positions_list.append(list(pos))

    tdoa_measurements = []
    for i in range(1, n_mics):
        mic_pair     = f"{mic_names[0]}-{mic_names[i]}"
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
            args=(mic_positions_list, tdoa_measurements, c),
            method="lm",
            max_nfev=1000,
        )
        if result.success:
            return tuple(result.x)
        return None
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Fungsi utama pemrosesan
# ─────────────────────────────────────────────────────────────────────────────

def process_event_tdoa(
    event_data: dict,
    mic_positions: dict,
    method: str = "bucher_misra",
) -> Tuple[Optional[list], Optional[int], Optional[List[str]]]:
    """
    Memproses satu event TDOA dan mengembalikan estimasi posisi.

    Mendelegasikan kalkulasi ke metode yang terdaftar di ssl_registry.
    Untuk mendapatkan daftar metode yang tersedia gunakan:
        from . import ssl_registry
        ssl_registry.get_available_methods()

    Args:
        event_data:    Data event dengan TDOA measurements (dict dengan kunci 'tdoa')
        mic_positions: Dict posisi mikrofon
        method:        Key metode SSL (sesuai ssl_registry). Default: 'bucher_misra'

    Returns:
        (estimated_position, cluster_size, clusters_info)
        - estimated_position : list [x, y, z] atau None
        - cluster_size       : int atau None (jika metode tidak menggunakan clustering)
        - clusters_info      : list of str atau None
    """
    cfg = get_global_config_manager().get_config()

    entry = ssl_registry.get_method(method)
    if entry is None:
        # Fallback: coba default
        fallback_key = ssl_registry.get_default_key()
        print(
            f"[WARN] Metode '{method}' tidak ditemukan di registry. "
            f"Fallback ke '{fallback_key}'."
        )
        entry = ssl_registry.get_method(fallback_key)

    if entry is None:
        print("[ERROR] Tidak ada metode SSL yang terdaftar. Pastikan registry sudah diinisialisasi.")
        return None, None, None

    try:
        result = entry.solve(event_data, mic_positions, cfg)
    except Exception as exc:
        print(f"[ERROR] Metode '{method}' gagal: {exc}")
        return None, None, None

    # Normalisasi hasil: pastikan selalu tuple 3 elemen
    if result is None:
        return None, None, None

    if not isinstance(result, (tuple, list)) or len(result) < 3:
        # Metode hanya mengembalikan posisi — bungkus ke format standar
        return list(result) if result is not None else None, None, None

    pos, cluster_size, clusters_info = result[0], result[1], result[2]
    if pos is not None:
        pos = list(pos)
    return pos, cluster_size, clusters_info


# ─────────────────────────────────────────────────────────────────────────────
# Simpan hasil
# ─────────────────────────────────────────────────────────────────────────────

def save_results_to_file(data: dict, events_results: list,
                         mic_positions: dict, output_file: str) -> None:
    """Simpan hasil estimasi posisi ke file teks dalam format sederhana."""
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("# MICROPHONE POSITIONS\n")
        for mic_name, pos in mic_positions.items():
            if isinstance(pos, dict):
                f.write(
                    f"{mic_name} = [{pos['x']:.2f}, {pos['y']:.2f}, {pos['z']:.2f}]\n"
                )
            else:
                f.write(f"{mic_name} = [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}]\n")

        f.write("\n# EVENT POSITIONS\n")
        for result in events_results:
            event_num    = result["event_number"]
            estimated_pos = result["estimated_position"]
            clusters_info = result.get("clusters_info", None)

            if estimated_pos is not None:
                if len(estimated_pos) == 2:
                    f.write(
                        f"e{event_num} = [{estimated_pos[0]:.2f}, {estimated_pos[1]:.2f}]\n"
                    )
                else:
                    f.write(
                        f"e{event_num} = [{estimated_pos[0]:.2f}, "
                        f"{estimated_pos[1]:.2f}, {estimated_pos[2]:.2f}]\n"
                    )
                if clusters_info:
                    for line in clusters_info:
                        f.write(f"  {line}\n")
            else:
                f.write(f"e{event_num} = FAILED\n")


# ─────────────────────────────────────────────────────────────────────────────
# Entry point standalone (jalankan langsung, bukan via GUI)
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # Inisialisasi registry sebelum digunakan
    ssl_registry.initialize()

    print("=" * 80)
    print("PROGRAM ESTIMASI POSISI DARI FILE JSON TDOA")
    print("=" * 80)

    cfg = get_global_config_manager().get_config()
    mic_positions = cfg.get("mic_positions", {})

    print(f"\nPosisi Mikrofon:")
    for mic_name, pos in mic_positions.items():
        if isinstance(pos, dict):
            print(f"  {mic_name}: [{pos['x']:.2f}, {pos['y']:.2f}, {pos['z']:.2f}]")
        else:
            print(f"  {mic_name}: [{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}]")

    # Pilih metode
    methods = ssl_registry.get_available_methods()
    print(f"\nMetode SSL yang tersedia:")
    for i, (key, display) in enumerate(methods):
        print(f"  {i+1}. {display} (key: {key})")

    method_key = ssl_registry.get_default_key()
    try:
        idx = int(input(f"\nPilih nomor metode (default=1 Bucher-Misra): ").strip()) - 1
        if 0 <= idx < len(methods):
            method_key = methods[idx][0]
    except (ValueError, IndexError):
        pass
    print(f"Menggunakan metode: {method_key}")

    json_files = glob.glob("*.json") + glob.glob("received_*.json")
    json_files = sorted(set(json_files))

    if json_files:
        print(f"\n{'='*80}")
        print(f"File JSON yang tersedia ({len(json_files)} file):")
        for i, file in enumerate(json_files, 1):
            size_kb = os.path.getsize(file) / 1024
            print(f"  {i}. {file:<50} ({size_kb:.2f} KB)")
    else:
        print("\n[INFO] Tidak ada file JSON ditemukan.")

    json_file = input("\nMasukkan nama file JSON: ").strip()

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
    print(f"Timestamp : {data.get('timestamp', 'N/A')}")
    print(f"Events    : {data.get('event_count', 0)}")
    print("=" * 80)

    events = data.get("events", [])
    events_results = []

    for event in events:
        event_num = event.get("event_number", "?")
        print(f"\n{'─'*80}\nEVENT {event_num}\n{'─'*80}")

        pos, cluster_size, clusters_info = process_event_tdoa(
            event, mic_positions, method=method_key
        )
        events_results.append({
            "event_number": event_num,
            "estimated_position": pos,
            "cluster_size": cluster_size,
            "clusters_info": clusters_info,
        })

        if pos is not None:
            pos_str = f"[{pos[0]:.2f}, {pos[1]:.2f}]" if len(pos) == 2 else f"[{pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f}]"
            print(f"Estimasi Posisi: {pos_str} m")
            if cluster_size is not None:
                print(f"Cluster Size   : {cluster_size} solusi konsisten")
        else:
            print("Estimasi Posisi: GAGAL")

    print("\n" + "=" * 80 + "\nPROSES SELESAI\n" + "=" * 80)

    out = json_file.replace(".json", "_results.txt")
    save_results_to_file(data, events_results, mic_positions, out)
    print(f"\nHasil disimpan ke: {out}")


if __name__ == "__main__":
    main()
