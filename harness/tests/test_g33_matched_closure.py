"""The matched closure, and the control that decides whether a row is evidence."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
import g33_matched_closure as mc  # noqa: E402
from test_g33_number_transport import _call, _stream  # noqa: E402


def _with_xfer(cid, mstep=1, dq="3F800000", dn="40000000"):
    """A complete call whose XFER universe matches the declared mstep — the
    strict parser now requires exactly sub-steps 1..mstep."""
    body = _call(cid).replace(
        "G33F MSTEP 1 main 1 i32 00000001",
        f"G33F MSTEP 1 main 1 i32 {mstep:08X}")
    xf = "".join(f"G33F XFER 1 {n} 1 main f32 {dq} {dn}\n"
                 for n in range(1, mstep + 1))
    xf += "G33F XFER 1 1 1 ice f32 00000000 00000000\n"
    return body.replace("G33N CALL_END", xf + "G33N CALL_END")


def test_transfers_are_summed_over_substeps_within_one_call():
    """The bottom cell exports once per sub-step; the segment budget spans them
    all, so a single-sub-step read would understate the outflow."""
    got = mc.transfers(_stream(_with_xfer(1, mstep=2),
                               feats="mstep,mstepi,nflux,xfer"))
    assert got[(1, 1, 1, "main")] == (2.0, 4.0)


def test_transfers_are_not_pooled_across_calls():
    """Keyed by the call's ordinal: pooling would attribute one call's outflow to
    another, which is the defect the G33N framing exists to stop."""
    got = mc.transfers(_stream(_with_xfer(1), _with_xfer(2),
                               feats="mstep,mstepi,nflux,xfer"))
    assert got[(1, 1, 1, "main")] == (1.0, 2.0)
    assert got[(2, 1, 1, "main")] == (1.0, 2.0)


def test_the_chain_map_matches_the_kernel_sub_cycles():
    """mstep carries qr/nr and mstep_i carries qi/ni (F:1179-1180). Pairing qr
    with ni is the un-matched comparison this module replaces."""
    assert mc.CHAIN == {"main": ("qr", "nr"), "ice": ("qi", "ni")}


def test_a_failing_mass_control_is_flagged_not_reported_as_a_result(capsys):
    """A mass row that does not close means the accounting for that chain is
    missing a term, so NEITHER row of the pair is evidence."""
    def fake(_stream, basis="operator"):
        return {("ice", "qi", 2): {"out": 1.0, "residual": -3.8, "start": 1.0,
                                   "calls": 12},
                ("ice", "ni", 2): {"out": 1.0, "residual": -1.6, "start": 1.0,
                                   "calls": 12},
                ("main", "qr", 1): {"out": 1.0, "residual": 1e-9, "start": 1.0,
                                    "calls": 12},
                ("main", "nr", 1): {"out": 1.0, "residual": 0.15, "start": 1.0,
                                    "calls": 12}}
    orig, mc.closures = mc.closures, fake
    try:
        mc.report("")
    finally:
        mc.closures = orig
    out = capsys.readouterr().out
    assert "!! ice/qi col 2: matched_mass_control_failed" in out
    assert "!! main/qr" not in out, "a control that closes must not be flagged"


def test_an_unusable_row_carries_a_null_number_result_in_the_JSON(monkeypatch):
    """A warning printed under a table is separated from it the moment someone
    copies the table. In the JSON the exclusion is structural (owner §6.2)."""
    def fake(_stream, basis="operator"):
        return {("ice", "qi", 2): {"out": 1.0, "residual": -3.8, "start": 1.0,
                                   "calls": 1},
                ("ice", "ni", 2): {"out": 1.0, "residual": -1.6, "start": 1.0,
                                   "calls": 1},
                ("main", "qr", 1): {"out": 1.0, "residual": 1e-12, "start": 1.0,
                                    "calls": 1},
                ("main", "nr", 1): {"out": 1.0, "residual": 0.15, "start": 1.0,
                                    "calls": 1}}
    monkeypatch.setattr(mc, "closures", fake)
    a = mc.analysis("")
    assert a["ice/ni/2"]["usable"] is False
    assert a["ice/ni/2"]["number_result"] is None
    assert "matched_mass_control_failed" in a["ice/ni/2"]["reason"]
    assert a["main/nr/1"]["usable"] is True
    assert a["main/nr/1"]["number_result"] == pytest.approx(0.15)


def test_the_control_tolerance_is_derived_not_a_round_number():
    """1e-3 accepted a residual thousands of f32 eps as 'roundoff' (owner §6.1).
    gamma_n = n*eps/(1-n*eps) scales with the operation count."""
    small = mc.control_tolerance(8, 1.0)
    large = mc.control_tolerance(8000, 1.0)
    assert small < large < 1e-3
    assert small == pytest.approx(8 * 2.0 ** -24, rel=1e-6)


def test_the_interface_term_is_departure_minus_arrival():
    """dq(i,k+1) is written twice with different caps: as the cell's own outflow
    (pre-update) and as the inflow below (post-update). Pairing the two across an
    interface is what exposes the destroyed mass (P0-4b)."""
    ROOTB = ROOT / "g33_fortran"
    b = (ROOTB / "g33_fortran_bindings.py").read_text()
    assert "CAP_SITES" in b and "TOP_SITES" in b
    # each cap site emits BOTH of a cell's transfers, mass and number
    assert '"dqr(i,k)", "dqr(i,k+1)", "dnr(i,k)", "dnr(i,k+1)"' in b
    assert '"dqi(i,k)", "dqi(i,k+1)", "dni(i,k)", "dni(i,k+1)"' in b
    # the TOP cell is updated outside the interior loop, so it needs its own site
    assert "min(falk(i,k,4)*dtcld/dend(i,k),qci(i,k,2))" in b


def test_the_new_sites_stay_under_the_number_macro():
    """They must not reach the decision stream, like every emission before them."""
    ovl = (ROOT / "g33_fortran" / "make_fortran_overlay.py").read_text()
    for fn in ("_cap_inflow_lines", "_top_lines"):
        body = ovl.split(f"def {fn}(")[1].split("\ndef ")[0]
        assert "KDM6_G33_NUMBER_DUMP" in body
        assert "KDM6_G33_FORTRAN_DUMP" not in body


def test_instrumentation_sites_are_keyed_by_ALGORITHM():
    """The conservative variant rewrote the sedimentation update, so the legacy
    anchors do not exist in it. Keying the sites by algorithm is what let the
    overlay fail loudly on a missing anchor instead of instrumenting the wrong
    statement (owner §11)."""
    import sys
    sys.path.insert(0, str(ROOT / "g33_fortran"))
    import g33_fortran_bindings as fb
    for sites in (fb.XFER_SITES, fb.CAP_SITES, fb.TOP_SITES):
        # The property is that the two BASES differ, not that the vocabulary
        # has exactly two words in it. Diagnostic arms derived from a base
        # share its anchors -- they change what a line computes, not where it
        # sits -- so pinning the set made every new arm fail a test about
        # something else.
        assert {"legacy", "conservative"} <= set(sites), sorted(sites)
        assert sites["legacy"] != sites["conservative"]
        # A derived arm's table is its base's, or MECHANICALLY DERIVED from
        # it. The first version of this demanded identity, and `cons_nmass`
        # broke it correctly: conservative anchors ON the line Arm N edits, so
        # that arm must re-anchor. What the check is for is that no arm
        # invents anchors -- every site must appear in one of the two bases,
        # modulo the one substitution the variant generator applies.
        import re
        def _canon(t):
            return {re.sub(r"dend\(i,k\+1\)\*delz\(i,k\+1\)/\(dend\(i,k\)"
                           r"\*delz\(i,k\)\)", "delz(i,k+1)/delz(i,k)", x)
                    for row in t for x in (row if isinstance(row, tuple) else (row,))
                    if isinstance(x, str)}
        bases = _canon(sites["legacy"]) | _canon(sites["conservative"])
        for algo, tab in sites.items():
            stray = _canon(tab) - bases
            assert not stray, (
                f"{algo} anchors on text neither base carries: {sorted(stray)[:2]}"
                f" -- a new base needs its own anchors, not an invented one")
    # conservative's number inflow keeps the dz-only ratio: that is the anchor
    assert any("delz(i,k+1)/delz(i,k)" in a
               for a, *_ in fb.XFER_SITES["conservative"])


# ---- owner §6.3: the control is per call, not on the aggregate ---------------

def test_two_calls_whose_residuals_CANCEL_do_not_pass():
    """The aggregate control summed every call's residual and judged the total,
    so +1e-3 on one call and -1e-3 on the next gave a residual of zero and the
    row was admitted -- while BOTH calls' accounting had failed. This is the
    single most dangerous shape the old control accepted, because a defect that
    alternates sign is exactly what a cap or a threshold produces."""
    d = {"out": 1.0, "residual": 0.0, "start": 1.0, "calls": 2,
         "per_call": [{"residual": +1e-3, "out": 1.0, "scale": 1.0, "ops": 8},
                      {"residual": -1e-3, "out": 1.0, "scale": 1.0, "ops": 8}]}
    c = mc.control(d)
    assert c["net"] == pytest.approx(0.0), "the aggregate view sees nothing"
    assert c["gross"] == pytest.approx(2e-3), "the accounting error is real"
    ok, why = mc.usable(d)
    assert not ok and "worst call" in why


def test_a_row_whose_every_call_closes_is_admitted():
    d = {"out": 1.0, "residual": 0.0, "start": 1.0, "calls": 2,
         "per_call": [{"residual": +1e-9, "out": 1.0, "scale": 1.0, "ops": 8},
                      {"residual": -1e-9, "out": 1.0, "scale": 1.0, "ops": 8}]}
    assert mc.usable(d)[0]


def test_the_tolerance_scale_is_not_the_surface_flux_alone():
    """A near-cancelling budget can have |F| far smaller than the terms that
    produced it, so scaling by |F| alone made the threshold arbitrarily tight
    exactly where the arithmetic was worst (owner §6.2)."""
    tiny_flux = {"residual": 1e-6, "scale": 1e-6, "ops": 8}
    real_scale = {"residual": 1e-6, "scale": 1e3, "ops": 8}
    assert mc.control_tolerance(8, tiny_flux["scale"]) < abs(tiny_flux["residual"])
    assert mc.control_tolerance(8, real_scale["scale"]) > abs(real_scale["residual"])


def test_the_operation_count_grows_with_mstep_and_K():
    """It was a flat `calls * 8`, so a 10-sub-step column got the same threshold
    as a 1-sub-step one (owner §6.1)."""
    assert mc.control_tolerance(4 * (10 + 2), 1.0) > mc.control_tolerance(4 * (1 + 2), 1.0)


def test_the_threshold_does_not_claim_to_be_a_proof():
    """Owner §6: gamma_n here is a screening threshold. The operation count is a
    floor and the kernel is not a straight-line summation, so calling a pass a
    roundoff certificate would be overclaiming -- and the artifact says so."""
    d = {"out": 1.0, "residual": 0.0, "start": 1.0, "calls": 1, "per_call": []}
    assert "not a proven bound" in mc.control(d)["tolerance_basis"]



# ---- owner §11: the physical measure may not move with the process ----------

def test_the_OPERATOR_measure_carries_no_qv_so_it_cannot_move():
    """rho_m is what the kernel budgets. The window-fixing below must leave it
    untouched, which is why the published operator headlines are unaffected."""
    import inspect
    src = inspect.getsource(mc._density)
    assert 'if basis == "operator":\n        return rec["rho"]' in src


def test_the_measure_takes_qv_from_the_WINDOW_START_not_the_first_call():
    """`G33R INITIAL` is the window's true start. The first sedimentation call's
    pre-sed `qv` is a SEGMENT quantity -- other microphysics runs before it --
    and the first version used that, regressing the very distinction §16-3
    established for the number inventory (owner P0-1).

    Behavioural, not a source grep: the two are given DIFFERENT humidities and
    the measure must follow the window start."""
    from test_g33_dual_ledger import RHO, DZ, _stream, _g33r

    call_qv = [0.02] * 4                 # what the calls carry
    window_qv = [0.00] * 4               # what the window began with
    g33n = _stream(call_qv).split("G33R BEGIN")[0]
    pre = [10.0, 20.0, 30.0, 40.0]
    post = list(pre)
    stream = g33n + _g33r(call_qv, 0.0, pre, post, initial_qv=window_qv)

    m = mc.window_cell_mass(stream, "physical")
    # window qv is zero, so rho_d == rho_m; the call's 0.02 would divide it down
    for k in range(len(RHO)):
        assert m[(1, k)].density == pytest.approx(RHO[k]), \
            "the measure followed the CALL's qv, not the window's"
        assert m[(1, k)].mass == pytest.approx(RHO[k] * DZ)


def test_the_measure_is_a_LAYER_MASS_not_a_density():
    """`rho*dz` is what is conserved. Freezing only the density and multiplying
    by each call's own `delz` would let the measure move with `delz`."""
    from test_g33_dual_ledger import RHO, DZ, _stream

    m = mc.window_cell_mass(_stream([0.0] * 4), "operator")
    for k in range(len(RHO)):
        assert m[(1, k)].mass == pytest.approx(m[(1, k)].density * m[(1, k)].delz)
        assert m[(1, k)].delz == pytest.approx(DZ)


