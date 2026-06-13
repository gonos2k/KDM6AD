"""P1 -- observation/model-step alignment scheduler (design 2, 10; M1 gate).

Aligns each observation valid time to a checkpointed model step-end boundary
``t_k = window_start + k * model_dt`` (k = 0 .. N). No time interpolation
(principle 3): an observation that does not land on a step boundary within
``obs_time_tolerance`` is REJECTED, because the window adjoint can only attach
an observation adjoint at a checkpointed step (design 2.2 -- the checkpoint
boundary is a hard precondition, not a loss).

The bound step index ``k`` is the SAME integer ``t`` that ``da_window`` passes
to ``obs_adjoint(t, x_t)`` (da_window.py:148 ``Callable[[int, State], ...]``;
:162 ``x_t`` = state before step t for t<T, final for t=T). So
``obs_adjoint_callback`` consults ``ObsSchedule.get(k)`` directly and the
window driver accumulates the returned covector via ``_add_states``.
"""
from __future__ import annotations

import math
import numbers
from datetime import datetime
from typing import NamedTuple


def _as_seconds(t) -> float:
    """Return a finite float seconds for a numeric or ``datetime`` valid time (UTC).

    ``datetime`` is reduced via ``.timestamp()`` (POSIX seconds) and MUST be
    tz-aware UTC: a tz-naive datetime is rejected because ``.timestamp()`` would
    silently interpret it in the host LOCAL timezone and misbind when mixed with
    aware times (design 2.1, "UTC explicit"). Numeric values (including numpy
    scalars) pass through ``float``. A non-finite result is rejected so a caller
    catching the documented ``ValueError`` sees all bad inputs uniformly instead
    of a leaked ``OverflowError`` (inf) or opaque NaN-cast error downstream.
    """
    if isinstance(t, datetime):
        if t.tzinfo is None or t.tzinfo.utcoffset(t) is None:
            raise ValueError(
                "datetime valid times must be tz-aware UTC; a naive datetime "
                "uses the host LOCAL tz and silently misbinds when mixed "
                "(design 2.1). Attach tzinfo=timezone.utc.")
        s = t.timestamp()
    else:
        s = float(t)
    if not math.isfinite(s):
        raise ValueError(f"valid time / window bound must be finite; got {s} (rejected)")
    return s


def _obs_valid_time(entry) -> float:
    """Extract the valid time (seconds) from one observation entry.

    Accepts a bare time (number/``datetime``), an object exposing
    ``.valid_time``, or a ``(valid_time, payload)`` sequence. ``str``/``bytes``
    are rejected up front: they are indexable, so without an explicit guard a
    string entry would fall through to ``entry[0]`` and silently misbind a
    single character as the time (violating the reject-don't-drop contract). An
    object whose ``.valid_time`` is ``None`` is a malformed obs and is rejected
    rather than falling through to the sequence path. The whole ``entry`` is
    preserved as the per-step payload elsewhere; only its valid time is read here.
    """
    if isinstance(entry, (datetime, numbers.Number)):
        return _as_seconds(entry)
    if isinstance(entry, (str, bytes, bytearray)):
        raise TypeError(
            "obs entry must be a time, expose .valid_time, or be a "
            f"(valid_time, payload) sequence; got {type(entry).__name__}")
    if hasattr(entry, "valid_time"):
        vt = entry.valid_time
        if vt is None:
            raise TypeError("obs entry exposes .valid_time=None (malformed obs)")
        return _as_seconds(vt)
    try:
        return _as_seconds(entry[0])
    except (TypeError, KeyError, IndexError, ValueError):
        raise TypeError(
            "obs entry must be a time, expose .valid_time, or be a "
            f"(valid_time, payload) sequence; got {type(entry).__name__}")


def _nearest_step(t_seconds: float, start_seconds: float, dt: float) -> int:
    """Nearest integer step index for ``t`` (round half up, deterministic).

    Half-up (``floor(x + 0.5)``) avoids banker's-rounding surprises; the
    exact half-way case is an off-step observation that the tolerance check
    rejects regardless of which neighbour it snaps to.
    """
    return int(math.floor((t_seconds - start_seconds) / dt + 0.5))


