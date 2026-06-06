# Panduan Custom SSL Method — Miss Distance Indicator

Dokumen ini menjelaskan cara membuat **Custom SSL Method** yang kompatibel dengan sistem MDI Ground Station.

---

## Apa itu Custom SSL Method?

Custom SSL Method adalah file Python (`.py`) yang berisi implementasi algoritma estimasi posisi (Sound Source Localization) menggunakan data TDOA. Setelah ditambahkan, metode ini akan muncul otomatis di dropdown "Metode Kalkulasi TDOA" pada tab Process.

---

## Cara Menambahkan Custom Method

Ada **dua cara** untuk menambahkan custom method:

### Cara 1 — Melalui Antarmuka GUI (Direkomendasikan)

1. Buka tab **Process** di Ground Station
2. Klik tombol **"➕ Add Custom Method…"**
3. Pilih file `.py` Anda dari dialog
4. File akan otomatis disalin ke folder `custom_ssl_methods/`
5. Metode langsung muncul di dropdown

### Cara 2 — Manual (Salin Langsung ke Folder)

1. Temukan folder `custom_ssl_methods/` (berada di sebelah `MDI_Ground.exe`)
2. Salin file `.py` Anda ke dalam folder tersebut
3. Klik tombol **"↻ Refresh Metode"** di tab Process

---

## Kontrak Fungsi

Setiap file custom method **wajib** memiliki:

### 1. Fungsi `solve`

```python
def solve(event_data: dict, mic_positions: dict, config: dict) -> tuple:
    ...
    return estimated_pos, cluster_size, clusters_info
```

**Parameter:**

| Parameter | Tipe | Deskripsi |
|-----------|------|-----------|
| `event_data` | `dict` | Data satu event dari JSON, berisi kunci `"tdoa"` |
| `mic_positions` | `dict` | Posisi mikrofon: `{"mic0": {"x":..,"y":..,"z":..}, ...}` |
| `config` | `dict` | Konfigurasi sistem (lihat bagian Config Keys) |

**Return Value:**

| Elemen | Tipe | Deskripsi |
|--------|------|-----------|
| `estimated_pos` | `list[float]` atau `None` | Koordinat `[x, y, z]` dalam meter, atau `None` jika gagal |
| `cluster_size` | `int` atau `None` | Ukuran cluster yang dipilih, atau `None` jika metode tidak menggunakan clustering |
| `clusters_info` | `list[str]` atau `None` | Deskripsi tiap cluster, atau `None` |

### 2. Konstanta `DISPLAY_NAME`

```python
DISPLAY_NAME = "Nama Metode Saya"
```

Teks ini akan ditampilkan di dropdown UI. Jika tidak ada, nama file akan digunakan.

---

## Config Keys yang Tersedia

```python
config.get("speed_of_sound", 343.0)    # Kecepatan suara dalam m/s
config.get("cluster_eps", 1.0)         # Toleransi clustering dalam meter
config.get("mic_positions", {})        # Posisi mikrofon (sama dengan parameter)
```

---

## Format Data TDOA

`event_data["tdoa"]` berisi dictionary dengan format:

```python
{
  "mic0-mic1": 0.00123,   # tau_mic0 - tau_mic1 dalam detik
  "mic0-mic2": -0.00045,  # positif = mic0 lebih jauh dari sumber
  "mic1-mic2": -0.00078,
  # ... semua pasang C(n,2) mikrofon
}
```

**Konvensi tanda:** `"mic_i-mic_j"` menyimpan `tau_i - tau_j`.

---

## Template Lengkap

Salin template berikut sebagai titik awal:

```python
"""
Nama Metode Saya — Deskripsi singkat algoritma

Kontrak Fungsi:
  solve(event_data, mic_positions, config) -> (estimated_pos, cluster_size, clusters_info)
"""

import numpy as np

# Nama yang ditampilkan di dropdown UI
DISPLAY_NAME = "Nama Metode Saya"

# Default kecepatan suara jika tidak ada di config
_DEFAULT_C = 343.0


def solve(event_data: dict, mic_positions: dict, config: dict) -> tuple:
    """
    Estimasi posisi sumber suara dari data TDOA.

    Args:
        event_data:    Data event berisi 'tdoa' dict
        mic_positions: Dict posisi mikrofon
        config:        Konfigurasi sistem

    Returns:
        (estimated_pos, cluster_size, clusters_info)
    """
    c = config.get("speed_of_sound", _DEFAULT_C)
    tdoa_data = event_data.get("tdoa", {})

    # Normalisasi mic_positions ke list [x, y, z]
    mic_names = list(mic_positions.keys())
    n_mics = len(mic_names)

    def get_pos(name):
        p = mic_positions[name]
        if isinstance(p, dict):
            return [p["x"], p["y"], p["z"]]
        return list(p)

    stations = [get_pos(m) for m in mic_names]

    # ─── Implementasi algoritma Anda di sini ──────────────────────────────

    # Contoh: kembalikan centroid mikrofon sebagai placeholder
    estimated_pos = list(np.mean(stations, axis=0))

    # Untuk metode yang tidak menggunakan clustering:
    #   return estimated_pos, None, None
    #
    # Untuk metode dengan clustering:
    #   return estimated_pos, cluster_size_int, ["Cluster 1: ...", "Cluster 2: ..."]

    return estimated_pos, None, None
```

---

## Contoh: Simple Centroid Method

```python
"""
Centroid Method — Estimasi sederhana berbasis centroid mikrofon

File ini hanya sebagai contoh demonstrasi kontrak fungsi.
"""

import numpy as np

DISPLAY_NAME = "Centroid (Demo)"

def solve(event_data, mic_positions, config):
    stations = []
    for name, p in mic_positions.items():
        if isinstance(p, dict):
            stations.append([p["x"], p["y"], p["z"]])
        else:
            stations.append(list(p))

    centroid = list(np.mean(stations, axis=0))
    return centroid, None, None
```

---

## Tips & Troubleshooting

> **Metode tidak muncul di dropdown?**
> Pastikan file tidak dimulai dengan underscore (`_`), dan memiliki fungsi `solve()`.

> **Error saat dijalankan?**
> Cek log di panel Processing Log. Pesan error dari metode custom akan tampil di sana.

> **Metode butuh library eksternal?**
> Pastikan library sudah terinstall di environment Python yang sama dengan MDI Ground Station.
> Contoh: `pip install scipy` jika menggunakan `scipy.optimize`.
