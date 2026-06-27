# Bab 1: Pendahuluan

---

## 1.1 Gambaran Umum Sistem

**Miss Distance Indicator (MDI)** adalah sistem berbasis akustik yang dirancang untuk mendeteksi dan mengestimasi posisi sumber suara impulsif — seperti suara tembakan atau ledakan — yang terjadi di sekitar drone yang sedang beroperasi. Sistem ini bertujuan memberikan indikasi *miss distance*, yaitu seberapa jauh proyektil melewati posisi drone.

Sistem MDI bekerja dengan cara:
1. Merekam suara secara multi-channel menggunakan beberapa mikrofon yang dipasang di drone
2. Mendeteksi kejadian (*event*) suara yang tiba-tiba dan signifikan
3. Menghitung **TDOA (Time Difference of Arrival)** — selisih waktu kedatangan suara di tiap mikrofon
4. Menggunakan data TDOA tersebut untuk mengestimasi posisi sumber suara dalam ruang 3D menggunakan algoritma **Bucher-Misra**
5. Menampilkan hasil estimasi posisi kepada operator di darat secara visual

---

## 1.2 Arsitektur Sistem

Sistem MDI terdiri dari **dua subsistem** yang berjalan pada perangkat terpisah dan berkomunikasi via koneksi serial (UART):

```
┌─────────────────────────────────────┐     Serial (UART)     ┌──────────────────────────────────────┐
│         SUBSISTEM UDARA             │ ◄──────────────────── │         SUBSISTEM DARAT              │
│         (Drone Unit)                │                        │         (Ground Station)             │
│                                     │ ──────────────────────►│                                      │
│  • Raspberry Pi 5                   │    Data JSON TDOA      │  • Laptop / PC Operator              │
│  • Zoom H8 / H6E (Audio Interface)  │                        │  • Aplikasi GUI MDI Ground Station   │
│  • 4–6 Mikrofon                     │                        │                                      │
│  • Sistem Operasi: Linux            │                        │  • Sistem Operasi: Windows / Linux   │
└─────────────────────────────────────┘                        └──────────────────────────────────────┘
```

### Subsistem Udara (Drone Unit)
Berjalan di Raspberry Pi 5 yang terpasang pada drone. Bertanggung jawab untuk:
- Merekam audio multi-channel dari Zoom Recorder
- Melakukan noise reduction pada sinyal audio
- Mendeteksi event suara berdasarkan lonjakan RMS
- Menghitung TDOA antar semua pasang mikrofon menggunakan GCC-PHAT
- Mengirimkan file hasil (`session_tdoa.json`) ke Ground Station via serial

### Subsistem Darat (Ground Station)
Berjalan di laptop/PC operator. Bertanggung jawab untuk:
- Mengirimkan perintah ke drone (START, STOP, STATUS)
- Menerima file JSON hasil deteksi dari drone
- Memproses data TDOA menjadi estimasi posisi 3D (algoritma Bucher-Misra)
- Menampilkan hasil secara visual: 3D Tactical View dan 2D Radar View
- Mengelola konfigurasi sistem (drone dan ground station)

---

## 1.3 Alur Data Keseluruhan (Continuous Streaming Mode)

Sistem MDI menggunakan arsitektur **perekaman dan pemrosesan kontinu (continuous streaming)**. Data audio diproses dalam potongan waktu (*chunk*) secara berkala selama sesi perekaman aktif:

```
[Drone] Perekaman Audio Berkelanjutan (Zoom H8/H6E via arecord)
        ↓
[Drone] Pemotongan Audio per Chunk (durasi 5s, overlap 1s)
        ↓
[Drone] Ekstraksi Channel + Noise Reduction (per chunk)
        ↓
[Drone] Deteksi Event via RMS (per chunk)
        ↓
[Drone] Perhitungan TDOA via GCC-PHAT (per chunk)
        ↓
[Drone] Transmisi JSON Real-time via Serial → [START]/[END] marker
        ↓
[Ground] Penerimaan JSON Real-time & Deduplikasi Event Overlap
        ↓
[Ground] Penyimpanan File JSON per Chunk (tdoa_*.json)
        ↓
[Ground] Estimasi Posisi via SSL (Bucher-Misra) + Visualisasi 3D/2D
```

---

## 1.4 Tujuan Dokumen

User Manual ini menyediakan informasi yang diperlukan bagi **operator lapangan teknis** untuk:
- Menyiapkan hardware dan software sistem MDI
- Menjalankan operasi perekaman dan pengolahan data secara benar
- Menginterpretasikan hasil visualisasi
- Mengkonfigurasi parameter sistem sesuai kebutuhan operasional
- Mengatasi masalah umum yang mungkin terjadi di lapangan

---

## 1.5 Target Pembaca

Dokumen ini ditujukan untuk **operator lapangan teknis** yang:
- Memiliki pemahaman dasar tentang sistem elektronik dan komunikasi serial
- Familiar dengan pengoperasian drone dan perangkat perekam audio
- Mampu menjalankan perintah dasar pada antarmuka baris perintah (terminal/command prompt)
- Tidak harus memiliki latar belakang pemrograman Python

---

## 1.6 Prasyarat Sistem

Sebelum menggunakan sistem MDI, pastikan tersedia:

**Hardware:**
- Raspberry Pi 5 (terpasang di drone)
- Zoom H8 atau Zoom H6 Essential (H6E)
- 4 hingga 6 mikrofon kondenser yang kompatibel
- Koneksi serial: USB-to-TTL converter atau modul telemetri radio
- Laptop/PC untuk Ground Station

**Software:**
- Ground Station: Python 3.11+ (atau file `.exe` distribusi)
- Drone System: Python 3.11+ pada Raspberry Pi OS (64-bit)

**Pengetahuan Minimal:**
- Cara membuka terminal / command prompt
- Cara menghubungkan perangkat ke port USB
- Cara membaca nilai koordinat XYZ sederhana
