"""G3.3-M Fortran leg (P1) — build + run the standalone reference Fortran.

The reference host WRF/KIM-meso Fortran tree is gitignored (not distributed), so
this is LOCAL-ONLY: it SKIPS when gfortran or the reference source is absent (so
it is a clean skip in CI) and builds + runs the driver where the source is
present (the owner's host), asserting the driver reports OK and emits a
well-formed raw-bit stream — the operand-domain evidence the four-case G3.3-M
comparator (P4) consumes.
"""
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "harness" / "g33_fortran" / "fortran_build.sh"
REF = ROOT / "host" / "KIM-meso_v1.0" / "phys" / "module_mp_kdm6.F"

pytestmark = pytest.mark.skipif(
    shutil.which("gfortran") is None or not REF.is_file(),
    reason="Fortran leg is local-only (needs gfortran + the gitignored host reference tree)",
)


ALGOS = ["legacy", "conservative"]


def _build_and_run(algo="legacy", *, overlay=False, dump=False):
    with tempfile.TemporaryDirectory(prefix="g33-fortran-test.") as td:
        out = Path(td) / "build"
        flags = [f"--algo={algo}"]
        if dump:
            flags.append("--dump")        # implies --overlay
        elif overlay:
            flags.append("--overlay")
        r = subprocess.run(["bash", str(BUILD), str(out), *flags],
                           capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, f"build failed:\n{r.stdout}\n{r.stderr}"
        driver = out / "g33_fortran_driver"
        assert driver.is_file(), "driver not built"
        run = subprocess.run([str(driver)], capture_output=True, text=True)
        assert run.returncode == 0, f"driver crashed:\n{run.stderr}"
        return run.stdout


@pytest.mark.parametrize("algo", ALGOS)
def test_fortran_driver_builds_runs_and_emits_raw_bits(algo):
    import sys
    sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
    import g33_fortran_dump as fd

    out = _build_and_run(algo)
    assert f"FORTRAN DRIVER OK ({algo}" in out
    assert f"G33F BEGIN v1 {algo}" in out and f"G33F END v1 {algo}" in out
    # final state: 12 fields x 3 cols x 4 levels (top-first k = 0..3).
    state = fd.parse_state(out)
    assert len(state) == 12 * 3 * 4, f"expected 144 STATE records, got {len(state)}"
    assert {k for (_, _, k) in state} == {0, 1, 2, 3}, "STATE k must be top-first 0..3"
    # 3 precip families x 3 columns; fixture identity present.
    assert len(fd.parse_prec(out)) == 3 * 3, "expected 9 PREC records"
    assert fd.parse_fixin(out), "no FIXIN fixture-identity records"
    # the 'th' column-1 values must be plausible ~285-293 K.
    import struct
    th = [v for (n, i, k), v in state.items() if n == "th" and i == 1]
    vals = [struct.unpack(">f", v.to_bytes(4, "big"))[0] for v in th]
    assert all(280.0 < v < 300.0 for v in vals), f"th out of range: {vals}"


def _schema_fields(algo, role):
    """The authoritative (op_id, field, dtype) set the overlay must emit for a
    cell role, taken from the single schema the C++ container + P4 comparator use."""
    import sys
    sys.path.insert(0, str(ROOT / "harness"))
    import g33_schema as schema
    out = set()
    for sp in ("qr", "nr"):
        for op_id in schema.ops_for_species(algo, role, sp):
            for f, dt in schema.op_fields(algo, role, op_id):
                out.add((op_id, f, dt))
    return out


@pytest.mark.parametrize("algo", ALGOS)
def test_fortran_overlay_full_abc_and_emits_full_schema(algo):
    import sys
    sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
    sys.path.insert(0, str(ROOT / "harness"))
    import g33_fortran_dump as fd

    # FULL Fortran A/B/C (owner P0-7):
    #   A = canonical module
    #   B = generated overlay, dump macro OFF
    #   C = same generated overlay, dump macro ON
    a = _build_and_run(algo)                          # A
    b = _build_and_run(algo, overlay=True)            # B
    c = _build_and_run(algo, overlay=True, dump=True)  # C

    # A==B==C raw-bit in final state + precip: the overlay only ADDS guarded
    # WRITEs, so with the macro off it is byte-identical to canonical, and with
    # it on the extra WRITEs must not perturb any prognostic value.
    sa, sb, sc = fd.parse_state(a), fd.parse_state(b), fd.parse_state(c)
    pa, pb, pc = fd.parse_prec(a), fd.parse_prec(b), fd.parse_prec(c)
    assert sa == sb, "generated overlay (macro OFF) changed final state vs canonical"
    assert sa == sc, "dump build changed final state — instrumentation NOT non-invasive"
    assert pa == pb == pc, "precip differs across A/B/C — NOT non-invasive"

    # Only C emits op records; A (canonical) and B (macro off) emit none.
    assert not fd.parse_ops(a), "canonical build A must not emit op records"
    assert not fd.parse_ops(b), "overlay build B (macro OFF) must not emit op records"

    dump = c
    ops = fd.parse_ops(dump)
    assert ops, "no G33OP records emitted by C"

    # Every emitted record must carry the schema dtype for its (role, op, field).
    top_fields = _schema_fields(algo, "TOP")
    int_fields = _schema_fields(algo, "INTERIOR")   # == BOTTOM op set
    for o in ops:
        want = top_fields if o["k"] == 0 else int_fields
        assert (o["op"], o["field"], o["dtype"]) in want, \
            f"emitted {(o['op'], o['field'], o['dtype'])} not in schema for k={o['k']}"

    # COMPLETENESS: for every active (col, k, n) cell the emitted (op,field,dtype)
    # set must equal the schema's EXACTLY — no rung dropped, none invented. This
    # is what makes the Fortran dump comparable to the C++ container in P4.
    groups = {}
    for o in ops:
        groups.setdefault((o["col"], o["k"], o["n"]), set()).add(
            (o["op"], o["field"], o["dtype"]))
    saw_top = saw_int = False
    for (col, k, n), got in groups.items():
        want = top_fields if k == 0 else int_fields
        assert got == want, f"cell col={col} k={k} n={n}: {got ^ want} differs from schema"
        saw_top |= (k == 0)
        saw_int |= (k >= 1)
    assert saw_top and saw_int, "fixture must exercise both TOP (k=0) and interior (k>=1)"


def _set_tok(line, idx, val):
    t = line.split()
    t[idx] = val
    return " ".join(t)


@pytest.mark.parametrize("algo", ALGOS)
def test_strict_parser_accepts_good_and_rejects_mutants(algo):
    import sys
    sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
    sys.path.insert(0, str(ROOT / "harness"))
    import g33_fortran_dump as fd

    good = _build_and_run(algo, overlay=True, dump=True)
    run = fd.parse_fortran_run(good, algo, K=4, B=3)   # must accept a clean run
    assert run.algorithm == algo and run.ops and run.fixture_sha256
    # ops are canonically ordered per column (op_seq_id monotonic within a lane).
    for c in range(1, 4):
        seqs = [r.op_seq_id for r in run.ops if r.col == c]
        assert seqs == sorted(seqs) and len(seqs) == len(set(seqs))

    lines = good.splitlines()
    op_i = next(i for i, l in enumerate(lines) if l.startswith("G33FOP"))
    st_i = next(i for i, l in enumerate(lines) if l.startswith("G33F STATE"))
    beg_i = next(i for i, l in enumerate(lines) if l.startswith("G33F BEGIN"))
    # G33FOP loop chain n col k op field dtype hex  -> col=idx4, k=idx5, n=idx3
    one_col = [i for i, l in enumerate(lines)
               if l.startswith("G33FOP") and l.split()[4] == "2"]

    def _mut(fn):
        m = list(lines)
        fn(m)
        return "\n".join(m)

    mutants = {
        "drop one op": lambda m: m.pop(op_i),
        "duplicate op": lambda m: m.insert(op_i, m[op_i]),
        "whole column dropped": lambda m: [m.pop(i) for i in reversed(one_col)],
        "op k out of range": lambda m: m.__setitem__(op_i, _set_tok(m[op_i], 5, "9")),
        "op n out of gate": lambda m: m.__setitem__(op_i, _set_tok(m[op_i], 3, "7")),
        "malformed op (bad dtype)": lambda m: m.__setitem__(op_i, _set_tok(m[op_i], 8, "BAD")),
        "duplicate state key": lambda m: m.insert(st_i, m[st_i]),
        "BEGIN removed": lambda m: m.pop(beg_i),
    }
    for name, fn in mutants.items():
        with pytest.raises(fd.FortranRunError):
            fd.parse_fortran_run(_mut(fn), algo, K=4, B=3)


def test_strict_parser_closeout_mutants():
    # PR#61 hardening: loop/chain identity, signed mstep range, exact
    # STATE/PREC/FIXIN/PARAM universe, phase bracketing.
    import sys
    sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
    sys.path.insert(0, str(ROOT / "harness"))
    import g33_fortran_dump as fd

    good = _build_and_run("legacy", overlay=True, dump=True)
    fd.parse_fortran_run(good, "legacy", K=4, B=3)   # accepts clean
    lines = good.splitlines()

    def idx(pred):
        return next(i for i, l in enumerate(lines) if pred(l))

    op_i = idx(lambda l: l.startswith("G33FOP"))
    ms_i = idx(lambda l: l.startswith("G33F MSTEP"))
    st_i = idx(lambda l: l.startswith("G33F STATE"))
    pr_i = idx(lambda l: l.startswith("G33F PREC"))
    fx_i = idx(lambda l: l.startswith("G33F FIXIN"))
    pm_i = idx(lambda l: l.startswith("G33F PARAM"))

    def mut(fn):
        m = list(lines)
        fn(m)
        return "\n".join(m)

    cases = {
        "loop != 1": lambda m: m.__setitem__(op_i, _set_tok(m[op_i], 1, "9")),
        "chain != main": lambda m: m.__setitem__(op_i, _set_tok(m[op_i], 2, "ice")),
        "mstep negative (signed FFFFFFFF)": lambda m: m.__setitem__(ms_i, _set_tok(m[ms_i], 4, "FFFFFFFF")),
        "mstep > 100 (0x65)": lambda m: m.__setitem__(ms_i, _set_tok(m[ms_i], 4, "00000065")),
        "STATE record missing": lambda m: m.pop(st_i),
        "PREC record missing": lambda m: m.pop(pr_i),
        "FIXIN record missing": lambda m: m.pop(fx_i),
        "PARAM name wrong": lambda m: m.__setitem__(pm_i, _set_tok(m[pm_i], 2, "bogus")),
        "op after STATE (phase order)": lambda m: m.insert(st_i + 1, m[op_i]),
    }
    for name, fn in cases.items():
        with pytest.raises(fd.FortranRunError):
            fd.parse_fortran_run(mut(fn), "legacy", K=4, B=3)


def test_strict_parser_closeout2_mutants():
    # PR#62A: duplicate MSTEP, A/B held to the strict parser (noninstrumented),
    # finiteness/domain, and a PROPER cross-cell reorder.
    import sys
    sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
    sys.path.insert(0, str(ROOT / "harness"))
    import g33_fortran_dump as fd

    C = _build_and_run("legacy", overlay=True, dump=True)   # instrumented
    A = _build_and_run("legacy")                            # canonical -> noninstrumented
    fd.parse_fortran_run(C, "legacy", 4, 3)                                    # accepts
    fd.parse_fortran_run(A, "legacy", 4, 3, evidence_mode="noninstrumented")   # accepts

    cl = C.splitlines()
    ms = next(i for i, l in enumerate(cl) if l.startswith("G33F MSTEP"))
    fx = next(i for i, l in enumerate(cl) if l.startswith("G33F FIXIN qr"))
    op0 = cl[next(i for i, l in enumerate(cl) if l.startswith("G33FOP"))]

    def cmut(fn):
        m = list(cl)
        fn(m)
        return "\n".join(m)

    def move_op_to_end(m):                       # proper reorder: pop + reinsert late
        i = next(j for j, l in enumerate(m) if l.startswith("G33FOP"))
        line = m.pop(i)
        j = next(k for k, l in enumerate(m) if l.startswith("G33F STATE"))
        m.insert(j, line)

    c_cases = {
        "duplicate MSTEP": lambda m: m.insert(ms, m[ms]),
        "conflicting MSTEP": lambda m: m.insert(ms, _set_tok(m[ms], 4, "00000002")),
        "NaN FIXIN": lambda m: m.__setitem__(fx, _set_tok(m[fx], 6, "7FC00000")),
        "cross-cell op reorder": move_op_to_end,
    }
    for name, fn in c_cases.items():
        with pytest.raises(fd.FortranRunError):
            fd.parse_fortran_run(cmut(fn), "legacy", 4, 3)

    al = A.splitlines()
    st = next(i for i, l in enumerate(al) if l.startswith("G33F STATE"))

    def amut(fn):
        m = list(al)
        fn(m)
        return "\n".join(m)

    a_cases = {   # A is noninstrumented — the strict parser must still reject these
        "op record in A": lambda m: m.insert(st, op0),
        "malformed G33F in A": lambda m: m.insert(st, "G33F BOGUS 1 2 3"),
        "duplicate STATE in A": lambda m: m.insert(st, m[st]),
    }
    for name, fn in a_cases.items():
        with pytest.raises(fd.FortranRunError):
            fd.parse_fortran_run(amut(fn), "legacy", 4, 3, evidence_mode="noninstrumented")


def test_presed_stage_records():
    # PR#62A P0-7: outer_pre_sed + substep_pre whole-K snapshots, exact + finite.
    import sys
    sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
    sys.path.insert(0, str(ROOT / "harness"))
    import g33_fortran_dump as fd

    C = _build_and_run("legacy", overlay=True, dump=True)
    run = fd.parse_fortran_run(C, "legacy", 4, 3)
    # outer_pre_sed = 6 fields x 3 x 4; both stages present.
    assert sum(1 for k in run.stages if k[0] == "outer_pre_sed") == 6 * 3 * 4
    assert any(k[0] == "substep_pre" for k in run.stages)
    assert sum(1 for k in run.stages if k[0] == "surface") == 6 * 3   # P0-8
    assert ("outer_pre_sed", 0, "qr", 1, 0) in run.stages
    assert ("surface", 0, "bottom_fall_qr", 1, -1) in run.stages

    cl = C.splitlines()
    sg = next(i for i, l in enumerate(cl) if l.startswith("G33F STAGE outer_pre_sed"))
    # tokens: G33F STAGE <stage> <n> <field> <col> <k> <dtype> <hex>
    w1 = next(i for i, l in enumerate(cl) if l.startswith("G33F STAGE substep_pre")
              and l.split()[4] == "work1_qr")
    A = _build_and_run("legacy").splitlines()
    st_a = next(i for i, l in enumerate(A) if l.startswith("G33F STATE"))

    with pytest.raises(fd.FortranRunError):        # a dropped stage record
        fd.parse_fortran_run("\n".join(cl[:sg] + cl[sg + 1:]), "legacy", 4, 3)
    with pytest.raises(fd.FortranRunError):        # NaN in a work1 (f64) snapshot
        m = list(cl); m[w1] = _set_tok(m[w1], 8, "7FF8000000000000")
        fd.parse_fortran_run("\n".join(m), "legacy", 4, 3)
    with pytest.raises(fd.FortranRunError):        # STAGE leaking into A (noninstrumented)
        m = list(A); m.insert(st_a, cl[sg])
        fd.parse_fortran_run("\n".join(m), "legacy", 4, 3, evidence_mode="noninstrumented")


@pytest.mark.parametrize("algo", ALGOS)
def test_actual_vs_shadow_offline_replay(algo):
    # the ACTUAL stored q_post/n_post match an offline replay from the dumped
    # operands — proves the dump observes the real update, not just shadows.
    import sys
    sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
    sys.path.insert(0, str(ROOT / "harness"))
    import g33_fortran_dump as fd
    run = fd.parse_fortran_run(_build_and_run(algo, overlay=True, dump=True),
                               algo, K=4, B=3)
    assert fd.verify_offline_replay(run) > 0


def test_offline_replay_catches_mutated_actual_update():
    # NON-VACUOUSNESS: a REAL source mutant that drops the inflow term from the
    # conservative interior qr UPDATE (operands + shadows unchanged) makes the
    # STORED q_post diverge from the replay — the verifier must catch it.
    import sys
    sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
    sys.path.insert(0, str(ROOT / "harness"))
    import make_fortran_overlay as mk
    import g33_fortran_dump as fd

    src = (ROOT / "host/KIM-meso_v1.0/phys/module_mp_kdm6_cons.F").read_text()
    overlay = mk.build_overlay("conservative", src)
    anchor = "                          +dqr(i,k+1)*src_metric/dst_metric"
    assert overlay.count(anchor) == 1, "actual inflow line not unique"
    mutant = overlay.replace(anchor, "                          +0.0")

    with tempfile.TemporaryDirectory(prefix="g33-mutant.") as td:
        mpath = Path(td) / "mutant.F"
        mpath.write_text(mutant)
        out = Path(td) / "build"
        r = subprocess.run(
            ["bash", str(BUILD), str(out), "--algo=conservative",
             f"--overlay-file={mpath}"], capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, f"mutant build failed:\n{r.stdout}\n{r.stderr}"
        run_out = subprocess.run([str(out / "g33_fortran_driver")],
                                 capture_output=True, text=True).stdout

    run = fd.parse_fortran_run(run_out, "conservative", K=4, B=3)  # structurally complete
    with pytest.raises(fd.FortranRunError):
        fd.verify_offline_replay(run)


def test_abc_bundle_is_persistent_and_recheckable():
    import hashlib
    import json
    WRAP = ROOT / "harness" / "g33_fortran" / "run_fortran_abc.py"
    with tempfile.TemporaryDirectory(prefix="g33-abc.") as td:
        out = Path(td) / "abc"
        r = subprocess.run(["python3", str(WRAP), "--algo", "legacy", "--out", str(out)],
                           capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, f"abc wrapper failed:\n{r.stdout}\n{r.stderr}"
        man = json.loads((out / "abc_manifest.json").read_text())
        assert man["abc_equal"] is True and man["op_record_count"] > 0
        # raw streams persisted and re-checkable against the manifest.
        for c in ("A", "B", "C"):
            raw = (out / c / "stdout.g33f").read_bytes()
            assert hashlib.sha256(raw).hexdigest() == man["stdout_sha256"][c]
        assert (out / "C" / "normalized_ops.json").is_file()
        assert man["executable_sha256"]["A"] != man["executable_sha256"]["C"]


def test_run_wrapper_writes_complete_manifest():
    # end-to-end: build + run + strict-parse + decision-grade run_manifest.json.
    WRAP = ROOT / "harness" / "g33_fortran" / "run_fortran_case.py"
    with tempfile.TemporaryDirectory(prefix="g33-run.") as td:
        out = Path(td) / "run"
        r = subprocess.run(["python3", str(WRAP), "--algo", "legacy", "--out", str(out)],
                           capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, f"wrapper failed:\n{r.stdout}\n{r.stderr}"
        import json
        man = json.loads((out / "run_manifest.json").read_text())
        required = ["repo_commit", "repo_dirty", "algorithm", "fixture_sha256",
                    "parameter_sha256", "stdout_sha256", "stderr_sha256",
                    "executable_sha256", "compiler_binary_sha256", "os",
                    "architecture", "python_version", "mstep_per_column",
                    "op_record_count", "host_source_sha256", "harness_source_sha256"]
        assert all(k in man for k in required), \
            f"missing manifest keys: {[k for k in required if k not in man]}"
        assert man["algorithm"] == "legacy" and man["op_record_count"] > 0
        assert all(len(man[k]) == 64 for k in ("fixture_sha256", "stdout_sha256",
                                               "compiler_binary_sha256"))
