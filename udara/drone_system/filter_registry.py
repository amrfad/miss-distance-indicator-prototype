"""
Filter Registry — Plugin Registry untuk Audio Filtering
Mendukung built-in filters dan custom filters dari folder eksternal.

Cara kerja:
  1. Muat semua built-in filters dari builtin_filters/
  2. Scan folder custom_filters/ untuk filter tambahan (opsional)
  3. Sediakan get_method_class(key) yang mengembalikan Class (bukan instance)

Penggunaan di processor.py:
    from .filter_registry import get_method_class

    FilterClass = get_method_class("spectral_gating")
    method_params = cfg.get("filter_configs", {}).get("spectral_gating", {})
    filter_instance = FilterClass(**method_params)
    filtered_audio = filter_instance.apply(channel_audio, sample_rate)
"""

import os
import importlib
import importlib.util
import inspect
import sys
from typing import Optional, Type

from .base_filter import BaseAudioFilter
from .builtin_filters import BUILTIN_FILTER_MAP

# ── Konstanta ──────────────────────────────────────────────────────────
DEFAULT_METHOD = "spectral_gating"

# ── Internal registry dict {key: FilterClass} ──────────────────────────
_REGISTRY: dict[str, Type[BaseAudioFilter]] = {}
_INITIALIZED = False


def _initialize():
    """
    Inisialisasi registry sekali saja (lazy initialization).
    1. Daftarkan semua built-in filters yang tersedia (is_available() == True)
    2. Scan custom_filters/ jika folder tersebut ada
    """
    global _INITIALIZED
    if _INITIALIZED:
        return

    # 1. Daftarkan built-in filters
    for key, FilterClass in BUILTIN_FILTER_MAP.items():
        if FilterClass.is_available():
            _REGISTRY[key] = FilterClass
            print(f"[FILTER REGISTRY] [OK] Loaded built-in: '{key}' ({FilterClass.get_display_name()})")
        else:
            print(f"[FILTER REGISTRY] [SKIP] Not available: '{key}'")

    # 2. Scan custom_filters/ folder (opsional)
    _load_custom_filters()

    # Pastikan default tersedia
    if DEFAULT_METHOD not in _REGISTRY:
        # Fallback ke passthrough jika spectral_gating tidak tersedia
        from .builtin_filters.passthrough import PassthroughFilter
        _REGISTRY[DEFAULT_METHOD] = PassthroughFilter
        print(f"[FILTER REGISTRY] [WARN] Default '{DEFAULT_METHOD}' tidak tersedia, "
              f"fallback ke PassthroughFilter")

    _INITIALIZED = True
    print(f"[FILTER REGISTRY] Initialized dengan {len(_REGISTRY)} metode: {list(_REGISTRY.keys())}")


