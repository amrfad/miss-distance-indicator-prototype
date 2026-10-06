# MDI Ground Station Demo (2D Sound Source Localization)

Aplikasi Ground Station mandiri (terpisah dari `darat/`) yang disederhanakan khusus untuk demonstrasi Miss Distance Indicator (MDI) dengan arsitektur UI, layout, dan tema taktis yang **identik dengan Ground Station `darat/`**.

---

## 🌟 Fitur Utama

1. **Desain Antarmuka Taktis Identik dengan Ground Station Darat:**
   - **Header Bar**: Tombol toggle sidebar hamburger (`☰`), judul MDI Ground Station (`DEMO 2D`), indikator status koneksi drone (● NOT CONNECTED / ● CONNECTED), dan jam digital real-time.
   - **Collapsible Sidebar**: Navigasi sidebar gelap (`#0b1220`) dengan tombol menu interaktif:
     - `📊 LIVE & RADAR`
     - `⚙ CONFIGURATION`
   - **Tactical 2D Phosphor Radar**: Layar radar polar militer berlatar phosphor green dengan ring jarak konsentris (5m, 10m, 15m, 20m), siluet pesawat drone di tengah, marker posisi mikrofon, blip target Miss Distance berwarna kuning/merah, serta scroll-wheel zoom dan koordinat target hover tooltip.
   - **Telemetry Card & Metric Bar**: Card metrik modern untuk `STATUS`, `METHOD`, `EVENTS`, `LAST CPA`, dan `MISS DISTANCE` (meter).
   - **Collapsible System Log**: Panel log sistem di bagian bawah dengan pewarnaan level log (INFO hijau, WARNING kuning, ERROR merah, DEBUG biru), tombol Clear, dan tombol Hide/Show.

2. **Khusus Lokalisasi 2D:**
   - **Rotating Multilateration 2D (5-Mic LOO Median)**: Linear Least Squares 2D dengan rotasi subset Leave-One-Out (LOO) dan agregasi median. Kebal outlier dan bebas akar imajiner.
   - **Chan-Ho WLS 2D (Ensemble + WLS)**: Two-Stage Weighted Least Squares 2D dengan clustering dan seleksi kluster berdasarkan residual TDOA minimum.

3. **Operasional & Utilitas:**
   - Kontrol serial penuh: tombol `CONNECT`, `DISCONNECT`, `START REC`, `STOP REC`, dan `STANDBY`.
   - Tombol **"📂 REPLAY JSON FILE..."** untuk simulasi dan demonstrasi offline tanpa hardware drone.
   - Tombol **"🗑 CLEAR RADAR"** untuk reset target blip.

---

## 🚀 Cara Menjalankan

Dari direktori root proyek:

```bash
python demo_ground/main.py
```

Atau dari dalam folder `demo_ground/`:

```bash
python main.py
```

---

## 📂 Struktur Direktori

```
demo_ground/
├── main.py                     ← Entry point aplikasi (memuat mdi_theme.qss)
├── config.json                 ← File konfigurasi default (bisa diubah via UI)
├── README.md                   ← Dokumentasi petunjuk penggunaan
├── assets/
│   └── plane.ply               ← 3D model siluet drone untuk radar
├── core/
│   ├── config_manager.py       ← Pengelola konfigurasi JSON
│   ├── json_receiver.py        ← Parser marker [START]/[END] & deduplikasi serial
│   └── serial_manager.py       ← Driver port serial USB
├── ssl_2d/
│   ├── chan_ho_2d.py           ← Algoritma Chan-Ho WLS 2D
│   └── rotating_multilat_2d.py ← Algoritma Rotating Multilateration 2D
└── ui/
    ├── dashboard.py            ← MainDashboard shell (Header + Sidebar + Splitter)
    ├── pages/
    │   ├── live_page.py        ← Halaman Radar 2D & Kontrol Serial
    │   └── config_page.py      ← Halaman Konfigurasi Form & Tabel Mic
    ├── widgets/
    │   ├── radar_2d_widget.py  ← Tactical Phosphor Radar 2D Display
    │   ├── log_panel.py        ← Collapsible System Log Panel
    │   └── mesh_loader.py      ← Loader siluet drone
    └── styles/
        ├── mdi_theme.qss       ← Tema taktis Ground Station (v3.1)
        └── icons/              ← Asset ikon antarmuka
```
