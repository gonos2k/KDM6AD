"""Focused tests for predeclared slot choice and fixed-point geolocation guards."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np


SCRIPT = Path(__file__).with_name("heldout_l1b.py")
spec = importlib.util.spec_from_file_location("heldout_l1b", SCRIPT)
heldout = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(heldout)


def objects_for(date: str, channels: set[str]) -> dict[str, dict[str, dict]]:
    return {date + stamp: {channel: {"etag": f"{channel}-{stamp}"}
                           for channel in channels}
            for stamp in ("0554", "0556", "0558")}


def test_exact_complete_slot_wins_without_considering_other_values():
    date = "20250720"
    rows = objects_for(date, set(heldout.CLEAN_IR_CHANNELS))
    result = heldout.choose_slot(rows, date)
    assert result["selected_slot"] == date + "0556"
    assert result["rule"] == "EXACT_SLOT_COMPLETE"


def test_extra_nonanalysis_channels_do_not_hide_a_complete_thermal_slot():
    # The actual LA020GE manifest includes 12 bands, while this reader needs 9.
    # Completeness must not demand equality with the manifest's entire band set.
    date = "20250720"
    rows = objects_for(date, set(heldout.CLEAN_IR_CHANNELS) | {"sw038", "nr013", "nr016"})
    result = heldout.choose_slot(rows, date)
    assert result["selected_slot"] == date + "0556"
    assert result["rule"] == "EXACT_SLOT_COMPLETE"
    assert result["exact_slot_missing_channels"] == []


def test_incomplete_exact_slot_uses_nearest_complete_timestamp_tie_earlier():
    date = "20250721"
    expected = set(heldout.CLEAN_IR_CHANNELS)
    rows = objects_for(date, expected)
    del rows[date + "0556"]["ir096"]
    result = heldout.choose_slot(rows, date)
    assert result["selected_slot"] == date + "0554"
    assert result["rule"] == "NEAREST_COMPLETE_NOMINAL_SLOT_TIMESTAMP_ONLY"
    assert result["exact_slot_missing_channels"] == ["ir096"]


def test_no_complete_slot_in_window_returns_missing_scene():
    date = "20250720"
    expected = set(heldout.CLEAN_IR_CHANNELS)
    rows = {date + "0544": {channel: {} for channel in expected},
            date + "0608": {channel: {} for channel in expected}}
    result = heldout.choose_slot(rows, date)
    assert result["selected_slot"] is None
    assert result["rule"] == "MISSING_SCENE_NO_COMPLETE_SLOT_WITHIN_10_MIN"


def test_geolocation_nearest_ignores_quality_and_rejects_missing_geometry():
    lat = np.array([np.nan, 35.4156, 35.5])
    lon = np.array([np.nan, 122.1433, 122.2])
    idx, finite, distance = heldout.nearest_geolocated(lat, lon)
    assert idx == 1
    assert finite.tolist() == [False, True, True]
    assert distance < 10.0
    missing_idx, missing_finite, missing_distance = heldout.nearest_geolocated(
        np.array([np.nan, np.nan]), np.array([np.nan, np.nan]))
    assert missing_idx is None
    assert not missing_finite.any()
    assert np.isinf(missing_distance)
