"""
Tests for LaptopConfigPanel serial port auto-detection and QComboBox UI methods.
"""

import sys
import os
import unittest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Initialize QApplication for PySide6 GUI tests
app = QApplication.instance() or QApplication(sys.argv)

from darat.ui.config_laptop import LaptopConfigPanel


class TestLaptopConfigPanelSerialPort(unittest.TestCase):
    def setUp(self):
        self.panel = LaptopConfigPanel()

    def test_serial_port_combo_box(self):
        # Verify serial_port is QComboBox and editable
        self.assertTrue(self.panel.serial_port.isEditable())

    def test_refresh_serial_ports(self):
        self.panel.refresh_serial_ports()
        val = self.panel._get_serial_port_value()
        self.assertIsInstance(val, str)
        self.assertGreater(len(val), 0)

    def test_set_and_get_config(self):
        test_cfg = {
            "serial_port": "COM15",
            "baud_rate": 115200,
            "serial_timeout": 2.0,
        }
        self.panel.set_config(test_cfg)
        ui_vals = self.panel._get_values_from_ui()
        self.assertEqual(ui_vals["serial_port"], "COM15")
        self.assertEqual(ui_vals["baud_rate"], 115200)
        self.assertEqual(ui_vals["serial_timeout"], 2.0)

    def test_custom_typed_port(self):
        self.panel.serial_port.setCurrentText("/dev/ttyUSB9")
        val = self.panel._get_serial_port_value()
        self.assertEqual(val, "/dev/ttyUSB9")


if __name__ == "__main__":
    unittest.main()
