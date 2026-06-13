"""M1 gates for the model-side RTTOV observation scheduler (design 2, 10).

Contract under test (``build_obs_schedule``):
- align each obs valid time to a checkpointed step boundary t_k = start + k*dt;
- bind within ``obs_time_tolerance``, otherwise REJECT (no interpolation;
  checkpoint-boundary hard precondition, design 2.2);
- the bound key k is the integer step index da_window passes to obs_adjoint.

The three named M1 cases (design M1 spec) plus edge cases that lock the
reject-don't-drop and out-of-window/misaligned-window preconditions.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from kdm6.obs.model_rttov_scheduler import (
    ObsSchedule,
    ObsWindowConfig,
    build_obs_schedule,
)

# A clean 10-step window: t_k = 0, 100, ..., 1000.
WIN = ObsWindowConfig(window_start_time=0.0, model_dt=100.0, window_end_time=1000.0)
TOL = 0.5


# --- M1 named cases ---------------------------------------------------------

def test_obs_schedule_exact_match():
    """obs valid time == a step end -> bound to that step index."""
    sched = build_obs_schedule(WIN, [0.0, 300.0, 1000.0], TOL)
    assert isinstance(sched, ObsSchedule)
    assert set(sched.by_step) == {0, 3, 10}
    assert sched.get(3) == [300.0]
    assert sched.get(0) == [0.0]
    assert sched.get(10) == [1000.0]


def test_obs_schedule_rejects_off_step_obs():
    """model_dt does not divide the obs offset -> hard reject (not a silent drop)."""
    with pytest.raises(ValueError, match="off-step"):
        build_obs_schedule(WIN, [150.0], TOL)


def test_obs_schedule_boundary_obs():
    """Observations exactly at the window start (k=0) and end (k=N) bind."""
    sched = build_obs_schedule(WIN, [0.0, 1000.0], TOL)
    assert sched.get(0) == [0.0]
    assert sched.get(10) == [1000.0]
    # Nothing bound in between.
    assert sched.get(5) is None


# --- tolerance edge ---------------------------------------------------------

def test_within_tolerance_binds():
    """|t_obs - t_k| just inside tolerance binds to the nearest step."""
    sched = build_obs_schedule(WIN, [100.4, 299.6], TOL)
    assert sched.get(1) == [100.4]
    assert sched.get(3) == [299.6]


def test_at_tolerance_boundary_binds_inclusive():
    """|t_obs - t_k| == tolerance binds (inclusive comparison)."""
    sched = build_obs_schedule(WIN, [100.5], TOL)
    assert sched.get(1) == [100.5]


def test_just_beyond_tolerance_rejects():
    """|t_obs - t_k| just over tolerance is off-step -> reject."""
    with pytest.raises(ValueError, match="off-step"):
        build_obs_schedule(WIN, [100.6], TOL)


# --- window bounds ----------------------------------------------------------

def test_out_of_window_after_end_rejects():
    """A well-aligned obs beyond window_end (k>N) is out of window -> reject."""
    with pytest.raises(ValueError, match=r"outside the window"):
        build_obs_schedule(WIN, [1100.0], TOL)


def test_out_of_window_before_start_rejects():
    """A well-aligned obs before window_start (k<0) is out of window -> reject."""
    with pytest.raises(ValueError, match=r"outside the window"):
        build_obs_schedule(WIN, [-100.0], TOL)


def test_misaligned_window_rejects():
    """window span not an integer multiple of model_dt -> reject at config time."""
    bad = ObsWindowConfig(window_start_time=0.0, model_dt=100.0, window_end_time=950.0)
    with pytest.raises(ValueError, match="integer number of model_dt"):
        build_obs_schedule(bad, [0.0], TOL)


def test_open_window_allows_large_k():
    """window_end_time=None leaves the upper bound open (only k>=0 enforced)."""
    open_win = ObsWindowConfig(window_start_time=0.0, model_dt=100.0, window_end_time=None)
    sched = build_obs_schedule(open_win, [5000.0], TOL)
    assert sched.get(50) == [5000.0]


# --- payload, batching, accessors ------------------------------------------

def test_multiple_obs_same_step_batched():
    """Several observations binding to the same step accumulate (order kept)."""
    sched = build_obs_schedule(WIN, [(200.0, "a"), (200.0, "b")], TOL)
    assert sched.get(2) == [(200.0, "a"), (200.0, "b")]


def test_payload_tuple_preserved():
    """(valid_time, payload) entries are preserved verbatim as the step payload."""
    payload = {"channels": [8, 9], "bt_obs": [250.0, 251.0]}
    sched = build_obs_schedule(WIN, [(400.0, payload)], TOL)
    assert sched.get(4) == [(400.0, payload)]


def test_entry_with_valid_time_attribute():
    """An object exposing .valid_time is accepted and preserved as payload."""

    class Obs:
        def __init__(self, vt):
            self.valid_time = vt

    o = Obs(500.0)
    sched = build_obs_schedule(WIN, [o], TOL)
    assert sched.get(5) == [o]


def test_get_returns_none_for_unbound_step():
    sched = build_obs_schedule(WIN, [300.0], TOL)
    assert sched.get(7) is None


def test_empty_obs_gives_empty_schedule():
    sched = build_obs_schedule(WIN, [], TOL)
    assert sched.by_step == {}
    assert sched.get(0) is None


# --- guards -----------------------------------------------------------------

def test_nonpositive_dt_raises():
    bad = ObsWindowConfig(window_start_time=0.0, model_dt=0.0, window_end_time=1000.0)
    with pytest.raises(ValueError, match="model_dt must be a finite value > 0"):
        build_obs_schedule(bad, [0.0], TOL)


def test_inf_model_dt_raises():
    bad = ObsWindowConfig(window_start_time=0.0, model_dt=float("inf"), window_end_time=1000.0)
    with pytest.raises(ValueError, match="model_dt must be a finite value > 0"):
        build_obs_schedule(bad, [0.0], TOL)


def test_negative_tolerance_raises():
    with pytest.raises(ValueError, match="obs_time_tolerance must be a finite value >= 0"):
        build_obs_schedule(WIN, [0.0], -1.0)


@pytest.mark.parametrize("bad_tol", [float("inf"), float("nan")])
def test_non_finite_tolerance_raises(bad_tol):
    """A non-finite tolerance would make |delta| > tol always False, silently
    disabling off-step/misalignment rejection -> must be rejected up front."""
    with pytest.raises(ValueError, match="obs_time_tolerance must be a finite value >= 0"):
        build_obs_schedule(WIN, [150.0], bad_tol)


def test_bad_entry_type_raises():
    with pytest.raises(TypeError, match="obs entry must be"):
        build_obs_schedule(WIN, [object()], TOL)


# --- robustness: str/bytes silent-misbind guard (review F2/F8) --------------

@pytest.mark.parametrize("bad_entry", ["0", "300.0", b"\x00\x01", bytearray(b"\x01")])
def test_str_bytes_entry_rejected(bad_entry):
    """str/bytes are indexable -> must be rejected, not silently misbound."""
    with pytest.raises(TypeError, match="obs entry must be"):
        build_obs_schedule(WIN, [bad_entry], TOL)


def test_valid_time_none_rejected():
    """An object exposing .valid_time=None is malformed -> reject (not fall through)."""

    class Obs:
        valid_time = None

    with pytest.raises(TypeError, match=r"\.valid_time=None"):
        build_obs_schedule(WIN, [Obs()], TOL)


def test_valid_time_zero_accepted():
    """.valid_time == 0.0 is a legitimate boundary time, not 'missing'."""

    class Obs:
        valid_time = 0.0

    sched = build_obs_schedule(WIN, [Obs()], TOL)
    assert sched.get(0) is not None


# --- robustness: non-finite times (review F3/F9) ----------------------------

@pytest.mark.parametrize("bad_time", [float("inf"), float("-inf"), float("nan")])
def test_non_finite_obs_time_rejected(bad_time):
    """+/-inf/nan obs times raise a ValueError (not a leaked OverflowError/cast)."""
    with pytest.raises(ValueError, match="finite"):
        build_obs_schedule(WIN, [bad_time], TOL)


def test_non_finite_window_end_rejected():
    bad = ObsWindowConfig(window_start_time=0.0, model_dt=100.0, window_end_time=float("nan"))
    with pytest.raises(ValueError, match="finite"):
        build_obs_schedule(bad, [0.0], TOL)


# --- robustness: tz-aware UTC enforcement (review F4/F7) --------------------

def test_tz_naive_datetime_rejected():
    """A tz-naive datetime silently uses host LOCAL tz -> reject loudly."""
    naive_start = datetime(2026, 1, 1, 0, 0, 0)  # no tzinfo
    win = ObsWindowConfig(window_start_time=naive_start, model_dt=3600.0)
    with pytest.raises(ValueError, match="tz-aware UTC"):
        build_obs_schedule(win, [naive_start], TOL)


def test_mixed_naive_aware_datetime_rejected():
    """Mixing a naive window start with an aware obs time is the silent-misbind trap."""
    aware_start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    win = ObsWindowConfig(window_start_time=aware_start, model_dt=3600.0)
    naive_obs = datetime(2026, 1, 1, 2, 0, 0)  # no tzinfo
    with pytest.raises(ValueError, match="tz-aware UTC"):
        build_obs_schedule(win, [naive_obs], TOL)


# --- datetime support -------------------------------------------------------

def test_datetime_valid_times():
    """UTC datetime valid times align on an hourly window."""
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=6)
    win = ObsWindowConfig(window_start_time=start, model_dt=3600.0, window_end_time=end)
    sched = build_obs_schedule(win, [start + timedelta(hours=2)], TOL)
    assert sched.get(2) is not None


def test_datetime_off_step_rejects():
    start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=6)
    win = ObsWindowConfig(window_start_time=start, model_dt=3600.0, window_end_time=end)
    with pytest.raises(ValueError, match="off-step"):
        build_obs_schedule(win, [start + timedelta(hours=2, minutes=30)], TOL)
