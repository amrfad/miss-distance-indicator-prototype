"""
Tests for RaspiConfigPanel conditional visibility (SDR vs ONLINE/Serial vs OFFLINE).
"""

import sys
import os
import unittest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

app = QApplication.instance() or QApplication(sys.argv)

from darat.ui.config_raspi import RaspiConfigPanel


class TestRaspiConfigPanelConditionalUI(unittest.TestCase):
    def setUp(self):
        self.panel = RaspiConfigPanel()

    def test_visibility_sdr_mode(self):
        self.panel.operation_mode.setCurrentText("SDR")
        self.assertFalse(self.panel._sdr_section.isHidden())
        self.assertTrue(self.panel._serial_container.isHidden())

    def test_visibility_online_serial_mode(self):
        self.panel.operation_mode.setCurrentText("ONLINE")
        self.assertTrue(self.panel._sdr_section.isHidden())
        self.assertFalse(self.panel._serial_container.isHidden())

    def test_visibility_offline_mode(self):
        self.panel.operation_mode.setCurrentText("OFFLINE")
        self.assertTrue(self.panel._sdr_section.isHidden())
        self.assertTrue(self.panel._serial_container.isHidden())

    def test_visibility_updated_via_set_config(self):
        self.panel.set_config({"operation_mode": "ONLINE"})
        self.assertTrue(self.panel._sdr_section.isHidden())
        self.assertFalse(self.panel._serial_container.isHidden())

        self.panel.set_config({"operation_mode": "SDR"})
        self.assertFalse(self.panel._sdr_section.isHidden())
        self.assertTrue(self.panel._serial_container.isHidden())


if __name__ == "__main__":
    unittest.main(verbosity=2)
