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
    got = list(nt.calls(_stream(_call(1), _call(2), _call(3))))
    assert [c["call_id"] for c in got] == [1, 2, 3]
    assert all(c["outer_pre_sed"] for c in got), "each call carries its own state"


# ---- owner P0-4 / P0-1..P0-3: the number stream is a fail-closed protocol ----

#: schema 2 declares the features the stream carries. The default is the core
#: set: the extension records have their own completeness checks, so a helper
#: that declared them without emitting them would fail for the right reason but
#: obscure the test that wanted them.
def _hdr(nsplit=1, ntile=1, schema=4, feats="mstep,mstepi,nflux",
         rho_profile="as-is"):
    return (f"G33N STREAM_BEGIN {schema} {nsplit} {ntile} {nsplit*ntile} "
            f"legacy rezero {feats} {rho_profile}\n")


def _call(cid, cols=(1,), *, ks=2, end=True, drop=None, split=None, tile=1,
          loop=1):
    """One bracketed kernel call, complete unless asked otherwise.

    CALL_BEGIN declares the column range it actually emits: the range is a
    contract the parser checks, so a helper that lied about it would be testing
    the wrong thing (owner P0-3).
    """
    split = cid if split is None else split
    out = [f"G33N CALL_BEGIN {cid} {split} {tile} {min(cols)} {max(cols)} "
           f"{ks} 42C80000"]
    for stage in ("outer_pre_sed", "outer_post_sed"):
        for c in cols:
            for k in range(ks):
                # qv at BOTH endpoints: the dry basis needs rho_d = rho_m/(1+qv)
                # and carrying it at both makes "sedimentation does not touch qv"
                # checkable rather than assumed.
                for f in ("nr", "ni", "qr", "qi", "qv", "rho", "delz"):
                    if stage == "outer_post_sed" and f in ("rho", "delz"):
                        continue
                    out.append(f"G33F STAGE {loop} - {stage} 0 {f} {c} {k} f32 3F800000")
    for c in cols:
        # the surface stage has an exact universe AND an exact vocabulary:
        # one row per column at k = -1, carrying the protocol's seven fields
        for sf in sorted(nt.SURFACE_REQUIRED):
            out.append(f"G33F STAGE {loop} - surface 0 {sf} {c} -1 "
                       f"f32 3F800000")
    for c in cols:
        out.append(f"G33F MSTEP {loop} main {c} i32 00000001")
        out.append(f"G33F MSTEPI {loop} {c} i32 00000001")
    for c in cols:
        for f in nt.NFLUX_FIELDS:
            if drop == f:
                continue
            # dtcld restates delt/loops and den/delz the bottom cell -- the
            # parser now compares the duplicates, so the helper must emit a
            # CONSISTENT stream (delt=100, loops=1 -> dtcld=100).
            hexv = "42C80000" if f == "nflux_dtcld" else "3F800000"
            out.append(f"G33F NFLUX {loop} {c} {f} f32 {hexv}")
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
    with pytest.raises(nt.StreamError, match="last G33N record is not STREAM_END"):
        list(nt.calls(s))


def test_parsed_call_count_must_equal_the_declared_count():
    s = _hdr(96) + _call(1) + "G33N STREAM_END\n"
    with pytest.raises(nt.StreamError, match="carries 1 calls, header declared 96"):
        list(nt.calls(s))


def test_ntile2_has_unique_global_call_ids():
    """`s` alone repeats once per tile; a two-tile run must still be contiguous.
    The tiles cover disjoint columns, as a real decomposition does."""
    s = _stream(_call(1, cols=(1,), split=1, tile=1),
                _call(2, cols=(2,), split=1, tile=2),
                _call(3, cols=(1,), split=2, tile=1),
                _call(4, cols=(2,), split=2, tile=2),
                nsplit=2, ntile=2)
    assert [c["call_id"] for c in nt.calls(s)] == [1, 2, 3, 4]
    assert [(c["split"], c["tile"]) for c in nt.calls(s)] == [(1, 1), (1, 2),
                                                              (2, 1), (2, 2)]


def test_a_call_id_inconsistent_with_its_split_and_tile_is_rejected():
    s = _stream(_call(1, cols=(1,), split=1, tile=1),
                _call(2, cols=(2,), split=2, tile=2), nsplit=2, ntile=2)
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
    # a 2-loop call sub-cycles at dtcld = delt/2, and the parser now
    # compares that duplicate fact -- so the composed stream must say 50.0
    half = _call(1).replace("nflux_dtcld f32 42C80000",
                            "nflux_dtcld f32 42480000")
    half2 = _call(1, loop=2).replace("nflux_dtcld f32 42C80000",
                                     "nflux_dtcld f32 42480000")
    two = half.rstrip().rsplit("G33N CALL_END", 1)[0] \
        + half2.split("42C80000\n", 1)[1]
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
    s = "G33N STREAM_BEGIN 4 4 2 3 legacy rezero mstep as-is\nG33N STREAM_END\n"
    with pytest.raises(nt.StreamError, match="header is inconsistent"):
        list(nt.calls(s))


def test_a_truncated_call_is_refused():
    s = _hdr(2) + _call(1) + _call(2, end=False) + "G33N STREAM_END\n"
    with pytest.raises(nt.StreamError, match="STREAM_END inside call"):
        list(nt.calls(s))


def test_a_headerless_stream_is_refused(tmp_path):
    """The bypass: without the header the expected-count check never ran, so a
    closed-prefix truncation passed as a shorter run that finished (owner P0-1)."""
    with pytest.raises(nt.StreamError, match="first G33N record is not STREAM_BEGIN"):
        list(nt.calls(_call(1) + _call(2)))


def test_a_stream_not_ending_in_STREAM_END_is_refused():
    with pytest.raises(nt.StreamError, match="last G33N record is not STREAM_END"):
        list(nt.calls(_hdr(1) + _call(1)))


def test_two_headers_are_refused():
    with pytest.raises(nt.StreamError, match="more than one STREAM_BEGIN"):
        list(nt.calls(_hdr(1) + _hdr(1) + _call(1) + "G33N STREAM_END\n"))


def test_partial_consumption_cannot_skip_the_end_checks():
    """`calls()` returned a generator, so taking the first call with next() and
    stopping never reached the expected-count check (owner P0-1)."""
    s = _hdr(96) + _call(1) + "G33N STREAM_END\n"
    with pytest.raises(nt.StreamError, match="carries 1 calls"):
        next(iter(nt.calls(s)))


def test_tiles_with_a_gap_or_overlap_are_refused():
    s = _stream(_call(1, cols=(1,), split=1, tile=1),
                _call(2, cols=(3,), split=1, tile=2), nsplit=1, ntile=2)
    with pytest.raises(nt.StreamError, match="domain stands at column 2"):
        list(nt.calls(s))


def test_a_column_outside_the_declared_range_is_refused():
    s = _stream(_call(1, cols=(1,)).replace("outer_pre_sed 0 nr 1 0",
                                            "outer_pre_sed 0 nr 5 0"))
    with pytest.raises(nt.StreamError, match="CALL_BEGIN declared"):
        list(nt.calls(s))


def test_levels_disagreeing_with_the_declared_K_are_refused():
    s = _stream(_call(1, ks=2).replace(
        "G33N CALL_BEGIN 1 1 1 1 1 2", "G33N CALL_BEGIN 1 1 1 1 1 3"))
    with pytest.raises(nt.StreamError, match="declared K=3"):
        list(nt.calls(s))


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
    """Drop column 2's NFLUX rather than renaming it: an unrecognised family is
    now refused earlier, which would test a different guard."""
    body = "\n".join(l for l in _call(1, cols=(1, 2)).splitlines()
                     if not l.startswith("G33F NFLUX 1 2 ")) + "\n"
    with pytest.raises(nt.StreamError, match="NFLUX covers"):
        list(nt.calls(_stream(body)))


