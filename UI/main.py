# UI/main.py
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from UI.dashboard import MainDashboard


def _load_stylesheet(app: QApplication) -> None:
    """Load the MDI QSS theme from UI/styles/mdi_theme.qss."""
    qss_path = os.path.join(os.path.dirname(__file__), "styles", "mdi_theme.qss")
    if os.path.exists(qss_path):
        with open(qss_path, encoding="utf-8") as f:
            app.setStyleSheet(f.read())
    else:
        print(f"[WARN] Theme file not found: {qss_path}")


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("MDI Ground Control")
    app.setOrganizationName("MDI Project")

    _load_stylesheet(app)

    window = MainDashboard()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
