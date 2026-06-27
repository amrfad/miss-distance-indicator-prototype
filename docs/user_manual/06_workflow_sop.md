# Bab 6: Prosedur Operasional Standar (SOP)

---

## 6.1 SOP-01: Setup Awal (Pertama Kali)

Ikuti prosedur ini saat menggunakan sistem MDI untuk pertama kalinya atau setelah perubahan hardware.

### Langkah-Langkah

**A. Persiapan Hardware (lihat Bab 3 untuk detail)**
1. Pasang Raspberry Pi 5 di drone
2. Sambungkan Zoom H8/H6E ke Raspberry Pi via USB
3. Sambungkan semua mikrofon ke input XLR Zoom
4. Sambungkan koneksi serial (USB-to-TTL atau telemetri) antara RPi dan laptop
5. Atur Zoom ke mode **Audio Interface**

**B. Instalasi Software (lihat Bab 2 untuk detail)**
1. Install Drone System di Raspberry Pi
2. Install Ground Station di laptop
3. Konfigurasikan autostart (`mdi_drone.service`) jika diinginkan

**C. Pengukuran Posisi Mikrofon**
1. Ukur koordinat XYZ tiap mikrofon secara fisik dengan penggaris/meteran
2. Gunakan pusat drone sebagai titik origin (0, 0, 0)
3. Catat hasil pengukuran

**D. Konfigurasi Awal**
1. Jalankan Ground Station dan Drone System
2. Buka tab **Config → Ground Station → Microphone Positions**
3. Masukkan koordinat tiap mikrofon hasil pengukuran
4. Klik **SAVE CONFIG**
5. Buka tab **Config → Raspberry Pi**
6. Atur **Device Profile** (H8 atau H6E) dan **Mic Count**
7. Atur **Operation Mode** ke `ONLINE`
8. Pastikan **Serial Port** dan **Baud Rate** sudah benar
9. Klik **SAVE CONFIG** → klik **RESTART** saat diminta

**E. Uji Coba Komunikasi**
1. Di tab Command, klik **CONNECT**
2. Klik **STATUS** → pastikan respons muncul di panel
3. Klik **START REC**, tunggu 5 detik, klik **STOP REC**
4. Pastikan file JSON diterima (indikator "Last JSON Received" terisi)
5. Klik **PROCESS DATA** → pastikan ada event yang terdeteksi (atau "0 events" jika lingkungan tenang)

---

## 6.2 SOP-02: Operasi Misi Harian

Prosedur standar untuk setiap sesi operasional lapangan.

### Checklist Pra-Misi

- [ ] Zoom H8/H6E dalam mode Audio Interface
- [ ] Semua kabel XLR terpasang
- [ ] Koneksi serial terpasang (USB-to-TTL atau modul telemetri)
- [ ] Raspberry Pi sudah booting (LED indikator aktif)
- [ ] Laptop Ground Station sudah menyala

### Alur Misi

```
PERSIAPAN
    │
    ▼
[1] Nyalakan Raspberry Pi
    └─ Tunggu ±30–60 detik hingga booting selesai
    │
    ▼
[2] Jalankan Ground Station di laptop
    └─ python darat/main.py
    │
    ▼
[3] Buka tab Config → Verifikasi parameter
    └─ Pastikan Mic Count, Device Profile, Serial Port sudah benar
    │
    ▼
[4] Tab Command → Klik CONNECT
    └─ Tunggu indikator "● CONNECTED"
    │
    ▼
[5] Klik STATUS
    └─ Baca respons drone di panel Status Response
    └─ Pastikan tidak ada error
    │
    ▼
[6] Klik START REC ──► Drone mulai merekam audio
    └─ Indikator berubah jadi "● RECORDING"
    │
    ▼ (misi berlangsung)
    │  • Drone memotong audio per chunk (misal 5s)
    │  • Proses denoising & deteksi event berjalan di drone
    │  • Jika ada event, drone mengirim file tdoa.json via serial
    │  • Panel "LAST JSON RECEIVED" terisi file tdoa_*.json baru
    │
[7] Klik STOP REC ──► Drone menghentikan perekaman
    └─ Drone menyelesaikan pemrosesan chunk terakhir
    └─ Indikator kembali ke "○ IDLE"
    │
    ▼
[8] Klik PROCESS DATA (atau buka tab Process manual)
    └─ Pilih salah satu file tdoa_*.json chunk yang ingin dihitung
    └─ Pilih metode SSL
    └─ Klik PROCESS → Baca hasil koordinat 3D di log
    │
    ▼
[9] Buka tab VISUALIZE
    └─ Pilih file *_results.txt hasil pemrosesan
    └─ Klik VISUALIZE SELECTED
    └─ Amati posisi sumber suara di 3D Tactical dan 2D Radar
    │
    ▼
[10] Klik DISCONNECT jika sesi selesai
```

### Durasi Pemrosesan Drone dan Latensi

