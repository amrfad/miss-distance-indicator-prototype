# AGENTS.md — AI Agent Reference Guide
## Miss Distance Indicator Prototype

> Dokumen ini adalah acuan utama untuk AI agent (Copilot, Antigravity, dsb.) yang akan
> memodifikasi, memperluas, atau debug codebase ini. Baca sebelum membuat perubahan apapun.

---

## 1. Gambaran Sistem

Sistem ini terdiri dari **dua subsistem** yang berjalan di perangkat terpisah:

| Subsistem | Direktori | Platform | Fungsi |
|-----------|-----------|----------|--------|
| **Darat (Ground Unit)** | `darat/` | Windows/Linux | GUI PyQt6 untuk konfigurasi (REST/Serial), command kontrol, pemrosesan TDOA, dan visualisasi |
| **Udara (Drone Unit)** | `udara/` | Linux (Raspberry Pi) | Merekam audio multi-channel, mendeteksi event, menghitung TDOA, mengirim ke ground |

Kedua subsistem berkomunikasi via **serial port** (UART) menggunakan protokol START/END marker.

### Alur Data Keseluruhan
```
[Drone] Audio Recording (arecord)
      ↓
[Drone] Channel Extraction + Noise Reduction (AudioProcessor)
      ↓
[Drone] Event Detection via RMS fusion (EventDetector)
      ↓
[Drone] TDOA Calculation GCC-PHAT (calculate_all_tdoa)
      ↓
[Drone] Serial TX → JSON dengan [START]/[END] marker (SerialCommunicator)
      ↓
[Ground] Serial RX → JSON buffering (JsonReceiver)
      ↓
[Ground] Bucher-Misra 3D + Clustering (process_event_tdoa)
      ↓
[Ground] 3D/2D Visualization (visualize_3d, visualize_2d_projections)
```

---

## 2. Struktur Direktori

```
Prototype/
├── AGENTS.md                     ← dokumen ini
├── darat/                        ← Ground Unit (working version)
│   ├── __init__.py
│   ├── main.py                   ← Entry point: python darat/main.py (PySide6 launcher)
│   ├── visualize_results.py      ← Matplotlib visualization
│   ├── core/                     ← Konfigurasi & state management
│   │   ├── config.py             ← Konstanta Ground Unit
│   │   ├── config_manager.py     ← Konfigurasi dinamis
│   │   └── file_transfer.py      ← Penerimaan & perutean berkas serial
│   ├── io/                       ← Komunikasi serial & I/O
│   │   ├── serial_manager.py     ← Driver Serial port
│   │   └── json_receiver.py      ← Parser data JSON [START]/[END]
│   ├── localization/                      ← Algoritma Sound Source Localization (SSL)
│   │   ├── process_json_tdoa.py  ← Orchestrator TDOA solver
│   │   ├── ssl_registry.py       ← Registry plugin SSL
│   │   └── builtin_ssl/          ← Implementasi solver (Bucher-Misra, Consensus, dll)
│   ├── api/                      ← Jaringan & REST Daemon
│   │   ├── config_api.py         ← REST API untuk konfigurasi UI
│   │   └── network_setup.py      ← Automasi Static IP Adapter
│   └── ui/                       ← Package antarmuka pengguna (PySide6)
│       ├── main.py
│       ├── dashboard.py          ← Main window & tab coordinator
│       ├── pages/                ← Layar-layar utama (Config, Command, Process, Visualize)
│       ├── services/             ← Bridge layer (SerialBridge, RestClient)
│       ├── widgets/              ← Komponen UI (StatusPanel, LogPanel, dll)
│       └── styles/               ← File .qss untuk tema antarmuka
├── udara/
│   ├── run_drone_system.py       ← Entry point drone
│   └── drone_system/
│       ├── main.py               ← Orchestrator online/offline mode
│       ├── config_api.py         ← REST API untuk konfigurasi drone
│       ├── network_setup.py      ← Konfigurasi IP drone
│       ├── core/                 ← Konfigurasi & pengendali utama
│       │   ├── config.py         ← Konstanta Drone Unit
│       │   ├── config_manager.py ← Konfigurasi dinamis
│       │   └── controller.py     ← Pipeline: record→process→detect→TDOA→send
│       ├── audio/                ← Audio capture & digital signal processing
│       │   ├── recorder.py       ← arecord subprocess + device probing
│       │   ├── processor.py      ← Channel extraction
│       │   ├── detector.py       ← RMS-based event detection
│       │   └── logger.py         ← JSON/CSV persistence
│       ├── io/                   ← Serial I/O
│       │   ├── serial_handler.py ← Read/write serial command
│       │   └── comms.py          ← File transfer via serial
│       └── tdoa/                 ← Pemrosesan matematika TDOA
│           ├── tdoa.py           ← GCC-PHAT + cross-correlation
│           ├── filter_registry.py← Registry filter noise reduction
│           ├── base_filter.py    ← Kelas dasar plugin filter audio
│           ├── builtin_filters/  ← Filter bawaan (Spectral Gating, Wiener, dll)
│           └── custom_filters/   ← Filter kustom eksternal
└── tests/
```
    ├── README.md
    ├── darat/
    │   ├── fixtures/sample_tdoa.json
    │   ├── fixtures/sample_results.txt
    │   ├── test_process_json_tdoa.py
    │   └── test_file_transfer.py
    └── udara/
        └── test_tdoa.py