def test_an_unknown_G33F_FAMILY_is_refused():
    """A family this parser has never heard of is a protocol mismatch; an
    unconsumed STAGE is not (the stream legitimately carries stages this parser
    does not read)."""
    inside = _call(1).replace("G33F MSTEP 1 main 1",
                              "G33F NOPE 1 1 1 f32 3F800000\nG33F MSTEP 1 main 1")
    with pytest.raises(nt.StreamError, match="unknown G33F record family"):
        list(nt.calls(_stream(inside)))
    # an unconsumed STAGE inside a call is fine: the stream legitimately carries
    # stages this parser does not read
    ok = _call(1).replace(
        "G33F MSTEP 1 main 1",
        "G33F STAGE 0 - kernel_init_constants 0 pi 1 3 f32 40490FDB\n"
        "G33F MSTEP 1 main 1")
    assert len(nt.calls(_stream(ok))) == 1


def test_a_substep_count_missing_for_a_column_is_refused():
    s = _stream(_call(1, cols=(1, 2)).replace("G33F MSTEPI 1 2 i32 00000001\n", ""))
    with pytest.raises(nt.StreamError, match="ice sub-step counts"):
        list(nt.calls(s))


def test_a_nonpositive_operand_is_refused():
    s = _stream(_call(1).replace("NFLUX 1 1 nflux_delz f32 3F800000",
                                 "NFLUX 1 1 nflux_delz f32 00000000"))
    with pytest.raises(nt.StreamError, match="nflux_delz=0"):
        list(nt.calls(s))


def test_an_extension_record_outside_any_call_is_REFUSED():
    """This asserted the opposite until schema 3: a stray extension record was
    silently DROPPED, so a stream whose records had drifted out of their brackets
    looked complete. CAPIN had no completeness check to notice the loss, so the
    cap analysis would have been computed over whatever survived (owner P0-4).

    Not attributing it to a call was never enough -- discarding evidence quietly
    is the same failure as misfiling it."""
    stray = "G33F MSTEPI 1 1 i32 00000009\n"
    s = _hdr(1) + stray + _call(1) + "G33N STREAM_END\n"
    with pytest.raises(nt.StreamError, match="MSTEPI record outside any call"):
        nt.calls(s)


def test_a_stage_this_parser_does_not_READ_is_still_carried():
    """The property the tolerance was FOR: the stream legitimately carries
    stages this parser never consumes -- kernel_init_constants, the micro
    bisection -- and refusing those would reject valid decision streams.

    It used to be tested by putting one OUTSIDE the call bracket, which is a
    different proposition and the one that was wrong. Measured across the whole
    published archive: 55 streams, 6,265,378 records in this parser's
    namespace, 0 of them outside a bracket. So "unread stage" is tolerated
    here, inside the call, and "outside any call" is refused above
    (owner priority 1).
    """
    stray = "G33F STAGE 1 - kernel_init 0 rhoair0 1 0 f32 3F800000\n"
    s = _stream(_call(1).replace("G33F MSTEP 1 main 1", stray + "G33F MSTEP 1 main 1", 1))
    assert [c["call_id"] for c in nt.calls(s)] == [1]


def test_a_nonzero_driver_exit_is_rejected(tmp_path):
    """stdout is not evidence when the process that wrote it failed."""
    exe = tmp_path / "fail"
    exe.write_text("#!/bin/sh\necho 'G33N STREAM_BEGIN 1 1 1 1 legacy rezero'\nexit 3\n")
    exe.chmod(0o755)
    with pytest.raises(SystemExit, match="exited 3"):
        nt.main([str(exe), "1"])


# ---- schema 3: the extension protocol becomes fail-closed (owner §4) --------
#
# Each of these asserted nothing before schema 3, and every one of them is a way
# a malformed or incomplete stream reached an analysis that reported a number.

def _ext(cid=1, cols=(1,), ks=2, mstep=1, *, drop_capin=False, drop_topout=False,
         dup=None, bad_topout_k=None, nan_xfer=False, extra=""):
    """A call carrying the full extension universe, complete unless asked."""
    body = _call(cid, cols=cols, ks=ks, end=False).replace(
        "G33F MSTEP 1 main 1 i32 00000001",
        f"G33F MSTEP 1 main 1 i32 {mstep:08X}")
    out = [body.rstrip("\n")]
    for c in cols:
        for chain, ms in (("main", mstep), ("ice", 1)):
            for n in range(1, ms + 1):
                v = "7FC00000" if nan_xfer else "3F800000"
                out.append(f"G33F XFER 1 {n} {c} {chain} f32 {v} 40000000")
                if not drop_topout:
                    k = 0 if bad_topout_k is None else bad_topout_k
                    out.append(f"G33F TOPOUT 1 {n} {c} {k} {chain} f32 "
                               f"3F800000 40000000")
                if not drop_capin:
                    for k in range(1, ks):
                        out.append(f"G33F CAPIN 1 {n} {c} {k} {chain} f32 "
                                   f"3F800000 3F800000 40000000 40000000")
    if dup:
        out.append(dup)
    out.append(extra.rstrip("\n") if extra else "")
    out.append(f"G33N CALL_END {cid} {cid} 1")
    return "\n".join(x for x in out if x) + "\n"


_FEATS = "mstep,mstepi,nflux,xfer,capin,topout"


def test_the_full_extension_universe_parses(mstep=1):
    """The control: everything below must fail for its own reason, not because
    the helper builds an invalid stream."""
    assert len(nt.calls(_stream(_ext(), feats=_FEATS))) == 1


def test_a_declared_feature_with_ZERO_records_is_refused():
    """P0-1, and the most dangerous of the six: `capin` in the header with no
    CAPIN records passed, so the cap analysis it backs -- 39/255 interfaces,
    100.00% of the ice residual -- would have been computed over nothing."""
    with pytest.raises(nt.StreamError, match="capin.*covers"):
        nt.calls(_stream(_ext(drop_capin=True), feats=_FEATS))


def test_an_incomplete_capin_universe_is_refused():
    """A cap group missing one interface: the residual attribution silently loses
    that interface's contribution."""
    s = _stream(_ext(ks=3), feats=_FEATS)
    kept = [l for l in s.splitlines()
            # CAPIN is `G33F CAPIN loop n col k chain ...`, so k is field 5.
            if not (l.startswith("G33F CAPIN") and l.split()[5] == "2")]
    with pytest.raises(nt.StreamError, match="capin covers"):
        nt.calls("\n".join(kept) + "\n")


def test_a_TOPOUT_at_the_wrong_level_is_refused():
    """P0-6: completeness checked the sub-step set only, so a record at k=2 --
    or two at one sub-step and different levels -- passed. TOPOUT is the TOP
    cell's removal; its level is part of its identity, not decoration."""
    with pytest.raises(nt.StreamError, match="topout covers"):
        nt.calls(_stream(_ext(bad_topout_k=1), feats=_FEATS))


def test_a_duplicate_with_the_SAME_value_is_refused():
    """P0-2: `_put` raised only when the values DIFFERED, so a duplicated stream
    overwrote silently -- while its own docstring said a second write is a defect.
    The duplication is the defect; that the values agree is not a defence."""
    dup = "G33F XFER 1 1 1 main f32 3F800000 40000000"
    with pytest.raises(nt.StreamError, match="duplicate record"):
        nt.calls(_stream(_ext(dup=dup), feats=_FEATS))


def test_an_UNDECLARED_extension_record_is_refused():
    """P0-3: the contract said an undeclared feature is rejected; the parser read
    it anyway and merely skipped its universe check -- so the record entered the
    analysis with nothing verifying it was complete."""
    with pytest.raises(nt.StreamError, match="does not declare|declares features"):
        nt.calls(_stream(_ext(), feats="mstep,mstepi,nflux"))


def test_a_NaN_in_an_extension_record_is_refused():
    """P0-5: finite checks covered NFLUX and CAPIN only. A NaN XFER parsed, made
    the residual NaN, and reached a JSON writer that emits a bare `NaN` token --
    not even valid JSON, and it had passed every gate."""
    with pytest.raises(nt.StreamError, match="non-finite"):
        nt.calls(_stream(_ext(nan_xfer=True), feats=_FEATS))


def test_one_column_short_a_LEVEL_is_refused():
    """The level universe pooled all columns, so a short column passed whenever
    another supplied the level. The matched closure integrates exactly these
    per-column level sets, so this silently integrated over fewer cells and took
    the wrong cell as the bottom one."""
    s = _stream(_ext(cols=(1, 2), ks=2), feats=_FEATS)
    kept = [l for l in s.splitlines()
            if not (l.startswith("G33F STAGE") and l.split()[7] == "2"
                    and l.split()[8] == "1")]
    with pytest.raises(nt.StreamError, match="levels .* do not match"):
        nt.calls("\n".join(kept) + "\n")


