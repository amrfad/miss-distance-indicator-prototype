"""
SSL Registry — Plugin System untuk Metode Sound Source Localization

Modul ini bertugas:
  1. Memuat (load) metode-metode built-in dari paket darat/builtin_ssl/
  2. Memuat metode-metode custom dari folder eksternal (di luar executable)
  3. Menyediakan API terpusat untuk UI dan prosesor TDOA

Kontrak Setiap Metode SSL:
  - Harus mengekspos fungsi `solve(event_data, mic_positions, config) -> tuple`
  - Harus mengekspos konstanta `DISPLAY_NAME: str`
  - Nilai kembalian:  (estimated_pos, cluster_size, clusters_info)
    - estimated_pos : list/tuple [x, y, z] atau None
    - cluster_size  : int atau None (jika metode tidak menggunakan clustering)
    - clusters_info : list of str atau None
"""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from typing import Callable, Dict, Optional

# ─────────────────────────────────────────────────────────────────────────────
# Struktur data internal
# ─────────────────────────────────────────────────────────────────────────────

class MethodEntry:
    """Representasi satu metode SSL yang terdaftar."""

    def __init__(self, key: str, display_name: str, solve_fn: Callable, source: str):
        self.key = key             # identifier unik (e.g. "bucher_misra")
        self.display_name = display_name
        self.solve = solve_fn
        self.source = source       # "builtin" atau "custom"

    def __repr__(self) -> str:
        return f"<MethodEntry key={self.key!r} source={self.source!r}>"


# ─────────────────────────────────────────────────────────────────────────────
# Registry (singleton)
# ─────────────────────────────────────────────────────────────────────────────

_registry: Dict[str, MethodEntry] = {}

# Urutan tampilan default: nama key built-in yang harus muncul pertama
_BUILTIN_ORDER = ["rotating_multilat_2d", "nlls_2d", "chan_ho_2d", "bucher_misra", "chan_ho", "pivot", "consensus", "density_consensus", "rotating_multilat"]

# Nama modul built-in yang diketahui beserta package-nya
_BUILTIN_MODULES = {
    "rotating_multilat_2d": "darat.localization.builtin_ssl.rotating_multilat_2d",
    "nlls_2d": "darat.localization.builtin_ssl.nlls_2d",
    "chan_ho_2d": "darat.localization.builtin_ssl.chan_ho_2d",
    "bucher_misra": "darat.localization.builtin_ssl.bucher_misra",
    "chan_ho":       "darat.localization.builtin_ssl.chan_ho",
    "pivot":         "darat.localization.builtin_ssl.pivot",
    "consensus":     "darat.localization.builtin_ssl.consensus",
    "density_consensus": "darat.localization.builtin_ssl.density_consensus",
    "rotating_multilat": "darat.localization.builtin_ssl.rotating_multilat",
}


def _load_module_safe(module_name: str, file_path: Optional[str] = None) -> Optional[object]:
    """
    Muat modul Python secara aman.
    - Jika file_path diberikan: gunakan importlib.util (untuk custom external).
    - Jika tidak: gunakan import biasa (untuk built-in).
    """
    try:
        if file_path:
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None:
                return None
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        else:
            return importlib.import_module(module_name)
    except Exception as exc:
        print(f"[SSL Registry] Gagal memuat modul '{module_name}': {exc}")
        return None


def _register(key: str, mod: object, source: str) -> bool:
    """
    Validasi kontrak dan daftarkan metode dari modul.
    Returns True jika berhasil.
    """
    solve_fn = getattr(mod, "solve", None)
    if not callable(solve_fn):
        print(f"[SSL Registry] Modul '{key}' tidak memiliki fungsi 'solve'. Dilewati.")
        return False

    display_name = getattr(mod, "DISPLAY_NAME", key)

    _registry[key] = MethodEntry(
        key=key,
        display_name=display_name,
        solve_fn=solve_fn,
        source=source,
    )
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Fungsi publik
# ─────────────────────────────────────────────────────────────────────────────

