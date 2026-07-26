"""The multi-subcycle evidence path (public CI — no build).

The one-loop arithmetic fixture cannot exercise the machinery that exists for
multi-subcycle transport: heterogeneous mstep, inactive lanes, per-loop state
continuity, cumulative surface precipitation. This runs the checked-in
`arithmetic_multisubcycle_v1` evidence — 3 cloud outer loops with mstep differing
BOTH across columns and BETWEEN loops — through the whole reader/validator chain.
"""
import sys
from pathlib import Path

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
    assert sorted({s["loop"] for s in NORM["stages"]}) == [1, 2, 3]


def test_gate_contract_holds_with_real_inactive_lanes():
    mask = gev.validate_gate_semantics(NORM, mech)
    inactive = [lane for lane, active in mask.items() if not active]
    # the one-loop fixture has NO inactive lane; this evidence must have many, so the
    # gate law, the no-op relations and the active-stream filter are really exercised
    assert inactive, "expected gate-inactive lanes in multi-subcycle evidence"
    assert len(inactive) > 10


def test_full_ladder_replays_bit_exactly_across_loops():
    assert rp.replay_run(NORM) > 4000
