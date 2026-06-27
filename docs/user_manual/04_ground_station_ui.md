# Bab 4: Panduan Antarmuka Pengguna — Ground Station

---

## 4.1 Tampilan Umum Aplikasi

Ground Station MDI adalah aplikasi desktop berbasis GUI (Graphical User Interface) yang dibangun dengan PySide6. Saat pertama kali dibuka, tampilan terdiri dari beberapa area:

```
┌─────────────────────────────────────────────────────────────────────┐
│  HEADER: "Miss Distance Indicator — Ground Control Station"         │
│  Status Koneksi  |  Status Perekaman  |  Jam Digital               │
├──────────┬──────────────────────────────────────────────────────────┤
│          │                                                          │
│ SIDEBAR  │              AREA KONTEN UTAMA                           │
│          │         (Menampilkan halaman aktif)                      │
│ [Config] │                                                          │
│ [Command]│                                                          │
│ [Process]│                                                          │
│[Visualize│                                                          │
│          │                                                          │
├──────────┴──────────────────────────────────────────────────────────┤
│  PANEL LOG (bawah): Pesan sistem, status, error                     │
└─────────────────────────────────────────────────────────────────────┘
```

> 📸 **[PLACEHOLDER SCREENSHOT]** — *Screenshot tampilan utama aplikasi Ground Station dengan keempat elemen utama diberi label: Header, Sidebar, Area Konten, Panel Log.*

### Komponen Utama

| Komponen | Fungsi |
|---|---|
| **Header** | Menampilkan judul aplikasi, indikator status koneksi serial, status perekaman, dan jam real-time |
| **Sidebar** | Navigasi antar halaman. Klik tombol untuk berpindah tab. Sidebar dapat dipersempit dengan tombol hamburger (☰) |
| **Area Konten** | Menampilkan halaman yang sedang aktif (Config / Command / Process / Visualize) |
| **Panel Log** | Menampilkan semua pesan log sistem secara real-time. Log diberi warna sesuai level (INFO = putih, WARNING = kuning, ERROR = merah, DEBUG = abu-abu) |

---

## 4.2 Tab CONFIG — Konfigurasi Sistem

Tab Config memiliki dua sub-tab: **Raspberry Pi** dan **Ground Station**.

> 📸 **[PLACEHOLDER SCREENSHOT]** — *Screenshot tab Config menampilkan kedua sub-tab: "🔒 RASPBERRY PI" dan "🖥 GROUND STATION".*

### 4.2.1 Sub-tab Raspberry Pi

Sub-tab ini mengatur konfigurasi Drone System yang berjalan di Raspberry Pi. Parameter dibagi ke dalam grup:

**OPERATION MODE (🔒 = Memerlukan Restart)**
- **Operation Mode**: `ONLINE` (serial) atau `OFFLINE` (keyboard)
- **Device Profile**: `H8` atau `H6E` sesuai Zoom Recorder yang digunakan
- **Output Directory**: Direktori penyimpanan file rekaman di RPi

**AUDIO CONFIGURATION (🔒)**
- **Sample Rate**: Frekuensi sampling audio (48000 Hz direkomendasikan)
- **Mic Count**: Jumlah mikrofon aktif (4 atau 6, hanya untuk H8)
- **Audio Device**: Identifier perangkat `arecord` (contoh: `hw:2,0`)
- **Terminate Timeout**: Waktu tunggu penghentian `arecord`

**EVENT DETECTION (🔄 = Live, berlaku tanpa restart)**
- **Detect Ratio**: Sensitivitas deteksi event (lebih rendah = lebih sensitif)
- **Filter Ratio**: Filter kualitas sinyal event
- **Min Duration**: Durasi minimum event yang valid
- **Max Gap**: Gap maksimum antara event agar digabungkan
- **Ignore Time**: Detik awal perekaman yang diabaikan

**NOISE REDUCTION (🔄)**
- **Prop. Decrease**: Intensitas pengurangan noise (0.0–1.0)
- **Normalization Percentile**: Persentil untuk normalisasi amplitudo
- **Stationary**: Mode noise stasioner (centang jika noise bersifat konstan)
- **Normalize**: Normalisasi output audio

