#!/usr/bin/env python3
"""Pure-Python contracts for the focused G3.3 surface self-check."""
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_dump as gd
import g33_expectation as ge
import g33_surface_selfcheck as gss


def f32(values):
    return np.asarray(values, dtype=np.float32)


def test_recompute_surface_matches_left_associated_f32_expression():
    qr = f32([1.0e-4, 3.0e-4, 7.0e-4])
    qs = f32([2.0e-5, 4.0e-5, 6.0e-5])
    qg = f32([1.0e-5, 2.0e-5, 3.0e-5])
    qi = f32([3.0e-5, 2.0e-5, 1.0e-5])
    dz = f32([310.0, 420.0, 530.0])

    got = gss.recompute_surface(qr, qs, qg, qi, dz, dtcld=20.0)

    total = (qr + qs).astype(np.float32)
    total = (total + qg).astype(np.float32)
    total = (total + qi).astype(np.float32)
    snow = (qs + qi).astype(np.float32)

    def inc(fall):
        out = np.maximum(fall, np.float32(0.0)).astype(np.float32)
        out = (out * dz).astype(np.float32)
        out = (out / np.float32(1000.0)).astype(np.float32)
        out = (out * np.float32(20.0)).astype(np.float32)
        return (out * np.float32(1000.0)).astype(np.float32)

    np.testing.assert_array_equal(got["bottom_fall_total"], total)
    np.testing.assert_array_equal(got["rain_increment"], inc(total))
    np.testing.assert_array_equal(got["snow_increment"], inc(snow))
    np.testing.assert_array_equal(got["graupel_increment"], inc(qg))


def test_qi_omission_changes_rain_but_not_graupel_subset():
    qr = f32([1.0e-4, 2.0e-4])
    qs = f32([3.0e-5, 4.0e-5])
    qg = f32([5.0e-5, 6.0e-5])
    qi = f32([7.0e-5, 8.0e-5])
    dz = f32([300.0, 400.0])

    full = gss.recompute_surface(qr, qs, qg, qi, dz)
    omitted = gss.recompute_surface(qr, qs, qg, np.zeros_like(qi), dz)

    assert np.any(full["rain_increment"].view(np.uint32) !=
                  omitted["rain_increment"].view(np.uint32))
    np.testing.assert_array_equal(full["graupel_increment"],
                                  omitted["graupel_increment"])


@pytest.mark.parametrize(
    "args, message",
    [
        ((f32([1, 2]), f32([1]), f32([1, 2]), f32([1, 2]), f32([1, 2])),
         "different shapes"),
        ((f32([-1, 2]), f32([1, 2]), f32([1, 2]), f32([1, 2]), f32([1, 2])),
         "negative"),
        ((f32([1, np.inf]), f32([1, 2]), f32([1, 2]), f32([1, 2]), f32([1, 2])),
         "non-finite"),
        ((f32([1, 2]), f32([1, 2]), f32([1, 2]), f32([1, 2]), f32([1, 0])),
         "non-positive"),
    ],
)
def test_recompute_surface_fails_closed_on_invalid_operands(args, message):
    with pytest.raises(gd.G33Corruption, match=message):
        gss.recompute_surface(*args)


def test_surface_schedule_has_two_main_substeps_and_one_surface_container():
    index = ge.run_index(gss._schedule("conservative"))
    assert [c["container_id"] for c in index["containers"]] == [
        "L1_main_n1",
        "L1_main_n2",
        "L1_surface",
    ]
    surface = index["containers"][-1]
    assert surface["record_count"] == 9
    assert surface["last_op_seq_id"] - surface["first_op_seq_id"] + 1 == 9