def test_one_cell_short_a_FIELD_is_refused():
    """The rectangular universe: one field's gap must not be filled by another
    field's presence in the same cell set."""
    s = _stream(_ext(), feats=_FEATS)
    kept = [l for l in s.splitlines()
            if not (l.startswith("G33F STAGE") and "outer_pre_sed" in l
                    and l.split()[6] == "qr" and l.split()[8] == "1")]
    with pytest.raises(nt.StreamError, match="carries fields"):
        nt.calls("\n".join(kept) + "\n")


def test_a_stage_missing_a_field_the_closure_READS_is_refused():
    """Rectangularity alone would accept a stream with no `rho` at all, because
    every cell would agree about not having it."""
    s = _stream(_ext(), feats=_FEATS)
    kept = [l for l in s.splitlines()
            if not (l.startswith("G33F STAGE") and l.split()[6] == "rho")]
    with pytest.raises(nt.StreamError, match="carries no.*rho"):
        nt.calls("\n".join(kept) + "\n")


def test_mstep_below_one_is_refused():
    """`range(1, 0+1)` is empty, so mstep=0 made every extension universe
    vacuously satisfied. Now caught at PARSE, by the same bound that stops an
    absurd count allocating (owner P1-11.6) — earlier than the universe check,
    which is where it used to be found."""
    s = _stream(_ext(), feats=_FEATS).replace(
        "G33F MSTEP 1 main 1 i32 00000001", "G33F MSTEP 1 main 1 i32 00000000")
    with pytest.raises(nt.StreamError, match="outside 1\\.\\."):
        nt.calls(s)


def test_the_parser_refuses_the_schema_it_does_not_implement():
    with pytest.raises(nt.StreamError, match="declares schema 3"):
        nt.calls(_stream(_ext(), feats=_FEATS, schema=3))


def test_an_absurd_mstep_is_refused_before_it_allocates():
    """`FFFFFFFF` read as unsigned is 4.29e9, and the exact-universe check
    materialises set(range(1, mstep+1)) — memory exhaustion before any clean
    error. Decoded signed and bounded instead (owner P1-11.6)."""
    for bad in ("FFFFFFFF", "7FFFFFFF", "00000000"):
        s = _stream(_ext(), feats=_FEATS).replace(
            "G33F MSTEP 1 main 1 i32 00000001",
            f"G33F MSTEP 1 main 1 i32 {bad}")
        with pytest.raises(nt.StreamError, match="outside 1\\.\\.|not a sub-step"):
            nt.calls(s)


def test_a_legitimate_mstep_still_parses():
    """The bound must be generous enough that no real schedule reaches it."""
    s = _stream(_ext(mstep=3), feats=_FEATS)
    assert nt.calls(s)[0]["mstep"][(1, "main", 1)] == 3
    assert nt.MSTEP_MAX >= 1024


# --- the f64 record family (owner D6) --------------------------------------
#
# The G33F records used to write `'f32', transfer(<real>, 0)`. Under
# -fdefault-real-8 that took FOUR bytes of an EIGHT-byte value into an int32
# mold and labelled the result f32, so a reader parsed a valid-looking bit
# pattern that was not the number: pi came out `54442D18`, the low word of
# 400921FB54442D18, which reads as 3.3702806e+12.
#
# It was guarded at three layers instead of fixed, and the guards were why it
# stayed unfixed. What replaces them is an agreement, checked on every read,
# between a record's label, its hex width and the stream's PROTOCOL header.

#: The header a real f64 build writes: widths AND both IEEE triples.
_PROTO64 = "G33N PROTOCOL 8 8 2 53 1024 2 53 1024"
_PROTO32 = "G33N PROTOCOL 4 8 2 24 128 2 53 1024"

_F64_ONE = "3FF0000000000000"      # 1.0
_F32_ONE = "3F800000"


def _f64(text):
    """The f32 synthetic stream, widened -- header, labels and hex together."""
    out = []
    for line in text.splitlines():
        if line.startswith("G33N STREAM_BEGIN"):
            # AFTER the header, which is where the driver writes it.
            out += [line, _PROTO64]
            continue
        # 42C80000 (100.0) appears both as the CALL_BEGIN delt and as the
        # NFLUX dtcld payload -- both widen with the stream.
        line = (line.replace(" f32 ", " f64 ").replace(_F32_ONE, _F64_ONE)
                .replace("42C80000", "4059000000000000"))
        out.append(line)
    return "\n".join(out) + "\n"


def test_an_f64_STREAM_parses_to_the_SAME_numbers():
    """The family is a width change, not a meaning change."""
    s32 = _stream(_call(1))
    got32, got64 = nt.calls(s32), nt.calls(_f64(s32))
    assert len(got32) == len(got64) == 1
    assert got32[0]["delt"] == got64[0]["delt"] == 100.0
    assert got32[0]["outer_pre_sed"] == got64[0]["outer_pre_sed"]


def test_an_f64_LABEL_on_an_f32_WIDTH_is_refused():
    """The exact shape of the original defect: a label that does not describe
    the bytes beside it."""
    bad = _f64(_stream(_call(1))).replace(f"f64 {_F64_ONE}", f"f64 {_F32_ONE}", 1)
    with pytest.raises(nt.StreamError, match="hex digits"):
        nt.calls(bad)


def test_an_f32_LABEL_on_an_f64_WIDTH_is_refused():
    bad = _stream(_call(1)).replace(f"f32 {_F32_ONE}", f"f32 {_F64_ONE}", 1)
    with pytest.raises(nt.StreamError, match="hex digits"):
        nt.calls(bad)


def test_a_RECORD_that_disagrees_with_the_HEADER_is_refused():
    """The header is written from `storage_size`, so it is what the compiler
    did. A record claiming otherwise means the overlay and the compile were
    given different widths -- which is the wrong-number path itself."""
    # An otherwise well-formed f64 stream with ONE record left at f32: its
    # label and its width agree with each other and with nothing else.
    one = _f64(_stream(_call(1))).replace(f"f64 {_F64_ONE}", f"f32 {_F32_ONE}", 1)
    with pytest.raises(nt.StreamError, match="header declares"):
        nt.calls(one)
    # ...and the unlabelled `delt`, whose width is the header's word alone.
    s = _stream(_call(1))
    with pytest.raises(nt.StreamError, match="hex digits"):
        nt.calls(s.replace("\n", "\n" + _PROTO64 + "\n", 1))


def test_a_stream_with_NO_protocol_header_reads_as_f32():
    """Every archived stream predates the header, and every one of them was an
    f32 build. The default is the answer for them, not a guess."""
    s = _stream(_call(1))
    assert "PROTOCOL" not in s
    assert nt.calls(s)[0]["delt"] == 100.0


def test_a_stream_whose_DOUBLES_were_promoted_to_16_bytes_is_refused():
    """-fdefault-real-8 without -fdefault-double-8 makes `double precision`
    REAL(16), and the schema-f64 fields stop being readable at all. The build
    script passes both; this refuses a stream built by something that did not."""
    with pytest.raises(nt.StreamError, match="16-byte doubles|byte doubles"):
        nt.calls(_f64(_stream(_call(1))).replace(
            "PROTOCOL 8 8 2 53 1024", "PROTOCOL 8 16 2 53 1024"))


# --- the header is a STREAM-WIDE contract (owner priority 2) -----------------
#
# The width was read into a variable the record loop reassigned, so a second
# PROTOCOL simply took effect from where it appeared. A run whose first calls
# were f32 and whose later ones were f64 then read as one consistent stream --
# which is exactly the agreement between label, width and header that the D6
# family was supposed to establish, defeated by making the header mutable.


def test_a_SECOND_protocol_header_is_refused():
    s = _f64(_stream(_call(1)))
    with pytest.raises(nt.StreamError, match="two G33N PROTOCOL headers"):
        nt.calls(s.replace(_PROTO64,
                           _PROTO64 + '\n' + _PROTO64))


