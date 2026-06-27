# Appendix

---

## Appendix A: Daftar Perubahan Dokumen

Tabel berikut mencatat riwayat perubahan dokumen User Manual ini.

| Nomor Versi | Tanggal | Penulis | Deskripsi Perubahan |
|---|---|---|---|
| 1.0 | 27/06/2026 | — | Penerbitan pertama |
| | | | |
| | | | |

---

## Appendix B: Glossary

Istilah-istilah teknis yang digunakan dalam dokumen ini, disusun secara alfabetis.

| Istilah | Akronim | Definisi |
|---|---|---|
| Arecord | — | Utilitas perekam audio bawaan Linux (ALSA). Digunakan drone untuk merekam dari Zoom Recorder via USB. |
| Audio Interface | — | Mode operasi pada Zoom H8/H6E yang menjadikannya perangkat audio input/output untuk komputer. |
| Baudrate | — | Kecepatan transmisi data pada komunikasi serial, diukur dalam bits per detik (bps). Ground station dan drone harus menggunakan baudrate yang sama. Default: 230400 bps. |
| Bucher-Misra | — | Algoritma estimasi posisi 3D sumber suara berbasis data TDOA. Membutuhkan minimal 4 mikrofon (stasiun). Menghasilkan satu set solusi kandidat yang kemudian difilter menggunakan clustering. |
| Channel | — | Saluran audio individual dari satu mikrofon. Zoom H8 dapat merekam hingga 12 channel secara simultan. |
| Cluster / Clustering | — | Proses pengelompokan solusi posisi kandidat dari Bucher-Misra. Solusi yang berdekatan (dalam radius Cluster EPS) dikelompokkan, dan kelompok terbesar dipilih sebagai estimasi posisi akhir. |
| Cluster EPS | — | Epsilon (ε) pada algoritma clustering — jarak maksimum (dalam meter) antara dua titik agar dianggap satu kelompok. Default: 1.0 m. |
| COM Port | — | Nama port serial pada Windows (contoh: COM3, COM7). Setara dengan `/dev/ttyUSB0` pada Linux. |
| Cross-Correlation | — | Operasi matematis untuk mengukur kemiripan antara dua sinyal audio pada berbagai offset waktu. Digunakan oleh GCC-PHAT untuk menemukan TDOA antar pasangan mikrofon. |
| Detect Ratio | — | Ambang batas sensitivitas deteksi event suara. Nilai lebih rendah = lebih sensitif (lebih mudah terdeteksi). Default: 0.20. |
| Event | — | Satu kejadian suara tiba-tiba yang terdeteksi oleh sistem drone, seperti suara tembakan atau ledakan. Data setiap event berisi timestamp, durasi, dan nilai TDOA. |
| Filter Ratio | — | Ambang batas untuk memfilter event dengan kualitas sinyal rendah setelah deteksi. Nilai lebih tinggi = lebih ketat. Default: 0.40. |
| GCC-PHAT | Generalized Cross-Correlation with Phase Transform | Algoritma perhitungan TDOA yang robust terhadap noise dan reverberasi. Diterapkan pada domain frekuensi menggunakan Phase Transform (PHAT) weighting. |
| Ground Station | — | Subsistem yang berjalan di laptop/PC operator di darat. Mengendalikan drone, menerima data JSON, dan memproses serta memvisualisasikan hasil TDOA. |
| JSON | JavaScript Object Notation | Format file data teks terstruktur. Digunakan untuk mengirimkan hasil TDOA dari drone ke Ground Station (`session_tdoa.json`). |
| MDI | Miss Distance Indicator | Sistem yang mengestimasi jarak lewat (miss distance) dari proyektil terhadap drone, berbasis deteksi dan lokalisasi suara. |
| Mikrofon (Mic) | — | Sensor penangkap suara. Sistem MDI menggunakan 4–6 mikrofon yang dipasang pada posisi tertentu di sekitar drone. |
| OFFLINE Mode | — | Mode operasi drone tanpa koneksi serial ke Ground Station. Drone dikontrol menggunakan keyboard secara langsung. Digunakan untuk testing di darat. |
| ONLINE Mode | — | Mode operasi drone dengan koneksi serial aktif ke Ground Station. Semua perintah dikirim dari Ground Station. |
| Operation Mode | — | Pilihan mode operasi drone: `ONLINE` (dikontrol serial) atau `OFFLINE` (dikontrol keyboard). Memerlukan restart drone untuk berlaku. |
| Raspberry Pi | RPi | Komputer mini berbasis Linux yang dipasang di drone. Menjalankan subsistem Udara (Drone System). |
| REST API | Representational State Transfer API | Antarmuka pemrograman berbasis HTTP yang digunakan Ground Station untuk mengirim dan menerima konfigurasi dari drone secara nirkabel (via Wi-Fi). |
| RMS | Root Mean Square | Ukuran energi rata-rata sinyal audio. Digunakan oleh Event Detector untuk mendeteksi lonjakan suara mendadak. |
| Serial Port | — | Antarmuka komunikasi data satu arah per waktu, digunakan untuk menghubungkan Ground Station dengan drone. Pada Windows: COM3, COM7, dst. Pada Linux: /dev/ttyUSB0, dst. |
| Session | — | Satu sesi perekaman penuh, dari `START_REC` hingga `STOP_REC`. Setiap sesi menghasilkan folder dan file output sendiri. |
| Sound Source Localization | SSL | Proses estimasi posisi sumber suara dalam ruang tiga dimensi berdasarkan data TDOA dari beberapa mikrofon. |
| Spectral Gating | — | Metode noise reduction yang menghapus komponen frekuensi di bawah ambang batas (noise floor). Filter bawaan default sistem MDI. |
| TDOA | Time Difference of Arrival | Selisih waktu kedatangan suara dari sumber yang sama antara dua mikrofon. Nilainya dalam satuan detik. Contoh: TDOA mic0-mic1 = 0.00012 s. |
| UART | Universal Asynchronous Receiver-Transmitter | Protokol komunikasi serial yang digunakan pada koneksi fisik antara Ground Station dan drone. |
| USB-to-TTL | — | Konverter sinyal USB ke UART (TTL level). Digunakan untuk menghubungkan port USB laptop dengan GPIO/UART Raspberry Pi. |
| Wiener Filter | — | Metode noise reduction berbasis statistik spektrum sinyal. Salah satu filter bawaan alternatif di sistem MDI. |
| Zoom H8 | — | Perekam audio portabel dengan kemampuan 12 channel dan mode Audio Interface. Digunakan sebagai antarmuka mikrofon utama di sistem MDI. |
| Zoom H6E | — | Varian Zoom Recorder dengan 6 channel. Alternatif dari H8. Mendukung 4 mikrofon. |

---

## Appendix C: Daftar Dokumen Referensi

| Nama Dokumen | Lokasi | Tanggal |
|---|---|---|
| AGENTS.md — Panduan Developer MDI | `Prototype/AGENTS.md` | 2026 |
| README Drone System | `udara/drone_system/README.md` | 2025 |
| Panduan Custom SSL Method | `darat/README_CUSTOM_SSL.md` | 2026 |
| Panduan Custom Audio Filter | `udara/README_CUSTOM_FILTER.md` | 2026 |
| Communication Contract Config-UI | `Prototype/communication-contract_config-ui.md` | 2026 |
| Zoom H8 Product Manual | https://zoomcorp.com | — |
| Raspberry Pi 5 Documentation | https://www.raspberrypi.com/documentation/ | — |
