"""Two-pass schedule derivation (public CI — no build).

The C++ contract must declare loops/mstepmax before the run, but mstep is only
knowable BY running. The way out is a SEPARATE probe channel, not a pre-declared
ceiling: an earlier design tried to over-declare to the algorithm's maximum and was
disproved by experiment, because op_seq_id is a process-global counter that the
sealed descriptor pins per record.

So: run the probe, re-derive mstep in Python from the raw fall speeds the probe
dumped, seal that exact schedule, and require the evidence run to reproduce it. These
tests pin each of those steps.
"""
import math
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
import g33_derived as gd              # noqa: E402
import g33_expectation as ge          # noqa: E402
import g33_schedule_probe as sp       # noqa: E402
sys.path.insert(0, str(ROOT / 'harness' / 'g33_overlay'))
import run_cpp_probe as probe_mod     # noqa: E402

BASE = {"case_id": "abc-fourcase_v1", "pair_id": "abc-legacy", "backend": "cpp",
        "algorithm": "legacy", "B": 3, "K": 4, "loops": 1,
        "mstepmax_main": [1], "mstepmax_ice": [1], "species_scope": ["qr", "nr"],
        "qcrmin": 1e-8, "dtcld": 100.0,
        "instrumented_stages": list(ge.CPP_OVERLAY_STAGES)}


def _probe(scopes):
    """{(loop, chain): mstep vector} -> a probe reading that ran to completion."""
    return {k: {"mstep": v, "n_seen": set(range(1, max(v) + 1))}
            for k, v in scopes.items()}


# ---- the probe stream --------------------------------------------------------

def _f32w(v):
    return struct.pack(">f", v).hex()


def _line(loop, n, field, values, dtype="f32"):
    words = "".join(_f32w(v) for v in values) if dtype == "f32" else None
    hexed = " ".join(words[i:i + 8] for i in range(0, len(words), 8))
    return f"KDM6SCHED {loop} main {n} {field} {dtype} {len(values)} {hexed}"


def _stream(loop, n, *, work1_qr, workn_qr, work1_qs, work1_qg, mstep, dtcld):
    return "\n".join([
        _line(loop, n, "work1_qr", work1_qr), _line(loop, n, "workn_qr", workn_qr),
        _line(loop, n, "work1_qs", work1_qs), _line(loop, n, "work1_qg", work1_qg),
        _line(loop, n, "mstep_native", mstep), _line(loop, n, "dtcld", dtcld),
    ]) + "\n"


def test_a_probe_stream_parses_to_its_scopes():
    raw = _stream(1, 1, work1_qr=[0.0], workn_qr=[0.0], work1_qs=[0.0],
                  work1_qg=[0.0], mstep=[1.0], dtcld=[100.0])
    parsed = sp.parse_sched_stream(raw)
    assert set(parsed) == {(1, "main", 1)}
    assert parsed[(1, "main", 1)]["dtcld"] == [100.0]


@pytest.mark.parametrize("bad", [
    "KDM6SCHED 1 main 1 work1_qr f32 2 3f800000",          # count != words
    "KDM6SCHED 1 main 1 work1_qr f32 1 3f80",               # short word
    "KDM6SCHED 1 main 1 work1_qr f16 1 3f800000",           # unknown dtype
    "KDM6SCHED x main 1 work1_qr f32 1 3f800000",           # non-integer scope
    "KDM6SCHED 1 main",                                      # truncated
])
def test_a_malformed_probe_line_is_a_broken_probe(bad):
    # skipping it would seal a schedule built from whatever survived truncation
    with pytest.raises(sp.ProbeError):
        sp.parse_sched_stream(bad + "\n")


def test_an_empty_stream_is_not_an_empty_schedule():
    with pytest.raises(sp.ProbeError, match="no KDM6SCHED"):
        sp.parse_sched_stream("KDM6ABC 1 legacy fourcase_v1 3 4\nEND\n")


# ---- the independent re-derivation -------------------------------------------

def test_the_producers_mstep_must_match_its_own_operands():
    # x = f32(0.025)*100 = 2.50000004 -> floor(3.5) = 3. NOT 0.02: its f32
    # round-trip is 0.0199999996, so x lands just under the 2.0 switch and gives 2 —
    # the very sensitivity switch_margin() exists to measure.
    ok = _stream(1, 1, work1_qr=[0.025], workn_qr=[0.0], work1_qs=[0.0],
                 work1_qg=[0.0], mstep=[3.0], dtcld=[100.0])
    assert sp.probe_from_stream(ok)[(1, "main")]["mstep"] == [3]

    lying = _stream(1, 1, work1_qr=[0.025], workn_qr=[0.0], work1_qs=[0.0],
                    work1_qg=[0.0], mstep=[2.0], dtcld=[100.0])
    with pytest.raises(sp.ProbeError, match="not what its operands imply"):
        sp.probe_from_stream(lying)


