"""
Miss Distance Indicator — Ground Control Station
Entry point: python -m darat.main  (or  python darat/main.py)
"""

import sys
import os
from tkinter import font

# Ensure project root is on path when run as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont
    from darat.ui.dashboard import MainDashboard
    from darat.network_setup import init_network

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
    qss_path = os.path.join(
        os.path.dirname(__file__), "ui", "styles", "mdi_theme.qss"
    )
    if os.path.exists(qss_path):
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())
            

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
