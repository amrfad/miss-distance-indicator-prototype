"""
Drone System Diagnostics Engine (Pre-Flight / System Check).

Menyediakan pengecekan modular hardware & software untuk subsistem udara:
  - CHK-02: Kesehatan OS & daya Raspberry Pi (disk, suhu CPU, undervoltage)
  - CHK-03: Deteksi perangkat ALSA audio (arecord -l vs config)
  - CHK-04: Validasi parameter hardware audio (arecord --dump-hw-params)
  - CHK-05: Uji rekam multi-channel singkat & ekstraksi channel (mic0..micN)
  - CHK-06: Analisis kualitas sinyal per mikrofon (RMS, dBFS, Peak, DC, dead/clip)
  - CHK-07: Smoke test filter aktif + TDOA engine & proyeksi Real-Time Factor (RTF)
  - Live Mic Tap Monitor: pengambilan slice audio cepat untuk cek mapping fisik mic
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import soundfile as sf

from .config import DEVICE_PROFILES, get_take_indices
from ..tdoa import filter_registry
from ..tdoa.tdoa import calculate_all_tdoa

# Lock global agar tidak ada dua operasi diagnostik mengakses arecord secara bersamaan
_DIAG_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).astimezone().isoformat()


def _make_check(
    check_id: str,
    name: str,
    status: str,
    measured: str,
    detail: str = "",
    metrics: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "id": check_id,
        "name": name,
        "status": status,
        "measured": measured,
        "detail": detail,
        "metrics": metrics or {},
    }


# ─────────────────────────────────────────────────────────────────────────────
# CHK-02: OS, Storage, Thermal, & Power Health
# ─────────────────────────────────────────────────────────────────────────────

def _read_cpu_temp_c() -> Optional[float]:
    """Baca suhu CPU Linux/Raspberry Pi dalam Celsius (None jika tidak tersedia)."""
    thermal_path = "/sys/class/thermal/thermal_zone0/temp"
    if os.path.exists(thermal_path):
        try:
            with open(thermal_path, "r", encoding="utf-8") as f:
                raw = float(f.read().strip())
            return round(raw / 1000.0 if raw > 200 else raw, 1)
        except Exception:
            pass

    try:
        res = subprocess.run(
            ["vcgencmd", "measure_temp"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2,
        )
        if res.returncode == 0 and res.stdout:
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)", res.stdout)
            if m:
                return round(float(m.group(1)), 1)
    except Exception:
        pass
    return None


def _read_throttled_hex() -> Optional[str]:
    """Baca status throttling/undervoltage Raspberry Pi via vcgencmd (None jika tidak tersedia)."""
    try:
        res = subprocess.run(
            ["vcgencmd", "get_throttled"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2,
        )
        if res.returncode == 0 and res.stdout:
            m = re.search(r"(0x[0-9a-fA-F]+)", res.stdout)
            if m:
                return m.group(1).lower()
    except Exception:
        pass
    return None


def check_os_health(base_output_dir: str = "drone_recordings") -> Dict[str, Any]:
    """CHK-02: Cek kapasitas storage, izin tulis, suhu CPU, dan undervoltage Raspi."""
    target_dir = base_output_dir or "."
    disk_free_gb: Optional[float] = None
    writable = False

    try:
        os.makedirs(target_dir, exist_ok=True)
        usage = shutil.disk_usage(target_dir)
        disk_free_gb = round(usage.free / (1024 ** 3), 2)
        probe_file = os.path.join(target_dir, ".diag_write_probe")
        with open(probe_file, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe_file)
        writable = True
    except Exception:
        writable = False

    cpu_temp = _read_cpu_temp_c()
    throttled = _read_throttled_hex()

    status = "PASS"
    notes: List[str] = []

    if not writable:
        status = "FAIL"
        notes.append(f"Folder output '{target_dir}' tidak bisa ditulis.")

    if disk_free_gb is None:
        status = "FAIL"
        notes.append("Gagal membaca kapasitas disk.")
    elif disk_free_gb < 0.5:
        status = "FAIL"
        notes.append(f"Sisa storage kritis ({disk_free_gb:.2f} GB < 0.5 GB).")
    elif disk_free_gb < 2.0 and status != "FAIL":
        status = "WARN"
        notes.append(f"Sisa storage menipis ({disk_free_gb:.2f} GB < 2.0 GB).")

    if cpu_temp is not None:
        if cpu_temp >= 80.0:
            status = "FAIL"
            notes.append(f"Suhu CPU terlalu tinggi ({cpu_temp:.1f}°C >= 80°C).")
        elif cpu_temp >= 70.0 and status != "FAIL":
            status = "WARN"
            notes.append(f"Suhu CPU hangat ({cpu_temp:.1f}°C).")

    if throttled is not None:
        try:
            val = int(throttled, 16)
            active_undervolt = bool(val & 0x1)
            active_throttled = bool(val & 0x4)
            past_issue = bool(val & 0xF0000)
            if active_undervolt or active_throttled:
                status = "FAIL"
                notes.append(f"Undervoltage/throttling aktif ({throttled}). Cek catu daya.")
            elif past_issue and status != "FAIL":
                status = "WARN"
                notes.append(f"Pernah terjadi undervoltage/throttling ({throttled}).")
        except ValueError:
            pass

    parts = []
    if cpu_temp is not None:
        parts.append(f"{cpu_temp:.1f}°C")
    if disk_free_gb is not None:
        parts.append(f"{disk_free_gb:.2f} GB free")
    if throttled is not None:
        parts.append(f"pwr={throttled}")
    if not parts:
        parts.append("Writable" if writable else "Not writable")

    detail = " ".join(notes) if notes else "Storage, suhu, dan daya normal."
    return _make_check(
        "CHK-02",
        "Raspi OS & Power Health",
        status,
        " | ".join(parts),
        detail,
        {
            "disk_free_gb": disk_free_gb,
            "writable": writable,
            "cpu_temp_c": cpu_temp,
            "throttled": throttled,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# CHK-03: ALSA Audio Device Detection (arecord -l)
# ─────────────────────────────────────────────────────────────────────────────

def parse_arecord_list(output: str) -> List[Dict[str, Any]]:
    """Parse output dari `arecord -l` menjadi list of capture devices."""
    devices: List[Dict[str, Any]] = []
    pattern = re.compile(
        r"card\s+(\d+):\s*([^\[]+)\[([^\]]+)\],\s*device\s+(\d+):\s*([^\[]+)\[([^\]]+)\]",
        re.IGNORECASE,
    )
    for line in (output or "").splitlines():
        m = pattern.search(line)
        if m:
            card_idx = int(m.group(1))
            dev_idx = int(m.group(4))
            devices.append({
                "hw_id": f"hw:{card_idx},{dev_idx}",
                "card": card_idx,
                "device": dev_idx,
                "card_name": m.group(3).strip(),
                "device_name": m.group(6).strip(),
            })
    return devices


def check_alsa_device(configured_device: str) -> Dict[str, Any]:
    """CHK-03: Verifikasi perangkat capture ALSA terdeteksi & cocok dengan config."""
    try:
        res = subprocess.run(
            ["arecord", "-l"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
        )
        out = res.stdout or ""
    except FileNotFoundError:
        return _make_check(
            "CHK-03",
            "ALSA Audio Device",
            "FAIL",
            "arecord not found",
            "Perintah 'arecord' tidak ditemukan di sistem (alsa-utils belum terpasang).",
        )
    except Exception as exc:
        return _make_check(
            "CHK-03",
            "ALSA Audio Device",
            "FAIL",
            "arecord error",
            f"Gagal menjalankan 'arecord -l': {exc}",
        )

    devices = parse_arecord_list(out)
    if not devices:
        return _make_check(
            "CHK-03",
            "ALSA Audio Device",
            "FAIL",
            "0 devices",
            "Tidak ada perangkat audio capture yang terdeteksi di arecord -l. Cek kabel USB & mode Audio Interface Zoom.",
            {"configured_device": configured_device, "devices": []},
        )

    # Normalisasi (mis. plughw:2,0 -> hw:2,0)
    norm_cfg = configured_device.replace("plughw:", "hw:")
    matched = next((d for d in devices if d["hw_id"] == norm_cfg), None)

    if matched:
        return _make_check(
            "CHK-03",
            "ALSA Audio Device",
            "PASS",
            f"{matched['hw_id']} ({matched['card_name']})",
            f"Perangkat '{matched['card_name']}' terdeteksi sesuai konfigurasi ({configured_device}).",
            {
                "configured_device": configured_device,
                "matched_device": matched,
                "devices": devices,
            },
        )

    # Cari kandidat Zoom atau device pertama untuk saran
    zoom_candidate = next(
        (
            d for d in devices
            if any(k in (d["card_name"] + " " + d["device_name"]).lower() for k in ("zoom", "h8", "h6"))
        ),
        devices[0],
    )
    return _make_check(
        "CHK-03",
        "ALSA Audio Device",
        "WARN",
        f"Config {configured_device} != {zoom_candidate['hw_id']}",
        (
            f"Device config '{configured_device}' tidak ditemukan, namun terdeteksi "
            f"'{zoom_candidate['card_name']}' di {zoom_candidate['hw_id']}. "
            f"Perbarui 'arecord_device' di tab CONFIG jika nomor card USB bergeser."
        ),
        {
            "configured_device": configured_device,
            "suggested_device": zoom_candidate["hw_id"],
            "devices": devices,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# CHK-04: Audio Hardware Params (arecord --dump-hw-params)
# ─────────────────────────────────────────────────────────────────────────────

def parse_hw_params_output(output: str) -> Tuple[List[str], Optional[int], Optional[int], Optional[int]]:
    """Parse format, max channels, min rate, max rate dari output arecord --dump-hw-params."""
    formats: List[str] = []
    max_ch: Optional[int] = None
    min_rate: Optional[int] = None
    max_rate: Optional[int] = None

    for line in (output or "").splitlines():
        l = line.strip()
        if l.startswith("-"):
            parts = l.lstrip("- ").split()
            if parts and re.match(r"^[A-Z0-9_]+$", parts[0]):
                formats.append(parts[0])
        elif l.upper().startswith("FORMAT:"):
            rest = l.split(":", 1)[1].strip()
            for tok in rest.split():
                if re.match(r"^[A-Z0-9_]+$", tok):
                    formats.append(tok)
        elif l.upper().startswith("CHANNELS:"):
            nums = [int(n) for n in re.findall(r"\d+", l)]
            if nums:
                max_ch = max(nums)
        elif l.upper().startswith("RATE:"):
            nums = [int(n) for n in re.findall(r"\d+", l)]
            if nums:
                min_rate = min(nums)
                max_rate = max(nums)

    # Deduplicate preserving order
    unique_formats = list(dict.fromkeys(formats))
    return unique_formats, max_ch, min_rate, max_rate


def check_hw_params(
    device: str,
    active_profile: str = "H8",
    expected_rate: int = 48000,
) -> Dict[str, Any]:
    """CHK-04: Validasi format, jumlah channel, dan sample rate perangkat ALSA."""
    profile = DEVICE_PROFILES.get(active_profile, DEVICE_PROFILES["H8"])
    expected_fmt = profile["format"]
    expected_ch = profile["channels"]

    try:
        res = subprocess.run(
            ["arecord", "-D", device, "--dump-hw-params", "-d", "1", "/dev/null"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=5,
        )
        out = res.stdout or ""
    except FileNotFoundError:
        return _make_check(
            "CHK-04",
            "Audio HW Parameters",
            "FAIL",
            "arecord not found",
            "Perintah 'arecord' tidak tersedia.",
        )
    except Exception as exc:
        return _make_check(
            "CHK-04",
            "Audio HW Parameters",
            "FAIL",
            "Probe error",
            f"Gagal mem-probe {device}: {exc}",
        )

    if "Device or resource busy" in out:
        return _make_check(
            "CHK-04",
            "Audio HW Parameters",
            "FAIL",
            "Device busy",
            f"Perangkat {device} sedang digunakan oleh proses lain.",
        )

    formats, max_ch, min_rate, max_rate = parse_hw_params_output(out)
    if not formats and max_ch is None:
        return _make_check(
            "CHK-04",
            "Audio HW Parameters",
            "FAIL",
            "Probe failed",
            f"Tidak bisa membaca parameter hardware untuk {device}. Output: {out[:160].strip()}",
        )

    fmt_ok = (expected_fmt in formats) if formats else False
    ch_ok = (max_ch is not None and max_ch >= expected_ch)
    rate_ok = True
    if min_rate is not None and max_rate is not None:
        rate_ok = (min_rate <= expected_rate <= max_rate)

    measured = f"{max_ch or '?'}ch | {expected_fmt if fmt_ok else (formats[0] if formats else '?')} | {expected_rate}Hz"
    metrics = {
        "device": device,
        "profile": active_profile,
        "expected_format": expected_fmt,
        "expected_channels": expected_ch,
        "expected_rate": expected_rate,
        "supported_formats": formats,
        "max_channels": max_ch,
        "min_rate": min_rate,
        "max_rate": max_rate,
    }

    if fmt_ok and ch_ok and rate_ok:
        return _make_check(
            "CHK-04",
            "Audio HW Parameters",
            "PASS",
            measured,
            f"Parameter hardware sesuai profil {active_profile}.",
            metrics,
        )

    issues = []
    if not fmt_ok:
        issues.append(f"format {expected_fmt} tidak ada (tersedia: {formats})")
    if not ch_ok:
        issues.append(f"max channels {max_ch} < target {expected_ch}")
    if not rate_ok:
        issues.append(f"rate {expected_rate}Hz di luar rentang [{min_rate}, {max_rate}]")

    status = "FAIL" if (not ch_ok or not rate_ok) else "WARN"
    return _make_check(
        "CHK-04",
        "Audio HW Parameters",
        status,
        measured,
        "Ketidaksesuaian parameter hardware: " + "; ".join(issues),
        metrics,
    )


# ─────────────────────────────────────────────────────────────────────────────
# CHK-05 & CHK-06: Capture, Channel Split, & Mic Signal Health
# ─────────────────────────────────────────────────────────────────────────────

def capture_audio_sample(
    device: str,
    fmt: str,
    rate: int,
    channels: int,
    duration_sec: float,
    output_wav: str,
) -> Tuple[bool, str]:
    """
    Rekam sampel audio multi-channel ke file WAV via arecord.
    Untuk durasi < 1.0 detik menggunakan --samples=<N> (dengan fallback -d 1).
    """
    dur_val = max(0.2, float(duration_sec))
    base_cmd = [
        "arecord",
        "-D", device,
        "-f", fmt,
        "-r", str(int(rate)),
        "-c", str(int(channels)),
        "-t", "wav",
        "-q",
    ]

    if dur_val < 1.0:
        n_samples = max(1024, int(round(dur_val * rate)))
        cmd = base_cmd + [f"--samples={n_samples}", output_wav]
    else:
        cmd = base_cmd + ["-d", str(int(round(dur_val))), output_wav]

    timeout_sec = max(5.0, dur_val + 5.0)
    try:
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_sec,
        )
        if res.returncode != 0 and dur_val < 1.0:
            # Fallback jika versi arecord tidak mendukung --samples
            fallback_cmd = base_cmd + ["-d", "1", output_wav]
            res = subprocess.run(
                fallback_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=6.0,
            )
        if res.returncode != 0:
            err = (res.stderr or res.stdout or "").strip()
            return False, f"arecord exit {res.returncode}: {err}"
        if not os.path.exists(output_wav) or os.path.getsize(output_wav) <= 44:
            return False, "File WAV hasil rekaman kosong atau tidak terbentuk."
        return True, "OK"
    except FileNotFoundError:
        return False, "Perintah 'arecord' tidak ditemukan."
    except subprocess.TimeoutExpired:
        return False, f"arecord timeout setelah {timeout_sec:.1f}s."
    except Exception as exc:
        return False, str(exc)


def analyze_mic_channels(
    data: np.ndarray,
    take_indices: Sequence[int],
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Hitung statistik RMS, dBFS, Peak, DC offset, dan status kesehatan tiap mic.

    Args:
        data: Array 2D audio (n_samples, n_channels)
        take_indices: Tuple index channel fisik yang dipetakan ke mic0..mic{N-1}

    Returns:
        (mic_metrics_list, loudest_mic_name)
    """
    if data is None or data.ndim != 2 or data.shape[0] == 0:
        return [], None

    n_ch = data.shape[1]
    raw_metrics: List[Dict[str, Any]] = []

    for i, ch_idx in enumerate(take_indices):
        mic_name = f"mic{i}"
        if ch_idx >= n_ch:
            raw_metrics.append({
                "mic": mic_name,
                "channel_index": int(ch_idx),
                "rms": 0.0,
                "rms_db": -120.0,
                "peak": 0.0,
                "dc_offset": 0.0,
                "clipped_samples": 0,
                "status": "MISSING",
                "note": f"Channel index {ch_idx} di luar batas ({n_ch} ch)",
            })
            continue

        sig = np.asarray(data[:, ch_idx], dtype=np.float64)
        rms = float(np.sqrt(np.mean(sig ** 2)))
        rms_db = float(20.0 * np.log10(max(rms, 1e-6)))
        peak = float(np.max(np.abs(sig)))
        dc_offset = float(np.mean(sig))
        clipped = int(np.sum(np.abs(sig) >= 0.99))

        raw_metrics.append({
            "mic": mic_name,
            "channel_index": int(ch_idx),
            "rms": round(rms, 6),
            "rms_db": round(rms_db, 1),
            "peak": round(peak, 4),
            "dc_offset": round(dc_offset, 6),
            "clipped_samples": clipped,
            "status": "OK",
            "note": "",
        })

    # Evaluasi noise floor relatif terhadap median mic aktif (non-dead & non-clip)
    active_dbs = [
        m["rms_db"]
        for m in raw_metrics
        if m["rms_db"] > -85.0 and m["clipped_samples"] == 0 and m["status"] != "MISSING"
    ]
    median_db = float(np.median(active_dbs)) if active_dbs else -120.0

    loudest_mic: Optional[str] = None
    loudest_rms = -1.0

    for m in raw_metrics:
        if m["status"] == "MISSING":
            continue
        if m["rms"] > loudest_rms:
            loudest_rms = m["rms"]
            loudest_mic = m["mic"]

        if m["rms"] <= 1e-5 or m["rms_db"] <= -85.0 or (active_dbs and (median_db - m["rms_db"]) > 20.0):
            m["status"] = "DEAD"
            m["note"] = f"Sinyal mati/mic terlepas ({m['rms_db']:.1f} dBFS vs median {median_db:.1f} dBFS)"
        elif m["peak"] >= 0.99 or m["clipped_samples"] > 0:
            m["status"] = "CLIP"
            m["note"] = f"Hard clipping ({m['clipped_samples']} sample)"
        elif abs(m["dc_offset"]) >= 0.01:
            m["status"] = "WARN"
            m["note"] = f"DC offset tinggi ({m['dc_offset']:+.4f})"
        elif active_dbs and (m["rms_db"] - median_db) > 12.0:
            m["status"] = "WARN"
            m["note"] = f"Noise floor +{m['rms_db'] - median_db:.1f} dB di atas median"
        else:
            m["status"] = "OK"
            m["note"] = "Normal"

    if loudest_rms <= 1e-5:
        loudest_mic = None

    return raw_metrics, loudest_mic