class ObsWindowConfig(NamedTuple):
    """Assimilation-window timing (design 4.1). Times UTC; dt/tolerance seconds.

    ``window_end_time`` may be ``None`` to leave the upper bound open (only
    ``k >= 0`` is enforced); otherwise ``N = round((end - start) / model_dt)``
    bounds the admissible step indices to ``[0, N]``. NOTE: in open mode the
    upper bound is delegated to the caller -- ``da_window`` only calls
    ``obs_adjoint(t, x_t)`` for ``t`` in ``[0, T]`` (T = len(forcings)), so an
    obs bound to ``k > T`` would never be assimilated. To preserve
    reject-don't-drop, a caller feeding ``da_window`` should pass a finite
    ``window_end_time = window_start + T * model_dt`` so out-of-window
    observations are rejected at build time.
    """
    window_start_time: object              # numeric POSIX seconds or datetime (UTC)
    model_dt: float                        # step-end interval [s], > 0
    window_end_time: object | None = None  # numeric/datetime (UTC) or None (open)


class ObsSchedule(NamedTuple):
    """Step-index binding of aligned observations (design 4.1)."""
    # step_index k -> list of obs entries (payload) bound to that step.
    by_step: dict

    def get(self, step_index):
        """``schedule.get(t)`` contract (design 10/14.3).

        Returns the LIST of obs entries bound to ``step_index`` (a step may
        carry several observation footprints), or ``None`` if no obs is bound.
        The P6 callback iterates ``compute_obs_loss`` over the list and sums.
        """
        return self.by_step.get(step_index)


def build_obs_schedule(window_cfg, obs_valid_times, obs_time_tolerance) -> ObsSchedule:
    """Bind each observation to ``t_k = window_start + k * model_dt`` (design 2.1).

    contract (2.1 / 2.2)::

        bind   : exists k in [0, N] with |t_obs - t_k| <= obs_time_tolerance
                 -> append entry to by_step[k]
        reject : otherwise -> raise ValueError (off-step / out-of-window).
                 No interpolation; the checkpoint boundary is a hard
                 precondition, and silently dropping an observation would be
                 silent data loss in the assimilation.

    ``window_cfg`` is duck-typed: it must expose ``window_start_time`` and
    ``model_dt`` (and optionally ``window_end_time``); ``ObsWindowConfig`` fits.
    ``obs_valid_times`` is an iterable of observation entries (see
    ``_obs_valid_time`` for accepted shapes). Returns an ``ObsSchedule`` whose
    ``by_step[k]`` is the list of entries bound to step ``k`` (several
    observations may share a step; input order is preserved).
    """
    start_s = _as_seconds(window_cfg.window_start_time)
    dt = float(window_cfg.model_dt)
    if not (math.isfinite(dt) and dt > 0.0):
        raise ValueError(f"model_dt must be a finite value > 0 (got {dt})")
    tol = float(obs_time_tolerance)
    if not (math.isfinite(tol) and tol >= 0.0):
        # A non-finite tolerance silently disables rejection: |delta| > inf and
        # |delta| > nan are both False, so every off-step / misaligned obs would
        # bind -- the exact reject-don't-drop collapse this scheduler forbids.
        raise ValueError(
            f"obs_time_tolerance must be a finite value >= 0 (got {tol})")

    end = getattr(window_cfg, "window_end_time", None)
    n_steps: int | None = None
    if end is not None:
        end_s = _as_seconds(end)
        span = end_s - start_s
        n_steps = _nearest_step(end_s, start_s, dt)
        if n_steps < 0 or abs(span - n_steps * dt) > tol:
            raise ValueError(
                "window is not an integer number of model_dt steps "
                f"(span={span}, model_dt={dt}, tol={tol}); "
                "obs cannot bind to a checkpoint boundary (design 2.2).")

    by_step: dict = {}
    for entry in obs_valid_times:
        t_obs_s = _obs_valid_time(entry)
        k = _nearest_step(t_obs_s, start_s, dt)
        t_k = start_s + k * dt
        if abs(t_obs_s - t_k) > tol:
            raise ValueError(
                "off-step observation: valid time does not align to a model "
                f"step boundary within tolerance (t_obs={t_obs_s}, nearest "
                f"t_k={t_k}, |delta|={abs(t_obs_s - t_k)} > tol={tol}); "
                "model_dt must integer-divide the obs cadence (design 2.2).")
        if k < 0 or (n_steps is not None and k > n_steps):
            raise ValueError(
                f"observation step index k={k} is outside the window "
                f"[0, {n_steps}] (t_obs={t_obs_s}).")
        by_step.setdefault(k, []).append(entry)

    return ObsSchedule(by_step=by_step)