def test_a_MIXED_WIDTH_stream_is_refused_at_its_second_header():
    """The failure this closes, spelled out: calls 1..k at one width, a fresh
    header, calls k+1.. at another. Every record agrees with the header in
    force when it was read, and the stream is still not one run."""
    s = _stream(_call(1), _call(2))
    mixed = s.replace("G33N CALL_BEGIN 2", _PROTO64 + "\nG33N CALL_BEGIN 2")
    with pytest.raises(nt.StreamError, match="PROTOCOL header after the stream"):
        nt.calls(mixed)


def test_a_LATE_protocol_header_is_refused():
    """After the body began it would be retroactive: the records before it were
    already decoded at the default width."""
    s = _stream(_call(1))
    with pytest.raises(nt.StreamError, match="PROTOCOL header after the stream"):
        nt.calls(s.replace("G33F MSTEP 1 main 1",
                           _PROTO64 + "\nG33F MSTEP 1 main 1"))


def test_a_protocol_header_after_STREAM_END_is_refused():
    s = _stream(_call(1))
    with pytest.raises(nt.StreamError, match="PROTOCOL header after the stream"):
        nt.calls(s.replace("G33N STREAM_END",
                           "G33N STREAM_END\n" + _PROTO64))


def test_the_header_may_still_sit_on_either_side_of_STREAM_BEGIN():
    """The driver writes it after; nothing in the format requires that, and the
    position check is about the BODY, not about which header line comes first."""
    s = _f64(_stream(_call(1)))
    before = s.replace(_PROTO64 + '\n', "")
    before = _PROTO64 + '\n' + before
    assert nt.calls(before)[0]["delt"] == nt.calls(s)[0]["delt"] == 100.0


# --- records this parser CHECKS without consuming (owner priority 3) ---------
#
# `KNOWN_G33F` accepted a family name and never looked at the rest of the line,
# so the whole G33FOP op ladder and every unconsumed STAGE went through the
# number analyses unread. An eight-byte default real written through the
# schema's `Z8.8` overflows to `********` in gfortran, which matched nothing,
# matched no pattern, and was dropped in silence -- the D6 wrong-number path
# surviving in the family D6 did not reach.

_OP = ("G33FOP 1 main 1 1 0 QR_FALK mul_dend_q f32 3F800000\n"
       "G33FOP 1 main 1 1 0 QR_FALK mul_work1 f64 3FF0000000000000\n"
       "G33FOP 1 main 1 1 0 QR_FALK shadow_falk_f32 f32 3F800000\n")


def _with_ops(text, ops=_OP):
    return text.replace("G33F MSTEP 1 main 1", ops + "G33F MSTEP 1 main 1", 1)


def test_a_well_formed_op_ladder_rides_along_untouched():
    """It is CHECKED, not consumed: the numbers the analyses produce are the
    same with and without it."""
    plain, withops = _stream(_call(1)), _with_ops(_stream(_call(1)))
    assert nt.calls(plain)[0]["outer_pre_sed"] == \
        nt.calls(withops)[0]["outer_pre_sed"]


def test_an_OVERFLOWED_op_record_is_refused_instead_of_dropped():
    """What `Z8.8` does to an eight-byte value. It used to match no pattern,
    reach the family check, and be skipped -- so the wrong-number path showed up
    as a stream that simply had fewer records than the run emitted."""
    bad = _with_ops(_stream(_call(1)),
                    "G33FOP 1 main 1 1 0 QR_FALK mul_dend_q f32 ********\n")
    with pytest.raises(nt.StreamError, match="malformed G33FOP"):
        nt.calls(bad)


def test_an_op_record_whose_LABEL_and_WIDTH_disagree_is_refused():
    bad = _with_ops(_stream(_call(1)),
                    "G33FOP 1 main 1 1 0 QR_FALK mul_dend_q f32 "
                    "3FF0000000000000\n")
    with pytest.raises(nt.StreamError, match="carries 16 hex digits"):
        nt.calls(bad)


def test_one_op_field_may_not_change_WIDTH_within_a_stream():
    """A width is a property of the build, so it is constant over the run. This
    is the check a header cannot make: a field pinned at `real(...,4)` is
    legitimately narrower than the default real, so "agrees with the header" is
    not the contract -- "never moves" is."""
    bad = _with_ops(_stream(_call(1)),
                    "G33FOP 1 main 1 1 0 QR_FALK mul_dend_q f32 3F800000\n"
                    "G33FOP 1 main 2 1 0 QR_FALK mul_dend_q f64 "
                    "3FF0000000000000\n")
    with pytest.raises(nt.StreamError, match="mid-run"):
        nt.calls(bad)


def test_an_UNCONSUMED_stage_is_checked_too():
    """`kernel_init_constants` and the micro bisection are carried by the same
    stdout and read by nobody here. They are records the run emitted."""
    bad = _with_ops(_stream(_call(1)),
                    "G33F STAGE 1 - kernel_init_constants 0 pi 1 -1 f32 "
                    "40490FDB40490FDB\n")
    with pytest.raises(nt.StreamError, match="carries 16 hex digits"):
        nt.calls(bad)


def test_a_PINNED_narrow_field_beside_a_wide_one_is_accepted_at_f64():
    """The case a blanket promotion gets wrong. In an f64 build `mul_dend_q` is
    a default real and widens; `shadow_falk_f32` is an explicit `real(...,4)`
    and does not. Both are schema-f32, so only the storage class separates
    them -- and the stream is well-formed with the two side by side."""
    ops = ("G33FOP 1 main 1 1 0 QR_FALK mul_dend_q f64 3FF0000000000000\n"
           "G33FOP 1 main 1 1 0 QR_FALK shadow_falk_f32 f32 3F800000\n")
    got = nt.calls(_with_ops(_f64(_stream(_call(1))), ops))
    assert len(got) == 1


# --- the namespace is CLOSED, and it closes at the bracket (owner priority 1) -
#
# The unknown-family refusals lived AFTER `if cur is None: continue`, so they
# only ever saw records inside a call. Measured on a real f64 stream: an
# unknown G33N between two calls, an unknown G33F before the first, a
# well-formed G33FOP after STREAM_END -- four mutations, four silent
# acceptances, the parsed call count unchanged at 12. That is the `********`
# defect again: a record the parser cannot place became a record that was never
# there.

@pytest.mark.parametrize("what,mutate", [
    ("unknown G33N between calls",
     lambda t: t.replace("G33N CALL_BEGIN", "G33N FUTURE_FAMILY 1 2\nG33N CALL_BEGIN", 1)),
    ("unknown G33F between calls",
     lambda t: t.replace("G33N CALL_BEGIN", "G33F NOSUCHFAMILY 1 2\nG33N CALL_BEGIN", 1)),
    ("a WELL-FORMED op record outside any call",
     lambda t: t.replace("G33N STREAM_END",
                         "G33FOP 1 main 1 1 0 QR_FALK mul_dend_q f32 3F800000\n"
                         "G33N STREAM_END", 1)),
    ("a WELL-FORMED stage record outside any call",
     lambda t: t.replace("G33N STREAM_END",
                         "G33F STAGE 1 - kernel_init_constants 0 pi 1 -1 f32 40490FDB\n"
                         "G33N STREAM_END", 1)),
    ("anything at all after STREAM_END",
     lambda t: t.replace("G33N STREAM_END", "G33N STREAM_END\nG33F NOSUCH 9 9", 1)),
])
def test_a_record_this_parser_cannot_PLACE_is_refused(what, mutate):
    with pytest.raises(nt.StreamError, match="outside any call|after STREAM_END"):
        nt.calls(mutate(_stream(_call(1))))


def test_ANOTHER_protocols_records_in_the_same_stdout_are_left_alone():
    """What keeps the world closed rather than merely small: a driver writes
    G33R and G33P into the same stdout, and those are not this parser's to
    place. Only the G33N/G33F namespace is closed."""
    s = _stream(_call(1)).replace(
        "G33N CALL_BEGIN",
        "G33P INITIAL qv 1 0 3F800000\nG33R STATE 1 1 1 th 3F800000\nG33N CALL_BEGIN", 1)
    assert len(nt.calls(s)) == 1


# --- a payload is a VALUE, not a digit count (owner priority 2) --------------

