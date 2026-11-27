"""
Tests for degraded-mode SSL localization (5, 4, 3, and <3 active mics)
with non-sequential microphone names and NLLS 2D fallback.
"""

import numpy as np
import pytest

from darat.localization import ssl_registry
from darat.localization.builtin_ssl import nlls_2d, rotating_multilat_2d, chan_ho_2d
from darat.localization.process_json_tdoa import process_event_tdoa
from tests_automated.helpers.tdoa_factories import (
    PROTOTYPE_MIC_POSITIONS,
    build_ideal_tdoa,
)


@pytest.fixture(autouse=True)
def setup_registry():
    ssl_registry.initialize()


def _subset_mics(names):
    return {m: PROTOTYPE_MIC_POSITIONS[m] for m in names}


def test_when_mic2_missing_then_rotating_multilat_2d_solves_without_keyerror():
    # Arrange
    source_xy = [4.0, 3.0]
    five_mics = _subset_mics(["mic0", "mic1", "mic3", "mic4", "mic5"])
    event_data = {"tdoa": build_ideal_tdoa([4.0, 3.0, 0.0], five_mics)}

    # Act
    est, n_sub, _ = rotating_multilat_2d.solve(event_data, five_mics, {"speed_of_sound": 343.0})
    err = np.linalg.norm(np.array(est) - np.array(source_xy))

    # Assert
    assert est is not None
    assert n_sub == 5
    assert err < 0.15


def test_when_mic2_and_mic4_missing_then_chan_ho_2d_solves_accurately():
    # Arrange
    source_xy = [3.5, -4.0]
    four_mics = _subset_mics(["mic0", "mic1", "mic3", "mic5"])
    event_data = {"tdoa": build_ideal_tdoa([3.5, -4.0, 0.0], four_mics)}

    # Act
    est, _, _ = chan_ho_2d.solve(event_data, four_mics, {"speed_of_sound": 343.0})
    err = np.linalg.norm(np.array(est) - np.array(source_xy))

    # Assert
    assert est is not None
    assert err < 0.25


def test_when_three_mics_active_then_nlls_2d_solves_and_flags_degraded():
    # Arrange
    source_xy = [0.0, 4.0]
    three_mics = _subset_mics(["mic0", "mic1", "mic3"])
    event_data = {"tdoa": build_ideal_tdoa([0.0, 4.0, 0.0], three_mics)}

    # Act
    est, n_pairs, info = nlls_2d.solve(event_data, three_mics, {"speed_of_sound": 343.0})
    err = np.linalg.norm(np.array(est) - np.array(source_xy))

    # Assert
    assert est is not None
    assert n_pairs == 3
    assert err < 0.25


def test_when_process_event_tdoa_receives_three_mics_then_falls_back_to_nlls_2d():
    # Arrange
    source_xy = [0.0, 4.0]
    three_mics = _subset_mics(["mic0", "mic1", "mic3"])
    event_data = {
        "active_mics": ["mic0", "mic1", "mic3"],
        "excluded_mics": {"mic2": "DEAD", "mic4": "DEAD", "mic5": "DEAD"},
        "tdoa": build_ideal_tdoa([0.0, 4.0, 0.0], three_mics),
    }

    # Act
    est, _, info = process_event_tdoa(event_data, PROTOTYPE_MIC_POSITIONS, method="rotating_multilat_2d")
    err = np.linalg.norm(np.array(est) - np.array(source_xy))

    # Assert
    assert est is not None
    assert err < 0.25
    assert any("DEGRADED MODE (3 mics)" in line for line in (info or []))


def test_when_rotating_multilat_3d_receives_four_mics_then_falls_back_to_nlls_2d():
    # Arrange
    source_xy = [-3.0, 5.0]
    four_mics = _subset_mics(["mic0", "mic1", "mic3", "mic5"])
    event_data = {
        "active_mics": ["mic0", "mic1", "mic3", "mic5"],
        "tdoa": build_ideal_tdoa([-3.0, 5.0, 0.0], four_mics),
    }

    # Act
    est, _, info = process_event_tdoa(event_data, PROTOTYPE_MIC_POSITIONS, method="rotating_multilat")
    err = np.linalg.norm(np.array(est) - np.array(source_xy))

    # Assert
    assert est is not None
    assert err < 0.05
    assert any("DEGRADED MODE (4 mics)" in line for line in (info or []))


def test_when_fewer_than_three_mics_active_then_process_event_tdoa_returns_none():
    # Arrange
    event_data = {
        "active_mics": ["mic0", "mic1"],
        "excluded_mics": {"mic2": "DEAD", "mic3": "DEAD", "mic4": "DEAD", "mic5": "DEAD"},
        "tdoa": {},
    }

    # Act
    est, count, info = process_event_tdoa(event_data, PROTOTYPE_MIC_POSITIONS, method="rotating_multilat_2d")

    # Assert
    assert est is None
    assert count == 0
    assert any("Insufficient" in line for line in (info or []))
