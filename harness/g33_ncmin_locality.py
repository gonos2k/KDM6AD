#!/usr/bin/env python3
"""What the scalar `ncmin` costs, measured rather than counted.

`ncmin` is assigned inside the column loop and survives it holding the LAST
column's threshold (`ncmin_land` or `ncmin_sea` by that column's `xland`). A
column-local operator must give the same answer for every tile decomposition;
this one does not, so the answer depends on where a tile or MPI boundary falls.

`FINDING_ncmin_scalar_vs_percell.md` reported "31 / 144 cells differ" and called
it "a whole-state difference, not a rounding one". That was a COUNT and an
assertion. A count cannot tell a roundoff-scale difference from a dominating
one -- the same conflation owner §10 named for the cap-bound interfaces -- so
this reports the SIZE beside it.

Exhaustive over the CONTIGUOUS PARTITIONS of the domain, not just even splits:
`(1, 2)` differs in zero cells because both tiles end on land, so a gate that
only tried even splits would pass while the operator was arbitrarily non-local.

    python g33_ncmin_locality.py <driver> <fixture-name>
"""
from __future__ import annotations

import math
import re
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import g33_number_transport as nt  # noqa: E402
import g33_refine_analyze as ra  # noqa: E402
from g33_refine_experiment import fixture_dims  # noqa: E402

#: The condensate species, and the vapour that feeds them.
CONDENSATE = ("qc", "qr", "qi", "qs", "qg")

#: f32 machine epsilon. The scale a "rounding difference" would live at.
F32_EPS = 2.0 ** -23


def compositions(n: int) -> list[tuple]:
    """Every ordered way to split `n` columns into contiguous tiles."""
    if n == 0:
        return [()]
    return [(first,) + rest
            for first in range(1, n + 1)
            for rest in compositions(n - first)]


def read_records(text: str, *, label: str, nsplit: int = 1) -> dict:
    """{(cls, name, col, k): raw hex} for every G33R record.

    ONLY from a stream the strict parser took. The first version parsed the
    lines itself and accepted anything: a driver emitting NOTHING gave an empty
    dict, every partition then showed zero differing components, and the report
    printed "identical gating" -- a completely broken run reading as the
    strongest possible pass. Validating through `ra.read_text` brings the checks
    that already exist (exactly one BEGIN and END, the full field set, a
    non-ragged grid, no duplicate records, no non-finite value).

    The hex is taken raw afterwards, because the comparison is about the BITS
    the operator produced and 0.0 == -0.0 would hide a sign flip.
    """
    ra.read_text(text, nsplit=nsplit, label=label)
    out = {}
    for p in (ln.split() for ln in text.splitlines()):
        if p[:1] != ["G33R"]:
            continue
        if p[1] in ("STATE", "INITIAL", "FORCING"):
            out[(p[1].lower(), p[2], int(p[3]), int(p[4]))] = p[5]
        elif p[1] == "PREC":
            out[("prec", p[2], int(p[3]), None)] = p[4]
    if not out:
        raise ra.RefineError(f"{label}: no G33R records")
    return out


def read_state(text: str, *, label: str, nsplit: int = 1) -> dict:
    """{(field, col, k): raw hex} -- the final state only."""
    return {k[1:]: v
            for k, v in read_records(text, label=label, nsplit=nsplit).items()
            if k[0] == "state"}


def _expect_same_inputs(base: dict, got: dict, label: str) -> None:
    """Baseline and partition must have run the SAME atmosphere.

    Without this the analysis attributes every difference to `ncmin` while
    having checked only that the two runs cover the same cell universe. A
    partition driver that transposed the column mapping would satisfy the
    universe check, produce large differences, and be read as a strong `ncmin`
    effect -- and "a large difference is suspicious" cannot separate the two,
    because a large difference is exactly what this tool reports (owner P0-S1).

    Compared RAW-BIT: the twelve INITIAL prognostics and the rho/delz/pii
    forcing, every cell. Not the final STATE -- that is the measurement.
    """
    for cls in ("initial", "forcing"):
        a = {k: v for k, v in base.items() if k[0] == cls}
        b = {k: v for k, v in got.items() if k[0] == cls}
        if not a or not b:
            # `G33R INITIAL` is OPTIONAL to the strict parser, so two streams
            # that both lack it made this comparison pass with nothing compared
            # -- the same-atmosphere guarantee evaporating exactly where it
            # could not be checked (Codex).
            raise ra.RefineError(
                f"{label}: no `{cls}` records, so the same-atmosphere contract "
                f"would be vacuous. This analysis needs them.")
        if set(a) != set(b):
            raise ra.RefineError(
                f"{label}: the {cls} universe differs from the baseline by "
                f"{len(set(a) ^ set(b))} records")
        bad = [k for k in a if a[k] != b[k]]
        if bad:
            raise ra.RefineError(
                f"{label}: {len(bad)} {cls} records differ from the baseline "
                f"(e.g. {bad[0]}: {a[bad[0]]} vs {b[bad[0]]}) -- the two runs "
                f"did not receive the same atmosphere, so a difference in the "
                f"final state cannot be attributed to ncmin")


#: Independent trajectories the same-atmosphere control is replicated over:
#: every density profile the driver offers, both aux-carry arms, three
#: sub-step counts. One confirming pair is an anecdote; the attribution rests
#: on this holding wherever the operator is exercised.
RHO_MODES = ("as-is", "uniform", "inverted", "x2", "offset+", "offset-")
TRAJECTORIES = tuple((nsplit, carry, rho)
                     for rho in RHO_MODES
                     for carry in ("rezero", "carry")
                     for nsplit in (1, 3, 12))


def run(driver: str, tiles, nsplit: int = 1, carry: str = "rezero",
        rho: str = "as-is") -> str:
    """The driver's stdout for one decomposition on one trajectory."""
    r = subprocess.run([driver, str(nsplit), carry,
                        ",".join(map(str, tiles)), rho],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"driver exited {r.returncode}\n{r.stderr[-2000:]}")
    return r.stdout