@pytest.mark.parametrize("what,record", [
    ("op f64 NaN",   "G33FOP 1 main 1 1 0 QR_FALK mul_work1 f64 7FF8000000000000"),
    ("op f64 +Inf",  "G33FOP 1 main 1 1 0 QR_FALK mul_work1 f64 7FF0000000000000"),
    ("op f32 NaN",   "G33FOP 1 main 1 1 0 QR_FALK mul_dend_q f32 7FC00000"),
    ("op u8 = FF",   "G33FOP 1 main 1 1 0 QR_OUTFLOW cap_active u8 FF"),
    ("op u8 = 02",   "G33FOP 1 main 1 1 0 QR_OUTFLOW cap_active u8 02"),
    ("stage f32 -Inf",
     "G33F STAGE 1 - micro_post_melt 0 qq 1 0 f32 FF800000"),
])
def test_a_checked_only_payload_must_be_a_NUMBER_the_emitter_could_write(what, record):
    """Width and label agreement says the bytes are the size they claim, not
    that they are a number. The consumed records have had this since a NaN XFER
    reached a JSON writer that emits a bare `NaN` token; the op ladder got the
    width half and not the value half."""
    bad = _with_ops(_stream(_call(1)), record + "\n")
    with pytest.raises(nt.StreamError, match="payload"):
        nt.calls(bad)


def test_the_LEGAL_boolean_values_still_pass():
    """`merge(1, 0, <logical>)` through Z2.2 is exactly these two."""
    for h in ("00", "01"):
        s = _with_ops(_stream(_call(1)),
                      f"G33FOP 1 main 1 1 0 QR_OUTFLOW cap_active u8 {h}\n")
        assert len(nt.calls(s)) == 1


def test_EVERY_label_the_parser_admits_has_a_DECODER():
    """The completeness rule on the third vocabulary. A label added to
    HEX_WIDTH without a decoder would raise KeyError deep inside a parse
    instead of being refused as an unknown label."""
    assert set(nt.HEX_WIDTH) == set(nt._DECODE), \
        sorted(set(nt.HEX_WIDTH) ^ set(nt._DECODE))


# --- the header says the FORMAT, not only the width (owner priority 7) -------
#
# `_real` unpacks with `>f`/`>d`, which is IEEE binary32/binary64. A storage
# size of four bytes does not make a Fortran real one of those -- the standard
# does not say so -- and the header declared only the size. So the reader's
# strongest assumption was the one thing the stream never stated.

@pytest.mark.parametrize("what,header", [
    ("the old two-field shape", "G33N PROTOCOL 8 8"),
    ("widths and one triple", "G33N PROTOCOL 8 8 2 53 1024"),
    ("a trailing field", "G33N PROTOCOL 8 8 2 53 1024 2 53 1024 0"),
])
def test_a_HALF_STATED_protocol_header_is_refused(what, header):
    """Worse than none: none is read under a documented default, half is read
    as agreement."""
    s = _f64(_stream(_call(1))).replace(_PROTO64, header)
    with pytest.raises(nt.StreamError, match="malformed G33N PROTOCOL"):
        nt.calls(s)


@pytest.mark.parametrize("what,triple", [
    ("a decimal radix", "10 53 1024"),
    ("binary32 digits on an 8-byte real", "2 24 1024"),
    ("a truncated exponent range", "2 53 308"),
])
def test_a_NON_IEEE_real_model_is_refused(what, triple):
    s = _f64(_stream(_call(1))).replace(
        _PROTO64, f"G33N PROTOCOL 8 8 {triple} 2 53 1024")
    with pytest.raises(nt.StreamError, match="radix, digits, maxexponent"):
        nt.calls(s)


def test_the_DOUBLE_model_is_checked_too():
    """`double precision` is what the schema-f64 fields are, and it is decoded
    with the same assumption."""
    s = _f64(_stream(_call(1))).replace(
        _PROTO64, "G33N PROTOCOL 8 8 2 53 1024 10 53 1024")
    with pytest.raises(nt.StreamError, match="radix, digits, maxexponent"):
        nt.calls(s)


def test_an_f32_build_states_its_own_format():
    """The f32 side of the same header, so the check is not f64-only."""
    s = _stream(_call(1)).replace("G33N STREAM_BEGIN",
                                  _PROTO32 + "\nG33N STREAM_BEGIN", 1)
    assert nt.calls(s)[0]["delt"] == 100.0
    bad = s.replace(_PROTO32, "G33N PROTOCOL 4 8 2 53 128 2 53 1024")
    with pytest.raises(nt.StreamError, match="radix, digits, maxexponent"):
        nt.calls(bad)


def test_a_stream_with_NO_header_is_still_read_under_the_documented_default():
    """Every archived stream predates the header entirely, and the default is
    the answer for them rather than a guess -- unchanged by this."""
    s = _stream(_call(1))
    assert "PROTOCOL" not in s
    assert nt.calls(s)[0]["delt"] == 100.0


# --- coverage anchored at column 1, congruent across splits (review §7) ------
#
# The check took the first tile's own start as origin, so a split covering 2..3
# -- column 1 missing entirely -- was contiguous from where it happened to
# begin, and passed. Measured. The real driver refuses these before emitting,
# but this parser judges arbitrary artifacts and may not re-assume that.


def test_a_split_whose_tiles_start_past_COLUMN_1_is_refused():
    s = _stream(_call(1, cols=(2,), split=1, tile=1), nsplit=1, ntile=1)
    with pytest.raises(nt.StreamError, match="domain stands at column 1"):
        nt.calls(s)


def test_two_splits_covering_DIFFERENT_domains_are_refused():
    s = _stream(_call(1, cols=(1,), split=1, tile=1),
                _call(2, cols=(1,), split=2, tile=1),
                _call(3, cols=(2,), split=2, tile=2),
                nsplit=2, ntile=1)
    # nsplit/ntile bookkeeping: build by hand -- split 1 covers 1..1, split 2
    # covers 1..2, headers consistent.
    s = (_hdr(nsplit=1, ntile=3, schema=4).replace(" 3 ", " 3 ", 1))
    s = ("G33N STREAM_BEGIN 4 2 2 4 legacy rezero mstep,mstepi,nflux as-is\n"
         + _call(1, cols=(1,), split=1, tile=1)
         + _call(2, cols=(2,), split=1, tile=2)
         + _call(3, cols=(1,), split=2, tile=1)
         + _call(4, cols=(2, 3), split=2, tile=2)
         + "G33N STREAM_END\n")
    with pytest.raises(nt.StreamError, match="decompose the domain differently"):
        nt.calls(s)


# --- ONE identity reader, the strict one (review §6) -------------------------


def test_validated_run_identity_is_the_strict_parse_plus_the_header():
    got = nt.validated_run_identity(_stream(_call(1)))
    assert got == {"nsplit": 1, "carry": "rezero", "rho": "as-is",
                   "width": 1, "levels": 2, "ntile": 1,
                   "tile_ranges": ((1, 1),), "tile_sizes": (1,),
                   "algorithm": "legacy", "real_bytes": 4,
                   # A stream that declares no metric still HAS one: the
                   # registry resolves it from the arm, so the identity is
                   # complete for historical streams too (owner review 4.3).
                   "number_transfer_metric": "thickness",
                   "delt": 100.0, "dtcld": 100.0,
                   "loops": 1}


def test_validated_run_identity_REFUSES_what_calls_refuses():
    """The property the private regex lost: a stream the strict parser refuses
    has no run identity to report."""
    bad = ("G33N STREAM_BEGIN 4 12 1 12 legacy rezero mstep as-is\n"
           "G33N CALL_BEGIN 1 1 1 1 3 4 42C80000\n"
           "G33N STREAM_BEGIN 4 12 1 12 legacy rezero mstep as-is\n")
    with pytest.raises(nt.StreamError):
        nt.validated_run_identity(bad)


def test_validated_run_identity_pins_the_EXPECTED_width():
    s = _stream(_call(1))
    with pytest.raises(nt.StreamError, match="expected the fixture"):
        nt.validated_run_identity(s, expected_width=3)


# --- an empty call is not a processed tile (owner review §5) -----------------
#
# Every completeness rule iterates `call["loops"]`, so an empty set ran every
# check zero times and CALL_BEGIN + CALL_END with nothing between counted as
# complete -- its declared columns covered by nothing while the tile-span check
# summed the declaration. Measured. The recurring defect class: measuring
# nothing, certified as complete.


