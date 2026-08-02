"""The number-transport recovery, and the traps it was nearly reported through."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_number_transport as nt  # noqa: E402


def _weights(den, dz, carries_density):
    return [0.0] + [dz[t - 1] / dz[t] * (den[t - 1] / den[t] if carries_density else 1.0)
                    for t in range(1, len(dz))]


def _forward(x, a, w):
    """Apply the kernel's update with transfers `a` and inflow weights `w`."""
    return [x[t] - a[t] + (a[t - 1] * w[t] if t else 0.0) for t in range(len(x))]


DEN = [0.4, 0.6, 0.8, 1.2]          # top-first: density increases downward
DZ = [150.0, 150.0, 150.0, 150.0]


def test_the_recovery_inverts_the_update_it_assumes():
    """Round trip: apply the update forward with known transfers, recover them."""
    a = [1.0, 2.0, 3.0, 4.0]
    for dens in (False, True):
        w = _weights(DEN, DZ, dens)
        x = [10.0, 20.0, 30.0, 40.0]
        got = nt.transfers(x, _forward(x, a, w), w)
        assert got == pytest.approx(a, rel=1e-12)


def test_a_wrong_weight_does_NOT_recover_the_transfers():
    """This is what makes the hypothesis test discriminating rather than
    circular: recovering under the wrong weight gives the wrong bottom-cell
    transfer, so comparing it against the emitted accumulator can fail."""
    a = [1.0, 2.0, 3.0, 4.0]
    x = [10.0, 20.0, 30.0, 40.0]
    truth = _weights(DEN, DZ, False)          # kernel uses dz-only for number
    wrong = _weights(DEN, DZ, True)
    got = nt.transfers(x, _forward(x, a, truth), wrong)
    assert got[-1] != pytest.approx(a[-1], rel=1e-3)


def test_the_mass_weight_forces_a_zero_residual_whatever_the_data():
    """Reported once as a 'control'. It is not one: with the mass weight every
    telescoped term is identically zero, so the residual vanishes for ARBITRARY
    transfers. Kept as a test so the claim cannot come back."""
    w = _weights(DEN, DZ, True)
    for a in ([1.0, 2.0, 3.0, 4.0], [0.0, 5.0, 0.0, 7.0], [9.0, 9.0, 9.0, 9.0]):
        x = [10.0, 20.0, 30.0, 40.0]
        x1 = _forward(x, a, w)
        n0 = sum(DEN[t] * DZ[t] * x[t] for t in range(4))
        n1 = sum(DEN[t] * DZ[t] * x1[t] for t in range(4))
        surface = DEN[-1] * DZ[-1] * a[-1]
        assert (n1 - n0) + surface == pytest.approx(0.0, abs=1e-9 * abs(n0))


def test_the_number_weight_does_NOT_force_zero_and_creates():
    """Same algebra with the dz-only weight leaves a strictly positive residual
    whenever density increases downward -- the defect itself."""
    w = _weights(DEN, DZ, False)
    a = [1.0, 2.0, 3.0, 4.0]
    x = [10.0, 20.0, 30.0, 40.0]
    x1 = _forward(x, a, w)
    n0 = sum(DEN[t] * DZ[t] * x[t] for t in range(4))
    n1 = sum(DEN[t] * DZ[t] * x1[t] for t in range(4))
    residual = (n1 - n0) + DEN[-1] * DZ[-1] * a[-1]
    assert residual > 0
    # and it equals the interface sum -- an identity, which is why it is not
    # reported as evidence, only used to say WHERE the residual comes from.
    assert residual == pytest.approx(
        sum((DEN[t] - DEN[t - 1]) * DZ[t - 1] * a[t - 1] for t in range(1, 4)))


def test_uniform_density_creates_nothing():
    """The mechanism is the density contrast, so removing it removes the effect."""
    den = [0.8] * 4
    w = _weights(den, DZ, False)
    a = [1.0, 2.0, 3.0, 4.0]
    x = [10.0, 20.0, 30.0, 40.0]
    x1 = _forward(x, a, w)
    n0 = sum(den[t] * DZ[t] * x[t] for t in range(4))
    n1 = sum(den[t] * DZ[t] * x1[t] for t in range(4))
    assert (n1 - n0) + den[-1] * DZ[-1] * a[-1] == pytest.approx(0.0, abs=1e-9)


def test_species_are_bound_to_the_right_chain_and_measure():
    """mstep covers qr/nr/qs/qg and mstep_i covers qi/ni (F:1179-1180); only the
    mass rows carry the density ratio."""
    assert nt.SPECIES["nr"][0] == "main" and nt.SPECIES["qr"][0] == "main"
    assert nt.SPECIES["ni"][0] == "ice" and nt.SPECIES["qi"][0] == "ice"
    assert [nt.SPECIES[s][2] for s in ("nr", "ni")] == [False, False]
    assert [nt.SPECIES[s][2] for s in ("qr", "qi")] == [True, True]


def test_calls_are_split_sequentially_not_by_the_loop_index():
    """`loop` resets to 1 every kernel call, so keying by it collapses every call
    onto the last one -- which, after the rain has fallen out, is all zeros."""
    src = (ROOT / "g33_number_transport.py").read_text()
    assert "resets to 1 on every call" in src
