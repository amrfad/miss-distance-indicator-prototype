"""
Drone Config REST API
FastAPI server untuk konfigurasi drone (Raspberry Pi).

Base URL  : http://<drone-ip>:5000
Contract  : communication-contract_config-ui.md section 3

Cara menjalankan (via thread daemon di main.py):
    from .config_api import create_app
    app = create_app(config_manager, audio_system)
    # kemudian jalankan dengan uvicorn di thread terpisah
"""

import sys
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .core.config_manager import ConfigManager, ConfigError, ValidationError
from .core.diagnostics import run_auto_checks, capture_live_mic_sample
from .tdoa import filter_registry


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).astimezone().isoformat()


def _ok(data: Any) -> dict:
    return {"success": True, "data": data, "error": None, "timestamp": _now_iso()}


def _err(code: str, message: str, field: Optional[str] = None, status: int = 400) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={
            "success": False,
            "data": None,
            "error": {"code": code, "message": message, "field": field},
            "timestamp": _now_iso(),
        },
    )


def create_app(config_manager: ConfigManager, audio_system=None) -> FastAPI:
    """
    Factory function untuk membuat FastAPI app.

    Args:
        config_manager: Shared ConfigManager instance (thread-safe)
        audio_system:   DroneAudioSystem instance (untuk query status recording)

    Returns:
        FastAPI app yang siap dijalankan dengan uvicorn
    """
    app = FastAPI(
        title="Drone Config API",
        version="1.0.0",
        description="REST API untuk konfigurasi drone Miss Distance Indicator",
    )

    # CORS — izinkan semua origin agar UI bisa akses dari PC manapun di LAN
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    # ── Global exception handler ──────────────────────────────────────

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return _err("SERVER_ERROR", str(exc), status=500)

    # ── GET /config ───────────────────────────────────────────────────

    @app.get("/config", summary="Ambil seluruh konfigurasi drone")
    async def get_config():
        """
        Kembalikan semua parameter konfigurasi drone saat ini.
        Mencakup parameter 🔒 (ground-only) dan 🔄 (runtime).
        """
        return _ok(config_manager.get_all())

    # ── PATCH /config ─────────────────────────────────────────────────

    @app.patch("/config", summary="Update satu atau lebih parameter")
    async def patch_config(request: Request):
        """
        Update parameter konfigurasi drone.
        Parameter 🔒 dapat diubah via endpoint ini, tapi memerlukan restart.
        Jika drone sedang recording, request ditolak (DRONE_BUSY).
        """
        # Cek apakah drone sedang recording
        if audio_system is not None:
            try:
                is_recording = (
                    hasattr(audio_system, "recorder")
                    and audio_system.recorder.is_recording()
                )
                if is_recording:
                    return _err(
                        "DRONE_BUSY",
                        "Drone sedang recording; tidak bisa ubah config saat ini",
                        status=409,
                    )
            except Exception:
                pass

        # Parse body
        try:
            body: dict = await request.json()
        except Exception:
            return _err("VALIDATION_ERROR", "Request body harus berupa JSON object")

        if not isinstance(body, dict) or not body:
            return _err("VALIDATION_ERROR", "Request body tidak boleh kosong")

        # Delegate ke ConfigManager
        try:
            result = config_manager.update(body, source="rest")
        except ConfigError as e:
            status = 400
            return _err(e.code, e.message, e.field, status=status)

        # Apply ke runtime objects
        if audio_system is not None:
            detector = getattr(audio_system, "detector", None)
            processor = getattr(audio_system, "processor", None)
            config_manager.apply_to_runtime_objects(detector=detector, processor=processor)

        return _ok(result)

    # ── GET /config/schema ────────────────────────────────────────────

    @app.get("/config/schema", summary="Ambil schema metadata semua parameter")
    async def get_config_schema():
        """
        Kembalikan metadata setiap parameter untuk rendering form UI dinamis.
        UI dapat menggunakan field category, type, enum, min/max/step, dll.
        """
        return _ok(config_manager.get_schema())

    # ── GET /filter-schemas ───────────────────────────────────────────

    @app.get("/filter-schemas", summary="Ambil skema parameter semua filter yang tersedia")
    async def get_filter_schemas():
        """
        Kembalikan skema parameter default untuk setiap metode filter yang terdaftar.

        Format response:
        {
          "spectral_gating": {
            "display_name": "Spectral Gating (noisereduce)",
            "params": {
              "prop_decrease": {"value": 1.0, "type": "float", "min": 0.0, "max": 1.0, ...},
              ...
            }
          },
          "wavelet_denoising": {...},
          ...
        }

        Digunakan oleh Ground Station untuk merender form parameter dinamis
        sesuai metode filter yang dipilih user.
        """
        return _ok(filter_registry.get_all_schemas())


    @app.post("/config/reset", summary="Reset config ke nilai default")
    async def reset_config(request: Request):
        """
        Reset parameter ke nilai default hardcoded.

        scope: "all" | "runtime_only" | "ground_only"
        """
        try:
            body: dict = await request.json()
        except Exception:
            body = {}

        scope = body.get("scope", "all") if isinstance(body, dict) else "all"

        try:
            result = config_manager.reset(scope)
        except ConfigError as e:
            return _err(e.code, e.message, e.field)

        if audio_system is not None:
            detector = getattr(audio_system, "detector", None)
            config_manager.apply_to_runtime_objects(detector=detector)

        return _ok(result)

    # ── GET /system/status ────────────────────────────────────────────

    @app.get("/system/status", summary="Status runtime drone")
    async def get_system_status():
        """
        Kembalikan status runtime drone: apakah sedang recording,
        operation mode, uptime, dan lainnya.
        """
        import time

        is_recording = False
        current_session = None
        uptime_seconds = None

        if audio_system is not None:
            try:
                is_recording = (
                    hasattr(audio_system, "recorder")
                    and audio_system.recorder.is_recording()
                )
                current_session = getattr(audio_system, "current_session_dir", None)
                start_time = getattr(audio_system, "recording_start_time", None)
                if start_time is not None:
                    uptime_seconds = round(time.time() - start_time, 1)
            except Exception:
                pass

        cfg = config_manager.get_all()
        return _ok({
            "is_recording": is_recording,
            "operation_mode": cfg.get("operation_mode", "OFFLINE"),
            "active_profile": cfg.get("active_profile", "H8"),
            "current_session": current_session,
            "uptime_seconds": uptime_seconds,
            "serial_connected": _check_serial_connected(audio_system),
        })

    @app.post("/system/restart", summary="Restart proses drone")
    async def restart_system():
        """
        Perintahkan sistem drone untuk keluar secara langsung.
        Menghentikan perekaman jika aktif dan keluar menggunakan os._exit(5)
        agar systemd dapat melakukan restart otomatis.
        """
        if audio_system:
            audio_system.restart_requested = True
            try:
                if audio_system.recorder and audio_system.recorder.is_recording():
                    print("[CONFIG API] Stopping active recording before restart...")
                    audio_system.recorder.stop_recording()
            except Exception as e:
                print(f"[CONFIG API] Error stopping recording: {e}")

        def _delayed_exit():
            import time
            import os
            time.sleep(1)
            print("[CONFIG API] Exiting process now via os._exit(5)...")
            sys.stdout.flush()
            os._exit(5)

        threading.Thread(target=_delayed_exit, daemon=True).start()
        return _ok({"message": "Drone system restarting in 1 second..."})

    # ── Diagnostics / System Check Endpoints ──────────────────────────

    def _is_recording_active() -> bool:
        if audio_system is None:
            return False
        try:
            return bool(
                hasattr(audio_system, "recorder")
                and audio_system.recorder.is_recording()
            )
        except Exception:
            return False

    @app.post("/diagnostics/run", summary="Jalankan System Check / Pre-Flight Diagnostics")
    def run_diagnostics_endpoint(body: Optional[dict] = None):
        """
        Menjalankan rangkaian auto-check hardware & software sisi udara.
        Menggunakan sync handler agar FastAPI mengeksekusi di threadpool tanpa memblokir event loop.
        Ditolak dengan 409 DRONE_BUSY jika drone sedang recording.
        """
        if _is_recording_active():
            return _err(
                "DRONE_BUSY",
                "Drone sedang recording; hentikan rekaman sebelum menjalankan System Check.",
                status=409,
            )

        opts = body if isinstance(body, dict) else {}
        report = run_auto_checks(
            audio_system=audio_system,
            config_manager=config_manager,
            options=opts,
        )
        return _ok(report)

    @app.post("/diagnostics/mic-sample", summary="Ambil 1 slice level mikrofon untuk Live Mic Tap Monitor")
    def mic_sample_endpoint(body: Optional[dict] = None):
        """
        Rekam slice pendek (~0.4s) dari perangkat audio dan kembalikan metrik RMS/Peak tiap mic.
        Ditolak dengan 409 DRONE_BUSY jika drone sedang recording.
        """
        if _is_recording_active():
            return _err(
                "DRONE_BUSY",
                "Drone sedang recording; tidak dapat memantau mikrofon via diagnostik.",
                status=409,
            )

        opts = body if isinstance(body, dict) else {}
        dur = float(opts.get("duration_sec", 0.4))
        try:
            sample = capture_live_mic_sample(
                audio_system=audio_system,
                config_manager=config_manager,
                duration_sec=dur,
            )
            return _ok(sample)
        except Exception as exc:
            return _err("MIC_SAMPLE_ERROR", str(exc), status=500)

    return app


