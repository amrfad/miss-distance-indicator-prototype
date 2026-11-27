"""Unit tests untuk udara/drone_system/core/diagnostics.py."""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import numpy as np
import soundfile as sf

# Pastikan root udara ada di sys.path
_UDARA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "udara"))
if _UDARA_DIR not in sys.path:
    sys.path.insert(0, _UDARA_DIR)

from drone_system.core import diagnostics


class TestDiagnosticsParsers(unittest.TestCase):
    def test_parse_arecord_list_zoom_h8(self):
        sample_out = (
            "**** List of CAPTURE Hardware Devices ****\n"
            "card 2: H8 [Zoom H8], device 0: USB Audio [USB Audio]\n"
            "  Subdevices: 1/1\n"
            "  Subdevice #0: subdevice #0\n"
        )
        devices = diagnostics.parse_arecord_list(sample_out)
        self.assertEqual(len(devices), 1)
        self.assertEqual(devices[0]["hw_id"], "hw:2,0")
        self.assertEqual(devices[0]["card_name"], "Zoom H8")

    def test_parse_hw_params_output(self):
        sample_out = (
            "HW Params of device 'hw:2,0':\n"
            "FORMAT:  S24_3LE S32_LE\n"
            "CHANNELS: 12\n"
            "RATE: [44100 96000]\n"
        )
        formats, max_ch, min_r, max_r = diagnostics.parse_hw_params_output(sample_out)
        self.assertIn("S24_3LE", formats)
        self.assertIn("S32_LE", formats)
        self.assertEqual(max_ch, 12)
        self.assertEqual(min_r, 44100)
        self.assertEqual(max_r, 96000)


class TestMicAnalysis(unittest.TestCase):
    def test_analyze_mic_channels_healthy_and_loudest(self):
        rng = np.random.default_rng(42)
        n_samples = 4800
        data = rng.normal(0.0, 0.01, size=(n_samples, 12))
        # Buat mic2 (channel index 6) sedikit lebih keras agar jadi loudest
        data[:, 6] = rng.normal(0.0, 0.025, size=n_samples)

        metrics, loudest = diagnostics.analyze_mic_channels(data, (4, 5, 6, 7, 8, 9))
        self.assertEqual(len(metrics), 6)
        self.assertEqual(loudest, "mic2")
        chk = diagnostics.evaluate_mic_health_check(metrics)
        self.assertEqual(chk["status"], "PASS")

    def test_analyze_mic_channels_detects_dead_and_clip(self):
        rng = np.random.default_rng(7)
        data = rng.normal(0.0, 0.01, size=(4800, 12))
        data[:, 4] = 0.0          # mic0 dead
        data[:10, 5] = 1.0        # mic1 clipped

        metrics, _ = diagnostics.analyze_mic_channels(data, (4, 5, 6, 7, 8, 9))
        self.assertEqual(metrics[0]["status"], "DEAD")
        self.assertEqual(metrics[1]["status"], "CLIP")
        chk = diagnostics.evaluate_mic_health_check(metrics)
        self.assertEqual(chk["status"], "FAIL")
        self.assertIn("mic0", chk["detail"])
        self.assertIn("mic1", chk["detail"])

    def test_analyze_mic_channels_detects_unplugged_preamp_noise(self):
        rng = np.random.default_rng(11)
        data = rng.normal(0.0, 0.01, size=(4800, 12))  # ~ -40 dBFS
        data[:, 6] = rng.normal(0.0, 0.00003, size=4800)  # ~ -90 dBFS (unplugged XLR preamp noise)

        metrics, _ = diagnostics.analyze_mic_channels(data, (4, 5, 6, 7, 8, 9))
        self.assertEqual(metrics[2]["status"], "DEAD")
        chk = diagnostics.evaluate_mic_health_check(metrics)
        self.assertEqual(chk["status"], "FAIL")
        self.assertIn("mic2", chk["detail"])


class TestAlsaAndPipeline(unittest.TestCase):
    @patch("drone_system.core.diagnostics.subprocess.run")
    def test_check_alsa_device_card_shifted_returns_warn(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="card 3: H8 [Zoom H8], device 0: USB Audio [USB Audio]\n",
        )
        res = diagnostics.check_alsa_device("hw:2,0")
        self.assertEqual(res["status"], "WARN")
        self.assertEqual(res["metrics"]["suggested_device"], "hw:3,0")

    @patch("drone_system.core.diagnostics.subprocess.run")
    def test_check_alsa_device_no_device_returns_fail(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="**** List of CAPTURE Hardware Devices ****\n")
        res = diagnostics.check_alsa_device("hw:2,0")
        self.assertEqual(res["status"], "FAIL")

    def test_check_dsp_pipeline_synthetic_wavs(self):
        rng = np.random.default_rng(123)
        sr = 48000
        dur = 1.0
        n = int(sr * dur)
        with tempfile.TemporaryDirectory() as tmpdir:
            files = []
            base_pulse = rng.normal(0.0, 0.005, size=n)
            base_pulse[20000:20200] += 0.3 * np.hanning(200)
            for i in range(6):
                p = os.path.join(tmpdir, f"mic{i}_diag.wav")
                sig = np.roll(base_pulse, i * 5) + rng.normal(0.0, 0.001, size=n)
                sf.write(p, sig, sr)
                files.append(p)

            cfg = {
                "filter_method": "passthrough",
                "filter_configs": {},
                "tdoa_method": "eccct",
                "chunk_duration_sec": 8.0,
                "drone_rpm": 4000.0,
                "env_smooth_ms": 2.0,
                "env_decimation": 10,
                "do_closure_tuning": True,
            }
            res = diagnostics.check_dsp_pipeline(files, sr, cfg, sample_duration_sec=dur)
            self.assertIn(res["status"], ("PASS", "WARN"))
            self.assertEqual(res["metrics"]["tdoa_pairs"], 15)

    def test_run_auto_checks_skip_mic_and_pipeline(self):
        class DummyConfigMgr:
            def get_all(self):
                return {
                    "arecord_device": "hw:2,0",
                    "active_profile": "H8",
                    "sample_rate": 48000,
                    "num_mics_h8": 6,
                    "base_output_dir": tempfile.gettempdir(),
                }

        with patch.object(diagnostics, "check_alsa_device", return_value=diagnostics._make_check("CHK-03", "ALSA Audio Device", "PASS", "hw:2,0")), \
             patch.object(diagnostics, "check_hw_params", return_value=diagnostics._make_check("CHK-04", "Audio HW Parameters", "PASS", "12ch")):
            report = diagnostics.run_auto_checks(
                audio_system=None,
                config_manager=DummyConfigMgr(),
                options={
                    "check_os": True,
                    "check_audio_hw": True,
                    "check_capture": False,
                    "check_mic_health": False,
                    "check_pipeline": False,
                },
            )
            by_id = {c["id"]: c for c in report["checks"]}
            self.assertEqual(by_id["CHK-03"]["status"], "PASS")
            self.assertEqual(by_id["CHK-04"]["status"], "PASS")
            self.assertEqual(by_id["CHK-05"]["status"], "SKIP")
            self.assertEqual(by_id["CHK-06"]["status"], "SKIP")
            self.assertEqual(by_id["CHK-07"]["status"], "SKIP")


if __name__ == "__main__":
    unittest.main(verbosity=2)
