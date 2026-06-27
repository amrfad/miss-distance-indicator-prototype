# Bab 7: Referensi Konfigurasi

Dokumen ini merupakan referensi lengkap seluruh parameter konfigurasi yang dapat diubah pada sistem MDI. Parameter dibagi menjadi dua kelompok: **Konfigurasi Drone (Raspberry Pi)** dan **Konfigurasi Ground Station**.

---

## 7.1 Legenda

| Simbol | Makna |
|---|---|
| ⚠ **Restart** | Parameter ini memerlukan restart Drone System agar berlaku setelah diubah |
| 🔄 **Runtime** | Parameter ini berlaku secara langsung (live) tanpa perlu restart |

---

## 7.2 Konfigurasi Drone (Raspberry Pi)

Diakses melalui: **Tab Config → sub-tab Raspberry Pi**

### Grup: Mode Operasi

| Parameter | Default | Tipe | Status | Deskripsi |
|---|---|---|---|---|
| `operation_mode` | `OFFLINE` | Pilihan: `OFFLINE`/`ONLINE` | ⚠ Restart | Mode operasi drone. `ONLINE` = dikontrol Ground Station via serial. `OFFLINE` = dikontrol keyboard. |
| `active_profile` | `H8` | Pilihan: `H8`/`H6E` | ⚠ Restart | Profil perangkat audio. `H8` = Zoom H8 (hingga 6 mic, format S24_3LE). `H6E` = Zoom H6 Essential (4 mic, format S32_LE). |
| `base_output_dir` | `drone_recordings` | String (path) | ⚠ Restart | Direktori penyimpanan hasil rekaman di Raspberry Pi. Dapat berupa path relatif atau absolut. |

### Grup: Konfigurasi Audio

| Parameter | Default | Tipe | Status | Deskripsi |
|---|---|---|---|---|
| `sample_rate` | `48000` | Pilihan: `44100`/`48000`/`96000` | ⚠ Restart | Sample rate audio dalam Hz. Nilai lebih tinggi = kualitas lebih baik tapi file lebih besar dan pemrosesan lebih berat. Gunakan `48000` untuk operasi normal. |
| `num_mics_h8` | `6` | Integer: 4 atau 6 | ⚠ Restart | Jumlah mikrofon yang digunakan (hanya berlaku untuk profil H8). Atur `4` jika hanya menggunakan 4 input XLR. |
| `arecord_device` | `hw:2,0` | String | ⚠ Restart | Identifier perangkat audio `arecord`. Format: `hw:CARD,DEVICE`. Cari nilai yang benar dengan perintah `arecord -l` di Raspberry Pi. |
| `arecord_terminate_timeout` | `3.0` | Float (detik) | ⚠ Restart | Waktu tunggu saat mematikan `arecord`. Naikkan jika drone sering gagal menghentikan perekaman dengan bersih. |

### Grup: Deteksi Event

| Parameter | Default | Range | Status | Deskripsi |
|---|---|---|---|---|
| `detect_ratio` | `0.20` | 0.01 – 1.0 | 🔄 Runtime | Sensitivitas deteksi event. Nilai lebih rendah = lebih sensitif (mendeteksi suara lebih lemah). Nilai lebih tinggi = hanya mendeteksi suara sangat keras. **Turunkan jika event tidak terdeteksi; naikkan jika terlalu banyak false positive.** |
| `filter_ratio` | `0.40` | 0.01 – 1.0 | 🔄 Runtime | Ambang batas kualitas sinyal event. Event dengan energi relatif di bawah nilai ini dibuang. |
| `min_duration` | `0.25` | 0.01 – 5.0 detik | 🔄 Runtime | Durasi minimum event agar dianggap valid. Event yang lebih pendek dari nilai ini diabaikan. |
| `max_gap` | `0.10` | 0.01 – 5.0 detik | 🔄 Runtime | Gap maksimum antara dua event agar digabungkan menjadi satu event tunggal. |
| `ignore_time` | `0.5` | 0.0 – 10.0 detik | 🔄 Runtime | Durasi awal perekaman yang diabaikan untuk deteksi. Berguna untuk menghindari noise saat `arecord` baru dimulai. |

### Grup: Noise Reduction

