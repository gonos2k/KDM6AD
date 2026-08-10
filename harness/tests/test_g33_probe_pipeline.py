"""The real probe/f64 driver output, through the real strict parser.

LOCAL ONLY (needs gfortran + the gitignored host reference tree).

The G33P schema literal in the Fortran driver drifted to 3 while the parser moved
to 4, and every probe and f64 bundle stopped being producible. Nothing failed,
because the parser's own tests build SYNTHETIC streams at the parser's version
and no test ever fed real driver output to `pr.read()` (owner P0-1).

A static version-consistency check lives in test_g33_probe_read.py so public CI
catches the literal drifting again. This file is the other half: it runs the
actual binary, which is the only thing that proves the pipeline works end to end.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_probe_read as pr  # noqa: E402

REPO = ROOT.parent
BUILD = ROOT / "g33_fortran" / "refine_build.sh"
REF = REPO / "host" / "KIM-meso_v1.0" / "phys" / "module_mp_kdm6.F"

pytestmark = pytest.mark.skipif(
    shutil.which("gfortran") is None or not REF.is_file(),
    reason="local-only (needs gfortran + the gitignored host reference tree)",
)


def _run(tmp, flag):
    out = tmp / "build"
    b = subprocess.run(["bash", str(BUILD), str(out),
                        "--fixture=g33_fixture_multisubcycle_v1",
                        "--algo=legacy", flag],
                       capture_output=True, text=True, cwd=REPO)
    assert b.returncode == 0, f"{flag} build failed:\n{b.stdout}\n{b.stderr}"
    r = subprocess.run([str(out / "g33_refine_driver"), "12", "rezero"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


@pytest.mark.parametrize("flag", ["--probe", "--f64"])
def test_the_real_driver_output_parses(tmp_path, flag):
    """The end-to-end check that was missing. Both arms emit G33P; if the
    driver's schema literal and the parser disagree by so much as one, this
    raises ProbeError and the whole arm is unproducible."""
    got = pr.read(_run(tmp_path, flag))
    assert got[("meta", "schema")] == pr.SCHEMA
    assert got[("meta", "source_precision")] == "f32"
    assert got[("meta", "rho_profile")] == "as-is"
    assert got[("meta", "tiles")]


def test_the_probe_arm_declares_f32_and_the_f64_arm_declares_f64(tmp_path):
    """An f64 stream and an f32 one are the same text with different numbers, so
    the declaration is what stops a reader mixing them."""
    assert pr.read(_run(tmp_path / "a", "--probe"))[("meta", "precision")] == "f32"
    assert pr.read(_run(tmp_path / "b", "--f64"))[("meta", "precision")] == "f64"


def test_a_real_precision_pair_compares_under_the_current_contract(tmp_path):
    """The comparison the f64 evidence rests on, run through the current
    toolchain rather than quoted from an archived result."""
    a = pr.read(_run(tmp_path / "a", "--probe"))
    b = pr.read(_run(tmp_path / "b", "--f64"))
    d = pr.diff(a, b, "precision_pair")
    assert d["records"] > 0 and d["ulp_lattice"] == "f32"


def test_a_real_f64_BUNDLE_can_be_produced(tmp_path):
    """The whole point of P0-1: with the schema literal drifted, this path raised
    ProbeError and no f64 bundle could be made at all. It also exercises the
    cross-member contract (owner §8.4) on real streams rather than synthetic
    ones — a three-member chain must satisfy every invariant at once."""
    import json
    import g33_refine_experiment as xp

    # `produce()` refuses unless every producing module's working bytes hash to
    # its HEAD blob (owner P0-1) -- correct for a bundle, wrong for a test suite
    # that runs while those modules are being edited. The check itself is
    # exercised in test_g33_refine_experiment.py, against the real function.
    monkeypatch_pin = pytest.MonkeyPatch()
    monkeypatch_pin.setattr(xp, "require_pinned_producer", lambda *a, **k: None)
    try:
            dest = xp.produce(tmp_path / "chain",
                          fixture="g33_fixture_multisubcycle_v1", algo="legacy",
                          nsplits=(3, 6, 12), mode="rezero", nflux=False,
                          module=REPO / "host/KIM-meso_v1.0/phys/module_mp_kdm6.F",
                          arm="f64")
    finally:
        monkeypatch_pin.undo()
    man = json.loads((dest / "manifest.json").read_text())
    assert man["arm"] == "f64" and man["precision"] == "f64"
    assert man["decision_eligible"] is False
    assert sorted(m["nsplit"] for m in man["members"]) == [3, 6, 12]
    assert all(m["precision"] == "f64" for m in man["members"])
