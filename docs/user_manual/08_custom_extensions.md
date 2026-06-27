# Bab 8: Ekstensi Kustom

Sistem MDI dirancang dengan arsitektur plugin — operator dan pengembang dapat menambahkan algoritma baru tanpa mengubah kode inti. Terdapat dua jenis ekstensi yang didukung:

1. **Custom SSL Method** — Algoritma estimasi posisi kustom (untuk Ground Station)
2. **Custom Audio Filter** — Algoritma noise reduction kustom (untuk Drone System)

---

## 8.1 Custom SSL Method (Ground Station)

### Apa itu Custom SSL Method?

Custom SSL Method adalah file Python yang berisi implementasi algoritma Sound Source Localization (SSL) — estimasi posisi sumber suara dari data TDOA. Setelah file ditambahkan, metode ini akan muncul otomatis di dropdown **"Metode Kalkulasi TDOA"** pada tab Process.

### 8.1.1 Cara Menambahkan Custom SSL Method

#### Cara 1 — Melalui GUI (Direkomendasikan)

1. Buka tab **Process** di Ground Station
2. Klik tombol **"➕ Add Custom Method…"**
3. Pilih file `.py` dari dialog file browser
4. File otomatis disalin ke folder `custom_ssl_methods/`
5. Metode langsung muncul di dropdown tanpa perlu restart

#### Cara 2 — Manual (Salin Langsung ke Folder)

1. Temukan folder `custom_ssl_methods/` di lokasi instalasi Ground Station:
   - Dari source code: `Prototype/custom_ssl_methods/`
   - Dari distribusi `.exe`: di folder sebelah `MDI_Ground.exe`
2. Salin file `.py` ke dalam folder tersebut
3. Di tab Process, klik **"↻ Refresh Metode"** — metode baru akan muncul di dropdown

> ℹ️ **Tidak perlu registrasi eksplisit.** Registry bersifat *auto-discover* — cukup taruh file di folder yang benar.

### 8.1.2 Kontrak Fungsi

Setiap file custom SSL method **wajib** mengandung fungsi `solve` dengan signature berikut:

```python
def solve(event_data: dict, mic_positions: dict, config: dict) -> tuple:
    ...
    return estimated_pos, cluster_size, clusters_info
```

**Parameter Input:**

| Parameter | Tipe | Deskripsi |
|---|---|---|
| `event_data` | `dict` | Data satu event dari JSON, berisi kunci `"tdoa"` |
| `mic_positions` | `dict` | Posisi mikrofon: `{"mic0": {"x":.., "y":.., "z":..}, ...}` |
| `config` | `dict` | Konfigurasi sistem (kecepatan suara, cluster EPS, dll.) |

**Nilai Kembalian:**

| Elemen | Tipe | Deskripsi |
|---|---|---|
| `estimated_pos` | `list[float]` atau `None` | Koordinat `[x, y, z]` dalam meter, atau `None` jika gagal |
| `cluster_size` | `int` atau `None` | Ukuran cluster yang dipilih, atau `None` jika tidak ada clustering |
| `clusters_info` | `list[str]` atau `None` | Deskripsi tiap cluster, atau `None` |

**Config Keys yang tersedia dalam parameter `config`:**

```python
config.get("speed_of_sound", 343.0)  # Kecepatan suara dalam m/s
config.get("cluster_eps", 1.0)        # Toleransi clustering dalam meter
config.get("mic_positions", {})       # Posisi mikrofon (sama dengan parameter)
```

### 8.1.3 Konstanta DISPLAY_NAME

Tambahkan konstanta ini di file agar nama metode dapat dibaca di dropdown:

```python
DISPLAY_NAME = "Nama Metode Saya"
```

Jika tidak ada, nama file akan digunakan sebagai fallback.

### 8.1.4 Format Data TDOA

`event_data["tdoa"]` berisi dictionary dengan format:

```python
{
  "mic0-mic1": 0.00123,   # tau_mic0 - tau_mic1 dalam detik
  "mic0-mic2": -0.00045,  # positif = mic0 lebih jauh dari sumber suara
  "mic1-mic2": -0.00078,
  # ... semua pasang C(n, 2) mikrofon
}
```

