# demo_ground/ui/pages/config_page.py
"""
Configuration Page — Pengaturan Serial, Parameter SSL 2D, dan Tabel Posisi Mikrofon.
Mengadopsi layout Card dan styling form persis Ground Station darat/.
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFrame, QLabel, QComboBox, QDoubleSpinBox,
    QTableWidget, QTableWidgetItem, QPushButton,
    QHeaderView, QMessageBox, QScrollArea,
)
from PySide6.QtCore import Signal, Qt


class ConfigPage(QWidget):
    """Layar konfigurasi Ground Station Demo dengan styling card taktis."""

    config_saved = Signal()
    log_message = Signal(str, str)

    def __init__(self, config_manager, serial_bridge=None, parent=None):
        super().__init__(parent)
        self.config_manager = config_manager
        self.serial_bridge = serial_bridge

        self._build_ui()
        self.load_from_config()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(12)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        # ── Card 1: Serial & Communication Parameters ──
        card_serial = QFrame()
        card_serial.setObjectName("card")
        cs_layout = QVBoxLayout(card_serial)
        cs_layout.setContentsMargins(16, 16, 16, 16)
        cs_layout.setSpacing(12)

        cs_title = QLabel("SERIAL PORT CONFIGURATION")
        cs_title.setObjectName("sectionTitle")
        cs_layout.addWidget(cs_title)

        grid_s = QGridLayout()
        grid_s.setSpacing(10)

        grid_s.addWidget(QLabel("TARGET COM PORT:"), 0, 0)
        self.port_combo = QComboBox()
        grid_s.addWidget(self.port_combo, 0, 1)

        self.btn_refresh = QPushButton("↻ REFRESH PORTS")
        self.btn_refresh.clicked.connect(self._refresh_ports)
        grid_s.addWidget(self.btn_refresh, 0, 2)

        grid_s.addWidget(QLabel("BAUD RATE (BPS):"), 1, 0)
        self.baud_combo = QComboBox()
        self.baud_combo.addItems(["9600", "115200", "230400", "460800", "921600"])
        grid_s.addWidget(self.baud_combo, 1, 1)

        cs_layout.addLayout(grid_s)
        layout.addWidget(card_serial)

        # ── Card 2: 2D SSL Localization Settings ──
        card_ssl = QFrame()
        card_ssl.setObjectName("card")
        css_layout = QVBoxLayout(card_ssl)
        css_layout.setContentsMargins(16, 16, 16, 16)
        css_layout.setSpacing(12)

        css_title = QLabel("2D LOCALIZATION ALGORITHM PARAMETERS")
        css_title.setObjectName("sectionTitle")
        css_layout.addWidget(css_title)

        grid_ssl = QGridLayout()
        grid_ssl.setSpacing(10)

        grid_ssl.addWidget(QLabel("SOLVER METHOD:"), 0, 0)
        self.method_combo = QComboBox()
        from ...ssl.ssl_dispatcher import SOLVER_CHOICES
        for k, label in SOLVER_CHOICES.items():
            self.method_combo.addItem(label, k)
        grid_ssl.addWidget(self.method_combo, 0, 1)

        grid_ssl.addWidget(QLabel("SPEED OF SOUND (m/s):"), 1, 0)
        self.spin_c = QDoubleSpinBox()
        self.spin_c.setObjectName("monoField")
        self.spin_c.setRange(300.0, 380.0)
        self.spin_c.setSingleStep(0.5)
        self.spin_c.setValue(343.0)
        grid_ssl.addWidget(self.spin_c, 1, 1)

        grid_ssl.addWidget(QLabel("CLUSTER EPS (meter):"), 2, 0)
        self.spin_eps = QDoubleSpinBox()
        self.spin_eps.setObjectName("monoField")
        self.spin_eps.setRange(0.1, 10.0)
        self.spin_eps.setSingleStep(0.1)
        self.spin_eps.setValue(1.0)
        grid_ssl.addWidget(self.spin_eps, 2, 1)

        css_layout.addLayout(grid_ssl)
        layout.addWidget(card_ssl)

        # ── Card 3: Microphone Array Geometry (3D) ──
        card_mics = QFrame()
        card_mics.setObjectName("card")
        cm_layout = QVBoxLayout(card_mics)
        cm_layout.setContentsMargins(16, 16, 16, 16)
        cm_layout.setSpacing(12)

        cm_title = QLabel("MICROPHONE ARRAY GEOMETRY (METERS)")
        cm_title.setObjectName("sectionTitle")
        cm_layout.addWidget(cm_title)

        self.mic_table = QTableWidget(6, 3)
        self.mic_table.setHorizontalHeaderLabels([
            "X — Lateral (m)", "Y — Longitudinal (m)", "Z — Vertical (m)"
        ])
        self.mic_table.setVerticalHeaderLabels([f"mic{i}" for i in range(6)])
        self.mic_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.mic_table.setMinimumHeight(195)
        cm_layout.addWidget(self.mic_table)

        layout.addWidget(card_mics)

        # ── Actions Row ──
        btn_bar = QHBoxLayout()
        self.btn_reset = QPushButton("↺ RESET TO DEFAULTS")
        self.btn_reset.setObjectName("btnReset")
        self.btn_reset.setMinimumHeight(40)
        self.btn_reset.clicked.connect(self._on_reset_clicked)
        btn_bar.addWidget(self.btn_reset)

        btn_bar.addStretch()

        self.btn_save = QPushButton("💾 SAVE CONFIGURATION")
        self.btn_save.setObjectName("btnSave")
        self.btn_save.setMinimumHeight(40)
        self.btn_save.clicked.connect(self._on_save_clicked)
        btn_bar.addWidget(self.btn_save)

        layout.addLayout(btn_bar)

        scroll.setWidget(container)
        root.addWidget(scroll)

    def _refresh_ports(self):
        curr = self.port_combo.currentData() or self.config_manager.get("serial_port", "COM3")
        self.port_combo.clear()
        
        manager = getattr(self.serial_bridge, "manager", self.serial_bridge)
        ports = manager.get_available_ports() if manager and hasattr(manager, "get_available_ports") else []
        idx_to_select = 0
        for i, p in enumerate(ports):
            self.port_combo.addItem(p["display_label"], p["device"])
            if p["device"] == curr:
                idx_to_select = i
        if self.port_combo.count() == 0:
            self.port_combo.addItem("COM3 (Virtual)", "COM3")
        else:
            self.port_combo.setCurrentIndex(idx_to_select)

    def load_from_config(self):
        cfg = self.config_manager.get_all()
        self._refresh_ports()

        # Baud
        baud_str = str(cfg.get("baud_rate", 230400))
        idx = self.baud_combo.findText(baud_str)
        if idx >= 0:
            self.baud_combo.setCurrentIndex(idx)

        # SSL method
        method_key = cfg.get("ssl_method", "auto_adaptive")
        m_idx = self.method_combo.findData(method_key)
        if m_idx >= 0:
            self.method_combo.setCurrentIndex(m_idx)

        self.spin_c.setValue(float(cfg.get("speed_of_sound", 343.0)))
        self.spin_eps.setValue(float(cfg.get("cluster_eps", 1.0)))

        mics = cfg.get("mic_positions", {})
        for i in range(6):
            m_name = f"mic{i}"
            pos = mics.get(m_name, {"x": 0.0, "y": 0.0, "z": 0.0})
            if isinstance(pos, dict):
                x_val = float(pos.get("x", 0.0))
                y_val = float(pos.get("y", 0.0))
                z_val = float(pos.get("z", 0.0))
            else:
                x_val = float(pos[0]) if len(pos) > 0 else 0.0
                y_val = float(pos[1]) if len(pos) > 1 else 0.0
                z_val = float(pos[2]) if len(pos) > 2 else 0.0

            xi = QTableWidgetItem(f"{x_val:+.3f}")
            xi.setTextAlignment(Qt.AlignCenter)
            yi = QTableWidgetItem(f"{y_val:+.3f}")
            yi.setTextAlignment(Qt.AlignCenter)
            zi = QTableWidgetItem(f"{z_val:+.3f}")
            zi.setTextAlignment(Qt.AlignCenter)

            self.mic_table.setItem(i, 0, xi)
            self.mic_table.setItem(i, 1, yi)
            self.mic_table.setItem(i, 2, zi)

    def _on_save_clicked(self):
        port = self.port_combo.currentData() or self.port_combo.currentText()
        baud = int(self.baud_combo.currentText())
        method = self.method_combo.currentData()
        c = self.spin_c.value()
        eps = self.spin_eps.value()

        mic_positions = {}
        try:
            for i in range(6):
                x = float(self.mic_table.item(i, 0).text().strip())
                y = float(self.mic_table.item(i, 1).text().strip())
                z = float(self.mic_table.item(i, 2).text().strip())
                mic_positions[f"mic{i}"] = {"x": x, "y": y, "z": z}
        except Exception:
            QMessageBox.critical(self, "Validation Error", "All microphone coordinates (X, Y, Z) must be valid numbers.")
            return

        new_data = {
            "serial_port": port,
            "baud_rate": baud,
            "ssl_method": method,
            "speed_of_sound": c,
            "cluster_eps": eps,
            "mic_positions": mic_positions,
        }

        self.config_manager.update(new_data)
        self.config_manager.save()
        self.config_saved.emit()
        self.log_message.emit("Ground station configuration saved successfully.", "INFO")
        QMessageBox.information(self, "Saved", "Configuration saved successfully!")

    def _on_reset_clicked(self):
        reply = QMessageBox.question(
            self, "Reset Defaults",
            "Reset all configuration parameters to default factory settings?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.config_manager.reset_to_default()
            self.load_from_config()
            self.config_saved.emit()
            self.log_message.emit("Configuration reset to defaults.", "INFO")
