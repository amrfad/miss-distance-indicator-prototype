# AGENTS.md — AI Agent Reference Guide
## Miss Distance Indicator Prototype

> Dokumen ini adalah acuan utama untuk AI agent (Copilot, Antigravity, dsb.) yang akan
> memodifikasi, memperluas, atau debug codebase ini. Baca sebelum membuat perubahan apapun.

---

## 1. Gambaran Sistem

Sistem ini terdiri dari **dua subsistem** yang berjalan di perangkat terpisah:

| Subsistem | Direktori | Platform | Fungsi |
|-----------|-----------|----------|--------|
| **Darat (Ground Unit)** | `darat/` | Windows/Linux | GUI Tkinter untuk menerima, memproses, dan memvisualisasikan data TDOA |
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
│   ├── main.py                   ← Entry point: python darat/main.py
│   ├── app.py                    ← EventGUI koordinator (thin)
│   ├── config.py                 ← SEMUA KONSTANTA di sini
│   ├── file_transfer.py          ← State machine file transfer
│   ├── json_receiver.py          ← Penerimaan JSON via serial
│   ├── serial_manager.py         ← Serial port management
│   ├── process_json_tdoa.py      ← Bucher-Misra solver + TDOA processing
│   ├── visualize_results.py      ← Matplotlib visualization
│   └── screens/
│       ├── __init__.py
│       ├── home_screen.py
│       ├── command_screen.py
│       ├── process_screen.py
│       └── visualize_screen.py
├── udara/
│   ├── run_drone_system.py       ← Entry point drone
│   └── drone_system/
│       ├── config.py             ← SEMUA KONSTANTA drone di sini
│       ├── main.py               ← Orchestrator online/offline mode
│       ├── controller.py         ← Pipeline: record→process→detect→TDOA→send
│       ├── recorder.py           ← arecord subprocess + device probing
│       ├── processor.py          ← Channel extraction + noise reduction
│       ├── detector.py           ← RMS-based event detection
│       ├── logger.py             ← JSON/CSV persistence
│       ├── serial_handler.py     ← Command read/write serial
│       ├── comms.py              ← File transfer via serial
│       └── tdoa.py               ← GCC-PHAT + cross-correlation
└── tests/
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

**Darat:** Semua konstanta ada di `darat/config.py`
- Posisi mikrofon → `MIC_POSITIONS`
- Command strings → `CMD_STANDBY`, `CMD_START_RECORD`, dst.
- Serial parameters → `BAUD_RATE`, `SERIAL_TIMEOUT`

**Udara:** Semua konstanta ada di `udara/drone_system/config.py`
- Device profiles → `DEVICE_PROFILES`, `ACTIVE_PROFILE`
- Audio parameters → `SAMPLE_RATE`, `HOP_LENGTH`, dst.
- Detection thresholds → `DETECT_RATIO`, `FILTER_RATIO`, `MIN_DURATION`

> [!WARNING]
> **JANGAN hardcode konstanta di dalam method/function.** Selalu referensikan dari config.py.

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
> - Pengirim: `udara/drone_system/comms.py` (START_MARKER, END_MARKER)
> - Penerima: `darat/json_receiver.py` (deteksi marker `[START]` dan `[END]`)

### 3.3 Working Directory — Jangan `os.chdir()`

Versi original menggunakan `os.chdir()` yang mengubah working directory global.
Versi refactored menggunakan `app.working_directory` sebagai instance variable.

```python
# ✅ BENAR (refactored pattern)
json_files = glob.glob(os.path.join(app.working_directory, "*.json"))

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

## 4. Menambah Screen Baru (GUI)

1. Buat file `darat/screens/nama_screen.py`
2. Buat class dengan pattern:
```python
class NamaScreen:
    def __init__(self, app):
        self.app = app  # EventGUI instance

    def build(self):
        frame = self.app.main_frame
        # ... bangun widget ...
        # Set log_text jika screen punya log widget:
        self.app.log_text = Text(...)
