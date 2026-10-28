from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from harness.analyze_qnc_face_residual_probe import analyze_case
from harness.native_qnc_advect_qi_trace_records import read_qnc_producer_trace
from harness.native_qnc_representative_trace_records import read_representative_trace


ROOT = Path(__file__).resolve().parents[1] / "evidence"


def _control():
    trace = read_qnc_producer_trace(
        ROOT / "native_qnc_advect_qi_2026-10-28/data/control/qnc_producer.tsv")
    state = read_representative_trace(
        ROOT / "native_qnc_representative_boundaries_2026-10-28/data/control/representative_moments.tsv")
    return trace, state


def test_rejects_post_face_that_does_not_match_applied_scale():
    trace, state = _control()
    key = (3, "RK3_PD_POST_LIMIT_FACES", 113, 12, 70, "FX_EAST")
    values = dict(trace.values)
    values[key] ^= 1
    with pytest.raises(ValueError, match="target-scaled outgoing face"):
        analyze_case(replace(trace, values=values), state, case="control")


def test_rejects_low_order_face_changed_by_limiter():
    trace, state = _control()
    key = (3, "RK3_PD_POST_LIMIT_FACES", 113, 12, 70, "FZ_LOW_BOTTOM")
    values = dict(trace.values)
    values[key] ^= 1
    with pytest.raises(ValueError, match="low-order face changed"):
        analyze_case(replace(trace, values=values), state, case="control")


def test_rejects_scale_incompatible_with_recorded_limiter_inputs():
    trace, state = _control()
    values = dict(trace.values)
    for stage in ("RK3_PD_PRE_LIMIT", "RK3_PD_LIMIT_CELL"):
        values[(3, stage, 113, 12, 70, "PH_LOW")] += 100
    with pytest.raises(ValueError, match="scale differs from source-compatible"):
        analyze_case(replace(trace, values=values), state, case="control")