def gated_state(driver: str, fixture: str, tiles, reference=None,
                nsplit: int = 1, carry: str = "rezero",
                rho: str = "as-is") -> tuple:
    """One decomposition's final state, through EVERY gate, once.

    The single runner `local_oracle`, `class_law` and `control_replication`
    share. The 36-trajectory control originally called `read_state(run(...))`
    directly, applying none of them: no tile-liveness, no same-atmosphere
    contract, no cell-universe check. A driver that mapped columns differently
    per tile class, or dropped a column on one arm, could produce
    within-class-identical and across-class-different and pass the attribution
    control -- the weaker-reader-beside-the-strict-one defect this repo keeps
    finding (owner P0-2).

    Returns (state, records) so a caller can use the records as the reference
    for the rest of its legs.
    """
    label = f"{','.join(map(str, tiles))}/{nsplit}/{carry}/{rho}"
    text = run(driver, tiles, nsplit, carry, rho)
    _expect_tiles_are_live(text, tiles, label, nsplit)
    rec = read_records(text, label=label, nsplit=nsplit)
    if reference is not None:
        _expect_same_inputs(reference, rec, label)
    state = {k[1:]: v for k, v in rec.items() if k[0] == "state"}
    _expect_universe(state, *fixture_dims(fixture), label)
    return state, rec


def control_replication(driver: str, fixture: str) -> dict:
    """The attribution control, run on every trajectory rather than one.

    WITHIN a threshold class the decomposition genuinely changes -- `(1,2)` is
    two kernel calls over (1,1) and (2,3), `(3,)` is one over (1,3) -- and the
    answer must not. ACROSS classes it must. Both directions are needed: 36
    identical results would otherwise be consistent with trajectories that are
    insensitive to everything, which would make the control vacuous rather than
    strong.
    """
    cls = equivalence_classes(fixture)
    within = next((ms for ms in cls.values() if len(ms) > 1), None)
    if within is None:
        raise ra.RefineError(
            f"{fixture}: no two decompositions share a threshold vector, so the "
            f"same-atmosphere control cannot be formed on this fixture")
    keys = list(cls)
    if len(keys) < 2:
        # BOTH halves are required. Treating a missing across-class pair as
        # satisfied made `holds` True with ZERO across-class checks, and the
        # report then printed "differs in 0/36 -- both directions" (Codex): a
        # guarantee evaporating exactly where it could not be checked, the same
        # shape as the vacuous same-atmosphere contract.
        raise ra.RefineError(
            f"{fixture}: every decomposition shares one threshold vector, so "
            f"there is no across-class pair and the control has only one "
            f"direction. A one-directional result cannot separate `the gate is "
            f"what matters` from `these trajectories are insensitive to "
            f"everything`")
    across = (cls[keys[0]][0], cls[keys[1]][0])

    same, differ = [], []
    for nsplit, carry, rho in TRAJECTORIES:
        # The reference for THIS trajectory: same nsplit/carry/rho, so the
        # same-atmosphere contract compares runs that should share an
        # atmosphere. Comparing across trajectories would refuse correctly but
        # for the wrong reason -- a different rho profile IS a different
        # atmosphere.
        ref = None
        states = {}
        for tiles in (within[0], within[1], across[0], across[1]):
            if tiles in states:
                continue
            states[tiles], rec = gated_state(driver, fixture, tiles, ref,
                                             nsplit, carry, rho)
            ref = ref or rec
        leg = (nsplit, carry, rho)
        if states[within[0]] == states[within[1]]:
            same.append(leg)
        if states[across[0]] != states[across[1]]:
            differ.append(leg)
    return {"within_pair": within[:2], "across_pair": across,
            "trajectories": len(TRAJECTORIES),
            "within_identical": len(same), "across_differing": len(differ),
            "holds": (len(same) == len(TRAJECTORIES)
                      and len(differ) == len(TRAJECTORIES))}


def tile_brackets(text: str) -> list:
    """The (i0, i1) column bounds each kernel call ACTUALLY received.

    `G33N CALL_BEGIN` is written from INSIDE the tile loop, carrying the very
    bounds handed to `kdm62D` on the next statement. Needs an `--nflux` build,
    whose STATE records are byte-identical to the plain one on this fixture.

    Read through the STRICT G33N parser, not by scanning for the token. The
    scan trusted a substring: a valid G33R block plus two forged CALL_BEGIN
    lines -- no STREAM_BEGIN, no STREAM_END, no CALL_END, no records at all --
    produced exactly the brackets asked for and passed the liveness gate, while
    `nt.calls()` rejects that stream on its first record (owner P0-E1). A
    load-bearing gate must not be the one place a weaker reader is used.
    """
    return [c["cols"] for c in nt.calls(text)]


def _expect_tiles_are_live(text: str, tiles, label: str,
                           nsplit: int = 1) -> None:
    """The kernel must have been called over the decomposition we ASKED for.

    The previous version ran an INVALID spec and required a refusal. That only
    proves the argument is parsed and validated -- and validation lives in the
    argument parser while use lives in the tile loop, so a driver that validated
    the spec and then called the kernel over the whole domain passed it
    (Codex). Every partition would then equal the baseline and the tool would
    report zero differences everywhere: "the operator is column-local", the
    strongest possible pass and the exact claim it exists to refute.

    This reads the bounds the kernel was given, so validating-and-ignoring is
    caught where being-refused never was.
    """
    one, i = [], 0
    for t in tiles:
        one.append((i + 1, i + t))
        i += t
    # The kernel is called over the decomposition ONCE PER SUB-STEP, so the
    # bracket sequence is the tile pattern repeated `nsplit` times. The gate
    # assumed nsplit=1 and only ever ran there; requiring the exact repetition
    # count rather than relaxing to "contains" makes it check the SUB-STEP
    # count too -- a run that silently did fewer sub-steps now fails here.
    want = one * nsplit
    got = tile_brackets(text)
    if not got:
        raise ra.RefineError(
            f"{label}: no G33N CALL_BEGIN records -- this needs an --nflux "
            f"build, without which nothing says which decomposition ran")
    if got != want:
        raise ra.RefineError(
            f"{label}: the kernel was called over {got}, not the requested "
            f"{one} x {nsplit} sub-steps -- the tile argument is not reaching "
            f"the partitioning, or the sub-step count is not what was asked")


