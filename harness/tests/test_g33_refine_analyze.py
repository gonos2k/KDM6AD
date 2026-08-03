"""The refinement analyzer, and the design rule that makes a sweep a refinement.

The §9 sweep as specified does not refine — the kernel picks its own internal step
from `delt`, and 1/2/3/6/12 maps onto dtcld 100/150/100/50/25. A test suite that
only checked the arithmetic would have passed while the experiment measured
nothing, so the design rule is asserted here alongside it.
"""
import math
import struct
import json
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

def _run(dtcld=None, **vals):
    """A minimal in-memory member. `dtcld` is REQUIRED by the analyzer's step
    contract (owner P0-1) — a member that does not say what step it ran cannot
    carry an order — so the helper supplies it rather than each caller."""
    out = {("state", f, 1, 0): v for f, v in vals.items()}
    if dtcld is not None:
        out |= {("meta", "dtcld"): dtcld, ("meta", "mode"): "rezero",
                ("meta", "algorithm"): "legacy"}
    return out


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
    runs = {n: _run(dtcld=300 / n, qr=float(n)) for n in (3, 6, 12, 24)}
    got = ra.successive(runs)["mass"]
    assert set(got) == {100.0, 50.0, 25.0}


def test_error_to_finest_uses_the_actual_finest_member(tmp_path):
    runs = {n: _run(dtcld=300 / n, qr=float(n)) for n in (3, 6, 12, 24)}
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


def test_the_flux_follows_the_WATER_BUDGET_not_the_diagnostic(tmp_path):
    """Changing the fallout diagnostic alone must NOT move the ledger.

    This is the whole correction. The diagnostic and the column water loss disagree
    by an O(1) amount (P0-4b), and a ledger whose flux term came from the diagnostic
    inherited that defect: for legacy the flux was 4-7x the enthalpy change, so the
    residual restated the diagnostic error rather than measuring thermodynamics, and
    the conservative interface looked ~74x better when the two were in fact
    comparable. The flux now follows the water that actually left.
    """
    p = _stream_ledger(tmp_path, name="p.txt")            # initial == final, so dW = 0
    base = ra.enthalpy_ledger(ra.read(p))
    txt = p.read_text().replace("G33R PREC 1 1 00000000", "G33R PREC 1 1 3F800000")
    moved = ra.enthalpy_ledger(ra.read(_write(tmp_path, txt, "p2.txt")))
    assert base[1]["residual"] == pytest.approx(moved[1]["residual"], abs=1e-9)
    assert moved[1]["H_precip_out"] == pytest.approx(0.0, abs=1e-9)


def test_the_flux_is_nonzero_when_water_actually_leaves(tmp_path):
    """The complement: a column that LOSES water must carry enthalpy out, or the
    budget is closed by ignoring the outflow."""
    p = _stream_ledger(tmp_path, name="w.txt")
    txt = p.read_text().replace("G33R STATE qr 1 0 3F800000", "G33R STATE qr 1 0 00000000")
    txt = txt.replace("G33R PREC 1 1 00000000", "G33R PREC 1 1 3F800000")
    L = ra.enthalpy_ledger(ra.read(_write(tmp_path, txt, "w2.txt")))
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


def test_rain_is_the_TOTAL_and_snow_graupel_are_SUBSETS(tmp_path):
    """F:1462-1464: fallsum sums all four species into `rain`, while `snow` is
    fall(2)+fall(4) and `graupel` is fall(3) — components of it, not siblings.
    Summing the three double-counts the frozen part. An earlier version of this
    module did exactly that, and the resulting ~2x offset against the column water
    budget was nearly written off as a convention difference."""
    txt = _stream_fc().replace("G33R PREC 1 1 3F800000", "G33R PREC 1 1 40800000")
    r = ra.read(_write(tmp_path, txt, "p.txt"))
    assert ra.total_precip(r, 1) == pytest.approx(4.0)          # rain alone
    assert ra._ice_fraction(r, 1) == pytest.approx(2.0 / 4.0)   # (snow+graupel)/total


