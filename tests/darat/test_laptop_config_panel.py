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
from darat.io.serial_manager import is_bluetooth_port, is_usb_port, format_port_label


class MockPort:
    def __init__(self, device, description="", hwid="", vid=None, pid=None, manufacturer=""):
        self.device = device
        self.description = description
        self.hwid = hwid
        self.vid = vid
        self.pid = pid
        self.manufacturer = manufacturer


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

    def test_serial_helpers(self):
        bt_port = MockPort("COM4", "Standard Serial over Bluetooth link", "BTHMODEM\\...")
        usb_port = MockPort("COM3", "Silicon Labs CP210x USB to UART Bridge", "USB VID:PID=10C4:EA60", vid=0x10C4, pid=0xEA60)

        self.assertTrue(is_bluetooth_port(bt_port))
        self.assertFalse(is_bluetooth_port(usb_port))

        self.assertTrue(is_usb_port(usb_port))
        self.assertFalse(is_usb_port(bt_port))

        self.assertEqual(format_port_label(usb_port), "COM3 — Silicon Labs CP210x USB to UART Bridge")

    def test_port_filtering_and_labeling(self):
        bt_port = MockPort("COM4", "Standard Serial over Bluetooth link", "BTHMODEM\\...")
        usb_port = MockPort("COM3", "Silicon Labs CP210x USB to UART Bridge", "USB VID:PID=10C4:EA60", vid=0x10C4, pid=0xEA60)

        import serial.tools.list_ports
        original_comports = serial.tools.list_ports.comports
        try:
            serial.tools.list_ports.comports = lambda: [bt_port, usb_port]
            self.panel.serial_port.clear()
            self.panel._update_serial_port_selection("COM3")

            # Bluetooth port (COM4) should be filtered out by default unless targeted
            item_data_list = [self.panel.serial_port.itemData(i) for i in range(self.panel.serial_port.count())]
            self.assertIn("COM3", item_data_list)
            self.assertNotIn("COM4", item_data_list)

            # Selected item text should contain formatted label
            self.assertEqual(self.panel.serial_port.currentText(), "COM3 — Silicon Labs CP210x USB to UART Bridge")
            self.assertEqual(self.panel._get_serial_port_value(), "COM3")
        finally:
            serial.tools.list_ports.comports = original_comports

    def test_conditional_visibility_sdr_vs_serial(self):
        # Default is SERIAL
        self.assertTrue(self.panel._sdr_container.isHidden())
        self.assertFalse(self.panel._serial_container.isHidden())

        # Switch to SDR via dropdown
        self.panel.comm_backend.setCurrentText("SDR")
        self.assertFalse(self.panel._sdr_container.isHidden())
        self.assertTrue(self.panel._serial_container.isHidden())

        # Switch back to SERIAL via set_config
        self.panel.set_config({"comm_backend": "SERIAL"})
        self.assertTrue(self.panel._sdr_container.isHidden())
        self.assertFalse(self.panel._serial_container.isHidden())

    def test_new_schema_fields_roundtrip(self):
        cfg = {
            "comm_backend": "SDR",
            "sdr_ipc_host": "127.0.0.2",
            "sdr_connect_timeout": 45.0,
            "multilat_aggregate": "mean",
            "multilat_max_norm": 350.0,
        }
        self.panel.set_config(cfg)
        ui_vals = self.panel._get_values_from_ui()
        self.assertEqual(ui_vals["sdr_ipc_host"], "127.0.0.2")
        self.assertEqual(ui_vals["sdr_connect_timeout"], 45.0)
        self.assertEqual(ui_vals["multilat_aggregate"], "mean")
        self.assertEqual(ui_vals["multilat_max_norm"], 350.0)


if __name__ == "__main__":
    unittest.main()

