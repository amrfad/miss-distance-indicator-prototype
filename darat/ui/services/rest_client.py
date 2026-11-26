"""
RestClient — Non-blocking HTTP client for drone and ground station REST APIs.

Runs requests in QThread workers so the GUI thread is never blocked.
"""

from typing import Optional

from PySide6.QtCore import QObject, QThread, Signal


class _ApiWorker(QObject):
    """Background worker (one-shot) that performs a single HTTP request."""

    finished = Signal(dict)
    error    = Signal(str)

    def __init__(self, method: str, url: str, body: Optional[dict] = None, timeout: float = 2.0):
        super().__init__()
        self._method  = method
        self._url     = url
        self._body    = body
        self._timeout = float(timeout)

    def run(self):
        try:
            import requests  # type: ignore[import]
            timeout = self._timeout
            if self._method == "GET":
                resp = requests.get(self._url, timeout=timeout)
            elif self._method == "PATCH":
                resp = requests.patch(self._url, json=self._body, timeout=timeout)
            elif self._method == "POST":
                resp = requests.post(
                    self._url, json=self._body or {}, timeout=timeout
                )
            else:
                self.error.emit(f"Unknown HTTP method: {self._method}")
                return
            if not resp.ok:
                detail = f"HTTP {resp.status_code}"
                try:
                    payload = resp.json()
                    err_obj = payload.get("error") if isinstance(payload, dict) else None
                    if isinstance(err_obj, dict) and err_obj.get("message"):
                        code = err_obj.get("code", "")
                        detail = f"{code}: {err_obj['message']}" if code else err_obj["message"]
                except Exception:
                    pass
                self.error.emit(detail)
                return
            self.finished.emit(resp.json())
        except ImportError:
            self.error.emit(
                "requests library not installed. Run: pip install requests"
            )
        except Exception as exc:
            err_msg = str(exc)
            if "ConnectionRefusedError" in err_msg or "Failed to establish a new connection" in err_msg:
                err_msg = f"Connection refused to {self._url}"
            elif "Read timed out" in err_msg or "Connect timeout" in err_msg:
                err_msg = f"Connection timed out to {self._url}"
            self.error.emit(err_msg)


