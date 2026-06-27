# Bab 3: Panduan Hardware dan Pemasangan

---

## 3.1 Daftar Hardware yang Dibutuhkan

### Komponen Wajib

| Komponen | Spesifikasi / Model | Fungsi |
|---|---|---|
| Komputer Drone | Raspberry Pi 5 (RAM 4 GB atau 8 GB) | Menjalankan Drone System |
| Audio Recorder | Zoom H8 **atau** Zoom H6 Essential (H6E) | Antarmuka mikrofon multi-channel |
| Mikrofon | 4 atau 6 unit, kondenser, konektor XLR | Penangkap suara |
| Sistem Telemetri | SIYI HM30 (air unit + ground unit) | Komunikasi serial nirkabel drone ↔ Ground Station |
| Laptop / PC | Windows 10/11 atau Linux, RAM ≥ 4 GB | Menjalankan Ground Station |
| Kabel USB-A ke USB-C atau USB-A ke USB-A | Sesuai tipe port Zoom | Menghubungkan Zoom ke Raspberry Pi |
| Kabel XLR | 4 atau 6 unit | Menghubungkan mikrofon ke Zoom |

### Komponen Opsional / Pendukung

| Komponen | Fungsi |
|---|---|
| Power bank / baterai khusus RPi | Catu daya Raspberry Pi saat di drone |
| USB Hub | Jika Raspberry Pi perlu banyak perangkat USB |

---

## 3.2 Konfigurasi Zoom Recorder

### Mengaktifkan Mode Audio Interface

> **PENTING:** Zoom H8/H6E harus diatur ke mode **Audio Interface** agar dapat dikenali sebagai perangkat audio oleh Raspberry Pi. Mode ini **berbeda** dari mode recorder biasa.

**Langkah untuk Zoom H8:**
1. Nyalakan Zoom H8
2. Navigasi ke menu utama: tekan tombol **MENU**
3. Pilih **System** → **USB**
4. Pilih **Audio Interface**
5. Sambungkan kabel USB ke Raspberry Pi
6. Pastikan Zoom terdeteksi sebagai audio device: pada Raspberry Pi, jalankan `arecord -l` dan cek apakah perangkat Zoom muncul

> 📸 **[PLACEHOLDER GAMBAR]** — *Foto layar Zoom H8 saat memilih menu Audio Interface. Tambahkan foto aktual perangkat.*

**Langkah untuk Zoom H6 Essential (H6E):**
1. Nyalakan Zoom H6E
2. Tekan tombol **MENU**
3. Pilih **USB** → **Audio Interface**
4. Hubungkan ke Raspberry Pi

---

## 3.3 Konfigurasi Mikrofon

### Jumlah Mikrofon

Sistem MDI mendukung **4 atau 6 mikrofon**:
- **4 mikrofon**: Konfigurasi minimum. Menggunakan input XLR channel 5-8 pada H8 (indeks `take_indices_4mic`)
- **6 mikrofon**: Konfigurasi penuh. Menggunakan channel 5-10 pada H8 (indeks `take_indices_6mic`), termasuk 2 mikrofon capsule bawaan Zoom

Untuk **Zoom H6E**: Selalu 4 mikrofon (channel 3–6).

### Posisi Mikrofon (Koordinat 3D)

Posisi mikrofon dalam sistem koordinat 3D (satuan meter) **harus diukur secara fisik** dan dimasukkan ke konfigurasi Ground Station. Koordinat menggunakan sistem sumbu sebagai berikut:

```
         +Y (depan drone)
          ↑
          |
 -X ──────┼────── +X (kanan drone)
          |
          ↓
         -Y (belakang drone)

+Z = atas (naik)
-Z = bawah (turun)
```

> 📸 **[PLACEHOLDER GAMBAR/DIAGRAM]** — *Diagram top-view drone dengan posisi 4 atau 6 mikrofon yang diberi label mic0–mic5, lengkap dengan koordinat XYZ dan jarak antar mikrofon. Buat gambar berdasarkan konfigurasi aktual pemasangan mikrofon di drone.*

**Posisi default pada sistem (untuk referensi awal, sesuaikan dengan pengukuran aktual):**

| Mic | X (m) | Y (m) | Z (m) | Keterangan |
|---|---|---|---|---|
| mic0 | -1.58 | 0.77 | 0.09 | Kiri depan |
| mic1 | 1.60 | 0.77 | 0.09 | Kanan depan |
| mic2 | -0.59 | -0.92 | -0.07 | Kiri belakang |
| mic3 | 0.59 | -0.92 | -0.05 | Kanan belakang |
| mic4 | -0.50 | -0.11 | -0.16 | Kiri tengah |
| mic5 | 0.13 | -0.01 | -0.17 | Kanan tengah |