```
3. Export di `screens/__init__.py`
4. Tambahkan method `show_nama()` di `EventGUI` (`app.py`):
```python
def show_nama(self):
    self.clear_screen()
    self.current_screen = "nama"
    NamaScreen(self).build()
```
5. Tambahkan tombol navigasi di screen yang sesuai

---

## 5. Menambah Command Serial Baru

1. Tambahkan konstanta di `darat/config.py`:
```python
CMD_NEW_COMMAND = "NEW_CMD"
```
2. Tambahkan handler di `darat/screens/command_screen.py`:
```python
def _new_command(self):
    self.app.serial_manager.send_command(CMD_NEW_COMMAND)
    self._update_status(f"Status: ... ({CMD_NEW_COMMAND} sent)")
    self.app.log_message("...")
```
3. Tambahkan tombol di `CommandScreen.build()`
4. Tambahkan handler di **drone side** `udara/drone_system/main.py` fungsi `process_command()`:
```python
elif command == "NEW_CMD":
    # handle command
    response = "OK:done"
```

---

## 6. Menambah Mikrofon / Mengubah Posisi Mikrofon

Edit `darat/config.py`:
```python
MIC_POSITIONS = {
    "mic0": np.array([x, y, z]),
    # ... tambah mic baru
}
```

Edit juga `udara/drone_system/config.py`:
- `NUM_MICS_H8` — jumlah mic yang digunakan
- `DEVICE_PROFILES["H8"]["take_indices_6mic"]` — channel indices

---

## 7. Menambah Format File yang Didukung

Edit `darat/config.py`:
```python
SUPPORTED_EXTENSIONS = [".mp4", ".wav", ".txt", ".json", ".new_ext"]
```

Edit `darat/file_transfer.py` — fungsi `get_file_type()`:
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
- `screens/*.py` — perlu Tkinter display
- `serial_manager.py` / `serial_handler.py` — perlu hardware serial
- `recorder.py` — perlu arecord (Linux only)
- `json_receiver.py` — perlu mock threading + serial

---

## 9. Proses Bisnis yang TIDAK Boleh Diubah

Berikut adalah invariant sistem yang harus dipertahankan:

| Invariant | Lokasi |
|-----------|--------|
| Bucher-Misra membutuhkan tepat 4 stasiun | `process_json_tdoa.py:bucher_misra_3d()` |
| TDOA dihitung untuk semua pasangan C(n,2) | `tdoa.py:calculate_all_tdoa()` |
| Cluster dipilih berdasarkan ukuran terbesar | `process_json_tdoa.py:process_event_tdoa()` |
| JSON diterima hanya setelah `STOP_REC` command | `command_screen.py:_stop_record()` |
| File transfer menggunakan START/END marker | `file_transfer.py`, `comms.py` |
| Noise reduction menggunakan GCC-PHAT default | `config.py:IS_GCC_PHAT = True` |

---

## 10. Known Limitations & Technical Debt

1. **`json_receiver.py`** — Loop blocking dengan polling 100ms. Jika perlu improvement,
   pertimbangkan asyncio atau event-driven approach.

2. **`comms.py` + `serial_handler.py`** — Dua class yang membuka koneksi serial terpisah
   ke port yang sama. Perlu dikonsolidasi jika ada masalah konflik port.

3. **`screens/`** — Tidak ada state persistence antar screen (misal: pilihan file di
   process_screen hilang saat balik ke home). Pertimbangkan simple state dict di `app.py`.

4. **Clustering EPS hardcoded** — `eps=1.0` meter di `process_event_tdoa()`. Pertimbangkan
   memindahkan ke `config.py` sebagai `CLUSTER_EPS`.

5. **Tidak ada logging terstruktur** — `print()` digunakan di seluruh kode udara.
   Pertimbangkan `logging` module jika perlu log level control.