def test_the_uninstrumented_species_are_part_of_the_maximum():
    # work1_qg alone sets mstep here; reading only qr/nr would derive 1 and the
    # cross-check would then reject a run that is perfectly correct
    raw = _stream(1, 1, work1_qr=[0.0], workn_qr=[0.0], work1_qs=[0.0],
                  work1_qg=[0.025], mstep=[3.0], dtcld=[100.0])
    assert sp.probe_from_stream(raw)[(1, "main")]["mstep"] == [3]


def test_a_probe_missing_an_operand_cannot_be_derived():
    raw = _line(1, 1, "work1_qr", [0.0]) + "\n" + _line(1, 1, "mstep_native", [1.0])
    with pytest.raises(sp.ProbeError, match="missing"):
        sp.probe_from_stream(raw + "\n")


def test_a_non_integral_mstep_is_refused():
    raw = _stream(1, 1, work1_qr=[0.0], workn_qr=[0.0], work1_qs=[0.0],
                  work1_qg=[0.0], mstep=[2.5], dtcld=[100.0])
    with pytest.raises(sp.ProbeError, match="not integral"):
        sp.probe_from_stream(raw)


# ---- the switch margin -------------------------------------------------------

def test_switch_margin_uses_all_four_fall_speeds():
    # x = 1.5 -> m = 2, so the distance to either switch is 0.5
    raw = _stream(1, 1, work1_qr=[0.0], workn_qr=[0.0], work1_qs=[0.015],
                  work1_qg=[0.0], mstep=[2.0], dtcld=[100.0])
    margin = sp.switch_margin(raw)
    assert margin[(1, "main", 1)] == pytest.approx(0.5, abs=1e-5)


def test_a_duplicate_record_is_refused_not_overwritten():
    # last-wins is never right here: the survivor would seal the container universe
    line = _line(1, 1, "work1_qr", [0.0])
    with pytest.raises(sp.ProbeError, match="duplicate"):
        sp.parse_sched_stream(line + "\n" + line + "\n")


def test_an_unknown_probe_field_is_refused():
    with pytest.raises(sp.ProbeError, match="unknown probe field"):
        sp.parse_sched_stream(_line(1, 1, "work1_qx", [0.0]) + "\n")


@pytest.mark.parametrize("bad_value", [float("nan"), float("inf"), -1.0])
def test_an_inadmissible_fall_speed_is_refused(bad_value):
    # derive_mstep clamps a negative speed to 1 — right as arithmetic, wrong as a
    # conclusion. A broken measurement is not a one-substep run.
    raw = _stream(1, 1, work1_qr=[bad_value], workn_qr=[0.0], work1_qs=[0.0],
                  work1_qg=[0.0], mstep=[1.0], dtcld=[100.0])
    with pytest.raises(sp.ProbeError, match="fall-speed domain"):
        sp.probe_from_stream(raw)


@pytest.mark.parametrize("bad_dt", [0.0, -100.0, float("inf")])
def test_a_nonpositive_dtcld_is_refused(bad_dt):
    raw = _stream(1, 1, work1_qr=[0.0], workn_qr=[0.0], work1_qs=[0.0],
                  work1_qg=[0.0], mstep=[1.0], dtcld=[bad_dt])
    with pytest.raises(sp.ProbeError, match="positive finite timestep"):
        sp.probe_from_stream(raw)


def test_the_abandoned_discovery_path_is_gone():
    # two designs for one job were live at once; the container-discovery one was
    # disproved by experiment and became unreachable. Leaving it invited a later
    # reader to switch it back on.
    import inspect
    import g33_bundle_io as bio
    assert "discovery" not in inspect.signature(bio.verify_cpp_evidence).parameters
    for gone in ("PROBE_MARKER", "probe_case_id", "is_probe", "assert_not_evidence"):
        assert not hasattr(sp, gone), f"{gone} survived the removal"


# ---- the derivation ----------------------------------------------------------

@pytest.mark.parametrize("x,want", [
    (0.0, 1), (0.99, 1), (1.0, 2), (1.49, 2), (1.5, 2), (1.99, 2), (2.0, 3),
])
def test_mstep_relation_is_floor_x_plus_one(x, want):
    # nint(x+0.5) == floor(x+1) for x >= 0; the threshold is x >= m-1, not m-0.5
    assert sp.derive_mstep([x], 1.0) == [want]


def test_derivation_is_clamped_to_the_contract_range():
    lo, hi = gd.MSTEP_RANGE
    assert sp.derive_mstep([-5.0, 1e9], 1.0) == [lo, hi]