def _f32(h: str) -> float:
    return struct.unpack(">f", bytes.fromhex(h))[0]


def _ordered(h: str) -> int:
    """The f32 bits mapped to a MONOTONIC integer.

    A raw signed-int32 difference is the representable-step distance only for
    same-sign positives: it is wrong across zero, and makes +0.0 and -0.0 look
    2^31 apart (owner §11.4). Flipping the sign bit for positives and inverting
    negatives gives an ordering in which adjacent floats are adjacent integers.
    """
    u = struct.unpack(">I", bytes.fromhex(h))[0]
    return (0xFFFFFFFF - u) if u & 0x80000000 else (u | 0x80000000)


def _ulps(a: str, b: str) -> int:
    """Distance in representable f32 steps -- the unit a rounding claim is in."""
    return abs(_ordered(a) - _ordered(b))


def fixture_xland(fixture: str) -> dict:
    """{column: 1.0 land | 2.0 sea} declared by the fixture source.

    The mechanism depends on the surface type at each tile's LAST column, and
    the stream carries no `xland`. Reading it from the fixture keeps the
    prediction checkable without widening the protocol (owner P0-S1).
    """
    src = (Path(__file__).resolve().parent / "g33_fortran"
           / f"{fixture}.f90").read_text()
    m = re.search(r"XLAND_BITS\(B\)\s*=\s*\[(.*?)\]", src, re.S)
    if not m:
        raise SystemExit(f"cannot read XLAND_BITS from {fixture}.f90")
    bits = re.findall(r"z'([0-9A-Fa-f]{8})'", m.group(1))
    return {i: struct.unpack(">f", bytes.fromhex(b))[0]
            for i, b in enumerate(bits, start=1)}


def fixture_ncmin(fixture: str) -> tuple:
    """(ncmin_land, ncmin_sea) declared by the fixture source."""
    src = (Path(__file__).resolve().parent / "g33_fortran"
           / f"{fixture}.f90").read_text()
    out = []
    for name in ("NCMIN_LAND_BITS", "NCMIN_SEA_BITS"):
        m = re.search(name + r"\s*=\s*int\(z'([0-9A-Fa-f]{8})'", src)
        if not m:
            raise SystemExit(f"cannot read {name} from {fixture}.f90")
        out.append(struct.unpack(">f", bytes.fromhex(m.group(1)))[0])
    return tuple(out)


def threshold_can_matter(run: dict, col: int, ncmin: tuple) -> bool:
    """Can the two candidate `ncmin` values produce different behaviour here?

    `ncmin` is used BOTH as a gate -- `nci(i,k,1) .le./.gt./.ge. ncmin` at many
    sites -- and as a FLOOR, `value = max(ncmin, nci(i,k,*))` (F:2736, 2750,
    2888). The two candidates agree only where the number exceeds BOTH: then
    every comparison lands the same way and neither floor binds. So the choice
    can matter iff `n <= max(ncmin_land, ncmin_sea)` for either number moment.

    Without this the prediction says a differing tile-end surface type forces
    every column in the tile to differ, which is only true where the gate is
    ACTIVE (owner §7.2). On `boundary_mapping_v1` nc runs 4.0e+07..5.0e+07
    against thresholds 2.5e+07 and 1.0e+08, so it is active in every cell -- and
    that is WHY the column prediction is exact here, not a general property.
    """
    # `run` carries 3-tuple `prec` and `meta` keys alongside the 4-tuple state
    # ones, so the shape is checked before unpacking rather than after it raises.
    hi = max(ncmin)
    ks = {key[3] for key in run
          if len(key) == 4 and key[0] == "initial" and key[2] == col}
    return any(run[("initial", f, col, k)] <= hi
               for k in ks for f in ("nc", "ni"))


def predicted_columns(tiles, xland: dict, width: int, active=None) -> set:
    """Which columns the MECHANISM says must differ from the whole-domain run.

    `ncmin` survives the column loop holding the LAST column's threshold, so
    every column in a tile is gated on that tile's final `xland`. The baseline
    is one tile ending at `width`. A column differs exactly when its tile's
    ending surface type differs from the baseline's.

    This is a far stronger causal statement than magnitude: it names the
    columns in advance. "A large difference is suspicious" cannot attribute
    anything, because a large difference is what the tool reports (owner P0-S1).
    """
    baseline_gate = xland[width]
    out, first = set(), 1
    for t in tiles:
        last = first + t - 1
        if xland[last] != baseline_gate:
            # A differing threshold only changes the answer where the gate is
            # ACTIVE. `active` names the columns where it can be; None means
            # "not evaluated", which keeps the older callers honest by leaving
            # the prediction as the upper bound it always was.
            block = set(range(first, last + 1))
            out |= block if active is None else block & active
        first = last + 1
    return out


def _expect_universe(got: dict, cols: int, levels: int, label: str) -> None:
    """The run must cover the domain the FIXTURE declares.

    Comparing a partition against the baseline only asks whether they agree with
    each other, and a run that drops a column agrees with itself perfectly: with
    column 3 gone everywhere, the tool reported `31/96` and a shrunken
    denominator as a normal result. Had the SEA column gone instead, it would
    have reported zero differences and concluded the operator is column-local --
    the claim it exists to refute. Only a figure from outside the run can catch
    that, so this one comes from the fixture source.
    """
    # The emitter writes `emit_fld(name, i, KM-k, ...)` over `i = 1..IM`,
    # `k = 1..KM`, so the protocol's indices are columns 1..B and levels 0..K-1.
    # Both are checked as SETS. Levels were checked by COUNT alone, which
    # admitted an axis shifted off its origin -- `{10,11,12,13}` has four
    # entries too (owner/Codex).
    #
    # What a universe check CANNOT see, enumerated so the boundary is stated
    # once rather than discovered one axis at a time: a REVERSED level axis and
    # a TRANSPOSED column mapping are both the same SET. They are ordering
    # properties, not universe ones. Neither passes silently -- either applied
    # to one run and not the other makes most cells differ, so they surface as
    # an implausibly large result rather than a clean one, which is the
    # opposite of the failure mode this gate exists for.
    want_cols, want_k = set(range(1, cols + 1)), set(range(levels))
    have_cols = {k[1] for k in got}
    have_k = {k[2] for k in got}
    if have_cols != want_cols:
        raise ra.RefineError(
            f"{label}: columns {sorted(have_cols)}, fixture declares "
            f"{sorted(want_cols)}")
    if have_k != want_k:
        raise ra.RefineError(
            f"{label}: levels {sorted(have_k)}, fixture declares "
            f"{sorted(want_k)}")
    want = len(ra.STATE_FIELDS) * cols * levels
    if len(got) != want:
        raise ra.RefineError(f"{label}: {len(got)} STATE records, expected {want}")


