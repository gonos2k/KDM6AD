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


def _build_and_run(dump=False):
    with tempfile.TemporaryDirectory(prefix="g33-fortran-test.") as td:
        out = Path(td) / "build"
        cmd = ["bash", str(BUILD), str(out)] + (["--dump"] if dump else [])
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
        assert r.returncode == 0, f"build failed:\n{r.stdout}\n{r.stderr}"
        driver = out / "g33_fortran_driver"
        assert driver.is_file(), "driver not built"
        run = subprocess.run([str(driver)], capture_output=True, text=True)
        assert run.returncode == 0, f"driver crashed:\n{run.stderr}"
        return run.stdout


def test_fortran_driver_builds_runs_and_emits_raw_bits():
    out = _build_and_run()
    assert "FORTRAN DRIVER OK" in out
    assert "G33-FORTRAN-BEGIN legacy" in out and "G33-FORTRAN-END legacy" in out
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


def test_fortran_overlay_emits_qr_ladder_and_is_non_invasive():
    import sys
    sys.path.insert(0, str(ROOT / "harness" / "g33_fortran"))
    import g33_fortran_dump as fd

    canon = _build_and_run(dump=False)
    dump = _build_and_run(dump=True)

    # NON-INVASIVE: the instrumentation only adds WRITEs — the final prognostic
    # state and precip must be BYTE-IDENTICAL between the canonical and the
    # dump (overlay) builds. This is the Fortran analogue of C++ A/B/C.
    assert fd.parse_state(canon) == fd.parse_state(dump), \
        "overlay perturbed the final state — instrumentation is NOT non-invasive"
    assert fd.parse_prec(canon) == fd.parse_prec(dump), \
        "overlay perturbed precip — instrumentation is NOT non-invasive"

    # The dump carries the interior QR op ladder (top-first k >= 1; the top cell
    # k=0 is a separate branch not yet instrumented), 5 fields per (col, k, n).
    ops = fd.parse_ops(dump)
    assert ops, "no G33OP records emitted"
    fields = {(o["op"], o["field"]) for o in ops}
    assert fields == {
        ("QR_FALK", "falk_f32"), ("QR_OUTFLOW", "dq_out"),
        ("QR_INFLOW", "dq_in"), ("QR_FALLACC", "fall_after"),
        ("QR_UPDATE", "q_post"),
        ("NR_FALK", "falk_f32"), ("NR_OUTFLOW", "dn_out"),
        ("NR_INFLOW", "dn_in"), ("NR_FALLACC", "fall_after"),
        ("NR_UPDATE", "n_post")}, f"unexpected op/field set: {fields}"
    assert all(o["k"] >= 1 for o in ops), "interior ladder must be top-first k>=1"
    # canonical build emits NO G33OP (macro off).
    assert not fd.parse_ops(canon), "canonical build must not emit op records"
