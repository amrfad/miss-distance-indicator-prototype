# demo_ground/ui/dashboard.py
"""
MainDashboard — QMainWindow with collapsible sidebar navigation, top tactical header,
and bottom collapsible LogPanel.
Arsitektur komunikasi SIYI (SerialBridge, FileTransfer, JsonReceiver) identik 1:1 dengan darat/.
"""

import os
import sys
from datetime import datetime

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QStackedWidget, QFrame, QLabel, QPushButton,
    QButtonGroup, QSplitter,
)
from PySide6.QtCore import Qt, QTimer, Slot, Signal

from ..core.config_manager import ConfigManager
from ..core.file_transfer import FileTransferManager
from ..core.json_receiver import JsonReceiver
from .services.serial_bridge import SerialBridge
from .widgets.log_panel import LogPanel
from .pages.live_page import LivePage
from .pages.config_page import ConfigPage


class MainDashboard(QMainWindow):
    """Jendela utama Ground Station Demo dengan arsitektur komunikasi identik darat/."""

    log_signal = Signal(str, str)  # (pesan, level)

    _PAGE_LIVE = 0
    _PAGE_CONFIG = 1

    def __init__(self, config_manager=None):
        super().__init__()
        self.setWindowTitle("Miss Distance Indicator — Ground Station (2D Demo)")
        self.setMinimumSize(1100, 720)

        self._config_manager = config_manager or ConfigManager()

        # Direktori penyimpanan file rekaman drone (sama dengan darat/)
        if getattr(sys, 'frozen', False):
            _base_dir = os.path.dirname(sys.executable)
        else:
            _base_dir = os.path.realpath(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
            )
        self._drone_save_dir = os.path.join(_base_dir, "drone_recordings")
        os.makedirs(self._drone_save_dir, exist_ok=True)

        # ── Backend Communication Services (Identik 1:1 dengan darat/) ──
        self._serial_bridge = SerialBridge(config_manager=self._config_manager, parent=self)
        self._ft_log_msgs: list[str] = []
        self._file_transfer = FileTransferManager(
            log_callback=self._handle_file_transfer_log,
            save_directory=self._drone_save_dir,
        )
        self._json_receiver = JsonReceiver(
            serial_manager=self._serial_bridge.manager,
            file_transfer=self._file_transfer,
            log_callback=lambda msg: self.log_signal.emit(msg, "INFO"),
            save_directory=self._drone_save_dir,
        )

        # Hubungkan aliran data serial mentah ke FileTransferManager
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

        # 1. Header Bar (Hamburger + Title + Connection Indicator + Clock)
        root.addWidget(self._build_header())

        # 2. Main Splitter: Collapsible Sidebar + Content Container
        self._main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_splitter.setHandleWidth(4)
        self._main_splitter.setChildrenCollapsible(True)

        self._sidebar = self._build_sidebar()
        self._main_splitter.addWidget(self._sidebar)

        right_container = self._build_right_container()
        self._main_splitter.addWidget(right_container)

        self._main_splitter.setSizes([190, self.width() - 190])
        root.addWidget(self._main_splitter, stretch=1)

        # Live Clock Timer
        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._tick_clock)
        self._clock_timer.start(1000)

        self._navigate(self._PAGE_LIVE)
        self._log.log("MDI Ground Station Demo (2D) initialized.", "INFO")

    def _build_header(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("headerPanel")
        panel.setFixedHeight(52)

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(12, 0, 16, 0)
        layout.setSpacing(12)

        # Hamburger Button
        self._menu_btn = QPushButton("☰")
        self._menu_btn.setObjectName("menuBtn")
        self._menu_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._menu_btn.setCheckable(True)
        self._menu_btn.setChecked(True)
        self._menu_btn.setToolTip("Toggle sidebar")
        self._menu_btn.clicked.connect(self._toggle_sidebar)
        layout.addWidget(self._menu_btn)

        # Title
        title = QLabel("MDI Ground Station")
        title.setObjectName("appTitle")
        layout.addWidget(title)

        sub = QLabel("DEMO 2D")
        sub.setObjectName("appSubtitle")
        layout.addWidget(sub)

        layout.addStretch()

        # Connection Indicator Pill
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

        # Live Clock
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

        ver = QLabel("v2.0 · DEMO 2D")
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
            ("📊 LIVE & RADAR", self._PAGE_LIVE),
            ("⚙ CONFIGURATION", self._PAGE_CONFIG),
        ]
        for text, page_idx in nav_items:
            btn = QPushButton(text)
            btn.setObjectName("navBtn")
            btn.setCheckable(True)
            btn.setMinimumHeight(42)
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

        # Stacked Pages
        self._stack = QStackedWidget()
        self._page_live = LivePage(
            serial_bridge=self._serial_bridge,
            file_transfer=self._file_transfer,
            json_receiver=self._json_receiver,
            config_manager=self._config_manager,
            drone_save_dir=self._drone_save_dir,
            log_callback=lambda msg, lvl="INFO": self.log_signal.emit(msg, lvl),
            parent=self,
        )
        self._page_config = ConfigPage(
            config_manager=self._config_manager,
            serial_bridge=self._serial_bridge,
            parent=self,
        )

        self._stack.addWidget(self._page_live)
        self._stack.addWidget(self._page_config)
        content_splitter.addWidget(self._stack)

        # System Log Panel
        self._log = LogPanel()
        content_splitter.addWidget(self._log)
        content_splitter.setSizes([560, 240])

        layout.addWidget(content_splitter)

        # Wire signals
        self.log_signal.connect(self._log.log)
        self._page_live.log_message.connect(self._log.log)
        self._page_config.log_message.connect(self._log.log)
        self._page_config.config_saved.connect(self._page_live.refresh_display)

        return container

    def _navigate(self, page_idx: int):
        self._stack.setCurrentIndex(page_idx)
        for i, btn in enumerate(self._nav_buttons):
            btn.setChecked(i == page_idx)

    def _toggle_sidebar(self):
        sizes = self._main_splitter.sizes()
        if sizes[0] > 0:
            self._sidebar_last_width = sizes[0]
            self._main_splitter.setSizes([0, sum(sizes)])
            self._menu_btn.setChecked(False)
        else:
            w = getattr(self, "_sidebar_last_width", 190)
            self._main_splitter.setSizes([w, sum(sizes) - w])
            self._menu_btn.setChecked(True)

    def _tick_clock(self):
        now = datetime.now()
        self._clock_label.setText(now.strftime("  %H:%M:%S  ·  %Y-%m-%d"))

    @Slot(bool, str)
    def _on_connection_changed(self, connected: bool, port: str):
        if connected:
            self._header_conn_dot.setObjectName("statusOk")
            self._header_conn_dot.setStyleSheet("color: #16a34a;")
            self._header_conn_label.setText(f"CONNECTED  {port}")
            self._log.log(f"SIYI Telemetry serial connected: {port}", "INFO")
        else:
            self._header_conn_dot.setObjectName("statusError")
            self._header_conn_dot.setStyleSheet("color: #dc2626;")
            self._header_conn_label.setText("NOT CONNECTED")
            self._log.log("SIYI Telemetry serial disconnected.", "INFO")

        for w in (self._header_conn_dot, self._header_conn_label):
            w.style().unpolish(w)
            w.style().polish(w)

    def _handle_file_transfer_log(self, msg: str):
        """Salurkan log file transfer secara thread-safe ke main log dan serial bridge."""
        if not msg:
            return
        self.log_signal.emit(msg, "INFO")
        clean_msg = msg
        if msg.startswith("Received: "):
            clean_msg = msg[len("Received: "):]
        self._serial_bridge.message_received.emit(clean_msg)

    def closeEvent(self, event):
        try:
            self._serial_bridge.disconnect()
        except Exception:
            pass
        event.accept()