def humidity_weight_spread(text: str) -> dict:
    """{col: max a_k - min a_k} where a_k = 1/(1+qv(t0)) -- the physical weight.

    The two bases give the same RELATIVE difference only when this weight is
    vertically uniform, because `a_k` sits INSIDE the column sum:

        r_d = |sum_k a_k w_k dq_k| / |sum_k a_k w_k q_k|

    A common factor cancels; a level-dependent one does not. The finding claimed
    the equality followed necessarily from both runs sharing `qv(t0)`, which is
    false in general (owner §9.2). On `boundary_mapping_v1` the spread is
    EXACTLY zero -- qv is vertically constant per column -- so the agreement is
    a property of this fixture, measured here rather than assumed.
    """
    run = ra.read_text(text, nsplit=1)
    out = {}
    for key in run:
        if len(key) == 4 and key[0] == "initial" and key[1] == "qv":
            out.setdefault(key[2], []).append(1.0 / (1.0 + run[key]))
    return {c: max(v) - min(v) for c, v in out.items()}


def column_integrated(base_text: str, got_text: str, basis: str = "operator") -> dict:
    """{(col, field): (baseline, partition, abs, rel)} under the rho*dz measure.

    A per-component RELATIVE difference near 1 says the two runs disagree about
    a value, not that the value is large: `qi` reaches 0.997 on a baseline of
    6.6e-08 kg/kg, an absolute difference of 1.9e-05. Only a column integral
    says whether the disagreement carries mass (owner §11.3).
    """
    a, b = (ra.read_text(t, nsplit=1) for t in (base_text, got_text))
    cells = {(k[2], k[3]) for k in a if k[0] == "state"}
    out = {}
    for col in sorted({c for c, _ in cells}):
        ks = sorted(k for c, k in cells if c == col)

        def col_mass(run, fields):
            # DUAL BASIS (owner §7.1). rho_m*dz is the OPERATOR integral -- what
            # the kernel budgets. The mixing ratios are per DRY-air kg, so the
            # physical column mass is rho_d*dz with rho_d from the WINDOW-INITIAL
            # qv. Calling the operator result "the only physical form", as the
            # first version did, contradicts this repository's own basis
            # findings.
            def w(k):
                m = run[("forcing", "rho", col, k)] * run[("forcing", "delz", col, k)]
                if basis != "physical":
                    return m
                key = ("initial", "qv", col, k)
                if key not in run:
                    raise ra.RefineError(
                        "the physical basis needs the WINDOW-INITIAL qv from "
                        "G33R INITIAL, which this stream does not carry")
                return m / (1.0 + run[key])
            return sum(w(k) * sum(run[("state", f, col, k)] for f in fields)
                       for k in ks)

        for name, fields in ([(f, (f,)) for f in CONDENSATE]
                             + [("total_condensate", CONDENSATE)]):
            x, y = col_mass(a, fields), col_mass(b, fields)
            if x != y:
                # SIGNED as well as absolute (owner §9.4). The finding says the
                # single-tile run has "+20.72% more" rain than the oracle, but a
                # test on |rel| passes just as well if a future change makes it
                # 20.72% LESS. Direction has to be in the artifact to be
                # protected by one.
                out[(col, name)] = (x, y, abs(y - x),
                                    abs(y - x) / max(abs(x), 1e-30),
                                    y - x, (y - x) / x if x else None)
    return out