# ---- sealing -----------------------------------------------------------------

def test_sealed_schedule_is_the_per_loop_column_maximum():
    probe = _probe({(1, "main"): [1, 5, 9], (2, "main"): [1, 2, 10],
                      (3, "main"): [1, 1, 7]})
    s = sp.sealed_schedule(dict(BASE), probe)
    assert s["loops"] == 3 and s["mstepmax_main"] == [9, 10, 7]


def test_a_chain_that_emits_nothing_seals_as_the_neutral_one():
    # the ice chain under species_scope=[qr, nr] produces no containers at all;
    # deriving anything larger would be inventing evidence
    s = sp.sealed_schedule(dict(BASE), _probe({(1, "main"): [1, 1, 1]}))
    assert s["mstepmax_ice"] == [1]


def test_a_probe_that_stopped_early_cannot_be_sealed():
    # its own mstep says 9 substeps; it wrote 4. Sealing that would produce a
    # contract the evidence run could never satisfy.
    probe = {(1, "main"): {"mstep": [1, 5, 9], "n_seen": {1, 2, 3, 4}}}
    with pytest.raises(sp.ProbeError, match=r"substeps 1\.\.9"):
        sp.sealed_schedule(dict(BASE), probe)


def test_a_probe_with_a_HOLE_cannot_be_sealed():
    # It reached substep 9, so max(n) == mstep and the old completeness check was
    # satisfied — while substeps 2..8 never ran at all. A summary that keeps only
    # the furthest index cannot tell "ran 1..9" from "ran 1 and 9", and the gap is
    # exactly where a producer that skipped work would hide.
    probe = {(1, "main"): {"mstep": [1, 5, 9], "n_seen": {1, 9}}}
    with pytest.raises(sp.ProbeError, match=r"never \[2, 3, 4, 5, 6, 7, 8\]"):
        sp.sealed_schedule(dict(BASE), probe)


def test_a_partial_chain_cannot_be_sealed():
    probe = _probe({(1, "main"): [1], (2, "main"): [1], (1, "ice"): [1]})
    with pytest.raises(sp.ProbeError, match="partial chain"):
        sp.sealed_schedule(dict(BASE), probe)


def test_non_contiguous_outer_loops_are_refused():
    probe = _probe({(1, "main"): [1], (3, "main"): [1]})
    with pytest.raises(sp.ProbeError, match="not 1..N"):
        sp.sealed_schedule(dict(BASE), probe)


# ---- the reproduce gate ------------------------------------------------------

def test_evidence_must_reproduce_the_probe_schedule_exactly():
    probe = _probe({(1, "main"): [1, 5, 9]})
    sp.assert_reproduced(probe, _probe({(1, "main"): [1, 5, 9]}))
    with pytest.raises(sp.ProbeError):
        sp.assert_reproduced(probe, _probe({(1, "main"): [1, 5, 8]}))


def test_a_scope_appearing_in_only_one_run_is_a_finding():
    probe = _probe({(1, "main"): [1]})
    with pytest.raises(sp.ProbeError, match="scopes"):
        sp.assert_reproduced(probe, _probe({(1, "main"): [1], (2, "main"): [1]}))


# ---- the outer-loop count ----------------------------------------------------

def _authority_with_dt(dt: float) -> dict:
    return {"common_parameters": {"dt": struct.pack(">f", dt).hex()}}


def _next_f32(v: float) -> float:
    """The next representable f32 above v.

    A double nextafter is the wrong boundary here: the fixture stores dt as f32, so
    120.00000000000001 rounds straight back to 120.0 on the way in and the step is
    invisible.
    """
    import numpy as np
    return float(np.nextafter(np.float32(v), np.float32(np.inf)))


_NEXT_120 = _next_f32(120.0)
_NEXT_240 = _next_f32(240.0)


@pytest.mark.parametrize("dt,loops", [
    (20.0, 1), (120.0, 1),                      # exactly the threshold: still one
    (_NEXT_120, 2),                             # a hair over, in f32: two
    (120.5, 2),                                 # int(dt)//120 truncated this to 1
    (239.9, 2), (240.0, 2),
    (_NEXT_240, 3),
    (300.0, 3),
])
def test_outer_loop_count_ceils_the_real_dt(dt, loops):
    """`int(dt) // 120` truncates BEFORE dividing, so dt = 120.5 gave 1 loop where the
    reference takes 2. Both shipped fixtures are integral (20 s, 300 s), which is
    exactly why it stayed invisible."""
    got_loops, _ = probe_mod.step_schedule(_authority_with_dt(dt))
    assert got_loops == loops


