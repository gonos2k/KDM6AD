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


def test_calls_with_an_IDENTICAL_loop_index_are_still_separated():
    """The kernel's `loop` resets to 1 on every external call, so keying by it
    collapses every call onto the last -- which, after the rain has fallen out,
    is all zeros. The driver's brackets are what separate them; this asserts the
    separation itself rather than the comment explaining it."""
    got = list(nt.calls(_call(1) + _call(2) + _call(3)))
    assert [c["call_id"] for c in got] == [1, 2, 3]
    assert all(c["outer_pre_sed"] for c in got), "each call carries its own state"


# ---- owner P0-4: the number stream is a protocol, not a byproduct ------------

def _call(cid, cols=(1,), *, ks=2, end=True, drop=None):
    """One bracketed kernel call, complete unless asked otherwise."""
    out = [f"G33N CALL_BEGIN {cid} 1 1 42C80000"]
    for stage in ("outer_pre_sed", "outer_post_sed"):
        for c in cols:
            for k in range(ks):
                for f in ("nr", "ni", "qr", "qi", "rho", "delz"):
                    if stage == "outer_post_sed" and f in ("rho", "delz"):
                        continue
                    out.append(f"G33F STAGE 1 - {stage} 0 {f} {c} {k} f32 3F800000")
    for c in cols:
        out.append(f"G33F MSTEP 1 main {c} i32 00000001")
        out.append(f"G33F MSTEPI 1 {c} i32 00000001")
    for c in cols:
        for f in nt.NFLUX_FIELDS:
            if drop == f:
                continue
            out.append(f"G33F NFLUX 1 {c} {f} f32 3F800000")
    if end:
        out.append(f"G33N CALL_END {cid} 1")
    return "\n".join(out) + "\n"


def test_a_complete_stream_parses_into_bracketed_calls():
    got = list(nt.calls(_call(1) + _call(2)))
    assert [c["call_id"] for c in got] == [1, 2]


def test_a_truncated_call_is_refused():
    """The failure this protocol exists to catch: a stream that stops mid-call
    used to be re-attributed to the previous one by record order."""
    with pytest.raises(nt.StreamError, match="ends inside call"):
        list(nt.calls(_call(1) + _call(2, end=False)))


def test_a_missing_call_is_refused():
    with pytest.raises(nt.StreamError, match="call ids jump"):
        list(nt.calls(_call(1) + _call(3)))


def test_an_unclosed_call_before_the_next_is_refused():
    with pytest.raises(nt.StreamError, match="never ended"):
        list(nt.calls(_call(1, end=False) + _call(2)))


def test_an_incomplete_NFLUX_group_is_refused():
    with pytest.raises(nt.StreamError, match="NFLUX fields"):
        list(nt.calls(_call(1, drop="nflux_den")))


def test_NFLUX_must_cover_the_state_columns():
    s = _call(1, cols=(1, 2)).replace("G33F NFLUX 1 2", "G33F NOPE 1 2")
    with pytest.raises(nt.StreamError, match="NFLUX covers"):
        list(nt.calls(s))


def test_a_substep_count_missing_for_a_column_is_refused():
    s = _call(1, cols=(1, 2)).replace("G33F MSTEPI 1 2 i32 00000001\n", "")
    with pytest.raises(nt.StreamError, match="ice sub-step counts"):
        list(nt.calls(s))


def test_a_nonpositive_operand_is_refused():
    s = _call(1).replace("NFLUX 1 1 nflux_delz f32 3F800000",
                         "NFLUX 1 1 nflux_delz f32 00000000")
    with pytest.raises(nt.StreamError, match="nflux_delz=0"):
        list(nt.calls(s))


def test_records_outside_any_call_are_not_attributed_to_one():
    """Stray records used to join whichever call was being accumulated."""
    stray = "G33F MSTEPI 1 1 i32 00000009\n"
    assert [c["call_id"] for c in nt.calls(stray + _call(1))] == [1]
    assert nt.calls(stray + _call(1)).__next__()["mstep"][("ice", 1)] == 1