def test_an_EMPTY_call_is_refused():
    s = ("G33N STREAM_BEGIN 4 1 2 2 legacy rezero mstep,mstepi,nflux as-is\n"
         "G33N CALL_BEGIN 1 1 1 1 1 2 42C80000\nG33N CALL_END 1 1 1\n"
         + _call(2, cols=(2,), split=1, tile=2) + "G33N STREAM_END\n")
    with pytest.raises(nt.StreamError, match="carries no records at all"):
        nt.calls(s)


@pytest.mark.parametrize("what,begin,expect", [
    ("K = 0", "G33N CALL_BEGIN 1 1 1 1 1 0 42C80000", "not a level count"),
    ("inverted columns", "G33N CALL_BEGIN 1 1 1 3 1 2 42C80000",
     "non-empty 1-based"),
    ("column 0", "G33N CALL_BEGIN 1 1 1 0 1 2 42C80000", "non-empty 1-based"),
    ("NaN delt", "G33N CALL_BEGIN 1 1 1 1 1 2 7FC00000", "positive finite"),
    ("zero delt", "G33N CALL_BEGIN 1 1 1 1 1 2 00000000", "positive finite"),
])
def test_call_GEOMETRY_is_checked_where_it_is_declared(what, begin, expect):
    """Each of these was individually masked by later checks on well-formed
    streams and unchecked on degenerate ones."""
    s = ("G33N STREAM_BEGIN 4 1 1 1 legacy rezero mstep,mstepi,nflux as-is\n"
         + begin + "\nG33N CALL_END 1 1 1\nG33N STREAM_END\n")
    with pytest.raises(nt.StreamError, match=expect):
        nt.calls(s)


# --- the cid equation is not a range check (owner review §6) -----------------


def test_split_and_tile_must_be_IN_RANGE_not_merely_consistent():
    """Under ntile=2, split=0/tile=3 gives cid 1 and split=1/tile=2 gives cid
    2 -- the equation satisfied, the decomposition outside the domain the
    header declares. Measured passing."""
    s = ("G33N STREAM_BEGIN 4 1 2 2 legacy rezero mstep,mstepi,nflux as-is\n"
         + _call(1, cols=(1,), split=0, tile=3)
         + _call(2, cols=(2,), split=1, tile=2) + "G33N STREAM_END\n")
    with pytest.raises(nt.StreamError, match="outside 1"):
        nt.calls(s)


def test_one_stream_declares_ONE_K_and_ONE_delt():
    """The ranges plus the cid equation force the (split, tile) universe; K
    and delt were tied to nothing, so one call could describe a different
    vertical grid or step than its neighbours and each validated alone."""
    good = _stream(_call(1), _call(2))
    bad = good.replace("G33N CALL_BEGIN 2 2 1 1 1 2 42C80000",
                       "G33N CALL_BEGIN 2 2 1 1 1 2 42C90000")
    assert bad != good
    with pytest.raises(nt.StreamError, match="different timesteps"):
        nt.calls(bad)


def test_validated_run_identity_pins_the_EXPECTED_levels():
    with pytest.raises(nt.StreamError, match="expected the fixture's 4"):
        nt.validated_run_identity(_stream(_call(1)), expected_levels=4)


# --- one decomposition per stream, in tile-ID order (owner review §5) --------
#
# Coverage was checked with segments sorted by COLUMN RANGE and compared across
# splits only by the last column, so two shapes passed that are not one
# decomposition: a stream whose splits tile the domain differently, and a
# stream whose tile IDs are spatially permuted. `ncmin` is set by a tile's
# LAST column, so both change what the kernel computed. Measured before fixed.


def test_splits_running_DIFFERENT_tile_vectors_are_refused():
    s = _stream(_call(1, cols=(1,), split=1, tile=1),
                _call(2, cols=(2, 3), split=1, tile=2),
                _call(3, cols=(1, 2), split=2, tile=1),
                _call(4, cols=(3,), split=2, tile=2),
                nsplit=2, ntile=2)
    with pytest.raises(nt.StreamError, match="decompose the domain differently"):
        nt.calls(s)


def test_spatially_PERMUTED_tile_ids_are_refused():
    s = _stream(_call(1, cols=(2, 3), split=1, tile=1),
                _call(2, cols=(1,), split=1, tile=2),
                _call(3, cols=(2, 3), split=2, tile=1),
                _call(4, cols=(1,), split=2, tile=2),
                nsplit=2, ntile=2)
    with pytest.raises(nt.StreamError, match="in tile-ID order"):
        nt.calls(s)


def test_the_run_identity_carries_the_decomposition():
    s = _stream(_call(1, cols=(1,), split=1, tile=1),
                _call(2, cols=(2, 3), split=1, tile=2),
                _call(3, cols=(1,), split=2, tile=1),
                _call(4, cols=(2, 3), split=2, tile=2),
                nsplit=2, ntile=2)
    rid = nt.validated_run_identity(s)
    assert rid["ntile"] == 2
    assert rid["tile_ranges"] == ((1, 1), (2, 3))
    assert rid["tile_sizes"] == (1, 2)


def test_NFLUX_records_declaring_two_subcycle_steps_are_refused():
    """dtcld is a scalar of the run, recorded once per column in every NFLUX
    group -- two values is two runs' records in one stream (owner review §6)."""
    s = _stream(_call(1, cols=(1, 2)))
    s = s.replace("G33F NFLUX 1 2 nflux_dtcld f32 42C80000",
                  "G33F NFLUX 1 2 nflux_dtcld f32 40000000")
    with pytest.raises(nt.StreamError, match="different sub-cycle steps"):
        nt.calls(s)


# --- the loop universe is exact 1..L, one L per stream (owner review §4 r6) --


def test_records_living_only_on_loop_2_are_refused():
    """The per-loop checks walked the loops a call HAPPENS to carry, so a
    call whose records all sit on loop 2 -- loop 1 entirely absent -- was
    complete for every loop anyone looked at. Measured."""
    with pytest.raises(nt.StreamError, match="not exactly 1..1"):
        nt.calls(_stream(_call(1, loop=2)))


def test_calls_running_DISJOINT_loop_sets_are_refused():
    s = _stream(_call(1, loop=1), _call(2, loop=2))
    with pytest.raises(nt.StreamError, match="different inner-loop sets"):
        nt.calls(s)


def test_the_run_identity_carries_the_loop_count():
    assert nt.validated_run_identity(_stream(_call(1)))["loops"] == 1


# --- duplicate facts inside one stream are compared (owner review §9.1) ------


def test_nflux_den_delz_must_restate_the_bottom_cell():
    """The NFLUX group restates the bottom cell's rho/delz, recorded
    independently in outer_pre_sed at k = K-1. Measured across 4827
    published flux groups: exactly equal, every one."""
    s = _stream(_call(1)).replace("G33F NFLUX 1 1 nflux_den f32 3F800000",
                                  "G33F NFLUX 1 1 nflux_den f32 40000000")
    with pytest.raises(nt.StreamError, match="one run records one atmosphere"):
        nt.calls(s)


def test_the_subcycle_step_must_derive_from_the_external_step():
    """dtcld x loops == delt at the f32 word -- the kernel's own rule,
    restated in every NFLUX group and never compared to the CALL_BEGIN delt
    it derives from."""
    s = _stream(_call(1)).replace("G33F NFLUX 1 1 nflux_dtcld f32 42C80000",
                                  "G33F NFLUX 1 1 nflux_dtcld f32 40000000")
    with pytest.raises(nt.StreamError, match="not this stream's"):
        nt.calls(s)


def test_a_missing_surface_row_is_refused_not_skipped():
    """A surface cell that is not there used to come back as None -- a
    surface-dependent row silently dropped (owner review §9.2). Measured:
    all 8945 published loops carry exactly cols x {k=-1}."""
    s = _stream(_call(1, cols=(1, 2)))
    for sf in sorted(nt.SURFACE_REQUIRED):        # column 2 loses the stage
        s = s.replace(f"G33F STAGE 1 - surface 0 {sf} 2 -1 f32 3F800000\n", "")
    with pytest.raises(nt.StreamError, match="cannot be skipped"):
        nt.calls(s)