def test_the_measure_is_keyed_by_CELL_not_by_loop_or_tile():
    """A layer mass is not a property of a loop or a tile. Keying it on the
    first call made a legitimate multi-tile run raise for the columns that call
    did not cover."""
    from test_g33_dual_ledger import _stream

    for key in mc.window_cell_mass(_stream([0.0] * 4), "operator"):
        assert len(key) == 2, f"{key} carries more than (col, k)"


def test_forcing_that_MOVES_between_calls_is_refused(monkeypatch):
    """`rho` and `delz` are forcing -- verified identical in every call that
    carries them, not assumed. A measure built on a moving forcing cannot be
    fixed for the window."""
    from test_g33_dual_ledger import _stream

    stream = _stream([0.0] * 4)
    real = mc.nt.calls

    def drifting(text):
        cs = real(text)
        moved = dict(cs[0])
        moved["outer_pre_sed"] = {
            k: {**v, "rho": v["rho"] * 2} for k, v in cs[0]["outer_pre_sed"].items()}
        return cs + [moved]

    monkeypatch.setattr(mc.nt, "calls", drifting)
    with pytest.raises(ValueError, match="differ between calls"):
        mc.window_cell_mass(stream, "operator")


def test_a_stream_with_NO_WINDOW_cannot_produce_a_PHYSICAL_measure():
    """It needs the window-initial qv. Falling back to a call's own qv is what
    this replaced.

    The window may now come from G33R or from G33P -- an f64 build emits no
    G33R at all and carries the same values in the probe family (owner D6
    follow-on) -- so what is refused is a stream carrying NEITHER. The
    exception type is still ValueError: this function has refused with one
    since it existed and callers catch it, so the boundary translates rather
    than letting the type change go unreported (Codex).
    """
    from test_g33_dual_ledger import _stream

    g33n_only = _stream([0.01] * 4).split("G33R BEGIN")[0]
    mc.window_cell_mass(g33n_only, "operator")          # operator needs no qv
    with pytest.raises(ValueError, match="carries neither"):
        mc.window_cell_mass(g33n_only, "physical")


def test_a_PROBE_stream_produces_the_physical_measure_a_G33R_one_does():
    """The capability the change adds, checked here rather than only at the
    reader: without it the test above would pass on an implementation that
    refuses every f64 stream."""
    from test_g33_dual_ledger import _stream
    from test_g33_probe_read import _stream as _probe

    full = _stream([0.01] * 4)
    g33n_only = full.split("G33R BEGIN")[0]
    want = mc.window_cell_mass(full, "physical")
    got = mc.window_cell_mass(g33n_only + _probe(B=len({c for c, _k in want}),
                                                 K=len({k for _c, k in want})),
                              "physical")
    assert set(got) == set(want), (sorted(got), sorted(want))


def test_a_cell_absent_from_the_measure_is_REFUSED_not_recomputed():
    """Falling back to the call's own density would silently restore the moving
    weight for exactly the cells the window measure does not cover."""
    with pytest.raises(ValueError, match="no window measure"):
        mc.measure_at({(1, 0): None}, (2, 0), "test")
