# Bab 9: Format File Output

Dokumen ini menjelaskan format semua file yang dihasilkan oleh sistem MDI, baik dari Drone System maupun dari Ground Station.

---

## 9.1 Struktur Folder Sesi Rekaman

Setiap kali sesi rekaman selesai (`STOP_REC` diproses), Drone System membuat folder baru di direktori output:

```
drone_recordings/
└── session_YYYYMMDD_HHMMSS/
    ├── raw_12ch.wav              ← Rekaman mentah semua channel audio
    ├── detected_events.csv       ← Daftar event dalam format CSV
    ├── session_events.json       ← Data event dalam format JSON
    ├── session_tdoa.json         ← Hasil TDOA per event (dikirim ke ground)
    ├── event_1/                  ← Audio per-event setelah noise reduction
    │   ├── mic0_clean.wav
    │   ├── mic1_clean.wav
    │   ├── mic2_clean.wav
    │   └── mic3_clean.wav
    ├── event_2/
    │   └── ...
    └── event_N/
        └── ...
```

**Format nama folder sesi:**
- `session_YYYYMMDD_HHMMSS` — timestamp saat perekaman dimulai
- Contoh: `session_20260627_103045`

---

## 9.2 File: `raw_12ch.wav`

**Deskripsi:** File WAV rekaman mentah dari Zoom Recorder, berisi semua channel yang direkam.

| Atribut | Nilai |
|---|---|
| Format | WAV (PCM) |
| Channels | Sesuai profil device (H8: hingga 12 channel; H6E: 6 channel) |
| Sample Rate | Sesuai konfigurasi `sample_rate` (default: 48000 Hz) |
| Bit Depth | H8: 24-bit (S24_3LE); H6E: 32-bit (S32_LE) |

> ℹ️ Hanya sebagian channel yang digunakan untuk pemrosesan (sesuai `num_mics_h8` dan `take_indices`). File `raw_12ch.wav` disimpan sebagai arsip lengkap.

---

## 9.3 File: `detected_events.csv`

**Deskripsi:** Daftar event yang terdeteksi dalam format CSV. Berguna untuk analisis dengan spreadsheet atau tools eksternal.

**Format kolom:**

| Kolom | Tipe | Contoh | Deskripsi |
|---|---|---|---|
| `event_number` | Integer | `1` | Nomor urut event |
| `start_time` | Float (detik) | `2.341` | Waktu mulai event dalam rekaman (detik dari awal) |
| `end_time` | Float (detik) | `2.785` | Waktu selesai event |
| `duration` | Float (detik) | `0.444` | Durasi event |
| `rms_energy` | Float | `0.0234` | Energi RMS rata-rata event |

**Contoh isi file:**
```csv
event_number,start_time,end_time,duration,rms_energy
1,2.341,2.785,0.444,0.0234
2,5.120,5.480,0.360,0.0189
3,8.921,9.340,0.419,0.0312
```

---

## 9.4 File: `session_events.json`

**Deskripsi:** Data event dalam format JSON yang lebih kaya dibanding CSV. Berisi informasi session dan detail tiap event.

**Struktur JSON:**

```json
{
  "session_id": "session_20260627_103045",
  "timestamp": "2026-06-27T10:30:45",
  "sample_rate": 48000,
  "event_count": 3,
  "events": [
    {
      "event_number": 1,
      "start_sample": 112368,
      "end_sample": 133680,
      "start_time": 2.341,
      "end_time": 2.785,
      "duration": 0.444,
      "rms_energy": 0.0234
    },
    {
      "event_number": 2,
      ...
    }
  ]
}
```

**Penjelasan field:**

| Field | Deskripsi |
|---|---|
| `session_id` | Identifikasi unik sesi rekaman |
| `timestamp` | Waktu mulai sesi dalam format ISO 8601 |
| `sample_rate` | Sample rate yang digunakan (Hz) |
| `event_count` | Jumlah total event yang terdeteksi |
| `events[].event_number` | Nomor urut event (mulai dari 1) |
| `events[].start_sample` / `end_sample` | Indeks sample audio awal/akhir event |
| `events[].start_time` / `end_time` | Waktu dalam detik dari awal rekaman |
| `events[].duration` | Durasi event dalam detik |
| `events[].rms_energy` | Energi RMS rata-rata event |

---

## 9.5 File: `tdoa.json` (di Drone) / `tdoa_YYYYMMDD_HHMMSS.json` (di Ground Station)

