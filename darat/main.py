"""
Miss Distance Indicator — Ground Control Station
Entry point: python -m darat.main  (or  python darat/main.py)
"""

import sys
import os

# Ensure project root is on path when run as script
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtGui import QFont
    from darat.ui.dashboard import MainDashboard

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
    font = QFont("JetBrains Mono", 10)
    font.setStyleHint(QFont.StyleHint.Monospace)
    app.setFont(font)

    window = MainDashboard()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
