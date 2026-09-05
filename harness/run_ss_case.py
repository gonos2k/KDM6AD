#!/usr/bin/env python3
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path


def replace_line(text: str, key: str, value: str) -> str:
    lines=[]
    done=False
    for line in text.splitlines():
        stripped=line.strip()
        # exact-key match: key must be followed by '=' (after optional spaces),
        # so 'history_interval' does NOT clobber 'history_interval_s'.
        if stripped.startswith(key) and stripped[len(key):].lstrip().startswith('='):
            prefix=line[:len(line)-len(line.lstrip())]
            lines.append(f"{prefix}{key:<36}= {value},")
            done=True
        else:
            lines.append(line)
    if not done:
        raise SystemExit(f"missing namelist key {key}")
    return "\n".join(lines)+"\n"


def set_or_insert(text: str, key: str, value: str, section: str = "&domains") -> str:
    """Set `key`, inserting it into `section` when the namelist does not carry it.

    `replace_line` REFUSES a missing key, which is right for keys the namelist is
    supposed to have -- a typo there should stop the run, not silently add a new
    setting. `nproc_x`/`nproc_y` are different: WRF chooses the decomposition
    itself unless told, so their absence is the normal state and inserting them
    is the point.
    """
    try:
        return replace_line(text, key, value)
    except SystemExit:
        pass
    lines, done = [], False
    for line in text.splitlines():
        lines.append(line)
        if not done and line.strip().lower().startswith(section):
            lines.append(f" {key:<36}= {value},")
            done = True
    if not done:
        raise SystemExit(f"cannot insert {key}: no {section} section in the namelist")
    return "\n".join(lines) + "\n"


def remove_keys(text: str, keys: set[str]) -> str:
    out=[]
    for line in text.splitlines():
        stripped=line.strip()
        # exact-key match (same predicate as replace_line): key must be immediately
        # followed by '=', so 'fogvis_clw_min' does NOT also drop 'fogvis_clw_min_gm3'.
        if any(stripped.startswith(key) and stripped[len(key):].lstrip().startswith('=')
               for key in keys):
            continue
        out.append(line)
    return "\n".join(out)+"\n"


def parse_proc_grid(rsl_text: str) -> str | None:
    """The decomposition WRF actually used, as `NXxNY`, from rsl.error.0000.

    `--proc-grid` only pre-checks that the two factors multiply to `--np`. WRF
    is free to do something else -- and a run whose grid is not the requested
    one is a different experiment wearing the requested one's directory name
    (owner review 9.5). Returns None when the lines are not there, which is
    reported as "not found" rather than as agreement.
    """
    # A partial answer is not a grid.  Require one unambiguous X/Y pair; WRF
    # startup text can be concatenated from multiple logs, and silently using
    # the first pair would make the recorded actual decomposition unreliable.
    x = re.findall(r"\bntasks\s+in\s+x\s+(\d+)", rsl_text, re.IGNORECASE)
    y = re.findall(r"\bntasks\s+in\s+y\s+(\d+)", rsl_text, re.IGNORECASE)
    if len(x) != 1 or len(y) != 1:
        return None
    return f"{x[0]}x{y[0]}"


class NamelistInputError(ValueError):
    """The active input set cannot be resolved without guessing."""


