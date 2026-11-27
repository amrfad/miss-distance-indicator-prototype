"""
Tests for per-chunk in-flight microphone health detection and name-preserving TDOA.
Follows tests_automated conventions:
- Flat statements, Arrange-Act-Assert
- <= 3 assertions per test
- 'When {case}, then {expectation}' naming
"""

import numpy as np

from drone_system.audio.mic_health import assess_chunk_mic_health
from drone_system.core.config_manager import get_global_config_manager
from drone_system.tdoa.tdoa import calculate_all_tdoa


def _build_inflight_audio(seed: int = 42, n_samples: int = 4800) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(0.0, 0.04, size=(n_samples, 12))


def test_when_all_six_mics_healthy_then_none_excluded():
    # Arrange
    audio = _build_inflight_audio()
    active_indices = (4, 5, 6, 7, 8, 9)

    # Act
    report = assess_chunk_mic_health(audio, active_indices)

    # Assert
    assert len(report.healthy_names) == 6
    assert report.excluded_mics == {}


def test_when_one_mic_is_dead_then_only_dead_mic_is_excluded():
    # Arrange
    audio = _build_inflight_audio()
    audio[:, 6] = 0.0  # mic2 dead
    active_indices = (4, 5, 6, 7, 8, 9)

    # Act
    report = assess_chunk_mic_health(audio, active_indices)

    # Assert
    assert report.healthy_names == ["mic0", "mic1", "mic3", "mic4", "mic5"]
    assert "mic2" in report.excluded_mics
    assert "DEAD" in report.excluded_mics["mic2"]


def test_when_three_mics_are_dead_then_three_healthy_mics_are_preserved():
    # Arrange
    audio = _build_inflight_audio()
    audio[:, 6] = 0.0  # mic2 dead
    audio[:, 8] = 0.0  # mic4 dead
    audio[:, 9] = 0.0  # mic5 dead
    active_indices = (4, 5, 6, 7, 8, 9)

    # Act
    report = assess_chunk_mic_health(audio, active_indices)

    # Assert
    assert report.healthy_names == ["mic0", "mic1", "mic3"]
    assert len(report.excluded_mics) == 3


def test_when_one_mic_is_clipping_then_marked_as_clip():
    # Arrange
    audio = _build_inflight_audio()
    audio[:, 5] = 1.0  # mic1 rail clipping
    active_indices = (4, 5, 6, 7, 8, 9)

    # Act
    report = assess_chunk_mic_health(audio, active_indices)

    # Assert
    assert "mic1" not in report.healthy_names
    assert "CLIP" in report.excluded_mics["mic1"]


def test_when_one_mic_has_high_noise_then_marked_as_high_noise():
    # Arrange
    rng = np.random.default_rng(99)
    audio = _build_inflight_audio()
    audio[:, 7] = rng.normal(0.0, 0.35, size=audio.shape[0])  # mic3 +18 dB louder
    active_indices = (4, 5, 6, 7, 8, 9)

    # Act
    report = assess_chunk_mic_health(audio, active_indices)

    # Assert
    assert "mic3" not in report.healthy_names
    assert "HIGH_NOISE" in report.excluded_mics["mic3"]


def test_when_calculate_all_tdoa_called_with_mic_names_then_preserves_original_keys():
    # Arrange
    audio = _build_inflight_audio(n_samples=4800)
    cfg_mgr = get_global_config_manager()
    prev_method = cfg_mgr.get("tdoa_method")
    cfg_mgr.update({"tdoa_method": "gcc_phat"}, source="rest")

    # Act
    tdoa = calculate_all_tdoa(
        audio,
        fs=48000,
        channel_indices=[4, 5, 7, 8, 9],
        mic_names=["mic0", "mic1", "mic3", "mic4", "mic5"],
    )
    cfg_mgr.update({"tdoa_method": prev_method}, source="rest")

    # Assert
    assert len(tdoa) == 10
    assert "mic0-mic3" in tdoa
    assert all("mic2" not in k for k in tdoa.keys())