def test_the_total_is_never_the_sum_of_the_three(tmp_path):
    """The bug, as a value: with rain=4, snow=1, graupel=1 the total is 4, not 6."""
    txt = _stream_fc().replace("G33R PREC 1 1 3F800000", "G33R PREC 1 1 40800000")
    r = ra.read(_write(tmp_path, txt, "t.txt"))
    naive = sum(r[k] for k in r if k[0] == "prec" and k[2] == 1)
    assert ra.total_precip(r, 1) == pytest.approx(4.0)
    assert naive == pytest.approx(6.0), "precondition: the naive sum over-counts"
    assert ra.total_precip(r, 1) != pytest.approx(naive)


def test_the_diagnostic_trust_ratio_is_total_over_water_out(tmp_path):
    """The guard against this evidence set's recurring failure: reading the fallout
    diagnostic as if it were the water that left. 1.0 means they agree and the
    diagnostic may be used as a physical quantity; anything else means it may not."""
    p = _stream_ledger(tmp_path, name="d.txt")
    txt = p.read_text().replace("G33R STATE qr 1 0 3F800000", "G33R STATE qr 1 0 00000000")
    txt = txt.replace("G33R PREC 1 1 00000000", "G33R PREC 1 1 3F800000")
    r = ra.read(_write(tmp_path, txt, "d2.txt"))
    ks = sorted({k[3] for k in r if k[0] == "state"})
    assert ra._water_out(r, 1, ks) == pytest.approx(1.0)     # qr 1.0 -> 0.0, rho*dz = 1
    assert ra.total_precip(r, 1) == pytest.approx(1.0)
    assert ra.total_precip(r, 1) / ra._water_out(r, 1, ks) == pytest.approx(1.0)


def test_the_topology_share_is_rho_dz_weighted(tmp_path):
    """Owner P0: the flip's materiality must use this repo's declared column-water
    measure (rho*dz weighted), not an unweighted layer sum. With NON-UNIFORM rho
    the two differ, so a fixture where they agree cannot prove the code is right.

    Built so the weighted answer is exactly 2/3 and the unweighted one exactly 1/2:
    two levels, qg = 1 in both, other water = 1 in level 0 only, and rho*dz = 1 at
    level 0 against 2 at level 1.
    """
    B, K = 1, 2
    rows = [f"G33R BEGIN nsplit 3 rezero legacy delt 100.000000 loops 1 dtcld 100.000000"]
    for f in ra.STATE_FIELDS:
        for k in range(K):
            v = "3F800000" if (f == "qg" or (f == "qv" and k == 0)) else "00000000"
            rows.append(f"G33R STATE {f} 1 {k} {v}")
    for k in range(K):
        rows.append(f"G33R FORCING rho 1 {k} " + ("3F800000" if k == 0 else "40000000"))
        rows.append(f"G33R FORCING delz 1 {k} 3F800000")
        rows.append(f"G33R FORCING pii 1 {k} 3F800000")
    for f in (1, 2, 3):
        rows.append(f"G33R PREC {f} 1 00000000")
    r = ra.read(_write(tmp_path, "\n".join(rows + ["G33R END"]) + "\n", "w.txt"))

    ks = [0, 1]
    w = {k: r[("forcing", "rho", 1, k)] * r[("forcing", "delz", 1, k)] for k in ks}
    weighted = (sum(w[k] * r[("state", "qg", 1, k)] for k in ks)
                / sum(w[k] * sum(r[("state", f, 1, k)] for f in ra.MASS) for k in ks))
    unweighted = (sum(r[("state", "qg", 1, k)] for k in ks)
                  / sum(r[("state", f, 1, k)] for f in ra.MASS for k in ks))
    assert weighted == pytest.approx(3.0 / 4.0)      # (1+2)/(1+1+2)
    assert unweighted == pytest.approx(2.0 / 3.0)    # (1+1)/(1+1+1)
    assert weighted != pytest.approx(unweighted), "fixture must separate the two"

    src = (ROOT / "g33_refine_analyze.py").read_text()
    body = src[src.index("    def _share("):src.index("    print(f\"\\n  final-state presence proxy")]
    code = "\n".join(l.split("#", 1)[0] for l in body.splitlines())
    assert "forcing" in code and "rho" in code, "_share must weight by rho*dz"


