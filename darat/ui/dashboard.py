# darat/ui/dashboard.py
"""MainDashboard — QMainWindow with collapsible sidebar navigation."""

import os
from datetime import datetime

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QFrame, QLabel, QPushButton,
    QButtonGroup, QSplitter,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSlot

from ..serial_manager import SerialManager
from ..file_transfer import FileTransferManager
from ..json_receiver import JsonReceiver
from ..config_manager import get_global_config_manager

from .widgets.control_buttons import ControlButtons
from .widgets.status_panel import StatusPanel
from .widgets.log_panel import LogPanel
from .services.serial_bridge import SerialBridge
from .services.rest_client import RestClient
from .pages.config_page import ConfigPage
from .pages.command_page import CommandPage
from .pages.process_page import ProcessPage
from .pages.visualize_page import VisualizePage


class MainDashboard(QMainWindow):
    """Main application window with collapsible sidebar navigation."""

    _PAGE_CONFIG = 0
    _PAGE_COMMAND = 1
    _PAGE_PROCESS = 2
    _PAGE_VISUALIZE = 3

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Miss Distance Indicator — Ground Control Station")
        self.setMinimumSize(1100, 700)

        # ── Backend services ────────────────────────────────────────────
        self._config_manager = get_global_config_manager()
        cfg = self._config_manager.get_config()

        self._serial_bridge = SerialBridge(self)
        self._rest_client = RestClient(
            drone_ip=cfg.get("raspi_ip", "192.168.1.100"),
            parent=self
        )
        self._ft_log_msgs: list[str] = []
        self._file_transfer = FileTransferManager(
            log_callback=lambda msg: self._ft_log_msgs.append(msg),
            save_directory=os.getcwd(),
        )
        self._json_receiver = None

        # Wire serial bridge signals
        self._serial_bridge.connection_changed.connect(self._on_connection_changed)
        self._serial_bridge.data_received.connect(
            lambda data: self._file_transfer.process_incoming_data(data)
        )

        # ── Build UI ────────────────────────────────────────────────────
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header (dengan hamburger)
        root.addWidget(self._build_header())

        # MAIN SPLITTER: sidebar (kiri) + semua konten kanan (toolbar, status, pages, log)
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setHandleWidth(4)
        self._main_splitter.setChildrenCollapsible(True)

        # Sidebar (akan collapse ke 0)
        self._sidebar = self._build_sidebar()
        self._main_splitter.addWidget(self._sidebar)

        # Container kanan (toolbar + status + pages + log)
        right_container = self._build_right_container()
        self._main_splitter.addWidget(right_container)

        # Set initial sizes: sidebar 180px, sisanya otomatis
        self._main_splitter.setSizes([180, self.width() - 180])

        root.addWidget(self._main_splitter, stretch=1)

        # Bottom status bar
        root.addWidget(self._build_bottom_bar())

        # ── Start timers ────────────────────────────────────────────────
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)

        self._start_config_api()
        self._navigate(self._PAGE_CONFIG)

    # ══════════════════════════════════════════════════════════════════════
    # UI Builders
    # ══════════════════════════════════════════════════════════════════════

    def _build_header(self) -> QWidget:
        """Header with hamburger menu, title, and clock."""
        panel = QWidget()
        panel.setObjectName("headerPanel")
        panel.setFixedHeight(56)

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(12, 0, 16, 0)
        layout.setSpacing(12)

        # Hamburger menu button (toggle sidebar collapse)
        self._menu_btn = QPushButton("☰")
        self._menu_btn.setObjectName("menuBtn")
        self._menu_btn.setFixedSize(36, 36)
        self._menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_btn.setCheckable(True)
        self._menu_btn.setChecked(True)
        self._menu_btn.clicked.connect(self._toggle_sidebar)
        layout.addWidget(self._menu_btn)

        # Title
        title = QLabel("◈ MISS DISTANCE INDICATOR")
        title.setObjectName("appTitle")
        layout.addWidget(title)

        subtitle = QLabel("GROUND CONTROL STATION")
        subtitle.setObjectName("appSubtitle")
        layout.addWidget(subtitle)

        layout.addStretch()

        # Clock
        self._clock_label = QLabel()
        self._clock_label.setObjectName("statusValue")
        self._clock_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._clock_label)
        self._tick_clock()

        return panel

    def _build_sidebar(self) -> QFrame:
        """Build collapsible sidebar navigation."""
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setMinimumWidth(0)  # Biar bisa collapse ke 0
        sidebar.setMaximumWidth(200)  # Maksimal lebar

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(8, 20, 8, 20)
        layout.setSpacing(8)

        # Logo
        logo = QLabel("MDI")
        logo.setObjectName("sidebarTitle")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(logo)

        ver = QLabel("v2.0 · GROUND UNIT")
        ver.setObjectName("sidebarSubtitle")
        ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(ver)

        # Divider
        div = QFrame()
        div.setObjectName("sidebarDivider")
        div.setFixedHeight(1)
        layout.addSpacing(10)
        layout.addWidget(div)
        layout.addSpacing(10)

        # Navigation buttons
        self._nav_buttons = []
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)

        nav_items = [
            ("⚙   CONFIG", self._PAGE_CONFIG),
            ("📡   COMMAND", self._PAGE_COMMAND),
            ("🔬   PROCESS", self._PAGE_PROCESS),
            ("📊   VISUALIZE", self._PAGE_VISUALIZE),
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

        # Connection status di sidebar (akan ikut collapse/hide)
        conn_div = QFrame()
        conn_div.setObjectName("sidebarDivider")
        conn_div.setFixedHeight(1)
        layout.addWidget(conn_div)
        layout.addSpacing(8)

        self._sidebar_conn_dot = QLabel("●")
        self._sidebar_conn_dot.setObjectName("sidebarConnDot")
        self._sidebar_conn_dot.setStyleSheet("color: #dc2626; font-size: 10px;")
        self._sidebar_conn_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._sidebar_conn_dot)

        self._sidebar_conn_label = QLabel("NOT CONNECTED")
        self._sidebar_conn_label.setObjectName("sidebarConnLabel")
        self._sidebar_conn_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._sidebar_conn_label.setWordWrap(True)
        layout.addWidget(self._sidebar_conn_label)

        return sidebar

    def _build_right_container(self) -> QWidget:
        """Build right container: toolbar + status + page stack + log."""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        self._toolbar = ControlButtons()
        self._toolbar.setFixedHeight(48)
        self._toolbar.connect_clicked.connect(self._do_connect)
        self._toolbar.disconnect_clicked.connect(self._do_disconnect)
        self._toolbar.start_clicked.connect(self._do_start_record)
        self._toolbar.stop_clicked.connect(self._do_stop_record)
        self._toolbar.apply_serial_clicked.connect(self._do_apply_serial)
        layout.addWidget(self._toolbar)

        # Thin divider
        hdiv = QFrame()
        hdiv.setFrameShape(QFrame.Shape.HLine)
        hdiv.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(hdiv)

        # Status strip (compact 1 row)
        self._status = StatusPanel()
        self._status.setFixedHeight(52)
        layout.addWidget(self._status)

        # Content splitter (page stack + log panel)
        content_splitter = QSplitter(Qt.Orientation.Vertical)
        content_splitter.setHandleWidth(4)
        content_splitter.setChildrenCollapsible(False)

        # Page stack
        self._stack = QStackedWidget()

        # Create JsonReceiver and pages
        self._json_receiver = JsonReceiver(
            serial_manager=self._serial_bridge.manager,
            file_transfer=self._file_transfer,
            log_callback=lambda msg: self._log.log(msg, "INFO") if hasattr(self, '_log') else None,
        )

        self._serial_bridge.message_received.connect(
            lambda msg: self._log.log(msg, "DEBUG") if hasattr(self, '_log') else None
        )

        self._page_config = ConfigPage(rest_client=self._rest_client)
        self._page_command = CommandPage(
            serial_bridge=self._serial_bridge,
            file_transfer=self._file_transfer,
            json_receiver=self._json_receiver,
        )
        self._page_process = ProcessPage(working_dir=os.getcwd())
        self._page_visualize = VisualizePage(working_dir=os.getcwd())

        self._stack.addWidget(self._page_config)
        self._stack.addWidget(self._page_command)
        self._stack.addWidget(self._page_process)
        self._stack.addWidget(self._page_visualize)
        content_splitter.addWidget(self._stack)

        # Log panel
        self._log = LogPanel()
        content_splitter.addWidget(self._log)
        content_splitter.setSizes([600, 200])

        layout.addWidget(content_splitter, stretch=1)

        # Wire page signals
        for page in (self._page_config, self._page_command,
                     self._page_process, self._page_visualize):
            if hasattr(page, "log_message"):
                page.log_message.connect(self._log.log)

        self._page_config.restart_requested.connect(self._do_restart_drone)
        self._page_config.apply_serial_requested.connect(self._apply_serial_config)

        self._rest_client.ground_config_updated.connect(self._on_ground_config_updated)

        self._page_command.recording_started.connect(
            lambda: self._toolbar.set_recording(True)
        )
        self._page_command.recording_stopped.connect(
            lambda: self._toolbar.set_recording(False)
        )
        self._page_command.json_received.connect(self._on_json_received)

        self._page_process.results_saved.connect(self._on_results_saved)

        return container

    def _toggle_sidebar(self, checked: bool):
        """Toggle sidebar collapse using QSplitter."""
        if checked:
            # Expanded: sidebar 180px
            self._main_splitter.setSizes([180, self._main_splitter.width() - 180])
        else:
            # Collapsed: sidebar 0px (hilang total)
            self._main_splitter.setSizes([0, self._main_splitter.width()])

    def _build_bottom_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("bottomBar")
        bar.setFixedHeight(28)

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(16)

        self._bottom_status = QLabel("● SYSTEM READY")
        self._bottom_status.setObjectName("statusOk")
        layout.addWidget(self._bottom_status)

        layout.addStretch()

        self._bottom_datetime = QLabel()
        self._bottom_datetime.setObjectName("statusHeading")
        layout.addWidget(self._bottom_datetime)
        self._tick_clock()

        return bar

    # ══════════════════════════════════════════════════════════════════════
    # Navigation & Actions
    # ══════════════════════════════════════════════════════════════════════

    def _navigate(self, page_idx: int):
        self._stack.setCurrentIndex(page_idx)
        btn = self._nav_group.button(page_idx)
        if btn:
            btn.setChecked(True)

    @pyqtSlot()
    def _do_connect(self):
        self._log.log("Connecting to serial port…", "INFO")
        ok = self._serial_bridge.connect_auto()
        if not ok:
            self._log.log("Auto-connect failed. Check port and baud rate.", "ERROR")

    @pyqtSlot()
    def _do_disconnect(self):
        self._serial_bridge.disconnect()
        self._log.log("Serial port disconnected.", "INFO")

    @pyqtSlot()
    def _do_start_record(self):
        from ..config import CMD_START_RECORD
        self._serial_bridge.send_command(CMD_START_RECORD)
        self._toolbar.set_recording(True)
        self._log.log("Recording started (via toolbar)", "INFO")

    @pyqtSlot()
    def _do_stop_record(self):
        from ..config import CMD_STOP_RECORD
        self._serial_bridge.send_command(CMD_STOP_RECORD)
        self._toolbar.set_recording(False)
        self._log.log("Recording stopped (via toolbar)", "INFO")

    @pyqtSlot()
    def _do_apply_serial(self):
        runtime_cfg = self._page_config.get_runtime_config()
        self._apply_serial_config(runtime_cfg)

    @pyqtSlot(dict)
    def _apply_serial_config(self, cfg: dict):
        if not cfg:
            self._log.log("No runtime params to send via serial.", "WARNING")
            return
        ok = self._serial_bridge.send_set_config(cfg)
        if ok:
            self._log.log(f"SET_CONFIG sent — {len(cfg)} runtime params", "INFO")
        else:
            self._log.log("SET_CONFIG failed — check serial connection.", "ERROR")

    @pyqtSlot()
    def _do_restart_drone(self):
        self._rest_client.restart_drone()
        self._log.log("Restart command sent to drone via REST API.", "WARNING")

    @pyqtSlot(bool, str)
    def _on_connection_changed(self, connected: bool, port: str):
        self._toolbar.set_connected(connected, port)
        if connected:
            self._sidebar_conn_dot.setStyleSheet("color: #16a34a; font-size:10px;")
            self._sidebar_conn_label.setText(port or "CONNECTED")
            self._bottom_status.setText(f"● CONNECTED  {port}")
            self._bottom_status.setObjectName("statusOk")
            self._log.log(f"Serial connected: {port}", "INFO")
        else:
            self._sidebar_conn_dot.setStyleSheet("color: #dc2626; font-size:10px;")
            self._sidebar_conn_label.setText("NOT CONNECTED")
            self._bottom_status.setText("● NOT CONNECTED")
            self._bottom_status.setObjectName("statusError")

    @pyqtSlot(str)
    def _on_json_received(self, filename: str):
        self._status.update_status({"last_detection": os.path.basename(filename) if filename else "—"})
        if filename:
            d = os.path.dirname(filename) or self._page_process._working_dir
            self._page_process.set_working_dir(d)
            self._page_visualize.set_working_dir(d)

    @pyqtSlot(str)
    def _on_results_saved(self, results_path: str):
        if not results_path:
            return
        self._page_visualize.set_working_dir(os.path.dirname(results_path))
        self._page_visualize.highlight_file(results_path)
        self._navigate(self._PAGE_VISUALIZE)
        self._log.log(f"Auto-switched to Visualize: {os.path.basename(results_path)}", "INFO")

    @pyqtSlot()
    def _tick_clock(self):
        now = datetime.now()
        self._clock_label.setText(now.strftime("  %H:%M:%S  ·  %Y-%m-%d"))
        if hasattr(self, "_bottom_datetime"):
            self._bottom_datetime.setText(now.strftime("%Y-%m-%d  %H:%M:%S"))

    def _start_config_api(self):
        try:
            from ..config_api import start_ground_api_thread
            start_ground_api_thread(
                config_manager=self._config_manager,
                host="0.0.0.0",
                port=5001,
            )
            self._log.log("Ground Config API started → http://localhost:5001", "INFO")
        except Exception as exc:
            self._log.log(f"Config API not started: {exc}", "WARNING")

    def closeEvent(self, event):
        self._serial_bridge.disconnect()
        event.accept()

    def _on_ground_config_updated(self, data: dict):
        if "raspi_ip" in data:
            new_ip = data["raspi_ip"]
            self._rest_client.set_drone_ip(new_ip)
            self._log.log(f"RestClient target IP updated: {new_ip}", "INFO")