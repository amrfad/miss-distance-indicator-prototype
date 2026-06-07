# Panduan Custom Audio Filter — Miss Distance Indicator

Dokumen ini menjelaskan cara membuat **Custom Audio Filter** yang kompatibel dengan sistem MDI Drone (Udara).
Setelah ditambahkan, metode filter Anda akan muncul otomatis di dropdown **"Filter Method"** pada tab Config Ground Station.

---

## Apa itu Custom Audio Filter?

Custom Audio Filter adalah file Python (`.py`) yang berisi implementasi algoritma noise reduction pada sinyal audio.
Filter ini akan dipanggil secara otomatis oleh `AudioProcessor` sebelum proses deteksi event dilakukan.

---

## Cara Menambahkan Custom Filter

### Manual — Salin ke Folder `custom_filters/`

1. Temukan folder `custom_filters/` di dalam direktori drone:
   ```
   udara/drone_system/custom_filters/
   ```
   Jika folder belum ada, buat secara manual.

2. Salin file `.py` Anda ke dalam folder tersebut.

3. **Restart sistem drone** (`python run_drone_system.py`).
   Registry akan otomatis mendeteksi dan mendaftarkan filter Anda saat startup.

4. Di Ground Station, refresh config tab atau restart Ground Station.
   Metode baru akan muncul di dropdown **"Filter Method"**.

> **Catatan:** Tidak perlu mendaftarkan filter secara eksplisit di kode manapun.
> Registry bersifat *auto-discover* — cukup taruh file di folder yang benar.

---

## Kontrak Kelas

Setiap custom filter **wajib** berupa kelas Python yang mewarisi `BaseAudioFilter`:

```python
from udara.drone_system.base_filter import BaseAudioFilter
```

> Saat diletakkan di `custom_filters/`, import path menggunakan relative import internal.
> Lihat contoh di bawah untuk pola yang benar.

### Method yang Wajib Diimplementasikan

#### 1. `apply(audio, sample_rate) -> np.ndarray`

```python
def apply(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
    ...
    return filtered_audio
```

| Parameter | Tipe | Deskripsi |
|-----------|------|-----------|
| `audio` | `np.ndarray` | Array 1D float audio satu channel |
| `sample_rate` | `int` | Sample rate dalam Hz (misalnya 48000) |

**Return:** `np.ndarray` 1D dengan panjang yang **sama atau lebih pendek** dari input.
- Nilai harus dalam rentang `[-1.0, 1.0]` (clip jika perlu)
- Dtype harus sama dengan input

> **Panjang Output:** Jika filter melakukan trimming (seperti spectral gating yang membuang
> 0.8s awal/akhir), `processor.py` akan secara otomatis menyinkronkan panjang array
> antar-channel. Tidak perlu khawatir soal ini.

#### 2. `get_params() -> dict`

```python
def get_params(self) -> dict:
    return {
        "nama_param": {
            "value": nilai_default,      # Required
            "type": "float",             # Required: "float" | "int" | "bool" | "str"
            "min": 0.0,                  # Opsional (untuk float/int)
            "max": 1.0,                  # Opsional (untuk float/int)
            "step": 0.1,                 # Opsional (untuk float/int)
            "description": "...",        # Opsional, tampil sebagai tooltip di UI
        },
        # ... parameter lainnya
    }
```

Dictionary ini digunakan oleh Ground Station untuk **merender form parameter secara otomatis**:

| Tipe | Widget yang dirender |
|------|----------------------|
| `"float"` | `QDoubleSpinBox` |
| `"int"` | `QSpinBox` |
| `"bool"` | `QCheckBox` |
| `"str"` | `QLineEdit` |

Jika filter tidak memiliki parameter, kembalikan `{}` (dict kosong).

#### 3. `is_available() -> bool` *(staticmethod)*

```python
@staticmethod
def is_available() -> bool:
    ...
```

Kembalikan `True` jika semua library yang dibutuhkan filter ini sudah terinstall.
Kembalikan `False` jika ada dependensi yang hilang — filter akan otomatis di-skip oleh registry
(tidak menyebabkan error).

**Pola yang direkomendasikan:**

```python
try:
    import my_special_library
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

@staticmethod
def is_available() -> bool:
    return _AVAILABLE
```