| Parameter | Default | Range | Status | Deskripsi |
|---|---|---|---|---|
| `prop_decrease` | `1.0` | 0.0 – 1.0 | 🔄 Runtime | Seberapa besar noise dikurangi. `1.0` = pengurangan penuh. `0.5` = 50% pengurangan. Kurangi jika suara target ikut terpotong. |
| `normalization_percentile` | `99.9` | 0.1 – 100.0 % | 🔄 Runtime | Persentil untuk normalisasi amplitudo sinyal. Digunakan agar level audio konsisten. |
| `stationary` | `False` | Boolean | 🔄 Runtime | Aktifkan jika noise bersifat stasioner (konstan, seperti bunyi mesin). Nonaktifkan untuk noise yang berubah-ubah (angin, dll.). |
| `normalize` | `False` | Boolean | 🔄 Runtime | Normalisasi output audio setelah noise reduction. Berguna untuk Zoom H6E yang menggunakan format 32-bit float. |
| `freq_mask_smooth_hz` | `100` | 10 – 2000 Hz | 🔄 Runtime | Smoothing mask frekuensi dalam Hz. Nilai lebih tinggi = transisi lebih halus antar frekuensi. |
| `time_mask_smooth_ms` | `10` | 1 – 200 ms | 🔄 Runtime | Smoothing mask waktu dalam ms. |

### Grup: Filter Method

| Parameter | Default | Tipe | Status | Deskripsi |
|---|---|---|---|---|
| `filter_method` | `spectral_gating` | String | 🔄 Runtime | Metode noise reduction yang digunakan. Pilihan bawaan: `spectral_gating`, `wiener_filter`. Metode kustom akan muncul setelah ditambahkan (lihat Bab 8). |
| `filter_configs` | `{}` | Dict | 🔄 Runtime | Parameter spesifik per metode filter. Dikonfigurasi secara otomatis melalui panel Filter Method di GUI. |

### Grup: TDOA / GCC-PHAT

| Parameter | Default | Range | Status | Deskripsi |
|---|---|---|---|---|
| `is_gcc_phat` | `True` | Boolean | ⚠ Restart | Aktifkan algoritma GCC-PHAT untuk perhitungan TDOA. Sangat direkomendasikan tetap `True` untuk akurasi optimal. |
| `hop_length` | `512` | 64 – 4096 | 🔄 Runtime | Ukuran hop untuk analisis frame audio. Mempengaruhi resolusi waktu perhitungan TDOA. |
| `frame_length` | `1024` | 128 – 8192 | 🔄 Runtime | Ukuran frame analisis. Harus ≥ 2 × `hop_length`. |

### Grup: Serial & File Output

| Parameter | Default | Tipe | Status | Deskripsi |
|---|---|---|---|---|
| `serial_port` | `/dev/ttyUSB0` | String | ⚠ Restart | Port serial yang digunakan drone untuk komunikasi. Cek dengan `ls /dev/tty*` di Raspberry Pi. |
| `baud_rate` | `230400` | Pilihan | ⚠ Restart | Kecepatan komunikasi serial. **Harus sama persis dengan setting di Ground Station.** |
| `serial_timeout` | `5.0` | Float (detik) | ⚠ Restart | Timeout membaca data serial. |
| `events_csv` | `detected_events.csv` | String | ⚠ Restart | Nama file CSV untuk daftar event yang terdeteksi. |
| `events_json` | `session_events.json` | String | ⚠ Restart | Nama file JSON untuk data detail event. |
| `tdoa_json` | `session_tdoa.json` | String | ⚠ Restart | Nama file JSON hasil TDOA yang dikirim ke Ground Station. |

### Grup: Timing / Delays

| Parameter | Default | Range | Status | Deskripsi |
|---|---|---|---|---|
| `event_padding_sec` | `0.3` | 0.0 – 2.0 detik | 🔄 Runtime | Padding audio tambahan sebelum dan sesudah event untuk memastikan sinyal lengkap tertangkap. |
| `post_recording_delay` | `0.5` | 0.0 – 10.0 detik | 🔄 Runtime | Delay setelah `arecord` berhenti sebelum memulai pemrosesan. |
| `main_loop_delay` | `0.1` | 0.01 – 5.0 detik | 🔄 Runtime | Interval polling perintah serial dalam mode ONLINE. |

---

## 7.3 Konfigurasi Ground Station

Diakses melalui: **Tab Config → sub-tab Ground Station**

### Grup: Komunikasi Serial

| Parameter | Default | Tipe | Deskripsi |
|---|---|---|---|
| `serial_port` | `COM3` | String | Port serial di Ground Station. Windows: `COM3`, `COM7`, dll. Linux: `/dev/ttyUSB0`. |
| `baud_rate` | `230400` | Pilihan | Kecepatan serial. **Harus sama dengan konfigurasi drone.** |
| `serial_timeout` | `1.0` | Float (detik) | Timeout pembacaan serial di Ground Station. |

### Grup: Jaringan / TCP (Alternatif)