def _strip_namelist_comments(text: str) -> str:
    """Remove Fortran ``!`` comments while preserving quoted ``!`` bytes."""
    out: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(text):
        c = text[i]
        if quote is not None:
            out.append(c)
            # Fortran escapes a quote in a string by doubling it.
            if c == quote and i + 1 < len(text) and text[i + 1] == quote:
                out.append(text[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in ("'", '"'):
            quote = c
            out.append(c)
        elif c == "!":
            while i < len(text) and text[i] != "\n":
                i += 1
            if i < len(text):
                out.append("\n")
        else:
            out.append(c)
        i += 1
    if quote is not None:
        raise NamelistInputError("unterminated quoted string in namelist")
    return "".join(out)


_NML_ASSIGNMENT = re.compile(r"(?im)^[ \t]*([a-z][a-z0-9_]*)[ \t]*=")
_NML_SECTION = re.compile(r"(?im)^[ \t]*&[a-z][a-z0-9_]*\b")
_NML_SECTION_END = re.compile(r"(?m)^[ \t]*/[ \t]*(?:!.*)?$")


def _namelist_assignments(text: str) -> dict[str, list[str]]:
    """Read ordinary one-key-per-line Fortran namelist assignments.

    This intentionally does not pretend to be a general Fortran parser.  WRF
    namelists use this form for the input-name and interval controls.  A
    duplicate key, an assignment outside a namelist section, or a same-line
    multi-assignment is rejected so a provenance record never reflects a
    guessed file set.
    """
    clean = _strip_namelist_comments(text)
    if re.search(r"(?im)^\s*@?include\b", clean):
        raise NamelistInputError("namelist include directives are unsupported")
    matches = list(_NML_ASSIGNMENT.finditer(clean))
    if not matches:
        if "=" in clean:
            raise NamelistInputError(
                "unsupported namelist layout: assignments must start on their own line")
        return {}
    sections = list(_NML_SECTION.finditer(clean))
    closes = list(_NML_SECTION_END.finditer(clean))
    assignments: dict[str, list[str]] = {}
    for i, match in enumerate(matches):
        key = match.group(1).lower()
        line_start = clean.rfind("\n", 0, match.start()) + 1
        section_starts = [s.start() for s in sections if s.start() < line_start]
        close_starts = [s.start() for s in closes if s.start() < line_start]
        section_start = max(section_starts, default=-1)
        section_end = max(close_starts, default=-1)
        if section_start <= section_end:
            raise NamelistInputError(f"assignment {key!r} is outside a namelist section")
        end = matches[i + 1].start() if i + 1 < len(matches) else len(clean)
        section_close = _NML_SECTION_END.search(clean, match.end(), end)
        if section_close:
            end = section_close.start()
        raw = clean[match.end():end].strip()
        if not raw:
            raise NamelistInputError(f"namelist key {key} has no value")
        # A second `key =` before the next line assignment is a syntax form this
        # small reader cannot safely distinguish from a string/value typo.
        if re.search(r"(?im),[ \t]*[a-z][a-z0-9_]*[ \t]*=", raw):
            raise NamelistInputError(
                f"same-line multiple assignments near namelist key {key}")
        if key in assignments:
            raise NamelistInputError(f"duplicate namelist key {key}")
        assignments[key] = _split_namelist_values(raw)
    return assignments


def _split_namelist_values(raw: str) -> list[str]:
    values: list[str] = []
    token: list[str] = []
    quote: str | None = None
    i = 0
    while i < len(raw):
        c = raw[i]
        if quote is not None:
            token.append(c)
            if c == quote and i + 1 < len(raw) and raw[i + 1] == quote:
                token.append(raw[i + 1])
                i += 2
                continue
            if c == quote:
                quote = None
        elif c in ("'", '"'):
            quote = c
            token.append(c)
        elif c == ",":
            if token:
                values.append("".join(token).strip())
                token = []
        else:
            token.append(c)
        i += 1
    if quote is not None:
        raise NamelistInputError("unterminated quoted value in namelist")
    if token and "".join(token).strip():
        values.append("".join(token).strip())

    expanded: list[str] = []
    for value in values:
        m = re.fullmatch(r"(\d+)\*(.+)", value, re.DOTALL)
        if m:
            expanded.extend([m.group(2).strip()] * int(m.group(1)))
        else:
            expanded.append(value)
    return expanded


def _unquote_namelist_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1].replace(value[0] * 2, value[0])
    return value


def _domain_value(values: list[str], domain: int, *, max_dom: int | None = None,
                  key: str = "value", scalar_ok: bool = False) -> str:
    """Select one explicitly supplied domain value.

    WRF has several repeat-last and defaulting rules, but this audit helper is
    deliberately narrower: it may consume a scalar interval (a declared value
    applied to every domain), an exact per-domain list, or a scalar filename
    containing ``<domain>``.  A scalar literal filename for a multi-domain run
    is ambiguous and therefore fails closed instead of guessing that WRF will
    repeat it.
    """
    if not values:
        return ""
    if max_dom is None:
        # Kept for small callers that need the first value only.  Resolution of
        # active inputs always supplies max_dom and therefore gets the strict
        # cardinality checks below.
        return _unquote_namelist_value(values[domain - 1]) if domain <= len(values) else ""
    if len(values) == max_dom:
        return _unquote_namelist_value(values[domain - 1])
    if len(values) == 1 and (scalar_ok or max_dom == 1):
        return _unquote_namelist_value(values[0])
    if len(values) == 1 and "<domain>" in values[0].lower():
        return _unquote_namelist_value(values[0])
    raise NamelistInputError(
        f"{key} supplies {len(values)} value(s) for max_dom={max_dom}; "
        "use one explicit value per domain or a <domain> filename pattern")


def _parse_max_dom(assignments: dict[str, list[str]]) -> int:
    values = assignments.get("max_dom", ["1"])
    if len(values) != 1:
        raise NamelistInputError("max_dom must have exactly one integer value")
    raw = _unquote_namelist_value(values[0]).strip()
    if not re.fullmatch(r"[+-]?\d+", raw):
        raise NamelistInputError("max_dom must be an integer (fractional values are unsupported)")
    max_dom = int(raw)
    if max_dom < 1:
        raise NamelistInputError("max_dom must be positive")
    return max_dom


def resolve_active_namelist_inputs(text: str) -> list[dict[str, str]]:
    """Resolve active initial, boundary, and auxiliary input files.

    The returned paths are the names WRF receives after ``<domain>`` expansion.
    Only ordinary WRF namelists are supported: one assignment per line, no
    ``include``/macro expansion, and explicit ``auxinputN_interval`` controls.
    Unsupported syntax raises :class:`NamelistInputError` instead of silently
    assuming that only ``wrfinput`` exists.
    """
    assignments = _namelist_assignments(text)
    max_dom = _parse_max_dom(assignments)

    specs: list[dict[str, str]] = []

    def add_names(key: str, kind: str, active: list[bool] | None = None) -> None:
        values = assignments.get(key)
        if values is None:
            return
        for domain in range(1, max_dom + 1):
            name = _domain_value(values, domain, max_dom=max_dom, key=key)
            is_active = active is None or active[domain - 1]
            if not is_active:
                continue
            if not name:
                raise NamelistInputError(
                    f"active {key} has an empty value for domain d{domain:02d}")
            if any(ch in name for ch in "*?"):
                raise NamelistInputError(
                    f"wildcard {key} value is unsupported: {name!r}")
            # WRF's ``<domain>`` token is the numeric suffix (``01``), while
            # the surrounding ``d`` is supplied by the caller's pattern.
            resolved_name = re.sub(r"<domain>", f"{domain:02d}", name,
                                   flags=re.IGNORECASE)
            specs.append({"kind": kind, "domain": f"d{domain:02d}",
                          "name": resolved_name})

    add_names("input_inname", "init")
    add_names("bdy_inname", "boundary")
    for key in sorted(k for k in assignments if re.fullmatch(r"auxinput\d+_inname", k)):
        number = key[len("auxinput"): -len("_inname")]
        interval = assignments.get(f"auxinput{number}_interval")
        interval_s = assignments.get(f"auxinput{number}_interval_s")
        if interval is None and interval_s is None:
            raise NamelistInputError(
                f"{key} has no explicit interval; auxiliary activation/default "
                "scope is unsupported")
        active: list[bool] | None = None
        active = []
        for domain in range(1, max_dom + 1):
            vals = []
            for source in (interval, interval_s):
                if source is not None:
                    raw = _domain_value(source, domain, max_dom=max_dom,
                                        key=f"auxinput{number} interval",
                                        scalar_ok=True)
                    try:
                        vals.append(float(raw))
                    except ValueError as exc:
                        raise NamelistInputError(
                            f"auxinput{number} interval must be numeric") from exc
            active.append(any(v > 0 for v in vals))
        add_names(key, f"auxinput{number}", active)
    return specs


def hash_resolved_inputs(run: Path, specs: list[dict[str, str]]) -> dict:
    """Hash each resolved active input, retaining missing/error facts."""
    records: list[dict] = []
    for spec in specs:
        candidate = Path(spec["name"])
        resolved = candidate if candidate.is_absolute() else run / candidate
        resolved = resolved.resolve(strict=False)
        rec = {**spec, "resolved_path": str(resolved),
               "sha256_before": None, "sha256_after": None,
               "sha256": None, "status": "missing"}
        try:
            digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        except OSError as exc:
            rec["error"] = str(exc)
        else:
            rec.update({"sha256_before": digest, "sha256": digest,
                        "status": "ok"})
        records.append(rec)
    identity = {"schema": 1, "declared": bool(records),
            "parser_scope": "ordinary WRF assignments; no include/macro expansion",
            "records": records,
            "complete": all(r["status"] == "ok" for r in records)}
    if records:
        identity["canonical_sha256"] = canonical_input_sha256(identity)
    return identity


def refresh_input_hashes(identity: dict) -> None:
    """Fill the after-run hashes and flag an input changed while WRF ran."""
    for rec in identity.get("records", []):
        try:
            after = hashlib.sha256(Path(rec["resolved_path"]).read_bytes()).hexdigest()
        except OSError as exc:
            rec["after_error"] = str(exc)
            rec["status_after"] = "missing"
            rec["sha256_after"] = None
        else:
            rec["sha256_after"] = after
            rec["status_after"] = "ok"
        rec["stable"] = (rec.get("sha256_before") is not None
                          and rec.get("sha256_before") == rec.get("sha256_after"))
    identity["complete"] = all(r.get("status") == "ok" and r.get("stable")
                                for r in identity.get("records", []))


def canonical_input_sha256(identity: dict) -> str:
    """Hash the producer's path-independent input identity records.

    Resolved paths are intentionally excluded: they identify where the producer
    read a file on its host, while the canonical identity is the ordered set of
    active kind/domain/name/hash records.  This digest attests to the recorded
    bytes; it does not claim that an archived run directory still contains the
    historical input files.
    """
    records = identity.get("records", identity) if isinstance(identity, dict) else identity
    canonical = []
    for rec in records or []:
        if not isinstance(rec, dict):
            continue
        canonical.append({
            "kind": rec.get("kind"),
            "domain": rec.get("domain"),
            "name": rec.get("name"),
            "sha256": rec.get("sha256_before", rec.get("sha256")),
        })
    canonical.sort(key=lambda r: (str(r["kind"]), str(r["domain"]),
                                 str(r["name"])))
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def campaign_id_from_controls(controls: dict) -> str:
    """Return the campaign identity for the producer's canonical controls.

    This is deliberately a public producer function so consumers can recompute
    the identity from the stored controls.  The resulting digest is an
    integrity/self-consistency check; it does not authenticate who supplied the
    controls or prove that a caller's expected schema is scientifically true.
    """
    if not isinstance(controls, dict):
        raise ValueError("campaign controls must be an object")
    payload = json.dumps(controls, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def campaign_identity(*, args, runner_sha256: str, effective_namelist: str,
                      input_identity: dict | None) -> dict:
    """Create the shared identity used to pair the two C4 scheme arms.

    ``mp`` and the requested processor grid are deliberately arm-specific and
    therefore excluded from ``campaign_id``.  The effective run controls,
    runner, active input seal, and label are shared controls; hashing them gives
    the C4 consumer a stable pair key instead of pairing independently selected
    directory names.  The actual grid is retained on the record for the
    decomposition assertion, but never folded into the shared key.
    """
    controls = {
        "label": args.label,
        "minutes": args.minutes,
        "seconds": args.seconds,
        "history": args.history,
        "history_s": args.history_s,
        "fixed_dt": bool(args.fixed_dt),
        "np": args.np,
        "radt": args.radt,
        "runner_sha256": runner_sha256,
        "namelist_without_grid_sha256": hashlib.sha256(
            "\n".join(line for line in effective_namelist.splitlines()
                    if "nproc_x" not in line and "nproc_y" not in line)
            .encode("utf-8")).hexdigest(),
        "input_canonical_sha256": (
            input_identity.get("canonical_sha256")
            if input_identity and input_identity.get("records") else None),
    }
    return {"schema": 1,
            "campaign_id": campaign_id_from_controls(controls),
            "scheme": args.mp,
            "controls": controls}


def input_identity_text(identity: dict) -> str:
    lines = ["schema 1", f"declared {'yes' if identity.get('declared') else 'no'}",
             f"complete {'yes' if identity.get('complete') else 'NO'}"]
    if identity.get("canonical_sha256"):
        lines.append(f"canonical_sha256 {identity['canonical_sha256']}")
    for rec in identity.get("records", []):
        lines.append(" ".join((rec["kind"], rec["domain"], rec["name"],
                                rec.get("sha256_before") or "(missing)",
                                f"after={rec.get('sha256_after') or '(pending)'}",
                                f"stable={'yes' if rec.get('stable') else 'NO'}")))
    return "\n".join(lines) + "\n"


def write_input_identity(out: Path, identity: dict) -> None:
    if identity.get("records"):
        identity["canonical_sha256"] = canonical_input_sha256(identity)
    (out / "input_sha256.json").write_text(json.dumps(identity, indent=2,
                                                         sort_keys=True) + "\n")
    (out / "input_sha256").write_text(input_identity_text(identity))


def build_child_env() -> dict:
    # Single-thread fence for strict-bitwise parity. KMP_DUPLICATE_LIB_OK is
    # intentionally NOT set here: it is caller-owned — a parent UNSET stays unset,
    # an explicit parent TRUE/FALSE is preserved verbatim. The runner never forces it.
    env=os.environ.copy()
    env.update({
        'OMP_NUM_THREADS':'1',
        'VECLIB_MAXIMUM_THREADS':'1',
        'MKL_NUM_THREADS':'1',
        'OMP_THREAD_LIMIT':'1',
        'GFORTRAN_ERROR_BACKTRACE':'1',
    })
    return env


def main() -> int:
    ap=argparse.ArgumentParser()
    # 37/137: legacy KDM6 Fortran / KDM6AD C++.
    # 237/337: conservative-interface-v1 corrected Fortran reference / C++ v2
    # (docs/FREEZE_LIFT_CONSERVATIVE_INTERFACE_V1.md, C4).
    ap.add_argument('--mp', choices=['37','137','237','337'], required=True)
    ap.add_argument('--minutes', type=int, default=10)
    ap.add_argument('--seconds', type=int, default=0,
                    help='extra run_seconds — step-granular runs (dt=20: 1 step = --minutes 0 --seconds 20)')
    ap.add_argument('--history', type=int, default=1)
    ap.add_argument('--history-s', type=int, default=None, dest='history_s',
                    help='history_interval_s (seconds). Effective output interval '
                         '= history_interval*60 + history_interval_s, so the base '
                         '=20 drifts +20s/frame and never lands on the run-end '
                         'time; pass 0 for EXACT hourly frames that include the '
                         'terminal state. Default: leave the namelist value.')
    ap.add_argument('--np', type=int, default=1,
                    help='MPI ranks; np>1 adds --mca btl self,tcp (Open MPI shm BTL SEGVs with libtorch-loaded ranks)')
    ap.add_argument('--label', default='smoke')
    ap.add_argument('--case', type=Path, default=None, metavar='DIR',
                    help='case directory holding namelist.input and wrf.exe '
                         '(default: the directory this script is in)')
    ap.add_argument('--fixed-dt', action='store_true', help='Disable adaptive time step for parity smoke runs')
    ap.add_argument('--proc-grid', default=None, metavar='NXxNY',
                    help='force the MPI decomposition, e.g. 1x4, 2x2, 4x1. WRF '
                         'picks one itself otherwise, so the seam direction is '
                         'not a variable the caller controls -- and separating '
                         'a seam-direction effect from a rank-count one needs '
                         'the same np run with different grids '
                         '(OPEN_QUESTIONS_after_pr167, item 3).')
    ap.add_argument('--radt', type=int, default=None,
                    help='radiation call interval in minutes. For the NEGATIVE '
                         'CONTROL on the six-minute field-count jump: if that '
                         'jump is the first radiation call, it must move when '
                         'this does, and stay put if it does not.')
    args=ap.parse_args()

    # ARGUMENT VALIDATION BEFORE FILESYSTEM ACCESS. The grid check first lived
    # beside the namelist edit, so on a host without the namelist the run died
    # on a missing file and never reached it -- a guard that only fires where it
    # is least needed.
    if args.np < 1:
        raise SystemExit(f"--np must be >= 1, got {args.np}")
    proc_grid = None
    if args.proc_grid is not None:
        try:
            nx, ny = (int(v) for v in args.proc_grid.lower().split('x'))
        except ValueError:
            raise SystemExit(f"--proc-grid wants NXxNY, got {args.proc_grid!r}")
        if nx < 1 or ny < 1:
            raise SystemExit(
                f"--proc-grid factors must be >= 1, got {args.proc_grid!r}")
        if nx * ny != args.np:
            raise SystemExit(
                f"--proc-grid {args.proc_grid} is {nx * ny} ranks and --np is "
                f"{args.np}; a grid that does not multiply to the rank count is "
                f"silently ignored by WRF, which would make the control a null")
        proc_grid = (nx, ny)

    # ONE RUNNER. The case is named on the command line; the default keeps a
    # copy placed beside a case working, but nothing needs such a copy now.
    run = (args.case or Path(__file__).parent).resolve()
    # EVERYTHING AFTER THE LOCK IS INSIDE A RESTORE SCOPE. The protecting try
    # used to open ~90 lines below, so a failure in between -- a namelist key
    # that will not substitute, a write that fails, mkdir on a full disk --
    # left the lock held AND the namelist rewritten, and the case needed a
    # manual repair for a run that never started (owner review 9.1).
    _restore_needed = False
    original = None
    _lock = run/'.ss-case-lock'
    _lock_acquired = False
    _input_identity: dict | None = None
    nml = run/'namelist.input'
    try:
        mine = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        # ONE RUN PER CASE DIRECTORY. This rewrites `namelist.input`, deletes the
        # previous rsl/wrfout, runs, then restores. Two concurrent runs interleave
        # all four: each overwrites the other's namelist, deletes the other's
        # output, archives results produced under the wrong settings, and the second
        # to finish restores a namelist the first had already replaced. This repo
        # has already paid for one shared-mutable-state race (the compile-time
        # fixture); the lock is the same answer (owner review 9.3).
        try:
            _lock_fd = os.open(_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            try:
                held = _lock.read_text().strip() or "(holder wrote no name)"
            except OSError:
                held = "(released while we were reporting it; try again)"
            print(f"run_ss_case: {_lock.name} is held by: {held}\n"
                  f"             This case directory takes one run at a time.\n"
                  f"             Wait, or remove the lock if that process is gone.",
                  file=sys.stderr)
            return 3
        _lock_acquired = True
        with os.fdopen(_lock_fd, 'w') as _lf:
            _lf.write(f"pid {os.getpid()} mp{args.mp} {args.label} "
                      f"{args.minutes}min np{args.np}\n")

        try:
            _exe_path = str((run/'wrf.exe').resolve())
            _exe_before = hashlib.sha256((run/'wrf.exe').read_bytes()).hexdigest()
        except OSError as e:
            _exe_path, _exe_before = str(run/'wrf.exe'), f'unavailable: {e}'

        original=nml.read_text()
        text=original
        text=remove_keys(text, {
            'qnn_land_mult', 'qnn_sea_mult',
            'fogvis_vis_consis_opt', 'fogvis_hydro_gate_opt', 'fogvis_hydro_min',
            'fogvis_clw_gate_opt', 'fogvis_clw_min', 'fogvis_ccn_aer_opt',
            'fogvis_ccn_ref_cm3', 'fogvis_ccn_rh_opt', 'fogvis_ccn_drh',
            'fogvis_ccn_rh_low_opt', 'fogvis_ccn_rh_low0', 'fogvis_ccn_rh_low_drh',
            'fogvis_ccn_rh_low_min', 'fogvis_ff_thresh', 'fogvis_hydro_wc0_gm3',
            'fogvis_hydro_dwc_gm3', 'fogvis_clw_wc0_gm3', 'fogvis_clw_dwc_gm3',
            'fogvis_ccn_beta_ref', 'fogvis_ccn_gamma', 'fogvis_ccn_rh0',
            'fogvis_ccn_rh_max',
        })
        for key,value in [
            ('run_days','0'),
            ('run_hours','0'),
            ('run_minutes',str(args.minutes)),
            ('run_seconds',str(args.seconds)),
            ('input_inname','"wrfinput_d<domain>"'),
            ('bdy_inname','"wrfbdy_d<domain>"'),
            ('auxinput24_inname','"wrfchainp_d<domain>"'),
            ('history_interval',str(args.history)),
            ('frames_per_outfile','1000'),
            ('mp_physics',args.mp),
            ('nio_tasks_per_group','0'),
            ('nio_groups','1'),
        ]:
            text=replace_line(text,key,value)
        if args.history_s is not None:
            text=replace_line(text, 'history_interval_s', str(args.history_s))
        if proc_grid is not None:
            text=set_or_insert(text, 'nproc_x', str(proc_grid[0]))
            text=set_or_insert(text, 'nproc_y', str(proc_grid[1]))
        if args.radt is not None:
            text=replace_line(text, 'radt', str(args.radt))
        if args.fixed_dt:
            text=replace_line(text, 'use_adaptive_time_step', '.false.')
            text=replace_line(text, 'step_to_output_time', '.false.')
        _restore_needed = True
        nml.write_text(text)

        stamp=time.strftime('%Y%m%d_%H%M%S')
        _np_tag = f"_np{args.np}" if args.np != 1 else ''
        _sec_tag = f"{args.seconds}s" if args.seconds else ''
        _rad_tag = f"_radt{args.radt}" if args.radt is not None else ''
        _grid_tag = f"_{args.proc_grid}" if args.proc_grid is not None else ''
        out=run/'runs'/f"mp{args.mp}_{args.label}_{args.minutes}min{_sec_tag}_hist{args.history}{_rad_tag}{_np_tag}{_grid_tag}_{stamp}"
        # PID, and exist_ok=False. The stamp resolves to one second, so two runs
        # started in the same second with the same arguments shared a directory and
        # interleaved their archives. The case lock above already serialises runs in
        # ONE case dir; this keeps the collision impossible rather than unlikely,
        # and makes it loud if it ever happens anyway (owner review 9.4).
        out = out.with_name(f"{out.name}_p{os.getpid()}")
        out.mkdir(parents=True, exist_ok=False)
        # Resolve the exact files named by the effective namelist before WRF is
        # launched.  A missing active file remains a recorded failed identity so
        # the runner can still preserve WRF's own launch/error output; it is never
        # replaced with an assumed wrfinput-only hash.
        try:
            _input_specs = resolve_active_namelist_inputs(text)
        except NamelistInputError as exc:
            raise SystemExit(f"cannot resolve active namelist inputs: {exc}") from exc
        _input_identity = hash_resolved_inputs(run, _input_specs)
        write_input_identity(out, _input_identity)
        for pat in ['rsl.error.*','rsl.out.*','wrfout_d01_*','klfs_lc05_fcst.*','klfs_lc05_prcp.*','klfs_lc05_ocean.*','klfs_lc05_energy.*','kdm6_step1_*.bin','kdm6_driver_step1_*.bin','kdm6_upstream_*.bin']:
            for p in run.glob(pat):
                if p.is_file() or p.is_symlink():
                    p.unlink()
        # KDM6_SUBSTEP_DUMP per-substep/graupel parity dumps: the Fortran dumps use position='append', so
        # they accumulate (duplicate-record corruption) unless cleaned each run. Clean ONLY the current run's
        # own tree (mp37=KDM6 writes fort_*, mp137=KDM6AD writes cpp_*) — NEVER the other tree's, which the
        # cross-tree comparison still needs. No-op when the dump macro is off (no such files exist).
        # Fortran schemes (37 legacy, 237 conservative reference) write fort_*;
        # C++ schemes (137 legacy, 337 conservative v2) write cpp_*.
        _dump_prefix = 'fort' if args.mp in ('37','237') else 'cpp'
        for pat in [_dump_prefix + '_*.bin']:  # ALL own-tree dumps (append-mode; stale mixed-schema records corrupt readers)
            for p in run.glob(pat):
                if p.is_file() or p.is_symlink():
                    p.unlink()
        env=build_child_env()
        stdout=out/f"wrf_mp{args.mp}_{args.label}.stdout"
        proc=None
    except BaseException:
        # Restore what was touched, release, and re-raise unchanged.  Both the
        # restoration and unlink are cleanup operations: one failing must not
        # prevent the other, or a setup error leaves a permanently held lock.
        _restore_error = None
        if _restore_needed and original is not None:
            try:
                nml.write_text(original)
            except BaseException as exc:
                _restore_error = exc
                print(f"run_ss_case: setup cleanup could not restore {nml}: {exc}",
                      file=sys.stderr)
        if _lock_acquired:
            try:
                _lock.unlink(missing_ok=True)
            except BaseException as exc:
                print(f"run_ss_case: setup cleanup could not release {_lock}: {exc}",
                      file=sys.stderr)
        # Keep the original setup exception active.  `_restore_error` is logged
        # above; replacing the useful parser/IO error with cleanup noise makes
        # the failure harder to diagnose.
        raise
    try:
        with stdout.open('w') as f:
            # Inner try/except is scoped to the SPAWN ONLY (mpirun/wrf.exe launch). A
            # missing/non-executable launcher raises OSError here → catch it, leave proc=None,
            # and fall through to the rc=127 fallback instead of a bare traceback. A nonzero
            # WRF exit is NOT an exception — it returns via proc.returncode.
            # NOTE: opening the stdout log (the `with` above) is deliberately OUTSIDE this
            # except — a log-open failure is a setup/IO error, not a launch failure, and must
            # surface as itself rather than be mislabeled and mapped to rc=127. Likewise the
            # provenance copy below is outside it so a copy error is not swallowed.
            try:
                mpi_cmd=['mpirun','-np',str(args.np)]
                if args.np > 1:
                    mpi_cmd += ['--mca','btl','self,tcp']
                proc=subprocess.run(mpi_cmd+[str(run/'wrf.exe')], cwd=run, env=env,
                                    stdout=f, stderr=subprocess.STDOUT, check=False)
            except OSError as e:
                # Record the launch failure in BOTH stderr and the run's own stdout log, so the
                # cause is visible from the run directory alone (rsl logs won't exist — no spawn).
                msg = f"run_ss_case: launch failed: {e}"
                print(msg, file=sys.stderr)
                print(msg, file=f)
        # Provenance: WHICH BINARY RAN. Comparing two runs assumes they came from
        # the same wrf.exe, and nothing recorded it -- so a comparison made days
        # apart, across a session that swapped binaries for diagnostic arms,
        # could not be shown to be a fair one afterwards. The hash was checked
        # by hand at every swap, which is evidence in a transcript and not in
        # the run. It is in the run now.
        # BEFORE AND AFTER. Hashing only after the run records whatever the file
        # is when the run ENDS, which is not necessarily what executed: a
        # symlink retargeted or a binary rebuilt mid-run would be recorded as
        # the one that ran (owner review 9.2). Both are written, with the
        # resolved path, and a mismatch is stated rather than silently resolved.
        try:
            h_after = hashlib.sha256((run/'wrf.exe').read_bytes()).hexdigest()
        except OSError as e:
            h_after = f'unavailable: {e}'
        (out/'wrf_exe_sha256').write_text(
            f"{h_after}\n"
            f"before {_exe_before}\n"
            f"after  {h_after}\n"
            f"stable {'yes' if _exe_before == h_after else 'NO -- the binary changed during the run'}\n"
            f"path   {_exe_path}\n")
        # 9.5: WHAT WRF ACTUALLY DID, not what was asked for. `--proc-grid`
        # only pre-checks the arithmetic; WRF prints the decomposition it chose,
        # and a run whose grid is not the requested one is not the experiment
        # (owner review 9.5). Recorded either way; a mismatch is named.
        try:
            _r0 = next(iter(sorted(run.glob('rsl.error.0000'))), None)
            _actual = parse_proc_grid(
                _r0.read_text(errors='replace')[:20000]) if _r0 else None
        except OSError:
            _actual = None
        # And the runner's own identity, so "which script produced this" is a
        # fact in the run rather than a memory. `uncomparable` is written as
        # itself: on a host without the repository there is nothing to compare.
        (out/'runner_sha256').write_text(
            f"runner {mine}\n"
            f"path   {Path(__file__).resolve()}\n")
        _requested = args.proc_grid
        (out/'proc_grid').write_text(
            f"requested {_requested or '(unset -- WRF chose)'}\n"
            f"actual    {_actual or '(not found in rsl.error.0000)'}\n"
            f"matches   {'yes' if (_actual and _requested and _actual == _requested) else ('n/a' if not _requested else 'NO -- this run is not the requested decomposition')}\n"
            f"np        {args.np}\n")
        if _input_identity is not None:
            # Re-read after the model exits.  The before hash is the input that
            # was actually available to the launch; a changed or disappearing
            # file is an invalid identity for causal comparisons.
            refresh_input_hashes(_input_identity)
            write_input_identity(out, _input_identity)
        # Provenance: archive the EXACT namelist used (before we restore the pristine one).
        if proc is not None:
            rsl=[p for pat in ('rsl.error.*','rsl.out.*') for p in run.glob(pat)]
            for src in [nml]+rsl:
                if src.exists(): shutil.copy2(src, out/src.name)
    finally:
        # ORDER. Restore, archive, and only then release: the outputs are still
        # in the case directory until they are copied, so a waiter that started
        # at the release would delete them as its own stale files. Releasing
        # first is the same fail-open the fixture lock was fixed for.
        # Restore the pristine working namelist so the next run / git-diff is not polluted
        # by this run's mutations (see the §10 namelist-race lesson: stale working-dir namelist
        # → truncated runs → phantom parity failures).
        # Restoration can fail independently of archive I/O.  Capture both
        # cleanup errors, always attempt lock release, and preserve the active
        # model/archive exception when there is one.
        _body_error = sys.exc_info()[1]
        _restore_error = None
        try:
            try:
                nml.write_text(original)
            except BaseException as exc:
                _restore_error = exc
                print(f"run_ss_case: could not restore {nml}: {exc}", file=sys.stderr)

            # THE RELEASE MUST SURVIVE A FAILING ARCHIVE. The copy loop is the only
            # step here that touches a filesystem it does not control -- a full
            # disk, a vanishing file -- and the unlink sat AFTER it, so one raised
            # copy left the lock held for a run that had already finished. Found by
            # injecting an OSError into shutil.copy2 (owner review 9.1, the half of
            # it that is not in setup).
            _archive_error = None
            try:
                for pat in ['wrfout_d01_*','klfs_lc05_fcst.*','klfs_lc05_prcp.*','klfs_lc05_ocean.*','klfs_lc05_energy.*','kdm6_step1_*.bin','kdm6_driver_step1_*.bin','kdm6_upstream_*.bin']:
                    for src in run.glob(pat):
                        if src.is_file(): shutil.copy2(src, out/src.name)
            except BaseException as exc:
                _archive_error = exc
            finally:
                if _lock_acquired:
                    try:
                        _lock.unlink(missing_ok=True)
                    except BaseException as exc:
                        print(f"run_ss_case: could not release {_lock}: {exc}",
                              file=sys.stderr)
            if _archive_error is not None:
                if _restore_error is not None:
                    print(f"run_ss_case: restoration also failed: {_restore_error}",
                          file=sys.stderr)
                if _body_error is None:
                    raise _archive_error
            elif _restore_error is not None and _body_error is None:
                raise _restore_error
        finally:
            # If the model body already raised, leave that original exception in
            # control; cleanup diagnostics above are sufficient and the lock has
            # already had its unconditional release attempt.
            pass
    # THE EXPERIMENT'S VERDICT IS NOT THE MODEL'S EXIT CODE. A run whose binary
    # changed under it, or whose processor grid is not the one requested, is
    # recorded as such -- and a pipeline reading only the exit code took it as a
    # success anyway (owner review 9.2). The verdict is written beside the
    # metadata and, when the experiment is invalid, returned.
    # proc is None only if the launch raised OSError above (caught) → report 127
    # (command-not-found convention); otherwise use WRF's real exit code.
    rc = proc.returncode if proc is not None else 127
    _invalid = []
    if _exe_before != h_after:
        _invalid.append("binary_changed_during_run")
    if _requested and _actual and _actual != _requested:
        _invalid.append("processor_grid_mismatch")
    if _requested and not _actual:
        _invalid.append("processor_grid_not_found")
    if _input_identity is not None and not _input_identity.get("complete", False):
        _invalid.append("active_input_identity_incomplete")
    # A crashed run is not a valid experiment. The asymmetry above is deliberate
    # and kept: a ZERO exit still does not make an experiment valid. What was
    # missing is the other direction. An MPI transport failure
    # ("writev failed: No buffer space available", exit 14, right after
    # SIMULATION START) left this file reading `true`, and findings cited it as
    # if it certified the run; the exit code was in a sibling file nobody read.
    if rc != 0:
        _invalid.append("model_did_not_complete")
    import json as _json
    (out/'experiment_valid.json').write_text(_json.dumps({
        "experiment_valid": not _invalid,
        "invalid_reasons": _invalid,
        "requested_proc_grid": _requested,
        "actual_proc_grid": _actual,
        "active_input_identity_complete": (
            _input_identity.get("complete") if _input_identity is not None else None),
        "exit_code": rc,
        "model_completed": rc == 0,
    }, indent=1) + "\n")
    # Shared campaign identity for downstream pair consumers.  This is written
    # even for an invalid run so a reader can explain why no pair was formed;
    # ``experiment_valid`` remains the independent execution verdict.
    _campaign = campaign_identity(args=args, runner_sha256=mine,
                                  effective_namelist=text,
                                  input_identity=_input_identity)
    _campaign.update({"requested_proc_grid": _requested,
                      "actual_proc_grid": _actual,
                      "exit_code": rc,
                      "experiment_valid": not _invalid})
    (out/'run_identity.json').write_text(
        _json.dumps(_campaign, indent=1, sort_keys=True) + "\n")
    (out/'exit_code').write_text(str(rc)+'\n')
    print(out)
    if _invalid and rc == 0:
        print(f"run_ss_case: the MODEL succeeded and the EXPERIMENT did not: "
              f"{_invalid}\n"
              f"             see {out.name}/experiment_valid.json",
              file=sys.stderr)
        return 4
    return rc

if __name__ == '__main__':
    raise SystemExit(main())