**FILTER METHOD (🔄)**
- Pilih metode noise reduction dari dropdown (Spectral Gating, Wiener Filter, atau metode kustom)
- Parameter spesifik metode yang dipilih akan muncul secara dinamis

**TDOA / GCC-PHAT**
- **GCC-PHAT**: Aktifkan/nonaktifkan algoritma GCC-PHAT (sangat direkomendasikan: aktif)
- **Hop Length** dan **Frame Length**: Parameter analisis frame

**SERIAL & OUTPUT FILES (🔒)**
- **Serial Port**: Port serial drone (contoh: `/dev/ttyUSB0`)
- **Baud Rate**: Kecepatan serial (harus sama dengan Ground Station)
- **Events CSV/JSON** dan **TDOA JSON**: Nama file output

**TIMING / DELAYS (🔄)**
- **Event Padding**: Audio tambahan sebelum/sesudah event
- **Post-Rec Delay**: Delay setelah stop sebelum processing
- **Main Loop Delay**: Interval polling perintah serial

> ℹ️ Parameter bertanda **⚠** memerlukan **RESTART** drone. Setelah menyimpan parameter tersebut, klik tombol **RESTART** yang muncul di banner peringatan.

**Tombol aksi:**
- **💾 SAVE CONFIG**: Kirim perubahan ke drone via REST API
- **↺ RESET DEFAULTS**: Kembalikan semua nilai ke default
- **👁 PREVIEW CONFIG (JSON)**: Tampilkan konfigurasi saat ini dalam format JSON (bisa disalin ke clipboard)
- **RESTART**: Restart Drone System di Raspberry Pi

> 📸 **[PLACEHOLDER SCREENSHOT]** — *Screenshot sub-tab Raspberry Pi dengan grup "Event Detection" dan "Noise Reduction" terlihat. Tunjukkan banner ⚠ restart yang muncul saat ada perubahan parameter 🔒.*

### 4.2.2 Sub-tab Ground Station

Sub-tab ini mengatur konfigurasi lokal Ground Station (laptop/PC operator).

**SERIAL COMMUNICATION**
- **Serial Port**: Port serial di laptop untuk terhubung ke drone (Windows: COM3; Linux: /dev/ttyUSB0)
- **Baud Rate**: Harus cocok dengan konfigurasi drone
- **Timeout**: Timeout pembacaan serial

**NETWORK / TCP (ALTERNATIVE)**
- **Use TCP**: Gunakan TCP sebagai alternatif serial untuk data transfer (jika tersedia jaringan Wi-Fi)
- **Drone IP Address**: IP Raspberry Pi di jaringan (default: `10.99.99.2`)
- **TCP Port**: Port REST API drone (default: `5000`)

**PROCESSING PARAMETERS**
- **Speed of Sound**: Kecepatan suara dalam m/s (sesuaikan dengan suhu udara)
- **Cluster EPS**: Toleransi clustering Bucher-Misra dalam meter

**VISUALIZATION SETTINGS**
- **Update Interval**: Interval refresh grafik visualisasi
- **Plot Buffer Size**: Jumlah data maksimum di buffer tampilan

**MICROPHONE POSITIONS (3D coordinates in meters)**
- Grid 6 baris × 3 kolom (X, Y, Z) untuk posisi tiap mikrofon
- Tombol **↺ Reset Mic Positions to Default**: Kembalikan ke nilai default
- Klik **💾 SAVE CONFIG** untuk menyimpan perubahan

> 📸 **[PLACEHOLDER SCREENSHOT]** — *Screenshot sub-tab Ground Station bagian Microphone Positions — tampilkan grid input X/Y/Z untuk mic0 hingga mic5.*

---

## 4.3 Tab COMMAND — Kontrol Perekaman

Tab Command adalah pusat kendali operasi utama. Operator menggunakan tab ini untuk menghubungkan serial, memulai/menghentikan perekaman, dan mengecek status drone.

> 📸 **[PLACEHOLDER SCREENSHOT]** — *Screenshot tab Command lengkap: status bar di atas, grid tombol 3×2, panel Status Response, dan panel Last JSON Received.*

### 4.3.1 Status Bar