```

---

## 3. Aturan WAJIB Sebelum Memodifikasi Kode

### 3.1 Konfigurasi — Selalu via Config File

**Darat:** Semua konstanta ada di `darat/core/config.py`
- Posisi mikrofon → `MIC_POSITIONS`
- Command strings → `CMD_STANDBY`, `CMD_START_RECORD`, dst.
- Serial parameters → `BAUD_RATE`, `SERIAL_TIMEOUT`

**Udara:** Semua konstanta ada di `udara/drone_system/core/config.py`
- Device profiles → `DEVICE_PROFILES`, `ACTIVE_PROFILE`
- Audio parameters → `SAMPLE_RATE`, `HOP_LENGTH`, dst.
- Detection thresholds → `DETECT_RATIO`, `FILTER_RATIO`, `MIN_DURATION`

> [!WARNING]
> **JANGAN hardcode konstanta di dalam method/function.** Selalu referensikan dari core/config.py.

### 3.2 Protokol Komunikasi Serial

**Ground → Drone:** Text command (e.g., `"START_REC\n"`)
**Drone → Ground (file JSON):** Binary dengan marker:
```
[START]\n
<json content bytes>
\n[END]\n
```

> [!IMPORTANT]
> Jangan ubah format marker tanpa mengupdate **kedua sisi** sekaligus:
> - Pengirim: `udara/drone_system/io/comms.py` (START_MARKER, END_MARKER)
> - Penerima: `darat/io/json_receiver.py` (deteksi marker `[START]` dan `[END]`)

### 3.3 Working Directory — Jangan `os.chdir()`

Aplikasi PyQt6 menggunakan widget dengan _internal state_ untuk *working directory* masing-masing, bukan variabel global:

```python
# ✅ BENAR (refactored pattern)
json_files = glob.glob(os.path.join(self._working_dir, "*.json"))

# ❌ SALAH (jangan lakukan ini)
os.chdir(directory)
json_files = glob.glob("*.json")
```

### 3.4 Relative Imports di Paket Darat

`darat/` adalah Python package. Gunakan relative imports:
```python
# ✅ BENAR
from .config import MIC_POSITIONS
from .file_transfer import FileTransferManager

# ❌ SALAH
from config import MIC_POSITIONS
import file_transfer
```

---

## 4. Menambah Screen Baru (GUI PyQt6)

1. Buat file `darat/ui/pages/nama_page.py`
2. Buat class yang inherit dari `QWidget`:
```python
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

class NamaPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Ini Halaman Baru"))
```
3. Export di `darat/ui/pages/__init__.py`
4. Daftarkan di `MainDashboard` (`darat/ui/dashboard.py`):
    - Instansiasi objek *page* tersebut (misal: `self._page_nama = NamaPage()`)
    - Tambahkan ke `QStackedWidget` (`self._stack.addWidget(self._page_nama)`)
    - Tambahkan tombol navigasinya di `_build_sidebar()`
5. Pastikan menggunakan *signal* dan *slot* untuk interaksi dengan proses backend. Gunakan `SerialBridge` atau `RestClient` dari `services/` untuk komunikasi eksternal.

---

## 5. Menambah Command Serial Baru

1. Tambahkan konstanta di `darat/core/config.py`:
```python
CMD_NEW_COMMAND = "NEW_CMD"
```
2. Tambahkan handler di `darat/ui/pages/command_page.py`:
```python
def _new_command(self):
    self._serial.send_command(CMD_NEW_COMMAND)
    self._set_status(f"Status: ... ({CMD_NEW_COMMAND} sent)")
    self.log_message.emit("...", "INFO")