def test_the_ledger_reports_a_modelling_band(tmp_path):
    """Owner P0-4: the departing water is charged at the bottom-level temperature
    and nothing in the endpoint data says it left from there. The band recomputes
    the residual with every level in turn. On the real fixture it is 131% of the
    conservative column-2 residual, so a point value would overstate the ~10x
    comparison."""
    L = ra.enthalpy_ledger(ra.read(_stream_ledger(tmp_path, th_end="438C0000")))
    lo, hi = L[1]["relative_band"]
    assert lo <= L[1]["relative"] <= hi


def test_the_outflow_split_separates_bottom_flux_from_the_unaccounted_part(tmp_path):
    """-dW_col = P_bottom + D_internal. Conservative reads D_internal ~ 0; legacy
    reads it NEGATIVE on this fixture, i.e. the diagnostic over-reports -- the
    opposite sign from the P0-4b real-case defect."""
    p = _stream_ledger(tmp_path, name="s.txt")
    txt = p.read_text().replace("G33R STATE qr 1 0 3F800000", "G33R STATE qr 1 0 00000000")
    txt = txt.replace("G33R PREC 1 1 00000000", "G33R PREC 1 1 3F000000")   # 0.5
    r = ra.read(_write(tmp_path, txt, "s2.txt"))
    d = ra.outflow_split(r, 1, sorted({k[3] for k in r if k[0] == "state"}))
    assert d["water_out"] == pytest.approx(1.0)
    assert d["P_bottom"] == pytest.approx(0.5)
    assert d["D_internal"] == pytest.approx(0.5)     # here the column lost MORE
    assert d["D_share"] == pytest.approx(0.5)


def test_the_manifest_uses_the_STRICT_parser_for_members(tmp_path):
    """Owner §9: reading only the BEGIN line would admit a truncated or ragged
    member into the manifest — precisely what the strict reader rejects, and the
    manifest is what claims the table is reproducible."""
    d = tmp_path / "out"; d.mkdir()
    (d / "n3.rezero.txt").write_text(_stream(nsplit=3))
    lines = _stream(nsplit=6).splitlines()
    del lines[5]                                   # ragged: one state record short
    (d / "n6.rezero.txt").write_text("\n".join(lines) + "\n")
    mod = tmp_path / "m.F"; mod.write_text("x")
    fix = tmp_path / "f.f90"; fix.write_text("y")
    with pytest.raises(ra.RefineError):
        rm.build(d, module=mod, fixture=fix, compiler="gfortran-test")


def test_build_provenance_absent_is_null_not_an_empty_list(tmp_path):
    """An empty command list is indistinguishable from a build nobody recorded.
    `null` says which one it is."""
    d = tmp_path / "o"; d.mkdir()
    (d / "n3.rezero.txt").write_text(_stream(nsplit=3))
    mod = tmp_path / "m.F"; mod.write_text("x")
    fix = tmp_path / "f.f90"; fix.write_text("y")
    man = rm.build(d, module=mod, fixture=fix, compiler="c")
    assert man["build_provenance"] is None


def test_findings_are_linked_by_digest(tmp_path):
    """A finding citing a table nobody can tie to the run it came from is
    unreviewable (owner §9)."""
    d = tmp_path / "o"; d.mkdir()
    (d / "n3.rezero.txt").write_text(_stream(nsplit=3))
    mod = tmp_path / "m.F"; mod.write_text("x")
    fix = tmp_path / "f.f90"; fix.write_text("y")
    doc = tmp_path / "FINDING_x.md"; doc.write_text("# a claim\n")
    man = rm.build(d, module=mod, fixture=fix, compiler="c", findings=[doc])
    assert man["findings"] == [{"path": str(doc), "sha256": rm.sha256(doc)}]
    assert rm.build(d, module=mod, fixture=fix, compiler="c")["findings"] == []


def test_a_finding_that_is_not_there_is_loud(tmp_path):
    """Silently recording nothing would leave the manifest claiming a link it
    does not have."""
    d = tmp_path / "o"; d.mkdir()
    (d / "n3.rezero.txt").write_text(_stream(nsplit=3))
    mod = tmp_path / "m.F"; mod.write_text("x")
    fix = tmp_path / "f.f90"; fix.write_text("y")
    with pytest.raises(FileNotFoundError):
        rm.build(d, module=mod, fixture=fix, compiler="c",
                 findings=[tmp_path / "absent.md"])


