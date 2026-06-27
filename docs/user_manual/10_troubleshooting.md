# Bab 10: Troubleshooting dan Dukungan

---

## 10.1 Tabel Error Umum

### 10.1.1 Error Koneksi Serial

| Gejala | Kemungkinan Penyebab | Solusi |
|---|---|---|
| Tombol CONNECT tidak berhasil; indikator tetap DISCONNECTED | Port serial salah dikonfigurasi | Cek nama port di Config → Ground Station → Serial Port (Windows: Device Manager; Linux: `ls /dev/tty*`) |
| `Permission denied` saat CONNECT di Linux | User tidak punya hak akses port serial | Jalankan: `sudo usermod -a -G dialout $USER` lalu logout dan login ulang |
| CONNECTED tapi tidak ada respons dari STATUS | Baudrate tidak cocok | Pastikan baudrate Ground Station = baudrate drone (default: 230400). Cek di kedua sisi. |
| Koneksi sering putus (intermittent) | Kabel USB serial longgar atau kualitas buruk | Ganti kabel; coba port USB yang berbeda; cek kualitas konektor |
| Tidak ada respons sama sekali (drone mode ONLINE) | Drone tidak dalam mode ONLINE, atau serial_port drone salah | SSH ke RPi, cek log drone: `journalctl -u mdi_drone.service -n 50` |

### 10.1.2 Error Perekaman Audio

| Gejala | Kemungkinan Penyebab | Solusi |
|---|---|---|
| `Device not found` / `arecord: device not detected` | Zoom tidak dalam mode Audio Interface | Cek mode di Zoom: Menu → USB → Audio Interface |
| `arecord: device not detected` | Kabel USB Zoom-RPi belum terpasang atau longgar | Cabut dan pasang kembali kabel USB; cek `arecord -l` di RPi |
| Nilai `arecord_device` salah (misal `hw:3,0` tapi device ada di `hw:2,0`) | Nomor card berbeda di sistem RPi | Jalankan `arecord -l` di RPi; cari baris `card X: ...` untuk Zoom; update config |
| Audio kosong / silent (0 event terdeteksi padahal ada suara) | Gain Zoom terlalu rendah | Naikkan gain/volume pada Zoom Recorder secara fisik |
| Selalu `0 events` meskipun ada suara keras | `detect_ratio` terlalu tinggi | Turunkan `detect_ratio` (coba 0.10 atau 0.05) di Config → Raspberry Pi |
| Terlalu banyak false event | `detect_ratio` terlalu rendah | Naikkan `detect_ratio`; atau naikkan `min_duration` |

### 10.1.3 Error Pengiriman dan Penerimaan JSON

| Gejala | Kemungkinan Penyebab | Solusi |
|---|---|---|
| Setelah STOP_REC, "LAST JSON RECEIVED" tidak terisi setelah lama menunggu | Tidak ada event terdeteksi (file JSON tetap kosong) | Cek log Ground Station dan drone; cek event count di JSON di RPi |
| File JSON diterima tapi isinya rusak / parse error | Transmisi terpotong di tengah | Cek log Ground Station; pastikan koneksi serial stabil selama transmisi |
| Drone mengirim JSON tapi Ground Station tidak menerima | Ground Station tidak dalam mode terima (START_REC belum dikirim) | Pastikan alur yang benar: CONNECT → START_REC → STOP_REC (jangan skip langkah) |

### 10.1.4 Error Pemrosesan TDOA (Ground Station)

| Gejala | Kemungkinan Penyebab | Solusi |
|---|---|---|
| `Position : FAILED` untuk semua event | Koordinat posisi mikrofon tidak konsisten | Verifikasi koordinat mic di Config → Ground Station. Pastikan diukur dengan benar. |
| `Position : FAILED` untuk semua event | `cluster_eps` terlalu kecil — solusi tersebar | Naikkan `cluster_eps` (coba 2.0, 3.0, 5.0) |
| Estimasi posisi tidak masuk akal (sangat jauh atau ekstrem) | Nilai TDOA mengandung error besar | Coba metode SSL alternatif; verifikasi posisi mikrofon; periksa kualitas sinyal audio |
| `Bucher-Misra requires at least 4 stations` | Kurang dari 4 mikrofon dikonfigurasi | Pastikan `num_mics_h8 = 4` (minimum), dan 4 mikrofon terhubung secara fisik |
| Error `KeyError: 'mic0-mic1'` | Data TDOA tidak lengkap di file JSON | File JSON mungkin korup atau dari sesi dengan mic count berbeda dari konfigurasi saat ini |

