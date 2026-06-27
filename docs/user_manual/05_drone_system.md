# Bab 5: Sistem Drone (Subsistem Udara)

---

## 5.1 Gambaran Umum

Subsistem Udara (Drone System) berjalan di Raspberry Pi 5 yang terpasang pada drone. Sistem ini sepenuhnya beroperasi dari terminal dan tidak memiliki antarmuka grafis. Semua interaksi dari operator dilakukan melalui Ground Station via koneksi serial (mode ONLINE), atau langsung dari keyboard Raspberry Pi (mode OFFLINE).

Entry point utama:
```bash
python run_drone_system.py
```

---

## 5.2 Mode Operasi

### Mode ONLINE
Sistem menunggu perintah dari Ground Station via serial port. Ini adalah mode operasional utama saat drone sedang terbang.

**Kapan digunakan:** Saat operasi lapangan nyata dengan drone terbang dan operator di darat.

**Konfigurasi yang diperlukan:**
- `operation_mode = "ONLINE"` (di konfigurasi drone)
- `serial_port` sudah benar (contoh: `/dev/ttyUSB0`)
- `baud_rate` cocok dengan Ground Station (default: `230400`)

### Mode OFFLINE
Sistem menerima perintah dari keyboard secara langsung. Berguna untuk testing sistem audio dan pipeline pemrosesan tanpa Ground Station.

**Kapan digunakan:** Testing di darat, debugging, kalibrasi threshold deteksi.

**Kontrol keyboard:**
| Tombol | Perintah | Fungsi |
|---|---|---|
| `s` | START_REC | Mulai perekaman |
| `p` | STOP_REC | Hentikan perekaman dan proses |
| `t` | STATUS | Cek status perekaman |
| `i` | INFO | Tampilkan info sistem lengkap |
| `q` | QUIT | Keluar dari program |

---

## 5.3 Perintah yang Dapat Diterima (Mode ONLINE)

Perintah dikirim dari Ground Station sebagai teks via serial:

| Perintah | Respon Drone | Deskripsi |
|---|---|---|
| `START_REC` | `OK:Recording started...` | Mulai merekam audio dari Zoom Recorder |
| `STOP_REC` | `OK:Processing...` | Hentikan perekaman, proses audio, kirim hasil JSON |
| `STATUS` | `OK:Recorder=True/False,...` | Laporan status perekaman saat ini |
| `INFO` | `OK:Recorder=...,Features=...` | Info sistem: profil, format audio, fitur aktif |
| `SET_CONFIG` | `OK:SET_CONFIG:N params updated` | Terapkan konfigurasi baru dari Ground Station |

> ℹ️ **Catatan:** Perintah `SET_CONFIG` dikirim otomatis oleh Ground Station saat operator menekan tombol **SAVE CONFIG** di tab Config. Operator tidak perlu mengetik perintah ini secara manual.

---

## 5.4 Pipeline Pemrosesan Audio (Continuous Chunk Processing)

Drone System menggunakan arsitektur **multi-threaded (producer-consumer)** untuk melakukan perekaman dan pemrosesan audio secara kontinu tanpa menjeda perekaman:

```
[arecord Subprocess] (Merekam PCM bytes kontinu)
         │
         ▼ (stdout pipe)
[_stream_processor_thread] (Producer: Membaca raw bytes & membangun window)
         │
         ▼ (antrean Chunk Queue, maks 10 chunk)
[_chunk_worker_loop] (Consumer: Memproses chunk WAV & TDOA secara serial)
         │
         ▼ (jika ONLINE mode)
[Serial Transmission] (Mengirim file tdoa.json dengan [START]/[END])
```

Berikut adalah tahap detail pemrosesan untuk setiap chunk:

### Tahap 1: Pengambilan Stream (Stream Processing Thread)
- Utilitas `arecord` berjalan sebagai background subprocess, mengalirkan raw PCM bytes melalui stdout pipe.
- `_stream_processor_thread` membaca byte stream secara terus-menerus dan menyusunnya ke dalam buffer memori (*ring buffer*).
- Setiap kali ukuran buffer mencapai durasi satu window (default: `chunk_duration_sec` + `chunk_overlap_sec`, contoh: 5s + 1s = 6s audio), thread mengambil window tersebut dan memasukannya ke dalam antrean `chunk_queue`.
- Thread mempertahankan `overlap_bytes` terakhir di memori sebagai awal untuk window berikutnya untuk mendeteksi event yang berada di perbatasan chunk.

### Tahap 2: Konversi dan Ekstraksi (Worker Thread)
- `_chunk_worker_loop` mengambil chunk dari queue secara berurutan (*first-in-first-out*).
- Konversi raw bytes menjadi numpy array `float32` dan menyimpannya sebagai file WAV lokal sementara di dalam subfolder `chunks/chunk_YYYYMMDD_HHMMSS_ffffff/raw.wav`.
- Mengekstrak channel mikrofon yang aktif berdasarkan profil perangkat (`active_profile` & `num_mics_h8`).