def _load_custom_filters():
    """
    Scan folder 'custom_filters/' di sebelah filter_registry.py.
    Setiap file .py di dalam folder tersebut akan di-import.
    Kelas yang merupakan subclass dari BaseAudioFilter akan otomatis didaftarkan
    menggunakan nama file (tanpa .py) sebagai key.

    Catatan implementasi:
    Filter custom mungkin mengimport BaseAudioFilter menggunakan path yang berbeda
    (relative import, sys.path insert, dsb.), yang bisa menyebabkan issubclass() gagal
    karena Python menganggap dua class berbeda padahal sama secara logika.
    Untuk mengatasi ini, kita daftarkan 'base_filter' ke sys.modules di bawah semua
    alias yang mungkin digunakan sebelum load module custom.
    """
    registry_dir = os.path.dirname(os.path.abspath(__file__))
    custom_dir = os.path.join(registry_dir, "custom_filters")

    if not os.path.isdir(custom_dir):
        return

    # Pastikan BaseAudioFilter tersedia di semua alias module yang mungkin digunakan
    # oleh custom filters (e.g. 'base_filter', 'drone_system.base_filter', dll)
    _ensure_base_filter_aliases(registry_dir)

    for fname in os.listdir(custom_dir):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue

        module_key = fname[:-3]  # Hilangkan .py
        fpath = os.path.join(custom_dir, fname)

        try:
            spec = importlib.util.spec_from_file_location(
                f"drone_system.custom_filters.{module_key}", fpath
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Cari subclass dari BaseAudioFilter di dalam module
            # Kita cek dengan SEMUA kemungkinan versi BaseAudioFilter yang terdaftar di sys.modules
            base_classes = _get_all_base_filter_classes()
            found_class = None
            skipped_unavailable = False

            for _, obj in inspect.getmembers(module, inspect.isclass):
                is_subclass = False
                for base_cls in base_classes:
                    try:
                        if issubclass(obj, base_cls) and obj is not base_cls:
                            is_subclass = True
                            break
                    except TypeError:
                        continue

                if is_subclass:
                    if obj.is_available():
                        found_class = obj
                        break
                    else:
                        skipped_unavailable = True

            if found_class is not None:
                _REGISTRY[module_key] = found_class
                print(f"[FILTER REGISTRY] [OK] Loaded custom: '{module_key}' ({found_class.__name__})")
            elif skipped_unavailable:
                print(f"[FILTER REGISTRY] [SKIP] Custom '{module_key}': dependensi tidak tersedia "
                      f"(is_available() == False)")
            else:
                # File ada tapi tidak mengandung subclass BaseAudioFilter
                print(f"[FILTER REGISTRY] [WARN] Custom '{module_key}': tidak ada subclass "
                      f"BaseAudioFilter yang valid. Pastikan class mewarisi BaseAudioFilter "
                      f"dari udara/drone_system/base_filter.py")

        except Exception as e:
            print(f"[FILTER REGISTRY] [ERR] Gagal load custom filter '{fname}': {e}")


def _ensure_base_filter_aliases(registry_dir: str):
    """
    Daftarkan modul base_filter ke sys.modules di bawah semua alias yang mungkin
    digunakan oleh custom filters, sehingga issubclass() check selalu berhasil.
    """
    import importlib.util as ilu
    base_filter_path = os.path.join(registry_dir, "base_filter.py")
    aliases = [
        "base_filter",
        "drone_system.base_filter",
        "udara.drone_system.base_filter",
    ]
    for alias in aliases:
        if alias not in sys.modules:
            try:
                spec = ilu.spec_from_file_location(alias, base_filter_path)
                mod = ilu.module_from_spec(spec)
                sys.modules[alias] = mod
                spec.loader.exec_module(mod)
            except Exception:
                pass


def _get_all_base_filter_classes() -> list:
    """
    Kumpulkan semua varian class BaseAudioFilter yang ada di sys.modules.
    Ini mengatasi kasus di mana custom filter mengimport dari path yang berbeda.
    """
    result = [BaseAudioFilter]  # Yang resmi (digunakan oleh built-in)
    for mod_name, mod in sys.modules.items():
        if mod is None:
            continue
        if "base_filter" in mod_name:
            cls = getattr(mod, "BaseAudioFilter", None)
            if cls is not None and cls not in result:
                result.append(cls)
    return result


# ── Public API ─────────────────────────────────────────────────────────

def get_method_class(key: str) -> Type[BaseAudioFilter]:
    """
    Mengembalikan Class (bukan instance) filter berdasarkan key.
    Class dikembalikan agar bisa di-inisiasi dengan parameter yang spesifik.

    Args:
        key (str): Nama metode filter (e.g. "spectral_gating", "wavelet_denoising")

    Returns:
        Type[BaseAudioFilter]: Class filter yang sesuai.
        Jika key tidak ditemukan, kembalikan default (spectral_gating / passthrough).
    """
    _initialize()

    if key not in _REGISTRY:
        print(f"[FILTER REGISTRY] [WARN] Metode '{key}' tidak ditemukan, "
              f"menggunakan default '{DEFAULT_METHOD}'")
        return _REGISTRY.get(DEFAULT_METHOD, list(_REGISTRY.values())[0])

    return _REGISTRY[key]


def list_available_methods() -> list[str]:
    """
    Mengembalikan daftar key semua metode yang tersedia di registry.
    """
    _initialize()
    return list(_REGISTRY.keys())


def get_all_schemas() -> dict:
    """
    Mengembalikan skema parameter default untuk semua metode yang terdaftar.
    Format: {method_key: {"display_name": str, "params": {...}}}

    Digunakan oleh config_api.py untuk endpoint GET /filter-schemas.
    """
    _initialize()
    schemas = {}
    for key, FilterClass in _REGISTRY.items():
        try:
            # Inisiasi dengan parameter default untuk mendapatkan skema
            instance = FilterClass()
            schemas[key] = {
                "display_name": FilterClass.get_display_name(),
                "params": instance.get_params(),
            }
        except Exception as e:
            print(f"[FILTER REGISTRY] [ERR] Gagal get schema untuk '{key}': {e}")
    return schemas


def reset():
    """Reset registry (untuk testing)."""
    global _INITIALIZED
    _REGISTRY.clear()
    _INITIALIZED = False
