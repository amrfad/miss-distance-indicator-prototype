# darat/core/session_merger.py
"""
Session Merger Module
Menggabungkan beberapa file JSON chunk TDOA yang diterima selama satu sesi rekaman
menjadi satu file master session JSON terpadu.
"""

import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any


def merge_session_jsons(
    file_paths: List[str],
    output_dir: str,
    session_id: Optional[str] = None,
    tolerance_sec: float = 0.05,
) -> Optional[str]:
    """
    Gabungkan daftar file JSON chunk TDOA menjadi satu file master session JSON.

    Langkah yang dilakukan:
      1. Membaca dan memvalidasi file JSON chunk yang ada dalam daftar.
      2. Mengumpulkan metadata sesi (sample rate, channel, profile mic, dsb.).
      3. Menduplikasi & memfilter event-event yang saling tumpang tindih (overlap).
      4. Mengurutkan seluruh event secara kronologis berdasarkan waktu absolut.
      5. Melakukan penomoran ulang sekuensial pada event_number (1..N).
      6. Menyimpan hasil penggabungan ke output_dir/tdoa_session_{timestamp}.json.

    Args:
        file_paths: List path file JSON chunk yang diterima selama sesi rekaman.
        output_dir: Direktori tempat menyimpan file hasil penggabungan.
        session_id: Optional ID sesi eksplisit. Jika None, diambil dari data event/chunk.
        tolerance_sec: Toleransi selisih waktu (detik) untuk deteksi duplikasi overlap.

    Returns:
        Path absolut ke file JSON hasil penggabungan, atau None jika gagal/tidak ada data valid.
    """
    if not file_paths:
        return None

    # 1. Filter file yang benar-benar ada di filesystem
    valid_files = [p for p in file_paths if p and os.path.isfile(p)]
    if not valid_files:
        return None

    parsed_chunks: List[Dict[str, Any]] = []
    for path in valid_files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    parsed_chunks.append(data)
        except Exception:
            # Lewati file korup atau tidak dapat dibaca
            continue

    if not parsed_chunks:
        return None

    # 2. Ekstraksi metadata dasar dari chunk pertama yang valid
    first_chunk = parsed_chunks[0]
    sample_rate = first_chunk.get("sample_rate", 48000)
    device_profile = first_chunk.get("device_profile", "Unknown")
    format_str = first_chunk.get("format", "Unknown")
    channels = first_chunk.get("channels", 0)
    num_mics = first_chunk.get("num_mics", 0)
    num_tdoa_pairs = first_chunk.get("num_tdoa_pairs", 0)
    timestamp = first_chunk.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # 3. Tentukan session_id
    extracted_session_id = session_id
    if not extracted_session_id:
        # Coba cari session_id di dalam event terlebih dahulu (dibuat oleh drone saat start)
        for chunk in parsed_chunks:
            events = chunk.get("events", [])
            for ev in events:
                if isinstance(ev, dict) and ev.get("session_id"):
                    extracted_session_id = ev.get("session_id")
                    break
            if extracted_session_id:
                break

    if not extracted_session_id:
        # Fallback ke session_id top-level chunk
        for chunk in parsed_chunks:
            top_sess = chunk.get("session_id")
            if top_sess:
                extracted_session_id = top_sess
                break

    if not extracted_session_id:
        extracted_session_id = f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    # 4. Agregasi event dari semua chunk dengan deduplikasi & ekstraksi sort key
    unique_events: List[Dict[str, Any]] = []
    seen_intervals: List[tuple[float, float]] = []  # [(abs_start, abs_end)]
    seen_legacy_keys: set = set()

    for chunk in parsed_chunks:
        events = chunk.get("events", [])
        if not isinstance(events, list):
            continue

        chunk_offset = chunk.get("chunk_offset_sec", 0.0)

        for ev in events:
            if not isinstance(ev, dict):
                continue

            # Buat salinan event agar tidak mengubah referensi asli
            ev_copy = dict(ev)

            # Tentukan waktu mulai absolut
            abs_start = ev_copy.get("event_abs_start_sec")
            abs_end = ev_copy.get("event_abs_end_sec")

            if abs_start is not None:
                try:
                    start_val = float(abs_start)
                    end_val = float(abs_end) if abs_end is not None else (start_val + 0.25)

                    # Cek overlap dengan interval yang sudah diterima
                    is_dup = False
                    for seen_start, seen_end in seen_intervals:
                        overlap_start = max(seen_start - tolerance_sec, start_val - tolerance_sec)
                        overlap_end = min(seen_end + tolerance_sec, end_val + tolerance_sec)
                        if (overlap_end - overlap_start) > 0:
                            is_dup = True
                            break

                    if is_dup:
                        continue

                    seen_intervals.append((start_val, end_val))
                    ev_copy["_sort_time"] = start_val
                    unique_events.append(ev_copy)
                except (ValueError, TypeError):
                    ev_copy["_sort_time"] = 0.0
                    unique_events.append(ev_copy)
            else:
                # Fallback: hitung dari chunk_offset + start_in_chunk jika ada
                start_in_chunk = ev_copy.get("event_start_in_chunk")
                if start_in_chunk is not None:
                    try:
                        calculated_start = float(chunk_offset) + float(start_in_chunk)
                        ev_copy["event_abs_start_sec"] = calculated_start
                        ev_copy["_sort_time"] = calculated_start
                    except (ValueError, TypeError):
                        ev_copy["_sort_time"] = 0.0
                else:
                    # Fallback format lawas
                    chunk_ts = ev_copy.get("chunk_timestamp", "")
                    orig_num = ev_copy.get("event_number", "")
                    legacy_key = (chunk_ts, orig_num)
                    if legacy_key in seen_legacy_keys and chunk_ts:
                        continue
                    if chunk_ts:
                        seen_legacy_keys.add(legacy_key)
                    ev_copy["_sort_time"] = float(len(unique_events))

                unique_events.append(ev_copy)

    # 5. Urutkan event secara kronologis berdasarkan waktu absolut
    unique_events.sort(key=lambda item: item.get("_sort_time", 0.0))

    # 6. Renumber sekuensial event_number: 1, 2, ..., N & bersihkan internal sort key
    for idx, ev in enumerate(unique_events, start=1):
        ev["event_number"] = idx
        ev.pop("_sort_time", None)

    # 7. Hitung total durasi rekaman
    total_duration = 0.0
    if unique_events:
        max_end = 0.0
        for ev in unique_events:
            end_val = ev.get("event_abs_end_sec") or (ev.get("event_abs_start_sec", 0.0) + 0.5)
            try:
                max_end = max(max_end, float(end_val))
            except (ValueError, TypeError):
                pass
        total_duration = round(max_end + 1.0, 2)
    else:
        # Jika tidak ada event, jumlahkan durasi chunk jika tersedia
        for chunk in parsed_chunks:
            dur = chunk.get("chunk_duration_sec", 0.0) or chunk.get("total_recording_duration", 0.0)
            try:
                total_duration += float(dur)
            except (ValueError, TypeError):
                pass
        total_duration = round(total_duration, 2)

    # 8. Susun dokumen JSON terpadu
    merged_doc = {
        "session_id": extracted_session_id,
        "timestamp": timestamp,
        "merged_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_recording_duration": total_duration,
        "sample_rate": sample_rate,
        "event_count": len(unique_events),
        "chunk_count": len(parsed_chunks),
        "device_profile": device_profile,
        "format": format_str,
        "channels": channels,
        "num_mics": num_mics,
        "num_tdoa_pairs": num_tdoa_pairs,
        "type": "SESSION_TDOA_RESULTS",
        "events": unique_events,
    }

    # 9. Simpan ke output_dir
    os.makedirs(output_dir, exist_ok=True)
    out_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_filename = f"tdoa_session_{out_timestamp}.json"
    out_filepath = os.path.join(output_dir, out_filename)

    with open(out_filepath, "w", encoding="utf-8") as f:
        json.dump(merged_doc, f, indent=2, ensure_ascii=False)

    return out_filepath
