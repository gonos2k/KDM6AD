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

from .rttov_runner import ad_rttov_home, rttov_runtime_root, run_rttov_k

# The ami/501 GK2A AMI clear-sky fixture (6 profiles x 16 channels, 69 layers).
_AMI501_FIXTURE = "external/rttov14/src/rttov_test/tests.1.gfortran-openmp/ami/501"
# The AMI ALL-SKY cloud fixture (ami/501 + f_hydrotable + cloud input files). RTTOV
# allocates nhydro = ntypes(7) + 1 (Baran) = 8 for VIS/IR, so hydro.txt has 8 columns:
# OPAC 1-5, CLW-Deff liquid (col 6), Baum ice (col 7), Baran (col 8, unused). hydro_deff
# has nhydro-1 = 7 columns (Baran excluded). Liquid/ice are the Deff-bearing slots 6/7.
_AMI_CLOUD_FIXTURE = "external/rttov14/src/rttov_test/tests.1.gfortran-openmp/ami/cloud"
_NHYDRO = 8            # hydro.txt columns (7 hydrotable types + Baran)
_NHYDRO_DEFF = 7       # hydro_deff.txt columns (nhydro - 1, Baran has no Deff)
_LIQ_COL = 5           # 0-based: slot 6 = CLW-Deff liquid
_ICE_COL = 6           # 0-based: slot 7 = Baum ice
# RttovInput.profile cloud keys -> (matrix, column). content [g/m^3], Deff [micron].
_CLOUD_KEYS = ("HYDRO6", "HYDRO7", "HYDRO_DEFF6", "HYDRO_DEFF7", "CFRAC")


# Project-local runtime layout (tools/build_rttov_runtime.sh): cases/ami/{501,cloud}.
_RUNTIME_AMI501 = "cases/ami/501"
_RUNTIME_AMI_CLOUD = "cases/ami/cloud"


def default_fixture_case_dir() -> Path:
    """Resolve the ami/501 clear-sky fixture: prefer the project-local rttov_runtime
    bundle (self-contained), else AD_RTTOV_HOME (design 14.1)."""
    rt = rttov_runtime_root()
    if rt is not None and (rt / _RUNTIME_AMI501).is_dir():
        return rt / _RUNTIME_AMI501
    return ad_rttov_home() / _AMI501_FIXTURE


def cloud_fixture_case_dir() -> Path:
    """Resolve the AMI all-sky cloud fixture: prefer the project-local rttov_runtime
    bundle (self-contained), else AD_RTTOV_HOME (Phase 5)."""
    rt = rttov_runtime_root()
    if rt is not None and (rt / _RUNTIME_AMI_CLOUD).is_dir():
        return rt / _RUNTIME_AMI_CLOUD
    return ad_rttov_home() / _AMI_CLOUD_FIXTURE


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


def _validate_cloud_domain(rttov_input) -> None:
    """Reject cloud values RTTOV would silently MISHANDLE (reject-don't-drop), before
    any filesystem mutation:
      * content (HYDRO6/7) must be finite and >= 0 (negative hydrometeor mass is
        unphysical and RTTOV does not guard it),
      * CFRAC must be finite and in [0, 1] (RTTOV expects a fraction),
      * Deff (HYDRO_DEFF6/7) must be finite, and > 0 in EVERY layer where the matching
        content > 0 -- a non-positive Deff in a cloudy layer trips RTTOV's positive-Deff
        gate (rttov_calc_hydro_deff.F90:125) to SILENTLY substitute the parametrized
        deff_param scheme, dropping the model's explicit effective diameter (and making
        the HYDRO_DEFF adjoint meaningless). Deff <= 0 in a CLEAR layer is fine (no
        content there), so the guard is content-coupled, not blanket-positive."""
    import numpy as np
    prof = rttov_input.profile
    for p in range(rttov_input.nprofiles):
        cfrac = np.asarray(prof["CFRAC"][p], dtype=float).reshape(-1)
        if not np.all(np.isfinite(cfrac)) or np.any(cfrac < 0.0) or np.any(cfrac > 1.0):
            raise ValueError(f"profile {p}: CFRAC must be finite and in [0, 1].")
        for content_key, deff_key in (("HYDRO6", "HYDRO_DEFF6"), ("HYDRO7", "HYDRO_DEFF7")):
            c = np.asarray(prof[content_key][p], dtype=float).reshape(-1)
            d = np.asarray(prof[deff_key][p], dtype=float).reshape(-1)
            if not np.all(np.isfinite(c)) or np.any(c < 0.0):
                raise ValueError(f"profile {p}: {content_key} must be finite and >= 0.")
            if not np.all(np.isfinite(d)):
                raise ValueError(f"profile {p}: {deff_key} must be finite.")
            if np.any((c > 0.0) & ~(d > 0.0)):
                raise ValueError(
                    f"profile {p}: {deff_key} must be > 0 wherever {content_key} > 0 -- a "
                    "non-positive Deff in a cloudy layer would silently fall back to "
                    "deff_param, dropping the model's explicit effective diameter.")