# ---- owner P0-1: the order is against the step the KERNEL ran ---------------

def _member(tmp_path, nsplit, dtcld, *, delt=None, loops=1, mode="rezero",
            algo="legacy", drop_step=False):
    """One member whose BEGIN reports an explicit dtcld, read as the analyzer
    reads it (filename bound to nsplit)."""
    delt = 300.0 / nsplit if delt is None else delt
    body = _stream(nsplit=nsplit, mode=mode, algo=algo).splitlines()
    body[0] = (f"G33R BEGIN nsplit {nsplit} {mode} {algo}" if drop_step else
               f"G33R BEGIN nsplit {nsplit} {mode} {algo} delt {delt:.6f} "
               f"loops {loops} dtcld {dtcld:.6f}")
    d = tmp_path / f"m{nsplit}"
    d.mkdir(exist_ok=True)
    return ra.read(_write(d, "\n".join(body) + "\n",
                          name=f"n{nsplit}.{mode}.txt"), nsplit=nsplit)


def _runs(tmp_path, *specs, **kw):
    return {n: _member(tmp_path, n, h, **kw) for n, h in specs}


def test_the_step_comes_from_the_stream_not_the_filename(tmp_path):
    assert ra.steps(_runs(tmp_path, (3, 100.0), (6, 50.0))) == {3: 100.0, 6: 50.0}


def test_a_member_with_no_dtcld_cannot_carry_an_order(tmp_path):
    """Older streams predate the field. An order against a step nobody recorded
    is exactly the defect this exists to stop."""
    with pytest.raises(ra.RefineError, match="no dtcld"):
        ra.steps({3: _member(tmp_path, 3, 0.0, drop_step=True)})


def test_N_doubling_is_NOT_taken_as_the_step_halving(tmp_path):
    """`loops = max(nint(delt/dtcldcr),1)` (F:930) makes N = 1,2,3 run
    100, 150, 100 s. A pair whose N doubled but whose step did not halve must
    yield no order at all."""
    r = _runs(tmp_path, (2, 150.0), (4, 120.0))
    assert ra._halving_pairs(r) == []
    assert all(not v for v in ra.successive(r).values())


def test_a_real_halving_still_pairs(tmp_path):
    """The guard must not refuse the chains the sweep actually uses."""
    r = _runs(tmp_path, (3, 100.0), (6, 50.0), (12, 25.0))
    assert ra._halving_pairs(r) == [(3, 6), (6, 12)]


def test_the_same_step_twice_is_refused(tmp_path):
    """N = 1 and N = 3 both run dtcld = 100 s on the real driver."""
    with pytest.raises(ra.RefineError, match="same step twice"):
        ra.require_orderable(_runs(tmp_path, (1, 100.0), (3, 100.0)))


def test_members_that_integrate_different_totals_are_refused(tmp_path):
    r = _runs(tmp_path, (3, 100.0))
    r[6] = _member(tmp_path, 6, 50.0, delt=99.0)
    with pytest.raises(ra.RefineError, match="different total times"):
        ra.require_comparable(r)


def test_members_that_mix_modes_are_refused(tmp_path):
    r = _runs(tmp_path, (3, 100.0))
    r[6] = _member(tmp_path, 6, 50.0, mode="carry")
    with pytest.raises(ra.RefineError, match="mix modes"):
        ra.require_comparable(r)


def test_the_finest_member_is_the_smallest_STEP_not_the_largest_N(tmp_path):
    """N = 2 runs a COARSER step than N = 1, so `max(N)` is the wrong finest."""
    r = _runs(tmp_path, (2, 150.0), (1, 100.0))
    assert min(r, key=lambda n: ra.steps(r)[n]) == 1
    assert set(ra.to_finest(r)["th"]) == {150.0}


# ---- owner P0-2: the manifest must certify ONE experiment -------------------

