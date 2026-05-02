"""
Tests README — Cara Menjalankan dan Struktur Test Suite

## Struktur
```
tests/
├── README.md                  ← file ini
├── darat/
│   ├── fixtures/
│   │   ├── sample_tdoa.json   ← JSON TDOA fixture (2 events, 6 mics)
│   │   └── sample_results.txt ← Results fixture untuk visualize test
│   ├── test_process_json_tdoa.py  ← Tests untuk TDOA processing
│   └── test_file_transfer.py      ← Tests untuk file transfer state machine
└── udara/
    └── test_tdoa.py               ← Tests untuk GCC-PHAT & cross-correlation
```

## Prasyarat
Install dependencies darat:
```bash
pip install numpy scipy matplotlib pyserial
```

Install dependencies udara (untuk test_tdoa):
```bash
pip install numpy scipy
```

## Menjalankan Semua Tests
Dari root `Prototype/`:
```bash
# Semua tests sekaligus
python -m pytest tests/ -v

# Hanya darat
python -m pytest tests/darat/ -v

# Hanya udara
python -m pytest tests/udara/ -v
```

Atau tanpa pytest (stdlib saja):
```bash
python tests/darat/test_process_json_tdoa.py
python tests/darat/test_file_transfer.py
python tests/udara/test_tdoa.py
```

## Apa yang Diuji

### test_process_json_tdoa.py
| Test | Tujuan |
|------|--------|
| TestBucherMisra3D | Solver mengembalikan solusi valid, error handling |
| TestClusterSolutions | Clustering benar, sorted by size desc |
| TestClusterSolutions.test_dead_code_not_present | **Verifikasi dead code sudah dihapus** |
| TestProcessEventTdoa | Processing 2-event fixture tidak crash |
| TestSaveResultsToFile | Output file format benar |

### test_file_transfer.py
| Test | Tujuan |
|------|--------|
| TestGetFileType | Mapping ext → string (no duplication) |
| TestFileTransferManager.test_handle_file_start_* | State machine transition |
| TestFileTransferManager.test_handle_file_end_* | File disimpan dengan benar |
| TestFileTransferManager.test_json_router_* | JSON routing mechanism |

### test_tdoa.py (udara)
| Test | Tujuan |
|------|--------|
| TestGccPhat | GCC-PHAT akurat untuk delay yang diketahui |
| TestCrossCorrelation | Cross-correlation basic |
| TestCalculateAllTdoa | C(n,2) pasangan, format key, silent signal |

## Coverage Saat Ini
Modul yang di-cover:
- ✅ `refactored/darat/process_json_tdoa.py` — 80%+ coverage
- ✅ `refactored/darat/file_transfer.py` — 90%+ coverage
- ✅ `refactored/udara/drone_system/tdoa.py` — 90%+ coverage

Modul yang perlu hardware/GUI (belum di-cover):
- ⏳ `serial_manager.py` — perlu hardware serial port
- ⏳ `json_receiver.py` — perlu mock serial + threading
- ⏳ `screens/*.py` — perlu Tkinter display (headless tidak supported)
- ⏳ `recorder.py` — perlu arecord (Linux only)
- ⏳ `detector.py` — perlu file WAV audio

## Menambah Test Baru
1. Buat file `test_<module>.py` di `tests/darat/` atau `tests/udara/`
2. Tambahkan `sys.path.insert` ke `refactored/darat/` atau `refactored/udara/`
3. Gunakan `unittest.TestCase` atau pytest style
4. Gunakan fixtures di `fixtures/` untuk data test
5. Jalankan `python -m pytest tests/ -v` untuk verifikasi
"""