**Deskripsi:** Ini adalah file JSON hasil pemrosesan TDOA per chunk.
- **Di Drone:** Disimpan di subfolder chunk masing-masing dengan nama `tdoa.json` (contoh: `drone_recordings/session_xxx/chunks/chunk_xxx/tdoa.json`).
- **Di Ground Station:** Diterima secara real-time via serial dan disimpan di direktori kerja Ground Station dengan nama berformat `tdoa_YYYYMMDD_HHMMSS.json` (berdasarkan timestamp waktu penerimaan).

**Struktur JSON:**

```json
{
  "session_id": "session_20260627_103045",
  "timestamp": "2026-06-27T10:30:45",
  "event_count": 1,
  "config": {
    "sample_rate": 48000,
    "num_mics": 4,
    "active_profile": "H8"
  },
  "events": [
    {
      "event_number": 1,
      "chunk_timestamp": "20260627_103050_123456",
      "event_start_in_chunk": 2.341,
      "event_end_in_chunk": 2.785,
      "tdoa": {
        "mic0-mic1": 0.000124,
        "mic0-mic2": -0.000458,
        "mic0-mic3": 0.000089,
        "mic1-mic2": -0.000582,
        "mic1-mic3": -0.000035,
        "mic2-mic3": 0.000547
      }
    }
  ]
}
```

**Penjelasan field khusus:**

| Field | Tipe | Deskripsi |
|---|---|---|
| `events[].chunk_timestamp` | String | Timestamp pembuatan chunk di drone (digunakan Ground Station untuk deduplikasi event duplikat yang berada di overlap window) |
| `events[].event_start_in_chunk` | Float | Detik mulai event relatif terhadap awal chunk audio |
| `"mic_i-mic_j"` | Float (detik) | Selisih waktu kedatangan suara: τ_i − τ_j |

**Jumlah pasang TDOA** = C(n, 2) = n! / (2!(n-2)!)
- 4 mikrofon → 6 pasang
- 6 mikrofon → 15 pasang

---

## 9.6 File Audio Per-Event: `event_N/micX_clean.wav` (di Drone)

**Deskripsi:** Potongan audio bersih (setelah noise reduction) untuk satu event dan satu mikrofon, disimpan di dalam subfolder event masing-masing chunk di drone.

| Atribut | Nilai |
|---|---|
| Format | WAV mono |
| Durasi | Durasi event + `event_padding_sec` di kedua sisi |
| Sample Rate | Sama dengan sesi |
| Penamaan | `mic{N}_clean.wav` di mana N = indeks mikrofon |

---

## 9.7 File: `*_results.txt` (Output Ground Station)

**Deskripsi:** File teks yang dihasilkan Ground Station setelah memproses `session_tdoa.json`. Berisi ringkasan hasil estimasi posisi untuk semua event.

**Format file:**

```
Session: session_20260627_103045
Processed: 2026-06-27 10:32:15
Method: Bucher-Misra 3D
============================================================
Mic Positions:
  mic0: x=-1.580, y=0.770, z=0.090
  mic1: x=1.600, y=0.770, z=0.090
  mic2: x=-0.590, y=-0.920, z=-0.070
  mic3: x=0.590, y=-0.920, z=-0.050
============================================================

EVENT 1
  Start Time : 2.341 s
  Duration   : 0.444 s
  Position   : [1.234, -0.567, 2.891] m
  Cluster    : 5 consistent solutions
  Status     : VALID

EVENT 2
  Start Time : 5.120 s
  Duration   : 0.360 s
  Position   : FAILED
  Status     : FAILED (no valid solution)

EVENT 3
  Start Time : 8.921 s
  Duration   : 0.419 s
  Position   : [-0.312, 1.789, 1.543] m
  Cluster    : 3 consistent solutions
  Status     : VALID

============================================================
Summary: 3 events | 2 valid | 1 failed
```

**Lokasi file:** Disimpan di direktori kerja Ground Station (direktori yang sama dengan file JSON yang diproses), dengan nama `<session_id>_results.txt`.

---

## 9.8 Perbedaan File `session_events.json` vs `session_tdoa.json`

| Aspek | `session_events.json` | `session_tdoa.json` |
|---|---|---|
| Isi utama | Informasi deteksi event (waktu, durasi, energi) | Nilai TDOA antar mikrofon per event |
| Dibuat oleh | Drone (Event Detector) | Drone (TDOA Calculator) |
| Dikirim ke Ground | Tidak (disimpan lokal di RPi) | **Ya** — dikirim via serial |
| Digunakan untuk | Analisis pola deteksi | Estimasi posisi di Ground Station |
| Format | JSON | JSON |