Karena sistem MDI memproses audio per chunk secara berkelanjutan (*online streaming*), latensi pengolahan data sangat rendah:
- **Delay pengiriman:** File JSON untuk suatu event suara biasanya akan diterima di Ground Station dalam waktu **2 hingga 5 detik** setelah event suara tersebut secara fisik terjadi di udara.
- **Waktu pasca STOP_REC:** Saat tombol STOP REC ditekan, Anda hanya perlu menunggu sekitar **2–5 detik** bagi drone untuk mengirimkan chunk terakhir sebelum status kembali ke IDLE sepenuhnya.

---

## 6.3 SOP-03: Pengujian Sistem di Darat (OFFLINE Mode)

Prosedur untuk testing sistem audio di darat tanpa Ground Station.

### Kapan Digunakan
- Testing threshold deteksi dengan suara buatan
- Kalibrasi level gain Zoom Recorder
- Verifikasi pipeline pemrosesan sebelum misi

### Langkah-Langkah

1. **Set mode ke OFFLINE** (via Ground Station terlebih dahulu, atau edit file konfigurasi JSON drone langsung)

2. **SSH ke Raspberry Pi** (atau akses langsung via keyboard):
   ```bash
   ssh pi@10.99.99.2
   cd ~/mdi/udara
   source .venv/bin/activate
   python run_drone_system.py
   ```

3. **Sistem akan menampilkan menu keyboard:**
   ```
   OFFLINE MODE - Keyboard Control
   Commands:
     s - Start Recording
     p - Stop Recording and Process
     t - Get Status
     i - System Info
     q - Quit
   ```

4. **Tekan `s`** untuk mulai merekam

5. **Buat suara impulsif** (ketuk keras pada permukaan, tepuk tangan, dll.) dalam jarak dekat dari mikrofon

6. **Tekan `p`** untuk berhenti dan memproses

7. **Cek output terminal** — pastikan event terdeteksi dan nilai TDOA tampil

8. **Transfer file hasil ke laptop** jika ingin divisualisasi:
   ```bash
   scp pi@10.99.99.2:~/mdi/udara/drone_recordings/session_*/session_tdoa.json ./
   ```

---

## 6.4 SOP-04: Recovery Setelah Kehilangan Koneksi Serial

Prosedur jika koneksi serial terputus di tengah sesi (misal: kabel lepas, sinyal radio putus).

### Identifikasi Masalah
- Indikator status di tab Command berubah menjadi "● DISCONNECTED"
- Tidak ada respons dari drone saat klik STATUS

### Langkah Recovery

**Jika drone masih merekam (START_REC sudah dikirim):**
1. Jangan panik — drone **tetap merekam secara mandiri** meskipun koneksi terputus
2. Perbaiki koneksi fisik (kencangkan kabel / perbaiki modul telemetri)
3. Di Ground Station, klik **DISCONNECT** terlebih dahulu (reset state)
4. Klik **CONNECT** kembali
5. Klik **STOP REC** untuk menghentikan rekaman
6. Tunggu file JSON diterima

**Jika koneksi tidak bisa dipulihkan:**
1. Hentikan Drone System secara langsung di Raspberry Pi (Ctrl+C atau `systemctl stop`)
   - Ini akan otomatis menghentikan rekaman dan memproses data yang ada
2. Transfer file `session_tdoa.json` secara manual ke laptop via USB atau SCP
3. Di Ground Station, tab Process → CHANGE DIR ke folder file JSON
4. Lanjutkan pemrosesan seperti biasa

---

## 6.5 SOP-05: Interpretasi Hasil Visualisasi

Panduan membaca hasil visualisasi setelah pemrosesan selesai.

### Membaca 3D Tactical View

```
         +Y (Depan Drone)
          ↑
    ●───────────●
   mic0         mic1   ← Titik biru = posisi mikrofon
    │             │
    │      ×      │    ← × = estimasi posisi sumber suara (event)
    │             │
   mic2         mic3
    ●───────────●
          │
         -Y (Belakang Drone)
```

- **Lokasi titik/spike**: Estimasi posisi sumber suara relatif terhadap drone
- **Nilai [x, y, z]**: Baca di panel log tab Process atau hover atas elemen visual
- **Konfiden**: Event dengan cluster size besar (> 5) lebih dipercaya

### Membaca 2D Radar View

- **Pusat radar (0, 0)**: Posisi drone
- **Jarak dari pusat**: Estimasi jarak sumber suara horizontal dari drone (dalam meter)
- **Arah titik**: Arah datang suara (proyeksi ke bidang XY)
- **Lingkaran konsentris**: Skala jarak (setiap lingkaran = N meter)

### Interpretasi Hasil

| Kondisi Hasil | Interpretasi | Tindakan |
|---|---|---|
| Semua event Valid, cluster size besar | Estimasi posisi dipercaya | Data dapat dilaporkan |
| Beberapa event Valid, beberapa Failed | Deteksi sebagian — mungkin SNR rendah | Laporkan event valid saja |
| Semua event Failed | Tidak ada solusi konsisten | Cek posisi mikrofon, coba turunkan cluster EPS |
| 0 events | Tidak ada suara terdeteksi | Cek threshold deteksi; mungkin terlalu tinggi |
| Posisi anomali (sangat jauh/tidak masuk akal) | Kemungkinan noise atau posisi mikrofon salah | Verifikasi koordinat mikrofon |
