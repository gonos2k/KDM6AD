#!/usr/bin/env python3
"""Many real columns, one at a time, through the actual kernel.

`FINDING_real_column_replay_v1` ran one column of the operational case and
found Arm N leaving 1.88 % of the legacy dry defect -- against a coefficient
estimate of 1.92-1.98 % over the whole domain. One column is an instance, which
is why that fixture's ceiling is STRUCTURAL_ONLY, and a single agreement can be
a coincidence.

This is the same experiment over a SAMPLE. The fixture data are compile-time
constants, so each column needs its own build: the manifest is rewritten, the
generator run, both arms built, both run, and the residuals taken. Slow and
completely mechanical.

WHAT IT CANNOT FIX. The columns come from one case at one time, so this is a
sample of THAT atmosphere and not of atmospheres. It answers "is 1.88 %
typical of this state" and nothing wider.

    python3 harness/g33_real_column_batch.py <wrfout> --columns 12 --json out.json
"""
from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
REPO = HERE.parent
RD, CP, P0, G = 287.04, 1004.5, 1.0e5, 9.81
FIXTURE_ID = "lc05_column_v1"
MANIFEST = HERE / "g33_fixture_lc05_column_v1.json"



def _frac(num: float, den: float):
    """num/den, or None where the column started with nothing (den == 0)."""
    return num / den if den else None


def _display(value, format_spec: str) -> str:
    """Render a number or the explicit unavailable sentinel used by reports."""
    return "n/a" if value is None else format(value, format_spec)