def _write_matrix(path: Path, rows) -> None:
    """Write a [nlay, ncol] matrix as space-separated ``%.6E`` per layer row."""
    path.write_text("".join(" ".join(f"{float(v):.6E}" for v in row) + "\n" for row in rows))


def _overlay_cloud(profile_dir: Path, rttov_input, p: int, nlay: int) -> None:
    """Overlay the all-sky cloud input files for profile ``p`` from the RttovInput.

    hydro.txt [nlay x 8]: content g/m^3 with liquid (HYDRO6) in slot-6 col, ice
    (HYDRO7) in slot-7 col, all other slots (OPAC 1-5, Baran 8) zero. hydro_deff.txt
    [nlay x 7]: effective DIAMETER micron, liquid/ice Deff in the same slot-6/7 cols.
    hydro_frac.txt: a ``hydro_frac_eff`` line then [nlay x 1] cloud fraction (CFRAC).
    The fixture provides f_hydrotable + the cloud namelist switches; the run derives
    layers from p_half, so the model cloud rides the fixture layer grid.

    hydro_deff.txt is WRITTEN here (not required to pre-exist): rttov_test reads it
    whenever the file exists (driver INQUIRE), and RTTOV's positive-Deff gate then uses
    the model's explicit Deff wherever it is > 0, falling back to deff_param.txt
    (the parametrized scheme) elsewhere -- so deff_param.txt MUST be present as the
    fallback (a fixture without it would error in the unconditional driver read)."""
    import numpy as np
    atm = profile_dir / "atm"
    # Cloud-fixture contract: the run reads content (hydro.txt) + fraction
    # (hydro_frac.txt) and ALWAYS reads deff_param.txt (driver line ~1691, no INQUIRE)
    # as the Deff fallback. Reject a non-cloud / Deff-incomplete fixture rather than
    # writing files the run will not read.
    for fn in ("hydro.txt", "hydro_frac.txt", "deff_param.txt"):
        if not (atm / fn).is_file():
            raise FileNotFoundError(
                f"cloud fixture profile missing {atm / fn} -- not a cloud-capable fixture "
                "(need hydro.txt + hydro_frac.txt + deff_param.txt fallback).")
    # UNIT contract: the model emits hydrometeor CONTENT in g/m^3, so the fixture must
    # declare mmr_hydro = F (g/m^3). mmr_hydro is read only if mmr_hydro_aer.txt EXISTS
    # (driver :1657 INQUIRE) and has NO type default when absent -- so a missing file or
    # an mmr_hydro=T would SILENTLY reinterpret the overlaid g/m^3 as kg/kg (BT wrong by
    # orders of magnitude). Reject-don't-drop.
    mmr_path = atm / "mmr_hydro_aer.txt"
    if not mmr_path.is_file():
        raise FileNotFoundError(
            f"cloud fixture profile missing {mmr_path} -- the hydrometeor unit flag is "
            "undefined without it (the model emits g/m^3 and needs mmr_hydro=F).")
    m = re.search(r"(?im)^\s*mmr_hydro\s*=\s*\.?\s*([TF])", mmr_path.read_text())
    if m is None or m.group(1).upper() != "F":
        raise ValueError(
            f"{mmr_path}: cloud fixture must set mmr_hydro = F (g/m^3) to match the model's "
            f"emitted content units (got {'mmr_hydro=' + m.group(1) if m else 'no mmr_hydro line'}).")
    # HYDROTABLE-dimension contract: the writer's slot layout (nhydro=8 = ntypes 7 +
    # Baran; liquid=col idx5, ice=col idx6) is hydrotable-specific. The fixture's
    # EXISTING hydro.txt column count IS nhydro -- verify it equals _NHYDRO before
    # overwriting, so a fixture built on a different hydrotable (different ntypes, hence
    # a different liquid/ice column) is rejected rather than silently mis-slotted.
    existing = [ln for ln in (atm / "hydro.txt").read_text().splitlines() if ln.strip()]
    ncol_fix = len(existing[0].split()) if existing else 0
    if ncol_fix != _NHYDRO:
        raise ValueError(
            f"{atm / 'hydro.txt'}: fixture hydro has {ncol_fix} columns but the AMI all-sky "
            f"writer assumes nhydro={_NHYDRO} (ntypes 7 + Baran), liquid=col {_LIQ_COL + 1} / "
            f"ice=col {_ICE_COL + 1} -- a different hydrotable would place the Deff-bearing "
            "slots in different columns. Use the AMI hydrotable fixture.")

    def _col(key):
        v = np.asarray(rttov_input.profile[key][p], dtype=float).reshape(-1)
        if v.shape[0] != nlay:
            raise ValueError(f"cloud field {key} length {v.shape[0]} != fixture layers {nlay}.")
        return v

    H = np.zeros((nlay, _NHYDRO))
    H[:, _LIQ_COL] = _col("HYDRO6")
    H[:, _ICE_COL] = _col("HYDRO7")
    D = np.zeros((nlay, _NHYDRO_DEFF))
    D[:, _LIQ_COL] = _col("HYDRO_DEFF6")
    D[:, _ICE_COL] = _col("HYDRO_DEFF7")
    _write_matrix(atm / "hydro.txt", H)
    _write_matrix(atm / "hydro_deff.txt", D)
    with open(atm / "hydro_frac.txt", "w") as fh:
        fh.write("0.000000E+00\n")                         # hydro_frac_eff (overlap, unused here)
        fh.write(_format_rttov_vector(_col("CFRAC")))


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


