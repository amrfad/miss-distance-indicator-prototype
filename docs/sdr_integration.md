# Integrasi MDI dengan SDR FDD

Pada mode SDR, GUI Darat tetap aplikasi MDI (PySide6). Di tiap perangkat,
controller radio berjalan sebagai **proses terpisah** dalam interpreter
radioconda (PyQt5/GNU Radio/UHD). Komunikasi aplikasi dan daemon hanya melalui
TCP lokal `127.0.0.1`: Ground port 5005, Air port 5006. Command Ground→Air dan
JSON TDOA Air→Ground tetap melalui USRP B210, **bukan Ethernet atau TCP antarperangkat**.

## Prasyarat

- Submodule `sdr-mdi` telah diinisialisasi dan memuat
  `ground_unit_headless.py` serta `air_unit_headless.py`.
- B210, UHD, GNU Radio, LoRa SDR, dan PyQt5 tersedia dalam radioconda **di
  kedua perangkat**. Interpreter MDI tetap milik lingkungan aplikasi sendiri.
- Frekuensi, SF, bandwidth, antenna, dan gain kedua unit disamakan melalui
  konfigurasi SDR (lihat `sdr-mdi/docs/CONFIGURATION.md`).

## Konfigurasi

1. Pada konfigurasi Darat set `comm_backend=SDR` dan `sdr_python_path` ke
   interpreter radioconda pada laptop. Path dapat diisi dari layar konfigurasi
   laptop (kolom **SDR Python**). Biarkan `sdr_ipc_port=5005` kecuali port itu
   sudah dipakai proses lain.
2. Pada konfigurasi Udara set `operation_mode=SDR`, `sdr_python_path` ke
   interpreter radioconda pada Raspberry Pi, dan bila perlu
   `sdr_air_ipc_port=5006`. Restart aplikasi Udara setelah mengganti mode.
3. Jalankan aplikasi MDI seperti biasa. Tombol CONNECT pada GUI Ground
   menjalankan daemon Ground; proses Udara menjalankan daemon Air.
4. `START_REC` dari GUI → RF START → Air memulai rekaman. File chunk bernama
   `tdoa.json` di direktori sesi rekaman dikirim berurutan melalui FDD.
   `STOP_REC` → Air menyelesaikan audio/chunk terakhir → tetap mengirim
   antrean data → kembali IDLE. File JSON yang direkonstruksi muncul di
   `drone_recordings` pada laptop dan ditampilkan di halaman Command.

Mode awal menggunakan `smdi` (tanpa redundansi SDEV) dan data plane
best-effort: `sent_unconfirmed` pada Air **bukan** bukti Ground menerima semua
event. Evaluasi hasil melalui `_reception.status`, `events_recovered` dan
`events_expected` di JSON hasil Ground. `sdr_mock_mode` hanya menguji IPC dan
controller lokal; tidak mensimulasikan radio dua perangkat atau penerimaan
end-to-end.

Konfigurasi via REST/Ethernet yang sudah ada **tidak diubah**. Jika Ground
berjalan sebagai executable PyInstaller, pastikan submodule/daemon serta
interpreter radioconda terpasang terpisah di lokasi yang dirujuk launcher.