### Tahap 3: Denoising & Deteksi Event
- Menerapkan filter noise reduction yang dipilih (contoh: *Spectral Gating*) ke data audio tiap channel.
- Menghitung nilai RMS dari gabungan channel untuk mendeteksi lonjakan energi (*event*).
- Mengabaikan event jika berada di zona awal (`ignore_time`), menyatukan event yang berdekatan (`max_gap`), dan menghapus event yang terlalu pendek (`min_duration`).
- Memotong dan menyimpan klip audio event bersih ke subfolder event.

### Tahap 4: Perhitungan & Transmisi TDOA
- Menghitung selisih waktu kedatangan (TDOA) antar semua pasangan mikrofon menggunakan algoritma **GCC-PHAT** untuk setiap event yang lolos filter.
- Menyimpan hasil perhitungan TDOA ke dalam format file JSON (`tdoa.json`) di subfolder chunk tersebut.
- Jika mode operasi adalah **ONLINE**, file JSON ini langsung dikirimkan ke Ground Station via serial dengan protokol marker `[START]\n<data>\n[END]\n`.

### Tahap 5: Penghentian Perekaman (STOP_REC)
- Saat perintah `STOP_REC` diterima, drone menghentikan subprocess `arecord`.
- Sisa data buffer terakhir diproses sebagai chunk final (durasi minimal 0.5 detik).
- Setelah semua antrean chunk selesai diproses oleh worker thread, sistem kembali ke status `IDLE`.

---

## 5.5 Output yang Dihasilkan

Setiap sesi perekaman menghasilkan folder di direktori `drone_recordings/` (dapat dikonfigurasi):

```
drone_recordings/
└── session_YYYYMMDD_HHMMSS/
    ├── raw_12ch.wav          ← Rekaman mentah semua channel
    ├── detected_events.csv   ← Daftar event (timestamp, durasi)
    ├── session_events.json   ← Data event dalam format JSON
    ├── session_tdoa.json     ← Hasil TDOA per event (dikirim ke ground)
    ├── event_1/              ← Audio per-event (setelah noise reduction)
    │   ├── mic0_clean.wav
    │   ├── mic1_clean.wav
    │   └── ...
    └── event_2/
        └── ...
```

Penjelasan detail format file lihat **Bab 9: Format File Output**.

---

## 5.6 REST API Konfigurasi Drone

Drone System menjalankan server REST API kecil (menggunakan Flask) yang memungkinkan Ground Station membaca dan mengubah konfigurasi secara nirkabel (via Wi-Fi atau jaringan lokal). API ini berjalan di background secara otomatis saat Drone System dijalankan.

**Default endpoint:**
- Host: `0.0.0.0` (semua interface)
- Port: `5000`
- Contoh: `http://10.99.99.2:5000/`

**Endpoint yang tersedia:**

| Method | Endpoint | Fungsi |
|---|---|---|
| `GET` | `/config` | Baca konfigurasi drone saat ini |
| `PATCH` | `/config` | Update parameter konfigurasi (runtime) |
| `POST` | `/restart` | Restart Drone System |
| `GET` | `/filter-schemas` | Baca skema parameter filter yang tersedia |

> ℹ️ **Operator tidak perlu mengakses REST API secara langsung.** Ground Station menggunakannya secara otomatis dari tab Config.

**Persyaratan koneksi REST API:**
- Laptop dan Raspberry Pi harus berada di jaringan yang sama
- IP Raspberry Pi harus dikonfigurasi di Ground Station (tab Config → Ground Station → **Drone IP Address**)
- Default IP Raspberry Pi: `10.99.99.2`

---

## 5.7 Mengubah Konfigurasi Drone

Ada dua cara mengubah konfigurasi drone:

### Cara 1: Via Ground Station GUI (Direkomendasikan)
1. Buka tab **Config** → sub-tab **Raspberry Pi**
2. Ubah parameter yang diinginkan
3. Klik **SAVE CONFIG**
4. Ground Station mengirim perubahan ke drone via REST API
5. Parameter bertanda ⚠ memerlukan **RESTART** drone agar berlaku

### Cara 2: Edit File Konfigurasi Langsung
File konfigurasi tersimpan di Raspberry Pi:
```
udara/config/drone_config_override.json
```

Edit file ini secara langsung (via SSH atau terminal RPi), lalu restart Drone System:
```bash
sudo systemctl restart mdi_drone.service
# atau Ctrl+C lalu jalankan ulang
```

---

## 5.8 Memantau Log Drone System

### Jika berjalan di terminal:
Log muncul langsung di terminal:
```
[SYSTEM] Drone Audio Detection System started
[RECORDER] arecord started, PID=1234
[DETECTOR] Event detected at t=2.34s, duration=0.41s
[TDOA] mic0-mic1: 0.00012s
...
```

### Jika berjalan sebagai systemd service:
```bash
# Real-time log:
journalctl -u mdi_drone.service -f

# Log terakhir 100 baris:
journalctl -u mdi_drone.service -n 100
```

### Dari Ground Station:
Log yang dikirim drone (response dari perintah STATUS/INFO) muncul di **Panel Status Response** pada tab Command.