def _bundle(tmp_path, *specs, mode="rezero"):
    d = tmp_path / "out"
    d.mkdir(exist_ok=True)
    for nsplit, dtcld in specs:
        body = _stream(nsplit=nsplit, mode=mode).splitlines()
        body[0] = (f"G33R BEGIN nsplit {nsplit} {mode} legacy "
                   f"delt {300.0/nsplit:.6f} loops 1 dtcld {dtcld:.6f}")
        (d / f"n{nsplit}.{mode}.txt").write_text("\n".join(body) + "\n")
    mod = tmp_path / "m.F"; mod.write_text("x")
    fix = tmp_path / "f.f90"; fix.write_text("y")
    return d, mod, fix


def test_the_filename_is_bound_to_the_stream(tmp_path):
    """A member called n6 whose BEGIN says nsplit 3 is a mislabelled file, and
    that is how two experiments become one table."""
    d, mod, fix = _bundle(tmp_path, (3, 100.0))
    (d / "n3.rezero.txt").rename(d / "n6.rezero.txt")
    with pytest.raises(ra.RefineError):
        rm.build(d, module=mod, fixture=fix, compiler="c")


def test_the_filename_mode_is_bound_to_the_stream(tmp_path):
    d, mod, fix = _bundle(tmp_path, (3, 100.0))
    (d / "n3.rezero.txt").rename(d / "n3.carry.txt")
    with pytest.raises(ra.RefineError, match="filename says mode"):
        rm.build(d, module=mod, fixture=fix, compiler="c")


def test_members_from_different_experiments_are_refused(tmp_path):
    """Mixed modes reach the manifest only if nothing checks across members."""
    d, mod, fix = _bundle(tmp_path, (3, 100.0))
    _bundle(tmp_path, (6, 50.0), mode="carry")
    with pytest.raises(ra.RefineError, match="mix modes"):
        rm.build(d, module=mod, fixture=fix, compiler="c")


def test_a_repeated_step_is_recorded_but_is_not_a_chain(tmp_path):
    """The N=1/N=3 policy control runs the same dtcld twice on purpose. The
    manifest must still describe it; only an ORDER over it is refused."""
    d, mod, fix = _bundle(tmp_path, (1, 100.0), (3, 100.0))
    man = rm.build(d, module=mod, fixture=fix, compiler="c")
    assert len(man["members"]) == 2 and not man["is_refinement_chain"]


def test_is_refinement_chain_orders_by_STEP_not_by_N(tmp_path):
    """Sorting the dtcld VALUES alone calls any bag of members a chain as long as
    the numbers happen to halve. N = 2 running the coarser step must not."""
    d, mod, fix = _bundle(tmp_path, (2, 100.0), (4, 50.0), (8, 25.0))
    assert rm.build(d, module=mod, fixture=fix, compiler="c")["is_refinement_chain"]
    (tmp_path / "b").mkdir()
    d2, mod2, fix2 = _bundle(tmp_path / "b", (2, 150.0), (4, 120.0))
    assert not rm.build(d2, module=mod2, fixture=fix2,
                        compiler="c")["is_refinement_chain"]


def test_provenance_from_a_different_build_is_refused(tmp_path):
    """A manifest whose provenance describes other sources documents a build
    that did not produce these members."""
    d, mod, fix = _bundle(tmp_path, (3, 100.0))
    prov = tmp_path / "bp.json"
    prov.write_text(json.dumps({"module_sha256": "deadbeef",
                                "fixture_sha256": "deadbeef"}))
    with pytest.raises(ra.RefineError, match="different build"):
        rm.build(d, module=mod, fixture=fix, compiler="c", build_provenance=prov)


# ---- owner §7.1: the parser must reject an incomplete record universe -------

def test_rho_without_delz_is_refused_at_parse_time(tmp_path):
    """It used to pass and fail later inside a column budget — by which point the
    stream had already been counted as a member."""
    lines = _stream().splitlines()
    body = [ln for ln in lines if ln != "G33R END"]
    for i in range(1, 3):
        for k in range(2):
            body.append(f"G33R FORCING rho {i} {k} 3F800000")
    with pytest.raises(ra.RefineError, match="must be present together"):
        ra.read(_write(tmp_path, "\n".join(body + ["G33R END"]) + "\n"))