Di bagian atas tab Command terdapat dua indikator status:

| Indikator | Warna/Teks | Makna |
|---|---|---|
| Status Koneksi | ● CONNECTED (hijau) | Serial terhubung, port aktif ditampilkan |
| Status Koneksi | ● DISCONNECTED (merah) | Serial tidak terhubung |
| Status Rekaman | ● RECORDING (hijau) | Drone sedang merekam audio |
| Status Rekaman | ○ IDLE (abu-abu) | Drone tidak merekam |

### 4.3.2 Grid Tombol Perintah

Enam tombol tersusun dalam grid 3 baris × 2 kolom:

| Tombol | Kondisi Aktif | Fungsi |
|---|---|---|
| **🔌 CONNECT** | Serial tidak terhubung | Buka koneksi serial ke drone |
| **⛌ DISCONNECT** | Serial terhubung | Putuskan koneksi serial |
| **● START REC** | Terhubung, tidak merekam | Kirim perintah `START_REC` ke drone; memulai thread penerimaan JSON berkelanjutan |
| **■ STOP REC** | Terhubung, sedang merekam | Kirim perintah `STOP_REC` ke drone; menghentikan perekaman dan mengakhiri sesi pengiriman data |
| **🔍 STATUS** | Terhubung | Kirim perintah `STATUS`; respons ditampilkan di panel bawah |
| **⚙ PROCESS DATA** | Terhubung + JSON diterima | Pindah ke tab Process dan langsung memproses file JSON chunk terakhir/terpilih |

### 4.3.3 Panel Status Response

Menampilkan respons drone dari perintah STATUS. Contoh respons:
```
> MIC=OK, SDR=OK, ZOOM=OK, RECORDING=False
```

Klik **🔍 STATUS** untuk memperbarui isi panel ini.

### 4.3.4 Panel Last JSON Received

Menampilkan nama file JSON chunk terakhir yang berhasil diterima dan disimpan dari drone. Karena data dikirim secara real-time per chunk (setiap beberapa detik sekali selagi merekam), panel ini akan terus ter-update secara berkala dengan nama file `tdoa_YYYYMMDD_HHMMSS.json` terbaru selama sesi perekaman aktif.

### Alur Operasi di Tab Command

1. Klik **CONNECT** → tunggu indikator berubah jadi CONNECTED
2. Klik **STATUS** → pastikan respons drone normal dan sistem siap
3. Klik **START REC** → indikator berubah jadi RECORDING. Aplikasi drone mulai merekam dan mengalirkan data TDOA secara real-time. Ground Station mulai menerima paket JSON chunk demi chunk secara kontinu di background.
4. Perhatikan panel **LAST JSON RECEIVED** — nama file JSON baru akan muncul setiap kali event suara berhasil dideteksi dan dihitung TDOA-nya pada chunk tersebut.
5. Klik **STOP REC** → drone menghentikan perekaman, mengirimkan sisa data buffer terakhir, dan mengakhiri sesi.
6. Klik **PROCESS DATA** → pindah ke tab Process secara otomatis untuk memproses file JSON yang diterima.

---

## 4.4 Tab PROCESS — Pemrosesan TDOA

Tab Process digunakan untuk mengolah file JSON hasil TDOA dari drone menjadi estimasi posisi sumber suara.

> 📸 **[PLACEHOLDER SCREENSHOT]** — *Screenshot tab Process: panel kiri berisi daftar file JSON, dropdown metode, dan tombol-tombol aksi. Panel kanan berisi log output pemrosesan.*

### 4.4.1 Panel Daftar File JSON (Kiri)

- **Direktori kerja saat ini** ditampilkan di bagian atas
- **Daftar file JSON** yang tersedia di direktori tersebut
- Tombol **📁 CHANGE DIR**: Ganti direktori kerja
- Tombol **↻ REFRESH**: Perbarui daftar file
- **Dropdown Metode**: Pilih metode kalkulasi SSL (Sound Source Localization)
  - Default: Bucher-Misra 3D
  - Metode kustom akan muncul di sini setelah ditambahkan
- Tombol **➕ Add Custom Method…**: Tambah metode SSL kustom (lihat Bab 8)
- Tombol **↻ Refresh Metode**: Reload daftar metode

