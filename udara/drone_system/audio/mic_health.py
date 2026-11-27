"""
Per-Chunk In-Flight Microphone Health Detection (Method-Agnostic).

Berjalan pada sinyal PCM mentah per chunk (sebelum filter, EventDetector, maupun TDOA)
sehingga berlaku seragam untuk Spectral Gating + GCC-PHAT, Comb-Notch + ECCCT, dan lainnya.

Menggunakan median energi khusus dari channel yang non-dead & non-clipping agar tetap
akurat meskipun >= 3 mikrofon mati bersamaan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Sequence

import numpy as np


@dataclass
class MicHealthReport:
    """Hasil evaluasi kesehatan mikrofon pada satu chunk audio."""

    healthy_indices: List[int] = field(default_factory=list)
    healthy_names: List[str] = field(default_factory=list)
    excluded_mics: Dict[str, str] = field(default_factory=dict)
    channel_rms_db: Dict[str, float] = field(default_factory=dict)


def assess_chunk_mic_health(
    data: np.ndarray,
    active_indices: Sequence[int],
    mic_names: Sequence[str] | None = None,
    dead_abs_db: float = -85.0,
    dead_rel_db: float = 20.0,
    high_noise_rel_db: float = 12.0,
    clip_threshold: float = 0.985,
    clip_ratio_limit: float = 0.02,
    dc_offset_limit: float = 0.05,
) -> MicHealthReport:
    """
    Evaluasi kesehatan tiap channel mikrofon pada array audio 2D (n_samples, n_channels).

    Args:
        data:              Array audio 2D (n_samples, n_channels)
        active_indices:    Daftar indeks channel fisik (mis. (4, 5, 6, 7, 8, 9))
        mic_names:         Nama logis tiap channel (default: mic0..mic{N-1})
        dead_abs_db:       Batas absolut RMS dBFS dianggap mati/flat
        dead_rel_db:       Drop dB di bawah median channel aktif dianggap mati/terputus
        high_noise_rel_db: Lonjakan dB di atas median channel aktif dianggap noise rusak
        clip_threshold:    Amplitudo sampel dianggap saturasi/clip
        clip_ratio_limit:  Proporsi sampel saturasi maksimal sebelum dianggap CLIP
        dc_offset_limit:   Batas absolut rata-rata sinyal (DC offset)

    Returns:
        MicHealthReport berisi healthy_indices, healthy_names, excluded_mics, channel_rms_db
    """
    report = MicHealthReport()
    if data is None or data.ndim != 2 or data.shape[0] == 0 or not active_indices:
        return report

    n_channels = data.shape[1]
    names = list(mic_names) if mic_names is not None else [f"mic{i}" for i in range(len(active_indices))]

    rms_db_list: List[float] = []
    clip_ratios: List[float] = []
    dc_offsets: List[float] = []
    valid_slots: List[int] = []

    for slot, ch_idx in enumerate(active_indices):
        mname = names[slot]
        if ch_idx >= n_channels:
            report.excluded_mics[mname] = "CHANNEL_OUT_OF_RANGE"
            continue

        sig = np.asarray(data[:, ch_idx], dtype=np.float64)
        rms = float(np.sqrt(np.mean(sig ** 2)))
        rms_db = float(20.0 * np.log10(max(rms, 1e-9)))
        clip_ratio = float(np.mean(np.abs(sig) >= clip_threshold))
        dc_abs = float(np.abs(np.mean(sig)))

        report.channel_rms_db[mname] = round(rms_db, 2)
        rms_db_list.append(rms_db)
        clip_ratios.append(clip_ratio)
        dc_offsets.append(dc_abs)
        valid_slots.append(slot)

    if not valid_slots:
        return report

    # Hitung median HANYA dari channel non-dead & non-clip agar tahan saat >= 3 mic mati
    baseline_dbs = [
        rms_db_list[k]
        for k in range(len(valid_slots))
        if rms_db_list[k] > dead_abs_db and clip_ratios[k] <= clip_ratio_limit
    ]
    median_db = float(np.median(baseline_dbs)) if baseline_dbs else float(np.median(rms_db_list))

    for k, slot in enumerate(valid_slots):
        ch_idx = int(active_indices[slot])
        mname = names[slot]
        rdb = rms_db_list[k]
        crat = clip_ratios[k]
        dc = dc_offsets[k]

        if crat > clip_ratio_limit:
            report.excluded_mics[mname] = f"CLIP ({crat * 100:.1f}%)"
        elif dc > dc_offset_limit:
            report.excluded_mics[mname] = f"DC_OFFSET ({dc:.3f})"
        elif rdb <= dead_abs_db or (median_db - rdb) > dead_rel_db:
            report.excluded_mics[mname] = f"DEAD ({rdb:.1f} dBFS)"
        elif (rdb - median_db) > high_noise_rel_db:
            report.excluded_mics[mname] = f"HIGH_NOISE (+{rdb - median_db:.1f} dB)"
        else:
            report.healthy_indices.append(ch_idx)
            report.healthy_names.append(mname)

    return report