def _verify_cloud_namelist(config_path: Path) -> None:
    """A cloud RttovInput needs a fixture whose namelist actually ENABLES hydrometeor
    scattering: defn%f_hydro (content) AND defn%f_hydro_frac (fraction) must be set to
    non-empty paths (rttov_test gates ``opts%scatt%hydrometeors`` on both -- driver
    ~line 1050). A fixture with the cloud atm/ files present but f_hydro/f_hydro_frac
    unset would run CLEAR-SKY while overlaying the model cloud -> silently wrong cloud
    BT/K. Reject-don't-drop: the overlaid hydro.txt/hydro_deff.txt would be ignored."""
    text = config_path.read_text()
    missing = []
    for name in ("f_hydro", "f_hydro_frac"):
        # non-empty quoted path (the driver default is "" = disabled).
        m = re.search(rf"^\s*defn%{re.escape(name)}\s*=\s*['\"]([^'\"]*)['\"]", text, re.M)
        if m is None or not m.group(1).strip():
            missing.append(name)
    if missing:
        raise ValueError(
            f"{config_path}: cloud RttovInput requires a hydrometeor-enabled fixture but "
            f"defn%{'/defn%'.join(missing)} is unset -- the overlaid cloud would run "
            "clear-sky (use the AMI cloud fixture / a hydrometeor-enabled case).")


def _verify_solar_namelist(config_path: Path) -> None:
    """A solar-channel observable (Phase 7) needs the fixture to (a) run solar
    (defn%opts%rt_all%solar=.TRUE., so RADIANCE%REFL is produced) AND (b) seed the
    REFLECTANCE adjoint (defn%opts%config%adk_refl=.TRUE., so the solar-channel K rows
    are d(REFL)/d(profile), not BT-K). If solar runs but adk_refl is off, the run STILL
    emits a REFL forward block, but the solar K rows are BT-K -- merge_solar_observable
    would return the REFL observable and RttovObsOp.backward would contract it against a
    BT-K row -> a finite, plausible, but WRONG gradient. This mirrors the adk_bt contract
    check; reject-don't-drop (Codex Phase-7 review HIGH)."""
    text = config_path.read_text()

    def _is_true(name: str) -> bool:
        m = re.search(rf"^\s*defn%{re.escape(name)}\s*=\s*(\.TRUE\.|\.FALSE\.)", text, re.M)
        return m is not None and m.group(1) == ".TRUE."

    bad = []
    if not _is_true("opts%rt_all%solar"):
        bad.append("defn%opts%rt_all%solar must be .TRUE. (else no RADIANCE%REFL is produced)")
    if not _is_true("opts%config%adk_refl"):
        bad.append("defn%opts%config%adk_refl must be .TRUE. (else solar-channel K is BT-K, "
                   "not d(REFL); a REFL observable would contract against a BT-K row)")
    if bad:
        raise ValueError(
            f"{config_path}: solar-channel observable requires a reflectance-K fixture -- "
            + "; ".join(bad))


