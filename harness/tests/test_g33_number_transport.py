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


# ---- owner P0-4 / P0-1..P0-3: the number stream is a fail-closed protocol ----

def _hdr(nsplit=1, ntile=1, schema=1):
    return f"G33N STREAM_BEGIN {schema} {nsplit} {ntile} {nsplit*ntile} legacy rezero\n"


def _call(cid, cols=(1,), *, ks=2, end=True, drop=None, split=None, tile=1,
          loop=1):
    """One bracketed kernel call, complete unless asked otherwise."""
    split = cid if split is None else split
    out = [f"G33N CALL_BEGIN {cid} {split} {tile} 1 {len(cols)} {ks} 42C80000"]
    for stage in ("outer_pre_sed", "outer_post_sed"):
        for c in cols:
            for k in range(ks):
                for f in ("nr", "ni", "qr", "qi", "rho", "delz"):
                    if stage == "outer_post_sed" and f in ("rho", "delz"):
                        continue
                    out.append(f"G33F STAGE {loop} - {stage} 0 {f} {c} {k} f32 3F800000")
    for c in cols:
        out.append(f"G33F MSTEP {loop} main {c} i32 00000001")
        out.append(f"G33F MSTEPI {loop} {c} i32 00000001")
    for c in cols:
        for f in nt.NFLUX_FIELDS:
            if drop == f:
                continue
            out.append(f"G33F NFLUX {loop} {c} {f} f32 3F800000")
    if end:
        out.append(f"G33N CALL_END {cid} {split} {tile}")
    return "\n".join(out) + "\n"


def _stream(*calls, nsplit=None, ntile=1, end=True, **kw):
    n = len(calls) if nsplit is None else nsplit
    return (_hdr(n, ntile, **kw) + "".join(calls)
            + ("G33N STREAM_END\n" if end else ""))


def test_a_complete_stream_parses_into_bracketed_calls():
    got = list(nt.calls(_stream(_call(1), _call(2))))
    assert [c["call_id"] for c in got] == [1, 2]


def test_closed_prefix_truncation_is_rejected():
    """The defect the header exists for: a run that stops at a CLOSED call
    boundary used to be indistinguishable from a shorter run that finished."""
    s = _hdr(96) + _call(1) + _call(2)          # 2 of a declared 96, no STREAM_END
    with pytest.raises(nt.StreamError, match="no STREAM_END"):
        list(nt.calls(s))


def test_parsed_call_count_must_equal_the_declared_count():
    s = _hdr(96) + _call(1) + "G33N STREAM_END\n"
    with pytest.raises(nt.StreamError, match="carries 1 calls, header declared 96"):
        list(nt.calls(s))


def test_ntile2_has_unique_global_call_ids():
    """`s` alone repeats once per tile; a two-tile run must still be contiguous."""
    s = _stream(_call(1, split=1, tile=1), _call(2, split=1, tile=2),
                _call(3, split=2, tile=1), _call(4, split=2, tile=2),
                nsplit=2, ntile=2)
    assert [c["call_id"] for c in nt.calls(s)] == [1, 2, 3, 4]
    assert [(c["split"], c["tile"]) for c in nt.calls(s)] == [(1, 1), (1, 2),
                                                              (2, 1), (2, 2)]


def test_a_call_id_inconsistent_with_its_split_and_tile_is_rejected():
    s = _stream(_call(1, split=1, tile=1), _call(2, split=2, tile=2),
                nsplit=2, ntile=2)
    with pytest.raises(nt.StreamError, match="does not match split"):
        list(nt.calls(s))


def test_call_end_split_and_tile_must_match_the_begin():
    s = _stream(_call(1).replace("G33N CALL_END 1 1 1", "G33N CALL_END 1 2 1"))
    with pytest.raises(nt.StreamError, match="reports split/tile"):
        list(nt.calls(s))


