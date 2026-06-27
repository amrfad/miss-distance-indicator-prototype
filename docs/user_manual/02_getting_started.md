# Bab 2: Memulai Sistem

---

## 2.1 Peringatan dan Perhatian Keselamatan

> ⚠️ **PERINGATAN — Baca sebelum mengoperasikan sistem:**

- **Level audio:** Jangan atur gain Zoom Recorder terlalu tinggi saat pengujian di dalam ruangan untuk menghindari kerusakan mikrofon akibat suara keras yang tiba-tiba.
- **Koneksi serial (SIYI HM30):** Selalu pastikan baudrate Ground Station dan Drone **identik** (default: 230400 bps) sebelum menghubungkan. Baudrate yang tidak cocok tidak akan merusak hardware, tetapi komunikasi tidak akan berfungsi.
- **Shutdown yang benar:** Selalu hentikan proses Drone System dengan benar (Ctrl+C atau perintah stop) sebelum memutus power Raspberry Pi, agar file rekaman tidak korup.
- **Perizinan serial di Linux:** Pada Linux, port serial (`/dev/ttyUSB0`) memerlukan izin akses. Tambahkan user ke grup `dialout`:
  ```bash
  sudo usermod -a -G dialout $USER
  # Kemudian logout dan login ulang agar berlaku
  ```

---

## 2.2 Persyaratan Sistem

### Ground Station (Laptop / PC Operator)

| Komponen | Persyaratan Minimum |
|---|---|
| Sistem Operasi | Windows 10/11 (64-bit) atau Linux (Ubuntu 20.04+) |
| RAM | 4 GB (8 GB direkomendasikan) |
| Storage | 2 GB ruang kosong untuk instalasi + ruang untuk file rekaman |
| Python | 3.11 atau lebih baru (jika menjalankan dari source code) |
| Port | Minimal 1 port USB (untuk serial) |

**Dependensi Python Ground Station:**
```
PySide6
numpy
scipy
scikit-learn
matplotlib
noisereduce
requests
pyserial
```

### Drone System (Raspberry Pi)

| Komponen | Persyaratan |
|---|---|
| Hardware | Raspberry Pi 5 (4 GB atau 8 GB RAM) |
| Sistem Operasi | Raspberry Pi OS 64-bit (Debian Bookworm atau lebih baru) |
| Python | 3.11 atau lebih baru |
| Storage | SD Card minimal 16 GB (32 GB direkomendasikan) |
| USB | Minimal 2 port USB (1 untuk Zoom, 1 untuk serial/telemetri) |

**Dependensi Python Drone System:**
```
numpy
scipy
noisereduce (opsional — direkomendasikan)
pyserial
flask
soundfile
```

---

## 2.3 Instalasi Ground Station

### Opsi A: Dari File Distribusi (.exe)