#### 4. `get_display_name() -> str` *(classmethod, opsional)*

```python
@classmethod
def get_display_name(cls) -> str:
    return "Nama yang Tampil di Dropdown"
```

Jika tidak di-override, nama class Python akan digunakan sebagai tampilan.

---

## Template Lengkap

Salin template berikut sebagai titik awal untuk custom filter Anda:

```python
"""
NamaFilter — Deskripsi singkat algoritma ini.

Letakkan file ini di:
  udara/drone_system/custom_filters/nama_filter.py

Registry akan otomatis mendaftarkan filter ini dengan key "nama_filter".
"""

import numpy as np

# ── Cek dependensi (ganti dengan library yang Anda butuhkan) ──────────
try:
    import some_library
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

# ── Wajib: import BaseAudioFilter ─────────────────────────────────────
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from base_filter import BaseAudioFilter


class NamaFilter(BaseAudioFilter):
    """
    Deskripsi detail algoritma filter ini.
    """

    def __init__(
        self,
        param_float: float = 0.5,
        param_int: int = 10,
        param_bool: bool = False,
        **kwargs,
    ):
        """
        Konstruktor menerima semua parameter sebagai keyword arguments.
        Nilai default digunakan jika Ground Station tidak mengirim override.
        """
        super().__init__(**kwargs)
        self.param_float = float(param_float)
        self.param_int = int(param_int)
        self.param_bool = bool(param_bool)

    def apply(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        """
        Terapkan filtering ke audio 1D array.
        """
        if not _AVAILABLE:
            # Graceful fallback jika dependensi tidak ada
            return audio

        # ─── Implementasi algoritma Anda di sini ──────────────────────

        filtered = audio.copy()  # Ganti dengan logika sesungguhnya

        # Clip ke valid range sebelum return
        filtered = np.clip(filtered, -1.0, 1.0)
        return filtered.astype(audio.dtype)

    def get_params(self) -> dict:
        """
        Deskripsikan semua parameter agar Ground Station bisa merender form.
        Kembalikan {} jika tidak ada parameter.
        """
        return {
            "param_float": {
                "value": self.param_float,
                "type": "float",
                "min": 0.0,
                "max": 1.0,
                "step": 0.05,
                "description": "Deskripsi singkat parameter ini",
            },
            "param_int": {
                "value": self.param_int,
                "type": "int",
                "min": 1,
                "max": 100,
                "step": 1,
                "description": "Deskripsi singkat parameter ini",
            },
            "param_bool": {
                "value": self.param_bool,
                "type": "bool",
                "description": "Deskripsi singkat parameter ini",
            },
        }

    @staticmethod
    def is_available() -> bool:
        return _AVAILABLE

    @classmethod
    def get_display_name(cls) -> str:
        return "Nama Filter (tampil di dropdown)"
```

---

## Contoh: Median Filter (Low-pass Sederhana)

Filter ini tidak membutuhkan library eksternal apapun selain NumPy:

```python
"""
Median Filter — Simple low-pass noise reduction via rolling median.

Letakkan file ini di:
  udara/drone_system/custom_filters/median_filter.py
"""

import numpy as np
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from base_filter import BaseAudioFilter


class MedianFilter(BaseAudioFilter):
    """
    Mengurangi noise impulsif (klik, pop) menggunakan rolling median window.
    Efektif untuk noise non-stasioner impulsif, tidak optimal untuk Gaussian noise.
    """

    def __init__(self, window_size: int = 5, normalize: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.window_size = int(window_size)
        self.normalize = bool(normalize)

    def apply(self, audio: np.ndarray, sample_rate: int) -> np.ndarray:
        from numpy.lib.stride_tricks import sliding_window_view
        half = self.window_size // 2
        padded = np.pad(audio, (half, half), mode='edge')
        windows = sliding_window_view(padded, self.window_size)
        filtered = np.median(windows, axis=-1)

        if self.normalize:
            peak = np.max(np.abs(filtered))
            if peak > 0:
                filtered = filtered / peak

        return np.clip(filtered, -1.0, 1.0).astype(audio.dtype)

    def get_params(self) -> dict:
        return {
            "window_size": {
                "value": self.window_size,
                "type": "int",
                "min": 3,
                "max": 51,
                "step": 2,
                "description": "Ukuran window rolling median (ganjil, lebih besar = lebih smooth)",
            },
            "normalize": {
                "value": self.normalize,
                "type": "bool",
                "description": "Normalisasi output audio",
            },
        }

    @staticmethod
    def is_available() -> bool:
        return True  # Hanya butuh NumPy, selalu tersedia

    @classmethod
    def get_display_name(cls) -> str:
        return "Median Filter (custom)"
```

