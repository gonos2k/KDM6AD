"""P4/P5 -- out-of-process RTTOV runner (design 7, 14.2; M4/M5).

RTTOV is external Fortran (RTTOV-14) and is invoked in a SEPARATE PROCESS, never
in-process: loading pyrttov/RTTOV's OpenMP into the libtorch process reproduces
the T10/T11 threading-conflict crash class (design 14.2; memory). A single
``runK`` produces BOTH the direct BT (``RADIANCE%BT``) and the full K-matrix
(``PROFILES_K(i)%...``) -- no separate runDirect is needed (design 7/14.2);
``run_rttov_direct`` is a value-only diagnostic.

This module owns the NON-torch boundary: it returns numpy arrays
(``RttovObsOp.forward`` casts them to torch in P6). The output side reuses the
verified rttov_test ASCII I/O via ``_rttov_reference/rttov_ascii.py``:
  RADIANCE%BT      -> [nprofiles, nchannels]          (direct BT)
  RADIANCE%QUALITY -> [nprofiles, nchannels]          (0 == usable)
  PROFILES_K(i)%F  -> [nprofiles, nchannels, L_F]     (K-matrix; i = chanprof,
                       nchanprof = nprofiles*nchannels; e.g. T/Q have L=nlayers,
                       P_HALF has L=nlevels). Matches pyrttov K shape
                       [nprofiles, nchannels, nlayers] (design 9.1).

AD_RTTOV_HOME (env, default /Users/yhlee/AD-RTTOV) locates the RTTOV assets;
the RTTOV binary/coef stay in AD-RTTOV (code dirs separate, design 14.1).
"""
from __future__ import annotations

import math
import os
import re
import signal
import subprocess
from contextlib import contextmanager
from numbers import Real
from pathlib import Path
from typing import NamedTuple

from ._rttov_reference.rttov_ascii import parse_rttov_ascii_blocks

DEFAULT_RTTOV_TIMEOUT = 300.0  # seconds per external call, not a cycle deadline


def validate_rttov_timeout(value):
    """Require a finite wall-clock limit; None does not opt out."""
    if (isinstance(value, bool) or not isinstance(value, Real)
            or not math.isfinite(value) or value <= 0):
        raise ValueError("RTTOV timeout must be a positive finite number of seconds")
    return float(value)


