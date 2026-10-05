"""
calibration_engine.py — Engine Estimasi Posisi Mikrofon 3D dari Observasi TDOA.

Modul ini mengimplementasikan nonlinear least-squares solver untuk mengkalibrasi
posisi 3D mikrofon (array 6 mic) secara absolut menggunakan sejumlah titik sumber suara
yang koordinat 3D-nya diketahui di dunia nyata.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from scipy.optimize import least_squares

logger = logging.getLogger(__name__)

NUM_MICS: int = 6
TDOA_PAIRS: List[Tuple[int, int]] = [
    (i, j) for i in range(NUM_MICS) for j in range(i + 1, NUM_MICS)
]
DEFAULT_SPEED_OF_SOUND: float = 343.0


@dataclass
class CalibrationSession:
    """Representasi satu sesi observasi pada satu posisi sumber suara."""
    session_id: str
    file_path: str
    source_pos: np.ndarray  # shape (3,) [x, y, z] dalam meter
    tdoa_median: Dict[str, float] = field(default_factory=dict)
    n_events: int = 0

    @property
    def is_valid(self) -> bool:
        """Sesi valid jika memiliki setidaknya 1 event dan data TDOA."""
        return self.n_events > 0 and len(self.tdoa_median) > 0


@dataclass
class CalibrationResult:
    """Hasil akhir komputasi kalibrasi posisi mikrofon."""
    mic_positions_dict: Dict[str, Dict[str, float]]
    mic_positions_array: np.ndarray  # shape (6, 3)
    rms_residual_ms: float
    converged: bool
    message: str
    n_sessions_used: int
    n_events_used: int


def unpack_params(params: np.ndarray, mode: str = "free_18") -> np.ndarray:
    """
    Mengubah parameter 1D flat dari optimizer menjadi matriks koordinat 3D (6, 3).
    """
    mic_pos = np.zeros((6, 3), dtype=float)
    if mode == "free_18":
        mic_pos = params.reshape((6, 3))
    elif mode == "pin_origin_15":
        mic_pos[0] = params[0:3]          # mic0
        mic_pos[1] = [0.0, 0.0, 0.0]      # mic1 (origin locked)
        mic_pos[2] = params[3:6]          # mic2
        mic_pos[3] = params[6:9]          # mic3
        mic_pos[4] = params[9:12]         # mic4
        mic_pos[5] = params[12:15]        # mic5
    else:
        raise ValueError(f"Mode optimizer tidak dikenal: {mode}")
    return mic_pos


def pack_params(mic_pos: np.ndarray, mode: str = "free_18") -> np.ndarray:
    """
    Mengubah matriks koordinat 3D (6, 3) menjadi parameter 1D flat untuk optimizer.
    """
    if mode == "free_18":
        return mic_pos.flatten().copy()
    elif mode == "pin_origin_15":
        return np.concatenate([
            mic_pos[0],
            mic_pos[2],
            mic_pos[3],
            mic_pos[4],
            mic_pos[5],
        ])
    else:
        raise ValueError(f"Mode optimizer tidak dikenal: {mode}")


def compute_tdoa_residuals(
    params: np.ndarray,
    observations: List[Dict[str, Any]],
    speed_of_sound: float = DEFAULT_SPEED_OF_SOUND,
    mode: str = "free_18",
) -> np.ndarray:
    """
    Menghitung vektor selisih (residual) antara TDOA observasi dan TDOA teoritis model.

    Model:
        tau_ij_teoritis = (||S_k - M_i|| - ||S_k - M_j||) / c
        residual = tau_ij_observasi - tau_ij_teoritis
    """
    mic_pos = unpack_params(params, mode=mode)
    res = []

    for obs in observations:
        s_coord = obs["source_pos"]
        tdoa_median = obs["tdoa_median"]

        for i, j in TDOA_PAIRS:
            key = f"mic{i}-mic{j}"
            tau_obs = tdoa_median.get(key)
            if tau_obs is None:
                continue

            d_i = np.linalg.norm(s_coord - mic_pos[i])
            d_j = np.linalg.norm(s_coord - mic_pos[j])
            tau_pred = (d_i - d_j) / speed_of_sound

            res.append(tau_obs - tau_pred)

    if not res:
        return np.array([0.0], dtype=float)

    return np.array(res, dtype=float)


def calibrate_mic_array(
    observations: List[Dict[str, Any]],
    x0: Optional[np.ndarray] = None,
    speed_of_sound: float = DEFAULT_SPEED_OF_SOUND,
    mode: str = "free_18",
    method: str = "trf",
    loss: str = "linear",
    max_nfev: int = 10000,
    verbose: bool = False,
) -> Tuple[np.ndarray, Any]:
    """
    Menjalankan optimasi least-squares untuk menemukan estimasi posisi 6 mikrofon.

    Args:
        observations: List dict observasi: [{"source_pos": (3,), "tdoa_median": dict}, ...]
        x0: Initial guess koordinat (flat 1D array).
        speed_of_sound: Kecepatan rambat suara (m/s).
        mode: 'free_18' atau 'pin_origin_15'.
        method: Algoritma scipy least_squares ('trf', 'dogbox', 'lm').
        loss: Fungsi loss ('linear', 'soft_l1', 'huber').
        max_nfev: Maksimal evaluasi fungsi.
        verbose: Log progres jika True.

    Returns:
        Tuple (mic_pos_estimated (6, 3), result_scipy)
    """
    if x0 is None:
        # Default fallback jika tidak ada initial guess
        default_array = np.array([
            [-1.58,  0.77,  0.09],
            [ 1.60,  0.77,  0.09],
            [-0.59, -0.92, -0.07],
            [ 0.59, -0.92, -0.05],
            [-0.50, -0.11, -0.16],
            [ 0.13, -0.01, -0.17],
        ], dtype=float)
        x0 = pack_params(default_array, mode=mode)

    result = least_squares(
        compute_tdoa_residuals,
        x0,
        args=(observations, speed_of_sound, mode),
        method=method,
        loss=loss,
        ftol=1e-14,
        xtol=1e-14,
        gtol=1e-14,
        max_nfev=max_nfev,
        verbose=2 if verbose else 0,
    )

    mic_pos_estimated = unpack_params(result.x, mode=mode)
    return mic_pos_estimated, result


def parse_tdoa_json(
    file_path: Union[str, Path],
    source_pos: Union[np.ndarray, List[float]],
) -> CalibrationSession:
    """
    Membaca file JSON TDOA dari drone dan mengekstrak median TDOA untuk setiap pasangan mic.

    Args:
        file_path: Path ke file JSON TDOA.
        source_pos: Koordinat sumber suara [x, y, z].

    Returns:
        CalibrationSession
    """
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File tidak ditemukan: {file_path}")

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    session_id = str(data.get("session_id", p.stem))
    events = data.get("events", [])
    if not isinstance(events, list):
        events = []

    pairs_data: Dict[str, List[float]] = {
        f"mic{i}-mic{j}": [] for i, j in TDOA_PAIRS
    }

    n_events = len(events)
    for ev in events:
        tdoa_dict = ev.get("tdoa", {})
        if not isinstance(tdoa_dict, dict):
            continue
        for key, val in tdoa_dict.items():
            if key in pairs_data and val is not None:
                try:
                    pairs_data[key].append(float(val))
                except (ValueError, TypeError):
                    continue

    tdoa_median: Dict[str, float] = {}
    for key, vals in pairs_data.items():
        if vals:
            tdoa_median[key] = float(np.median(vals))

    src_arr = np.asarray(source_pos, dtype=float).flatten()
    if src_arr.shape != (3,):
        raise ValueError(f"source_pos harus memiliki 3 elemen (x, y, z), didapat: {source_pos}")

    return CalibrationSession(
        session_id=session_id,
        file_path=str(p.resolve()),
        source_pos=src_arr,
        tdoa_median=tdoa_median,
        n_events=n_events,
    )


def run_calibration(
    sessions: List[CalibrationSession],
    initial_mic_positions: Optional[Union[Dict[str, Any], np.ndarray]] = None,
    speed_of_sound: float = DEFAULT_SPEED_OF_SOUND,
    mode: str = "free_18",
    loss: str = "soft_l1",
    verbose: bool = False,
) -> CalibrationResult:
    """
    Menjalankan proses kalibrasi dari daftar sesi yang diberikan.

    Args:
        sessions: Daftar CalibrationSession.
        initial_mic_positions: Posisi awal mic (dict dari config atau matriks (6,3)).
        speed_of_sound: Kecepatan rambat suara (m/s).
        mode: Mode parameterisasi optimizer ('free_18').
        loss: Loss function scipy ('linear', 'soft_l1', 'huber').
        verbose: Output log debug jika True.

    Returns:
        CalibrationResult
    """
    valid_sessions = [s for s in sessions if s.is_valid]

    if not valid_sessions:
        raise ValueError("Tidak ada sesi yang valid (memiliki event dan data TDOA) untuk dikalibrasi.")

    observations: List[Dict[str, Any]] = [
        {
            "source_pos": s.source_pos,
            "tdoa_median": s.tdoa_median,
        }
        for s in valid_sessions
    ]

    total_events = sum(s.n_events for s in valid_sessions)

    # Siapkan initial guess x0
    x0: Optional[np.ndarray] = None
    if initial_mic_positions is not None:
        if isinstance(initial_mic_positions, np.ndarray) and initial_mic_positions.shape == (6, 3):
            x0 = pack_params(initial_mic_positions, mode=mode)
        elif isinstance(initial_mic_positions, dict):
            arr = np.zeros((6, 3), dtype=float)
            for idx in range(6):
                key = f"mic{idx}"
                pos = initial_mic_positions.get(key)
                if isinstance(pos, dict):
                    arr[idx] = [float(pos.get("x", 0.0)), float(pos.get("y", 0.0)), float(pos.get("z", 0.0))]
                elif isinstance(pos, (list, tuple, np.ndarray)) and len(pos) >= 3:
                    arr[idx] = [float(pos[0]), float(pos[1]), float(pos[2])]
            x0 = pack_params(arr, mode=mode)

    estimated_pos, opt_res = calibrate_mic_array(
        observations=observations,
        x0=x0,
        speed_of_sound=speed_of_sound,
        mode=mode,
        loss=loss,
        verbose=verbose,
    )

    residuals = opt_res.fun
    rms_ms = float(np.sqrt(np.mean(residuals ** 2)) * 1000.0) if len(residuals) > 0 else 0.0

    res_dict: Dict[str, Dict[str, float]] = {}
    for idx in range(NUM_MICS):
        res_dict[f"mic{idx}"] = {
            "x": round(float(estimated_pos[idx, 0]), 4),
            "y": round(float(estimated_pos[idx, 1]), 4),
            "z": round(float(estimated_pos[idx, 2]), 4),
        }

    return CalibrationResult(
        mic_positions_dict=res_dict,
        mic_positions_array=estimated_pos,
        rms_residual_ms=round(rms_ms, 4),
        converged=bool(opt_res.success),
        message=str(opt_res.message),
        n_sessions_used=len(valid_sessions),
        n_events_used=total_events,
    )
