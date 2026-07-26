# darat/ui/dashboard.py
"""MainDashboard — QMainWindow with collapsible sidebar navigation (simplified)."""

import os
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QFrame, QLabel, QPushButton,
    QButtonGroup, QSplitter,
)
from PySide6.QtCore import Qt, QTimer, Slot, Signal

from ..io.serial_manager import SerialManager
from ..core.file_transfer import FileTransferManager
from ..io.json_receiver import JsonReceiver
from ..core.config_manager import get_global_config_manager

from .services.serial_bridge import SerialBridge
from .services.rest_client import RestClient
from .pages.config_page import ConfigPage
from .pages.command_page import CommandPage
from .pages.process_page import ProcessPage
from .pages.visualize_page import VisualizePage
from .widgets.log_panel import LogPanel


class MainDashboard(QMainWindow):
    """Main application window with collapsible sidebar navigation."""

    log_signal = Signal(str, str)  # (message, level)

    _PAGE_CONFIG = 0
    _PAGE_COMMAND = 1
    _PAGE_PROCESS = 2
    _PAGE_VISUALIZE = 3

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Miss Distance Indicator — Ground Control Station")
        self.setMinimumSize(1100, 700)

        # Backend services
        self._config_manager = get_global_config_manager()
        cfg = self._config_manager.get_config()

        self._serial_bridge = SerialBridge(self)
        self._rest_client = RestClient(
            drone_ip=cfg.get("raspi_ip", "10.99.99.2"),
            drone_port=int(cfg.get("drone_port", 5000)),
            parent=self
        )

        # Direktori penyimpanan file yang diterima dari drone
        # → Prototype/drone_recordings/ (relatif terhadap root project)
        _project_root = os.path.realpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
        )
        self._drone_save_dir = os.path.join(_project_root, "drone_recordings")
        os.makedirs(self._drone_save_dir, exist_ok=True)

        self._ft_log_msgs: list[str] = []
        self._file_transfer = FileTransferManager(
            log_callback=self._handle_file_transfer_log,
            save_directory=self._drone_save_dir,
        )
        self._json_receiver = None

        # Wire serial bridge signals
        self._serial_bridge.connection_changed.connect(self._on_connection_changed)
        self._serial_bridge.data_received.connect(
            lambda data: self._file_transfer.process_incoming_data(data)
        )

        # Build UI
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header (hamburger + status + jam)
        root.addWidget(self._build_header())

        # Main splitter: sidebar + right container
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setHandleWidth(4)
        self._main_splitter.setChildrenCollapsible(True)

        self._sidebar = self._build_sidebar()
        self._main_splitter.addWidget(self._sidebar)

        right_container = self._build_right_container()
        self._main_splitter.addWidget(right_container)

        self._main_splitter.setSizes([180, self.width() - 180])
        root.addWidget(self._main_splitter, stretch=1)

        # Start timers
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)

        self._start_config_api()
        self._navigate(self._PAGE_COMMAND)

    # ========== UI Builders ==========
    def _build_header(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("headerPanel")
        panel.setFixedHeight(52)

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(12, 0, 16, 0)
        layout.setSpacing(12)

        self._menu_btn = QPushButton("☰")
        self._menu_btn.setObjectName("menuBtn")
        self._menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_btn.setCheckable(True)
        self._menu_btn.setChecked(True)
        self._menu_btn.setToolTip("Toggle sidebar")
        self._menu_btn.clicked.connect(self._toggle_sidebar)
        layout.addWidget(self._menu_btn)

        title = QLabel("MDI Ground Station")
        title.setObjectName("appTitle")
        layout.addWidget(title)
        layout.addStretch()

        # Connection indicator
        self._header_conn_dot = QLabel("●")
        self._header_conn_dot.setObjectName("statusError")
        self._header_conn_dot.setFixedWidth(16)
        layout.addWidget(self._header_conn_dot)

        self._header_conn_label = QLabel("NOT CONNECTED")
        self._header_conn_label.setObjectName("statusHeading")
        layout.addWidget(self._header_conn_label)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(1)
        layout.addWidget(sep)

        self._clock_label = QLabel()
        self._clock_label.setObjectName("statusValue")
        layout.addWidget(self._clock_label)
        self._tick_clock()
        return panel

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(0)
        sidebar.setMaximumWidth(200)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 20, 8, 20)
        layout.setSpacing(8)

        logo = QLabel("MDI")
        logo.setObjectName("sidebarTitle")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        ver = QLabel("v2.0 · GROUND UNIT")
        ver.setObjectName("sidebarSubtitle")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ver)

        div = QFrame()
        div.setObjectName("sidebarDivider")
        div.setFixedHeight(1)
        layout.addSpacing(10)
        layout.addWidget(div)
        layout.addSpacing(10)

        self._nav_buttons = []
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        nav_items = [
            ("⚙ CONFIG", self._PAGE_CONFIG),
            ("📡 COMMAND", self._PAGE_COMMAND),
            ("🔬 PROCESS", self._PAGE_PROCESS),
            ("📊 VISUALIZE", self._PAGE_VISUALIZE),
        ]
        for text, page_idx in nav_items:
            btn = QPushButton(text)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setMinimumHeight(40)
            btn.clicked.connect(lambda checked, p=page_idx: self._navigate(p))
            self._nav_group.addButton(btn, page_idx)
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()
        return sidebar

    def _build_right_container(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        content_splitter = QSplitter(Qt.Orientation.Vertical)
        content_splitter.setHandleWidth(4)
        content_splitter.setChildrenCollapsible(False)

        self._stack = QStackedWidget()

        self._json_receiver = JsonReceiver(
            serial_manager=self._serial_bridge.manager,
            file_transfer=self._file_transfer,
            log_callback=lambda msg: self.log_signal.emit(msg, "INFO"),
            save_directory=self._drone_save_dir,
        )
        self._serial_bridge.message_received.connect(
            lambda msg: self._log.log(msg, "DEBUG") if hasattr(self, '_log') else None
        )

        self._page_config = ConfigPage(rest_client=self._rest_client)
        self._page_command = CommandPage(
            serial_bridge=self._serial_bridge,
            file_transfer=self._file_transfer,
            json_receiver=self._json_receiver,
            log_callback=self._log.log if hasattr(self, '_log') else None,
            navigate_callback=self._navigate,
        )
        self._page_process = ProcessPage(working_dir=os.getcwd())
        self._page_visualize = VisualizePage(working_dir=os.getcwd())

        self._stack.addWidget(self._page_config)
        self._stack.addWidget(self._page_command)
        self._stack.addWidget(self._page_process)
        self._stack.addWidget(self._page_visualize)
        content_splitter.addWidget(self._stack)

        self._log = LogPanel()
        content_splitter.addWidget(self._log)
        content_splitter.setSizes([550, 300])

        layout.addWidget(content_splitter, stretch=1)

        # Wire signals
        self.log_signal.connect(self._log.log)

        for page in (self._page_config, self._page_command,
                     self._page_process, self._page_visualize):
            if hasattr(page, "log_message"):
                page.log_message.connect(self._log.log)

        self._page_config.restart_requested.connect(self._do_restart_drone)
        self._page_config.apply_serial_requested.connect(self._apply_serial_config)
        self._rest_client.ground_config_updated.connect(self._on_ground_config_updated)
        self._page_process.results_saved.connect(self._on_results_saved)

        return container

    def _toggle_sidebar(self, checked: bool):
        if checked:
            self._main_splitter.setSizes([180, self._main_splitter.width() - 180])
        else:
            self._main_splitter.setSizes([0, self._main_splitter.width()])

    # ========== Navigation ==========
    def _navigate(self, page_idx: int):
        self._stack.setCurrentIndex(page_idx)
        btn = self._nav_group.button(page_idx)
        if btn:
            btn.setChecked(True)

    # ========== Serial Actions (called from CommandPage) ==========
    def _do_connect_command(self):
        self._log.log("Connecting to serial port...", "INFO")
        ok = self._serial_bridge.connect_auto()
        if not ok:
            self._log.log("Auto-connect failed.", "ERROR")
        return ok

    def _do_disconnect_command(self):
        self._serial_bridge.disconnect()
        self._log.log("Serial disconnected.", "INFO")

    def _do_start_record_command(self):
        from ..core.config import CMD_START_RECORD
        self._serial_bridge.send_command(CMD_START_RECORD)
        self._log.log("Recording start command sent", "INFO")

    def _do_stop_record_command(self):
        from ..core.config import CMD_STOP_RECORD
        self._serial_bridge.send_command(CMD_STOP_RECORD)
        self._log.log("Recording stop command sent", "INFO")

    @Slot(dict)
    def _apply_serial_config(self, cfg: dict):
        if not cfg:
            self._log.log("No runtime params to send.", "WARNING")
            return
        ok = self._serial_bridge.send_set_config(cfg)
        if ok:
            self._log.log(f"SET_CONFIG sent ({len(cfg)} params)", "INFO")
        else:
            self._log.log("SET_CONFIG failed", "ERROR")

    @Slot()
    def _do_restart_drone(self):
        if self._serial_bridge.is_connected():
            self._log.log("Sending restart command to drone via Serial...", "WARNING")
            from ..core.config import CMD_RESTART
            self._serial_bridge.send_command(CMD_RESTART)
        else:
            self._log.log("Serial not connected. Sending restart command to drone via REST...", "WARNING")
            self._rest_client.restart_drone()

    @Slot(bool, str)
    def _on_connection_changed(self, connected: bool, port: str):
        if connected:
            self._header_conn_dot.setObjectName("statusOk")
            self._header_conn_label.setText(f"CONNECTED  {port}")
        else:
            self._header_conn_dot.setObjectName("statusError")
            self._header_conn_label.setText("NOT CONNECTED")
        # Refresh style
        for w in (self._header_conn_dot, self._header_conn_label):
            w.style().unpolish(w)
            w.style().polish(w)

    @Slot(str)
    def _on_json_received(self, filename: str):
        self._log.log(f"JSON received: {os.path.basename(filename)}", "INFO")
        if filename:
            d = os.path.dirname(filename) or self._page_process._working_dir
            self._page_process.set_working_dir(d)
            self._page_visualize.set_working_dir(d)

    @Slot(str)
    def _on_results_saved(self, results_path: str):
        if results_path:
            self._page_visualize.set_working_dir(os.path.dirname(results_path))
            self._page_visualize.highlight_file(results_path)
            self._navigate(self._PAGE_VISUALIZE)
            self._log.log(f"Auto-switched to Visualize: {os.path.basename(results_path)}", "INFO")

    def _tick_clock(self):
        now = datetime.now()
        self._clock_label.setText(now.strftime("  %H:%M:%S  ·  %Y-%m-%d"))

    def _start_config_api(self):
        try:
            from ..api.config_api import start_ground_api_thread
            start_ground_api_thread(
                config_manager=self._config_manager,
                host="0.0.0.0",
                port=5001,
            )
            self._log.log("Ground Config API started → http://localhost:5001", "INFO")
        except Exception as exc:
            self._log.log(f"Config API not started: {exc}", "WARNING")

    def _on_ground_config_updated(self, data: dict):
        if "raspi_ip" in data:
            self._rest_client.set_drone_ip(data["raspi_ip"])
            self._log.log(f"RestClient target IP updated: {data['raspi_ip']}", "INFO")
        if "drone_port" in data:
            self._rest_client.set_drone_port(data["drone_port"])
            self._log.log(f"RestClient target port updated: {data['drone_port']}", "INFO")

    def closeEvent(self, event):
        self._serial_bridge.disconnect()
        event.accept()

    def _handle_file_transfer_log(self, msg: str):
        """Salurkan log file transfer secara thread-safe ke main log dan serial bridge."""
        if not msg:
            return
        # 1. Simpan ke telemetry buffer
        self._ft_log_msgs.append(msg)
        # 2. Tampilkan di log console utama secara thread-safe
        self.log_signal.emit(msg, "INFO")
        # 3. Teruskan ke serial bridge message_received agar CommandPage dapat menangkap respons STATUS/INFO
        clean_msg = msg
        if msg.startswith("Received: "):
            clean_msg = msg[len("Received: "):]
        self._serial_bridge.message_received.emit(clean_msg)

    def get_logger(self):
        return self._log.log