def test_the_dtcld_relation_holds_at_the_STREAMS_width():
    """Packing an f64 stream's dtcld x loops and delt to f32 dropped 29
    bits, so two distinct f64 facts sharing an f32 word compared equal
    (Codex). The relation now checks at the stream's own default-real
    width: a sub-f32 perturbation on an f64 stream refuses."""
    import struct
    s = _f64(_stream(_call(1)))
    bad = struct.pack(">d", 100.0 * (1 + 1e-12)).hex().upper()
    s2 = s.replace("nflux_dtcld f64 4059000000000000", f"nflux_dtcld f64 {bad}")
    assert s2 != s
    with pytest.raises(nt.StreamError, match="not this stream's"):
        nt.calls(s2)
    nt.calls(s)                         # the consistent stream still parses


def test_a_VALID_subcycle_whose_quotient_does_not_invert_still_parses():
    """The kernel rounds delt/L to the build's width; re-multiplying does
    NOT recover delt for ~9% of (delt, L) pairs at f64, so a product rule
    refused valid streams (Codex). The check now recomputes the kernel's
    own operation: dtcld must equal the correctly-rounded quotient.

    The pair is KERNEL-CONSISTENT (Codex, next round): the kernel picks
    L = max(nint(delt/dtcldcr), 1) with dtcldcr = 120 (F:930), so
    delt = 384.007... gives nint(3.2) = 3 loops -- a stream the kernel can
    actually emit, unlike an arbitrary (delt, L) the parser would judge but
    no run would produce."""
    import math
    import struct
    delt = float.fromhex("0x1.8001d7dbf7f69p+8")     # 384.00720000079906
    assert max(math.floor(delt / 120 + 0.5), 1) == 3, \
        "the pair no longer matches the kernel's own loop rule"
    q = struct.unpack(">d", struct.pack(">d", delt / 3))[0]
    assert struct.pack(">d", q * 3) != struct.pack(">d", delt), \
        "the chosen pair no longer demonstrates the non-inverting case"
    dh = struct.pack(">d", delt).hex().upper()
    qh = struct.pack(">d", q).hex().upper()
    parts = [_call(1, loop=l) for l in range(1, 4)]
    merged = parts[0].rstrip().rsplit("G33N CALL_END", 1)[0]
    for pt in parts[1:]:
        merged += pt.split("42C80000\n", 1)[1].rsplit("G33N CALL_END", 1)[0]
    merged += "G33N CALL_END 1 1 1\n"
    s = _f64("G33N STREAM_BEGIN 4 1 1 1 legacy rezero mstep,mstepi,nflux "
             "as-is\n" + merged + "G33N STREAM_END\n")
    s = s.replace("4059000000000000", dh)
    s = s.replace(f"nflux_dtcld f64 {dh}", f"nflux_dtcld f64 {qh}")
    assert sorted(nt.calls(s)[0]["loops"]) == [1, 2, 3]


def test_the_surface_VOCABULARY_is_the_emitters_own():
    """Two records of one fact: the parser states the surface stage's field
    set, the overlay generator emits it. Compared here rather than imported,
    so the reader does not depend on the writer -- and so a field added on
    one side without the other fails loudly (owner review §7)."""
    import sys as _s
    _s.path.insert(0, str(ROOT / "g33_fortran"))
    import g33_fortran_bindings as fb
    assert set(nt.SURFACE_REQUIRED) == {f for f, _dt, _e in fb.SURFACE_FIELDS}


def test_a_surface_row_missing_the_quantity_an_analysis_reads_is_refused():
    """A row that is PRESENT but carries something no analysis reads passed
    the universe check while a surface closure got None and dropped it."""
    s = _stream(_call(1))
    s = s.replace("G33F STAGE 1 - surface 0 bottom_fall_qr 1 -1 f32 3F800000\n",
                  "")
    with pytest.raises(nt.StreamError, match="is a silent skip"):
        nt.calls(s)


# ---- the residual as an IDENTITY, not a measurement ------------------------

def _live_streams():
    """Every published density arm on this host, or nothing."""
    from pathlib import Path
    return sorted(Path.home().glob(
        "kdm6ad-g33m-migrate/number-009-ice.bundles/*/n12.rezero*.txt"))


@pytest.mark.skipif(not _live_streams(), reason="no number bundle on this host")
@pytest.mark.parametrize("species", ["nr", "ni"])
def test_the_closed_form_REPRODUCES_the_measured_residual(species):
    """`sum [den(lower) - den(upper)] * delz(upper) * b` is the residual.

    The module header has stated this since the defect was found, beside a
    measurement, which left the claim resting on the size of an observed
    number. Evaluated from the same recovered transfers it is an identity:
    measured across six density arms and two species, every ratio
    1.000000000000, and both sides exactly zero under a uniform profile.

    That is what carries the defect from "this run leaks number" to "the
    source equation leaks number" -- and it needs no change to the frozen
    kernel to say so.
    """
    seen = 0
    for stream in _live_streams():
        for call in nt.calls(stream.read_text()):
            loop = nt.single_loop(call)
            if not isinstance(loop, int):
                continue
            for col in sorted({c for l, c, _k in call["outer_pre_sed"]
                               if l == loop}):
                out = nt.column(call, col, species)
                if out is None:
                    continue
                seen += 1
                ratio = out["predicted_over_measured"]
                if ratio is None:
                    # A uniform profile drives both sides to ROUNDOFF, not to
                    # a clean zero: -0.0 against 0.0, relative residual 5e-17.
                    scale = out["start"] or 1.0
                    assert abs(out["residual"]) < 1e-12 * scale, (stream.name, col)
                    assert abs(out["predicted_residual"]) < 1e-12 * scale, \
                        (stream.name, col)
                    continue
                assert abs(ratio - 1.0) < 1e-9, (stream.name, col, ratio, out)
    assert seen > 10, seen


@pytest.mark.skipif(not _live_streams(), reason="no number bundle on this host")
def test_the_identity_is_not_vacuous():
    """A predicted value that merely echoed the measured one would pass the
    test above and prove nothing. The arms disagree with each other in sign
    and magnitude exactly as the closed form says they must -- inverted
    density reverses it, doubled contrast roughly doubles it."""
    total = {}
    for stream in _live_streams():
        got = 0.0
        for call in nt.calls(stream.read_text()):
            loop = nt.single_loop(call)
            if not isinstance(loop, int):
                continue
            for col in sorted({c for l, c, _k in call["outer_pre_sed"]
                               if l == loop}):
                out = nt.column(call, col, "nr")
                if out is not None:
                    got += out["predicted_residual"]
        total[stream.name] = got
    base = total.get("n12.rezero.txt")
    assert base and base > 0, total
    if "n12.rezero.uniform.txt" in total:
        assert abs(total["n12.rezero.uniform.txt"]) < 1e-6 * base, total
    if "n12.rezero.inverted.txt" in total:
        assert total["n12.rezero.inverted.txt"] < 0, total
    if "n12.rezero.x2.txt" in total:
        assert 1.7 < total["n12.rezero.x2.txt"] / base < 2.3, total


# ---------------------------------------------------------------------------
# The transport-only closure at mstep > 1.
#
# `closure()` never needed the sub-step count, which is the whole point of the
# path. Its GUARD did: the surface-cap test went through `column()`, so the
# reader that advertises "no recursion" was silently mstep == 1 only, and the
# archive carried no number-closure figure above it at all.

def _guard_call(*, capin, flux, mstep=1, chain="main"):
    """The minimum a guard needs: CAPIN rows, the emitted accumulator, mstep."""
    return {"capin": capin, "flux": flux, "surface": {},
            "mstep": {(1, chain, 1): mstep}, "loops": {1},
            "outer_pre_sed": {(1, 1, 0): {}}}


def _guard_capin(rows, col=1, chain="main"):
    """rows: {k: (own_q, in_q, own_n, in_n)} for one sub-step."""
    return {(1, 1, col, chain, k): v for k, v in rows.items()}