class RestClient(QObject):
    """Non-blocking HTTP client for drone (port 5000) and ground (port 5001) APIs.

    All requests are fired in background QThreads. Signals notify the UI when
    responses arrive.
    """

    # Drone API
    drone_config_received  = Signal(dict)
    drone_config_updated   = Signal(dict)
    drone_status_received  = Signal(dict)
    drone_restarted        = Signal(dict)
    drone_schema_received  = Signal(dict)
    filter_schemas_received = Signal(dict)  # GET /filter-schemas
    diagnostics_received    = Signal(dict)  # POST /diagnostics/run
    diagnostics_error       = Signal(str)
    mic_sample_received     = Signal(dict)  # POST /diagnostics/mic-sample
    mic_sample_error        = Signal(str)

    # Ground station API
    ground_config_received = Signal(dict)
    ground_config_updated  = Signal(dict)
    ground_schema_received = Signal(dict)
    ground_config_reset    = Signal(dict)

    # Generic error for any failed request
    error = Signal(str)

    def __init__(
        self,
        drone_ip:    str = "10.99.99.2",
        drone_port:  int = 5000,
        ground_port: int = 5001,
        parent=None,
    ):
        super().__init__(parent)
        self._drone_ip    = drone_ip
        self._drone_port  = drone_port
        self._ground_port = ground_port
        self._active_threads = []

    # ── Configuration ────────────────────────────────────────────────────

    def set_drone_ip(self, ip: str):
        self._drone_ip = ip

    def set_drone_port(self, port: int):
        self._drone_port = int(port)

    @property
    def drone_base(self) -> str:
        return f"http://{self._drone_ip}:{self._drone_port}"

    @property
    def ground_base(self) -> str:
        return f"http://localhost:{self._ground_port}"

    # ── Internal helper ──────────────────────────────────────────────────

    def _fire(
        self,
        method: str,
        url:    str,
        body:   Optional[dict],
        on_ok,
        on_err=None,
        timeout: float = 2.0,
    ):
        thread = QThread(self)
        worker = _ApiWorker(method, url, body, timeout=timeout)
        worker.moveToThread(thread)

        # Keep references to prevent premature garbage collection
        job = (thread, worker)
        self._active_threads.append(job)

        def _cleanup():
            if job in self._active_threads:
                self._active_threads.remove(job)
            thread.deleteLater()
            worker.deleteLater()

        thread.started.connect(worker.run)
        worker.finished.connect(on_ok)
        worker.finished.connect(thread.quit)
        worker.error.connect(thread.quit)
        worker.error.connect(on_err if on_err else self.error.emit)
        thread.finished.connect(_cleanup)

        thread.start()

    # ── Drone endpoints ──────────────────────────────────────────────────

    def get_drone_config(self):
        self._fire(
            "GET", f"{self.drone_base}/config", None,
            lambda d: self.drone_config_received.emit(d.get("data", {})),
        )

    def patch_drone_config(self, changes: dict):
        self._fire(
            "PATCH", f"{self.drone_base}/config", changes,
            lambda d: self.drone_config_updated.emit(d.get("data", {})),
        )

    def get_drone_schema(self):
        self._fire(
            "GET", f"{self.drone_base}/config/schema", None,
            lambda d: self.drone_schema_received.emit(d.get("data", {})),
        )

    def get_drone_status(self):
        self._fire(
            "GET", f"{self.drone_base}/system/status", None,
            lambda d: self.drone_status_received.emit(d.get("data", {})),
        )

    def restart_drone(self):
        self._fire(
            "POST", f"{self.drone_base}/system/restart", {},
            lambda d: self.drone_restarted.emit(d.get("data", {})),
        )

    def get_filter_schemas(self):
        """Ambil skema parameter untuk semua metode filter yang tersedia di drone."""
        self._fire(
            "GET", f"{self.drone_base}/filter-schemas", None,
            lambda d: self.filter_schemas_received.emit(d.get("data", {})),
        )

    def run_diagnostics(self, options: Optional[dict] = None, timeout: float = 25.0):
        """Jalankan rangkaian System Check / Pre-Flight Diagnostics di drone."""
        self._fire(
            "POST", f"{self.drone_base}/diagnostics/run", options or {},
            lambda d: self.diagnostics_received.emit(d.get("data", {})),
            on_err=lambda msg: self.diagnostics_error.emit(msg),
            timeout=timeout,
        )

    def fetch_mic_sample(self, duration_sec: float = 0.4, timeout: float = 6.0):
        """Ambil 1 slice level mikrofon cepat untuk Live Mic Tap Monitor."""
        self._fire(
            "POST", f"{self.drone_base}/diagnostics/mic-sample",
            {"duration_sec": float(duration_sec)},
            lambda d: self.mic_sample_received.emit(d.get("data", {})),
            on_err=lambda msg: self.mic_sample_error.emit(msg),
            timeout=timeout,
        )

    # ── Ground station endpoints ─────────────────────────────────────────

    def get_ground_config(self):
        self._fire(
            "GET", f"{self.ground_base}/config/ground", None,
            lambda d: self.ground_config_received.emit(d.get("data", {})),
        )

    def patch_ground_config(self, changes: dict):
        self._fire(
            "PATCH", f"{self.ground_base}/config/ground", changes,
            lambda d: self.ground_config_updated.emit(d.get("data", {})),
        )

    def get_ground_schema(self):
        self._fire(
            "GET", f"{self.ground_base}/config/ground/schema", None,
            lambda d: self.ground_schema_received.emit(d.get("data", {})),
        )

    def reset_ground_config(self, scope: str = "all"):
        self._fire(
            "POST", f"{self.ground_base}/config/ground/reset", {"scope": scope},
            lambda d: self.ground_config_reset.emit(d.get("data", {})),
        )