Jika tersedia file distribusi `.exe` atau folder `dist/`:
1. Ekstrak folder distribusi ke lokasi yang diinginkan (contoh: `C:\MDI_Ground\`)
2. Jalankan `MDI_Ground.exe`
3. Tidak ada instalasi tambahan yang dibutuhkan

### Opsi B: Dari Source Code (Python)

1. **Pastikan Python 3.11+ terinstal:**
   ```
   python --version
   ```

2. **Clone atau copy folder `Prototype/` ke komputer Ground Station**

3. **Buat virtual environment (direkomendasikan):**
   ```bash
   cd Prototype/darat
   python -m venv .venv

   # Windows:
   .venv\Scripts\activate

   # Linux:
   source .venv/bin/activate
   ```

4. **Install dependensi:**
   ```bash
   pip install -r requirements.txt
   ```

   Atau menggunakan `uv` (lebih cepat):
   ```bash
   uv sync
   ```

5. **Verifikasi instalasi:**
   ```bash
   python -c "from PySide6.QtWidgets import QApplication; print('PySide6 OK')"
   ```

---

## 2.4 Instalasi Drone System di Raspberry Pi

### Langkah 1: Persiapkan Raspberry Pi OS

Pastikan Raspberry Pi sudah terinstal Raspberry Pi OS 64-bit. Update sistem:
```bash
sudo apt update && sudo apt upgrade -y
```

### Langkah 2: Install Python dan Dependensi Sistem

```bash
sudo apt install -y python3 python3-pip python3-venv alsa-utils
```

Verifikasi `arecord` tersedia:
```bash
arecord --version
```

### Langkah 3: Copy dan Setup Drone System

```bash
# Copy folder udara/ ke Raspberry Pi (via scp atau USB)
scp -r udara/ pi@10.99.99.2:~/mdi/

# Di Raspberry Pi:
cd ~/mdi/udara
python3 -m venv .venv
source .venv/bin/activate
pip install -r drone_system/requirements.txt
```

### Langkah 4: (Opsional) Setup Autostart sebagai Systemd Service

Agar Drone System otomatis berjalan saat Raspberry Pi dinyalakan:

```bash
# Salin file service
sudo cp mdi_drone.service /etc/systemd/system/

# Edit path di dalam file service sesuai lokasi instalasi
sudo nano /etc/systemd/system/mdi_drone.service

# Aktifkan dan mulai service
sudo systemctl daemon-reload
sudo systemctl enable mdi_drone.service
sudo systemctl start mdi_drone.service

# Cek status
sudo systemctl status mdi_drone.service
```

---

## 2.5 Menjalankan Ground Station

### Cara Menjalankan

**Dari file .exe (distribusi):**
- Double-click `MDI_Ground.exe`

**Dari source code:**
```bash
# Dari folder Prototype/
cd darat
python main.py
```

### Tampilan Awal

Saat pertama kali dibuka, Ground Station akan menampilkan jendela utama dengan:
- **Sidebar navigasi** di sebelah kiri (Config, Command, Process, Visualize)
- **Area konten** di tengah-kanan
- **Panel Log** di bagian bawah
- Aplikasi akan langsung menuju tab **Command** sebagai halaman awal

> 📸 **[PLACEHOLDER SCREENSHOT]** — *Screenshot tampilan awal aplikasi Ground Station. Tunjukkan sidebar, header "Miss Distance Indicator — Ground Control Station", dan tab Command yang aktif.*

---

## 2.6 Menjalankan Drone System

### Mode OFFLINE (Testing / Tanpa Koneksi Serial)

Mode ini untuk testing di darat tanpa menghubungkan serial ke Ground Station. Drone dikontrol dari keyboard secara langsung.

```bash
# Di Raspberry Pi (atau komputer yang menjalankan drone system):
cd ~/mdi/udara
source .venv/bin/activate

# Pastikan operation_mode = "OFFLINE" di konfigurasi
python run_drone_system.py
```

Setelah berjalan, gunakan keyboard:
| Tombol | Fungsi |
|---|---|
| `s` | Start Recording |
| `p` | Stop Recording dan proses |
| `t` | Cek Status sistem |
| `i` | Info sistem lengkap |
| `q` | Keluar |

### Mode ONLINE (Operasi Normal dengan Ground Station)

Mode ini digunakan saat operasi nyata. Drone menerima perintah dari Ground Station via serial.

```bash
# Di Raspberry Pi:
# Pastikan operation_mode = "ONLINE" dan serial_port sudah benar di konfigurasi
python run_drone_system.py
```

Sistem akan menampilkan pesan:
```
============================================================
DRONE AUDIO DETECTION SYSTEM — Continuous Streaming Mode
============================================================
Operation Mode: ONLINE
Serial Port: /dev/ttyUSB0
...
Waiting for commands from ground station...
Commands: START_REC | STOP_REC | STATUS
```

Sistem siap menerima perintah dari Ground Station.

### Menjalankan sebagai Systemd Service (Autostart)

Jika sudah dikonfigurasi sebagai service (lihat bagian 2.4):
```bash
# Cek status
sudo systemctl status mdi_drone.service

# Lihat log real-time
journalctl -u mdi_drone.service -f
```

---

## 2.7 Menutup Sistem dengan Benar

### Menutup Ground Station
- Klik tombol **X** pada jendela aplikasi, atau tekan `Alt + F4`
- Pastikan tidak ada sesi perekaman yang sedang aktif sebelum menutup

### Menutup Drone System
**Jika berjalan langsung di terminal:**
- Tekan `Ctrl + C` untuk menghentikan sistem dengan bersih
- Tunggu pesan `[SYSTEM] Shutdown complete` sebelum memutus power

**Jika berjalan sebagai service:**
```bash
sudo systemctl stop mdi_drone.service
```

> ⚠️ **Jangan langsung mencabut power Raspberry Pi** saat perekaman sedang berlangsung. Ini dapat menyebabkan file rekaman tidak tersimpan dengan benar.