def test_dtcld_is_an_f32_not_a_python_double():
    # the backends carry an f32 cloud timestep; a double here would seal a value
    # neither of them computes with
    _, dtcld = probe_mod.step_schedule(_authority_with_dt(100.0))
    assert dtcld == struct.unpack(">f", struct.pack(">f", dtcld))[0]
    loops, dtcld = probe_mod.step_schedule(_authority_with_dt(300.0))
    assert (loops, dtcld) == (3, 100.0)


@pytest.mark.parametrize("bad", [0.0, -20.0, float("inf"), float("nan")])
def test_a_nonsense_dt_is_refused(bad):
    with pytest.raises(SystemExit):
        probe_mod.step_schedule(_authority_with_dt(bad))


# -- the probe's own shape/vocabulary contract (owner PR C) --------------------

def _shape_line(loop, chain, n, field, vals, dtype="f32"):
    import struct
    w = "".join(struct.pack(">f", float(v)).hex() for v in vals)
    words = " ".join(w[i:i + 8] for i in range(0, len(w), 8))
    return f"KDM6SCHED {loop} {chain} {n} {field} {dtype} {len(vals)} {words}"


def _shape_stream(B=2, K=3, mstep=1, chain="main", work_len=None):
    """A complete one-substep scope; work_len overrides the [B,K] payload length."""
    v = (mstep - 0.5) / 100.0
    n_work = work_len if work_len is not None else B * K
    out = []
    for f in ("work1_qr", "workn_qr", "work1_qs", "work1_qg"):
        vals = [v] * n_work if f == "work1_qr" else [0.0] * n_work
        out.append(_shape_line(1, chain, 1, f, vals))
    out.append(_shape_line(1, chain, 1, "mstep_native", [mstep] * B))
    out.append(_shape_line(1, chain, 1, "dtcld", [100.0] * B))
    return "\n".join(out) + "\n"


def test_an_unknown_chain_is_refused():
    # an unknown chain would form its own scope and seal a schedule for a transport
    # chain the runtime never ran
    with pytest.raises(sp.ProbeError, match="unknown chain"):
        sp.parse_sched_stream(_shape_stream(chain="rain"))


def test_a_truncated_work_tensor_is_refused():
    """[B, K-1] still divides evenly by B, so it reads as a shorter column and the
    stream — which declares no K — cannot say otherwise. The grid therefore comes
    from the fixture authority."""
    truncated = _shape_stream(B=2, K=3, work_len=2 * 2)
    with pytest.raises(sp.ProbeError, match="fixture declares"):
        sp.probe_from_stream(truncated, expected_shape=(2, 3))
    # ...and without the declaration it is genuinely indistinguishable
    assert sp.probe_from_stream(truncated)[(1, "main")]["mstep"] == [1, 1]


def test_work_fields_of_differing_lengths_are_refused():
    s = _shape_stream(B=2, K=3)
    s = s.replace(_shape_line(1, "main", 1, "work1_qs", [0.0] * 6),
                  _shape_line(1, "main", 1, "work1_qs", [0.0] * 4))
    with pytest.raises(sp.ProbeError, match="differing lengths"):
        sp.probe_from_stream(s)


def test_a_scope_without_one_column_count_is_refused():
    s = _shape_stream(B=2, K=3)
    s = s.replace(_shape_line(1, "main", 1, "dtcld", [100.0] * 2),
                  _shape_line(1, "main", 1, "dtcld", [100.0] * 3))
    with pytest.raises(sp.ProbeError, match="no single column count"):
        sp.probe_from_stream(s)


def test_a_well_formed_scope_still_derives():
    # the guards must not refuse the shape the runtime actually emits
    probe = sp.probe_from_stream(_shape_stream(B=2, K=3, mstep=1))
    assert probe[(1, "main")]["mstep"] == [1, 1]


def test_the_fixture_itself_decides_whether_a_probe_is_required():
    """The evidence checker refuses to fall back to a one-loop default when the
    fixture's own dt implies more than one outer loop. That condition is computed
    here, so it is pinned here — a fixture whose loop count changed would otherwise
    silently move between the two paths."""
    import g33_fixture_v1 as gfx
    _, single = gfx.load_fixture("arithmetic_synthetic_v1")
    _, multi = gfx.load_fixture("arithmetic_multisubcycle_v1")
    assert sp.step_schedule(single)[0] == 1, "the default fixture takes one loop"
    loops, dtcld = sp.step_schedule(multi)
    assert (loops, dtcld) == (3, 100.0), (loops, dtcld)


def test_step_schedule_lives_with_the_protocol_not_the_cli():
    # both the probe CLI and the evidence checker ask this question; a second copy
    # would be the same fixture-constant assumption that dtcld and qcrmin already
    # produced once each
    import importlib
    cli = importlib.import_module("run_cpp_probe")
    assert cli.step_schedule is sp.step_schedule