def analysis(driver: str, fixture: str) -> dict:
    """Every contiguous partition against the whole domain as one tile.

    Raw hex compared, not parsed floats: the question is whether the operator
    produced the same bits, and a float round-trip is the wrong instrument.
    """
    width, levels = fixture_dims(fixture)
    xland = fixture_xland(fixture)
    ncmin = fixture_ncmin(fixture)
    base_text = run(driver, (width,))
    _expect_tiles_are_live(base_text, (width,), "baseline")
    base_rec = read_records(base_text, label="baseline")
    base = {k[1:]: v for k, v in base_rec.items() if k[0] == "state"}
    _expect_universe(base, width, levels, "baseline")
    base_run = ra.read_text(base_text, nsplit=1)
    active = {c for c in range(1, width + 1)
              if threshold_can_matter(base_run, c, ncmin)}
    rows = {}
    for tiles in compositions(width):
        if tiles == (width,):
            continue
        got_text = run(driver, tiles)
        label = f"tiles={','.join(map(str, tiles))}"
        _expect_tiles_are_live(got_text, tiles, label)
        got_rec = read_records(got_text, label=label)
        _expect_same_inputs(base_rec, got_rec, label)
        got = {k[1:]: v for k, v in got_rec.items() if k[0] == "state"}
        _expect_universe(got, width, levels, label)
        # The universes must be the SAME cells, or "how many differ" is counted
        # over whatever both happened to carry -- and a short baseline reports
        # FEWER differences, which is the flattering direction.
        if set(got) != set(base):
            raise ra.RefineError(
                f"tiles={tiles}: {len(set(got) ^ set(base))} cells are not in "
                f"both this partition and the whole-domain baseline")
        predicted = predicted_columns(tiles, xland, width, active)
        diff = {k: (base[k], got[k]) for k in base if base[k] != got[k]}
        fields = {}
        for (f, _c, _k), (a, b) in diff.items():
            fa, fb = _f32(a), _f32(b)
            rel = abs(fb - fa) / max(abs(fa), abs(fb), 1e-30)
            d = fields.setdefault(f, {"components": 0, "max_rel": 0.0,
                                      "max_ulps": 0, "max_abs": 0.0,
                                      "max_abs_baseline": 0.0})
            d["components"] += 1
            d["max_rel"] = max(d["max_rel"], rel)
            d["max_ulps"] = max(d["max_ulps"], _ulps(a, b))
            # ABSOLUTE too (owner §11.3). A relative difference near 1 says the
            # two runs disagree about the value, not that the value is large: a
            # tiny baseline gives ~100% for a negligible mass. Both are needed
            # before "cloud ice differs by O(1)" can mean anything physical, and
            # the baseline magnitude says which regime it is.
            if abs(fb - fa) > d["max_abs"]:
                d["max_abs"] = abs(fb - fa)
                d["max_abs_baseline"] = abs(fa)
        rows[",".join(map(str, tiles))] = {
            "components_differing": len(diff),
            "components_total": len(base),
            # 144 = 12 fields x 3 columns x 4 levels. The grid has
            # 12 CELLS; 144 is the number of prognostic state
            # COMPONENTS, and calling them cells overstated the
            # spatial extent by a factor of twelve (owner §11.1).
            "grid_cells": len({(k[1], k[2]) for k in base}),
            "columns": sorted({k[1] for k in diff}),
            # The judgement the finding asserted, now derived: is the largest
            # difference at the scale arithmetic noise lives at, or far above it?
            "max_rel": max((d["max_rel"] for d in fields.values()), default=0.0),
            "is_roundoff_scale": all(d["max_rel"] <= 16 * F32_EPS
                                     for d in fields.values()),
            "predicted_columns": sorted(predicted),
            "prediction_holds": sorted({k[1] for k in diff}) == sorted(predicted),
            "by_field": fields,
            # What the disagreement is worth once integrated over the column --
            # the only form in which "cloud ice differs" is a physical
            # statement rather than a per-component ratio (owner §11.3).
            "column_integrated": {
                b: {f"{c}/{f}": {"baseline": x, "partition": y, "abs": ad,
                                 "rel": rd, "signed_abs": sa, "signed_rel": sr}
                    for (c, f), (x, y, ad, rd, sa, sr)
                    in column_integrated(base_text, got_text, b).items()}
                for b in ("operator", "physical")},
            # The measurement stands on its own; the CAUSAL attribution is a
            # separate verdict. `prediction_holds: false` used to be recorded
            # and returned as an ordinary result (owner §7.3).
            "measurement_valid": True,
            "causal_attribution_valid": bool(
                sorted({k[1] for k in diff}) == sorted(predicted)),
        }
    return {"f32_eps": F32_EPS, "partitions": rows}


def local_oracle(driver: str, fixture: str) -> dict:
    """Every decomposition against the PER-COLUMN answer, not against each other.

    Running each column as its own tile makes `ncmin` that column's own
    threshold, so `(1,)*B` IS the direct sum the corrected operator would have
    to reproduce:

        M_local(X) = (+)_i M_i(X_i; xland_i)

    and it needs no change to the kernel -- the oracle is a decomposition, not a
    variant. That matters for what the numbers mean: the whole-domain run is
    what production does, and measuring it against the local answer says how far
    the shipped configuration is from column-locality, where measuring
    partitions against each other only says they disagree.

    The identification rests on the operator being otherwise column-local, which
    the `(1,2)` row shows: it differs from the whole domain in ZERO components
    even though the decomposition changed, so nothing but the `ncmin` gate
    responds to tiling here.
    """
    width, levels = fixture_dims(fixture)
    ones = (1,) * width
    ref, ref_rec = gated_state(driver, fixture, ones)
    ref_text = run(driver, ones)

    rows = {}
    for tiles in compositions(width):
        label = ",".join(map(str, tiles))
        got, _ = gated_state(driver, fixture, tiles, ref_rec)
        text = run(driver, tiles)
        diff = [k for k in ref if ref[k] != got[k]]
        rows[label] = {
            "is_the_oracle": tiles == ones,
            "components_differing": len(diff),
            "components_total": len(ref),
            "columns": sorted({k[1] for k in diff}),
            "column_integrated": {
                b: {f"{c}/{f}": {"baseline": x, "partition": y, "abs": ad,
                                 "rel": rd, "signed_abs": sa, "signed_rel": sr}
                    for (c, f), (x, y, ad, rd, sa, sr)
                    in column_integrated(ref_text, text, b).items()}
                for b in ("operator", "physical")},
        }
    return {"oracle": ",".join(map(str, ones)), "partitions": rows}


def imposed_threshold(tiles, fixture: str, col: int):
    """(imposed ncmin, the column's OWN ncmin) under this decomposition."""
    land, sea = fixture_ncmin(fixture)
    xland = fixture_xland(fixture)
    by_type = {1.0: land, 2.0: sea}
    if set(xland.values()) - set(by_type):
        raise ra.RefineError(
            f"fixture carries xland values {sorted(set(xland.values()))}, and "
            f"only land=1.0 / sea=2.0 have a known ncmin")
    first = 1
    for size in tiles:
        last = first + size - 1
        if first <= col <= last:
            return by_type[xland[last]], by_type[xland[col]]
        first = last + 1
    raise ValueError(f"column {col} is outside {tiles}")