def load_builtin_methods() -> None:
    """Muat semua metode built-in dari paket darat.builtin_ssl."""
    for key, module_path in _BUILTIN_MODULES.items():
        mod = _load_module_safe(module_path)
        if mod is None:
            continue
        if _register(key, mod, source="builtin"):
            display = getattr(mod, "DISPLAY_NAME", key)
            print(f"[SSL Registry] Built-in dimuat: '{display}' (key={key})")


def load_custom_methods(folder_path: str) -> None:
    """
    Muat semua file .py dari folder eksternal sebagai metode custom.
    Dipanggil saat startup dengan path folder di sebelah executable (atau cwd).

    Args:
        folder_path: Path absolut ke folder berisi custom SSL modules.
    """
    folder = Path(folder_path)
    if not folder.is_dir():
        return

    for py_file in sorted(folder.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        key = f"custom_{py_file.stem}"
        mod = _load_module_safe(key, str(py_file))
        if mod is None:
            continue
        if _register(key, mod, source="custom"):
            display = getattr(mod, "DISPLAY_NAME", key)
            print(f"[SSL Registry] Custom dimuat: '{display}' (key={key}, file={py_file.name})")


def reload_custom_methods(folder_path: str) -> None:
    """
    Hapus semua metode custom yang sudah terdaftar, lalu muat ulang.
    Dipanggil setelah user menambah file baru melalui UI.
    """
    global _registry
    _registry = {k: v for k, v in _registry.items() if v.source != "custom"}
    load_custom_methods(folder_path)


def get_available_methods() -> list[tuple[str, str]]:
    """
    Kembalikan daftar (key, display_name) yang tersedia, terurut:
    - Built-in sesuai _BUILTIN_ORDER
    - Custom secara alfabetis

    Returns:
        list of (key, display_name)
    """
    ordered = []

    # Built-in dulu, sesuai urutan
    for key in _BUILTIN_ORDER:
        if key in _registry:
            ordered.append((key, _registry[key].display_name))

    # Built-in yang tidak ada di _BUILTIN_ORDER (jika ada tambahan)
    for key, entry in _registry.items():
        if entry.source == "builtin" and key not in _BUILTIN_ORDER:
            ordered.append((key, entry.display_name))

    # Custom
    custom = [(k, e.display_name) for k, e in sorted(_registry.items()) if e.source == "custom"]
    ordered.extend(custom)

    return ordered


def get_method(key: str) -> Optional[MethodEntry]:
    """
    Ambil MethodEntry berdasarkan key.

    Args:
        key: Identifier metode (e.g. "bucher_misra" atau "custom_mymethod")

    Returns:
        MethodEntry atau None jika tidak ditemukan
    """
    return _registry.get(key)


def get_default_key() -> str:
    """Kembalikan key metode default (Bucher-Misra)."""
    return "bucher_misra"


def get_custom_folder(app_dir: Optional[str] = None) -> str:
    """
    Tentukan path folder untuk custom SSL methods.

    Urutan prioritas:
    1. Folder 'custom_ssl_methods' di sebelah executable (untuk distribusi .exe)
    2. Folder 'custom_ssl_methods' di working directory saat ini
    3. Buat folder baru di working directory jika belum ada

    Args:
        app_dir: Opsional, direktori aplikasi (mis. dari sys._MEIPASS atau dirname(exe))

    Returns:
        Path absolut ke folder custom SSL methods
    """
    # Dalam mode bundled PyInstaller
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
    else:
        exe_dir = Path.cwd()

    folder = exe_dir / "custom_ssl_methods"
    folder.mkdir(exist_ok=True)
    return str(folder)


def initialize(app_dir: Optional[str] = None) -> str:
    """
    Inisialisasi registry: load built-in + custom.
    Dipanggil sekali saat aplikasi startup.

    Args:
        app_dir: Direktori root aplikasi (opsional).

    Returns:
        Path folder custom methods yang digunakan.
    """
    load_builtin_methods()
    custom_folder = get_custom_folder(app_dir)
    load_custom_methods(custom_folder)
    print(f"[SSL Registry] {len(_registry)} metode terdaftar total.")
    return custom_folder
