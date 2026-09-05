#!/usr/bin/env python3
"""Two decompositions of one forecast, compared without flattering either.

`FINDING_mpi_trajectory_growth_v1` reported quantiles over the cells that
DIFFER, a reflectivity growth factor across a support that changes between the
two times it compares, and an accumulated-precipitation maximum. Each is a real
number and none of them is what a reader takes it for (owner review §10-13).

Four corrections, and every statistic says which population it is over.

CONDITIONAL AND UNCONDITIONAL. `p99` over differing cells is not the domain's
`p99`. Both are reported; the first says how big a difference is where there is
one, the second how much of the domain carries it.

A FIXED MASK FOR GROWTH. Comparing a median at one minute with a median at ten
compares two different sets of cells, because the differing support grows from
4.8 % to 11.2 %. Growth is measured on the cells that differ at the FIRST time
and followed, so the population is held still.

SIGNED, FOR PRECIPITATION. `|dP|` cannot tell a domain that rains more from one
that rains the same in different places. The signed domain integral and the
exceedance fractions are what separate them.

REFLECTIVITY IN ITS OWN TERMS. The field's range here reaches 174.8 dBZ, which
is not a reflectivity, so a maximum is dominated by whatever produces those.
The physically screened population, the linear-Z ratio and the threshold AREAS
are reported instead -- the last being what a forecast is read in.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

#: Outside this, `REFL_10CM` is not being used as a reflectivity.
REFL_PHYSICAL = (-35.0, 80.0)


def _signed_mean(x, y, finite):
    """Mean signed difference over the finite cells.

    Same reason as the subtraction above: `inf - inf` warns, the NaN is excluded
    by `finite`, and the warning would only hide a real one later.
    """
    import numpy as np
    with np.errstate(invalid="ignore"):
        return float((y - x)[finite].mean())


def _num(var, index):
    """A numeric field, through the guard (owner review 8.3).

    `np.asarray` on a netCDF variable DROPS a mask, and this module then feeds
    the result to equality, a non-finite census, and precipitation and
    reflectivity thresholds. `g33_number_basis` was wired through the guard and
    this one -- equally load-bearing -- was not.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import g33_netcdf_read as nr
    data = nr.read_numeric(var, index)["data"]
    if data.size == 0:
        raise SystemExit(
            f"INSUFFICIENT: {getattr(var, 'name', 'numeric field')} has zero numeric cells")
    return data


def _fields(d):
    import numpy as np
    return [v for v in d.variables
            if d[v].dtype == np.float32 and d[v].ndim >= 3
            and "Time" in d[v].dimensions]


def _forecast_in(run_dir):
    """The one forecast file in a run directory, or a refusal naming what it found."""
    from pathlib import Path
    cands = sorted(p for p in Path(run_dir).iterdir()
                   if p.is_file() and (p.name.startswith("klfs_lc05_fcst.")
                                       or p.name.startswith("wrfout_d01_")))
    if len(cands) != 1:
        raise SystemExit(
            f"{run_dir}: expected exactly one forecast file, found {len(cands)}"
            + (f": {[c.name for c in cands]}" if cands else ""))
    return cands[0]


def _times_values(ds, label: str):
    """Read the required history labels before any frame-indexed statistic."""
    import numpy as np
    if "Times" not in ds.variables:
        raise SystemExit(
            f"INSUFFICIENT: {label} forecast is missing required Times variable")
    var = ds.variables["Times"]
    if "Time" not in var.dimensions:
        raise SystemExit(
            f"INSUFFICIENT: {label} Times variable lacks a Time dimension")
    axis = var.dimensions.index("Time")
    if var.shape[axis] < 1:
        raise SystemExit(f"INSUFFICIENT: {label} Times variable has no frames")
    try:
        value = np.asarray(var[:])
    except (IndexError, OSError, RuntimeError, ValueError) as exc:
        raise SystemExit(
            f"INSUFFICIENT: {label} Times variable cannot be read: {exc}") from exc
    if value.size == 0:
        raise SystemExit(f"INSUFFICIENT: {label} Times variable has no cells")
    return value


_GRID_TOKEN = re.compile(r"^(\d+)x(\d+)$")
_HEX64 = re.compile(r"^[0-9a-fA-F]{64}$")


def _grid_record(text: str | None, run_dir: Path) -> dict:
    """Parse the runner's requested/actual processor-grid record.

    A decomposition claim needs both sides of the record: a requested grid that
    WRF acknowledged and an actual grid parsed from ``rsl.error.0000``.  The
    old consumer compared opaque text and therefore accepted two different
    requests that both ran as 1x1.
    """
    if text is None:
        return {"present": False, "requested": None, "actual": None,
                "matches": None, "np": None, "valid": False}
    fields: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\s*(requested|actual|matches|np)\s+(.+?)\s*$",
                     line, re.IGNORECASE)
        if not m:
            if re.match(r"^\s*(requested|actual|matches|np)\b", line,
                        re.IGNORECASE):
                return {"present": True, "requested": None, "actual": None,
                        "matches": None, "np": None, "valid": False,
                        "error": f"malformed grid fact in {run_dir / 'proc_grid'}"}
            continue
        key = m.group(1).lower()
        if key in fields:
            return {"present": True, "requested": None, "actual": None,
                    "matches": None, "np": None, "valid": False,
                    "error": f"duplicate {key} in {run_dir / 'proc_grid'}"}
        fields[key] = m.group(2)

    def grid(value: str | None) -> tuple[str | None, bool]:
        if value is None:
            return None, False
        value = value.strip().lower()
        if value.startswith("(unset") or value.startswith("(not found"):
            return None, False
        m = _GRID_TOKEN.fullmatch(value.lower())
        if not m or int(m.group(1)) < 1 or int(m.group(2)) < 1:
            return None, True
        return f"{int(m.group(1))}x{int(m.group(2))}", False

    requested, requested_malformed = grid(fields.get("requested"))
    actual, actual_malformed = grid(fields.get("actual"))
    matches_present = "matches" in fields
    matches_raw = fields.get("matches", "").strip().lower()
    # The producer may append an explanatory ``-- ...`` comment.  The token
    # itself must still be one of the three declared values; arbitrary text is
    # never a reason to derive a value from the grids.
    match = re.fullmatch(r"(yes|no|n/a)(?:\s+--.*)?", matches_raw)
    if match and match.group(1) == "yes":
        matches = "yes"
    elif match and match.group(1) == "no":
        matches = "no"
    elif match and match.group(1) == "n/a":
        matches = "n/a"
    elif matches_present:
        matches = None
    else:
        # Older records did not carry a matches line.  Derive it only when both
        # grids are present; a malformed/missing actual grid remains invalid.
        matches = "yes" if requested is not None and actual is not None and requested == actual else None
    try:
        np_value = int(fields["np"]) if "np" in fields else None
        np_malformed = False
    except (TypeError, ValueError):
        np_value = None
        np_malformed = True
    valid = bool(actual is not None and (np_value is None or np_value > 0))
    if requested_malformed or actual_malformed or np_malformed:
        valid = False
    if matches_present and not match:
        valid = False
    if valid and np_value is not None:
        ax, ay = (int(v) for v in actual.split("x"))
        valid = ax * ay == np_value
    # ``matches`` is a claim about the two parsed grids, not an override for a
    # contradictory record.  Treat an explicit contradiction as malformed
    # metadata so attribution cannot proceed on an opaque text pair.
    if valid:
        if requested is not None:
            valid = (actual is not None and matches in {"yes", "no"}
                     and ((matches == "yes") == (requested == actual)))
        elif matches_present:
            # ``n/a`` is the only declared matches value for an unrequested
            # grid.  A yes/no claim without a requested grid is contradictory.
            valid = matches == "n/a"
    return {"present": True, "requested": requested, "actual": actual,
            "matches": matches, "np": np_value, "valid": valid,
            "raw": fields,
            "error": ("malformed requested/actual/np/matches field"
                       if (requested_malformed or actual_malformed or np_malformed
                           or (matches_present and not match)) else None)}


