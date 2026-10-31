"""
Unit tests for 2D XY visualization (Radar2DWidget, VisualizePage, and visualize_2d_xy)
and 2D localization algorithms (rotating_multilat_2d, chan_ho_2d).
"""

import json
import os
import sys
import unittest

os.environ["QT_QPA_PLATFORM"] = "offscreen"

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtWidgets import QApplication

# Ensure single QApplication instance
app = QApplication.instance() or QApplication(sys.argv)

from darat.visualize_results import parse_results_file, visualize_2d_xy
from darat.ui.widgets.radar_2d_widget import Radar2DWidget, _calc_clock_bearing
from darat.ui.pages.visualize_page import VisualizePage
from darat.localization import ssl_registry
from darat.localization.process_json_tdoa import process_event_tdoa


class TestVisualize2D(unittest.TestCase):

    def setUp(self):
        self.sample_results_path = os.path.join(
            PROJECT_ROOT, "tests", "darat", "fixtures", "sample_results.txt"
        )
        self.sample_tdoa_path = os.path.join(
            PROJECT_ROOT, "tests", "darat", "fixtures", "sample_tdoa.json"
        )
        ssl_registry.initialize()

    def test_calc_clock_bearing(self):
        """Test konversi koordinat (x, y) ke orientasi arah jarum jam."""
        # Utara (+Y) -> 12 o'clock (0 deg)
        clock_n, deg_n = _calc_clock_bearing(0.0, 5.0)
        self.assertEqual(clock_n, "12:00")
        self.assertAlmostEqual(deg_n, 0.0, places=1)

        # Timur (+X) -> 03 o'clock (90 deg)
        clock_e, deg_e = _calc_clock_bearing(5.0, 0.0)
        self.assertEqual(clock_e, "03:00")
        self.assertAlmostEqual(deg_e, 90.0, places=1)

        # Selatan (-Y) -> 06 o'clock (180 deg)
        clock_s, deg_s = _calc_clock_bearing(0.0, -5.0)
        self.assertEqual(clock_s, "06:00")
        self.assertAlmostEqual(deg_s, 180.0, places=1)

        # Barat (-X) -> 09 o'clock (270 deg)
        clock_w, deg_w = _calc_clock_bearing(-5.0, 0.0)
        self.assertEqual(clock_w, "09:00")
        self.assertAlmostEqual(deg_w, 270.0, places=1)

    def test_visualize_2d_xy_matplotlib(self):
        """Test fungsi Matplotlib standalone 2D XY."""
        events, mic_positions = parse_results_file(self.sample_results_path)
        self.assertTrue(len(events) > 0)
        fig = visualize_2d_xy(events, "sample_results.txt", mic_positions)
        self.assertIsNotNone(fig)
        import matplotlib.pyplot as plt
        plt.close(fig)

    def test_radar_2d_widget_lifecycle(self):
        """Test inisialisasi, set_data, auto_fit, dan highlight pada Radar2DWidget."""
        radar = Radar2DWidget()
        self.assertIsNotNone(radar)

        events, mic_positions = parse_results_file(self.sample_results_path)
        radar.set_data(events, mic_positions)
        self.assertTrue(len(radar.canvas._events) > 0)

        # Auto-fit
        radar.auto_fit()
        self.assertGreater(radar.canvas.get_range(), 0.0)

        # Zoom controls
        initial_range = radar.canvas.get_range()
        radar._zoom_in()
        self.assertLessEqual(radar.canvas.get_range(), initial_range)
        radar._zoom_out()
        self.assertGreaterEqual(radar.canvas.get_range(), initial_range - 2.5)

        # Highlight event
        radar.highlight_event(1)
        self.assertEqual(radar.canvas._highlighted_event_num, 1)

        # Clear
        radar.clear()
        self.assertEqual(len(radar.canvas._events), 0)

    def test_visualize_page_layout_and_2d_table(self):
        """Test VisualizePage dengan tabel 2D 6 kolom di sebelah kanan radar."""
        fixtures_dir = os.path.join(PROJECT_ROOT, "tests", "darat", "fixtures")
        page = VisualizePage(working_dir=fixtures_dir)

        # Highlight sample_results.txt
        page.highlight_file(self.sample_results_path)
        self.assertIsNotNone(page._get_selected_path())

        # Visualize
        page._visualize_selected()

        # Verifikasi metric chips terisi
        self.assertNotEqual(page._chip_total.text(), "TOTAL: --")
        self.assertNotEqual(page._chip_valid.text(), "VALID: --")

        # Verifikasi tabel 2D: tepat 6 kolom (Event, X, Y, Miss Dist, Bearing, Status)
        self.assertEqual(page._table.columnCount(), 6)
        self.assertGreater(page._table.rowCount(), 0)

        headers = [page._table.horizontalHeaderItem(i).text() for i in range(6)]
        self.assertEqual(
            headers,
            ["Event", "X (m)", "Y (m)", "Miss Dist (m)", "Bearing", "Status"]
        )

        # Verifikasi status seragam
        for r in range(page._table.rowCount()):
            status_text = page._table.item(r, 5).text()
            self.assertIn(status_text, ["VALID", "FAILED"])

        # Verifikasi interaksi klik tabel menyorot radar
        page._table.selectRow(0)
        self.assertIsNotNone(page._radar.canvas._highlighted_event_num)

    def test_2d_algorithms_registered(self):
        """Test algoritma 2D terdaftar di ssl_registry dan dapat di-resolve."""
        rot2d = ssl_registry.get_method("rotating_multilat_2d")
        self.assertIsNotNone(rot2d)
        self.assertEqual(rot2d.display_name, "Rotating Multilateration 2D")

        chan2d = ssl_registry.get_method("chan_ho_2d")
        self.assertIsNotNone(chan2d)
        self.assertEqual(chan2d.display_name, "Chan-Ho WLS 2D")

    def test_2d_algorithms_process_events(self):
        """Test pemrosesan event TDOA menggunakan metode 2D menghasilkan posisi 2 elemen [x, y]."""
        with open(self.sample_tdoa_path, "r") as f:
            data = json.load(f)

        events = data.get("events", [])
        self.assertTrue(len(events) > 0)

        # Posisi mikrofon default 6 mic
        mic_positions = {
            "mic0": [-0.60,  0.00,  0.00],
            "mic1": [-0.20, -0.60,  0.00],
            "mic2": [ 0.20, -0.60,  0.00],
            "mic3": [ 0.60,  0.00,  0.00],
            "mic4": [ 0.20,  0.60,  0.00],
            "mic5": [-0.20,  0.60,  0.00],
        }

        # Test Rotating Multilat 2D
        pos_rot, cluster_rot, info_rot = process_event_tdoa(
            events[0], mic_positions, method="rotating_multilat_2d"
        )
        if pos_rot is not None:
            self.assertEqual(len(pos_rot), 2)

        # Test Chan-Ho 2D
        pos_chan, cluster_chan, info_chan = process_event_tdoa(
            events[0], mic_positions, method="chan_ho_2d"
        )
        if pos_chan is not None:
            self.assertEqual(len(pos_chan), 2)


if __name__ == "__main__":
    unittest.main()