def _coef_channel_types(coef_path: Path) -> dict:
    """Parse the rtcoef SOLAR_SPECTRUM section -> {1-based channel id: type}, type
    0=thermal, 1=thermal+solar, 2=solar (rtcoef ASCII: after the ``SOLAR_SPECTRUM``
    header + ``!`` comment lines, each data row is ``<chan> <type> <solar_spectrum>
    <rayleigh>``; a ``!`` line after the data ends the section)."""
    types: dict = {}
    in_section = False
    for line in coef_path.read_text().splitlines():
        s = line.strip()
        if not in_section:
            if s == "SOLAR_SPECTRUM":
                in_section = True
            continue
        if not s or s.startswith("!"):
            if types:                 # a comment/blank AFTER the data rows ends the section
                break
            continue                  # header comments precede the data
        parts = s.split()
        if (len(parts) < 2 or not parts[0].lstrip("-").isdigit()
                or not parts[1].lstrip("-").isdigit()):
            break                     # a non-data line ends the section
        types[int(parts[0])] = int(parts[1])
    return types


def _resolve_coef_path(case_root: Path) -> Path:
    """The rtcoef .dat path the run uses: ``defn%coef_prefix`` (out/rttov_test.txt) +
    ``defn%f_coef`` (in/coef.txt)."""
    nl = (case_root / "out" / "rttov_test.txt").read_text()
    mp = re.search(r"(?m)^\s*defn%coef_prefix\s*=\s*'([^']*)'", nl)
    coef_txt = (case_root / "in" / "coef.txt").read_text()
    mc = re.search(r"(?m)^\s*defn%f_coef\s*=\s*'([^']*)'", coef_txt)
    if mp is None or mc is None or not mp.group(1).strip() or not mc.group(1).strip():
        raise ValueError(f"{case_root}: cannot resolve coef path (defn%coef_prefix / "
                         "defn%f_coef missing) -- needed to verify solar channel types.")
    return Path(mp.group(1)) / mc.group(1)


def _verify_solar_channel_types(case_root: Path, solar_ids) -> None:
    """Every requested solar id must be a PURE-SOLAR (type 2) channel per the coef
    SOLAR_SPECTRUM. A thermal (type 0) id would get a REFL(=0) observable contracted
    against its BT-K row, and a thermal+solar (type 1, e.g. SW038) id has a MIXED K
    (BT+REFL seeded) -- neither is a clean reflectance observable. reject-don't-drop:
    the writer otherwise accepts any in-range id as 'solar' (Codex stop-review)."""
    coef_path = _resolve_coef_path(case_root)
    if not coef_path.is_file():
        raise FileNotFoundError(
            f"coef {coef_path} not found -- cannot verify solar channel types.")
    types = _coef_channel_types(coef_path)
    if not types:
        raise ValueError(f"{coef_path}: no SOLAR_SPECTRUM channel types parsed.")
    bad = [f"ch{ci}(type {types.get(ci)})"
           for ci in sorted(_as_channel_id(c) for c in solar_ids) if types.get(ci) != 2]
    if bad:
        raise ValueError(
            f"solar_channels {bad} are not pure-solar (type 2) per the coef SOLAR_SPECTRUM "
            "-- only type-2 channels have a clean REFL observable + reflectance-K; thermal "
            "(type 0) and thermal+solar (type 1, e.g. SW038) channels must be used as BT/IR.")


def _verify_cloud_hydrotable(case_root: Path) -> None:
    """A cloud run needs a VIS/IR scattering hydrotable; the fixture names it in
    in/coef.txt (defn%f_hydrotable). A missing/empty entry means RTTOV has no optical
    properties for the overlaid hydrometeors (the run errors), and -- more subtly --
    the slot<->type mapping the writer assumes (HYDRO6=liquid/HYDRO7=ice) is defined by
    THAT table, so the cloud fixture must carry one. Require it to be set (the file's
    existence is resolved against the run's coef prefix and checked loudly at run time)."""
    coef = case_root / "in" / "coef.txt"
    if not coef.is_file():
        raise FileNotFoundError(
            f"cloud fixture missing {coef} (defn%f_hydrotable lives here).")
    m = re.search(r"(?im)^\s*defn%f_hydrotable\s*=\s*['\"]([^'\"]*)['\"]", coef.read_text())
    if m is None or not m.group(1).strip():
        raise ValueError(
            f"{coef}: cloud fixture must set defn%f_hydrotable (the VIS/IR scattering "
            "coefficient table) -- without it the overlaid hydrometeors have no optical "
            "properties and the slot<->type mapping is undefined.")


def _layer_pressure_from_half(ph):
    """Canonical layer pressure from half-levels: log-midpoint (geometric mean) of
    consecutive half-levels, with the TOA layer (p_half=0) falling back to the
    arithmetic midpoint. This is the ONE convention the writer defines + validates,
    so an interp caller must use the same (via fixture_layer_pressure())."""
    import numpy as np
    ph = np.asarray(ph, dtype=float).reshape(-1)
    lo, hi = ph[:-1], ph[1:]
    lay = np.sqrt(np.clip(lo, 0.0, None) * hi)          # log-midpoint (geometric mean)
    return np.where(lo <= 0.0, 0.5 * (lo + hi), lay)    # TOA (p_half=0): arithmetic midpoint


