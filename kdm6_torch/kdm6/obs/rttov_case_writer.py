"""P4-live -- write an RttovInput to a runnable rttov_test case + a live run_k.

Mirrors AD-RTTOV's verified ``rttov_fixture_profile_overlay_writer``: COPY a
fixture case (the runnable ``in/`` + ``out/`` -- run.sh, env.sh, coef, config,
gases, surface, geometry, pressure grid) and OVERLAY only ``atm/t.txt`` and
``atm/q.txt`` with the model's T / Q (RTTOV gas_units=2 ppmv-moist). The model
T/Q ride the FIXTURE's pressure grid (p_half/gases/surface kept), so they must
match the fixture's layer count (the overlay validates length). The case is
trimmed to the RttovInput's nprofiles. The rttov_test config references inputs by
RELATIVE path (``../in/...``), so a copied case is self-contained and runnable.

``make_live_run_k`` is the live ``run_k(RttovInput) -> (bt, K, rad_quality)`` the
P6 operator injects: write the case, run it OUT-OF-PROCESS via
``rttov_runner.run_rttov_k`` (OMP fence, freshness gate), and reorder the
RttovKOutput (its field order is (bt, rad_quality, k)) to the (bt, K, rad_quality)
contract. Env-coupled: needs AD_RTTOV_HOME's fixture case + the RTTOV exe.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .rttov_runner import ad_rttov_home, run_rttov_k

# The ami/501 GK2A AMI fixture case (6 profiles x 16 channels, 69 layers).
_AMI501_FIXTURE = "external/rttov14/src/rttov_test/tests.1.gfortran-openmp/ami/501"


def default_fixture_case_dir() -> Path:
    """Resolve the ami/501 fixture case under AD_RTTOV_HOME (design 14.1)."""
    return ad_rttov_home() / _AMI501_FIXTURE


def _format_rttov_vector(values) -> str:
    """RTTOV ASCII profile vector: one ``%.6E`` value per line (matches the fixture
    format + the AD-RTTOV overlay writer). %.6E is ~7 sig figs ~= RTTOV's internal
    single precision, so it is not the precision floor for the run. NOTE for future
    FD-through-RTTOV checks: a finite-difference T/Q perturbation must exceed this
    ASCII resolution (and RTTOV's float32 input resolution) to survive the round-trip
    -- bump the precision here if a tighter FD step is ever needed."""
    return "".join(f"{float(v):.6E}\n" for v in values)


def _fixture_count(path: Path) -> int:
    return len([ln for ln in path.read_text().splitlines() if ln.strip()])


def _overlay_atm(profile_dir: Path, field_file: str, values) -> None:
    path = profile_dir / "atm" / field_file
    if not path.is_file():
        raise FileNotFoundError(f"fixture profile missing {path}")
    n_fix = _fixture_count(path)
    if n_fix != len(values):
        raise ValueError(
            f"{path}: model length {len(values)} != fixture layer count {n_fix} -- "
            "the model T/Q must be interpolated onto the fixture's layer grid before overlay.")
    path.write_text(_format_rttov_vector(values))


def _as_channel_id(c) -> int:
    """Strict 1-based RTTOV channel id: reject bool / non-integral / non-positive.

    A bare ``int(c)`` would silently truncate a fractional id (``7.9 -> 7``, a
    DIFFERENT instrument band) -- reject-don't-drop."""
    if isinstance(c, bool):
        raise ValueError(f"channel {c!r} is a bool, not a channel id.")
    try:
        ci = int(c)
    except (TypeError, ValueError):
        raise ValueError(f"channel {c!r} is not an integer channel id.")
    if ci != c:   # fractional float (7.9) or stringy ('7') -> not an exact integer id
        raise ValueError(f"channel {c!r} is not an exact integer channel id.")
    if ci < 1:
        raise ValueError(f"channel {c!r} must be a positive (1-based) channel id.")
    return ci


def _write_channels_lprofiles(in_dir: Path, nprofiles: int, channels) -> int:
    """Author channels.txt + lprofiles.txt from the RttovInput (NOT trimmed from the
    fixture). The fixture's channel IDs are NOT necessarily the requested ones --
    keeping them would silently run the wrong channels (BT/K parse fine but mean a
    different instrument band). Each profile uses the SAME requested ``channels``;
    lprofiles maps every channel-calc of profile p to profile id p (1-based).
    Returns the total chanprof = nprofiles * len(channels) (the namelist nchannels).
    """
    ch = [_as_channel_id(c) for c in channels]
    if not ch:
        raise ValueError("RttovInput.config.channels is empty -- need >=1 channel.")
    chan_line = " ".join(str(c) for c in ch) + "\n"
    (in_dir / "channels.txt").write_text(chan_line * nprofiles)
    lpro = "".join(" ".join([str(p)] * len(ch)) + "\n" for p in range(1, nprofiles + 1))
    (in_dir / "lprofiles.txt").write_text(lpro)
    return nprofiles * len(ch)


def _verify_fixture_contract(config_path: Path, rttov_config) -> None:
    """The run uses the FIXTURE's namelist (adk_bt/gas_units/do_k), not the
    RttovInput's options -- so cross-check that the fixture actually produces what
    the obs operator assumes. A wrong ``fixture_case_dir`` that computed radiance-K
    (adk_bt=.FALSE.), no K (do_k=.FALSE.), or a different gas unit would silently
    make every K/Q mean something else (reject-don't-drop: the RttovInput's forced
    options would otherwise be silently ignored in favour of the fixture's)."""
    text = config_path.read_text()

    def _is_true(name: str) -> bool:
        # ^-anchored (re.M) so a stray substring/duplicate line can't be the first
        # match ahead of the real namelist line.
        m = re.search(rf"^\s*defn%{re.escape(name)}\s*=\s*(\.TRUE\.|\.FALSE\.)", text, re.M)
        return m is not None and m.group(1) == ".TRUE."

    bad = []
    if not _is_true("do_k"):
        bad.append("defn%do_k must be .TRUE. (the case must compute the K-matrix)")
    if not _is_true("opts%config%adk_bt"):
        bad.append("defn%opts%config%adk_bt must be .TRUE. (else K is radiance-K, not BT-K)")
    m = re.search(r"^\s*defn%run_gas_units\s*=\s*(\d+)", text, re.M)
    run_gu = int(m.group(1)) if m else None
    if run_gu != rttov_config.gas_units:
        bad.append(
            f"defn%run_gas_units={run_gu} != RttovInput.config.gas_units="
            f"{rttov_config.gas_units} (the run would use a different gas unit than packed)")
    if bad:
        raise ValueError(
            f"{config_path}: fixture namelist violates the obs-operator contract -- "
            + "; ".join(bad))


def fixture_layer_pressure(fixture_case_dir=None, *, profile: str = "001"):
    """Reference RTTOV layer pressure for a fixture profile, derived from its p_half.

    The fixture is layer-based and exposes only p_half (no f_p), so there is no
    authoritative layer-pressure file. This returns a sensible interpolation TARGET
    -- the log-midpoint (geometric mean) of consecutive half-levels, with the TOA
    layer (p_half=0) falling back to the arithmetic midpoint. Callers interpolate
    model T/Q onto this grid and pass them via PASSTHROUGH (cfg.rttov_layer_pressure
    left as the grid for the interp, but the resulting profile['P'] must NOT be sent
    to write_rttov_case -- the run ignores layer pressure, so the writer rejects it).
    """
    import numpy as np
    fixture = Path(fixture_case_dir) if fixture_case_dir is not None else default_fixture_case_dir()
    ph = np.loadtxt(fixture / "in" / "profiles" / profile / "atm" / "p_half.txt")
    lo, hi = ph[:-1], ph[1:]
    lay = np.sqrt(np.clip(lo, 0.0, None) * hi)          # log-midpoint (geometric mean)
    return np.where(lo <= 0.0, 0.5 * (lo + hi), lay)    # TOA (p_half=0): arithmetic midpoint


def _check_grid_matches_fixture(profile_dir: Path, p_half_model) -> None:
    """The run keeps the fixture's p_half (model T/Q are overlaid onto the fixture
    grid). If the RttovInput carries a P_HALF that differs, the model T/Q were built
    for a DIFFERENT vertical grid than the run uses -> silently wrong BT. Reject:
    cfg.rttov_level_pressure must BE the fixture grid (design 14.1)."""
    import numpy as np
    fix = np.loadtxt(profile_dir / "atm" / "p_half.txt")
    model = np.asarray(p_half_model, dtype=float).reshape(-1)
    if fix.shape != model.shape or not np.allclose(model, fix, rtol=1e-5, atol=1e-9):
        raise ValueError(
            f"{profile_dir}/atm/p_half.txt: RttovInput P_HALF does not match the "
            "fixture grid -- interpolate the model T/Q onto the fixture's p_half "
            "before overlay (cfg.rttov_level_pressure must be the fixture grid).")


def _patch_config_counts(config_path: Path, nprofiles: int, nchannels_total: int) -> None:
    """Rewrite the authoritative ``defn%nprofiles`` / ``defn%nchannels`` in the
    rttov_test namelist. RTTOV reads the profile/channel COUNT from this namelist
    (not from the in/ dir listing), so a trimmed case whose namelist still says
    nprofiles=6 fails ('Cannot read from channels.txt') -- the reader expects 6
    lines. ``nchannels_total`` is the total chanprof (Σ channels over profiles)."""
    if not config_path.is_file():
        raise FileNotFoundError(f"fixture config missing {config_path}")
    text = config_path.read_text()
    text, n1 = re.subn(r"(?m)^(\s*defn%nprofiles\s*=\s*)\d+", rf"\g<1>{nprofiles}", text)
    text, n2 = re.subn(r"(?m)^(\s*defn%nchannels\s*=\s*)\d+", rf"\g<1>{nchannels_total}", text)
    if n1 != 1 or n2 != 1:
        raise ValueError(
            f"{config_path}: expected one defn%nprofiles and one defn%nchannels "
            f"line (found {n1}/{n2}); cannot retarget the case profile count.")
    config_path.write_text(text)


def write_rttov_case(rttov_input, out_case_dir, *, fixture_case_dir=None, overwrite=False) -> Path:
    """Copy the fixture case and overlay atm/t.txt + atm/q.txt from ``rttov_input``.

    Returns the ``out/`` subdir (containing run.sh) for ``run_rttov_k``. The case is
    trimmed to ``rttov_input.nprofiles`` profiles (extra fixture profiles removed;
    channels/lprofiles authored from ``config.channels``). Never modifies the fixture.

    The run uses the FIXTURE's coefficient file regardless of
    ``rttov_input.config.coef_id`` (coef_id is provenance / config-hash only -- it is
    NOT a coef selector); the caller must point ``fixture_case_dir`` at a case built
    for the intended sensor. RttovInput fields the writer cannot honor are rejected,
    never silently dropped (surface/geometry, a P_HALF off the fixture grid, or a
    fixture whose namelist contradicts the forced K/gas-unit contract).
    """
    fixture = Path(fixture_case_dir) if fixture_case_dir is not None else default_fixture_case_dir()
    out = Path(out_case_dir)
    if not fixture.is_dir():
        raise FileNotFoundError(
            f"RTTOV fixture case not found: {fixture} (set AD_RTTOV_HOME / install ami/501).")
    if out.exists():
        if not overwrite:
            raise FileExistsError(f"out_case_dir already exists: {out} (use overwrite=True).")
        if out.resolve() == fixture.resolve():
            raise ValueError("refusing to overwrite the fixture case in place.")
        shutil.rmtree(out)
    shutil.copytree(fixture, out)

    # The run uses the fixture's config/grid/gases/surface/geometry -- only T/Q +
    # channels come from the RttovInput. Reject RttovInput fields the writer would
    # otherwise silently ignore (reject-don't-drop):
    cfg = rttov_input.config
    if getattr(cfg, "surface", None) is not None or getattr(cfg, "geometry", None) is not None:
        raise NotImplementedError(
            "RttovInputConfig.surface/geometry are not yet written into the case "
            "(the fixture's are used) -- pass None until the overlay lands, else they "
            "would be silently ignored.")
    _verify_fixture_contract(out / "out" / "rttov_test.txt", cfg)

    nprof = rttov_input.nprofiles
    prof_root = out / "in" / "profiles"
    prof_ids = sorted(d.name for d in prof_root.iterdir() if d.is_dir())
    if nprof > len(prof_ids):
        raise ValueError(
            f"RttovInput has {nprof} profiles but fixture provides only {len(prof_ids)}.")
    t_all = rttov_input.profile["T"]
    q_all = rttov_input.profile["Q"]
    # P_HALF is REQUIRED: the run keeps the fixture's p_half, so P_HALF is the only
    # witness that the model T/Q were built for the fixture grid. Without it the
    # writer would blindly place possibly-mis-gridded T/Q on the fixture grid (silent
    # wrong BT). profile["P"] (p_lay) is intentionally NOT consumed -- RTTOV is
    # layer-based and derives layers from p_half (the fixture has no f_p), so a
    # validated P_HALF fully fixes the grid and P would be redundant.
    ph_all = rttov_input.profile.get("P_HALF")
    if ph_all is None:
        raise ValueError(
            "RttovInput.profile lacks P_HALF -- set cfg.rttov_level_pressure to the "
            "fixture p_half so the writer can verify the model T/Q are on the fixture "
            "grid (the run keeps the fixture p_half; an unverified grid is rejected).")
    # profile["P"] (layer pressure, from cfg.rttov_layer_pressure) is REJECTED, not
    # bracket-checked: the layer-based run derives layers from the fixture p_half and
    # takes NO layer-pressure input (the fixture has no f_p), and there is no single
    # authoritative layer-mean convention to validate it against -- so accepting it
    # (even bracketed) would silently honor a grid the run ignores. Interpolate model
    # T/Q onto fixture_layer_pressure() and supply them WITHOUT a layer pressure.
    if "P" in rttov_input.profile:
        raise ValueError(
            "RttovInput carries a layer pressure (profile['P'], from "
            "cfg.rttov_layer_pressure) that the layer-based RTTOV run does not consume "
            "(it derives layers from the fixture p_half) -- the writer will not "
            "silently accept an unhonored grid. Interpolate the model T/Q onto "
            "fixture_layer_pressure() and supply them via passthrough (no p_lay).")
    for p in range(nprof):
        pdir = prof_root / prof_ids[p]
        _overlay_atm(pdir, "t.txt", t_all[p])
        _overlay_atm(pdir, "q.txt", q_all[p])
        _check_grid_matches_fixture(pdir, ph_all[p])
    # trim the case to exactly nprof profiles so the run/parse profile count matches.
    for extra in prof_ids[nprof:]:
        shutil.rmtree(prof_root / extra)
    # author channels.txt + lprofiles.txt from the requested channels (not the
    # fixture's) and patch the authoritative namelist counts. Per-profile aux files
    # (datetime/angles/be/gas_units/prof_id/near_surface/skin) live INSIDE each
    # in/profiles/NNN/, so removing the extra profile dirs already drops them; only
    # the top-level channels/lprofiles + namelist counts need retargeting.
    nchannels_total = _write_channels_lprofiles(out / "in", nprof, rttov_input.config.channels)
    _patch_config_counts(out / "out" / "rttov_test.txt", nprof, nchannels_total)
    return out / "out"


def make_live_run_k(out_case_dir, *, fixture_case_dir=None, timeout=None):
    """Build the live ``run_k(RttovInput) -> (bt, K, rad_quality)`` for RttovObsOp.

    Each call: write_rttov_case (overlay T/Q onto the fixture) -> out-of-process
    run_rttov_k (single runK: BT + K) -> reorder RttovKOutput to (bt, K,
    rad_quality). ``out_case_dir`` is rewritten each call (overwrite=True).

    NOT concurrency-safe: ``out_case_dir`` is a single shared, rewritten directory,
    so two overlapping calls on the SAME closure would clobber each other's case
    mid-run (-> wrong BT/K -> wrong gradient). Sequential use (one DA-window backward
    at a time) is fine; for concurrent callers give each its own ``out_case_dir``, or
    use ``rttov_obs_operator.default_run_k`` which allocates a unique per-call dir.
    """
    def _run_k(rttov_input):
        case_out = write_rttov_case(rttov_input, out_case_dir,
                                    fixture_case_dir=fixture_case_dir, overwrite=True)
        out = run_rttov_k(case_out, nchannels=len(rttov_input.config.channels),
                          expected_nprofiles=rttov_input.nprofiles, timeout=timeout)
        # RttovKOutput field order is (bt, rad_quality, k, ...) -> reorder to the
        # run_k contract (bt, K, rad_quality); never `tuple(out)`.
        return out.bt, out.k, out.rad_quality

    return _run_k
