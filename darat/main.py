import sys
import os

# Ensure UTF-8 output encoding on Windows consoles
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure project root is on path when run as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont
    from darat.ui.dashboard import MainDashboard
    from darat.api.network_setup import init_network

    # Inisialisasi SSL Registry (metode kalkulasi TDOA)
    from darat.localization import ssl_registry
    _custom_folder = ssl_registry.initialize()
    print(f"[INIT] SSL Registry dimuat. Custom folder: {_custom_folder}")

    # Inisialisasi network auto-config sebelum GUI berjalan
    print("[INIT] Mempersiapkan Automasi Jaringan Darat...")
    if init_network():
        import time
        print("[INIT] Menunggu 2 detik agar adapter jaringan stabil...")
        time.sleep(2.0)

    app = QApplication(sys.argv)
    app.setApplicationName("Miss Distance Indicator")
    app.setOrganizationName("MDI")

    # Load stylesheet
    if getattr(sys, 'frozen', False):
        # Di dalam bundle PyInstaller
        base_dir = sys._MEIPASS
        qss_path = os.path.join(base_dir, "darat", "ui", "styles", "mdi_theme.qss")
    else:
        # Mode development biasa
        base_dir = os.path.dirname(os.path.abspath(__file__))
        qss_path = os.path.join(base_dir, "ui", "styles", "mdi_theme.qss")

    if os.path.exists(qss_path):
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                qss_text = f.read()
            icons_dir = os.path.join(os.path.dirname(qss_path), "icons").replace("\\", "/")
            qss_text = qss_text.replace('url("icons/', f'url("{icons_dir}/')
            app.setStyleSheet(qss_text)
            print(f"[INIT] Stylesheet loaded successfully from: {qss_path}")
        except Exception as e:
            print(f"[INIT] ERROR: Gagal membaca stylesheet di {qss_path}: {e}")
    else:
        print(f"[INIT] WARNING: Stylesheet tidak ditemukan di: {qss_path}")
            

    # Default font
    font = QFont("Inter")
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setPointSize(10)
    app.setFont(font)

    window = MainDashboard()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
