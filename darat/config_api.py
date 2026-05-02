"""
Ground Station Config REST API
FastAPI server untuk konfigurasi ground station.

Base URL  : http://localhost:5001  (atau http://<ground-pc-ip>:5001)
Contract  : communication-contract_config-ui.md section 4

Desain: Dijalankan sebagai daemon thread dalam proses Tkinter yang sama,
sehingga tidak perlu proses terpisah. GUI Tkinter tetap berjalan di
main thread; FastAPI/uvicorn berjalan di daemon thread.

Cara integrasi (dipanggil dari darat/app.py):
    from .config_api import start_ground_api_thread
    start_ground_api_thread(config_manager)
"""

import threading
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config_manager import GroundConfigManager, ConfigError


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


def create_app(config_manager: GroundConfigManager) -> FastAPI:
    """
    Factory function untuk membuat FastAPI app ground station.

    Args:
        config_manager: Shared GroundConfigManager instance (thread-safe)

    Returns:
        FastAPI app yang siap dijalankan dengan uvicorn
    """
    app = FastAPI(
        title="Ground Station Config API",
        version="1.0.0",
        description="REST API untuk konfigurasi ground station Miss Distance Indicator",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        return _err("SERVER_ERROR", str(exc), status=500)

    # ── GET /config/ground ────────────────────────────────────────────

    @app.get("/config/ground", summary="Ambil seluruh konfigurasi ground station")
    async def get_ground_config():
        """
        Kembalikan semua parameter konfigurasi ground station saat ini,
        termasuk mic_positions sebagai {mic: {x, y, z}}.
        """
        return _ok(config_manager.get_all())

    # ── PATCH /config/ground ──────────────────────────────────────────

    @app.patch("/config/ground", summary="Update satu atau lebih parameter ground station")
    async def patch_ground_config(request: Request):
        """
        Update parameter konfigurasi ground station.

        Untuk mic_positions: bersifat MERGE — hanya key yang dikirim yang
        diperbarui, key lain tidak dihapus (section 4.1 contract).
        """
        try:
            body: dict = await request.json()
        except Exception:
            return _err("VALIDATION_ERROR", "Request body harus berupa JSON object")

        if not isinstance(body, dict) or not body:
            return _err("VALIDATION_ERROR", "Request body tidak boleh kosong")

        try:
            result = config_manager.update(body)
        except ConfigError as e:
            return _err(e.code, e.message, e.field)

        config_manager.apply_to_module()
        return _ok(result)

    # ── GET /config/ground/schema ─────────────────────────────────────

    @app.get("/config/ground/schema", summary="Ambil schema metadata parameter ground station")
    async def get_ground_schema():
        """
        Kembalikan metadata setiap parameter untuk rendering form UI dinamis.
        """
        return _ok(config_manager.get_schema())

    # ── POST /config/ground/reset ─────────────────────────────────────

    @app.post("/config/ground/reset", summary="Reset konfigurasi ground station ke default")
    async def reset_ground_config(request: Request):
        """Reset semua parameter ground station ke nilai default hardcoded."""
        try:
            body: dict = await request.json()
        except Exception:
            body = {}

        scope = body.get("scope", "all") if isinstance(body, dict) else "all"

        try:
            result = config_manager.reset(scope)
        except ConfigError as e:
            return _err(e.code, e.message, e.field)

        config_manager.apply_to_module()
        return _ok(result)

    return app


def start_ground_api_thread(
    config_manager: GroundConfigManager,
    host: str = "0.0.0.0",
    port: int = 5001,
) -> threading.Thread:
    """
    Start Ground Station FastAPI server di background daemon thread.

    Dipanggil dari darat/app.py setelah inisialisasi GroundConfigManager.
    Thread bersifat daemon sehingga otomatis berhenti ketika Tkinter GUI exit.

    Returns:
        Thread yang sudah di-start, atau None jika uvicorn tidak tersedia
    """
    try:
        import uvicorn
    except ImportError:
        print(
            "[CONFIG API GROUND] uvicorn tidak tersedia. "
            "Install: pip install uvicorn[standard]"
        )
        return None

    app = create_app(config_manager)

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
        name="GroundConfigAPI",
    )
    thread.start()
    print(f"[CONFIG API GROUND] Ground API server started on http://{host}:{port}")
    return thread
