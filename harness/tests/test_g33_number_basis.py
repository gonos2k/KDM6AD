"""What Arm N leaves against the physical measure, and why one fixture cannot say.

Arm N closes the OPERATOR's ledger, which is moist. The physical column number
is taken in dry mass (G33-BASIS-006), so a gap remains, and the tool's whole
claim is that the gap is the MOISTURE JUMP and nothing else.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_number_basis as nb  # noqa: E402

np = pytest.importorskip("numpy")


def _state(tmp_path, press, qv, name="wrfinput_synthetic"):
    """A WRF-shaped file with an explicit pressure and moisture profile.

    Synthetic, so the tool's properties are tested where CI runs: `host/**` is
    private and gitignored, and a test that needs it is silent on every public
    checkout.
    """
    netCDF4 = pytest.importorskip("netCDF4")
    path = tmp_path / name
    n = len(press)
    with netCDF4.Dataset(str(path), "w") as d:
        d.createDimension("Time", 1)
        d.createDimension("bottom_top", n)
        d.createDimension("south_north", 1)
        d.createDimension("west_east", 1)
        dims = ("Time", "bottom_top", "south_north", "west_east")
        for var, val in (("P", np.asarray(press, dtype="f8")),
                         ("PB", np.zeros(n)),
                         ("T", np.zeros(n)),          # theta = 300
                         ("QVAPOR", np.asarray(qv, dtype="f8"))):
            v = d.createVariable(var, "f8", dims)
            v[0, :, 0, 0] = val
    return path


PRESS = [1.0e5, 9.0e4, 8.0e4, 7.0e4, 6.0e4]


def test_uniform_moisture_leaves_arm_N_nothing_to_answer_for(tmp_path):
    """The archive's situation, as a property.

    Every published stream carrying qv carries it uniform in the column, so the
    two ledgers differ by a constant per column and cancel out of every ratio.
    That is why the basis question stayed open on fixture evidence -- not
    because Arm N was measured and found wanting.
    """
    got = nb.profile(_state(tmp_path, PRESS, [8e-3] * len(PRESS)))
    assert np.abs(got["armn_dry"]).max() < 1e-15, got["armn_dry"]
    assert np.abs(got["legacy_dry"]).max() > 0.05      # legacy still leaks


def test_what_arm_N_leaves_does_not_depend_on_the_density_profile(tmp_path):
    """The striking half of the closed form: it is the moisture jump ALONE.

    Two states with the same moisture and a differently SHAPED pressure
    profile must give the same `armn_dry` -- while `legacy_dry` moves. Shape,
    not scale: `den` goes as a power of `p`, so multiplying the whole profile
    by a constant leaves every interface ratio exactly where it was, and a
    test built on that would pass while measuring nothing.
    """
    qv = [1.6e-2, 1.2e-2, 6.0e-3, 2.0e-3, 4.0e-4]
    a = nb.profile(_state(tmp_path, PRESS, qv, "a"))
    b = nb.profile(_state(tmp_path, [1.0e5, 9.7e4, 9.3e4, 6.0e4, 3.0e4], qv, "b"))
    assert np.allclose(a["armn_dry"], b["armn_dry"], rtol=0, atol=1e-15)
    assert not np.allclose(a["legacy_dry"], b["legacy_dry"], rtol=1e-6)


def test_the_two_terms_compose_exactly_not_approximately(tmp_path):
    """`1 + eps_legacy_dry = (1 + eps_legacy_moist) * (1 + eps_armn_dry)`.

    Stated as an identity, so it is tested as one: the legacy defect against
    the physical measure FACTORISES, and Arm N removes exactly one factor. An
    approximate version of this would make the remaining term a residue of the
    algebra rather than a measured quantity.
    """
    got = nb.profile(_state(tmp_path, PRESS, [1.8e-2, 1.0e-2, 5e-3, 1e-3, 1e-4]))
    lhs = (1 + got["legacy_moist"]) * (1 + got["armn_dry"])
    assert np.abs(lhs - (1 + got["legacy_dry"])).max() < 1e-15


def test_the_tail_is_reported_with_its_absolute_scale(tmp_path):
    """A ratio without its scale is not a result.

    Where the density profile is near-neutral the fraction Arm N leaves blows
    up, because legacy had almost no defect there. The report must carry the
    absolute size at that tail, or a reader sees a maximum that is an artefact
    of the denominator.
    """
    press = [1.0e5, 9.99e4, 8.0e4, 7.0e4]        # first interface near-isopycnal
    got = nb.report(_state(tmp_path, press, [1.8e-2, 1.0e-2, 5e-3, 1e-3]))
    frac = got["armn_residual_fraction"]
    assert frac["max"] > frac["p90"]
    assert "tail_abs_armn_median" in frac and "tail_abs_legacy_median" in frac
    assert got["composition_max_abs_error"] < 1e-15


def _stream_call(qv, den, dz, x, x1, algorithm="legacy"):
    """A minimal parsed call, so the ledger arithmetic is tested without a run."""
    pre = {(1, 1, k): {"rho": den[k], "qv": qv[k], "delz": dz[k], "nr": x[k]}
           for k in range(len(qv))}
    post = {(1, 1, k): {"nr": x1[k]} for k in range(len(qv))}
    return {"outer_pre_sed": pre, "outer_post_sed": post, "loops": {1},
            "algorithm": algorithm}


def test_a_uniform_moisture_column_cannot_tell_the_two_ledgers_apart(monkeypatch):
    """The archive's situation, as arithmetic.

    With `qv` constant down the column the dry measure is the moist one times a
    constant, so the two residuals are proportional and carry the same
    information. No fixture published before this one could have shown a
    difference, whatever the arm did.
    """
    import g33_number_transport as nt
    den, dz = [0.4, 0.6, 0.9, 1.2], [300.0, 300.0, 300.0, 300.0]
    x, x1 = [5.0, 4.0, 3.0, 2.0], [4.0, 3.6, 2.9, 2.3]
    call = _stream_call([8e-3] * 4, den, dz, x, x1)
    monkeypatch.setattr(nt, "calls", lambda t: [call])
    monkeypatch.setattr(nt, "single_loop", lambda c: 1)
    got = nb.from_stream("", "nr")[1]
    assert got["moist"] / got["start_moist"] == pytest.approx(
        got["dry"] / got["start_dry"], rel=1e-12)


def test_a_moisture_gradient_makes_them_different_questions(monkeypatch):
    """With `qv` varying down the column the proportionality is gone."""
    import g33_number_transport as nt
    den, dz = [0.4, 0.6, 0.9, 1.2], [300.0, 300.0, 300.0, 300.0]
    x, x1 = [5.0, 4.0, 3.0, 2.0], [4.0, 3.6, 2.9, 2.3]
    call = _stream_call([5e-4, 2e-3, 6e-3, 1.4e-2], den, dz, x, x1)
    monkeypatch.setattr(nt, "calls", lambda t: [call])
    monkeypatch.setattr(nt, "single_loop", lambda c: 1)
    got = nb.from_stream("", "nr")[1]
    assert got["moist"] / got["start_moist"] != pytest.approx(
        got["dry"] / got["start_dry"], rel=1e-6)


def test_the_closed_form_is_an_identity_not_a_fit(monkeypatch):
    """`R = sum a_j dz_j (B_{j+1} A_j / A_{j+1} - B_j)`, evaluated from the same
    recovered transfers. Measured 1.00000000 on all six rows of the gradient
    fixture; here it is required rather than observed."""
    import g33_number_transport as nt
    den, dz = [0.4, 0.6, 0.9, 1.2], [300.0, 340.0, 380.0, 420.0]
    x, x1 = [5.0, 4.0, 3.0, 2.0], [4.0, 3.6, 2.9, 2.3]
    call = _stream_call([5e-4, 2e-3, 6e-3, 1.4e-2], den, dz, x, x1)
    monkeypatch.setattr(nt, "calls", lambda t: [call])
    monkeypatch.setattr(nt, "single_loop", lambda c: 1)
    got = nb.from_stream("", "nr")[1]
    for tag in ("moist", "dry"):
        assert got[f"{tag}_predicted_over_measured"] == pytest.approx(1.0, rel=1e-9)


def test_an_arm_whose_weight_IS_the_ledger_predicts_algebraic_zero(monkeypatch):
    """`A == B` makes every term of the closed form vanish ALGEBRAICALLY.

    Not bit-exactly: `B[j+1]*A[j]/A[j+1] - B[j]` is a division and a multiply
    that round, so evaluated in f64 it lands near 1e-14 rather than on 0.0.
    Requiring exact zero would be requiring the arithmetic to be something it is
    not; requiring it to be negligible against the DRY term is the real claim.
    """
    import g33_number_transport as nt
    den, dz = [0.4, 0.6, 0.9, 1.2], [300.0, 340.0, 380.0, 420.0]
    x, x1 = [5.0, 4.0, 3.0, 2.0], [4.0, 3.6, 2.9, 2.3]
    call = _stream_call([5e-4, 2e-3, 6e-3, 1.4e-2], den, dz, x, x1,
                        algorithm="nmass")
    monkeypatch.setattr(nt, "calls", lambda t: [call])
    monkeypatch.setattr(nt, "single_loop", lambda c: 1)
    got = nb.from_stream("", "nr")[1]
    assert abs(got["moist_predicted"]) < 1e-12 * abs(got["start_moist"])
    assert abs(got["dry_predicted"]) > 1e-6 * abs(got["start_dry"])
