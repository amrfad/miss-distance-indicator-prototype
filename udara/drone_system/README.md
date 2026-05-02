# Drone Audio Detection & TDOA System

Sistem ini adalah "otak" audio untuk drone yang bertugas mendeteksi suara tembakan atau proyektil (Miss Distance Indicator). Sistem ini berjalan di Raspberry Pi 5 dan berkomunikasi dengan Ground Station untuk menerima perintah dan mengirimkan hasil analisis.

## 🎯 Apa yang Sistem Ini Lakukan?

Secara sederhana, sistem ini melakukan 5 hal utama:
1.  **Merekam Audio**: Menggunakan audio recorder eksternal (Zoom H8 atau H6 Essential) untuk merekam suara lingkungan sekitar drone.
2.  **Membersihkan Suara**: Menghilangkan noise angin dan motor drone agar suara target lebih jelas.
3.  **Mendeteksi Event**: Mencari lonjakan suara tiba-tiba yang kemungkinan adalah suara tembakan.
4.  **Menghitung Lokasi (TDOA)**: Menghitung perbedaan waktu kedatangan suara antar mikrofon untuk menentukan arah sumber suara.
5.  **Lapor ke Ground**: Mengirimkan data hasil deteksi ke operator di darat.

## 🛠️ Perangkat Keras yang Dibutuhkan

*   **Raspberry Pi 5**: Sebagai komputer utama.
*   **Zoom H8 / H6 Essential**: Sebagai antarmuka mikrofon (Audio Interface).
*   **4x Mikrofon**: Disusun dalam konfigurasi tertentu (misal: tetrahedron atau persegi).
*   **Koneksi Serial (UART)**: Untuk komunikasi dengan Ground Station (menggunakan USB-to-TTL atau telemetry radio).

## 🚀 Cara Menjalankan

### 1. Persiapan Awal
Pastikan semua kabel terpasang:
*   Zoom Recorder terhubung ke USB Raspberry Pi.
*   (ONLINE mode) Modul Serial terhubung ke port USB/GPIO Raspberry Pi.

### 2. Pilih Mode Operasi

Edit file `config.py` dan set:
```python
# OFFLINE mode - kontrol dari keyboard (untuk testing)
OPERATION_MODE = "OFFLINE"

# ONLINE mode - kontrol dari serial/ground station
OPERATION_MODE = "ONLINE"
```

### 3. Jalankan Program

**Mode OFFLINE (Keyboard Control):**
```bash
cd "Untuk di Udara"
python3 run_drone_system.py
```
Kemudian gunakan keyboard:
- `s` - Start Recording
- `p` - Stop Recording and Process
- `t` - Get Status
- `i` - System Info
- `q` - Quit

**Mode ONLINE (Serial Control):**
```bash
cd "Untuk di Udara"
python3 run_drone_system.py
```
Sistem akan menunggu perintah dari Ground Station via serial.

## 📡 Komunikasi dengan Ground Station (ONLINE Mode)

Sistem ini dikendalikan sepenuhnya dari darat melalui Serial Port. Berikut adalah perintah yang bisa dikirim:

| Perintah | Fungsi |
| :--- | :--- |
| `START_REC` | **Mulai Merekam**. Drone akan mulai menyimpan audio. |
| `STOP_REC` | **Stop & Proses**. Drone berhenti merekam, lalu otomatis memproses audio, mendeteksi event, menghitung TDOA, dan mengirim hasil. |
| `STATUS` | Mengecek apakah drone sedang merekam atau diam (IDLE). |
| `INFO` | Meminta informasi status sistem (kesehatan device, storage, dll). |

### Contoh Alur Kerja:
1.  Operator mengirim `START_REC`.
2.  Drone membalas `OK:Recording started...`.
3.  (Drone terbang dan merekam).
4.  Operator mengirim `STOP_REC`.
5.  Drone membalas `OK:Processing...`.
6.  Drone melakukan filtering, deteksi, dan perhitungan TDOA.
7.  Drone mengirimkan file `session_tdoa.json` berisi hasil perhitungan ke Ground Station.

## 📂 Hasil Output (Data)

Setiap kali perekaman selesai, sistem membuat folder baru di `drone_recordings/` dengan nama unik (timestamp).

Isi folder tersebut:
*   `raw_12ch.wav`: File rekaman mentah (semua channel).
*   `session_events.json`: Daftar event yang terdeteksi (detik ke berapa, durasi, dll).
*   `session_tdoa.json`: Hasil perhitungan TDOA antar mikrofon untuk setiap event.
*   **Folder `event_1`, `event_2`, dst**: Berisi potongan audio khusus untuk event tersebut (sudah dibersihkan/denoised).

### Contoh Isi `session_tdoa.json`:
File ini yang dikirim ke Ground Station untuk diolah menjadi koordinat lokasi.
```json
{
  "session_id": "session_20251128_...",
  "events": [
    {
      "event_number": 1,
      "tdoa": {
        "mic0-mic1": 0.00012,
        "mic0-mic2": -0.00045,
        "mic0-mic3": 0.00008,
        ...
      }
    }
  ]
}
```

## ⚙️ Konfigurasi (Untuk Developer)

Pengaturan sistem ada di file `drone_system/config.py`. Beberapa hal penting yang bisa diubah:

*   **`ACTIVE_PROFILE`**: Pilih `"H8"` atau `"H6E"` sesuai alat yang dipakai.
*   **`SERIAL_PORT`**: Port komunikasi (default `/dev/ttyUSB0`).
*   **`EVENT_PADDING_SEC`**: Berapa detik audio tambahan yang diambil sebelum dan sesudah event (default 0.25s).
*   **`NORMALIZE`**: Set `True` agar audio tidak kekecilan/clipping (penting untuk Zoom H6E 32-bit float).

## 🔧 Troubleshooting

*   **Error "Device not found"**: Cek koneksi USB Zoom Recorder. Pastikan mode di Zoom sudah di-set ke "Audio Interface".
*   **Error Serial**: Pastikan baudrate di Ground Station sama dengan di `config.py` (default 230400).
*   **Audio Kosong/Silent**: Cek gain/volume di Zoom Recorder.

---
*Dibuat untuk Proyek Miss Distance Indicator - 2025*