def fixture_layer_pressure(fixture_case_dir=None, *, profile: str = "001"):
    """Canonical RTTOV layer pressure for a fixture profile (the interp TARGET).

    The fixture is layer-based and exposes only p_half (no f_p), so there is no
    authoritative layer-pressure file -- the writer DEFINES the canonical layer grid
    here (`_layer_pressure_from_half`: log-midpoint, TOA arithmetic). The live obs
    path sets ``cfg.rttov_layer_pressure`` to this so model T/Q are interpolated onto
    the fixture layers; the resulting ``profile['P']`` IS sent to write_rttov_case,
    which validates it equals this grid (an off-grid layer pressure is rejected).
    Each fixture profile has its own p_half, so this is per-profile.
    """
    import numpy as np
    fixture = Path(fixture_case_dir) if fixture_case_dir is not None else default_fixture_case_dir()
    ph = np.loadtxt(fixture / "in" / "profiles" / profile / "atm" / "p_half.txt")
    return _layer_pressure_from_half(ph)


def _check_grid_matches_fixture(profile_dir: Path, p_half_model, p_lay_model=None) -> None:
    """The run keeps the fixture's p_half (model T/Q are overlaid onto the fixture
    grid). If the RttovInput carries a P_HALF that differs, the model T/Q were built
    for a DIFFERENT vertical grid than the run uses -> silently wrong BT. Reject:
    cfg.rttov_level_pressure must BE the fixture grid (design 14.1).

    If a layer pressure ``p_lay_model`` (profile["P"], from cfg.rttov_layer_pressure)
    is present, it must equal the canonical fixture layer grid (the log-midpoint of
    THIS profile's p_half). This HONORS the interp path -- the caller interpolates
    model T/Q onto ``fixture_layer_pressure()`` and the writer verifies it -- while
    still rejecting an off-grid layer pressure (T/Q placed on the wrong layers)."""
    import numpy as np
    fix = np.loadtxt(profile_dir / "atm" / "p_half.txt")
    model = np.asarray(p_half_model, dtype=float).reshape(-1)
    if fix.shape != model.shape or not np.allclose(model, fix, rtol=1e-5, atol=1e-9):
        raise ValueError(
            f"{profile_dir}/atm/p_half.txt: RttovInput P_HALF does not match the "
            "fixture grid -- interpolate the model T/Q onto the fixture's p_half "
            "before overlay (cfg.rttov_level_pressure must be the fixture grid).")
    if p_lay_model is not None:
        canon = _layer_pressure_from_half(fix)
        p = np.asarray(p_lay_model, dtype=float).reshape(-1)
        if p.shape != canon.shape or not np.allclose(p, canon, rtol=1e-5, atol=1e-9):
            raise ValueError(
                f"{profile_dir}/atm/p_half.txt: RttovInput layer pressure (profile['P'], "
                "cfg.rttov_layer_pressure) does not match the fixture's canonical layer "
                "grid -- set cfg.rttov_layer_pressure = fixture_layer_pressure(...) so the "
                "model T/Q are interpolated onto the fixture layers (the run derives layers "
                "from the fixture p_half).")


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