def test_internal_loop2_does_not_overwrite_loop1():
    """A call with loops > 1 emits the same (stage, col, k) once per loop. The
    key carries the loop, so nothing is overwritten -- and the segment budget,
    which is defined for ONE loop, refuses the call rather than collapsing it."""
    two = _call(1).rstrip().rsplit("G33N CALL_END", 1)[0] \
        + _call(1, loop=2).split("42C80000\n", 1)[1]
    calls = list(nt.calls(_stream(two)))          # well-formed: parses
    assert calls[0]["loops"] == {1, 2}
    assert calls[0]["mstep"][(1, "ice", 1)] == 1
    assert calls[0]["mstep"][(2, "ice", 1)] == 1
    with pytest.raises(nt.StreamError, match="inner loops"):
        nt.single_loop(calls[0])


def test_a_duplicate_record_is_rejected_not_overwritten():
    s = _stream(_call(1) + "")
    dup = s.replace("G33F MSTEPI 1 1 i32 00000001",
                    "G33F MSTEPI 1 1 i32 00000001\nG33F MSTEPI 1 1 i32 00000009")
    with pytest.raises(nt.StreamError, match="duplicate record"):
        list(nt.calls(dup))


def test_an_unknown_G33N_record_inside_a_call_is_rejected():
    s = _stream(_call(1).replace("G33F MSTEP 1 main 1",
                                 "G33N SOMETHING 1\nG33F MSTEP 1 main 1"))
    with pytest.raises(nt.StreamError, match="unknown G33N record"):
        list(nt.calls(s))


def test_a_stream_declaring_another_schema_is_rejected():
    with pytest.raises(nt.StreamError, match="declares schema"):
        list(nt.calls(_stream(_call(1), schema=9)))


def test_an_inconsistent_header_is_rejected():
    s = "G33N STREAM_BEGIN 1 4 2 3 legacy rezero\n"
    with pytest.raises(nt.StreamError, match="header is inconsistent"):
        list(nt.calls(s))


def test_a_truncated_call_is_refused():
    with pytest.raises(nt.StreamError, match="ends inside call"):
        list(nt.calls(_hdr(2) + _call(1) + _call(2, end=False)))


def test_a_missing_call_is_refused():
    with pytest.raises(nt.StreamError, match="call ids jump"):
        list(nt.calls(_stream(_call(1), _call(3), nsplit=2)))


def test_an_unclosed_call_before_the_next_is_refused():
    with pytest.raises(nt.StreamError, match="never ended"):
        list(nt.calls(_stream(_call(1, end=False), _call(2))))


def test_an_incomplete_NFLUX_group_is_refused():
    with pytest.raises(nt.StreamError, match="NFLUX fields"):
        list(nt.calls(_stream(_call(1, drop="nflux_den"))))


def test_NFLUX_must_cover_the_state_columns():
    s = _stream(_call(1, cols=(1, 2)).replace("G33F NFLUX 1 2", "G33F NOPE 1 2"))
    with pytest.raises(nt.StreamError, match="NFLUX covers"):
        list(nt.calls(s))


def test_a_substep_count_missing_for_a_column_is_refused():
    s = _stream(_call(1, cols=(1, 2)).replace("G33F MSTEPI 1 2 i32 00000001\n", ""))
    with pytest.raises(nt.StreamError, match="ice sub-step counts"):
        list(nt.calls(s))


def test_a_nonpositive_operand_is_refused():
    s = _stream(_call(1).replace("NFLUX 1 1 nflux_delz f32 3F800000",
                                 "NFLUX 1 1 nflux_delz f32 00000000"))
    with pytest.raises(nt.StreamError, match="nflux_delz=0"):
        list(nt.calls(s))


def test_records_outside_any_call_are_not_attributed_to_one():
    stray = "G33F MSTEPI 1 1 i32 00000009\n"
    s = _hdr(1) + stray + _call(1) + "G33N STREAM_END\n"
    got = list(nt.calls(s))
    assert [c["call_id"] for c in got] == [1]
    assert got[0]["mstep"][(1, "ice", 1)] == 1


def test_a_nonzero_driver_exit_is_rejected(tmp_path):
    """stdout is not evidence when the process that wrote it failed."""
    exe = tmp_path / "fail"
    exe.write_text("#!/bin/sh\necho 'G33N STREAM_BEGIN 1 1 1 1 legacy rezero'\nexit 3\n")
    exe.chmod(0o755)
    with pytest.raises(SystemExit, match="exited 3"):
        nt.main([str(exe), "1"])