def _active_input_specs(run_dir: Path) -> list[dict[str, str]]:
    """Resolve the archived namelist's active input set.

    This calls the same ordinary-namelist resolver as the producer.  A minimal
    no-assignment fixture is retained as legacy synthetic metadata; an ordinary
    WRF run control without explicit input names is identity-incomplete and is
    refused because registry defaults are outside this parser's scope.
    """
    nml = Path(run_dir) / "namelist.input"
    if not nml.is_file():
        return []
    try:
        from run_ss_case import (_namelist_assignments,
                                 resolve_active_namelist_inputs)
        text = nml.read_text()
        assignments = _namelist_assignments(text)
        specs = resolve_active_namelist_inputs(text)
        # WRF supplies registry defaults for input_inname/bdy_inname and active
        # aux streams.  This audit parser intentionally does not recreate that
        # registry.  Once a normal WRF namelist identifies max_dom, require the
        # core names (and any declared auxiliary interval's matching name) so a
        # missing default cannot be misreported as a no-input experiment.
        # A real WRF namelist may omit max_dom (its registry default is one), so
        # use a small set of unmistakable WRF run controls to recognize that
        # scope.  The minimal ``&domains/`` fixtures used by old unit tests have
        # none of these controls and remain explicitly legacy synthetic inputs.
        standard_keys = {
            "max_dom", "history_interval", "history_interval_s", "run_days",
            "run_hours", "run_minutes", "run_seconds", "start_year",
            "mp_physics", "time_step", "input_from_file",
        }
        if standard_keys.intersection(assignments):
            missing_core = sorted({"input_inname", "bdy_inname"}
                                  - set(assignments))
            if missing_core:
                raise SystemExit(
                    f"{run_dir}: identity-incomplete: standard WRF defaults for "
                    f"{', '.join(missing_core)} are unsupported; declare explicit input names")
            aux_intervals = {
                match.group(1)
                for key in assignments
                for match in [re.fullmatch(r"(auxinput\d+)_interval(?:_s)?", key)]
                if match
            }
            missing_aux = sorted(
                f"{base}_inname" for base in aux_intervals
                if f"{base}_inname" not in assignments)
            if missing_aux:
                raise SystemExit(
                    f"{run_dir}: identity-incomplete: active auxiliary defaults are "
                    f"unsupported; declare explicit {', '.join(missing_aux)}")
        return specs
    except Exception as exc:
        if isinstance(exc, SystemExit):
            raise
        raise SystemExit(
            f"{run_dir}: cannot resolve active inputs from namelist.input: {exc}") from exc


def _active_input_declared(run_dir: Path) -> bool:
    return bool(_active_input_specs(run_dir))


def _validate_producer_status(run_dir: Path) -> bool:
    """Consume producer validity without inventing it for old fixtures.

    The SS producer writes both an explicit experiment verdict and an
    executable before/after stability line.  A final executable digest alone
    cannot prove that the bytes stayed fixed while the model ran.  Historical
    synthetic fixtures may predate these files, so their absence is retained as
    legacy metadata; an explicitly supplied invalid/stability record is always
    a hard refusal.
    """
    run_dir = Path(run_dir)
    validity = run_dir / "experiment_valid.json"
    if validity.is_file():
        try:
            record = json.loads(validity.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"{run_dir}: invalid experiment_valid.json: {exc}") from exc
        if not isinstance(record, dict) or record.get("experiment_valid") is not True:
            reasons = record.get("invalid_reasons") if isinstance(record, dict) else None
            raise SystemExit(
                f"{run_dir}: producer marked experiment_valid=false"
                + (f" ({reasons})" if reasons else ""))
        reasons = record.get("invalid_reasons")
        if not isinstance(reasons, list) or reasons:
            raise SystemExit(
                f"{run_dir}: experiment_valid=true contradicts invalid_reasons={reasons!r}")
        exit_code = record.get("exit_code")
        completed = record.get("model_completed")
        if not isinstance(exit_code, int) or isinstance(exit_code, bool):
            raise SystemExit(
                f"{run_dir}: producer validity lacks an integer exit_code")
        if exit_code != 0 or completed is not True:
            raise SystemExit(
                f"{run_dir}: experiment_valid=true contradicts exit_code="
                f"{exit_code} model_completed={completed!r}")
        requested = record.get("requested_proc_grid")
        actual = record.get("actual_proc_grid")
        if requested is not None and actual != requested:
            raise SystemExit(
                f"{run_dir}: experiment_valid=true contradicts processor grid "
                f"requested={requested!r} actual={actual!r}")
    exe = run_dir / "wrf_exe_sha256"
    if exe.is_file():
        try:
            lines = exe.read_text().splitlines()
        except OSError as exc:
            raise SystemExit(f"{run_dir}: cannot read wrf_exe_sha256: {exc}") from exc
        # The producer writes a bare final digest followed by explicit before,
        # after, and stable facts.  Read all four as one record.  A stable line
        # is not an authentication mechanism: it is accepted only when the
        # independently recorded digests imply the same result.
        nonempty = [line.strip() for line in lines if line.strip()]
        final = None
        before = after = None
        stable = None
        seen_keys: set[str] = set()
        for line in nonempty:
            if _HEX64.fullmatch(line):
                if final is not None:
                    raise SystemExit(f"{run_dir}: duplicate final executable digest")
                final = line.lower()
                continue
            m = re.fullmatch(r"(before|after)\s+([^\s]+)", line,
                             re.IGNORECASE)
            if m:
                key = m.group(1).lower()
                if key in seen_keys:
                    raise SystemExit(f"{run_dir}: duplicate {key} executable digest")
                seen_keys.add(key)
                digest = m.group(2)
                if not _HEX64.fullmatch(digest):
                    raise SystemExit(
                        f"{run_dir}: {key} executable digest is not a 64-hex hash")
                if key == "before":
                    before = digest.lower()
                else:
                    after = digest.lower()
                continue
            m = re.fullmatch(r"stable\s+(yes|no)(?:\s+--.*)?", line,
                             re.IGNORECASE)
            if m:
                if "stable" in seen_keys:
                    raise SystemExit(f"{run_dir}: duplicate stable executable fact")
                seen_keys.add("stable")
                stable = m.group(1).lower() == "yes"
                continue
            if re.match(r"^\s*path\s+", line, re.IGNORECASE):
                # The resolved path is descriptive and is not part of the
                # digest consistency check.
                continue
            raise SystemExit(f"{run_dir}: malformed executable identity line: {line!r}")

        has_pair_digests = before is not None or after is not None
        if stable is False and not has_pair_digests and not validity.is_file():
            raise SystemExit(
                f"{run_dir}: producer executable record is unstable (stable NO)")
        if has_pair_digests or stable is not None or validity.is_file():
            if final is None or before is None or after is None:
                raise SystemExit(
                    f"{run_dir}: executable identity lacks final/before/after digest")
            implied_stable = before == after == final
            if stable is not None and stable is not implied_stable:
                raise SystemExit(
                    f"{run_dir}: executable stable fact contradicts final/before/after digests")
            if stable is None and validity.is_file():
                raise SystemExit(
                    f"{run_dir}: producer validity lacks a stable executable record")
            if not implied_stable:
                raise SystemExit(
                    f"{run_dir}: executable final/before/after digests are inconsistent")
        elif stable is False:
            # Legacy records may carry only a stable NO claim; it remains a
            # hard refusal even though there are no digests to reconcile.
            raise SystemExit(
                f"{run_dir}: producer executable record is unstable (stable NO)")
        elif validity.is_file():
            raise SystemExit(
                f"{run_dir}: producer validity lacks a stable executable record")
    elif validity.is_file():
        raise SystemExit(
            f"{run_dir}: producer validity lacks wrf_exe_sha256 stability record")
    return validity.is_file()


