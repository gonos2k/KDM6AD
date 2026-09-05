"""Mean particle mass and column number (owner review §7).

The diagnostic's value depends entirely on measuring against the right baseline,
so that is what these pin.
"""
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_number_budget as nb   # noqa: E402
import g33_refine_analyze as ra  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_g33_refine_analyze import _stream, _write   # noqa: E402


def _bits(x):
    return f"{struct.unpack('<I', struct.pack('<f', x))[0]:08X}"


def _run(tmp_path, name, qi=1.0e-6, ni=1.0e3, rho=1.0):
    lines = _stream(nsplit=3, B=1, K=2).splitlines()
    body = [l for l in lines[1:-1]
            if not (l.startswith("G33R STATE qi") or l.startswith("G33R STATE ni"))]
    body += [f"G33R STATE qi 1 {k} {_bits(qi)}" for k in range(2)]
    body += [f"G33R STATE ni 1 {k} {_bits(ni)}" for k in range(2)]
    body += [f"G33R FORCING {n} 1 {k} {_bits(v)}"
             for n, v in (("rho", rho), ("delz", 1.0), ("pii", 1.0))
             for k in range(2)]
    return ra.read(_write(tmp_path, "\n".join([lines[0]] + body + ["G33R END"]) + "\n",
                          name))


def _budget_stream(algo, *, state_bits="3F800000", rho_bits="3F800000",
                   mode="rezero"):
    lines = _stream(nsplit=3, mode=mode, algo=algo, B=1, K=2).splitlines()
    body = lines[1:-1]
    body += [f"G33R FORCING {name} 1 {k} {bits}"
             for name, bits in (("rho", rho_bits), ("delz", "3F800000"),
                                ("pii", "3F800000")) for k in range(2)]
    body = [line.replace("3F800000", state_bits)
            if line.startswith("G33R STATE qg ") else line for line in body]
    return "\n".join([lines[0]] + body + ["G33R END"]) + "\n"


def test_mean_particle_mass_is_q_over_n(tmp_path):
    m = nb.mean_particle_mass(_run(tmp_path, "a.txt", qi=2.0e-6, ni=1.0e3))
    assert m[("qi", 1, 0)] == pytest.approx(2.0e-9)


def test_an_absent_species_is_skipped_not_reported_as_extreme(tmp_path):
    """q/n on a near-empty cell is a huge meaningless number, and reporting it
    would swamp the real signal."""
    m = nb.mean_particle_mass(_run(tmp_path, "b.txt", qi=1.0e-30, ni=1.0e-30))
    assert ("qi", 1, 0) not in m


def test_column_number_is_rho_dz_weighted(tmp_path):
    """Not a bare sum over levels: the physical column number is the rho*dz
    measure, which is the whole subject of §7."""
    n1 = nb.column_number(_run(tmp_path, "c.txt", ni=1.0e3, rho=1.0))
    n2 = nb.column_number(_run(tmp_path, "d.txt", ni=1.0e3, rho=2.0))
    assert n2[("ni", 1)] == pytest.approx(2 * n1[("ni", 1)])


def test_column_number_needs_forcing(tmp_path):
    assert nb.column_number(ra.read(_write(tmp_path, _stream(), "e.txt"))) == {}


def test_the_pairs_are_the_two_moment_species():
    """A pair that is not two-moment would produce a q/n with no meaning."""
    assert nb.PAIRS == (("qr", "nr"), ("qi", "ni"), ("qc", "nc"))
    for q, n in nb.PAIRS:
        assert q in ra.MASS and n in ra.NUMBER


def test_the_module_does_not_reuse_the_chain_universe_check():
    """`require_same_universe` also demands ONE algorithm, which is right for
    refinement members and wrong here -- comparing legacy against conservative is
    the entire point, and reusing it made the comparison impossible to run."""
    src = (ROOT / "g33_number_budget.py").read_text()
    code = "\n".join(l.split("#", 1)[0] for l in src.splitlines())
    assert "require_same_universe" not in code


def test_member_directory_must_be_nonempty_and_exact(tmp_path):
    legacy, conservative = tmp_path / "legacy", tmp_path / "conservative"
    legacy.mkdir(); conservative.mkdir()
    with pytest.raises(ValueError, match="no n\\*\\.txt"):
        nb._require_matching_members(legacy, conservative)

    (legacy / "n1.txt").write_text("placeholder")
    with pytest.raises(ValueError, match="missing conservative"):
        nb._require_matching_members(legacy, conservative)
    (conservative / "n2.txt").write_text("placeholder")
    with pytest.raises(ValueError, match="member sets differ"):
        nb._require_matching_members(legacy, conservative)
    (conservative / "n2.txt").unlink()
    (conservative / "n1.txt").write_text("placeholder")
    assert set(nb._require_matching_members(legacy, conservative)) == {"n1.txt"}


def test_number_budget_labels_basis_as_unresolved():
    assert "UNRESOLVED" in nb.NUMBER_BASIS
    assert "#/kg_d" in nb.NUMBER_BASIS and "#/m3" in nb.NUMBER_BASIS


def test_compare_accepts_signed_qg_state_but_rejects_negative_measure(tmp_path):
    """Signed final diagnostics (including known QIB/QG pathology) are observed
    state, while rho/delz are positive forcing metrics used by this budget."""
    legacy = _write(tmp_path, _budget_stream("legacy", state_bits="BF800000"),
                    "n3.legacy.txt")
    conservative = _write(tmp_path, _budget_stream("conservative", state_bits="BF800000"),
                          "n3.conservative.txt")
    nb.compare(legacy, conservative)

    bad = _write(tmp_path, _budget_stream("legacy", rho_bits="BF800000"),
                 "n3.bad.txt")
    with pytest.raises(ra.RefineError, match="rho.*finite and > 0"):
        nb.compare(bad, conservative)


def test_compare_rejects_a_changed_shared_rho_measure(tmp_path):
    """A rho=1 legacy / rho=2 conservative pair must not read as interface-only."""
    legacy = _write(tmp_path, _budget_stream("legacy"), "n3.legacy.txt")
    conservative = _write(tmp_path, _budget_stream("conservative", rho_bits="40000000"),
                          "n3.conservative.txt")
    with pytest.raises(ra.RefineError, match="shared forcing value.*rho"):
        nb.compare(legacy, conservative)


def test_compare_requires_the_legacy_conservative_pair(tmp_path):
    legacy = _write(tmp_path, _budget_stream("legacy"), "n3.legacy.txt")
    wrong = _write(tmp_path, _budget_stream("legacy"), "n3.wrong.txt")
    with pytest.raises(ra.RefineError, match="expected conservative"):
        nb.compare(legacy, wrong)