### 4.4.2 Menjalankan Pemrosesan

1. Pilih file JSON dari daftar (atau file sudah terpilih otomatis jika datang dari tab Command)
2. Pilih metode dari dropdown
3. Klik **▶ PROCESS SELECTED FILE**
4. Output pemrosesan muncul di panel log (kanan):
   ```
   Metode    : Bucher-Misra 3D
   Session ID: session_20260627_103045
   Timestamp : 2026-06-27T10:30:45
   Events    : 3
   ============================================================

   EVENT 1
   ────────────────────────────────────────
   Position  : [1.234, -0.567, 2.891] m
   Cluster   : 5 consistent solutions

   EVENT 2
   ────────────────────────────────────────
   Position  : FAILED (no valid solution)
   ...
   ```
5. Setelah selesai, tombol **💾 Save Results** tersedia untuk menyimpan hasil ke file `*_results.txt`
6. Hasil otomatis tersedia di tab Visualize

### 4.4.3 Membaca Output Pemrosesan

| Baris Output | Penjelasan |
|---|---|
| `Position : [x, y, z] m` | Estimasi koordinat sumber suara dalam meter relatif terhadap pusat drone |
| `Cluster : N consistent solutions` | Jumlah solusi kandidat yang sepakat — makin banyak makin konfiden |
| `Position : FAILED` | Algoritma tidak berhasil menemukan solusi yang konsisten. Lihat Bab 10. |

---

## 4.5 Tab VISUALIZE — Visualisasi Hasil

Tab Visualize menampilkan estimasi posisi sumber suara dalam dua representasi visual yang dapat dipilih.

> 📸 **[PLACEHOLDER SCREENSHOT]** — *Screenshot tab Visualize: panel kiri daftar file hasil, panel kanan dengan dua sub-tab "◈ 3D TACTICAL" dan "◉ 2D RADAR".*

### 4.5.1 Panel Pemilihan File (Kiri)

- Menampilkan daftar file `*_results.txt` di direktori kerja
- Tombol **📁 CHANGE DIR**: Ganti direktori
- Tombol **↻ REFRESH LIST**: Perbarui daftar
- Tombol **▶ VISUALIZE SELECTED**: Tampilkan visualisasi file yang dipilih
- Informasi hitungan: `N result files found`

### 4.5.2 Tampilan 3D Tactical View

Tab **◈ 3D TACTICAL** menampilkan visualisasi isometrik 3D (spike map):
- **Titik biru**: Posisi mikrofon
- **Garis/spike merah atau oranye**: Estimasi posisi sumber suara — panjang spike menunjukkan jarak
- Setiap event ditampilkan dengan spike terpisah

> 📸 **[PLACEHOLDER SCREENSHOT]** — *Screenshot tampilan 3D Tactical View dengan beberapa event terdisplay. Beri label: "titik biru = posisi mikrofon", "spike = sumber suara".*

> ℹ️ **Cara membaca 3D Tactical View:** Sumbu X (merah) = kanan-kiri drone, Sumbu Y (hijau) = depan-belakang drone, Sumbu Z (biru) = atas-bawah. Panjang spike menunjukkan konfiden relatif estimasi.

### 4.5.3 Tampilan 2D Radar View

Tab **◉ 2D RADAR** menampilkan proyeksi radar polar 2D (tampak atas):
- **Lingkaran konsentris**: Jarak dari pusat drone (dalam meter)
- **Titik pada radar**: Estimasi posisi sumber suara (proyeksi ke bidang horizontal)
- Sudut menunjukkan arah datang suara (0° = depan drone)

> 📸 **[PLACEHOLDER SCREENSHOT]** — *Screenshot tampilan 2D Radar View dengan beberapa titik event. Tunjukkan skala jarak dan orientasi arah.*

### 4.5.4 Bar Status Visualisasi

Di bawah area plot, ditampilkan ringkasan:
```
Total: 3  |  Valid: 2  |  Failed: 1
```
- **Total**: Jumlah event dalam file
- **Valid**: Event yang berhasil diestimasi posisinya
- **Failed**: Event yang gagal dihitung posisinya
