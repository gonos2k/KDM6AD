"""Departure against arrival, and the count that conflated two different events.

LOCAL ONLY (needs gfortran + the gitignored host reference tree). The numbers
this tool produces were published from a document before any tool existed, so the
binding test is that it reproduces them -- if the interface pairing is wrong, the
published figures do not come back.
"""
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_cap_interface as ci  # noqa: E402

REPO = ROOT.parent
BUILD = ROOT / "g33_fortran" / "refine_build.sh"
REF = REPO / "host" / "KIM-meso_v1.0" / "phys" / "module_mp_kdm6.F"

pytestmark = pytest.mark.skipif(
    shutil.which("gfortran") is None or not REF.is_file(),
    reason="local-only (needs gfortran + the gitignored host reference tree)",
)


@pytest.fixture(scope="module")
def stream(tmp_path_factory):
    out = tmp_path_factory.mktemp("cap") / "build"
    b = subprocess.run(["bash", str(BUILD), str(out),
                        "--fixture=g33_fixture_multisubcycle_v1",
                        "--algo=legacy", "--nflux"],
                       capture_output=True, text=True, cwd=REPO)
    assert b.returncode == 0, f"build failed:\n{b.stdout}\n{b.stderr}"
    r = subprocess.run([str(out / "g33_refine_driver"), "12", "rezero"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_the_cap_explains_the_whole_ice_mass_residual(stream):
    """The published figure: 100.00% on both ice columns. A wrong pairing gives
    some other percentage, so this is the test that the tool computes what the
    finding says it computes."""
    rows = ci.analysis(stream)["rows"]
    for col in ("2", "3"):
        assert rows[f"ice/{col}"]["explained"] == pytest.approx(1.0, abs=5e-5)


def test_the_main_chain_created_number_equals_the_measure_prediction(stream):
    """Ratio 1.0000 in all three columns -- the quantitative confirmation of the
    mechanism, on independently emitted per-interface transfers."""
    rows = ci.analysis(stream)["rows"]
    for col in ("1", "2", "3"):
        assert rows[f"main/{col}"]["created_over_predicted"] == \
            pytest.approx(1.0, abs=5e-4)


def test_the_ice_rows_are_cap_dominated_and_are_not_a_measure_measurement(stream):
    """-28.58 / -28.90: sign-flipped because the arrival is far below the
    uncapped value. The ice chain measures the cap, the main chain the measure."""
    rows = ci.analysis(stream)["rows"]
    assert rows["ice/2"]["created_over_predicted"] == pytest.approx(-28.58, abs=0.05)
    assert rows["ice/3"]["created_over_predicted"] == pytest.approx(-28.90, abs=0.05)


def test_the_binding_count_is_reported_PER_CHAIN_with_its_magnitude(stream):
    """The published claim was "39 of 255 interfaces, ALL in the ice chain". The
    ice count is exactly right; "all" was not. The main chain's departure and
    arrival differ at 23 interfaces too -- for a total interface term eight
    orders of magnitude smaller, which is WHY its residual stays at 1e-10.

    A bare count made those two the same event. The tool now reports the count
    beside the magnitude so they cannot be confused again."""
    a = ci.analysis(stream)
    assert a["total_interfaces"] == 255
    assert a["by_chain"]["ice"]["cap_bound"] == 39
    assert a["by_chain"]["main"]["cap_bound"] > 0, \
        "'all of them in the ice chain' would make this zero"
    assert a["by_chain"]["main"]["abs_interface_term"] < \
        1e-6 * a["by_chain"]["ice"]["abs_interface_term"]


def test_the_topmost_interface_is_included(stream):
    """The top cell is updated outside the interior loop, so CAPIN cannot see its
    departure; without TOPOUT the topmost interface is invisible and the residual
    would not close to 100%."""
    a = ci.analysis(stream)
    # K = 4 gives 3 interfaces per (column, chain, sub-step); dropping the top one
    # would give 2, so the count itself detects the omission.
    assert a["total_interfaces"] == 255


# ---- owner §2: "bit-for-bit" must be a raw-bit comparison, and it is SCOPED ---

@pytest.fixture(scope="module")
def variants(tmp_path_factory):
    """Both algorithms, same fixture, --nflux. Raw text, not parsed floats: the
    claim is about the stored patterns, so a float round-trip would be the wrong
    instrument."""
    out = {}
    for algo in ("legacy", "conservative"):
        d = tmp_path_factory.mktemp(algo) / "build"
        b = subprocess.run(["bash", str(BUILD), str(d),
                            "--fixture=g33_fixture_multisubcycle_v1",
                            f"--algo={algo}", "--nflux"],
                           capture_output=True, text=True, cwd=REPO)
        assert b.returncode == 0, f"{algo} build failed:\n{b.stdout}\n{b.stderr}"
        r = subprocess.run([str(d / "g33_refine_driver"), "12", "rezero", "3"],
                           capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        out[algo] = r.stdout
    return out


def _state(stream, field):
    return {(t[4], t[7], t[8]): t[10]
            for t in (l.split() for l in stream.splitlines())
            if len(t) > 10 and t[1] == "STAGE" and t[6] == field}


def _xfer(stream, idx):
    return {tuple(t[2:6]): t[7 + idx]
            for t in (l.split() for l in stream.splitlines())
            if len(t) > 8 and t[1] == "XFER"}


def test_the_MAIN_chain_is_raw_bit_identical_across_the_two_variants(variants):
    """The claim originally rested on two normalised residuals being equal, which
    is not a raw-bit comparison (owner §2). It is one now -- and it holds, which
    is WHY main/nr matches to the last digit rather than that being luck."""
    L, C = variants["legacy"], variants["conservative"]
    for field in ("nr", "qr"):
        a, b = _state(L, field), _state(C, field)
        assert a and a == b, f"main-chain {field} is not raw-bit identical"
    for idx in (0, 1):                      # dq then dn
        a, b = _xfer(L, idx), _xfer(C, idx)
        main = {k: v for k, v in a.items() if k[3] == "main"}
        assert main and all(b[k] == v for k, v in main.items())


def test_the_ICE_chain_is_NOT_identical_and_must_not_be(variants):
    """The conservative variant exists to fix the ice cap. If ice matched
    bit-for-bit the variant would not be doing anything, so this asserts the
    scope of the claim above rather than merely tolerating a difference."""
    L, C = variants["legacy"], variants["conservative"]
    for field in ("ni", "qi"):
        assert _state(L, field) != _state(C, field), \
            f"ice {field} is identical — the cap fix did nothing"
    ice = {k: v for k, v in _xfer(L, 1).items() if k[3] == "ice"}
    assert any(_xfer(C, 1)[k] != v for k, v in ice.items())
