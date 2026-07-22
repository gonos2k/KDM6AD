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


def _build_and_run(algo="legacy", dump=False):
    with tempfile.TemporaryDirectory(prefix="g33-fortran-test.") as td:
        out = Path(td) / "build"
        cmd = ["bash", str(BUILD), str(out), f"--algo={algo}"] + (
            ["--dump"] if dump else [])
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, f"build failed:\n{r.stdout}\n{r.stderr}"
        driver = out / "g33_fortran_driver"
        assert driver.is_file(), "driver not built"
        run = subprocess.run([str(driver)], capture_output=True, text=True)
        assert run.returncode == 0, f"driver crashed:\n{run.stderr}"
        return run.stdout


@pytest.mark.parametrize("algo", ALGOS)
def test_fortran_driver_builds_runs_and_emits_raw_bits(algo):
    out = _build_and_run(algo)
    assert f"FORTRAN DRIVER OK ({algo}" in out
    assert f"G33-FORTRAN-BEGIN {algo}" in out and f"G33-FORTRAN-END {algo}" in out
    # Every FLD line is: FLD <name> <i> <k> <8-hex>. 12 fields x 3 cols x 4 lvls.
    fld = re.findall(r"^FLD\s+(\S.*?)\s+(\d+)\s+(\d+)\s+([0-9A-F]{8})$", out, re.M)
    assert len(fld) == 12 * 3 * 4, f"expected 144 FLD records, got {len(fld)}"
    # 3 precip families x 3 columns.
    prec = re.findall(r"^PREC\s+(\d+)\s+(\d+)\s+([0-9A-F]{8})$", out, re.M)
    assert len(prec) == 3 * 3, f"expected 9 PREC records, got {len(prec)}"
    # the 'th' (temperature) column-1 top value must be a plausible ~285-293 K.
    th = [int(h, 16) for (n, i, k, h) in fld if n.strip() == "th" and i == "1"]
    import struct
    vals = [struct.unpack(">f", v.to_bytes(4, "big"))[0] for v in th]
    assert all(280.0 < v < 300.0 for v in vals), f"th out of range: {vals}"


def _schema_fields(algo, role):
    """The authoritative (op_id, field, dtype) set the overlay must emit for a
    cell role, taken from the single schema the C++ container + P4 comparator use."""
    import g33_expectation as ge
    out = set()
    for sp in ("qr", "nr"):
        for op_id in ge._ops_for_species(algo, role, sp):
            for f, dt in ge._op_fields(algo, role, op_id):
                out.add((op_id, f, dt))
    return out


@pytest.mark.parametrize("algo", ALGOS)
def test_fortran_overlay_emits_full_schema_and_is_non_invasive(algo):
    import sys
    sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
    sys.path.insert(0, str(ROOT / "harness"))
    import g33_fortran_dump as fd

    canon = _build_and_run(algo, dump=False)
    dump = _build_and_run(algo, dump=True)

    # NON-INVASIVE: the instrumentation only adds WRITEs (and reads into two
    # scratch temps) — the final prognostic state and precip must be
    # BYTE-IDENTICAL between the canonical and the dump build. Fortran A/B/C.
    assert fd.parse_state(canon) == fd.parse_state(dump), \
        "overlay perturbed the final state — instrumentation is NOT non-invasive"
    assert fd.parse_prec(canon) == fd.parse_prec(dump), \
        "overlay perturbed precip — instrumentation is NOT non-invasive"
    assert not fd.parse_ops(canon), "canonical build must not emit op records"

    ops = fd.parse_ops(dump)
    assert ops, "no G33OP records emitted"

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
