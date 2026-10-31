"""
Unit tests for 2D XY visualization (Radar2DWidget, VisualizePage, and visualize_2d_xy).
"""

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


class TestVisualize2D(unittest.TestCase):

    def setUp(self):
        self.sample_results_path = os.path.join(
            PROJECT_ROOT, "tests", "darat", "fixtures", "sample_results.txt"
        )

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

    def test_visualize_page_load_and_select(self):
        """Test VisualizePage mampu membaca direktori fixtures dan mempopulasikan tabel."""
        fixtures_dir = os.path.join(PROJECT_ROOT, "tests", "darat", "fixtures")
        page = VisualizePage(working_dir=fixtures_dir)

        # Highlight sample_results.txt
        page.highlight_file(self.sample_results_path)
        self.assertIsNotNone(page._get_selected_path())

        # Visualize
        page._visualize_selected()

        # Verifikasi metric chips dan tabel terisi
        self.assertNotEqual(page._chip_total.text(), "TOTAL: --")
        self.assertNotEqual(page._chip_valid.text(), "VALID: --")
        self.assertIn("PCA:", page._chip_pca.text())
        self.assertGreater(page._table.rowCount(), 0)

        # Verifikasi interaksi klik tabel
        page._table.selectRow(0)
        self.assertIsNotNone(page._radar.canvas._highlighted_event_num)


if __name__ == "__main__":
    unittest.main()
