"""
Ground Unit — Entry Point

Cara menjalankan (dari direktori manapun):
    python refactored/darat/main.py

Atau dari dalam direktori refactored/darat/:
    python main.py
"""

import sys
import os

# Tambahkan direktori 'refactored/' ke sys.path agar 'darat' bisa di-import sebagai package.
# Ini diperlukan karena app.py dan modul lain menggunakan relative imports (from .config import ...).
_this_dir = os.path.dirname(os.path.abspath(__file__))          # .../refactored/darat
_refactored_dir = os.path.dirname(_this_dir)                    # .../refactored
if _refactored_dir not in sys.path:
    sys.path.insert(0, _refactored_dir)

from darat.app import main  # noqa: E402 (import setelah sys.path setup)

if __name__ == "__main__":
    main()
