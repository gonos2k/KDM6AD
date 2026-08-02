"""The refinement analyzer, and the design rule that makes a sweep a refinement.

The §9 sweep as specified does not refine — the kernel picks its own internal step
from `delt`, and 1/2/3/6/12 maps onto dtcld 100/150/100/50/25. A test suite that
only checked the arithmetic would have passed while the experiment measured
nothing, so the design rule is asserted here alongside it.
"""
import math
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import g33_refine_analyze as ra   # noqa: E402

DTCLDCR = 120.0


def dtcld(delt):
    """The kernel's own internal step (F:930-932), which is what refines."""
    loops = max(int(delt / DTCLDCR + 0.5), 1)
    return delt if delt <= DTCLDCR else delt / loops


# ── the design rule ──────────────────────────────────────────────────────────

def test_the_sweep_as_specified_is_not_a_refinement():
    """N=2 integrates COARSER than N=1 and N=3 duplicates N=1. Measured on this
    sequence, the error to the finest is non-monotone, which reads as an operator
    that does not converge and is a sweep that does not refine."""
    steps = [dtcld(300 / n) for n in (1, 2, 3, 6, 12)]
    assert steps == [100.0, 150.0, 100.0, 50.0, 25.0]
    assert steps[1] > steps[0], "N=2 is coarser than N=1"
    assert steps[2] == steps[0], "N=3 duplicates N=1"
    assert steps != sorted(steps, reverse=True), "not monotonically refining"


def test_dtcldcr_is_a_target_interval_not_an_upper_bound():
    """Because the divisor is rounded with `nint` rather than a ceiling, dtcld
    EXCEEDS 120 s for any delt in (120, 180) -- 175 s at delt = 175, about 1.46x
    nominal. An earlier version of this finding called N=2 'past the code's own
    limit', which overstates what the code enforces. Whether that is intended is a
    production-physics question (nint vs ceiling) and a separate owner item."""
    assert dtcld(150.0) == 150.0 > DTCLDCR
    assert dtcld(175.0) == 175.0
    assert dtcld(180.0) == 90.0, "at 180 the rounding tips and the step halves"
    worst = max(dtcld(d) for d in [x / 10 for x in range(1200, 1800)])
    assert worst > DTCLDCR * 1.45


def test_the_corrected_chain_halves_cleanly():
    steps = [dtcld(300 / n) for n in (3, 6, 12, 24)]
    assert steps == [100.0, 50.0, 25.0, 12.5]
    for a, b in zip(steps, steps[1:]):
        assert a == 2 * b


def test_the_policy_control_pair_shares_an_internal_step():
    """N=1 and N=3 integrate identically (three 100 s steps) and differ only in how
    many times the coefficients are refreshed. That is what makes the pair a
    controlled contrast rather than two more sweep members."""
    assert dtcld(300.0) == dtcld(100.0) == 100.0
    assert max(int(300.0 / DTCLDCR + 0.5), 1) == 3     # N=1: one call, 3 subcycles
    assert max(int(100.0 / DTCLDCR + 0.5), 1) == 1     # N=3: three calls, 1 each


def test_the_split_is_exact_in_f32_for_every_member():
    """A member carrying a division rounding the others do not would put a
    difference into the sequence that is not the operator's."""
    for n in (1, 2, 3, 4, 6, 12, 24):
        q = struct.unpack("<f", struct.pack("<f", 300.0 / n))[0]
        assert q == 300.0 / n, n


# ── the analyzer ─────────────────────────────────────────────────────────────

def _run(**vals):
    return {("state", f, 1, 0): v for f, v in vals.items()}


def test_order_is_log2_of_the_error_ratio():
    s = {100.0: 4.0, 50.0: 2.0, 25.0: 1.0}
    assert [round(p, 9) for _, _, _, p in ra.orders(s)] == [1.0, 1.0]


def test_second_order_reads_as_two():
    s = {100.0: 4.0, 50.0: 1.0}
    assert round(ra.orders(s)[0][3], 9) == 2.0