> ⚠️ **PENTING:** Nilai koordinat di atas adalah default yang mungkin tidak sesuai dengan konfigurasi fisik drone Anda. **Selalu ukur dan masukkan koordinat aktual** ke tab Config → Ground Station → Microphone Positions sebelum operasi.

---

## 3.4 Diagram Koneksi Keseluruhan

> 📸 **[PLACEHOLDER DIAGRAM]** — *Diagram wiring lengkap yang menunjukkan:*
> - *Mikrofon (mic0–mic5) → kabel XLR → Zoom H8*
> - *Zoom H8 → kabel USB → Raspberry Pi 5*
> - *Raspberry Pi 5 → kabel bawaan SIYI HM30 (USB) → SIYI HM30 Air Unit (di drone)*
> - *SIYI HM30 Air Unit ~~radio link~~→ SIYI HM30 Ground Unit (di operator)*
> - *SIYI HM30 Ground Unit → USB → Laptop Ground Station (muncul sebagai COM port)*
> - *Label nama port: USB port RPi, COM port laptop*

**Deskripsi koneksi:**

```
[Mikrofon 0] ──XLR──► [Input 1 Zoom H8]
[Mikrofon 1] ──XLR──► [Input 2 Zoom H8]
[Mikrofon 2] ──XLR──► [Input 3 Zoom H8]
[Mikrofon 3] ──XLR──► [Input 4 Zoom H8]
                              │
                         USB (Zoom)
                              │
                    [Raspberry Pi 5]
                              │
                    USB (kabel bawaan SIYI)
                              │
               [SIYI HM30 Air Unit — di drone]
                              │
                     ~~ radio link ~~
                              │
             [SIYI HM30 Ground Unit — di operator]
                              │
                           USB
                              │
                    [Laptop Ground Station]
                    (COM3 / /dev/ttyUSB0)
```

---

## 3.5 Konfigurasi Koneksi Serial (SIYI HM30)

Sistem MDI menggunakan **SIYI HM30** sebagai sistem telemetri untuk komunikasi serial antara drone (Raspberry Pi) dan Ground Station (laptop). SIYI HM30 terdiri dari dua unit:

- **Air Unit** — dipasang di drone, terhubung ke Raspberry Pi
- **Ground Unit** — dipegang operator, terhubung ke laptop

Keduanya berkomunikasi secara nirkabel via radio.

### Koneksi di Sisi Drone (Raspberry Pi)

- Gunakan **kabel bawaan SIYI HM30** yang sudah tersedia (tinggal colok)
- Sambungkan kabel dari port USB Raspberry Pi ke port serial SIYI HM30 Air Unit
- Tidak ada wiring per-pin yang diperlukan
- SIYI HM30 Air Unit akan terdeteksi sebagai serial device: `/dev/ttyUSB0` (atau `/dev/ttyUSB1` tergantung urutan perangkat USB lain)
- Baudrate: **230400 bps** (default — harus cocok dengan konfigurasi Ground Station)

### Koneksi di Sisi Ground Station (Laptop)

- Sambungkan SIYI HM30 Ground Unit ke port USB laptop
- Ground Unit akan terdeteksi secara otomatis sebagai COM port:
  - **Windows:** `COM3`, `COM7`, dll. (cek di Device Manager → Ports)
  - **Linux:** `/dev/ttyUSB0` atau sejenisnya
- Konfigurasi port ini di Ground Station: tab **Config → Ground Station → Serial Port**

> 📸 **[PLACEHOLDER FOTO]** — *Foto SIYI HM30 Air Unit yang terpasang di drone dengan kabel bawaan tersambung ke Raspberry Pi, dan foto SIYI HM30 Ground Unit yang tersambung ke laptop via USB.*

> ℹ️ **Baudrate default SIYI HM30** untuk pass-through serial data adalah **230400 bps**. Pastikan nilai ini konsisten di konfigurasi drone dan Ground Station.

---

## 3.6 Verifikasi Hardware Sebelum Operasi

Gunakan checklist berikut sebelum setiap sesi operasional:

- [ ] Zoom H8/H6E dalam mode **Audio Interface**
- [ ] Semua kabel XLR mikrofon terpasang dengan benar
- [ ] Zoom terhubung ke Raspberry Pi via USB dan terdeteksi (`arecord -l` menampilkan Zoom)
- [ ] SIYI HM30 Air Unit terpasang di drone dan terhubung ke Raspberry Pi via kabel bawaan
- [ ] SIYI HM30 Ground Unit terhubung ke laptop via USB dan terdeteksi sebagai COM port
- [ ] Level gain pada Zoom diatur sesuai — tidak terlalu rendah (sinyal lemah) dan tidak clipping
- [ ] Raspberry Pi sudah booting dan Drone System berjalan
- [ ] Ground Station laptop sudah menyala dan aplikasi MDI siap dijalankan