@contextmanager
def exclusive_rttov_case(case_dir):
    """Reject overlapping writers/runners using the same canonical case path.

    The lock lives beside the rewritten directory. Keep its inode after release:
    unlinking an advisory lock allows two callers to lock different inodes.
    Unique disposable workspaces should contain both the case and this lock.
    """
    if os.name != "posix":
        raise RuntimeError("RTTOV external execution requires POSIX process groups")
    import fcntl
    case_dir = Path(case_dir).resolve()
    case_dir.parent.mkdir(parents=True, exist_ok=True)
    with (case_dir.parent / f".{case_dir.name}.rttov.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"RTTOV case already in use: {case_dir}") from exc
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


_DEFAULT_AD_RTTOV_HOME = "/Users/yhlee/AD-RTTOV"
_PK_PREFIX = re.compile(r"PROFILES_K\(\s*(\d+)\s*\)")

# Design 14.2/14.5 OMP fence: RTTOV's OpenMP must NOT spin unbounded into the
# (libtorch) parent's thread space -- the T10/T11 crash class. The runner is
# authoritative: it HARD-SETS single-thread OpenMP in the child env rather than
# relying on the caller's environment inheritance (a bare caller leaves it unset).
_OMP_FENCE = {"OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE", "OMP_THREAD_LIMIT": "1"}


def _child_env() -> dict:
    return {**os.environ, **_OMP_FENCE}


# RTTOV/Fortran non-finite markers the float regex (rttov_ascii._FLOAT_RE) does
# NOT match and therefore silently DROPS -- turning a bad value into a shorter
# field instead of a caught error (a uniform drop stays rectangular and passes
# the ragged + isfinite checks). Scan the raw text and reject so a NaN/Inf/
# overflow value can never be silently swallowed. (math.isfinite alone only
# catches regex-matchable infinities, e.g. a huge exponent like 1.0E+400.)
_NONFINITE_RE = re.compile(r"(?i)(?<![\w.])(nan|[+-]?inf(?:inity)?)(?![\w.])|\*{3,}")


def _assert_finite_ascii(path):
    m = _NONFINITE_RE.search(Path(path).read_text())
    if m:
        raise ValueError(
            f"{path}: non-finite marker {m.group(0)!r} in RTTOV output "
            "(NaN/Inf/overflow); the float parser would drop it and silently "
            "shorten a field -- rejecting instead.")


def ad_rttov_home() -> Path:
    """Resolve AD_RTTOV_HOME (env override; default per design 14.1)."""
    return Path(os.environ.get("AD_RTTOV_HOME", _DEFAULT_AD_RTTOV_HOME))


def rttov_runtime_root() -> Path | None:
    """Resolve the project-local, self-contained RTTOV runtime bundle, or None.

    The bundle (``<repo>/rttov_runtime/``: bin/rttov_test.exe + rtcoef/ + cases/ami/*,
    built by tools/build_rttov_runtime.sh) lets the cloud path run WITHOUT the external
    AD-RTTOV tree -- the fixture resolvers prefer it when present and fall back to
    ``ad_rttov_home()`` otherwise. ``KDM6_RTTOV_RUNTIME`` overrides the location; it
    still needs the system dylibs the exe links (MacPorts netcdf, Homebrew gcc).

    Returns the bundle root only if it actually contains the exe (a half-built or
    absent bundle resolves to None so the AD-RTTOV fallback is used)."""
    env = os.environ.get("KDM6_RTTOV_RUNTIME")
    root = Path(env) if env else Path(__file__).resolve().parents[3] / "rttov_runtime"
    return root if (root / "bin" / "rttov_test.exe").is_file() else None


class RttovKOutput(NamedTuple):
    """Single-runK result (design 7): direct BT + per-channel K-matrix + quality.

    ``bt``/``rad_quality`` are ``[nprofiles, nchannels]`` (rad_quality is always
    present -- the parser requires the RADIANCE%QUALITY block so the consumer can
    always enforce the design section-8 mask; the field is named ``rad_quality``
    to match the design's consumer contract); ``k`` maps each RTTOV PROFILES_K
    field (``T``, ``Q``, ``O3``, ``SKIN(1)%T``, ...) to a
    ``[nprofiles, nchannels, L_field]`` array. All numpy (non-torch boundary).
    ``evidence_level`` is always ``"wiring_only"`` because fixture-backed RTTOV
    output validates parser/wiring contracts, not independent physical evidence.
    """
    bt: "list"               # [nprofiles][nchannels]
    rad_quality: "list"      # [nprofiles][nchannels] (design 'rad_quality', section 8)
    k: dict                  # {field: [nprofiles][nchannels][L_field]}
    nprofiles: int
    nchannels: int
    refl: object = None      # [nprofiles][nchannels] solar reflectance (Phase 7); None if no solar
    evidence_level: str = "wiring_only"


def _reshape_profile_major(flat, nprofiles, nchannels):
    """Reshape a profile-major/channel-minor flat list to [nprofiles][nchannels]."""
    expected = nprofiles * nchannels
    if len(flat) != expected:
        raise ValueError(
            f"cannot reshape {len(flat)} values to ({nprofiles}, {nchannels}); "
            f"expected {expected}")
    return [flat[p * nchannels:(p + 1) * nchannels] for p in range(nprofiles)]


def _infer_nprofiles(n_flat, nchannels, what):
    if nchannels <= 0:
        raise ValueError(f"nchannels must be > 0 (got {nchannels})")
    if n_flat % nchannels != 0:
        raise ValueError(
            f"{what} length {n_flat} is not divisible by nchannels {nchannels}; "
            "wrong channel count or a corrupt RTTOV output.")
    return n_flat // nchannels


def parse_rttov_radiance(path, *, nchannels):
    """Parse an RTTOV radiance ASCII file -> {bt, rad_quality, nprofiles} reshaped
    to [nprofiles][nchannels]. BT is RADIANCE%BT (solar channels are 0 in BT
    space; IR carry the brightness temperature). PURE PARSER: it RETURNS the
    parsed ``nprofiles``; the truncation guard (validating against the known
    expected count) is enforced by the case/run boundary, not by an optional
    parameter here (an optional guard is a silent opt-out)."""
    _assert_finite_ascii(path)  # reject NaN/Inf/overflow tokens before they drop
    blocks = parse_rttov_ascii_blocks(path)
    if "RADIANCE%BT" not in blocks:
        raise ValueError(f"{path}: no RADIANCE%BT block (need store_rad/adk_bt).")
    bt_flat = blocks["RADIANCE%BT"]
    if any(not math.isfinite(v) for v in bt_flat):
        raise ValueError(f"{path}: RADIANCE%BT has non-finite values.")
    nprofiles = _infer_nprofiles(len(bt_flat), nchannels, "RADIANCE%BT")
    # QUALITY is REQUIRED, not optional. The design's quality mask
    # (section 8: mask = obs_ok & rad_quality==0 & cloud_gate) cannot be enforced
    # if the runner silently returns no quality -- a missing block means
    # store_rad/quality was not enabled, and unusable radiances would enter J_obs
    # unguarded. Surfacing it reliably IS the runner's half of the contract.
    if "RADIANCE%QUALITY" not in blocks:
        raise ValueError(
            f"{path}: no RADIANCE%QUALITY block -- store_rad/quality must be "
            "enabled; the RTTOV quality mask (design section 8) cannot be enforced "
            "without it.")
    qual_flat = blocks["RADIANCE%QUALITY"]
    if any(not math.isfinite(v) for v in qual_flat):
        raise ValueError(f"{path}: RADIANCE%QUALITY has non-finite values.")
    if len(qual_flat) != len(bt_flat):
        raise ValueError(
            f"{path}: RADIANCE%QUALITY length {len(qual_flat)} != RADIANCE%BT "
            f"length {len(bt_flat)} (inconsistent RTTOV output).")
    # REFL (solar reflectance/BRF) is the SOLAR-channel observable (Phase 7): present
    # only when the run has solar enabled (opts%rt_all%solar). Solar channels carry 0
    # in BT space and the cloud signal in REFL; thermal channels carry 0 in REFL. It is
    # OPTIONAL (a thermal-only run has no REFL block) -- absent -> None, not an error.
    refl = None
    refl_flat = blocks.get("RADIANCE%REFL")
    if refl_flat is not None:
        if len(refl_flat) != len(bt_flat):
            raise ValueError(
                f"{path}: RADIANCE%REFL length {len(refl_flat)} != RADIANCE%BT length "
                f"{len(bt_flat)} (inconsistent RTTOV output).")
        if any(not math.isfinite(v) for v in refl_flat):
            raise ValueError(f"{path}: RADIANCE%REFL has non-finite values.")
        refl = _reshape_profile_major(refl_flat, nprofiles, nchannels)
    return {
        "bt": _reshape_profile_major(bt_flat, nprofiles, nchannels),
        "refl": refl,
        "rad_quality": _reshape_profile_major(qual_flat, nprofiles, nchannels),
        "nprofiles": nprofiles,
    }


def parse_rttov_profiles_k(path, *, nchannels):
    """Parse PROFILES_K(i)%FIELD blocks -> {field: [nprofiles][nchannels][L]}.

    ``i`` runs over chanprof (nchanprof = nprofiles*nchannels). Each field is
    grouped across all chanprof rows and reshaped; L is that field's own length
    (T/Q -> nlayers, P_HALF -> nlevels, surface scalars -> small L).
    PURE PARSER: RETURNS the parsed ``nprofiles``; the truncation guard is
    enforced at the case/run boundary (no optional opt-out here). Empty/non-finite
    fields and a P_HALF/T level/layer mismatch are rejected.

    Row-identity contract: PROFILES_K rows carry explicit chanprof labels and are
    therefore keyed by ``PROFILES_K(i)`` below.  RADIANCE rows do NOT carry such a
    key; they are consumed positionally as profile-major/channel-minor rows that
    must match the ``channels.txt``/``lprofiles.txt`` authored for the case.  A
    shape-preserving profile permutation is therefore guarded by live row-canary
    tests, not parser metadata.
    """
    _assert_finite_ascii(path)  # reject NaN/Inf/overflow tokens before they drop
    blocks = parse_rttov_ascii_blocks(path)
    by_field: dict = {}            # field -> {chanprof_idx: values}
    for key, values in blocks.items():
        m = _PK_PREFIX.match(key.strip())
        if not m:
            continue
        idx = int(m.group(1))
        field = re.sub(r"\s+", "", key[m.end():].strip().lstrip("%"))
        rows = by_field.setdefault(field, {})
        if idx in rows:
            raise ValueError(
                f"{path}: duplicate PROFILES_K row for field {field!r}, "
                f"chanprof index {idx} (raw key {key!r}) -- refusing to "
                "overwrite an earlier K row.")
        rows[idx] = values
    if not by_field:
        raise ValueError(f"{path}: no PROFILES_K blocks found.")

    nchanprof = max(len(rows) for rows in by_field.values())
    nprofiles = _infer_nprofiles(nchanprof, nchannels, "nchanprof (PROFILES_K)")
    out: dict = {}
    for field, rows in by_field.items():
        if sorted(rows) != list(range(1, nchanprof + 1)):
            raise ValueError(
                f"PROFILES_K field {field!r} has chanprof indices {sorted(rows)[:5]}..., "
                f"expected 1..{nchanprof} (incomplete K output).")
        length = len(rows[1])
        if length == 0:
            raise ValueError(
                f"PROFILES_K field {field!r} is empty (L=0) -- a zero-length "
                "Jacobian is invalid output.")
        flat = [rows[i] for i in range(1, nchanprof + 1)]
        # sanity: every row same length (rectangular field) and finite
        if any(len(r) != length for r in flat):
            raise ValueError(f"PROFILES_K field {field!r} has ragged rows.")
        if any(not math.isfinite(v) for r in flat for v in r):
            raise ValueError(f"PROFILES_K field {field!r} has non-finite values.")
        # [nchanprof][L] -> [nprofiles][nchannels][L]
        out[field] = [
            [flat[p * nchannels + c] for c in range(nchannels)]
            for p in range(nprofiles)
        ]
    # RTTOV-14 layer-based invariant: P_HALF (levels) == T (layers) + 1.
    if "P_HALF" in out and "T" in out:
        n_lev = len(out["P_HALF"][0][0])
        n_lay = len(out["T"][0][0])
        if n_lev != n_lay + 1:
            raise ValueError(
                f"{path}: P_HALF has {n_lev} levels but T has {n_lay} layers "
                "(expected Nlevels = Nlayers + 1; design 5/profile.py:124).")
    return out, nprofiles


def parse_rttov_k_case(out_dir, *, nchannels, expected_nprofiles):
    """Assemble RttovKOutput from an already-run RTTOV-K case directory.

    Reads ``<out_dir>/k/radiance.txt`` (BT + quality) and
    ``<out_dir>/k/profiles_k.txt`` (K-matrix) -- both products of the SAME
    single runK (design 14.2). No subprocess; usable on a fixture's stored
    output (the verified-I/O path the design's first backend specifies).

    ``expected_nprofiles`` is REQUIRED (no None opt-out): the parsed BT and K
    profile counts are both validated against it, so a uniformly-truncated output
    (whole profiles dropped, BT/K truncating alike) is rejected here.
    """
    if expected_nprofiles <= 0:
        raise ValueError(
            f"expected_nprofiles must be > 0 (got {expected_nprofiles}) -- "
            "a fixture-backed run with zero cases is not evidence.")
    out_dir = Path(out_dir)
    rad = parse_rttov_radiance(out_dir / "k" / "radiance.txt", nchannels=nchannels)
    k, nprofiles_k = parse_rttov_profiles_k(
        out_dir / "k" / "profiles_k.txt", nchannels=nchannels)
    if rad["nprofiles"] != expected_nprofiles or nprofiles_k != expected_nprofiles:
        raise ValueError(
            f"profile count mismatch: radiance {rad['nprofiles']}, profiles_k "
            f"{nprofiles_k}, expected {expected_nprofiles} (uniformly-truncated "
            "output or wrong nchannels).")
    return RttovKOutput(
        bt=rad["bt"], rad_quality=rad["rad_quality"], k=k,
        nprofiles=expected_nprofiles, nchannels=nchannels, refl=rad.get("refl"))


def _resolve_run_script(case_dir, run_script):
    case_dir = Path(case_dir)
    candidate = case_dir / run_script
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(
        f"RTTOV run script not found: {candidate}. Prepare the case "
        "(AD-RTTOV profile overlay) before run_rttov_k.")


def _run_case_fresh(script, targets, timeout):
    """Bound a trusted POSIX wrapper and children remaining in its group.

    File-backed logs avoid waiting on inherited pipes after a shell exits.
    A wrapper must wait for its children; an early exit with group members is
    rejected. Deliberately detached sessions and whole-worker/cycle deadlines
    require the deployment supervisor and are outside this call boundary.
    """
    timeout = validate_rttov_timeout(timeout)
    if os.name != "posix":
        raise RuntimeError("RTTOV external execution requires POSIX process groups")
    for p in targets:
        if p.exists():
            p.unlink()
    stdout_path = script.parent / "run.stdout.log"
    stderr_path = script.parent / "run.stderr.log"
    failure_path = script.parent / "run.failure.txt"
    failure_path.unlink(missing_ok=True)

    def tail(path):
        try:
            with path.open("rb") as log:
                log.seek(0, os.SEEK_END)
                log.seek(max(0, log.tell() - 800))
                return log.read().decode("utf-8", errors="replace")
        except OSError:
            return ""  # A log I/O failure must not mask the execution error.

    try:
        with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
            proc = subprocess.Popen(
                ["sh", script.name], cwd=str(script.parent),
                stdout=stdout, stderr=stderr, env=_child_env(),
                start_new_session=True)
            try:
                returncode = proc.wait(timeout=timeout)
                # wait() reaped the leader. Remaining group members have not
                # finished writing, so their output cannot be accepted yet.
                try:
                    os.killpg(proc.pid, 0)
                except ProcessLookupError:
                    children_remain = False
                else:
                    children_remain = True
            finally:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                # Reap our direct child. The OS reaps orphan descendants;
                # do not claim portable ownership of their wait status.
                proc.wait(timeout=5.0)
        if returncode != 0:
            raise RuntimeError(f"RTTOV run failed (rc={returncode}) in {script.parent}")
        if children_remain:
            raise RuntimeError(f"RTTOV wrapper exited with unfinished children in {script.parent}")
        for p in targets:
            if not p.is_file():
                raise RuntimeError(
                    f"RTTOV exited 0 but did not write {p} -- invalid run (the prior "
                    "stale output was cleared; clean exit != valid output).")
    except BaseException as exc:
        diagnostic = tail(stderr_path) or tail(stdout_path)
        try:
            failure_path.write_text(f"{type(exc).__name__}: {exc}\n{diagnostic}\n")
        except OSError:
            pass  # e.g. a full disk; still propagate the original failure
        if isinstance(exc, subprocess.TimeoutExpired):
            exc.output, exc.stderr = tail(stdout_path), tail(stderr_path)
        elif isinstance(exc, RuntimeError):
            raise RuntimeError(f"{exc}: {diagnostic}") from exc
        raise


def run_rttov_k(case_dir, *, nchannels, expected_nprofiles,
                run_script="run.sh", timeout=DEFAULT_RTTOV_TIMEOUT):
    """Out-of-process single runK -> RttovKOutput (BT + K).

    Runs the prepared RTTOV case in a CHILD PROCESS (``sh run.sh`` in the case
    dir; design 14.2 threading isolation -- never load RTTOV in-process with
    libtorch; the child env hard-sets the OMP fence) after clearing the outputs
    to be parsed (freshness gate), then parses ``k/radiance.txt`` +
    ``k/profiles_k.txt``. Raises on non-zero exit, on un-refreshed output, and on
    a profile count != ``expected_nprofiles``.

    ``timeout`` is a positive finite limit in seconds (default 300) for the
    external process; None is rejected. On every exit the owned POSIX process
    group is terminated and the direct child reaped. Timeout raises
    ``subprocess.TimeoutExpired``; logs/failure text remain in the case.
    This does not impose a deadline on preparation, parsing, or the DA cycle.

    ``expected_nprofiles`` is REQUIRED (no default): the caller packed the input
    and knows how many profiles RTTOV was asked to compute, so making it optional
    would re-open the silent-truncation hole this guard exists to close.
    """
    timeout = validate_rttov_timeout(timeout)
    script = _resolve_run_script(case_dir, run_script)
    out_k = script.parent / "k"
    with exclusive_rttov_case(script.parent):
        _run_case_fresh(script, [out_k / "radiance.txt", out_k / "profiles_k.txt"], timeout)
        return parse_rttov_k_case(script.parent, nchannels=nchannels,
                                  expected_nprofiles=expected_nprofiles)


def run_rttov_direct(case_dir, *, nchannels, expected_nprofiles,
                     run_script="run.sh", timeout=DEFAULT_RTTOV_TIMEOUT):
    """(Diagnostic, value-only -- NOT the adjoint path, design 7.) Out-of-process
    direct run -> BT from ``direct/radiance.txt``. Normally a single ``run_rttov_k``
    supplies BT too; use this only for a value-only smoke. ``expected_nprofiles``
    is REQUIRED (no silent-truncation opt-out)."""
    timeout = validate_rttov_timeout(timeout)
    script = _resolve_run_script(case_dir, run_script)
    target = script.parent / "direct" / "radiance.txt"
    with exclusive_rttov_case(script.parent):
        _run_case_fresh(script, [target], timeout)
        rad = parse_rttov_radiance(target, nchannels=nchannels)
    if rad["nprofiles"] != expected_nprofiles:
        raise ValueError(
            f"{target}: parsed {rad['nprofiles']} profiles, expected "
            f"{expected_nprofiles} (uniformly-truncated output).")
    return rad