def test_a_bit_identical_member_reports_no_order_rather_than_zero():
    """A zero difference means two members agree to the last bit. That is an
    absence of the signal a rate describes, not a rate of zero — and log2(0) would
    otherwise raise or produce -inf."""
    assert ra.orders({100.0: 0.0, 50.0: 1.0})[0][3] is None
    assert ra.orders({100.0: 1.0, 50.0: 0.0})[0][3] is None


def test_non_halving_neighbours_are_skipped():
    """p = log2(E_h/E_h2) is only an order when the step actually halved. 100->75
    is a 4/3 ratio and reporting it as an order would misstate the exponent."""
    assert ra.orders({100.0: 4.0, 75.0: 2.0}) == []


def test_mass_and_number_are_reported_separately():
    """A mass field and a number moment can converge at different rates, and
    averaging them hides exactly the number-moment behaviour the conservative-nr
    blocker is about."""
    assert not set(ra.MASS) & set(ra.NUMBER)
    r = _run(qr=1.0, nr=2.0)
    assert ra._keys(r, "mass") != ra._keys(r, "number")


def test_the_norm_is_a_max_not_a_mean():
    """Most cells of an arithmetic-synthetic fixture are quiet; a mean would
    mostly measure how many."""
    a = {("state", "qr", 1, k): 0.0 for k in range(10)}
    b = dict(a); b[("state", "qr", 1, 3)] = 1.0
    assert ra._norm(a, b, list(a)) == 1.0


def test_successive_pairs_are_derived_not_hardcoded():
    """The doubling pairs must follow the members present — a hardcoded list built
    for 1/2/3/6/12 silently drops the 12->24 estimate the corrected chain adds."""
    runs = {n: _run(qr=float(n)) for n in (3, 6, 12, 24)}
    got = ra.successive(runs)["mass"]
    assert set(got) == {100.0, 50.0, 25.0}


def test_error_to_finest_uses_the_actual_finest_member(tmp_path):
    runs = {n: _run(qr=float(n)) for n in (3, 6, 12, 24)}
    got = ra.to_finest(runs)["mass"]
    assert 12.5 not in got, "the finest member is the reference, not a data point"
    assert set(got) == {100.0, 50.0, 25.0}


# ── the parser must fail closed (owner review §2) ─────────────────────────────
#
# A refinement member is a COMPLETE state, not "at least one record". The failure
# direction is what makes this a P0 rather than tidiness: a stream missing the cell
# that carries the largest difference produces a SMALLER error norm, so a
# permissive reader reports better convergence than actually happened. That is the
# same shape as the manifest-replayed-into-the-writer check that saw no missing
# k/shape/field, and the rate comparator that could pass a truncated dump.

def _stream(nsplit=3, mode="rezero", algo="legacy", B=2, K=2, end=True):
    out = [f"G33R BEGIN nsplit {nsplit} {mode} {algo} "
           f"delt {300/nsplit:.6f} loops 1 dtcld {300/nsplit:.6f}"]
    for f in ra.STATE_FIELDS:
        for i in range(1, B + 1):
            for k in range(K):
                out.append(f"G33R STATE {f} {i} {k} 3F800000")
    for f in (1, 2, 3):
        for i in range(1, B + 1):
            out.append(f"G33R PREC {f} {i} 3F800000")
    if end:
        out.append("G33R END")
    return "\n".join(out) + "\n"


def _write(tmp_path, text, name="n3.rezero.txt"):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_a_well_formed_member_parses(tmp_path):
    r = ra.read(_write(tmp_path, _stream()), nsplit=3)
    assert r[("meta", "nsplit")] == 3
    assert r[("meta", "dtcld")] == 100.0


def test_a_deleted_record_is_rejected(tmp_path):
    """THE case. Deleting the record carrying the largest difference makes the
    error norm smaller, so this fails in the flattering direction."""
    lines = _stream().splitlines()
    del lines[5]
    with pytest.raises(ra.RefineError, match="ragged|field set"):
        ra.read(_write(tmp_path, "\n".join(lines) + "\n"))