| Parameter | Default | Tipe | Deskripsi |
|---|---|---|---|
| `use_tcp` | `False` | Boolean | Aktifkan jika ingin menggunakan TCP socket sebagai pengganti serial untuk pengiriman data JSON. |
| `raspi_ip` | `10.99.99.2` | String (IP) | Alamat IP Raspberry Pi di jaringan. Digunakan untuk REST API konfigurasi. |
| `tcp_port` | `5000` | Integer | Port TCP untuk koneksi REST API ke drone. |

### Grup: Parameter Pemrosesan

| Parameter | Default | Range | Deskripsi |
|---|---|---|---|
| `speed_of_sound` | `343.0` | 300.0 – 380.0 m/s | Kecepatan suara yang digunakan dalam perhitungan posisi. Nilai ini dipengaruhi suhu udara. Gunakan rumus: `v = 331.3 + 0.606 × T°C` untuk kalkulasi akurat. |
| `cluster_eps` | `1.0` | 0.1 – 20.0 m | Jarak maksimum (meter) antara dua solusi kandidat Bucher-Misra agar dianggap satu cluster. Naikkan jika hasil sering "FAILED" karena solusi tersebar. |

### Grup: Posisi Mikrofon

Masukkan koordinat posisi fisik tiap mikrofon dalam sistem koordinat drone (satuan meter).

| Parameter | Contoh Default | Deskripsi |
|---|---|---|
| `mic0` (X, Y, Z) | -1.58, 0.77, 0.09 | Posisi 3D mikrofon 0 relatif terhadap pusat drone |
| `mic1` (X, Y, Z) | 1.60, 0.77, 0.09 | Posisi 3D mikrofon 1 |
| `mic2` (X, Y, Z) | -0.59, -0.92, -0.07 | Posisi 3D mikrofon 2 |
| `mic3` (X, Y, Z) | 0.59, -0.92, -0.05 | Posisi 3D mikrofon 3 |
| `mic4` (X, Y, Z) | -0.50, -0.11, -0.16 | Posisi 3D mikrofon 4 |
| `mic5` (X, Y, Z) | 0.13, -0.01, -0.17 | Posisi 3D mikrofon 5 |

> ⚠️ **Koordinat ini HARUS diukur secara fisik dari instalasi aktual.** Nilai default di atas hanya placeholder. Kesalahan posisi mikrofon akan langsung mempengaruhi akurasi estimasi posisi sumber suara.

### Grup: Pengaturan Visualisasi

| Parameter | Default | Range | Deskripsi |
|---|---|---|---|
| `update_interval_s` | `0.1` | 0.033 – 2.0 detik | Interval refresh tampilan visualisasi. |
| `plot_buffer_size` | `1000` | 100 – 20000 | Jumlah titik data maksimum yang ditampilkan pada grafik. |

---

## 7.4 Lokasi File Konfigurasi

Konfigurasi tersimpan dalam file JSON yang dapat diedit manual jika diperlukan:

| Subsistem | Lokasi File |
|---|---|
| Drone (Raspberry Pi) | `udara/config/drone_config_override.json` |
| Ground Station | `darat/config/ground_config_override.json` |

> ℹ️ Jika file override tidak ada, sistem menggunakan nilai default yang sudah tertanam di kode. File override dibuat pertama kali saat operator menekan **SAVE CONFIG** dari GUI.

---

## 7.5 Rekomendasi Pengaturan Per Kondisi

### Lingkungan dengan Banyak Noise Angin
- Naikkan `detect_ratio` (contoh: 0.35) untuk mengurangi false detection
- Aktifkan `stationary = False` (mode non-stasioner lebih cocok untuk noise angin)
- Naikkan `min_duration` (contoh: 0.3) untuk memfilter transien pendek

### Lingkungan Tenang (Indoor Testing)
- Turunkan `detect_ratio` (contoh: 0.10) untuk sensitivitas lebih tinggi
- Turunkan `min_duration` (contoh: 0.15) untuk mendeteksi suara lebih pendek

### Akurasi Posisi Rendah (Hasil sering FAILED)
- Turunkan `cluster_eps` secara bertahap (mulai dari 2.0, 3.0) jika cluster terlalu terpencar
- Pastikan `speed_of_sound` sudah dikoreksi sesuai suhu udara aktual
- Periksa kembali koordinat posisi mikrofon — pastikan sudah diukur ulang

### Suara Target Ikut Terpotong Saat Noise Reduction
- Turunkan `prop_decrease` (contoh: 0.6 atau 0.5)
- Aktifkan `normalize = True` untuk menormalisasi level output