---

## Aturan Penamaan File

| Aturan | Contoh |
|--------|--------|
| Gunakan `snake_case` | `my_custom_filter.py` |
| Nama file menjadi **key** registry | `"my_custom_filter"` |
| Jangan diawali underscore `_` | `_helper.py` akan di-skip |
| Satu class `BaseAudioFilter` per file | Class pertama yang valid yang diambil |

---

## Bagaimana Custom Filter Diproses

```
Startup Drone
     │
     ▼
filter_registry._initialize()
     │
     ├── Load built-in filters (spectral_gating, wavelet, wiener, passthrough)
     │
     └── Scan udara/drone_system/custom_filters/*.py
              │
              ├── [OK]   → Subclass BaseAudioFilter ditemukan & is_available() == True
              │              → Didaftarkan dengan key = nama file (tanpa .py)
              │
              ├── [SKIP] → Subclass ditemukan tapi is_available() == False
              │              → Di-skip, dependensi tidak tersedia
              │
              ├── [WARN] → File ada tapi tidak mengandung subclass BaseAudioFilter
              │              → Peringatan di log, tidak menyebabkan crash
              │
              └── [ERR]  → SyntaxError / ImportError saat load file
                             → Error di log, filter lain tetap berjalan

Ground Station (saat connect ke drone)
     │
     ▼
GET /filter-schemas
     │
     ▼
FilterConfigPanel merender dropdown + form parameter otomatis

User pilih metode → SAVE CONFIG → PATCH /config
     │
     ▼
drone_config["filter_method"] = "my_custom_filter"
drone_config["filter_configs"]["my_custom_filter"] = {param: value, ...}

Recording selesai → AudioProcessor.filter_channels()
     │
     ▼
FilterClass = filter_registry.get_method_class("my_custom_filter")
instance = FilterClass(**method_params)
filtered = instance.apply(channel_audio, sample_rate)
```

---

## Tips & Troubleshooting

> **Filter tidak muncul di dropdown?**
> Pastikan:
> - File berada di `udara/drone_system/custom_filters/`
> - Nama file tidak diawali `_`
> - Class mewarisi `BaseAudioFilter` (bukan class biasa)
> - `is_available()` mengembalikan `True`
> - Drone sudah di-restart setelah file ditambahkan

> **Error `ModuleNotFoundError: No module named 'base_filter'`?**
> Tambahkan path resolution di awal file:
> ```python
> import sys, os
> sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
> from base_filter import BaseAudioFilter
> ```

> **`is_available()` harus return True/False atau boleh raise Exception?**
> Harus return `True` atau `False` — jangan raise exception.
> Exception di dalam `is_available()` akan menyebabkan filter di-skip dengan log `[ERR]`.

> **Filter butuh library eksternal?**
> Pastikan library sudah terinstall di environment Python Raspberry Pi:
> ```bash
> pip install nama-library
> ```
> Dan gunakan pola `try/except ImportError` untuk `is_available()`.

> **Bagaimana cara menguji filter tanpa drone?**
> Jalankan test sederhana langsung dari Python:
> ```python
> import sys, numpy as np
> sys.path.insert(0, 'udara')
> from drone_system.custom_filters.my_filter import MyFilter
>
> f = MyFilter(param_float=0.8)
> audio = np.random.randn(48000).astype(np.float32)
> out = f.apply(audio, 48000)
> print(f"Input shape: {audio.shape}, Output shape: {out.shape}")
> print(f"Output range: [{out.min():.3f}, {out.max():.3f}]")
> ```

> **Apakah `get_params()` harus mengembalikan nilai yang sudah ter-update dari `__init__`?**
> Ya. `get_params()` harus mencerminkan nilai **instance saat ini**, bukan hardcoded default.
> Ini penting agar Ground Station menampilkan nilai yang akurat saat form pertama dibuka.
