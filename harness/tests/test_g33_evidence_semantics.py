"""Public-CI coverage of the G3.3-M Fortran evidence contract (owner item 12).

Building the standalone Fortran needs the gitignored host reference tree, so those
tests skip in public CI. But the parser + semantics fail-closed behaviour is pure
Python and MUST be exercised everywhere. This runs the structural + causal
mutation corpus against a CHECKED-IN sample stream
(`data/g33_legacy_sample.g33f`, one legacy dump-build C run) — no gfortran needed.

Regenerate the sample after a protocol/overlay change:
    bash harness/g33_fortran/fortran_build.sh /tmp/o --algo=legacy --dump
    /tmp/o/g33_fortran_driver > harness/tests/data/g33_legacy_sample.g33f
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SAMPLE = Path(__file__).parent / "data" / "g33_legacy_sample.g33f"
sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
sys.path.insert(0, str(ROOT / "harness"))
import g33_fortran_dump as fd          # noqa: E402
import g33_fortran_semantics as sem    # noqa: E402

TEXT = SAMPLE.read_text()
ALGO, K, B = "legacy", 4, 3


def _tok(line, i, v):
    t = line.split()
    t[i] = v
    return " ".join(t)


def test_sample_parses_and_is_semantically_valid():
    run = fd.parse_fortran_run(TEXT, ALGO, K, B)
    assert run.ops and run.stages and run.state and run.precip
    sem.verify_semantics(run)
    # noninstrumented mode rejects the instrumented sample (it has MSTEP/OP/STAGE).
    with pytest.raises(fd.FortranRunError):
        fd.parse_fortran_run(TEXT, ALGO, K, B, evidence_mode="noninstrumented")


def _mut(fn):
    m = TEXT.splitlines()
    fn(m)
    return "\n".join(m)


def _first(pred):
    return next(i for i, l in enumerate(TEXT.splitlines()) if pred(l))


def test_parser_rejects_structural_mutants():
    op = _first(lambda l: l.startswith("G33FOP"))
    st = _first(lambda l: l.startswith("G33F STATE"))
    ms = _first(lambda l: l.startswith("G33F MSTEP"))
    sg = _first(lambda l: l.startswith("G33F STAGE outer_pre_sed"))
    beg = _first(lambda l: l.startswith("G33F BEGIN"))
    cases = [
        lambda m: m.pop(op),                                    # dropped op
        lambda m: m.insert(op, m[op]),                          # duplicate op
        lambda m: m.__setitem__(op, _tok(m[op], 5, "9")),       # op k out of range
        lambda m: m.__setitem__(op, _tok(m[op], 1, "9")),       # loop != 1
        lambda m: m.__setitem__(op, _tok(m[op], 2, "ice")),     # chain != main
        lambda m: m.__setitem__(op, _tok(m[op], 8, "BAD")),     # malformed dtype
        lambda m: m.__setitem__(ms, _tok(m[ms], 4, "FFFFFFFF")),  # signed -1 mstep
        lambda m: m.insert(ms, m[ms]),                          # duplicate MSTEP
        lambda m: m.pop(st),                                    # missing STATE
        lambda m: m.pop(sg),                                    # missing STAGE
        lambda m: m.pop(beg),                                   # missing BEGIN
        lambda m: (m.pop(op), m.insert(st, TEXT.splitlines()[op])),  # cross-cell reorder
    ]
    for fn in cases:
        with pytest.raises(fd.FortranRunError):
            fd.parse_fortran_run(_mut(fn), ALGO, K, B)


def test_semantics_rejects_causal_mutants():
    other = 0x40000000
    cases = [
        lambda S, P: S.__setitem__(("substep_pre", 1, "mstep", 1, -1), ("i32", 2)),
        lambda S, P: S.__setitem__(("substep_pre", 1, "gate", 1, -1), ("u8", 0)),
        lambda S, P: S.__setitem__(("substep_pre", 1, "qr", 1, 0), ("f32", other)),
        lambda S, P: S.__setitem__(("surface", 0, "bottom_fall_qr", 1, -1), ("f32", other)),
        lambda S, P: S.__setitem__(("surface", 0, "bottom_fall_total", 1, -1), ("f32", other)),
        lambda S, P: P.__setitem__((1, 1), other),
    ]
    for fn in cases:
        run = fd.parse_fortran_run(TEXT, ALGO, K, B)
        fn(run.stages, run.precip)
        with pytest.raises(sem.SemanticError):
            sem.verify_semantics(run)