def mechanism_for(tiles, fixture: str, col: int) -> str:
    """Why THIS partition moves THIS column, derived from the thresholds.

    Two versions were wrong before this one. The first hardcoded "a tile ending
    on land gates a sea column at the HIGHER floor, which suppresses
    autoconversion" -- true only while `ncmin_land > ncmin_sea`. The second
    derived that, but printed it ONCE, under a table carrying both signs: a
    reader applying the whole-domain explanation to the `+20.67%` row got the
    opposite mechanism, because there the affected column is gated at the LOWER
    threshold instead (Codex). The explanation belongs to the row.
    """
    imposed, own = imposed_threshold(tiles, fixture, col)
    if imposed == own:
        # This function is called ONLY for columns the run measured as moving.
        # Printing "unaffected" there would put a derived explanation in direct
        # contradiction with the table above it -- the same failure as the two
        # rounds before: an explanation that cannot be checked against what was
        # measured. `ncmin` is not the only way a column could move, so the
        # honest output is a refusal to explain, not a wrong explanation.
        raise ra.RefineError(
            f"col {col} moved under {tiles}, but it is gated at its own "
            f"{own:.3g} -- the `ncmin` mechanism does not explain this column")
    higher = imposed > own
    return (f"col {col}: gated at {imposed:.3g}, not its own {own:.3g} -- a "
            f"{'HIGHER' if higher else 'LOWER'} droplet floor, so "
            f"{'suppressed' if higher else 'freer'} autoconversion and "
            f"{'LESS' if higher else 'MORE'} rain")


F64_EPS = sys.float_info.epsilon


def agreement_digits(oracle: dict, gap: float) -> float:
    """Significant digits to which the two bases agree.

    `scale` is over BOTH bases. Taking it from the operator basis alone let the
    worst disagreement available certify as perfect agreement: where the
    operator recorded no departure and the physical basis recorded 20.7%, `gap`
    was 0.2072, `scale` was 0.0, and the division was skipped for `inf` -- the
    guard reporting INFINITE-digit agreement on a total mismatch (Codex).
    """
    scale = max((v["rel"] for r in oracle["partitions"].values()
                 for b in r["column_integrated"].values() for v in b.values()),
                default=0.0)
    if gap and not scale:
        raise ra.RefineError(
            f"the bases differ by {gap:.3e} while no departure was recorded in "
            f"either -- the residual and the figures it is measured against "
            f"disagree about whether anything happened")
    # `inf` means EXACTLY equal, and nothing else.
    return float("inf") if gap == 0.0 else -math.log10(gap / scale)


def gate_activity(text: str, fixture: str, tiles=None) -> dict:
    """How often the `ncmin` gate can BIND, per column, on this atmosphere.

    Without it a null result reads as evidence when it may only be evidence of
    an inert gate: `multisubcycle_v1` sets ncmin = 10 against nc ~ 1e8, so the
    gate binds in 0 of 12 cells, and showing no tiling dependence there says
    little about the boundary fixture's regime (Codex).

    TWO thresholds, because they are different questions and the first version
    reported only one under a name that read as the other (owner §6):

      local    each column's OWN threshold -- the per-column oracle's gate,
               what a corrected operator would apply
      imposed  the scalar the run ACTUALLY used, from its tile's last column

    On the whole-domain run of `boundary_mapping_v1` these differ: local binds
    8/12, imposed 12/12, because the sea column is gated at the land threshold.
    Reporting 8/12 alone described the oracle, not the run.
    """
    rec = read_records(text, label="gate-activity")
    land, sea = fixture_ncmin(fixture)
    xland = fixture_xland(fixture)
    width = fixture_dims(fixture)[0]
    tiles = tiles or (width,)
    out = {}
    for col in range(1, width + 1):
        local = land if xland[col] == 1.0 else sea
        imposed = imposed_threshold(tiles, fixture, col)[0]
        vals = [_f32(v) for k, v in rec.items()
                if k[0] == "initial" and k[1] == "nc" and k[2] == col]
        out[col] = {"cells": len(vals),
                    "local_threshold": local, "imposed_threshold": imposed,
                    "local_binding": sum(1 for v in vals if v <= local),
                    "imposed_binding": sum(1 for v in vals if v <= imposed)}
    return out


def _f32(hexword: str) -> float:
    return struct.unpack(">f", bytes.fromhex(hexword))[0]


def threshold_vector(tiles, fixture: str) -> tuple:
    """The ncmin each column is GATED AT under this decomposition.

    From the reference source, not inferred. `ncmin` is declared a plain local
    (`real :: ncmin`, F:812) -- not SAVE, not module-level -- so it cannot
    outlive one `kdm62D` call, and the loop that sets it (F:876-883) has no body
    but the assignment, so its only effect is that `slmsk(ite)` wins. The
    non-locality is therefore scoped to ONE call and determined solely by the
    surface type at that call's LAST column.
    """
    return tuple(imposed_threshold(tiles, fixture, c)[0]
                 for c in range(1, fixture_dims(fixture)[0] + 1))


def equivalence_classes(fixture: str) -> dict:
    """{threshold vector: [decompositions that produce it]}.

    If the mechanism really is `slmsk(ite)`-only, this partitions the whole
    decomposition space: same vector => same answer, bit for bit.
    """
    out = {}
    for tiles in compositions(fixture_dims(fixture)[0]):
        out.setdefault(threshold_vector(tiles, fixture), []).append(tiles)
    return out


def class_law(driver: str, fixture: str) -> dict:
    """Test that prediction: byte-identity WITHIN a class, difference ACROSS.

    This is what licenses reading a synthetic result as a statement about real
    decompositions. It turns "tiling changes the answer" into "the answer is a
    function of the imposed-threshold vector" -- so what a real MPI run would
    show reduces to WHICH vectors its patch layout produces, a geometric
    question about the decomposition rather than a physics campaign.
    """
    cls = equivalence_classes(fixture)
    width, levels = fixture_dims(fixture)
    ones = (1,) * width

    # THE SAME GATES `local_oracle` applies. Reading the streams directly
    # skipped every one of them, so a driver that validated the tile spec and
    # then ran the whole domain would make every partition identical -- and
    # this check reads identity as the law HOLDING. The strongest possible
    # confirmation, produced by a completely broken run (Codex).
    _ref_state, ref_rec = gated_state(driver, fixture, ones)
    state = {}
    for tiles in compositions(width):
        state[tiles], _ = gated_state(driver, fixture, tiles, ref_rec)

    within = [{"a": a, "b": b, "identical": state[a] == state[b]}
              for members in cls.values() for a in members[:1]
              for b in members[1:]]
    keys = list(cls)
    across = [{"a": cls[keys[i]][0], "b": cls[keys[j]][0],
               "differing": sum(1 for k in state[cls[keys[i]][0]]
                                if state[cls[keys[i]][0]][k]
                                != state[cls[keys[j]][0]][k])}
              for i in range(len(keys)) for j in range(i + 1, len(keys))]
    return {"classes": {",".join(f"{v:.3g}" for v in vec): [list(m) for m in ms]
                        for vec, ms in cls.items()},
            "within": within, "across": across,
            "within_pairs": len(within),
            # COMPUTED, so the report cannot announce a verdict the data does
            # not support. It printed "Held on every pair" unconditionally,
            # directly under rows reading `byte-identical = False` (Codex).
            "holds": (all(w["identical"] for w in within)
                      and all(x["differing"] > 0 for x in across))}


