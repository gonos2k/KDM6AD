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
    with pytest.raises(nt.StreamError, match="gap or overlap"):
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


def test_a_NON_extension_record_outside_a_call_is_still_tolerated():
    """The stream legitimately carries STAGE records for stages this parser does
    not read. Refusing those would reject valid decision streams; only the
    number-extension families are bracket-bound."""
    stray = "G33F STAGE 1 - kernel_init 0 rhoair0 1 0 f32 3F800000\n"
    s = _hdr(1) + stray + _call(1) + "G33N STREAM_END\n"
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

_F64_ONE = "3FF0000000000000"      # 1.0
_F32_ONE = "3F800000"


def _f64(text):
    """The f32 synthetic stream, widened -- header, labels and hex together."""
    out = []
    for line in text.splitlines():
        if line.startswith("G33N STREAM_BEGIN"):
            # AFTER the header, which is where the driver writes it.
            out += [line, "G33N PROTOCOL 8 8"]
            continue
        line = line.replace(" f32 ", " f64 ").replace(_F32_ONE, _F64_ONE)
        if line.startswith("G33N CALL_BEGIN"):
            line = line.replace("42C80000", "4059000000000000")
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
        nt.calls(s.replace("\n", "\nG33N PROTOCOL 8 8\n", 1))


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
        nt.calls(_f64(_stream(_call(1))).replace("PROTOCOL 8 8",
                                                 "PROTOCOL 8 16"))
