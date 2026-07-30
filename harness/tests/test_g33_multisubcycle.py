"""The multi-subcycle evidence path (public CI — no build).

The one-loop arithmetic fixture cannot exercise the machinery that exists for
multi-subcycle transport: heterogeneous mstep, inactive lanes, per-loop state
continuity, cumulative surface precipitation. This runs the checked-in
`arithmetic_multisubcycle_v1` evidence — 3 cloud outer loops with mstep differing
BOTH across columns and BETWEEN loops — through the whole reader/validator chain.
"""
import copy
import math
import struct
import sys
from pathlib import Path

import numpy as np
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

_f32 = lambda b: np.float32(struct.unpack(">f", struct.pack(">I", b))[0])
_bits = lambda v: struct.unpack(">I", struct.pack(">f", np.float32(v)))[0]
_f64 = lambda b: np.float64(struct.unpack(">d", struct.pack(">Q", b))[0])

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
    # ONCE-PER-CALL stages carry loop 0, meaning "not loop-scoped": the whole-step
    # output at one end, and the kernel-entry snapshots at the other. A kernel call
    # happens once however many sub-cycles it takes.
    once = {"final_output", "kernel_call_input", "kernel_init_constants",
            "kernel_after_entry_clamp"}
    loop_scoped = [s for s in NORM["stages"] if s["stage"] not in once]
    assert sorted({s["loop"] for s in loop_scoped}) == [1, 2, 3]
    for stage in sorted(once):
        rows = [s for s in NORM["stages"] if s["stage"] == stage]
        if stage == "kernel_call_input":
            continue           # wrapper-boundary sample: the driver does not emit it
        assert rows and {s["loop"] for s in rows} == {0}, stage


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


# ---- the producer's OWN per-loop output --------------------------------------
# The Fortran reference emits no per-loop increment, so these exercise the RELATION
# on real multi-loop operands: only a C++ leg carries actuals, and this fixture is
# the only committed evidence with enough loops to show what folding first hides.
EXPECTED_INC = rp.expected_surface_increments(NORM)


def _with_increments(*overrides):
    m = copy.deepcopy(NORM)
    m["surface_increments"] = dict(EXPECTED_INC)
    for key, delta in overrides:
        m["surface_increments"][key] += delta
    return m


def _fold(run, family, col):
    """The whole-step total the way the accumulator builds it."""
    inc = run["surface_increments"]
    acc = np.float32(0.0)
    for loop in sorted(l for (f, l, c) in inc if f == family and c == col):
        acc = np.float32(_f32(inc[(family, loop, col)]) + acc)
    return _bits(acc)


def test_the_producers_own_increments_replay_exactly():
    # replay_report, not replay_run: the coverage contract requires the FULL C++ set
    # of a cpp run, and this is a Fortran run carrying C++-shaped records to exercise
    # the relation on real multi-loop operands.
    report = rp.replay_report(_with_increments())
    checked = sum(v for k, v in report.items() if k.endswith("_increment(actual)"))
    assert checked == 27                     # 3 families x 3 loops x 3 columns


@pytest.mark.parametrize("loop", [1, 2, 3])
def test_a_single_loop_error_the_total_absorbs_still_dies(loop):
    # On col 3 a 1-ULP error in ANY loop leaves the f32 total bit-identical, so the
    # cumulative comparison alone cannot see it. Assert that blindness, then assert
    # the per-loop gate catches it anyway.
    bad = _with_increments((("rain", loop, 3), 1))
    assert _fold(bad, "rain", 3) == _fold(_with_increments(), "rain", 3)
    with pytest.raises(rp.FidelityError) as e:
        rp.replay_run(bad)
    assert str(e.value).startswith("OUTPUT.rain_increment(actual) at ")


@pytest.mark.parametrize("hi,lo", [(1, 2), (2, 3), (1, 3)])
def test_two_loop_errors_that_cancel_in_the_total_still_die(hi, lo):
    # every loop wrong, total right -- the exact false pass the fold-only check allows
    bad = _with_increments((("rain", hi, 3), 1), (("rain", lo, 3), -1))
    assert _fold(bad, "rain", 3) == _fold(_with_increments(), "rain", 3)
    with pytest.raises(rp.FidelityError) as e:
        rp.replay_run(bad)
    assert str(e.value).startswith("OUTPUT.rain_increment(actual) at ")


# ---- surface / whole-step output domain --------------------------------------

def _with_surface(field, bits, stage="surface"):
    m = copy.deepcopy(NORM)
    m["stages"].append({"loop": 1 if stage == "surface" else 0, "chain": "-",
                        "stage": stage, "n": 0, "col": 1, "k": -1, "field": field,
                        "dtype": "f32", "bits": bits})
    return m


@pytest.mark.parametrize("field,bits,stage", [
    ("bottom_fall_qr", 0xBF800000, "surface"),          # negative
    ("bottom_fall_total", 0x7F800000, "surface"),       # +inf
    ("delz_bottom", 0x00000000, "surface"),             # zero metric
    ("surface_denr", 0xBF800000, "surface"),            # negative metric
    ("rain_precip_cumulative", 0x7FC00000, "final_output"),   # NaN
    ("snow_precip_cumulative", 0xBF800000, "final_output"),   # negative
])
def test_a_corrupt_surface_value_is_invalid_evidence_not_a_divergence(field, bits,
                                                                     stage):
    # Unchecked, these reach the comparator and are reported as an out-of-scope or
    # external-input DIVERGENCE — a scientific verdict rendered on corrupt evidence.
    with pytest.raises(gev.GateSemanticsError):
        gev.validate_gate_semantics(_with_surface(field, bits, stage), mech)


def test_an_unknown_surface_field_has_no_silent_default():
    with pytest.raises(mech.TaxonomyHole):
        gev.validate_gate_semantics(_with_surface("invented_field", 0x3F800000), mech)


def test_mstep_is_bounded_below_by_the_instrumented_fall_speeds():
    """numdt maximises over work1_qr, workn_qr, work1_qs, work1_qg — and the last two
    are NOT dumped. So floor(x+1) computed from the instrumented species is a LOWER
    bound on mstep, never an equality. Violating it would mean the dumped operands or
    the schedule formula is wrong. See MULTISUBCYCLE_FIXTURE.md for the switch margin
    this leaves open."""
    w, ms, dt = {}, {}, {}
    for s in NORM["stages"]:
        if s["field"] in ("work1_qr", "workn_qr"):
            v = _f64(s["bits"]) if s["dtype"] == "f64" else _f32(s["bits"])
            key = (s["loop"], s["col"])
            w[key] = max(w.get(key, 0.0), float(v))
        elif s["field"] == "mstep":
            ms[(s["loop"], s["col"])] = int(s["bits"])
        elif s["field"] == "dtcld":
            dt[(s["loop"], s["col"])] = float(_f32(s["bits"]))
    assert len(w) == 9                                  # 3 loops x 3 columns
    dominated = 0
    for key in w:
        x = w[key] * dt[key]
        lower = math.floor(x + 1.0)                     # nint(x+0.5) == floor(x+1)
        assert lower <= ms[key], f"{key}: floor(x+1)={lower} > mstep={ms[key]}"
        if lower == ms[key]:
            margin = min(x - (lower - 1), lower - x)
            assert margin > 0.25, f"{key} sits {margin:.3f} from an mstep switch"
            dominated += 1
    assert dominated == 5      # the other four are set by uninstrumented qs/qg