def weight_is_uniform(base_text: str) -> bool:
    """Is a_k = 1/(1+qv(t0)) vertically CONSTANT in every column? Exactly.

    This is the whole question, and it is exact -- no tolerance enters. a_k sits
    INSIDE the column sum, so a per-column constant cancels from a per-column
    RELATIVE figure algebraically, and a level-dependent one does not.
    """
    return all(v == 0.0 for v in humidity_weight_spread(base_text).values())


#: Agreement demanded of two figures that are algebraically EQUAL, in
#: significant digits. Deliberately far below what f64 delivers (~16) and far
#: above any real divergence: a level-dependent a_k parts the bases at the scale
#: of its own spread, which is O(1e-3) or larger here.
#:
#: This is a HEURISTIC SANITY BOUND, not an error bound, and it decides nothing
#: -- the verdict comes from `weight_is_uniform`, which is exact. Two previous
#: versions of this check did claim a bound: first a bare f64 eps fitted to one
#: arm's one measurement, then `levels * eps`, which sounds derived but is not
#: valid for this quantity -- `rel = |y-x|/|x|` contains a SUBTRACTION, and
#: k*eps bounds a summation's error against sum|x_i|, saying nothing about the
#: cancellation in y-x (Codex). The honest structure is an exact precondition
#: plus an observed residual, not a fabricated tolerance.
SANITY_DIGITS = 8


def basis_gap(oracle: dict) -> float:
    """Max |rel(operator) - rel(physical)| over every departure both computed.

    Measures what the report used to assert. A key present in one basis and not
    the other is itself a disagreement (the departure was large enough to record
    on one measure and not the other), so it counts as a full mismatch rather
    than being skipped.
    """
    worst = 0.0
    for r in oracle["partitions"].values():
        op, ph = r["column_integrated"]["operator"], \
            r["column_integrated"]["physical"]
        for key in set(op) | set(ph):
            a = op.get(key, {}).get("rel")
            b = ph.get(key, {}).get("rel")
            worst = max(worst, abs(a - b) if a is not None and b is not None
                        else max(a or 0.0, b or 0.0))
    return worst