```
3. Tambahkan tombol di array `buttons` dalam `CommandPage._build_ui()`
4. Tambahkan handler di **drone side** `udara/drone_system/main.py` fungsi `process_command()`:
```python
elif command == "NEW_CMD":
    # handle command
    response = "OK:done"
```

---

## 6. Menambah Mikrofon / Mengubah Posisi Mikrofon

Edit `darat/core/config.py`:
```python
MIC_POSITIONS = {
    "mic0": np.array([x, y, z]),
    # ... tambah mic baru
}
```

Edit juga `udara/drone_system/core/config.py`:
- `NUM_MICS_H8` — jumlah mic yang digunakan
- `DEVICE_PROFILES["H8"]["take_indices_6mic"]` — channel indices

---

## 7. Menambah Format File yang Didukung

Edit `darat/core/config.py`:
```python
SUPPORTED_EXTENSIONS = [".mp4", ".wav", ".txt", ".json", ".new_ext"]
```

Edit `darat/core/file_transfer.py` — fungsi `get_file_type()`:
```python
mapping = {
    ".mp4": "Video",
    ".wav": "Audio",
    ".txt": "Text",
    ".json": "JSON",
    ".new_ext": "NewType",  # tambahkan di sini
}
```

---

## 8. Testing

### Menjalankan Tests
```bash
# Dari root Prototype/
python tests/darat/test_process_json_tdoa.py   # 16 tests
python tests/darat/test_file_transfer.py        # 18 tests
python tests/udara/test_tdoa.py                 # ~10 tests (butuh numpy, scipy)
```

### Menambah Test Baru
- Buat di `tests/darat/` atau `tests/udara/`
- Gunakan pattern `sys.path.insert(0, "...")` + import sebagai package `darat.xxx` atau `drone_system.xxx`
- Lihat `tests/README.md` untuk detail lengkap

### Modul yang Tidak Dapat Di-test Otomatis
- `ui/*.py` — perlu lingkungan desktop PyQt6 aktif
- `serial_manager.py` / `serial_handler.py` — perlu hardware serial
- `recorder.py` — perlu arecord (Linux only)
- `json_receiver.py` — perlu mock threading + serial

---

## 9. Proses Bisnis yang TIDAK Boleh Diubah

Berikut adalah invariant sistem yang harus dipertahankan:

| Invariant | Lokasi |
|-----------|--------|
| Bucher-Misra membutuhkan tepat 4 stasiun | `darat/localization/process_json_tdoa.py:bucher_misra_3d()` |
| TDOA dihitung untuk semua pasangan C(n,2) | `udara/drone_system/tdoa/tdoa.py:calculate_all_tdoa()` |
| Cluster dipilih berdasarkan ukuran terbesar | `darat/localization/process_json_tdoa.py:process_event_tdoa()` |
| JSON diterima hanya setelah `STOP_REC` command | `command_page.py:_stop_record()` |
| File transfer menggunakan START/END marker | `darat/core/file_transfer.py`, `udara/drone_system/io/comms.py` |
| TDOA default menggunakan ECCCT (Envelope Cross-Correlation) | `udara/drone_system/core/config_manager.py:tdoa_method = "eccct"` |
| Rotating Multilateration membutuhkan minimal 5 stasiun | `darat/localization/builtin_ssl/rotating_multilat.py:solve()` |

---

## 10. Known Limitations & Technical Debt

1. **`darat/io/json_receiver.py`** — Loop blocking dengan polling 100ms. Jika perlu improvement,
   pertimbangkan asyncio atau event-driven approach.

2. **`comms.py` + `serial_handler.py`** — Dua class di `udara/drone_system/io/` yang membuka koneksi serial terpisah
   ke port yang sama. Perlu dikonsolidasi jika ada masalah konflik port.

3. **Clustering EPS hardcoded** — `eps=1.0` meter di `process_event_tdoa()`. Saat ini `CLUSTER_EPS` ada di `config_laptop.py` namun belum sepenuhnya tersambung ke parameter `process_event_tdoa()`. Perlu integrasi argumen lebih lanjut.

4. **Tidak ada logging terstruktur** — `print()` digunakan di seluruh kode udara.
   Pertimbangkan `logging` module jika perlu log level control.