def _input_identity(run_dir: Path) -> dict:
    """Load and validate the runner's per-domain input hashes."""
    run_dir = Path(run_dir)
    json_path = run_dir / "input_sha256.json"
    text_path = run_dir / "input_sha256"
    active_specs = _active_input_specs(run_dir)
    declared_by_nml = bool(active_specs)
    if json_path.is_file():
        try:
            identity = json.loads(json_path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"{run_dir}: invalid input_sha256.json: {exc}") from exc
    elif text_path.is_file():
        records = []
        canonical_text = None
        try:
            lines = text_path.read_text().splitlines()
        except OSError as exc:
            raise SystemExit(f"{run_dir}: cannot read input_sha256: {exc}") from exc
        for line in lines:
            fields = line.split()
            if len(fields) == 2 and fields[0].lower() == "canonical_sha256":
                canonical_text = fields[1]
                continue
            if len(fields) < 4 or fields[0].lower() in {"schema", "declared", "complete"}:
                continue
            kind, domain, name, digest = fields[:4]
            records.append({"kind": kind, "domain": domain, "name": name,
                            "sha256_before": None if digest == "(missing)" else digest,
                            "sha256": None if digest == "(missing)" else digest,
                            "status": "ok" if digest != "(missing)" else "missing",
                            "stable": all(not f.startswith("stable=NO") for f in fields[4:])})
        identity = {"schema": 1, "declared": bool(records), "records": records,
                    "complete": all(r["status"] == "ok" and r.get("stable", True)
                                    for r in records)}
        if canonical_text is not None:
            identity["canonical_sha256"] = canonical_text
    else:
        if declared_by_nml:
            raise SystemExit(
                f"{run_dir}: active namelist inputs are not recorded in input_sha256")
        return {"present": False, "declared": False, "complete": True,
                "keys": (), "records": []}

    if not isinstance(identity, dict) or not isinstance(identity.get("records"), list):
        raise SystemExit(f"{run_dir}: input identity has no records list")
    declared_raw = identity.get("declared", bool(identity["records"]))
    if not isinstance(declared_raw, bool):
        raise SystemExit(f"{run_dir}: input identity declared flag is not boolean")
    declared = declared_raw
    if identity["records"] and not declared:
        raise SystemExit(f"{run_dir}: input identity has records but is marked undeclared")
    if declared_by_nml and (not declared or not identity["records"]):
        raise SystemExit(f"{run_dir}: namelist declares inputs but input identity is empty")
    expected_records = {(s["kind"], s["domain"], s["name"]) for s in active_specs}
    actual_records = set()
    for rec in identity["records"]:
        if not isinstance(rec, dict):
            raise SystemExit(f"{run_dir}: malformed input identity record")
        key = (rec.get("kind"), rec.get("domain"), rec.get("name"))
        if (not all(isinstance(part, str) and part for part in key)):
            raise SystemExit(
                f"{run_dir}: active input identity record lacks a non-empty kind/domain/name")
        if key in actual_records:
            raise SystemExit(
                f"{run_dir}: duplicate active input identity key {key!r}")
        actual_records.add(key)
    if expected_records != actual_records:
        raise SystemExit(
            f"{run_dir}: input identity does not cover the active namelist input set")
    keys = []
    for rec in identity["records"]:
        if not isinstance(rec, dict):
            raise SystemExit(f"{run_dir}: malformed input identity record")
        kind, domain = rec.get("kind"), rec.get("domain")
        before = rec.get("sha256_before", rec.get("sha256"))
        after = rec.get("sha256_after", rec.get("sha256"))
        digest = before
        if not isinstance(kind, str) or not isinstance(domain, str):
            raise SystemExit(f"{run_dir}: input identity record lacks kind/domain")
        if (not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-fA-F]{64}", digest)
                or not isinstance(after, str)
                or not re.fullmatch(r"[0-9a-fA-F]{64}", after)):
            raise SystemExit(f"{run_dir}: invalid input hash for {kind}/{domain}")
        derived_stable = before.lower() == after.lower()
        declared_stable = rec.get("stable")
        if declared_stable is not None and declared_stable is not derived_stable:
            raise SystemExit(
                f"{run_dir}: input {kind}/{domain} has contradictory stable metadata; "
                "canonical input identity hash is not trustworthy")
        status_after = rec.get("status_after", "ok")
        if (rec.get("status", "ok") != "ok" or status_after != "ok"
                or not derived_stable):
            raise SystemExit(f"{run_dir}: input {kind}/{domain} was unavailable or changed during run")
        keys.append((kind, domain, digest.lower()))
    complete_raw = identity.get("complete", True)
    if not isinstance(complete_raw, bool):
        raise SystemExit(f"{run_dir}: input identity complete flag is not boolean")
    if declared and not complete_raw:
        raise SystemExit(f"{run_dir}: input identity is incomplete")

    # A producer may seal its path-independent records with a canonical digest.
    # Validate that declaration against the records; never read the current
    # resolved_path as if it were the historical byte stream consumed by WRF.
    # Archived runs can legitimately lack those source files or have changed
    # paths, while the producer's before/after record remains the relevant
    # attestation.
    canonical = identity.get("canonical_sha256")
    producer_status_present = (run_dir / "experiment_valid.json").is_file()
    if canonical is not None:
        if not isinstance(canonical, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", canonical):
            raise SystemExit(f"{run_dir}: invalid canonical input identity hash")
        try:
            from run_ss_case import canonical_input_sha256
            expected_canonical = canonical_input_sha256(identity)
        except Exception as exc:
            raise SystemExit(f"{run_dir}: cannot compute canonical input identity hash: {exc}") from exc
        if canonical.lower() != expected_canonical:
            raise SystemExit(
                f"{run_dir}: canonical input identity hash does not match its records")
        attestation = "producer_canonical_record"
    else:
        # New producer runs have experiment_valid.json and therefore must carry
        # the seal.  Old synthetic metadata remains readable, but is explicitly
        # labelled unanchored and is never described as independently byte-checked.
        if producer_status_present and declared:
            raise SystemExit(
                f"{run_dir}: producer input identity lacks canonical record hash")
        attestation = "unanchored_metadata"
    return {"present": True, "declared": declared, "complete": True,
            "keys": tuple(sorted(keys)), "records": identity["records"],
            "canonical_sha256": canonical.lower() if isinstance(canonical, str) else None,
            "attestation": attestation}


def same_experiment(dir_a, dir_b, *, expect: str = "decomposition") -> dict:
    """Refuse two RUNS that are not the same experiment (owner review 8.2).

    `comparable` below checks the two FILES agree in field universe, time axis
    and shape. That is necessary and nowhere near sufficient: two forecasts of
    different initial states, built from different binaries, under different
    namelists, all pass it -- and then a divergence statistic gets attributed to
    the decomposition.

    `run_ss_case` now records what settles it, including the requested and
    actual processor grids plus hashes of every active initial, boundary, and
    auxiliary input. This reads that metadata and states which identities agree,
    so an attribution has something to stand on besides the array shapes.

    `expect` names what SHOULD differ: "decomposition" wants the same binary,
    runner and namelist with a different processor grid; "perturbation" wants
    all four identical, the input having been changed instead.
    """
    from pathlib import Path
    if expect not in {"decomposition", "perturbation"}:
        raise SystemExit(f"unknown experiment expectation: {expect}")

    producer_a = _validate_producer_status(Path(dir_a))
    producer_b = _validate_producer_status(Path(dir_b))
    if producer_a != producer_b:
        raise SystemExit(
            "producer validity metadata is present in only one run; "
            "legacy and sealed runs cannot be attributed as one experiment")

    def read(d, name):
        p = Path(d) / name
        return p.read_text().strip() if p.is_file() else None

    def first(text):
        return text.splitlines()[0].strip() if text else None

    out = {"applied": True, "expect": expect,
           "a": str(dir_a), "b": str(dir_b), "agree": {}, "differ": {}}
    out["producer_status"] = {"a": {"explicit": producer_a},
                               "b": {"explicit": producer_b}}
    for key, name, pick in (("wrf_exe", "wrf_exe_sha256", first),
                            ("runner", "runner_sha256", first),
                            ("proc_grid", "proc_grid", lambda t: t),
                            ("namelist", "namelist.input", lambda t: t),
                            # A decomposition experiment differs in the grid and
                            # in nothing else. The raw namelist ALWAYS differs
                            # here, because the runner writes nproc_x/nproc_y
                            # into it, so requiring the raw text would refuse
                            # every valid pair -- and not requiring anything let
                            # a pair differing in the time step, the physics or
                            # the forecast length pass as one experiment (owner
                            # review 15). Compare it with those two lines out.
                            ("namelist_but_grid", "namelist.input",
                             lambda t: None if t is None else "\n".join(
                                 ln for ln in t.splitlines()
                                 if "nproc_x" not in ln and "nproc_y" not in ln))):
        va, vb = pick(read(dir_a, name)), pick(read(dir_b, name))
        if va is None or vb is None:
            out["differ"][key] = "not recorded in one or both runs"
        elif va == vb:
            out["agree"][key] = True
        else:
            out["differ"][key] = "differs"

    # The raw file is retained in the report for auditability, while the
    # attribution decision uses structured actual/requested values.  A
    # decomposition comparison is valid only when each run's requested grid
    # was actually used and the pair's actual grids differ.
    grid_a = _grid_record(read(dir_a, "proc_grid"), Path(dir_a))
    grid_b = _grid_record(read(dir_b, "proc_grid"), Path(dir_b))
    out["proc_grid_identity"] = {
        "a": {k: grid_a.get(k) for k in ("requested", "actual", "matches", "np", "valid")},
        "b": {k: grid_b.get(k) for k in ("requested", "actual", "matches", "np", "valid")},
    }
    if grid_a.get("valid") and grid_b.get("valid"):
        if grid_a["actual"] == grid_b["actual"]:
            out["differ"]["proc_grid_actual"] = "same actual processor grid"
        else:
            out["differ"]["proc_grid_actual"] = "differs"

    inputs_a = _input_identity(Path(dir_a))
    inputs_b = _input_identity(Path(dir_b))
    input_declared = bool(inputs_a.get("declared") or inputs_b.get("declared"))
    if input_declared:
        if not (inputs_a.get("present") and inputs_b.get("present")):
            out["differ"]["input_sha256"] = "not recorded in one or both runs"
        elif inputs_a["keys"] == inputs_b["keys"]:
            out["agree"]["input_sha256"] = True
        else:
            out["differ"]["input_sha256"] = "differs"
    out["input_identity"] = {
        "required": input_declared,
        "a": {"present": inputs_a.get("present"), "declared": inputs_a.get("declared"),
              "complete": inputs_a.get("complete"), "records": len(inputs_a.get("records", [])),
              "attestation": inputs_a.get("attestation"),
              "canonical_sha256": inputs_a.get("canonical_sha256")},
        "b": {"present": inputs_b.get("present"), "declared": inputs_b.get("declared"),
              "complete": inputs_b.get("complete"), "records": len(inputs_b.get("records", [])),
              "attestation": inputs_b.get("attestation"),
              "canonical_sha256": inputs_b.get("canonical_sha256")},
    }

    must_agree = {"decomposition": ["wrf_exe", "runner", "namelist_but_grid"],
                  "perturbation": ["wrf_exe", "runner", "proc_grid", "namelist"]}[expect]
    if expect == "decomposition":
        if not (grid_a.get("valid") and grid_b.get("valid")):
            raise SystemExit(
                "decomposition attribution requires actual processor grids in both proc_grid records")
        bad_grid = []
        for label, grid in (("A", grid_a), ("B", grid_b)):
            if grid.get("requested") is None:
                bad_grid.append(f"{label} requested grid not recorded")
            elif grid.get("actual") != grid.get("requested") or grid.get("matches") != "yes":
                bad_grid.append(
                    f"{label} requested {grid.get('requested')} but actual is "
                    f"{grid.get('actual')} (matches={grid.get('matches')})")
        if bad_grid:
            raise SystemExit(
                "these runs cannot support decomposition attribution: " + "; ".join(bad_grid))
        if grid_a["actual"] == grid_b["actual"]:
            raise SystemExit(
                "both runs used the same processor grid (actual grid), so there is no "
                "decomposition difference to attribute anything to.")
        if input_declared:
            must_agree.append("input_sha256")
    else:
        # A perturbation comparison must keep the actual decomposition fixed.
        # Parse both records before looking at the requested/raw text; malformed
        # opaque grid strings are not a controlled input perturbation.
        if not (grid_a.get("valid") and grid_b.get("valid")):
            raise SystemExit(
                "perturbation attribution requires valid actual processor grids "
                "in both proc_grid records")
        if grid_a.get("actual") != grid_b.get("actual"):
            raise SystemExit(
                "perturbation attribution requires equal actual processor grids")
        bad_grid = []
        for label, grid in (("A", grid_a), ("B", grid_b)):
            if grid.get("requested") is not None and (
                    grid.get("actual") != grid.get("requested")
                    or grid.get("matches") != "yes"):
                bad_grid.append(
                    f"{label} requested {grid.get('requested')} but actual is "
                    f"{grid.get('actual')} (matches={grid.get('matches')})")
        if bad_grid:
            raise SystemExit(
                "these runs cannot support perturbation attribution: "
                + "; ".join(bad_grid))
        if input_declared:
        # Perturbation identity is useful only if the changed input is recorded;
        # all input hashes must be available and at least one must differ.
            if "input_sha256" not in out["differ"]:
                raise SystemExit(
                    "perturbation attribution requires a recorded input hash difference")
    bad = [k for k in must_agree if k not in out["agree"]]
    if bad:
        raise SystemExit(
            f"these runs are not one {expect} experiment: {bad} "
            f"({ {k: out['differ'].get(k) for k in bad} }). "
            f"A divergence measured across them cannot be attributed to "
            f"{expect}.")
    return out


def comparable(a, b) -> None:
    """Refuse two files that are not the same experiment.

    `coverage` walked `_fields(a)` alone, so a field present only in `b` was
    silently not compared and the count read as agreement. And nothing asked
    whether the two runs share a grid, a field universe or a time axis -- so
    two forecasts of different domains would compare, field by field, and
    report a number.
    """
    import numpy as np
    fa, fb = set(_fields(a)), set(_fields(b))
    if fa != fb:
        raise SystemExit(
            f"field universes differ: only in A {sorted(fa - fb)}; "
            f"only in B {sorted(fb - fa)}")
    ta = _times_values(a, "A")
    tb = _times_values(b, "B")
    if ta.shape != tb.shape or not np.array_equal(ta, tb):
        raise SystemExit(f"time axes differ: A {ta.shape}, B {tb.shape}")
    for v in sorted(fa):
        if a[v].dimensions != b[v].dimensions:
            raise SystemExit(
                f"{v}: dimension order differs: {a[v].dimensions} in A, "
                f"{b[v].dimensions} in B")
        if a[v].shape != b[v].shape:
            raise SystemExit(
                f"{v}: shape {a[v].shape} in A, {b[v].shape} in B")
        if any(size == 0 for size in a[v].shape):
            raise SystemExit(
                f"INSUFFICIENT: {v} has zero numeric cells in the selected population")
    if not fa:
        raise SystemExit(
            "INSUFFICIENT: no common supported numeric fields; Times-only or "
            "metadata-only files cannot establish a divergence result")


def coverage(a, b) -> list:
    """Per frame: how many fields differ, and which are new since the last."""
    import numpy as np
    comparable(a, b)
    out, prev = [], set()
    time_axis = a["Times"].dimensions.index("Time")
    for t in range(a["Times"].shape[time_axis]):
        now = {v for v in _fields(a)
               if not np.array_equal(_num(a[v], t), _num(b[v], t),
                                     equal_nan=False)}
        out.append({"frame": t, "differing": len(now),
                    "new_since_previous": sorted(now - prev),
                    "gone_since_previous": sorted(prev - now)})
        prev = now
    return out


def field_stats(a, b, name: str, t: int, mask=None) -> dict:
    """One field at one frame, conditional AND unconditional.

    NOT-A-NUMBER IS A DIFFERENCE. The test used to be `abs(x - y) > 0`, and
    `abs(nan - 1.0)` is `nan`, which is not greater than zero. So a field that
    went NaN in ONE decomposition and stayed finite in the other reported
    `differing = 0` -- "the two agree everywhere" -- for the one outcome a
    divergence tool exists to catch. `coverage()` calls the same field
    different, because `array_equal` is NaN-correct, so the two statistics this
    module reports contradicted each other exactly there.

    `x != y` is the same test `array_equal` makes, elementwise: NaN differs
    from everything including NaN, so the two now agree by construction. The
    non-finite census is reported beside the counts, because a reader owed the
    number of differing cells is also owed whether they differ by being broken.

    The magnitude statistics are taken over the FINITE differences only. A
    single NaN makes every percentile NaN, which reports nothing about the
    other cells and is not a size.
    """
    import numpy as np
    x = _num(a[name], t)
    y = _num(b[name], t)
    # `inf - inf` is NaN and warns. The NaN is expected and handled -- `finite`
    # excludes it below -- so the warning is noise that would hide a real one.
    # Suppressed around the subtraction only; it changes no value.
    with np.errstate(invalid="ignore"):
        d = np.abs(x - y)
    diff = x != y
    fx, fy = np.isfinite(x), np.isfinite(y)
    finite = np.isfinite(d)
    fd = d[finite]
    out = {"field": name, "frame": t,
           "cells": int(d.size),
           "differing": int(diff.sum()),
           "differing_fraction": float(diff.mean()),
           # THREE WAYS TO DIFFER, AND THEY PARTITION `differing` -- which the
           # first version of this got wrong. "Both non-finite" is NOT one of
           # them: `+inf` against `+inf` is both-non-finite and `x != y` is
           # FALSE, so counting it as a way to differ made the three sum to
           # MORE than `differing`. Two cells of `[+inf, nan]` against
           # themselves gave 0 + 0 + 2 against a `differing` of 1.
           #
           # The both-non-finite cells split: NaN differs from NaN, `+inf` does
           # not. Only the differing half belongs in the partition, and the
           # equal half is reported beside it because "both runs broke in the
           # same place, identically" is a finding of its own.
           "finite_value_differing": int((fx & fy & diff).sum()),
           "finiteness_differing": int((fx ^ fy).sum()),
           "both_nonfinite_differing": int((~fx & ~fy & diff).sum()),
           "both_nonfinite_equal": int((~fx & ~fy & ~diff).sum()),
           "nonfinite_a": int((~fx).sum()),
           "nonfinite_b": int((~fy).sum()),
           # NAMED FOR THE POPULATION THEY ARE OVER. Called `domain_p99` these
           # read as the domain's, and they are not when anything is non-finite:
           # the cells that are excluded are exactly the broken ones.
           "finite_domain_p99": float(np.percentile(fd, 99)) if fd.size else None,
           "finite_domain_p999": float(np.percentile(fd, 99.9)) if fd.size else None,
           "finite_domain_mean_abs": float(fd.mean()) if fd.size else None,
           "finite_signed_mean": _signed_mean(x, y, finite) if fd.size else None}
    cond = diff & finite
    if cond.any():
        out["conditional_p99"] = float(np.percentile(d[cond], 99))
        out["conditional_median"] = float(np.median(d[cond]))
    if mask is not None and mask.any():
        # THE FIXED MASK NEEDS THE FINITE MASK TOO. It is chosen at the FIRST
        # time and followed, so it can easily contain a cell that went
        # non-finite later -- and one of those makes the median and the p99 NaN,
        # which reports nothing about the rest of the held population. The
        # domain statistics above were fixed for this and this one was missed.
        held = mask & finite
        out["fixed_mask_cells"] = int(mask.sum())
        out["fixed_mask_finite_cells"] = int(held.sum())
        out["fixed_mask_nonfinite_cells"] = int((mask & ~finite).sum())
        out["fixed_mask_median"] = (float(np.median(d[held]))
                                    if held.any() else None)
        out["fixed_mask_p99"] = (float(np.percentile(d[held], 99))
                                 if held.any() else None)
    return out


def _ulp_distance(x, y, differs):
    """f32 ULP distance valid across sign, +/-0 and non-finite values.

    The previous form differenced the raw int32 view. That is the ULP distance only
    for two values of the SAME sign: the f32 bit pattern is sign-magnitude, so the
    negatives run backwards and -0.0 (0x80000000) sits a full 2^31 from +0.0. `W`
    crosses zero, so a generic report built on the old form could print an enormous
    ULP for two adjacent values (owner review 3.2). `PH` is a positive geopotential
    series, which is why the published PH fringe result is unaffected.

    Mapping each word onto a monotone line fixes both: complement a negative word,
    set the top bit of a non-negative one. Cells where either side is non-finite have
    no ULP distance and report 0 rather than a number that would be thresholded.
    """
    import numpy as np
    # Normalise -0.0 to +0.0 first. The ordered mapping alone puts them one integer
    # apart, so a pair that IEEE calls equal would report 1 ULP and everything
    # crossing zero would be off by one.
    xf = x.astype(np.float32) + np.float32(0.0)
    yf = y.astype(np.float32) + np.float32(0.0)
    xb = xf.view(np.uint32)
    yb = yf.view(np.uint32)
    def order(b):
        return np.where(b & 0x80000000, ~b, b | 0x80000000).astype("u8").astype("i8")
    finite = np.isfinite(xf) & np.isfinite(yf)
    return np.where(differs & finite, np.abs(order(xb) - order(yb)), 0)


def footprint(a, b, name: str, t: int) -> dict:
    """WHERE along i and along j the difference sits, as a count per column.

    The field COUNT cannot tell a difference made at a patch boundary from one
    made everywhere: both report the same 77. `FINDING_seam_is_i_specific_v1`
    established that cutting i produces the difference and cutting j does not,
    and left open what in the i-split produces it. A difference banded at the
    patch boundaries and a difference already spread across the domain point at
    different mechanisms, and collapsing the differing cells onto each axis is
    what separates them.

    The test is `x != y`, the same one `field_stats` and `coverage` make, so a
    field that went NaN on one side counts as differing here too.
    """
    import numpy as np
    x, y = _num(a[name], t), _num(b[name], t)
    d = x != y
    keep_i = tuple(r for r in range(d.ndim) if r != d.ndim - 1)
    keep_j = tuple(r for r in range(d.ndim) if r != d.ndim - 2)
    per_i, per_j = d.sum(axis=keep_i), d.sum(axis=keep_j)
    # SUPPORT IS NOT SIZE. The counts above are the width of the set of cells
    # that differ AT ALL, which locates a source and says nothing about whether
    # the band's edge is one ULP or the same size as its centre (owner review
    # 5.2). The magnitude per column is the other half, and it is one more
    # reduction over the array already loaded.
    with np.errstate(invalid="ignore"):
        gap = np.abs(x.astype("f8") - y.astype("f8"))
    gap = np.where(np.isfinite(gap), gap, 0.0)
    # The reader hands back f8, so the f32 words have to be recovered before they can
    # be viewed as integers -- viewing the f8 array gives twice as many int32s and
    # compares the wrong halves. _ulp_distance does that recovery and the ordered-bit
    # mapping; see its note for why the raw int32 difference was not general.
    ulp = _ulp_distance(x, y, d)
    # A HALF-PEAK core is not an energetic core (owner review 3.1). Both a peak that
    # grows and surroundings that do not move narrow it, so "the core does not widen"
    # cannot be read as "the difference energy stays localized". The per-column L2
    # answers the energy question directly and is one more reduction over an array
    # already in memory; the 50%/90% widths are derived downstream from i_l2.
    i_l2 = np.sqrt((gap ** 2).sum(axis=keep_i))
    return {"field": name, "frame": t,
            "i_counts": [int(v) for v in per_i],
            "j_counts": [int(v) for v in per_j],
            "i_absmax": [float(v) for v in gap.max(axis=keep_i)],
            "i_l2": [float(v) for v in i_l2],
            "i_ulpmax": [int(v) for v in ulp.max(axis=keep_i)],
            "cells_per_i": int(d.size // d.shape[-1]),
            "cells_per_j": int(d.size // d.shape[-2])}


def core_widths(absmax, l2) -> dict:
    """Three widths side by side, because they answer different questions.

    `half_peak` is the count of columns whose per-column max |diff| is at least half
    that frame's peak. It is a SUPPORT relative to a moving peak: a boundary value
    that grows faster than its surroundings narrows it without any energy moving
    (owner review 3.1), so it cannot carry a claim about localization on its own.

    `l2_50` / `l2_90` are the narrowest CONTIGUOUS windows containing the
    peak-energy column that hold 50% / 90% of the summed per-column energy. Those
    are the ones that answer "did the difference energy stay localized".

    Searched exhaustively, not grown greedily. Extending toward the heavier
    immediate neighbour does not minimise the window: with energies
    `[2, 2, 100, 1, 100]` and the peak in the middle, 90% needs width 3 (peak plus
    the two columns to its right), but a greedy step takes the 2 on the left twice
    before it ever reaches the 100 on the right. The domain is ~235 columns wide,
    so the exhaustive search costs nothing.
    """
    n = len(absmax)
    peak = max(absmax) if n else 0.0
    half = sum(1 for v in absmax if peak > 0.0 and v >= 0.5 * peak)
    e = [v * v for v in l2]
    total = sum(e)
    out = {"half_peak": half, "l2_50": 0, "l2_90": 0,
           "l2_peak_column": (max(range(n), key=lambda i: e[i]) + 1) if n and total > 0 else 0}
    if total <= 0.0:
        return out
    c = out["l2_peak_column"] - 1
    pre = [0.0]
    for v in e:
        pre.append(pre[-1] + v)
    for frac, key in ((0.5, "l2_50"), (0.9, "l2_90")):
        want, best = frac * total, n
        for lo in range(c + 1):
            for hi in range(max(c, lo), n):
                if pre[hi + 1] - pre[lo] >= want:
                    best = min(best, hi - lo + 1)
                    break
        out[key] = best
    return out


def _profile(counts, per, width: int = 58) -> str:
    """The per-column fractions as one line, so the shape is readable at all."""
    bar = " .:-=+*#%@"
    n = len(counts)
    out = []
    for s in range(width):
        lo, hi = s * n // width, max(s * n // width + 1, (s + 1) * n // width)
        f = max(counts[lo:hi]) / per if per else 0.0
        out.append(bar[min(len(bar) - 1, int(f * (len(bar) - 1) + 0.999))])
    return "".join(out)


def _span(counts) -> str:
    hit = [i for i, c in enumerate(counts) if c]
    if not hit:
        return "none"
    return f"{hit[0] + 1}..{hit[-1] + 1} ({len(hit)} of {len(counts)})"


def cell_area(state_path: Path, a, *, expected_sha256: str | None = None):
    """`A_ij = DX*DY / MAPFAC_M**2`, from a file that carries the map factor.

    The forecast frames here do not; `wrfinput_d01` does. Without it every
    spatial statistic is a grid-cell one, which this module labels as such.
    """
    import hashlib
    import netCDF4
    state_path = Path(state_path)
    if not state_path.is_file():
        raise SystemExit(f"MAPFAC provenance file is not a regular file: {state_path}")
    actual_sha = hashlib.sha256(state_path.read_bytes()).hexdigest()
    if expected_sha256 is None:
        raise SystemExit(
            "MAPFAC provenance is required: pass --mapfac-sha256 for bare files "
            "or use run-directory input identity")
    if (not isinstance(expected_sha256, str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256)
            or expected_sha256.lower() != actual_sha):
        raise SystemExit(
            f"MAPFAC file hash does not match the declared run identity "
            f"(actual {actual_sha})")
    with netCDF4.Dataset(str(state_path)) as d:
        if "MAPFAC_M" not in d.variables:
            raise SystemExit(f"{state_path}: MAPFAC_M is missing")
        # MAPFAC_M has no Time axis; read its complete two-dimensional field,
        # rather than treating index 0 as a frame selector.
        mf = _num(d["MAPFAC_M"], None)
        try:
            dx, dy = float(d.getncattr("DX")), float(d.getncattr("DY"))
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise SystemExit(f"{state_path}: DX/DY map provenance is missing or invalid") from exc
        import numpy as np
        if not (np.isfinite(dx) and np.isfinite(dy) and dx > 0.0 and dy > 0.0):
            raise SystemExit(f"{state_path}: DX and DY must be finite and positive")
        if not np.all(np.isfinite(mf)) or not np.all(mf > 0.0):
            raise SystemExit(
                f"{state_path}: MAPFAC_M must be finite and strictly positive")
    # The map factor must be THIS domain's. A wrfinput from another run of the
    # same grid size would pass silently and weight every cell wrongly.
    ref = a["RAINNC"].shape[-2:] if "RAINNC" in a.variables else a["T"].shape[-2:]
    if mf.shape != tuple(ref):
        raise SystemExit(f"MAPFAC_M is {mf.shape}, the forecast grid is {tuple(ref)}")
    for key in ("DX", "DY"):
        if key in a.ncattrs() and abs(float(a.getncattr(key)) - (dx if key == "DX" else dy)) > 1e-6:
            raise SystemExit(f"{key} differs between the map-factor file and the forecast")
    return dx * dy / (mf * mf)


def _mapfac_sha_for_runs(state_path: Path, run_dirs: list[Path]) -> str:
    """Bind the map-factor file to every run's active input record."""
    import hashlib
    actual = hashlib.sha256(Path(state_path).read_bytes()).hexdigest()
    for run_dir in run_dirs:
        identity = _input_identity(Path(run_dir))
        if not identity.get("declared"):
            raise SystemExit(
                f"{run_dir}: MAPFAC comparison requires declared active input identity")
        matches = []
        for rec in identity.get("records", []):
            name = Path(str(rec.get("name", ""))).name
            resolved = Path(str(rec.get("resolved_path", ""))).name
            if name == Path(state_path).name or resolved == Path(state_path).name:
                matches.append(rec)
        if len(matches) != 1:
            raise SystemExit(
                f"{run_dir}: MAPFAC file {Path(state_path).name} is not uniquely "
                "bound to an active input record")
        rec = matches[0]
        if rec.get("sha256_before", rec.get("sha256", "")).lower() != actual:
            raise SystemExit(
                f"{run_dir}: MAPFAC file hash differs from its active input record")
    return actual


def precipitation(a, b, t: int, name: str = "RAINNC", area=None) -> dict:
    """Signed and thresholded, because `|dP|` cannot tell more rain from
    rain somewhere else."""
    import numpy as np
    x = _num(a[name], t)
    y = _num(b[name], t)
    d = y - x
    # UNITS. `RAINNC` is mm per column, so a bare sum is mm x columns and is
    # not a depth. The domain MEAN is a depth; the sum is reported as what it
    # is, and the cancellation RATIO is dimensionless and unaffected either way
    # (owner review §11). A volume needs cell areas, which this frame does not
    # carry, so it is not claimed.
    # GRID-CELL mean, not area-weighted. On a map projection the cells differ
    # in area, so this is a model-grid statistic and not a domain precipitation
    # depth; a volume would need MAPFAC_M, which this frame does not carry
    # (owner review §12.2).
    # NON-FINITE, the same hole `field_stats` had. `abs(nan) > thr` is False,
    # so a column that went NaN counts as NOT exceeding every threshold and the
    # exceedance fractions understate silently. `reflectivity` is immune by
    # construction -- its physical screen drops NaN and reports the count -- so
    # this is the one of the three that needed the census made explicit.
    finite = np.isfinite(d)
    fd = d[finite]
    n = fd.size
    out = {"field": name, "frame": t,
           "signed_gridcell_mean_mm": float(fd.mean()) if n else None,
           "signed_sum_mm_times_columns": float(fd.sum()) if n else None,
           "gross_sum_mm_times_columns": float(np.abs(fd).sum()) if n else None,
           "cancellation_ratio": (float(abs(fd.sum()) / np.abs(fd).sum())
                                  if n and np.abs(fd).sum() else None),
           "columns": int(d.size),
           "nonfinite_columns": int((~finite).sum())}
    if area is not None:
        # AREA-WEIGHTED, which a grid-cell mean is not on a map projection.
        # Volume in m^3 of liquid water: mm -> m is 1e-3.
        af = np.asarray(area)[finite]
        out["area_weighted_mean_mm"] = float((fd * af).sum() / af.sum()) if n else None
        out["signed_volume_m3"] = float((fd * af).sum() * 1e-3) if n else None
        out["gross_volume_m3"] = float((np.abs(fd) * af).sum() * 1e-3) if n else None
    for thr in (1e-3, 1e-2, 1e-1):
        # over the FINITE columns; `nonfinite_columns` says how many are not in
        # this population, so the fraction has a stated denominator.
        out[f"fraction_over_{thr:g}mm"] = (float((np.abs(fd) > thr).mean())
                                           if n else None)
        out[f"columns_over_{thr:g}mm"] = int((np.abs(fd) > thr).sum())
    return out


def reflectivity(a, b, t: int, name: str = "REFL_10CM", area=None) -> dict:
    """Screened to the physical range, in linear Z, and as threshold AREAS."""
    import numpy as np
    x = _num(a[name], t)
    y = _num(b[name], t)
    lo, hi = REFL_PHYSICAL
    ok = (x >= lo) & (x <= hi) & (y >= lo) & (y <= hi)
    out = {"field": name, "frame": t,
           "physical_fraction": float(ok.mean()),
           "outside_physical": int((~ok).sum())}
    if ok.any():
        d = np.abs(x - y)[ok]
        out["screened_p99_dbz"] = float(np.percentile(d, 99))
        out["screened_max_dbz"] = float(d.max())
        zx, zy = 10.0 ** (x[ok] / 10.0), 10.0 ** (y[ok] / 10.0)
        r = np.where(zx > 0, zy / np.where(zx > 0, zx, 1.0), np.nan)
        out["linear_Z_ratio_p99"] = float(np.nanpercentile(r, 99))
    # CELL COUNTS, not areas. A physical area needs the map factor,
    #     A_ij = DX*DY / MAPFAC_M_ij**2
    # and this frame does not carry MAPFAC_M, so the count is reported as a
    # count and the word "area" is not used (owner review §12.1).
    for thr in (10.0, 20.0, 30.0, 40.0):
        ma, mb = (x >= thr) & (x <= hi), (y >= thr) & (y <= hi)
        out[f"cells_over_{thr:g}dbz_a"] = int(ma.sum())
        out[f"cells_over_{thr:g}dbz_b"] = int(mb.sum())
        if area is not None:
            # the column is a cell; area weighting collapses the vertical
            ca, cb = ma.any(axis=0), mb.any(axis=0)
            out[f"area_km2_over_{thr:g}dbz_a"] = float((ca * area).sum() * 1e-6)
            out[f"area_km2_over_{thr:g}dbz_b"] = float((cb * area).sum() * 1e-6)
    return out


def _fmt(v, spec: str = ".3e") -> str:
    """A missing or empty population prints as itself, not as `nan`.

    The row fell back to `float('nan')` when a field had no held population at
    all -- RAINNC, whose fixed mask is empty -- and a printed `nan` reads as a
    measurement that came out undefined rather than as one that was never
    taken.

    The precipitation row formatted its values directly, which crashed on
    `cancellation_ratio`. That field is None in exactly one case: the gross sum
    is zero, because the two decompositions AGREE. So the summary was reachable
    only while the runs still differed, and the first pair that matched took the
    whole report down -- including the JSON, written further on. Every printed
    statistic there is None on an empty population, so all of them go through
    here.
    """
    return "-" if v is None else format(v, spec)


def main() -> int:
    import netCDF4
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("run_a", type=Path,
                    help="a run DIRECTORY (gated) or a forecast file (ungated)")
    ap.add_argument("run_b", type=Path)
    ap.add_argument("--expect", choices=["decomposition", "perturbation"],
                    default="decomposition",
                    help="what the two runs are allowed to differ in")
    ap.add_argument("--frames", default="1,5,10")
    ap.add_argument("--fixed-mask-frame", type=int, default=1)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--footprint", default=None, metavar="FIELD[,FIELD]",
                    help="also report WHERE the difference sits: the differing "
                         "cells collapsed onto i and onto j, per column")
    ap.add_argument("--mapfac-from", type=Path, default=None,
                    help="a file carrying MAPFAC_M and DX/DY (wrfinput_d01); "
                         "enables area-weighted precipitation and area in km2")
    ap.add_argument("--mapfac-sha256", default=None,
                    help="sha256 of --mapfac-from when comparing bare forecast "
                         "files; run-directory comparisons derive it from the "
                         "active input identity")
    args = ap.parse_args()
    # THE GATE RUNS HERE, OR THE ARTIFACT SAYS IT DID NOT. same_experiment() was
    # written and then called from nothing, so every comparison this CLI made
    # was ungated -- a guard that exists and does not guard is worse than none,
    # because its existence reads as protection (owner review 7).
    #
    # A RUN DIRECTORY carries the metadata that settles attribution; a bare
    # forecast file does not. Both are accepted, and the difference is recorded:
    # given directories the gate runs and a mismatch refuses; given files the
    # comparison proceeds and says, in the JSON and on stderr, that no
    # experiment gate was applied.
    gate = None
    if args.run_a.is_dir() and args.run_b.is_dir():
        gate = same_experiment(args.run_a, args.run_b, expect=args.expect)
        file_a, file_b = _forecast_in(args.run_a), _forecast_in(args.run_b)
    elif args.run_a.is_dir() or args.run_b.is_dir():
        raise SystemExit("pass two run directories or two files, not one of each")
    else:
        file_a, file_b = args.run_a, args.run_b
        print("g33_mpi_divergence: NO EXPERIMENT GATE. These are forecast files, "
              "so nothing here checked that the two runs share a binary, a "
              "runner, a namelist or an input. Pass the run DIRECTORIES to have "
              "that checked.", file=sys.stderr)
    a, b = netCDF4.Dataset(str(file_a)), netCDF4.Dataset(str(file_b))
    # History labels are the time boundary for every requested statistic.  Do
    # this typed check before map-factor setup or frame indexing so a missing
    # label cannot escape as a netCDF traceback or an apparent empty result.
    times_a = _times_values(a, "A")
    times_b = _times_values(b, "B")
    if args.mapfac_from:
        if gate is not None:
            map_sha = _mapfac_sha_for_runs(args.mapfac_from,
                                           [args.run_a, args.run_b])
        else:
            map_sha = args.mapfac_sha256
            if map_sha is None:
                raise SystemExit(
                    "--mapfac-sha256 is required with bare forecast files")
        area = cell_area(args.mapfac_from, a, expected_sha256=map_sha)
    else:
        area = None
    frames = [int(f) for f in args.frames.split(",")]

    # THE REQUESTED FRAMES MUST EXIST. Asking for minute 10 of a one-minute run
    # raised `IndexError: index exceeds dimension bounds` from inside netCDF4 --
    # true, and it names neither the frame nor the file. A comparison that
    # cannot be made should say which one and stop.
    n_frames_a = times_a.shape[a["Times"].dimensions.index("Time")]
    n_frames_b = times_b.shape[b["Times"].dimensions.index("Time")]
    missing = [f for f in frames
               if f >= n_frames_a or f < -n_frames_a
               or f >= n_frames_b or f < -n_frames_b]
    if missing:
        raise SystemExit(
            f"these runs carry {n_frames_a} and {n_frames_b} frames "
            f"(0..{min(n_frames_a, n_frames_b) - 1}) and "
            f"frames {missing} were asked for. Pass --frames with what the "
            f"files actually hold.")
    fixed = args.fixed_mask_frame
    if (fixed < -n_frames_a or fixed >= n_frames_a
            or fixed < -n_frames_b or fixed >= n_frames_b):
        raise SystemExit(
            f"--fixed-mask-frame {fixed} is outside both runs' frame ranges "
            f"(A={n_frames_a}, B={n_frames_b}); choose an existing frame")
    cov = coverage(a, b)
    print("  frame  differing fields   new since previous")
    for row in cov:
        new = ", ".join(row["new_since_previous"][:8])
        print(f"  {row['frame']:5d}  {row['differing']:16d}   "
              f"{new[:70]}{'...' if len(new) > 70 else ''}")

    masks = {}
    for name in ("T", "REFL_10CM", "QVAPOR"):
        if name in a.variables:
            x = _num(a[name], args.fixed_mask_frame)
            y = _num(b[name], args.fixed_mask_frame)
            masks[name] = x != y

    # THE ARTIFACT SAYS WHETHER IT WAS GATED. A reader cannot tell from the
    # numbers whether the two runs were one experiment, so the answer travels
    # with them -- including "not checked", which is not the same as "checked
    # and fine".
    doc = {"experiment_gate": gate if gate is not None else {
               "applied": False,
               "why": "compared forecast FILES, not run directories; nothing "
                      "checked that the two runs share a binary, runner, "
                      "namelist or input"},
           "coverage": cov, "fields": [], "precipitation": [],
           "reflectivity": [], "fixed_mask_frame": args.fixed_mask_frame,
           "mapfac_sha256": (map_sha if args.mapfac_from else None)}
    print(f"\n  {'field':10s} {'t':>3s} {'differ':>8s} {'cond p99':>11s} "
          f"{'domain p99':>11s} {'fixed-mask med':>15s}")
    for t in frames:
        for name in ("T", "QVAPOR", "REFL_10CM", "RAINNC"):
            if name not in a.variables:
                continue
            r = field_stats(a, b, name, t, masks.get(name))
            doc["fields"].append(r)
            print(f"  {name:10s} {t:>3d} {r['differing_fraction']:7.2%} "
                  f"{_fmt(r.get('conditional_p99')):>11s} "
                  f"{_fmt(r.get('finite_domain_p99')):>11s} "
                  f"{_fmt(r.get('fixed_mask_median')):>15s}")
        if "RAINNC" in a.variables:
            doc["precipitation"].append(precipitation(a, b, t, area=area))
        if "REFL_10CM" in a.variables:
            doc["reflectivity"].append(reflectivity(a, b, t, area=area))

    if args.footprint:
        doc["footprint"] = []
        print(f"\n  {'field':10s} {'t':>3s} {'axis':>4s} {'columns that differ':>22s}"
              f"  profile (max per bucket, . = few  @ = all)")
        for t in frames:
            for name in args.footprint.split(","):
                if name not in a.variables:
                    print(f"  {name:10s} {t:>3d}   --  not in the forecast file")
                    continue
                r = footprint(a, b, name, t)
                r["core_widths"] = core_widths(r["i_absmax"], r["i_l2"])
                doc["footprint"].append(r)
                for ax, counts, per in (("i", r["i_counts"], r["cells_per_i"]),
                                        ("j", r["j_counts"], r["cells_per_j"])):
                    print(f"  {name:10s} {t:>3d} {ax:>4s} {_span(counts):>22s}"
                          f"  {_profile(counts, per)}")
                w = r["core_widths"]
                print(f"  {'':10s} {'':>3s}      half-peak {w['half_peak']:>3d} cols |"
                      f"  L2-50% {w['l2_50']:>3d} |  L2-90% {w['l2_90']:>3d}"
                      f"  (peak-energy column {w['l2_peak_column']})")

    # The JSON is the measurement; the tables below are a reading of it. It is
    # written FIRST so a formatting fault cannot destroy the result it reports.
    if args.json:
        args.json.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n")

    print(f"\n  {'t':>3s} {'signed cell-mean':>17s} {'cancel ratio':>13s} "
          f"{'>1e-3':>9s} {'>1e-2':>9s} {'>1e-1':>9s}")
    for r in doc["precipitation"]:
        print(f"  {r['frame']:>3d} {_fmt(r['signed_gridcell_mean_mm'], '.4e'):>17s} "
              f"{_fmt(r['cancellation_ratio'], '.4f'):>13s} "
              f"{_fmt(r['fraction_over_0.001mm'], '.3%'):>9s} "
              f"{_fmt(r['fraction_over_0.01mm'], '.3%'):>9s} "
              f"{_fmt(r['fraction_over_0.1mm'], '.3%'):>9s}")

    print(f"\n  {'t':>3s} {'in-range':>9s} {'screened p99':>13s} "
          f"{'>20dBZ cells a':>14s} {'cells b':>9s}")
    for r in doc["reflectivity"]:
        print(f"  {r['frame']:>3d} {r['physical_fraction']:8.3%} "
              f"{_fmt(r.get('screened_p99_dbz'), '.4f'):>13s} "
              f"{r['cells_over_20dbz_a']:14d} {r['cells_over_20dbz_b']:9d}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