def report(driver: str, fixture: str) -> None:
    a = analysis(driver, fixture)
    print("  Tile decomposition changes the answer. Size, not only count.\n")
    print(f"  {'partition':>10} {'components':>11} {'columns':>9} {'field':>6} "
          f"{'max |rel|':>12} {'max ulps':>10} {'max |abs|':>12} "
          f"{'baseline':>12}")
    for tiles, r in a["partitions"].items():
        if not r["components_differing"]:
            print(f"  {tiles:>10} {'0':>10} {'-':>9}   (both tiles end on the "
                  f"same surface type -- identical gating)")
            continue
        first = f"{r['components_differing']}/{r['components_total']}"
        for f, d in sorted(r["by_field"].items(), key=lambda x: -x[1]["max_rel"]):
            print(f"  {tiles if first else '':>10} {first:>11} "
                  f"{str(r['columns']) if first else '':>9} {f:>6} "
                  f"{d['max_rel']:12.4e} {d['max_ulps']:10d} "
                  f"{d['max_abs']:12.4e} {d['max_abs_baseline']:12.4e}")
            first = ""
    print(f"\n  f32 eps = {a['f32_eps']:.3e}. A rounding difference lives there.")
    for tiles, r in a["partitions"].items():
        if r["components_differing"] and not r["is_roundoff_scale"]:
            print(f"  {tiles}: max relative difference {r['max_rel']:.4e} is "
                  f"{r['max_rel'] / a['f32_eps']:.3g}x f32 eps.")
    o = local_oracle(driver, fixture)
    base_text = run(driver, (fixture_dims(fixture)[0],))
    print(f"\n  Against the PER-COLUMN answer `{o['oracle']}` -- the direct sum a "
          f"corrected operator\n  must reproduce. This is a synthetic fixture "
          f"driven sequentially: no MPI ranks,\n  no haloes, no real coastal "
          f"layout. It does NOT stand for a production run.\n")
    print(f"  {'partition':>10} {'components':>12} {'columns':>9} "
          f"{'worst column-integrated departure':>38}")
    for tiles, r in o["partitions"].items():
        ci = r["column_integrated"]["operator"]
        worst = max(ci.items(), key=lambda kv: kv[1]["rel"], default=(None, None))
        # SIGNED. An unsigned figure reads the same whether the run makes more
        # or less of the quantity, and the published sentence was backwards
        # because of exactly that (owner §9.4).
        w = (f"{worst[0]} {100*worst[1]['signed_rel']:+.2f}%" if worst[0] else "-")
        print(f"  {tiles:>10} {r['components_differing']:>5}/"
              f"{r['components_total']:<6} "
              f"{str(r['columns']) if r['columns'] else '-':>9} {w:>38}"
              + ("   <- the oracle" if r["is_the_oracle"] else ""))
    law = class_law(driver, fixture)
    print(f"\n  The mechanism as a LAW over the whole decomposition space. "
          f"`ncmin` is a plain\n  local (F:812, not SAVE, not module-level), so "
          f"it cannot outlive one kdm62D\n  call, and the loop that sets it "
          f"(F:876-883) has no body but the assignment --\n  so `slmsk(ite)` "
          f"wins and the answer should be a function of the imposed\n  "
          f"threshold vector alone:")
    for vec, members in law["classes"].items():
        print(f"    [{vec}]  <- "
              + ", ".join("(" + ",".join(map(str, m)) + ")" for m in members))
    for w in law["within"]:
        print(f"    WITHIN a class {tuple(w['a'])} vs {tuple(w['b'])}: "
              f"byte-identical = {w['identical']}")
    for x in law["across"]:
        print(f"    ACROSS classes {tuple(x['a'])} vs {tuple(x['b'])}: "
              f"{x['differing']} components differ")
    if not law["holds"]:
        # Checked BEFORE the sentence below claims it held, for the same reason
        # the basis guard is: a failure must not be preceded by its own
        # reassurance.
        raise ra.RefineError(
            "the imposed-threshold law is FALSIFIED on this run: "
            + "; ".join(
                [f"{tuple(w['a'])} and {tuple(w['b'])} share a threshold vector "
                 f"but differ" for w in law["within"] if not w["identical"]]
                + [f"{tuple(x['a'])} and {tuple(x['b'])} have different vectors "
                   f"but are identical" for x in law["across"]
                   if not x["differing"]])
            + " -- `ncmin` is not the only thing the decomposition changes here, "
              "so the synthetic result cannot be read as a statement about real "
              "decompositions")
    act = gate_activity(base_text, fixture, (fixture_dims(fixture)[0],))
    cells = sum(v["cells"] for v in act.values())
    loc = sum(v["local_binding"] for v in act.values())
    imp = sum(v["imposed_binding"] for v in act.values())
    print(f"  The `nc <= ncmin` gate binds in {imp}/{cells} cells under the "
          f"threshold this run\n  ACTUALLY imposed, and {loc}/{cells} under "
          f"each column's own -- the per-column oracle's\n  gate. They differ "
          f"because the sea column is gated at the land threshold, which is\n"
          f"  the defect itself (owner §6). A null result under an INERT gate "
          f"is evidence\n  of the gate being inert, not of the operator being "
          f"local, so this sits beside\n  the verdict.")
    rep = control_replication(driver, fixture)
    if not rep["holds"]:
        raise ra.RefineError(
            f"the same-atmosphere control FAILS: "
            f"{rep['within_identical']}/{rep['trajectories']} trajectories keep "
            f"{rep['within_pair'][0]} == {rep['within_pair'][1]} and "
            f"{rep['across_differing']}/{rep['trajectories']} keep the "
            f"across-class pair distinct -- the decomposition moves something "
            f"other than the ncmin gate")
    print(f"  Same-atmosphere control, replicated over {rep['trajectories']} "
          f"trajectories (6 density\n  profiles x 2 aux arms x 3 sub-step "
          f"counts): {rep['within_pair'][0]} and {rep['within_pair'][1]} share a "
          f"threshold vector\n  but are genuinely different decompositions, and "
          f"agree bit-for-bit in "
          f"{rep['within_identical']}/{rep['trajectories']}.\n  The "
          f"across-class pair differs in {rep['across_differing']}/"
          f"{rep['trajectories']} -- both directions, so the null result is\n"
          f"  not just trajectories insensitive to everything.")
    print(f"  Held on every pair. But this fixture is {fixture_dims(fixture)[0]} "
          f"columns wide, which yields\n  exactly {law['within_pairs']} "
          f"within-class pair, so the data is CONSISTENT with the law rather\n"
          f"  than a strong test of it. What it does establish is what a real "
          f"MPI run would\n  have to show: the question becomes WHICH threshold "
          f"vectors a real coastal patch\n  layout produces -- geometry of the "
          f"decomposition, not more physics.")

    print("\n  Why each row moves, per column -- the sign follows the "
          "threshold it was\n  given, and the two directions have opposite "
          "mechanisms:")
    for tiles, r in o["partitions"].items():
        for col in r["columns"]:
            print("    " + mechanism_for(tuple(int(x) for x in tiles.split(",")),
                                         fixture, col))
    # Both bases are computed, so AGREEMENT IS MEASURED, not asserted. The
    # table above prints the operator basis; claiming the physical basis gives
    # the same relative figures while never comparing the two is an unverified
    # claim standing next to the numbers that would settle it (Codex).
    gap = basis_gap(o)
    spread = humidity_weight_spread(base_text)
    uniform = weight_is_uniform(base_text)
    digits = agreement_digits(o, gap)

    # Checked BEFORE the text below, which tells the reader the bases agree
    # by construction: printing that and then raising leaves the reassuring
    # paragraph in the log above the failure.
    if uniform and digits < SANITY_DIGITS:
        raise ra.RefineError(
            f"a_k is exactly uniform, so the two bases are algebraically equal, "
            f"yet they agree to only {digits:.1f} significant digits "
            f"(residual {gap:.3e}). That is "
            f"far beyond floating-point summation -- something in the two "
            f"column integrals is not computing the same quantity")

    print(f"\n  Humidity weight a_k = 1/(1+qv(t0)), vertical spread per "
          f"column: max {max(spread.values()):.3e}.")
    if uniform:
        print(f"  It is EXACTLY uniform in every column, so it cancels from a "
              f"per-column\n  RELATIVE figure algebraically and the two bases "
              f"agree by construction. That\n  is a property of the fixture, "
              f"not a law: a_k sits INSIDE the column sum.")
        print(f"  Observed residual between the bases: {gap:.3e} "
              f"({digits:.1f} significant digits\n  of agreement) -- floating-"
              f"point summation, reported as an OBSERVATION. No\n  error bound "
              f"is claimed: `rel` contains a subtraction, and the usual k*eps\n"
              f"  summation bound says nothing about cancellation in it.")
    else:
        print(f"  It is NOT uniform, so it does not cancel: the bases differ by "
              f"{gap:.3e}\n  and every figure above is basis-specific and must "
              f"not be quoted without\n  naming its basis.")


def main(argv) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    report(argv[0], argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