def test_a_duplicate_record_with_a_different_value_is_rejected(tmp_path):
    """Last-write-wins is silent: the analysed value would be the second one with
    no indication the first existed."""
    lines = _stream().splitlines()
    lines.insert(6, "G33R STATE th 1 0 40000000")
    with pytest.raises(ra.RefineError, match="duplicate"):
        ra.read(_write(tmp_path, "\n".join(lines) + "\n"))


def test_a_missing_END_is_rejected(tmp_path):
    """A run killed partway through has every record it managed to write and no
    END. Without this it reads as a shorter but valid member."""
    with pytest.raises(ra.RefineError, match="END"):
        ra.read(_write(tmp_path, _stream(end=False)))


def test_a_second_BEGIN_is_rejected(tmp_path):
    """Two runs appended to one file: the records interleave and the duplicate
    check would fire, but the diagnosis should name the real cause."""
    with pytest.raises(ra.RefineError, match="BEGIN"):
        ra.read(_write(tmp_path, _stream() + _stream(nsplit=6)))


def test_a_nsplit_disagreeing_with_the_filename_is_rejected(tmp_path):
    """A member analysed under the wrong step lands at the wrong point in the
    chain, which changes every order estimate downstream of it."""
    with pytest.raises(ra.RefineError, match="nsplit"):
        ra.read(_write(tmp_path, _stream(nsplit=6), name="n3.rezero.txt"), nsplit=3)


def test_a_renamed_field_is_rejected(tmp_path):
    with pytest.raises(ra.RefineError, match="field set"):
        ra.read(_write(tmp_path, _stream().replace("G33R STATE th", "G33R STATE tt")))


def test_a_NaN_is_rejected(tmp_path):
    """NaN propagates through the subtraction and `max` silently: a NaN norm
    compares False against everything, so monotonicity checks pass."""
    with pytest.raises(ra.RefineError, match="non-finite"):
        ra.read(_write(tmp_path, _stream().replace(
            "G33R STATE th 1 0 3F800000", "G33R STATE th 1 0 7FC00000")))


def test_an_infinity_is_rejected(tmp_path):
    with pytest.raises(ra.RefineError, match="non-finite"):
        ra.read(_write(tmp_path, _stream().replace(
            "G33R STATE th 1 0 3F800000", "G33R STATE th 1 0 7F800000")))