def evaluate_mic_health_check(mic_metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
    """CHK-06: Buat ringkasan status check kesehatan mikrofon dari mic_metrics."""
    if not mic_metrics:
        return _make_check(
            "CHK-06",
            "Mic Signal Health",
            "FAIL",
            "No data",
            "Tidak ada data channel mikrofon untuk dianalisis.",
        )

    dead = [m["mic"] for m in mic_metrics if m["status"] == "DEAD"]
    clip = [m["mic"] for m in mic_metrics if m["status"] == "CLIP"]
    missing = [m["mic"] for m in mic_metrics if m["status"] == "MISSING"]
    warns = [m["mic"] for m in mic_metrics if m["status"] == "WARN"]
    ok_count = sum(1 for m in mic_metrics if m["status"] == "OK")
    total = len(mic_metrics)

    if missing or dead or clip:
        reasons = []
        if missing:
            reasons.append(f"missing: {', '.join(missing)}")
        if dead:
            reasons.append(f"mati/flat: {', '.join(dead)}")
        if clip:
            reasons.append(f"clipping: {', '.join(clip)}")
        return _make_check(
            "CHK-06",
            "Mic Signal Health",
            "FAIL",
            f"{ok_count}/{total} OK",
            "Masalah sinyal mikrofon — " + "; ".join(reasons) + ".",
            {"ok_count": ok_count, "total": total, "dead": dead, "clip": clip, "warn": warns},
        )

    if warns:
        return _make_check(
            "CHK-06",
            "Mic Signal Health",
            "WARN",
            f"{ok_count}/{total} OK ({len(warns)} warn)",
            f"Perhatian pada {', '.join(warns)} (noise floor / DC offset). Cek kabel atau gain.",
            {"ok_count": ok_count, "total": total, "warn": warns},
        )

    rms_vals = [m["rms_db"] for m in mic_metrics]
    spread_db = round(max(rms_vals) - min(rms_vals), 1) if rms_vals else 0.0
    return _make_check(
        "CHK-06",
        "Mic Signal Health",
        "PASS",
        f"{ok_count}/{total} OK (spread {spread_db} dB)",
        "Semua mikrofon aktif, bebas clipping, dan noise floor seimbang.",
        {"ok_count": ok_count, "total": total, "spread_db": spread_db},
    )


# ─────────────────────────────────────────────────────────────────────────────
# CHK-07: DSP Filter + TDOA Engine Smoke Test & Real-Time Factor (RTF)
# ─────────────────────────────────────────────────────────────────────────────

def check_dsp_pipeline(
    channel_files: Sequence[str],
    sample_rate: int,
    config: Dict[str, Any],
    sample_duration_sec: float = 2.0,
) -> Dict[str, Any]:
    """
    CHK-07: Uji eksekusi filter aktif + TDOA engine pada sampel rekaman,
    verifikasi bebas NaN/error, dan hitung estimasi Real-Time Factor (RTF).
    """
    if len(channel_files) < 2:
        return _make_check(
            "CHK-07",
            "DSP & TDOA Budget (RTF)",
            "FAIL",
            "Insufficient channels",
            f"Minimal 2 file channel diperlukan untuk uji DSP/TDOA (tersedia: {len(channel_files)}).",
        )

    filter_key = config.get("filter_method", filter_registry.DEFAULT_METHOD)
    filter_params = config.get("filter_configs", {}).get(filter_key, {})
    tdoa_method = config.get("tdoa_method", "eccct")
    chunk_dur = float(config.get("chunk_duration_sec", 8.0))

    try:
        t0 = time.perf_counter()

        # 1. Load & apply active filter ke seluruh channel
        FilterClass = filter_registry.get_method_class(filter_key)
        filtered_signals: List[np.ndarray] = []
        filter_instance = FilterClass(**filter_params) if (FilterClass and FilterClass.is_available()) else None

        for path in channel_files:
            sig, sr_file = sf.read(path)
            if sig.ndim > 1:
                sig = sig[:, 0]
            if filter_instance is not None:
                sig = filter_instance.apply(sig, sr_file)
            if np.any(np.isnan(sig)) or np.any(np.isinf(sig)):
                return _make_check(
                    "CHK-07",
                    "DSP & TDOA Budget (RTF)",
                    "FAIL",
                    f"{filter_key}: NaN/Inf",
                    f"Filter '{filter_key}' menghasilkan nilai NaN/Inf pada {os.path.basename(path)}.",
                )
            filtered_signals.append(sig)

        t_filter = time.perf_counter() - t0

        # 2. Jalankan 1x calculate_all_tdoa pada window 0.5 detik dari hasil filter
        t1 = time.perf_counter()
        min_len = min(len(s) for s in filtered_signals)
        actual_dur = min_len / float(sample_rate) if sample_rate > 0 else sample_duration_sec
        filtered_2d = np.column_stack([s[:min_len] for s in filtered_signals])
        win_samples = min(min_len, max(1024, int(round(0.5 * sample_rate))))
        start_idx = max(0, (min_len - win_samples) // 2)
        seg_2d = filtered_2d[start_idx:start_idx + win_samples, :]

        tdoa_result = calculate_all_tdoa(
            seg_2d,
            fs=sample_rate,
            channel_indices=list(range(len(filtered_signals))),
        )
        t_tdoa = time.perf_counter() - t1

        n_mics = len(channel_files)
        expected_pairs = n_mics * (n_mics - 1) // 2
        if not tdoa_result or len(tdoa_result) < expected_pairs:
            return _make_check(
                "CHK-07",
                "DSP & TDOA Budget (RTF)",
                "FAIL",
                f"{len(tdoa_result) if tdoa_result else 0}/{expected_pairs} pairs",
                f"TDOA ({tdoa_method}) gagal menghitung seluruh {expected_pairs} pasangan.",
            )

        has_bad = any(
            v is None or np.isnan(float(v)) or np.isinf(float(v))
            for v in tdoa_result.values()
        )
        if has_bad:
            return _make_check(
                "CHK-07",
                "DSP & TDOA Budget (RTF)",
                "FAIL",
                f"{tdoa_method}: invalid value",
                "Hasil TDOA mengandung nilai NaN/Inf/None.",
            )

        # Proyeksi waktu proses untuk 1 chunk penuh:
        # filter berskala ~linear terhadap durasi; TDOA dihitung per event (diasumsikan 1-2 event/chunk)
        scale = chunk_dur / max(actual_dur, 0.25)
        projected_chunk_sec = (t_filter * scale) + t_tdoa
        rtf = projected_chunk_sec / max(chunk_dur, 0.5)

        measured = f"RTF {rtf:.2f} ({filter_key} + {tdoa_method})"
        metrics = {
            "filter_method": filter_key,
            "tdoa_method": tdoa_method,
            "filter_sec": round(t_filter, 3),
            "tdoa_sec": round(t_tdoa, 3),
            "sample_dur_sec": round(actual_dur, 2),
            "chunk_dur_sec": chunk_dur,
            "projected_chunk_sec": round(projected_chunk_sec, 3),
            "rtf": round(rtf, 3),
            "tdoa_pairs": len(tdoa_result),
        }

        if rtf >= 1.0:
            status = "FAIL"
            detail = (
                f"Estimasi proses 1 chunk ({projected_chunk_sec:.2f}s) >= durasi chunk ({chunk_dur:.1f}s). "
                "Berisiko terjadi drop chunk di Raspberry Pi."
            )
        elif rtf >= 0.7:
            status = "WARN"
            detail = (
                f"Estimasi proses 1 chunk ({projected_chunk_sec:.2f}s / {chunk_dur:.1f}s) mendekati batas real-time."
            )
        else:
            status = "PASS"
            detail = (
                f"Filter ({t_filter*1000:.0f} ms) & TDOA ({t_tdoa*1000:.0f} ms, {len(tdoa_result)} pasang) OK. "
                f"Estimasi 1 chunk: {projected_chunk_sec:.2f}s / {chunk_dur:.1f}s."
            )

        return _make_check("CHK-07", "DSP & TDOA Budget (RTF)", status, measured, detail, metrics)

    except Exception as exc:
        return _make_check(
            "CHK-07",
            "DSP & TDOA Budget (RTF)",
            "FAIL",
            "DSP exception",
            f"Gagal menjalankan pipeline DSP/TDOA: {exc}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Orchestrator: Full Auto-Check & Live Mic Tap Sample
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_capture_params(config: Dict[str, Any]) -> Tuple[str, str, str, int, int, Tuple[int, ...]]:
    """Ambil parameter capture konsisten dari config drone."""
    device = config.get("arecord_device", "hw:2,0")
    active_profile = config.get("active_profile", "H8")
    rate = int(config.get("sample_rate", 48000))
    num_mics_h8 = int(config.get("num_mics_h8", 6))
    profile = DEVICE_PROFILES.get(active_profile, DEVICE_PROFILES["H8"])
    fmt = profile["format"]
    channels = int(profile["channels"])
    take_indices = get_take_indices(active_profile, num_mics_h8)
    return device, active_profile, fmt, rate, channels, take_indices


def run_auto_checks(
    audio_system=None,
    config_manager=None,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Jalankan rangkaian Automated Pre-Flight / System Check secara thread-safe.

    Options:
        check_os (bool):          default True
        check_audio_hw (bool):    default True
        check_capture (bool):     default True
        check_mic_health (bool):  default True (matikan jika mic dilepas)
        check_pipeline (bool):    default True
        sample_duration_sec (float): default 2.0
    """
    opts = options or {}
    do_os = bool(opts.get("check_os", True))
    do_audio_hw = bool(opts.get("check_audio_hw", True))
    do_capture = bool(opts.get("check_capture", True))
    do_mic = bool(opts.get("check_mic_health", True))
    do_pipeline = bool(opts.get("check_pipeline", True))
    sample_dur = float(opts.get("sample_duration_sec", 2.0))
    sample_dur = max(1.0, min(5.0, sample_dur))

    cfg = config_manager.get_all() if config_manager is not None else {}
    device, active_profile, fmt, rate, channels, take_indices = _resolve_capture_params(cfg)

    checks: List[Dict[str, Any]] = []
    mic_metrics: List[Dict[str, Any]] = []
    loudest_mic: Optional[str] = None

    with _DIAG_LOCK:
        # 1. CHK-02: OS & Power Health
        if do_os:
            checks.append(check_os_health(cfg.get("base_output_dir", "drone_recordings")))
        else:
            checks.append(_make_check("CHK-02", "Raspi OS & Power Health", "SKIP", "-", "Dilewati oleh pengguna."))

        # 2. CHK-03 & CHK-04: ALSA Device & HW Params
        alsa_ok_for_capture = True
        if do_audio_hw:
            chk_alsa = check_alsa_device(device)
            checks.append(chk_alsa)
            if chk_alsa["status"] == "FAIL":
                alsa_ok_for_capture = False
                checks.append(_make_check(
                    "CHK-04", "Audio HW Parameters", "FAIL", "Skipped (no device)",
                    "Perangkat audio tidak terdeteksi pada CHK-03.",
                ))
            else:
                chk_hw = check_hw_params(device, active_profile=active_profile, expected_rate=rate)
                checks.append(chk_hw)
                if chk_hw["status"] == "FAIL":
                    alsa_ok_for_capture = False
        else:
            checks.append(_make_check("CHK-03", "ALSA Audio Device", "SKIP", "-", "Dilewati oleh pengguna."))
            checks.append(_make_check("CHK-04", "Audio HW Parameters", "SKIP", "-", "Dilewati oleh pengguna."))

        # 3. CHK-05, CHK-06, CHK-07: Capture, Split, Mic Health, DSP/TDOA
        need_capture = do_capture or do_mic or do_pipeline
        if not need_capture:
            checks.append(_make_check("CHK-05", "Capture & Channel Split", "SKIP", "-", "Dilewati oleh pengguna."))
            checks.append(_make_check("CHK-06", "Mic Signal Health", "SKIP", "-", "Dilewati oleh pengguna."))
            checks.append(_make_check("CHK-07", "DSP & TDOA Budget (RTF)", "SKIP", "-", "Dilewati oleh pengguna."))
        elif not alsa_ok_for_capture:
            for cid, cname in (
                ("CHK-05", "Capture & Channel Split"),
                ("CHK-06", "Mic Signal Health"),
                ("CHK-07", "DSP & TDOA Budget (RTF)"),
            ):
                checks.append(_make_check(
                    cid, cname, "FAIL", "Blocked by Audio HW",
                    "Tidak dapat merekam karena perangkat audio gagal pada CHK-03/CHK-04.",
                ))
        else:
            with tempfile.TemporaryDirectory(prefix="mdi_diag_") as tmpdir:
                raw_wav = os.path.join(tmpdir, "diag_raw.wav")
                ok_cap, cap_msg = capture_audio_sample(
                    device=device,
                    fmt=fmt,
                    rate=rate,
                    channels=channels,
                    duration_sec=sample_dur,
                    output_wav=raw_wav,
                )

                if not ok_cap:
                    checks.append(_make_check(
                        "CHK-05", "Capture & Channel Split", "FAIL", "Capture failed", cap_msg
                    ))
                    if do_mic:
                        checks.append(_make_check(
                            "CHK-06", "Mic Signal Health", "FAIL", "Blocked", "Gagal capture sampel audio."
                        ))
                    else:
                        checks.append(_make_check("CHK-06", "Mic Signal Health", "SKIP", "-", "Dilewati oleh pengguna."))
                    if do_pipeline:
                        checks.append(_make_check(
                            "CHK-07", "DSP & TDOA Budget (RTF)", "FAIL", "Blocked", "Gagal capture sampel audio."
                        ))
                    else:
                        checks.append(_make_check("CHK-07", "DSP & TDOA Budget (RTF)", "SKIP", "-", "Dilewati oleh pengguna."))
                else:
                    # Extract channels
                    data, sr_read = sf.read(raw_wav, always_2d=True)
                    n_samples, n_ch = data.shape
                    actual_dur = n_samples / float(sr_read) if sr_read else 0.0

                    extracted_files: List[str] = []
                    for i, ch_idx in enumerate(take_indices):
                        if ch_idx < n_ch:
                            ch_path = os.path.join(tmpdir, f"mic{i}_diag.wav")
                            sf.write(ch_path, data[:, ch_idx], sr_read)
                            extracted_files.append(ch_path)

                    if do_capture:
                        if len(extracted_files) == len(take_indices) and actual_dur >= (sample_dur * 0.8):
                            checks.append(_make_check(
                                "CHK-05",
                                "Capture & Channel Split",
                                "PASS",
                                f"{len(extracted_files)}/{len(take_indices)} ch | {actual_dur:.2f}s",
                                f"Rekam {n_ch}ch ({sr_read} Hz) & pemisahan ke {len(extracted_files)} channel berhasil.",
                                {"extracted": len(extracted_files), "expected": len(take_indices), "duration_sec": round(actual_dur, 2)},
                            ))
                        else:
                            checks.append(_make_check(
                                "CHK-05",
                                "Capture & Channel Split",
                                "WARN" if extracted_files else "FAIL",
                                f"{len(extracted_files)}/{len(take_indices)} ch | {actual_dur:.2f}s",
                                f"Hanya {len(extracted_files)} dari {len(take_indices)} channel berhasil diekstrak.",
                            ))
                    else:
                        checks.append(_make_check("CHK-05", "Capture & Channel Split", "SKIP", "-", "Dilewati oleh pengguna."))

                    # Mic health metrics (tetap dihitung untuk tampilan meter jika ada data)
                    mic_metrics, loudest_mic = analyze_mic_channels(data, take_indices)
                    if do_mic:
                        checks.append(evaluate_mic_health_check(mic_metrics))
                    else:
                        checks.append(_make_check(
                            "CHK-06", "Mic Signal Health", "SKIP", "-",
                            "Dilewati (mode tanpa mikrofon).",
                        ))

                    if do_pipeline:
                        checks.append(check_dsp_pipeline(
                            extracted_files,
                            sample_rate=sr_read,
                            config=cfg,
                            sample_duration_sec=actual_dur,
                        ))
                    else:
                        checks.append(_make_check("CHK-07", "DSP & TDOA Budget (RTF)", "SKIP", "-", "Dilewati oleh pengguna."))

    # Hitung overall status
    statuses = [c["status"] for c in checks]
    if "FAIL" in statuses:
        overall = "FAIL"
    elif "WARN" in statuses:
        overall = "WARN"
    elif "PASS" in statuses:
        overall = "PASS"
    else:
        overall = "SKIP"

    return {
        "overall_status": overall,
        "timestamp": _now_iso(),
        "drone_profile": active_profile,
        "configured_device": device,
        "checks": checks,
        "mic_metrics": mic_metrics,
        "loudest_mic": loudest_mic,
    }


def capture_live_mic_sample(
    audio_system=None,
    config_manager=None,
    duration_sec: float = 0.4,
) -> Dict[str, Any]:
    """
    Ambil 1 slice audio cepat (~0.4s) untuk Live Mic Tap / Mapping Monitor.
    Mengembalikan level RMS, dBFS, Peak, status per mic, dan loudest_mic.
    """
    cfg = config_manager.get_all() if config_manager is not None else {}
    device, active_profile, fmt, rate, channels, take_indices = _resolve_capture_params(cfg)
    dur = max(0.2, min(2.0, float(duration_sec)))

    with _DIAG_LOCK:
        with tempfile.TemporaryDirectory(prefix="mdi_micmon_") as tmpdir:
            raw_wav = os.path.join(tmpdir, "slice.wav")
            ok, msg = capture_audio_sample(
                device=device,
                fmt=fmt,
                rate=rate,
                channels=channels,
                duration_sec=dur,
                output_wav=raw_wav,
            )
            if not ok:
                raise RuntimeError(msg)

            data, sr_read = sf.read(raw_wav, always_2d=True)
            mic_metrics, loudest_mic = analyze_mic_channels(data, take_indices)

    return {
        "timestamp": _now_iso(),
        "sample_rate": int(sr_read),
        "duration_sec": round(data.shape[0] / float(sr_read), 3) if sr_read else dur,
        "mic_metrics": mic_metrics,
        "loudest_mic": loudest_mic,
    }
