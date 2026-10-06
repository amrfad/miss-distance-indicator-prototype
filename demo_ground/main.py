"""
Entry Point: MDI Ground Station Demo (2D Sound Source Localization)
Mengadopsi arsitektur visual dan tema yang persis dengan Ground Station darat/.
"""

import sys
import os
from pathlib import Path

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
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR.parent) not in sys.path:
    sys.path.insert(0, str(BASE_DIR.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from demo_ground.core.config_manager import ConfigManager
from demo_ground.core.serial_manager import SerialManager
from demo_ground.core.json_receiver import JsonReceiver
from demo_ground.ui.dashboard import MainDashboard


def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Miss Distance Indicator — Ground Station Demo")
    app.setOrganizationName("MDI")

    # Load tactical stylesheet (mdi_theme.qss)
    qss_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "styles", "mdi_theme.qss")
    if os.path.exists(qss_path):
        try:
            with open(qss_path, "r", encoding="utf-8") as f:
                qss_text = f.read()
            icons_dir = os.path.join(os.path.dirname(qss_path), "icons").replace("\\", "/")
            qss_text = qss_text.replace('url("icons/', f'url("{icons_dir}/')
            app.setStyleSheet(qss_text)
            print(f"[INIT] Stylesheet loaded successfully from: {qss_path}")
        except Exception as e:
            print(f"[INIT] Warning: Failed to load stylesheet: {e}")

    # Set default font
    from PySide6.QtGui import QFont
    font = QFont("Inter")
    font.setStyleHint(QFont.StyleHint.SansSerif)
    font.setPointSize(10)
    app.setFont(font)

    # Core services
    config_manager = ConfigManager()

    window = MainDashboard(config_manager=config_manager)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
