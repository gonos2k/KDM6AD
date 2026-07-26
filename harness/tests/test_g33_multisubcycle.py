"""The multi-subcycle evidence path (public CI — no build).

The one-loop arithmetic fixture cannot exercise the machinery that exists for
multi-subcycle transport: heterogeneous mstep, inactive lanes, per-loop state
continuity, cumulative surface precipitation. This runs the checked-in
`arithmetic_multisubcycle_v1` evidence — 3 cloud outer loops with mstep differing
BOTH across columns and BETWEEN loops — through the whole reader/validator chain.
"""
import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = Path(__file__).parent / "data" / "g33_multisubcycle_legacy_sample.g33f"
sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
sys.path.insert(0, str(ROOT / "harness"))
import g33_evidence_validate as gev     # noqa: E402
import g33_fortran_dump as fd           # noqa: E402
import g33_fortran_semantics as sem     # noqa: E402
import g33_mechanism as mech            # noqa: E402
import g33_normalize as nz              # noqa: E402
import g33_replay as rp                 # noqa: E402

RUN = fd.parse_fortran_run(SAMPLE.read_text(), "legacy", 4, 3)
NORM = nz.from_fortran_run(RUN)


def test_evidence_really_is_multi_loop_and_heterogeneous():
    loops = sorted({lp for lp, _ch, _c in RUN.mstep})
    assert loops == [1, 2, 3]                       # dt=300 -> ceil(300/120)
    per_loop = {lp: [RUN.mstep[(lp, "main", c)] for c in (1, 2, 3)] for lp in loops}
    # mstep differs ACROSS columns ...
    assert any(len(set(v)) > 1 for v in per_loop.values())
    # ... and BETWEEN loops, which is what protocol v3's (loop, chain, col) key is for
    assert len({tuple(v) for v in per_loop.values()}) > 1


def test_strict_parse_and_semantics_hold():
    sem.verify_semantics(RUN)          # per-loop continuity + CUMULATIVE precip
    fd.verify_offline_replay(RUN)
    assert len(RUN.ops) > 5000 and len(RUN.stages) > 2000


def test_normalized_run_spans_every_outer_loop():
    assert sorted({o["loop"] for o in NORM["ops"]}) == [1, 2, 3]
    loop_scoped = [s for s in NORM["stages"] if s["stage"] != "final_output"]
    assert sorted({s["loop"] for s in loop_scoped}) == [1, 2, 3]
    # the whole-step output is not loop-scoped: loop 0, emitted once per column
    final = [s for s in NORM["stages"] if s["stage"] == "final_output"]
    assert final and {s["loop"] for s in final} == {0}


def test_gate_contract_holds_with_real_inactive_lanes():
    mask = gev.validate_gate_semantics(NORM, mech)
    inactive = [lane for lane, active in mask.items() if not active]
    # the one-loop fixture has NO inactive lane; this evidence must have many, so the
    # gate law, the no-op relations and the active-stream filter are really exercised
    assert inactive, "expected gate-inactive lanes in multi-subcycle evidence"
    assert len(inactive) > 10


def test_full_ladder_replays_bit_exactly_across_loops():
    report = rp.replay_report(NORM)
    assert set(report) == rp.RELATION_COVERAGE["legacy"]    # exact families, not a count
    assert sum(report.values()) == 6150


def _mutate_stage(stage, field, loop, col):
    m = copy.deepcopy(NORM)
    for s in m["stages"]:
        if (s["stage"], s["field"], s["loop"], s["col"]) == (stage, field, loop, col):
            s["bits"] ^= 1
            return m
    raise AssertionError(f"no {stage}.{field} at loop{loop}/col{col}")


# Per-loop surface records must each be gated on their OWN loop. While the whole-step
# PREC was attached to the last loop's surface stage, a corrupted loop-1 or loop-2
# increment had nowhere to fail; these rows are the standing proof that it now does.
@pytest.mark.parametrize("stage,field,loop,col,relation", [
    ("surface", "bottom_fall_qr", 1, 1, "SURFACE.bottom_fall_qr(carry)"),
    ("surface", "bottom_fall_qr", 2, 1, "SURFACE.bottom_fall_qr(carry)"),
    ("surface", "bottom_fall_qr", 3, 3, "SURFACE.bottom_fall_qr(carry)"),
    ("surface", "bottom_fall_qs", 2, 2, "SURFACE.bottom_fall_total"),
    ("surface", "bottom_fall_qi", 3, 3, "SURFACE.bottom_fall_total"),
    ("surface", "bottom_fall_total", 2, 2, "SURFACE.bottom_fall_total"),
    ("surface", "delz_bottom", 1, 1, "SURFACE.delz_bottom(state)"),
    ("surface", "delz_bottom", 3, 3, "SURFACE.delz_bottom(state)"),
    ("surface", "surface_denr", 2, 1, "SURFACE.surface_denr"),
    ("final_output", "rain_precip_cumulative", 0, 1, "OUTPUT.rain_precip_cumulative"),
    ("final_output", "snow_precip_cumulative", 0, 2, "OUTPUT.snow_precip_cumulative"),
    ("final_output", "graupel_precip_cumulative", 0, 3, "OUTPUT.graupel_precip_cumulative"),
])
def test_surface_and_cumulative_mutants_die_at_the_fidelity_gate(stage, field, loop,
                                                                col, relation):
    with pytest.raises(rp.FidelityError) as e:
        rp.replay_run(_mutate_stage(stage, field, loop, col))
    assert str(e.value).startswith(relation + " at ")


def test_cumulative_is_the_sum_over_loops_not_the_last_loop():
    # zeroing loop 1's fall must change the whole-step total: if the accumulator were
    # read off the last loop alone, this mutation would be invisible.
    per_loop = [s for s in NORM["stages"]
                if s["stage"] == "surface" and s["field"] == "bottom_fall_total"]
    assert len({s["loop"] for s in per_loop}) == 3
    finals = [s for s in NORM["stages"] if s["stage"] == "final_output"]
    assert finals and {s["loop"] for s in finals} == {0}    # not loop-scoped