def test_an_initial_state_over_different_cells_is_refused(tmp_path):
    """Counting records passes a member with the right NUMBER of wrong cells."""
    body = []
    for ln in _stream().splitlines():
        body.append(ln)
        if ln.startswith("G33R STATE"):
            f, i, k = ln.split()[2:5]
            body.append(f"G33R INITIAL {f} {int(i)+9} {k} 3F800000")
    with pytest.raises(ra.RefineError, match="different \\(field, col, k\\)"):
        ra.read(_write(tmp_path, "\n".join(body) + "\n"))


def test_a_ragged_column_is_refused(tmp_path):
    """A column short of a level silently shortens its column integral."""
    body = [ln for ln in _stream().splitlines()
            if not (ln.startswith("G33R STATE") and ln.split()[3] == "2"
                    and ln.split()[4] == "1")]
    with pytest.raises(ra.RefineError, match="different level sets"):
        ra.read(_write(tmp_path, "\n".join(body) + "\n"))


def test_prec_must_cover_exactly_the_state_columns(tmp_path):
    body = [ln for ln in _stream().splitlines()
            if not (ln.startswith("G33R PREC") and ln.split()[3] == "2")]
    with pytest.raises(ra.RefineError, match="species, column"):
        ra.read(_write(tmp_path, "\n".join(body) + "\n"))


# ---- the water orders are not convergence rates -----------------------------

def test_a_step_insensitive_column_integral_is_flagged_not_ordered():
    """Successive differences on a step-insensitive quantity describe the chain's
    own scatter. Reporting an "order" on them reads as a convergence rate."""
    b = {n: {("water", 1): 0.135243 + 1e-9 * n} for n in (3, 6, 12)}
    assert ra.cross_member_endpoint_spread(b, ("water", 1)) < ra._FLAT_SPREAD


def test_a_varying_column_integral_is_not_flagged():
    b = {n: {("water", 1): 0.12 + 0.001 * n} for n in (3, 6, 12)}
    assert ra.cross_member_endpoint_spread(b, ("water", 1)) > ra._FLAT_SPREAD


def test_spread_is_NOT_conservation(tmp_path):
    """Every member losing the SAME amount gives zero spread and a nonzero
    conservation residual. The spread cannot see it; R_W can (owner §5)."""
    b = {n: {("water", 1): 0.5} for n in (3, 6, 12)}
    assert ra.cross_member_endpoint_spread(b, ("water", 1)) == 0.0
    out = []
    for ln in _stream().splitlines():
        if ln == "G33R END":
            continue                       # re-added last: nothing may follow it
        out.append(ln)
        if ln.startswith("G33R STATE"):
            f, i, k = ln.split()[2:5]
            out.append(f"G33R INITIAL {f} {i} {k} 40000000")   # initial = 2.0
    for nm in ("rho", "delz"):
        for i in (1, 2):
            for k in range(2):
                out.append(f"G33R FORCING {nm} {i} {k} 3F800000")
    out.append("G33R END")
    r = ra.read(_write(tmp_path, "\n".join(out) + "\n"))
    d = ra.water_residual(r, 1)
    assert d["W_final"] < d["W_initial"], "the column lost water"
    assert d["residual"] != 0.0, "a real loss must show in R_W"


def test_the_water_caveat_is_generic_and_names_how_to_decide(tmp_path):
    """It must state the PRECONDITION for reading these numbers, not one
    fixture's answer — a future stream would otherwise be told its variation is
    precision drift on evidence that never touched it (owner §7.1)."""
    src = (ROOT / "g33_refine_analyze.py").read_text()
    assert "WATER ORDERS ARE A RATE ONLY IF THE VARIATION IS PHYSICAL" in src
    assert "--f64" in src, "it must say how to decide"
    assert "Do not carry that" in src, "it must scope the fixture's answer"


def test_a_bundle_with_two_members_at_one_nsplit_is_refused(tmp_path):
    """n3.rezero beside n3.carry collapsed to one entry, so the mode check ran on
    whichever survived (owner §7.3)."""
    d, mod, fix = _bundle(tmp_path, (3, 100.0))
    _bundle(tmp_path, (3, 100.0), mode="carry")
    with pytest.raises(ra.RefineError, match="more than one member for nsplit"):
        rm.build(d, module=mod, fixture=fix, compiler="c")