def write_rttov_case(rttov_input, out_case_dir, *, fixture_case_dir=None, overwrite=False,
                     solar_channels=()) -> Path:
    """Copy the fixture case and overlay atm/t.txt + atm/q.txt from ``rttov_input``.

    If ``rttov_input`` carries the full all-sky cloud set (HYDRO6/7 content +
    HYDRO_DEFF6/7 + CFRAC), the AMI cloud fixture is used (unless ``fixture_case_dir``
    is given) and atm/hydro.txt + atm/hydro_deff.txt + atm/hydro_frac.txt are overlaid
    too -- the liquid (slot-6) / ice (slot-7) Deff-bearing columns from the model.

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
    out = Path(out_case_dir)
    # Validate the RttovInput BEFORE any filesystem mutation (no leftover dir on reject).
    # The run uses the fixture's config/grid/gases/surface/geometry -- only T/Q (+ cloud)
    # + channels come from the RttovInput; reject fields the writer would silently ignore.
    cfg = rttov_input.config
    if getattr(cfg, "surface", None) is not None or getattr(cfg, "geometry", None) is not None:
        raise NotImplementedError(
            "RttovInputConfig.surface/geometry are not yet written into the case "
            "(the fixture's are used) -- pass None until the overlay lands, else they "
            "would be silently ignored.")
    # Reject cloud-family fields the writer does not recognize (a forbidden MW
    # RTTOV-SCATT slot like HYDRO1/HYDRO4, an extra HYDRO8, or a misspelled HYDRO6):
    # they would otherwise be silently dropped to a clear-sky run (reject-don't-drop,
    # and this fires even when no recognized cloud key is present).
    unknown_cloud = sorted(
        k for k in rttov_input.profile
        if (k.startswith("HYDRO") or k == "CFRAC") and k not in _CLOUD_KEYS)
    if unknown_cloud:
        raise ValueError(
            f"unrecognized cloud-family fields {unknown_cloud}: the AMI all-sky writer "
            f"handles only {list(_CLOUD_KEYS)} -- MW RTTOV-SCATT slots / extra "
            "hydrometeor types / misspellings are rejected, not silently dropped.")
    # All-sky: a cloud RttovInput (HYDRO6/7 content + HYDRO_DEFF6/7 + CFRAC) is overlaid
    # onto the AMI cloud fixture (f_hydrotable + cloud namelist switches). Require the
    # FULL cloud set -- a partial set would run with the fixture's stale cloud in the
    # missing slots (e.g. ice content but fixture Deff) -> silently wrong cloud BT/K.
    present = [k for k in _CLOUD_KEYS if k in rttov_input.profile]
    is_cloud = bool(present)
    if is_cloud and len(present) != len(_CLOUD_KEYS):
        raise ValueError(
            f"partial cloud RttovInput: have {present}, need all of {list(_CLOUD_KEYS)} "
            "-- a missing cloud field would inherit the fixture's stale value (wrong BT/K).")
    if is_cloud:
        _validate_cloud_domain(rttov_input)
    # Cloud RttovInput defaults to the AMI cloud fixture; an explicit fixture_case_dir
    # always wins (caller may target another cloud-capable sensor case).
    if fixture_case_dir is not None:
        fixture = Path(fixture_case_dir)
    elif is_cloud:
        fixture = cloud_fixture_case_dir()
    else:
        fixture = default_fixture_case_dir()
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
    # Everything past copytree may reject (a bad fixture contract, an off-grid P_HALF,
    # a profile-count mismatch, a cloud overlay error). On ANY failure remove the
    # just-copied case so no PARTIAL out_case_dir is left behind (else the next call
    # without overwrite=True would hit FileExistsError) -- reject-don't-drop (Codex F4).
    try:
        return _populate_case(out, rttov_input, cfg, is_cloud, solar_channels)
    except BaseException:
        shutil.rmtree(out, ignore_errors=True)
        raise


def _populate_case(out: Path, rttov_input, cfg, is_cloud: bool, solar_channels=()) -> Path:
    """Overlay the RttovInput onto the freshly-copied case ``out`` and return out/out.

    Split out of write_rttov_case so a post-copytree failure can be cleaned up by the
    caller (no partial case left behind)."""
    _verify_fixture_contract(out / "out" / "rttov_test.txt", cfg)
    if is_cloud:
        _verify_cloud_namelist(out / "out" / "rttov_test.txt")
        _verify_cloud_hydrotable(out)
    # Solar observable contract: if any REQUESTED channel is solar, the fixture must
    # produce reflectance-K (solar + adk_refl), else a REFL observable would contract
    # against a BT-K row -> silent wrong gradient (Codex Phase-7 review).
    if solar_channels:
        requested = {_as_channel_id(c) for c in rttov_input.config.channels}
        used_solar = requested & {_as_channel_id(c) for c in solar_channels}
        if used_solar:
            _verify_solar_namelist(out / "out" / "rttov_test.txt")
            _verify_solar_channel_types(out, used_solar)   # reject thermal/mixed ids

    nprof = rttov_input.nprofiles
    prof_root = out / "in" / "profiles"
    prof_ids = sorted(d.name for d in prof_root.iterdir() if d.is_dir())
    if nprof > len(prof_ids):
        raise ValueError(
            f"RttovInput has {nprof} profiles but fixture provides only {len(prof_ids)}.")
    t_all = rttov_input.profile["T"]
    q_all = rttov_input.profile["Q"]
    # P_HALF is REQUIRED: the run keeps the fixture's p_half, so P_HALF is the
    # half-level witness that the model T/Q were built for the fixture grid. Without
    # it the writer would blindly place possibly-mis-gridded T/Q on the fixture grid
    # (silent wrong BT). The layer witness is profile["P"] (validated below): RTTOV is
    # layer-based and derives layers from p_half (the fixture has no f_p), so neither
    # P_HALF nor P is written to the case -- both are grid witnesses for the T/Q.
    ph_all = rttov_input.profile.get("P_HALF")
    if ph_all is None:
        raise ValueError(
            "RttovInput.profile lacks P_HALF -- set cfg.rttov_level_pressure to the "
            "fixture p_half so the writer can verify the model T/Q are on the fixture "
            "grid (the run keeps the fixture p_half; an unverified grid is rejected).")
    # profile["P"] (layer pressure, from cfg.rttov_layer_pressure) is VALIDATED, not
    # silently accepted: it must equal the fixture's canonical layer grid
    # (fixture_layer_pressure()). This honors the interp path (caller interpolates
    # model T/Q onto fixture_layer_pressure()) while rejecting an off-grid layer
    # pressure. The layer pressure is not written to the case (the layer-based run
    # derives layers from p_half) -- it is purely the grid witness for the T/Q.
    pl_all = rttov_input.profile.get("P")
    for p in range(nprof):
        pdir = prof_root / prof_ids[p]
        _overlay_atm(pdir, "t.txt", t_all[p])
        _overlay_atm(pdir, "q.txt", q_all[p])
        _check_grid_matches_fixture(pdir, ph_all[p], None if pl_all is None else pl_all[p])
        if is_cloud:
            _overlay_cloud(pdir, rttov_input, p, len(t_all[p]))
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


# Raw flat PROFILES_K cloud field -> (ntype, per-slot liquid key, per-slot ice key).
# ntype/slot columns reuse the OVERLAY constants so the K read and the input write
# share ONE slot convention (liquid=_LIQ_COL=5, ice=_ICE_COL=6).
_CLOUD_K_FIELDS = (
    ("HYDRO", _NHYDRO, "HYDRO6", "HYDRO7"),
    ("HYDRO_DEFF", _NHYDRO_DEFF, "HYDRO_DEFF6", "HYDRO_DEFF7"),
)


def add_cloud_k_slots(k: dict, *, nlay: int) -> dict:
    """Augment a parsed K dict with the per-slot cloud K keys RttovObsOp.backward
    expects (HYDRO6/7 + HYDRO_DEFF6/7), derived from the raw flat PROFILES_K
    HYDRO/HYDRO_DEFF blocks. Mutates and returns ``k``.

    The live blocks are ``[nprofiles][nchannels][ntype*nlay]``, laid out TYPE-MAJOR
    (flat per chanprof = type0_lay0..type0_lay(nlay-1), type1_lay0..; i.e.
    ``flat.reshape(ntype, nlay)`` gives [type, layer]). VERIFIED empirically (Phase 6):
    with ice in layers 15-24 / liquid in 40-49, the HYDRO_DEFF K is nonzero EXACTLY at
    (those layers, cols 5/6). Liquid = column _LIQ_COL (5), ice = _ICE_COL (6) -- the
    SAME AMI VIS/IR convention the cloud overlay writes (so write-slot == read-slot).
    Each output key is (nprofiles, nchannels, nlay), matching the backward K-shape guard.

    No-op for a clear-sky K (no HYDRO blocks). reject-don't-drop: a flat length not
    equal to ntype*nlay (wrong hydrotable / layer count) is rejected rather than
    silently mis-slotted into a wrong-but-finite gradient."""
    import numpy as np
    for raw, ntype, liq_key, ice_key in _CLOUD_K_FIELDS:
        if raw not in k:
            continue
        arr = np.asarray(k[raw], dtype=float)            # (nprof, nch, ntype*nlay)
        if arr.ndim != 3:
            raise ValueError(f"PROFILES_K {raw!r} K has shape {arr.shape}, expected 3-D "
                             "[nprofiles, nchannels, ntype*nlay].")
        nprof, nch, L = arr.shape
        if L != ntype * nlay:
            raise ValueError(
                f"PROFILES_K {raw!r} flat length {L} != ntype*nlay = {ntype}*{nlay} = "
                f"{ntype * nlay} -- the (ntype, nlay) slot layout does not hold (wrong "
                "hydrotable / layer count); refusing to mis-slot the cloud K.")
        # type-major flat -> (nprof, nch, ntype, nlay): dim2 = hydrometeor type, dim3 = layer.
        slotted = arr.reshape(nprof, nch, ntype, nlay)
        k[liq_key] = slotted[:, :, _LIQ_COL, :]          # (nprof, nch, nlay) liquid
        k[ice_key] = slotted[:, :, _ICE_COL, :]          # (nprof, nch, nlay) ice
    return k


def merge_solar_observable(bt, refl, channels, solar_channels):
    """Build the per-channel OBSERVABLE (Phase 7): BT for thermal channels, REFL
    (solar reflectance/BRF) for the solar channels.

    RTTOV's single K run (adk_bt + adk_refl) is already per-channel-type -- the K row
    is d(BT)/d(profile) for a thermal channel and d(REFL)/d(profile) for a solar one
    (VERIFIED by FD). So the obs operator stays observable-AGNOSTIC: it contracts that
    same K against the cotangent of THIS merged observable, and each channel's row
    matches its observable. ``channels`` = the run's 1-based channel ids
    (rttov_input.config.channels); ``solar_channels`` = the subset whose observable is
    reflectance. Returns ``bt`` unchanged when ``solar_channels`` is empty (IR-only).

    reject-don't-drop: a solar channel requested but no REFL produced (solar not
    enabled in the run) is rejected, not silently left as BT=0 (a dead solar observable
    whose REFL-K would still be live -> wrong gradient with a zero forward)."""
    if not solar_channels:
        return bt
    import numpy as np
    chan_ids = [int(c) for c in channels]
    solar = {int(c) for c in solar_channels}
    # Reject an unknown/mismatched solar id (mirror ir_channel_gate's reject-don't-drop):
    # a partial typo (e.g. solar=(1..5,16) where 16 is a thermal channel in range) would
    # otherwise write REFL into a BT-K column -> a REFL observable paired with a BT-K row.
    unknown = solar - set(chan_ids)
    if unknown:
        raise ValueError(
            f"solar_channels {sorted(unknown)} are not in the run's channels {chan_ids} "
            "-- every solar id must map to a REFL column (the K row for that channel is "
            "reflectance-K only if it is actually a solar channel).")
    cols = [i for i, c in enumerate(chan_ids) if c in solar]
    if refl is None:
        raise ValueError(
            f"solar_channels {sorted(solar)} requested but the run produced no REFL "
            "(opts%rt_all%solar must be .TRUE. / a solar-capable fixture) -- refusing "
            "to return a zero solar observable while the K carries live REFL sensitivity.")
    obs = np.asarray(bt, dtype=float).copy()
    obs[:, cols] = np.asarray(refl, dtype=float)[:, cols]
    return obs


def make_live_run_k(out_case_dir, *, fixture_case_dir=None, solar_channels=(), timeout=None):
    """Build the live ``run_k(RttovInput) -> (observable, K, rad_quality)`` for RttovObsOp.

    Each call: write_rttov_case (overlay T/Q + cloud onto the fixture) -> out-of-process
    run_rttov_k (single runK: BT + REFL + K) -> cloud-K slot adapter -> merge the
    per-channel observable (BT for thermal, REFL for ``solar_channels``; Phase 7).
    ``out_case_dir`` is rewritten each call (overwrite=True). ``solar_channels`` (1-based
    ids) empty -> pure BT (IR-only / clear-sky, unchanged).

    NOT concurrency-safe: ``out_case_dir`` is a single shared, rewritten directory,
    so two overlapping calls on the SAME closure would clobber each other's case
    mid-run (-> wrong BT/K -> wrong gradient). Sequential use (one DA-window backward
    at a time) is fine; for concurrent callers give each its own ``out_case_dir``, or
    use ``rttov_obs_operator.default_run_k`` which allocates a unique per-call dir.
    """
    def _run_k(rttov_input):
        case_out = write_rttov_case(rttov_input, out_case_dir,
                                    fixture_case_dir=fixture_case_dir, overwrite=True,
                                    solar_channels=solar_channels)
        out = run_rttov_k(case_out, nchannels=len(rttov_input.config.channels),
                          expected_nprofiles=rttov_input.nprofiles, timeout=timeout)
        # Cloud K adapter: RTTOV emits the cloud K as flat PROFILES_K HYDRO/HYDRO_DEFF
        # blocks ([nprof][nch][ntype*nlay]); RttovObsOp.backward wants per-slot
        # HYDRO6/7 + HYDRO_DEFF6/7 ([nprof][nch][nlay]). No-op for clear-sky (no HYDRO).
        nlay = len(out.k["T"][0][0])                    # authoritative layer count from T-K
        add_cloud_k_slots(out.k, nlay=nlay)
        # Per-channel observable: BT (thermal) / REFL (solar). The K is already
        # per-channel-type, so the obs operator contracts it against this observable's
        # cotangent unchanged. RttovKOutput field order is (bt, rad_quality, k, ...) ->
        # reorder to the run_k contract (observable, K, rad_quality); never `tuple(out)`.
        observable = merge_solar_observable(out.bt, out.refl,
                                            rttov_input.config.channels, solar_channels)
        return observable, out.k, out.rad_quality

    # Tag the closure with its solar set so a consumer (obs_adjoint_callback) can verify
    # it matches ObsOperatorConfig.solar_channels -- a mismatch (e.g. cfg says solar but
    # this run_k merges pure BT) would be a silent config-mismatch wrong gradient.
    _run_k.solar_channels = tuple(int(c) for c in solar_channels)
    return _run_k
