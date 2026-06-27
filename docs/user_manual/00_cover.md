# Miss Distance Indicator (MDI)
# User Manual
**Versi:** 1.0
**Tanggal:** 27 Juni 2026
**Bahasa:** Bahasa Indonesia

---

## Daftar Isi

| No. | Bab | Halaman |
|---|---|---|
| 1 | [Pendahuluan](01_introduction.md) | — |
| 1.1 | Gambaran Umum Sistem | — |
| 1.2 | Arsitektur Sistem | — |
| 1.3 | Alur Data Keseluruhan | — |
| 1.4 | Tujuan Dokumen | — |
| 1.5 | Target Pembaca | — |
| 1.6 | Prasyarat Sistem | — |
| 2 | [Memulai Sistem](02_getting_started.md) | — |
| 2.1 | Peringatan dan Perhatian Keselamatan | — |
| 2.2 | Persyaratan Sistem | — |
| 2.3 | Instalasi Ground Station | — |
| 2.4 | Instalasi Drone System di Raspberry Pi | — |
| 2.5 | Menjalankan Ground Station | — |
| 2.6 | Menjalankan Drone System | — |
| 2.7 | Menutup Sistem dengan Benar | — |
| 3 | [Panduan Hardware dan Pemasangan](03_hardware_wiring.md) | — |
| 3.1 | Daftar Hardware yang Dibutuhkan | — |
| 3.2 | Konfigurasi Zoom Recorder | — |
| 3.3 | Konfigurasi Mikrofon | — |
| 3.4 | Diagram Koneksi Keseluruhan | — |
| 3.5 | Konfigurasi Koneksi Serial | — |
| 3.6 | Verifikasi Hardware Sebelum Operasi | — |
| 4 | [Panduan Antarmuka Pengguna — Ground Station](04_ground_station_ui.md) | — |
| 4.1 | Tampilan Umum Aplikasi | — |
| 4.2 | Tab CONFIG — Konfigurasi Sistem | — |
| 4.3 | Tab COMMAND — Kontrol Perekaman | — |
| 4.4 | Tab PROCESS — Pemrosesan TDOA | — |
| 4.5 | Tab VISUALIZE — Visualisasi Hasil | — |
| 5 | [Sistem Drone (Subsistem Udara)](05_drone_system.md) | — |
| 5.1 | Gambaran Umum | — |
| 5.2 | Mode Operasi | — |
| 5.3 | Perintah yang Dapat Diterima | — |
| 5.4 | Pipeline Pemrosesan Audio | — |
| 5.5 | Output yang Dihasilkan | — |
| 5.6 | REST API Konfigurasi Drone | — |
| 5.7 | Mengubah Konfigurasi Drone | — |
| 5.8 | Memantau Log Drone System | — |
| 6 | [Prosedur Operasional Standar (SOP)](06_workflow_sop.md) | — |
| 6.1 | SOP-01: Setup Awal (Pertama Kali) | — |
| 6.2 | SOP-02: Operasi Misi Harian | — |
| 6.3 | SOP-03: Pengujian Sistem di Darat (OFFLINE) | — |
| 6.4 | SOP-04: Recovery Setelah Kehilangan Koneksi | — |
| 6.5 | SOP-05: Interpretasi Hasil Visualisasi | — |
| 7 | [Referensi Konfigurasi](07_configuration_reference.md) | — |
| 7.1 | Legenda | — |
| 7.2 | Konfigurasi Drone (Raspberry Pi) | — |
| 7.3 | Konfigurasi Ground Station | — |
| 7.4 | Lokasi File Konfigurasi | — |
| 7.5 | Rekomendasi Pengaturan Per Kondisi | — |
| 8 | [Ekstensi Kustom](08_custom_extensions.md) | — |
| 8.1 | Custom SSL Method (Ground Station) | — |
| 8.2 | Custom Audio Filter (Drone System) | — |
| 9 | [Format File Output](09_output_data_format.md) | — |
| 9.1 | Struktur Folder Sesi Rekaman | — |
| 9.2 | File: raw_12ch.wav | — |
| 9.3 | File: detected_events.csv | — |
| 9.4 | File: session_events.json | — |
| 9.5 | File: session_tdoa.json | — |
| 9.6 | File Audio Per-Event | — |
| 9.7 | File: *_results.txt (Output Ground Station) | — |
| 9.8 | Perbedaan session_events.json vs session_tdoa.json | — |
| 10 | [Troubleshooting dan Dukungan](10_troubleshooting.md) | — |
| 10.1 | Tabel Error Umum | — |
| 10.2 | Diagnostic Checklist | — |
| 10.3 | Cara Mendapatkan Log untuk Dilaporkan | — |
| 10.4 | Kontak Dukungan | — |
| A | [Appendix A: Daftar Perubahan Dokumen](appendix.md) | — |
| B | [Appendix B: Glossary](appendix.md) | — |
| C | [Appendix C: Daftar Dokumen Referensi](appendix.md) | — |