def test_the_surface_cap_is_answered_without_recovering_a_transfer():
    """CAPIN's bottom cell IS what left, so the question needs no sub-step count."""
    call = _guard_call(capin=_guard_capin({1: (1.0, 1.0, 5.0, 5.0), 2: (2.0, 2.0, 7.0, 7.0)}),
                 flux={(1, 1): {"bottom_falln_nr": 7.0, "nflux_dtcld": 1.0}},
                 mstep=9)
    assert nt.surface_cap_binds(call, 1, "nr") is False
    call["flux"][(1, 1)]["bottom_falln_nr"] = 9.0        # accumulator overstates
    assert nt.surface_cap_binds(call, 1, "nr") is True


def test_a_guard_that_cannot_see_does_not_answer_no():
    """No CAPIN records -> None, never False. An unbuilt overlay is not a pass."""
    call = _guard_call(capin={}, flux={(1, 1): {"bottom_falln_nr": 7.0,
                                          "nflux_dtcld": 1.0}})
    assert nt.surface_cap_binds(call, 1, "nr") is None
    assert nt.interior_cap_binds(call, 1, "nr") is None


def test_an_interior_cap_is_LABELLED_not_excluded():
    """Different question from the surface one, and conflating them cost rows.

    Where an interior cap binds the residual is still what the operator did --
    the capped transfer is the one that ran -- so it is reported, while the
    surface test stays the exclusion, because that one is about whether `out`
    is the removal that happened.
    """
    rows = {1: (1.0, 0.4, 5.0, 2.0),        # interior: own != inflow
            2: (2.0, 2.0, 7.0, 7.0)}        # bottom: clean
    call = _guard_call(capin=_guard_capin(rows),
                 flux={(1, 1): {"bottom_falln_nr": 7.0, "nflux_dtcld": 1.0}})
    assert nt.interior_cap_binds(call, 1, "nr") is True
    assert nt.surface_cap_binds(call, 1, "nr") is False


def test_the_bottom_cell_is_not_counted_as_an_interior_interface():
    """Otherwise every surface cap would also read as an interior one and the
    two verdicts would stop being independent."""
    call = _guard_call(capin=_guard_capin({1: (1.0, 1.0, 5.0, 5.0),
                               2: (2.0, 0.5, 7.0, 1.0)}),   # bottom capped
                 flux={(1, 1): {"bottom_falln_nr": 7.0, "nflux_dtcld": 1.0}})
    assert nt.interior_cap_binds(call, 1, "nr") is False


def test_the_dry_arms_are_not_read_with_the_moist_measure():
    """The substring bug, pinned so it cannot come back.

    `nmass_dry` and `nmass_dry_window` both contain `nmass` and both weight by
    a DRY mass. A predicate keyed on the substring called them moist, which
    inverted which ledger appeared to close (owner review §9).
    """
    assert nt.number_transfer_metric("nmass") == "moist_layer_mass"
    assert nt.number_transfer_metric("nmass_dry") == "current_dry_layer_mass"
    assert nt.number_transfer_metric("nmass_dry_window") == "window_dry_layer_mass"
    # and the measures they produce are actually different
    den, dz, qv = [1.2, 1.0], [100.0, 120.0], [0.02, 0.01]
    mdry0 = [80.0, 90.0]
    got = {m: nt.number_transfer_weights(m, den, dz, qv, mdry0)[1]
           for m in ("thickness", "moist_layer_mass",
                     "current_dry_layer_mass", "window_dry_layer_mass")}
    assert len(set(got.values())) == 4, got


def test_an_unregistered_arm_stops_the_read_instead_of_guessing():
    with pytest.raises(ValueError, match="not a registered arm"):
        nt.number_transfer_metric("nmass_dry_experimental")
    with pytest.raises(ValueError, match="not a name"):
        nt.number_transfer_metric(None)


def test_the_stream_and_the_table_must_agree_about_the_metric():
    """Two sources, and neither is allowed to win quietly.

    `G33N METRIC` is what the BUILD said about itself; the table is what the
    name is taken to mean. Either can go stale -- the table was wrong about
    `nmass_dry` until it was measured -- so a disagreement has to stop the read
    rather than resolve toward whichever the reader trusts (owner review 3.1).
    """
    assert nt.number_transfer_metric("nmass_dry", "current_dry_layer_mass") \
        == "current_dry_layer_mass"
    assert nt.number_transfer_metric("nmass_dry", None) == "current_dry_layer_mass"
    with pytest.raises(ValueError, match="do not guess which"):
        nt.number_transfer_metric("nmass_dry", "moist_layer_mass")


def test_the_declared_metric_reaches_every_call_not_only_the_last():
    """`G33N METRIC` follows STREAM_BEGIN, so the header dict cannot hold it,
    and the assignment has to run per call. Both were wrong at first: the value
    was read from the header (always None) and set outside the loop (last call
    only)."""
    body = _stream(_call(1), _call(2), _call(3))
    head, rest = body.split("\n", 1)
    stream = head + "\nG33N METRIC current_dry_layer_mass\n" + rest
    got = nt.calls(stream)
    assert len(got) == 3
    assert [c.get("declared_metric") for c in got] == \
        ["current_dry_layer_mass"] * 3
    # and absent is absent, not a guess
    assert [c.get("declared_metric") for c in nt.calls(body)] == [None] * 3


def _hdr_with_metric(metric="thickness", extra=""):
    body = _stream(_call(1), _call(2))
    head, rest = body.split("\n", 1)
    return head + f"\nG33N METRIC {metric}\n" + extra + rest


def test_the_metric_declaration_is_exactly_once_and_only_in_the_header():
    """`G33N METRIC` names the measure the whole stream is READ with, so a
    second declaration, one before the header, or an unknown value each change
    which ledger a residual is judged against (owner review 4.1, 4.2)."""
    good = _hdr_with_metric()
    assert nt.stream_header(good)["number_transfer_metric"] == "thickness"

    with pytest.raises(nt.StreamError, match="declares G33N METRIC twice"):
        nt.stream_header(_hdr_with_metric(extra="G33N METRIC moist_layer_mass\n"))
    with pytest.raises(nt.StreamError, match="before STREAM_BEGIN"):
        nt.stream_header("G33N METRIC thickness\n" + _stream(_call(1)))
    with pytest.raises(nt.StreamError, match="not a measure"):
        nt.stream_header(_hdr_with_metric("made_up_measure"))


def test_an_unregistered_arm_cannot_walk_past_the_registry_by_declaring():
    """The docstring said an unknown arm stops the read; the code returned the
    declaration when the stream supplied one, so any name could bypass the
    closed registry. A declaration is a CROSS-CHECK, never a substitute
    (owner review 4.4)."""
    with pytest.raises(ValueError, match="not a registered arm"):
        nt.number_transfer_metric("not_an_arm", "thickness")
    with pytest.raises(ValueError, match="not a registered arm"):
        nt.number_transfer_metric("not_an_arm", None)


def test_the_measure_is_part_of_the_run_identity():
    """Two streams differing only in transfer measure were the same run to
    `validated_run_identity`, and the measure decides which ledger closes."""
    ident = nt.validated_run_identity(_hdr_with_metric())
    assert ident["number_transfer_metric"] == "thickness"
    # and the declaration must AGREE with the arm: `_stream` builds a `legacy`
    # header, so declaring a dry measure on it is a defect in one of the two
    # and is refused rather than resolved toward either.
    with pytest.raises(ValueError, match="do not guess which"):
        nt.validated_run_identity(_hdr_with_metric("current_dry_layer_mass"))


def test_both_readers_refuse_a_metric_declared_after_the_body():
    """`stream_header` broke at the first call, so it IGNORED a late metric
    while `calls()` refused it -- and the permissive one is what decides run
    identity. Found by the adversarial pass, not by the change that introduced
    the rule."""
    good = _hdr_with_metric()
    late = good.replace("G33N STREAM_END", "G33N METRIC moist_layer_mass\nG33N STREAM_END")
    for reader in (nt.stream_header, nt.calls):
        with pytest.raises(nt.StreamError, match="after the first call"):
            reader(late)
    # and a stream whose ONLY declaration is late -- no duplicate to catch it
    bare = _stream(_call(1), _call(2))
    only_late = bare.replace("G33N STREAM_END",
                             "G33N METRIC thickness\nG33N STREAM_END")
    for reader in (nt.stream_header, nt.calls):
        with pytest.raises(nt.StreamError, match="after the first call"):
            reader(only_late)