### 10.1.5 Error Konfigurasi

| Gejala | Kemungkinan Penyebab | Solusi |
|---|---|---|
| SAVE CONFIG tidak berhasil / tidak ada perubahan di drone | REST API drone tidak berjalan | Pastikan Drone System sudah berjalan dan IP yang dikonfigurasi benar (`raspi_ip`) |
| Perubahan parameter tidak berpengaruh setelah SAVE | Parameter tersebut memerlukan RESTART (ditandai ⚠) | Klik tombol RESTART yang muncul di banner peringatan |
| Konfigurasi Ground Station kembali ke default setiap kali aplikasi dibuka | File `ground_config_override.json` tidak tersimpan | Pastikan folder `darat/config/` bisa ditulis; cek izin folder |
| Filter baru tidak muncul di dropdown | Drone System belum di-restart setelah filter ditambahkan | Restart Drone System: `sudo systemctl restart mdi_drone.service` |

### 10.1.6 Error Visualisasi

| Gejala | Kemungkinan Penyebab | Solusi |
|---|---|---|
| `No result files found` di tab Visualize | Direktori kerja salah | Klik CHANGE DIR dan pilih folder yang berisi file `*_results.txt` |
| Visualisasi kosong setelah VISUALIZE SELECTED | File hasil tidak mengandung event valid | Cek isi file TXT; jika semua FAILED, baca bagian error TDOA |
| Tampilan 3D atau 2D tidak merespons | Aplikasi mungkin tidak responsif sementara | Tunggu beberapa detik; kalau tetap freeze, restart Ground Station |

---

## 10.2 Diagnostic Checklist

Gunakan checklist ini secara berurutan sebelum melaporkan masalah:

**Checklist Umum:**
- [ ] Semua kabel fisik terpasang dengan benar (USB, XLR, Serial)
- [ ] Zoom dalam mode Audio Interface (bukan mode Recorder biasa)
- [ ] Raspberry Pi sudah booting sepenuhnya (tunggu minimal 60 detik setelah power on)
- [ ] Drone System berjalan (cek dengan `sudo systemctl status mdi_drone.service`)
- [ ] Ground Station sudah berjalan
- [ ] Baudrate sama di kedua sisi (default: 230400)
- [ ] IP Raspberry Pi di konfigurasi Ground Station sudah benar

**Checklist Jika Tidak Ada Event:**
- [ ] `arecord -l` di RPi menampilkan Zoom Recorder
- [ ] Level gain Zoom tidak terlalu rendah
- [ ] `detect_ratio` tidak terlalu tinggi (coba kurangi ke 0.10)
- [ ] Pastikan ada suara yang signifikan saat testing

**Checklist Jika FAILED semua:**
- [ ] Koordinat mikrofon sudah diukur dan diinput dengan benar
- [ ] `speed_of_sound` sudah disesuaikan (coba nilai default 343.0 dulu)
- [ ] `cluster_eps` cukup besar (coba 2.0 atau lebih)
- [ ] Jumlah mikrofon yang dikonfigurasi cocok dengan yang terpasang

---

## 10.3 Cara Mendapatkan Informasi Log untuk Dilaporkan

Jika masalah tidak dapat diselesaikan sendiri, kumpulkan informasi berikut sebelum menghubungi tim support:

**Dari Ground Station:**
- Screenshot panel Log (bagian bawah aplikasi)
- File `ground_config_override.json` dari folder `darat/config/`

**Dari Drone System:**
```bash
# Log 100 baris terakhir
journalctl -u mdi_drone.service -n 100 > drone_log.txt

# Atau jika berjalan di terminal, salin output terminal
```

**File Data:**
- File `session_tdoa.json` yang bermasalah
- File `session_events.json` dari sesi yang sama

---

## 10.4 Kontak Dukungan

| Nama | Organisasi | Peran | Tanggung Jawab |
|---|---|---|---|
| — | — | — | — |

> ℹ️ **[PLACEHOLDER TABEL]** — *Isi tabel ini dengan nama, email, nomor telepon, dan peran personel yang bertanggung jawab terhadap sistem MDI.*