def test_half_a_file_is_rejected(tmp_path):
    lines = _stream().splitlines()
    with pytest.raises(ra.RefineError):
        ra.read(_write(tmp_path, "\n".join(lines[:len(lines) // 2]) + "\n"))


def test_an_unknown_G33R_record_is_rejected(tmp_path):
    """A new record class from a future driver must stop the analysis, not be
    skipped -- silently ignoring it is how a changed output format gets analysed
    under the old assumptions."""
    lines = _stream().splitlines()
    lines.insert(2, "G33R FLUX 1 0 3F800000")
    with pytest.raises(ra.RefineError, match="unrecognised"):
        ra.read(_write(tmp_path, "\n".join(lines) + "\n"))


def test_records_outside_the_block_are_rejected(tmp_path):
    with pytest.raises(ra.RefineError, match="outside"):
        ra.read(_write(tmp_path, _stream() + "G33R STATE th 1 0 3F800000\n"))


# ── cross-member identity ────────────────────────────────────────────────────

def test_members_with_different_universes_are_rejected(tmp_path):
    """Comparing over the intersection lets an incomplete member report a smaller
    error than a complete one -- convergence measured on absence."""
    a = ra.read(_write(tmp_path, _stream(nsplit=3), "a.txt"))
    b = ra.read(_write(tmp_path, _stream(nsplit=6, B=3), "b.txt"))
    with pytest.raises(ra.RefineError, match="record universe"):
        ra.require_same_universe({3: a, 6: b})


def test_members_mixing_algorithms_are_rejected(tmp_path):
    a = ra.read(_write(tmp_path, _stream(nsplit=3), "a.txt"))
    b = ra.read(_write(tmp_path, _stream(nsplit=6, algo="conservative"), "b.txt"))
    with pytest.raises(ra.RefineError, match="algorithms"):
        ra.require_same_universe({3: a, 6: b})


def test_matching_members_pass(tmp_path):
    a = ra.read(_write(tmp_path, _stream(nsplit=3), "a.txt"))
    b = ra.read(_write(tmp_path, _stream(nsplit=6), "b.txt"))
    ra.require_same_universe({3: a, 6: b})


def test_the_norm_does_not_skip_a_missing_key():
    """`_norm` must not carry an `if k in a and k in b` guard: that is the silent
    skip `require_same_universe` exists to make unnecessary, and leaving both is
    how the guard stops being load-bearing."""
    src = (ROOT / "g33_refine_analyze.py").read_text()
    body = src[src.index("def _norm("):src.index("def _keys(")]
    # Code only. The comment inside `_norm` names the guard in order to explain
    # why it is absent, and a raw substring search over the whole body matches
    # the explanation as readily as the thing it warns about.
    code = "\n".join(ln.split("#", 1)[0] for ln in body.splitlines())
    assert "if k in a and k in b" not in code


# ── where the order may be computed (owner review §4) ────────────────────────

def test_the_order_is_only_reported_for_the_successive_series(capsys, tmp_path):
    """The finest member is not the exact solution. With X_h = X* + C h^p the
    error to it is |C||h^p - hf^p|, whose ratio is NOT 2^p: a truly first-order
    operator reads +1.222 then +1.585 at hf = 12.5. Testing the formula alone
    passes whether or not it is applied to a series it is valid for, which is how
    the earlier +1.221/+1.413 got read as 'near or above first order'."""
    runs = {n: ra.read(_write(tmp_path, _stream(nsplit=n), f"n{n}.txt"))
            for n in (3, 6, 12, 24)}
    ra.report(runs, "t")
    out = capsys.readouterr().out
    head, _, tail = out.partition("error to finest")
    assert "order" in head
    assert "p = " not in tail, "an order was reported against the finest member"
    assert "monotone" in tail


def test_a_first_order_operator_reads_above_one_against_the_finest():
    """The bias, as a number, so the withdrawn reading cannot quietly return."""
    hf = 12.5
    ratio = (100.0 - hf) / (50.0 - hf)
    assert round(math.log2(ratio), 3) == 1.222
    assert round(math.log2((50.0 - hf) / (25.0 - hf)), 3) == 1.585


# ── experiment provenance (owner review §9) ──────────────────────────────────

import g33_refine_manifest as rm   # noqa: E402


def _outputs(tmp_path, ns):
    d = tmp_path / "out"
    d.mkdir(exist_ok=True)
    for n in ns:
        (d / f"n{n}.rezero.txt").write_text(_stream(nsplit=n))
    return d


def _build(d, tmp_path):
    mod = tmp_path / "m.F"; mod.write_text("x")
    fix = tmp_path / "f.f90"; fix.write_text("y")
    return rm.build(d, module=mod, fixture=fix, compiler="gfortran-test")


def test_an_experiment_manifest_is_never_decision_eligible(tmp_path):
    """A constant with no argument that sets it. Writing the experiment somewhere
    else would be a convention; this is structural."""
    man = _build(_outputs(tmp_path, (3, 6)), tmp_path)
    assert man["decision_eligible"] is False
    assert man["artifact_type"] == "refinement_experiment"
    src = (ROOT / "g33_refine_manifest.py").read_text()
    assert "decision_eligible=" not in src and '"decision_eligible": True' not in src


def test_the_manifest_records_what_is_needed_to_reproduce(tmp_path):
    man = _build(_outputs(tmp_path, (3, 6)), tmp_path)
    for k in ("repo_commit", "tree_dirty", "module_sha256", "fixture_sha256",
              "compiler", "analyzer_sha256", "members"):
        assert k in man, k
    assert all("output_sha256" in m for m in man["members"])


def test_the_manifest_reads_dtcld_from_the_run_not_from_N(tmp_path):
    """Recomputing it would restate the assumption the §9 correction exists to
    check -- that the kernel, not the caller, picks the step."""
    man = _build(_outputs(tmp_path, (3, 6)), tmp_path)
    assert {m["nsplit"]: m["dtcld"] for m in man["members"]} == {3: 100.0, 6: 50.0}


def test_the_specified_sweep_is_flagged_as_not_a_refinement_chain(tmp_path):
    """The synthetic stream reports dtcld = 300/N, so this checks the flag's logic
    on a halving vs a non-halving set of steps."""
    assert _build(_outputs(tmp_path, (3, 6, 12, 24)), tmp_path)["is_refinement_chain"]
    d = tmp_path / "o2"; d.mkdir()
    for n, s in ((3, 100.0), (4, 75.0)):
        (d / f"n{n}.rezero.txt").write_text(_stream(nsplit=n))
    assert not _build(d, tmp_path)["is_refinement_chain"]


def test_the_policy_control_pair_is_not_claimed_to_be_a_chain(tmp_path):
    """N=1 and N=3 share dtcld = 100 s -- that is what makes them a controlled
    contrast, and it is exactly what disqualifies them as a refinement sequence.
    The manifest must not present the pair as one."""
    d = tmp_path / "o3"; d.mkdir()
    (d / "n1.rezero.txt").write_text(
        "G33R BEGIN nsplit 1 rezero legacy delt 300.000000 loops 3 dtcld 100.000000\n"
        + "\n".join(_stream(nsplit=3).splitlines()[1:]) + "\n")
    (d / "n3.rezero.txt").write_text(_stream(nsplit=3))
    man = _build(d, tmp_path)
    assert not man["is_refinement_chain"]
    assert {m["dtcld"] for m in man["members"]} == {100.0}


# ── the C++ call-boundary control (owner review §3) ──────────────────────────

def test_the_cpp_leg_is_tagged_so_it_cannot_be_compared_against_fortran(tmp_path):
    """The C++ driver emits host-K (bottom-first) while the Fortran driver emits
    top-first, so a cross-backend read needs the normalizer's flip. Tagging the
    algorithm `-cpp` makes an accidental mixed set fail the analyzer's algorithm
    check instead of being silently compared with the k axis reversed -- which is
    the exact defect that produced the withdrawn v10 conclusion."""
    f = ra.read(_write(tmp_path, _stream(nsplit=3, algo="legacy"), "f.txt"))
    c = ra.read(_write(tmp_path, _stream(nsplit=3, algo="legacy-cpp"), "c.txt"))
    with pytest.raises(ra.RefineError, match="algorithms"):
        ra.require_same_universe({1: f, 3: c})


def test_the_control_pair_must_report_the_same_dtcld(tmp_path):
    """What makes N=1/N=3 a control rather than two refinement members: the C++
    picks loops=3 at delt=300 and loops=1 at delt=100, so both integrate at
    dtcld=100 with three coefficient refreshes. A member reporting a different
    dtcld is not part of this contrast."""
    a = ra.read(_write(tmp_path,
        "G33R BEGIN nsplit 1 rezero legacy-cpp delt 300.000000 loops 3 dtcld 100.000000\n"
        + "\n".join(_stream(nsplit=3).splitlines()[1:]) + "\n", "a.txt"))
    b = ra.read(_write(tmp_path, _stream(nsplit=3, algo="legacy-cpp"), "b.txt"))
    assert a[("meta", "dtcld")] == b[("meta", "dtcld")] == 100.0
    assert a[("meta", "loops")] == 3 and b[("meta", "loops")] == 1


def test_compute_loops_max_matches_the_fortran_rule():
    """The control depends on both backends choosing the same sub-cycle count.
    coordinator.cpp:1297 is `(int)(delt/dtcldcr + 0.5)`, and F:930 is
    `max(nint(delt/dtcldcr),1)` -- the same for positive delt."""
    def cpp(delt, cr=120.0):
        n = int(delt / cr + 0.5)
        return n if n > 1 else 1
    for delt in (12.5, 25.0, 50.0, 100.0, 150.0, 175.0, 300.0):
        assert cpp(delt) == max(int(delt / 120.0 + 0.5), 1)
    assert cpp(300.0) == 3 and cpp(100.0) == 1


# ── physical column budgets (owner review §7) ────────────────────────────────

def _stream_fc(nsplit=3, B=2, K=2, rho="3F800000", delz="3F800000"):
    """A stream carrying forcing, so a rho*dz budget can be formed."""
    body = _stream(nsplit=nsplit, B=B, K=K).splitlines()
    extra = [f"G33R FORCING {n} {i} {k} {v}"
             for n, v in (("rho", rho), ("delz", delz))
             for i in range(1, B + 1) for k in range(K)]
    return "\n".join(body[:-1] + extra + [body[-1]]) + "\n"


def test_a_budget_needs_forcing_and_says_so_without_it(tmp_path):
    """Optional so older streams still parse -- but silently reporting an empty
    budget as if it were a converged one would be worse than saying nothing."""
    assert ra.column_budgets(ra.read(_write(tmp_path, _stream()))) == {}


def test_forcing_must_cover_the_same_cells_as_the_state(tmp_path):
    """A half-populated forcing set drops columns from the budget, and a column
    integral missing a level is smaller -- the flattering direction again."""
    txt = _stream_fc().replace("G33R FORCING rho 1 0 3F800000\n", "")
    with pytest.raises(ra.RefineError, match="forcing"):
        ra.read(_write(tmp_path, txt))


def test_the_budget_is_rho_dz_weighted(tmp_path):
    """With rho = delz = 1 the weight is 1, so the column water budget is the plain
    sum of the six species over levels -- 6 species x 2 levels x 1.0."""
    r = ra.read(_write(tmp_path, _stream_fc()))
    b = ra.column_budgets(r)
    assert b[("water", 1)] == pytest.approx(12.0)
    assert b[("nr", 1)] == pytest.approx(2.0)


def test_the_weight_actually_multiplies(tmp_path):
    """rho = 2, delz = 4 -> weight 8. Guards against the weight being dropped,
    which would make the 'physical' budget the mixing-ratio sum again."""
    r = ra.read(_write(tmp_path, _stream_fc(rho="40000000", delz="40800000")))
    assert ra.column_budgets(r)[("water", 1)] == pytest.approx(96.0)


def test_budgets_are_reported_per_column_not_summed(tmp_path):
    """A budget error in one column must not be diluted by the others -- on this
    fixture column 3 behaves quite differently from column 1."""
    b = ra.column_budgets(ra.read(_write(tmp_path, _stream_fc(B=3))))
    assert {c for q, c in b if q == "water"} == {1, 2, 3}


# ── branch topology (owner review §5) ────────────────────────────────────────

def _stream_top(nsplit=3, th="43800000", qg="00000000", B=1, K=1):
    """th = 256.0 by default (cold); qg zero unless given."""
    out = [f"G33R BEGIN nsplit {nsplit} rezero legacy "
           f"delt {300/nsplit:.6f} loops 1 dtcld {300/nsplit:.6f}"]
    for f in ra.STATE_FIELDS:
        v = th if f == "th" else (qg if f == "qg" else "3F800000")
        for i in range(1, B + 1):
            for k in range(K):
                out.append(f"G33R STATE {f} {i} {k} {v}")
    for n in ("rho", "delz", "pii"):
        for i in range(1, B + 1):
            for k in range(K):
                out.append(f"G33R FORCING {n} {i} {k} 3F800000")
    for f in (1, 2, 3):
        for i in range(1, B + 1):
            out.append(f"G33R PREC {f} {i} 3F800000")
    return "\n".join(out + ["G33R END"]) + "\n"


def test_topology_needs_pii_and_says_so_without_it(tmp_path):
    assert ra.topology(ra.read(_write(tmp_path, _stream_fc()))) == {}


def test_the_cold_mask_uses_t_not_theta(tmp_path):
    """The branch is on t = th * pii against t0c. Reading `th` directly would put
    every cell on the wrong arm wherever pii != 1."""
    r = ra.read(_write(tmp_path, _stream_top(th="43800000")))   # 256 K, pii = 1
    assert ra.topology(r)[("cold", 1, 0)] is True
    r = ra.read(_write(tmp_path, _stream_top(th="43960000")))   # 300 K
    assert ra.topology(r)[("cold", 1, 0)] is False


def test_a_species_presence_flip_is_detected(tmp_path):
    """The measured instability: qg present at h=100 s, exactly zero for four
    members, present again at 3.125 s. A member set that straddles that is not
    computing a convergence rate."""
    a = ra.topology(ra.read(_write(tmp_path, _stream_top(qg="00000000"), "a.txt")))
    b = ra.topology(ra.read(_write(tmp_path, _stream_top(qg="30D1B717"), "b.txt")))
    assert a[("qg", 1, 0)] is False and b[("qg", 1, 0)] is True


def test_a_value_below_qmin_does_not_count_as_present(tmp_path):
    """Otherwise every denormal counts as a branch and the record is noise."""
    tiny = struct.unpack("<I", struct.pack("<f", 1.0e-20))[0]
    r = ra.read(_write(tmp_path, _stream_top(qg=f"{tiny:08X}")))
    assert ra.topology(r)[("qg", 1, 0)] is False


# ── moist-enthalpy ledger (owner review §8.2) ────────────────────────────────

def test_the_reference_enthalpies_reproduce_the_codes_latent_heats_at_T0():
    """h_v - h_l = XLV, h_l - h_i = XLF, h_v - h_i = XLS at T0. The code's own
    constants satisfy XLS - XLV == XLF exactly, so a consistent construction must
    agree with all three -- otherwise the ledger disagrees with the kernel about
    latent heat before any physics happens."""
    hd, hv, hl, hi = ra._enthalpies(ra.T0C)
    assert hd == 0.0
    assert hv - hl == pytest.approx(ra.XLV)
    assert hl - hi == pytest.approx(ra.XLF)
    assert hv - hi == pytest.approx(ra.XLS)
    assert ra.XLS - ra.XLV == pytest.approx(ra.XLF)


def test_the_constants_are_the_fortran_ones():
    """cp = 7 r_d/2 and cpv = 4 r_v are DERIVED in module_model_constants.F, not
    written as literals, so a hardcoded 1004.5 here could drift from the kernel."""
    assert ra.CPD == pytest.approx(7 * 287.0 / 2)
    assert ra.CPV == pytest.approx(4 * 461.6)
    assert (ra.CLIQ, ra.CICE) == (4190.0, 2106.0)


def test_the_ledger_needs_both_endpoints(tmp_path):
    """Without the initial state there is no dH, and reporting a residual computed
    against an assumed start would be worse than reporting nothing."""
    assert ra.enthalpy_ledger(ra.read(_write(tmp_path, _stream_fc()))) == {}


def _stream_ledger(tmp_path, th_end="43800000", name="l.txt"):
    """Initial == final except th, so dH isolates the temperature change."""
    body = _stream(nsplit=3, B=1, K=1).splitlines()
    init = [f"G33R INITIAL {f} 1 0 " + ("43800000" if f == "th" else "3F800000")
            for f in ra.STATE_FIELDS]
    fin = [f"G33R STATE {f} 1 0 " + (th_end if f == "th" else "3F800000")
           for f in ra.STATE_FIELDS]
    forc = [f"G33R FORCING {n} 1 0 3F800000" for n in ("rho", "delz", "pii")]
    prec = [f"G33R PREC {f} 1 00000000" for f in (1, 2, 3)]
    return _write(tmp_path, "\n".join([body[0]] + init + fin + forc + prec
                                      + ["G33R END"]) + "\n", name)


def test_an_unchanged_column_with_no_precipitation_closes_exactly(tmp_path):
    """The null case. If this is not zero the ledger has an offset and every
    comparison built on it inherits the offset."""
    L = ra.enthalpy_ledger(ra.read(_stream_ledger(tmp_path)))
    assert L[1]["residual"] == pytest.approx(0.0, abs=1e-9)


def test_a_warmed_column_shows_a_positive_dH(tmp_path):
    """Direction check: heating with no precipitation out must raise H, so the
    residual is positive. A sign error here would invert every reading."""
    L = ra.enthalpy_ledger(ra.read(_stream_ledger(tmp_path, th_end="438C0000")))
    assert L[1]["dH"] > 0 and L[1]["residual"] > 0


def test_precipitation_carries_enthalpy_out(tmp_path):
    """The flux term must have the sign that CLOSES a column losing condensate,
    not one that doubles the loss."""
    p = _stream_ledger(tmp_path, name="p.txt")
    txt = p.read_text().replace("G33R PREC 1 1 00000000", "G33R PREC 1 1 3F800000")
    L = ra.enthalpy_ledger(ra.read(_write(tmp_path, txt, "p2.txt")))
    assert L[1]["H_precip_out"] != 0.0
    assert L[1]["residual"] == pytest.approx(L[1]["dH"] + L[1]["H_precip_out"])


# ── operator-consistency ledger (owner review §8.1) ──────────────────────────

def test_the_code_coefficients_are_the_codes_own():
    """cpmcal/xlcal at F:818-819 with xlv1 = cl - cpv at F:3406. Getting xlv1
    wrong would make the operator ledger measure a formula the kernel does not
    use, which is the one thing it exists to avoid."""
    assert ra.XLV1 == pytest.approx(4190.0 - 4 * 461.6)
    assert ra.XLV1 == pytest.approx(2343.6)
    cpm, xl, xlf = ra._code_coeffs(ra.T0C, 0.0)
    assert cpm == pytest.approx(ra.CPD)          # qv -> 0, so cpm -> cpd
    assert xl == pytest.approx(ra.XLV)           # xlcal(t0c) == xlv0
    assert xlf == pytest.approx(ra.XLF)          # xls - xlv == xlf at T0


def test_the_codes_xlf_slope_differs_from_the_consistent_one():
    """§3.1: the code's d(xlf)/dT is +2343.6 where a Kirchhoff-consistent value is
    cl - ci = 2084, a 12.5% gap. That gap is exactly what separates the two
    ledgers -- if this assertion ever fails they measure the same thing and running
    both is pointless."""
    _, _, xlf0 = ra._code_coeffs(ra.T0C, 0.0)
    _, _, xlf1 = ra._code_coeffs(ra.T0C + 1.0, 0.0)
    assert xlf1 - xlf0 == pytest.approx(ra.XLV1)
    assert ra.XLV1 != pytest.approx(ra.CLIQ - ra.CICE)
    assert ra.CLIQ - ra.CICE == pytest.approx(2084.0)


def test_a_pure_freeze_leaves_the_operator_potential_unchanged(tmp_path):
    """The defining property: the code's update is cpm dT = xlf dq_ice, so
    converting liquid to ice at the code's own coefficients must leave h_op flat.
    If it does not, the potential is not the one the code conserves and every
    residual below is measuring the potential rather than the code."""
    t = 263.15
    cpm, _, xlf = ra._code_coeffs(t, 1.0e-3)
    dq = 1.0e-4
    dt = xlf / cpm * dq                                 # the code's own update
    cpm2, _, xlf2 = ra._code_coeffs(t + dt, 1.0e-3)
    h0 = cpm * (t - ra.T0C) - xlf * 0.0
    h1 = cpm2 * (t + dt - ra.T0C) - xlf2 * dq
    # not exact: xlf is re-evaluated at the new T, which is the convention chosen
    # so the ledger does not itself encode one policy's answer.
    assert abs(h1 - h0) < abs(xlf * dq) * 0.02


def test_the_two_ledgers_are_not_the_same_computation(tmp_path):
    """They must differ on identical input, or running both proves nothing."""
    r = ra.read(_stream_ledger(tmp_path, th_end="438C0000"))
    a = ra.enthalpy_ledger(r)[1]["residual"]
    b = ra.operator_ledger(r)[1]["residual"]
    assert a != b


def test_the_operator_ledger_needs_both_endpoints(tmp_path):
    assert ra.operator_ledger(ra.read(_write(tmp_path, _stream_fc()))) == {}