**Konvensi tanda:** `"mic_i-mic_j"` menyimpan `tau_i - tau_j`.

### 8.1.5 Template Lengkap

Gunakan template berikut sebagai titik awal:

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

    def get_pos(name):
        p = mic_positions[name]
        if isinstance(p, dict):
            return [p["x"], p["y"], p["z"]]
        return list(p)

    stations = [get_pos(m) for m in mic_names]

    # ─── Implementasi algoritma Anda di sini ──────────────────────────────

    # Contoh: kembalikan centroid mikrofon sebagai placeholder
    estimated_pos = list(np.mean(stations, axis=0))

    # Untuk metode tanpa clustering:
    #   return estimated_pos, None, None
    #
    # Untuk metode dengan clustering:
    #   return estimated_pos, cluster_size_int, ["Cluster 1: ...", "Cluster 2: ..."]

    return estimated_pos, None, None
```

### 8.1.6 Contoh: Simple Centroid Method

```python
"""
Centroid Method — Estimasi sederhana berbasis centroid mikrofon.
Hanya sebagai contoh demonstrasi kontrak fungsi.
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

### 8.1.7 Tips dan Troubleshooting SSL Method

> **Metode tidak muncul di dropdown?**
> Pastikan file tidak dimulai dengan underscore (`_`), dan memiliki fungsi `solve()` dengan signature yang benar.

> **Error saat dijalankan?**
> Cek log di panel Processing Log pada tab Process. Pesan error dari metode custom akan tampil di sana.

> **Metode membutuhkan library eksternal?**
> Pastikan library sudah terinstal di environment Python yang sama dengan MDI Ground Station.
> Contoh: `pip install scipy` jika menggunakan `scipy.optimize`.

---

## 8.2 Custom Audio Filter (Drone System)

### Apa itu Custom Audio Filter?

Custom Audio Filter adalah file Python yang berisi implementasi algoritma noise reduction kustom untuk sinyal audio. Filter ini dipanggil secara otomatis oleh `AudioProcessor` sebelum proses deteksi event dilakukan. Setelah ditambahkan ke Raspberry Pi dan Ground Station dikonfigurasi, filter baru akan muncul di dropdown **"Filter Method"** pada tab Config.

### 8.2.1 Cara Menambahkan Custom Audio Filter

1. Buat file `.py` dengan implementasi filter Anda (lihat kontrak dan template di bawah)
2. Transfer file ke **Raspberry Pi** (via SCP atau USB):
   ```bash
   scp my_filter.py pi@10.99.99.2:~/mdi/udara/drone_system/custom_filters/
   ```
   Jika folder `custom_filters/` belum ada, buat dulu:
   ```bash
   ssh pi@10.99.99.2
   mkdir -p ~/mdi/udara/drone_system/custom_filters/
   ```
3. **Restart Drone System** di Raspberry Pi:
   ```bash
   sudo systemctl restart mdi_drone.service
   # atau Ctrl+C lalu python run_drone_system.py
   ```
4. Di **Ground Station**, buka tab Config → sub-tab Raspberry Pi
5. Klik tombol **Refresh** pada panel Filter Method, atau restart Ground Station
6. Filter baru muncul di dropdown Filter Method

> ℹ️ **Auto-discover:** Registry filter bersifat otomatis. Tidak perlu mendaftarkan filter secara eksplisit di kode manapun.

### 8.2.2 Kontrak Kelas

Setiap custom filter **wajib** berupa kelas Python yang mewarisi `BaseAudioFilter`:

```python
from drone_system.tdoa.base_filter import BaseAudioFilter
```

**Method yang wajib diimplementasikan:**

#### `apply(audio, sample_rate) -> np.ndarray`

```python
def apply(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
    ...
    return filtered_audio
```

| Parameter | Tipe | Deskripsi |
|---|---|---|
| `audio` | `np.ndarray`, shape `(N,)` | Array 1D sinyal audio, dtype float32 atau float64 |
| `sample_rate` | `int` | Sample rate audio (contoh: 48000) |
| **Return** | `np.ndarray` | Array 1D dengan panjang yang sama, sinyal yang sudah difilter |

**Method opsional — direkomendasikan untuk dikonfigurasi dari Ground Station:**

#### `get_params() -> dict`

```python
def get_params(self) -> dict:
    return {
        "threshold": self.threshold,  # nilai saat ini
        "mode": self.mode
    }
```

Kembalikan dictionary berisi parameter konfigurasi filter saat ini.

#### `set_params(params: dict)`

```python
def set_params(self, params: dict):
    self.threshold = params.get("threshold", self.threshold)
    self.mode = params.get("mode", self.mode)
```

Terapkan perubahan parameter dari Ground Station.

#### `get_param_schema() -> dict`

```python
def get_param_schema(self) -> dict:
    return {
        "threshold": {"type": "float", "default": 0.5, "min": 0.0, "max": 1.0},
        "mode": {"type": "choice", "default": "fast", "choices": ["fast", "accurate"]}
    }
```

Definisikan skema parameter — digunakan Ground Station untuk membangun form konfigurasi secara dinamis.

**Tipe yang didukung dalam skema:**
- `"float"`: Input angka desimal dengan batas min/max
- `"int"`: Input angka bulat
- `"bool"`: Checkbox
- `"choice"`: Dropdown dengan pilihan tetap

### 8.2.3 Konstanta Kelas

| Konstanta | Tipe | Deskripsi |
|---|---|---|
| `NAME` | `str` | ID unik filter (wajib) |
| `DISPLAY_NAME` | `str` | Nama yang tampil di UI (opsional, default = NAME) |
| `DESCRIPTION` | `str` | Deskripsi singkat (opsional) |

### 8.2.4 Template Lengkap

```python
"""
My Custom Filter — Deskripsi singkat.
"""

import numpy as np

# Import BaseAudioFilter — gunakan path relatif internal
try:
    from ..base_filter import BaseAudioFilter
except ImportError:
    from drone_system.tdoa.base_filter import BaseAudioFilter


class MyCustomFilter(BaseAudioFilter):
    """Implementasi custom audio filter."""

    NAME = "my_custom_filter"
    DISPLAY_NAME = "My Custom Filter"
    DESCRIPTION = "Deskripsi singkat tentang cara kerja filter ini."

    def __init__(self):
        self.threshold = 0.5  # parameter default

    def apply(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Terapkan noise reduction ke sinyal audio.

        Args:
            audio:        Sinyal audio 1D (float32/float64)
            sample_rate:  Sample rate dalam Hz

        Returns:
            Sinyal yang sudah difilter (array 1D dengan panjang sama)
        """
        # ─── Implementasi Anda di sini ────────────────────────────────────
        filtered = audio.copy()
        # Contoh: zero-out sinyal di bawah threshold
        filtered[np.abs(filtered) < self.threshold * np.max(np.abs(filtered))] = 0.0
        return filtered

    def get_params(self) -> dict:
        return {"threshold": self.threshold}

    def set_params(self, params: dict):
        self.threshold = float(params.get("threshold", self.threshold))

    def get_param_schema(self) -> dict:
        return {
            "threshold": {
                "type": "float",
                "default": 0.5,
                "min": 0.0,
                "max": 1.0,
                "label": "Noise Threshold",
                "description": "Amplitudo minimum sinyal yang dipertahankan (rasio terhadap max)."
            }
        }
```

### 8.2.5 Tips dan Troubleshooting Audio Filter

> **Filter tidak muncul di dropdown setelah ditambahkan?**
> Pastikan file sudah ada di `drone_system/custom_filters/` dan Drone System sudah di-restart. Cek log terminal RPi untuk error import.

> **Filter muncul tapi error saat dijalankan?**
> Buka log drone (`journalctl -u mdi_drone.service -f`) dan cari pesan error. Pastikan method `apply()` selalu mengembalikan array dengan panjang yang sama dengan input.

> **Perubahan parameter dari Ground Station tidak tersimpan?**
> Pastikan method `set_params()` dan `get_param_schema()` sudah diimplementasikan. Tanpa ini, Ground Station tidak bisa mengirim parameter ke filter.

> **Library eksternal tidak ditemukan?**
> Install library di Raspberry Pi dengan:
> ```bash
> cd ~/mdi/udara
> source .venv/bin/activate
> pip install nama_library
> ```