def _check_serial_connected(audio_system) -> bool:
    """Helper: cek apakah serial handler terhubung."""
    # Main loop menyimpan serial_handler; tidak selalu accessible dari sini.
    # Untuk saat ini return None — bisa di-wire jika diperlukan.
    return None


def start_api_thread(
    config_manager: ConfigManager,
    audio_system=None,
    host: str = None,
    port: int = None,
) -> threading.Thread:
    """
    Start FastAPI server di background daemon thread.

    Dipanggil dari main.py setelah inisialisasi audio_system dan config_manager.
    Thread bersifat daemon sehingga otomatis berhenti ketika main thread exit.

    Args:
        config_manager: ConfigManager instance untuk membaca api_host dan api_port
        audio_system:   DroneAudioSystem instance (optional)
        host:           Override host (jika None, baca dari config)
        port:           Override port (jika None, baca dari config)

    Returns:
        Thread yang sudah di-start
    """
    try:
        import uvicorn
    except ImportError:
        print("[CONFIG API] uvicorn tidak tersedia. Install: pip install uvicorn[standard]")
        return None

    # Baca host dan port dari config jika tidak di-override
    if host is None:
        try:
            host = config_manager.get("api_host")
        except Exception:
            host = "0.0.0.0"
    if port is None:
        try:
            port = config_manager.get("api_port")
        except Exception:
            port = 5000

    app = create_app(config_manager, audio_system)

    thread = threading.Thread(
        target=uvicorn.run,
        kwargs={
            "app": app,
            "host": host,
            "port": port,
            "log_level": "warning",
            "access_log": False,
        },
        daemon=True,
        name="DroneConfigAPI",
    )
    thread.start()
    print(f"[CONFIG API] Drone API server started on http://{host}:{port}")
    return thread
