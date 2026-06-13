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
import subprocess
from pathlib import Path
from typing import NamedTuple

from ._rttov_reference.rttov_ascii import parse_rttov_ascii_blocks

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


class RttovKOutput(NamedTuple):
    """Single-runK result (design 7): direct BT + per-channel K-matrix + quality.

    ``bt``/``rad_quality`` are ``[nprofiles, nchannels]`` (rad_quality is always
    present -- the parser requires the RADIANCE%QUALITY block so the consumer can
    always enforce the design section-8 mask; the field is named ``rad_quality``
    to match the design's consumer contract); ``k`` maps each RTTOV PROFILES_K
    field (``T``, ``Q``, ``O3``, ``SKIN(1)%T``, ...) to a
    ``[nprofiles, nchannels, L_field]`` array. All numpy (non-torch boundary).
    """
    bt: "list"               # [nprofiles][nchannels]
    rad_quality: "list"      # [nprofiles][nchannels] (design 'rad_quality', section 8)
    k: dict                  # {field: [nprofiles][nchannels][L_field]}
    nprofiles: int
    nchannels: int


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
    if len(qual_flat) != len(bt_flat):
        raise ValueError(
            f"{path}: RADIANCE%QUALITY length {len(qual_flat)} != RADIANCE%BT "
            f"length {len(bt_flat)} (inconsistent RTTOV output).")
    return {
        "bt": _reshape_profile_major(bt_flat, nprofiles, nchannels),
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
        by_field.setdefault(field, {})[idx] = values
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
        nprofiles=expected_nprofiles, nchannels=nchannels)


def _resolve_run_script(case_dir, run_script):
    case_dir = Path(case_dir)
    candidate = case_dir / run_script
    if candidate.is_file():
        return candidate
    raise FileNotFoundError(
        f"RTTOV run script not found: {candidate}. Prepare the case "
        "(AD-RTTOV profile overlay) before run_rttov_k.")


def _run_case_fresh(script, targets, timeout):
    """Run ``sh run.sh`` out-of-process with the OMP fence, after clearing the
    output files we will parse, so a clean exit that does NOT rewrite them is
    caught (clean exit != valid output; the libomp I/O-race / stale-output class)."""
    for p in targets:
        if p.exists():
            p.unlink()
    result = subprocess.run(
        ["sh", script.name], cwd=str(script.parent),
        capture_output=True, text=True, timeout=timeout, env=_child_env())
    if result.returncode != 0:
        raise RuntimeError(
            f"RTTOV run failed (rc={result.returncode}) in {script.parent}: "
            f"{(result.stderr or result.stdout)[-800:]}")
    for p in targets:
        if not p.is_file():
            raise RuntimeError(
                f"RTTOV exited 0 but did not write {p} -- invalid run (the prior "
                "stale output was cleared; clean exit != valid output).")


def run_rttov_k(case_dir, *, nchannels, expected_nprofiles,
                run_script="run.sh", timeout=None):
    """Out-of-process single runK -> RttovKOutput (BT + K).

    Runs the prepared RTTOV case in a CHILD PROCESS (``sh run.sh`` in the case
    dir; design 14.2 threading isolation -- never load RTTOV in-process with
    libtorch; the child env hard-sets the OMP fence) after clearing the outputs
    to be parsed (freshness gate), then parses ``k/radiance.txt`` +
    ``k/profiles_k.txt``. Raises on non-zero exit, on un-refreshed output, and on
    a profile count != ``expected_nprofiles``.

    ``expected_nprofiles`` is REQUIRED (no default): the caller packed the input
    and knows how many profiles RTTOV was asked to compute, so making it optional
    would re-open the silent-truncation hole this guard exists to close.
    """
    script = _resolve_run_script(case_dir, run_script)
    out_k = script.parent / "k"
    _run_case_fresh(script, [out_k / "radiance.txt", out_k / "profiles_k.txt"], timeout)
    return parse_rttov_k_case(script.parent, nchannels=nchannels,
                              expected_nprofiles=expected_nprofiles)


def run_rttov_direct(case_dir, *, nchannels, expected_nprofiles,
                     run_script="run.sh", timeout=None):
    """(Diagnostic, value-only -- NOT the adjoint path, design 7.) Out-of-process
    direct run -> BT from ``direct/radiance.txt``. Normally a single ``run_rttov_k``
    supplies BT too; use this only for a value-only smoke. ``expected_nprofiles``
    is REQUIRED (no silent-truncation opt-out)."""
    script = _resolve_run_script(case_dir, run_script)
    target = script.parent / "direct" / "radiance.txt"
    _run_case_fresh(script, [target], timeout)
    rad = parse_rttov_radiance(target, nchannels=nchannels)
    if rad["nprofiles"] != expected_nprofiles:
        raise ValueError(
            f"{target}: parsed {rad['nprofiles']} profiles, expected "
            f"{expected_nprofiles} (uniformly-truncated output).")
    return rad