def _fraction_summary(rows: list[dict]) -> tuple[dict, list, list]:
    """Summarize defined fractions while preserving an empty population."""
    import statistics

    fr = sorted(r["fraction_left"] for r in rows
                if r.get("fraction_left") is not None)
    fx = sorted(r["fraction_left_xfer"] for r in rows
                if r.get("fraction_left_xfer") is not None)
    n = len(fr)
    # `fr[n // 2]` is the UPPER MIDDLE value on an even sample, not the median.
    # With 22 columns that is the 12th value where the median is the mean of the
    # 11th and 12th -- a small difference and the wrong name for it.
    summary = {"columns": n,
               "columns_with_fraction": n,
               "columns_unavailable": len(rows) - n,
               "summary_unavailable": not bool(fr),
               "median": statistics.median(fr) if fr else None,
               "upper_middle": fr[n // 2] if fr else None,
               "min": fr[0] if fr else None,
               "max": fr[-1] if fr else None,
               "p25": statistics.quantiles(fr, n=4)[0] if n >= 4 else None,
               "p75": statistics.quantiles(fr, n=4)[2] if n >= 4 else None,
               # The ACTUAL-transfer statistic beside the recovered one. They
               # are different quantities and the headline should say which.
               "median_xfer": statistics.median(fx) if fx else None,
               "min_xfer": fx[0] if fx else None,
               "max_xfer": fx[-1] if fx else None,
               "columns_xfer": len(fx)}
    return summary, fr, fx


def candidates(path: Path, want: int, field: str = "QNRAIN", levels: int = 6):
    """Columns carrying `field` over at least `levels` levels, spread evenly.

    Evenly over the SORTED candidate list rather than at random: the point is a
    spread across the domain's regimes, and a seeded random pick would be one
    more thing to have to reproduce.

    NOT STRATIFIED. Row-major order spreads the sample spatially and balances
    nothing -- not land against sea, not moisture-gradient quantile, not
    precipitation intensity, not the size of the legacy defect. So the
    distribution this produces is a deterministic spatial sample of one state
    and is NOT an unbiased estimate of that state's columns (owner review §8.3).
    """
    import numpy as np
    import netCDF4
    import g33_netcdf_read as nr
    with netCDF4.Dataset(str(path)) as d:
        n = _read_frame(d, field, -1)
    hits = np.argwhere((n > 0).sum(axis=0) >= levels)
    if len(hits) == 0:
        raise SystemExit(f"no column carries {field} over {levels} levels")
    step = max(1, len(hits) // want)
    return [tuple(int(v) for v in hits[i]) for i in range(0, len(hits), step)][:want]


def _read_frame(dataset, name: str, frame: int):
    """Read one model field through the shared mask and finite-value gate.

    A masked netCDF value must never become a finite compile-time fixture value.
    ``read_numeric`` refuses masks by default; this wrapper also refuses raw
    non-finite values so every field used for selection or manifest generation
    has the same input contract.
    """
    import g33_netcdf_read as nr

    try:
        got = nr.read_numeric(dataset[name], frame)
    except ValueError as exc:
        raise ValueError(f"{name}: invalid masked input at frame {frame}: {exc}") from exc
    if got["nonfinite_count"]:
        raise ValueError(
            f"{name}: {got['nonfinite_count']} nonfinite cells at frame {frame}")
    return got["data"]


def write_manifest(path: Path, j: int, i: int) -> dict:
    """Rewrite the committed manifest for one column. Returns its own summary."""
    import netCDF4
    import numpy as np
    from g33_number_basis import _physical
    with netCDF4.Dataset(str(path)) as d:
        # The batch's historical behavior is the terminal frame. Keep that
        # compatible choice, but make every read pass through one guarded
        # producer boundary.
        frame = -1
        g = lambda k: _read_frame(d, k, frame)                 # noqa: E731
        K = d.dimensions["bottom_top"].size
        p = _physical("pressure", (g("P") + g("PB"))[:, j, i], positive=True)
        th = _physical("potential temperature", (g("T") + 300.0)[:, j, i], positive=True)
        qv = g("QVAPOR")[:, j, i]
        ph = (g("PH") + g("PHB"))[:, j, i]
        dz = _physical("layer thickness", np.diff(ph) / G, positive=True)
        # THE MODEL'S OWN DENSITY, not a thermodynamic estimate. WRF's
        # hydrostatic relation makes `rho_d * dz = mu_d |d(eta)| / g` exact in
        # its own discretisation, and the host forms the `rho` it hands to
        # microphysics as `rho_d * (1 + qv)` (module_big_step_utilities_em.F:4856).
        mu = _physical("MU+MUB", (g("MU") + g("MUB"))[j, i], positive=True)
        dnw = _physical("|DNW|", np.abs(g("DNW")), positive=True)
        if dnw.shape != (K,):
            raise ValueError(f"DNW must be a {K}-level vector, got {dnw.shape}")
        rho_d = _physical("dry density", (mu * dnw) / G / dz, positive=True)
        den = _physical("moist density", rho_d * (1.0 + qv), positive=True)
        pii = _physical("Exner function", (p / P0) ** (RD / CP), positive=True)
        def f2b(v):
            _physical("fixture value", v)
            try:
                return struct.pack(">f", float(v)).hex()
            except OverflowError as exc:
                raise ValueError("fixture value is not representable as finite f32") from exc
        flip = lambda a: list(a[::-1])                           # WRF k=0 is BOTTOM
        src = json.loads(MANIFEST.read_text())
        fields = {}
        for nm, arr in (("th", th), ("qv", qv), ("qc", g("QCLOUD")[:, j, i]),
                        ("qr", g("QRAIN")[:, j, i]), ("qi", g("QICE")[:, j, i]),
                        ("qs", g("QSNOW")[:, j, i]), ("qg", g("QGRAUP")[:, j, i]),
                        ("nccn", g("QNCCN")[:, j, i]), ("nc", g("QNCLOUD")[:, j, i]),
                        ("ni", g("QNICE")[:, j, i]), ("nr", g("QNRAIN")[:, j, i]),
                        ("rho", den), ("pii", pii), ("p", p), ("delz", dz)):
            fields[nm] = [f2b(v) for v in flip(arr)]
        fields["bg"] = [f2b(0.0)] * K
        out = dict(src)
        out.update({"B": 1, "K": K, "fields": fields,
                    "xland": [f2b(g("XLAND")[j, i])]})
        # Validate the decoded f32 forcing before replacing the authority. In
        # particular, a positive f64 metric may have rounded to f32 zero.
        import g33_fixture_v1 as fx
        for name in ("rho", "pii", "p", "delz"):
            _physical(name, [fx._f32_word(w) for w in fields[name]], positive=True)
        if fx._f32_word(out["xland"][0]) not in (1.0, 2.0):
            raise ValueError("XLAND must be 1 or 2")
        MANIFEST.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")
        return {"j": j, "i": i, "xland": float(g("XLAND")[j, i]),
                "qv_surface": float(qv[0]), "qv_top": float(qv[-1]),
                "nr_levels": int((g("QNRAIN")[:, j, i] > 0).sum()),
                "frame": frame,
                "density": "canonical mu_d|d(eta)|/g, rho_m = rho_d(1+qv)"}


def residuals(build_root: Path, arm: str, nsplits=(12,), partial=True) -> dict:
    """Build one arm on the manifest as it currently stands; run it once per
    `nsplit`. The call step is `60 s / nsplit`, so 12, 6, 3, 2 give 5, 10, 20
    and 30 s -- the operational call is 20 s. `nsplit` is a runtime argument,
    so the timestep matrix costs no extra builds (owner review §9)."""
    import g33_number_basis as nb
    import g33_number_transport as nt  # noqa: F401
    out = build_root / arm
    b = subprocess.run(
        ["bash", str(HERE / "g33_fortran" / "refine_build.sh"), str(out),
         f"--fixture=g33_fixture_{FIXTURE_ID}", f"--algo={arm}", "--nflux"],
        capture_output=True, text=True, cwd=REPO)
    if b.returncode != 0:
        raise SystemExit(f"{arm}: build failed\n{b.stdout[-800:]}{b.stderr[-800:]}")
    got, failed = {}, {}
    for n in nsplits:
        r = subprocess.run([str(out / "g33_refine_driver"), str(n), "rezero", "1"],
                           capture_output=True, text=True)
        if r.returncode != 0:
            # A CRASH IS A PER-STEP VERDICT TOO. This used to abandon the whole
            # column, so the 5 and 10 s results were lost with it -- the same
            # complete-case loss the StreamError path was fixed for. It matters
            # more once an FPE trap is on: the process then EXITS on the
            # overflow instead of emitting it, so every -inf column would take
            # its shorter steps down with it (owner review 6.2).
            if not partial:
                raise SystemExit(f"{arm} nsplit={n}: driver crashed\n{r.stderr[-800:]}")
            failed[n] = f"driver exit {r.returncode}: {r.stderr.strip()[-120:]}"
            continue
        try:
            got[n] = nb.from_stream(r.stdout, "nr")[1]
        except nt.StreamError as exc:
            # ONE STEP'S VERDICT IS ITS OWN. A column that emits -inf at 30 s
            # still ran at 5, 10 and 20; discarding those made the operational
            # 20 s sample condition on surviving a step nothing uses, and cost
            # four land columns with above-median fractions
            # (FINDING_timestep_matrix_sample_v1).
            if not partial:
                raise
            failed[n] = f"StreamError: {exc}"[:200]
    if not got:
        raise nt.StreamError(f"{arm}: no call step produced a readable stream; "
                             + "; ".join(f"{k}:{v}" for k, v in failed.items()))
    got["_failed_steps"] = failed
    return got


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("state", type=Path)
    ap.add_argument("--columns", type=int, default=12)
    ap.add_argument("--nsplits", default="12",
                    help="comma-separated; 12,6,3,2 is the 5/10/20/30 s matrix")
    ap.add_argument("--json", type=Path, default=None)
    a = ap.parse_args()
    import g33_number_transport as nt

    # THIS TOOL OWNS SHARED, COMMITTED, MUTABLE STATE while it runs. The
    # fixture is a COMPILE-TIME constant, so every column rewrites
    # `MANIFEST` and regenerates the .f90 and .h beside it -- one fixed path,
    # not a private copy. Two ways that has already gone wrong:
    #
    #   * a `git add -A` mid-batch staged a transient column as if it were the
    #     fixture, caught only because the status was read;
    #   * a concurrent test run regenerated those artefacts between this tool's
    #     write and its build, producing a kernel whose .f90 and .h held
    #     DIFFERENT columns. That build ran and emitted -inf, which read as a
    #     kernel result and was not one.
    #
    # So: refuse to start dirty, refuse to start beside another holder, and
    # hold a lock naming who we are for anything that looks.
    # THE SAME PATHS AT BOTH ENDS. The start check looked at MANIFEST alone and
    # the end check at three whole DIRECTORIES, so a tree with any unrelated
    # edit under harness/g33_fortran passed the first and failed the second --
    # renaming the lock to .failed and demanding a manual repair for something
    # this batch never touched. Observed. These are the files it rewrites, and
    # they are what both ends ask about.
    OWNED = [str(MANIFEST),
             f"harness/g33_fortran/g33_fixture_{FIXTURE_ID}.f90",
             f"harness/g33_overlay/g33_fixture_{FIXTURE_ID}.h"]
    dirty = subprocess.run(["git", "status", "--porcelain", "--", *OWNED],
                           capture_output=True, text=True, cwd=REPO).stdout.strip()
    if dirty:
        raise SystemExit(f"the fixture files this batch rewrites are modified "
                         f"relative to HEAD:\n{dirty}\nA "
                         f"previous batch did not restore it. Inspect before "
                         f"running another.")
    failed = REPO / ".g33-fixture-lock.failed"
    if failed.exists():
        raise SystemExit(
            f"{failed.name} is present: a previous run could not restore the "
            f"working tree. Repair it and remove that file before running again.")
    lock = REPO / ".g33-fixture-lock"
    # ATOMIC. `if exists: ... write` is a race with exactly the window it is
    # meant to close -- two starters can both pass the test. O_CREAT|O_EXCL is
    # one syscall and cannot.
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError:
        # The holder can release between our failed open and this read, and it
        # can die between creating the lock and writing who it is. Neither may
        # turn the message that says WHO HOLDS IT into a traceback -- the whole
        # value of this path is the name it prints.
        try:
            held = lock.read_text().strip() or "(holder wrote no name)"
        except OSError:
            held = "(released while we were reporting it; try again)"
        raise SystemExit(
            f"{lock.name} is held by: {held}\n"
            f"The committed fixture is a compile-time constant, so two writers "
            f"produce a kernel built from two different columns. Wait, or "
            f"remove the lock if that process is gone.") from None
    with os.fdopen(fd, "w") as fh:
        fh.write(f"pid {os.getpid()}, {a.columns} columns, state {a.state}\n")
    print(f"  NOTE: {MANIFEST.name} and its generated .f90/.h are rewritten per "
          f"column until this finishes.\n"
          f"        Nothing else may build a fixture meanwhile -- not the test "
          f"suite, not a variant generator.\n"
          f"        Holding {lock.name}.")
    keep = MANIFEST.read_text()          # the committed column, restored at the end
    # REJECTED COLUMNS ARE PART OF THE RESULT. A sample reported only through
    # what survived cannot be checked for survivorship bias: if the columns that
    # fail are the ones with the largest defect, the distribution is a
    # selection. Every requested column is recorded with its verdict.
    rows, rejected = [], []
    try:
        for j, i in candidates(a.state, a.columns):
            meta = write_manifest(a.state, j, i)
            gen = subprocess.run([sys.executable, str(HERE / "g33_fixture_v1.py"),
                                  "--write", f"--fixture-id={FIXTURE_ID}"],
                                 capture_output=True, text=True, cwd=REPO)
            if gen.returncode != 0:
                why = gen.stderr.strip().splitlines()[-1][:120]
                rejected.append(dict(meta, stage="manifest", reason=why))
                print(f"  ({j},{i}) refused by the manifest: {why[:90]}")
                continue
            nsplits = tuple(int(v) for v in a.nsplits.split(","))
            with tempfile.TemporaryDirectory(prefix="g33-col.") as td:
                try:
                    legs = residuals(Path(td), "legacy", nsplits)
                    nms = residuals(Path(td), "nmass", nsplits)
                except SystemExit as exc:
                    rejected.append(dict(meta, stage="build_or_run",
                                         reason=str(exc)[:200]))
                    print(f"  ({j},{i}) {exc}")
                    continue
                except nt.StreamError as exc:
                    # A COLUMN THAT KILLS THE KERNEL IS A RESULT, not a crash:
                    # one emitted -inf at a 30 s step and aborted the remaining
                    # nineteen. But catching `Exception` files a KeyError, a
                    # parser regression and a corrupt file as though they were
                    # data -- the sample then completes while measuring nothing,
                    # which is worse than stopping. Only a StreamError is a
                    # verdict about the RUN; everything else re-raises.
                    rejected.append(dict(meta, stage="build_or_run",
                                         reason=f"StreamError: {exc}"[:200]))
                    print(f"  ({j},{i}) StreamError: {str(exc)[:90]}")
                    continue
            if nsplits[0] not in legs or nsplits[0] not in nms:
                rejected.append(dict(meta, stage="build_or_run",
                                     reason=f"the headline step {60 // nsplits[0]}s "
                                            f"did not produce a readable stream"))
                print(f"  ({j},{i}) headline step failed")
                continue
            leg, nm = legs[nsplits[0]], nms[nsplits[0]]
            row = dict(meta,
                       # the per-timestep matrix, ratio only: what the review
                       # asked to see is whether the FRACTION is timestep-
                       # invariant across the sample, as it was on one column
                       timestep_matrix={
                           f"{60 // n}s": (abs(nms[n]["dry_xfer"] / nms[n]["start_dry"])
                                           / abs(legs[n]["dry_xfer"] / legs[n]["start_dry"]))
                           for n in nsplits
                           if n in legs and n in nms and legs[n]["dry_xfer"]
            and legs[n]["start_dry"] and nms[n]["start_dry"]},
                       # named, so a step that failed is visible as a failure
                       # rather than as an absence
                       # PER ARM. Folding the two together with `or` lost which
                       # one failed, and that is the fact that says whether an
                       # overflow is common to the operator or introduced by a
                       # correction (owner review 6.3).
                       timestep_failed={
                           f"{60 // n}s": {"legacy": legs["_failed_steps"].get(n),
                                           "nmass": nms["_failed_steps"].get(n)}
                           for n in nsplits
                           if n in legs["_failed_steps"] or n in nms["_failed_steps"]},
                       legacy_moist=_frac(leg["moist"], leg["start_moist"]),
                       legacy_dry=_frac(leg["dry"], leg["start_dry"]),
                       # BOTH READERS, and `legacy_dry_xfer` was missing
                       # entirely -- so the ratio could only ever be formed
                       # from the recovered pair (owner review §10.1).
                       legacy_dry_xfer=_frac(leg["dry_xfer"], leg["start_dry"]),
                       legacy_moist_xfer=_frac(leg["moist_xfer"], leg["start_moist"]),
                       armn_moist_xfer=_frac(nm["moist_xfer"], nm["start_moist"]),
                       armn_dry=_frac(nm["dry"], nm["start_dry"]),
                       armn_dry_xfer=_frac(nm["dry_xfer"], nm["start_dry"]))
            row["fraction_left"] = abs(row["armn_dry"]) / abs(row["legacy_dry"]) \
                if row["legacy_dry"] and row["armn_dry"] is not None else None
            row["fraction_left_xfer"] = (
                abs(row["armn_dry_xfer"]) / abs(row["legacy_dry_xfer"])
                if row["legacy_dry_xfer"] and row["armn_dry_xfer"] is not None else None)
            rows.append(row)
            print(f"  ({j:3d},{i:3d}) xland={meta['xland']:.0f} "
                  f"legacy_dry {_display(row['legacy_dry'], '11.4e')}  "
                  f"armN_dry {_display(row['armn_dry'], '11.4e')}  "
                  f"leaves {_display(row['fraction_left'], '.4%')}")
    finally:
        # ORDER MATTERS. Releasing the lock before the generated .f90/.h are
        # back leaves a window in which a waiting process starts, sees the
        # restored MANIFEST, and builds the PREVIOUS column's sources -- which
        # is the contamination this lock exists to prevent, reintroduced by the
        # release itself. Restore, regenerate, verify, and only then release.
        MANIFEST.write_text(keep)
        subprocess.run([sys.executable, str(HERE / "g33_fixture_v1.py"),
                        "--write", f"--fixture-id={FIXTURE_ID}"],
                       capture_output=True, text=True, cwd=REPO)
        left = subprocess.run(["git", "status", "--porcelain", "--", *OWNED],
                              capture_output=True, text=True, cwd=REPO).stdout.strip()
        lock = REPO / ".g33-fixture-lock"
        if left:
            # FAIL CLOSED. Warning and releasing anyway is fail-open: the next
            # process starts on a tree that does not match HEAD and builds from
            # whatever is there. The lock stays, renamed so its state is legible,
            # and the next run refuses until someone repairs the tree
            # (owner review 6.4).
            lock.rename(REPO / ".g33-fixture-lock.failed")
            print(f"  RESTORE FAILED -- the tree is not back to HEAD:\n{left}\n"
                  f"  .g33-fixture-lock.failed left in place; repair the tree and "
                  f"remove it before the next run.")
        else:
            lock.unlink(missing_ok=True)

    if not rows:
        raise SystemExit("no column produced a usable pair")
    summary, fr, fx = _fraction_summary(rows)
    n = len(fr)
    if fr:
        print(f"\n  {n} columns, RECOVERED transfers: Arm N leaves median "
              f"{summary['median']:.4%} (min {summary['min']:.4%}, "
              f"max {summary['max']:.4%})")
    else:
        print(f"\n  {len(rows)} columns, RECOVERED transfers: Arm N leaves "
              "n/a (no defined legacy denominator)")
    if fx:
        print(f"  {len(fx)} columns, ACTUAL XFER:       median "
              f"{summary['median_xfer']:.4%} (min {summary['min_xfer']:.4%}, "
              f"max {summary['max_xfer']:.4%})")
    if rejected:
        print(f"  {len(rejected)} column(s) rejected; reasons in the JSON")
    if a.json:
        a.json.write_text(json.dumps(
            {"summary": summary, "columns": rows, "rejected": rejected,
             "requested": len(rows) + len(rejected)},
            indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