---

## Daftar Gambar

| No. | Judul Gambar | Bab |
|---|---|---|
| 1 | Tampilan Awal Aplikasi Ground Station | 2.5 |
| 2 | Diagram Koneksi Hardware MDI | 3.4 |
| 3 | Mode Audio Interface pada Zoom H8 | 3.2 |
| 4 | Koneksi GPIO Raspberry Pi ke USB-to-TTL | 3.5 |
| 5 | Tampilan Umum GUI Ground Station | 4.1 |
| 6 | Sub-tab Config Raspberry Pi | 4.2.1 |
| 7 | Sub-tab Config Ground Station — Microphone Positions | 4.2.2 |
| 8 | Tab Command — Grid Tombol dan Status Panel | 4.3 |
| 9 | Tab Process — Daftar File dan Log Output | 4.4 |
| 10 | Tab Visualize — 3D Tactical View | 4.5.2 |
| 11 | Tab Visualize — 2D Radar View | 4.5.3 |

---

## Daftar Tabel

| No. | Judul Tabel | Bab |
|---|---|---|
| 1 | Hardware yang Dibutuhkan | 3.1 |
| 2 | Posisi Default Mikrofon | 3.3 |
| 3 | Parameter Konfigurasi Drone: Mode Operasi | 7.2 |
| 4 | Parameter Konfigurasi Drone: Audio | 7.2 |
| 5 | Parameter Konfigurasi Drone: Deteksi Event | 7.2 |
| 6 | Parameter Konfigurasi Drone: Noise Reduction | 7.2 |
| 7 | Parameter Konfigurasi Drone: TDOA / GCC-PHAT | 7.2 |
| 8 | Parameter Konfigurasi Drone: Serial & Output | 7.2 |
| 9 | Parameter Konfigurasi Ground Station | 7.3 |
| 10 | Tabel Error: Koneksi Serial | 10.1.1 |
| 11 | Tabel Error: Perekaman Audio | 10.1.2 |
| 12 | Tabel Error: Pengiriman JSON | 10.1.3 |
| 13 | Tabel Error: Pemrosesan TDOA | 10.1.4 |
| 14 | Tabel Error: Konfigurasi | 10.1.5 |
| 15 | Tabel Error: Visualisasi | 10.1.6 |
| 16 | Kontak Dukungan | 10.4 |
| 17 | Glossary | Appendix B |
| 18 | Daftar Dokumen Referensi | Appendix C |
| 19 | Daftar Perubahan Dokumen | Appendix A |

---

## Informasi Dokumen

| Atribut | Nilai |
|---|---|
| Judul | Miss Distance Indicator (MDI) — User Manual |
| Versi | 1.0 |
| Tanggal Penerbitan | 27 Juni 2026 |
| Bahasa | Bahasa Indonesia |
| Status | Draft Pertama |
| Penulis | — |
| Reviewer | — |
