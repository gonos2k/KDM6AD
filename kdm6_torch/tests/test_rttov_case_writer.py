"""P4-live -- write_rttov_case + make_live_run_k (rttov_case_writer).

Two tiers:
  * overlay-correctness (needs only the AD-RTTOV fixture case on disk, no RTTOV
    run): copytree + overlay atm/t.txt/q.txt round-trips, nprofiles trim, length
    + exists guards.
  * LIVE (needs the RTTOV exe too): make_live_run_k runs RTTOV out-of-process and
    the obs operator autograd closes through the REAL K-matrix. Strongest signal:
    overlay the fixture's OWN T/Q back -> the run reproduces the fixture's
    known-good BT (within limits), and grads flow th/qv -> real K -> covector.

Both tiers are SKIPPED when the fixture/exe are absent (CI without AD-RTTOV), but
RUN here (AD_RTTOV_HOME present).
"""
import re
import shutil

import numpy as np
import pytest
import torch

from kdm6.state import Forcing, State
from kdm6.obs.model_profile_builder import (
    RttovProfileConfig, model_to_rttov_tensors, qv_to_q_ppmv_moist)
from kdm6.obs.obs_loss import compute_obs_loss
from kdm6.obs.rttov_case_writer import (
    cloud_fixture_case_dir, default_fixture_case_dir, make_live_run_k, write_rttov_case)
from kdm6.obs.rttov_input_builder import (
    RttovInputConfig, RttovInput, pack_rttov_input)
from kdm6.obs.rttov_obs_operator import RttovObsOp, _build_mask
from kdm6.obs.rttov_runner import parse_rttov_radiance

_FIX = default_fixture_case_dir()
_HAVE_FIXTURE = _FIX.is_dir() and (_FIX / "out" / "run.sh").is_file()


def _have_exe() -> bool:
    """The fixture run.sh names the RTTOV exe by absolute path -- check it exists."""
    if not _HAVE_FIXTURE:
        return False
    txt = (_FIX / "out" / "run.sh").read_text()
    m = re.search(r"(\S+\.exe)", txt)
    if not m:
        return False
    from pathlib import Path
    return Path(m.group(1)).is_file()


_HAVE_EXE = _have_exe()
needs_fixture = pytest.mark.skipif(not _HAVE_FIXTURE, reason="AD-RTTOV ami/501 fixture absent")
needs_live = pytest.mark.skipif(not _HAVE_EXE, reason="RTTOV exe absent (live run)")

# All-sky cloud fixture (ami/cloud: f_hydrotable + hydro/hydro_frac/deff_param inputs).
_CFIX = cloud_fixture_case_dir()
_HAVE_CLOUD_FIXTURE = _CFIX.is_dir() and (_CFIX / "out" / "run.sh").is_file()


def _have_cloud_exe() -> bool:
    if not _HAVE_CLOUD_FIXTURE:
        return False
    m = re.search(r"(\S+\.exe)", (_CFIX / "out" / "run.sh").read_text())
    from pathlib import Path
    return bool(m) and Path(m.group(1)).is_file()


_HAVE_CLOUD_EXE = _have_cloud_exe()
needs_cloud_fixture = pytest.mark.skipif(
    not _HAVE_CLOUD_FIXTURE, reason="AD-RTTOV ami/cloud fixture absent")
needs_cloud_live = pytest.mark.skipif(
    not _HAVE_CLOUD_EXE, reason="RTTOV cloud exe absent (live cloud run)")

_CHANNELS = tuple(range(1, 17))   # ami/501: 16 AMI channels


def _fixture_nlayers() -> int:
    return len(np.loadtxt(_FIX / "in" / "profiles" / "001" / "atm" / "t.txt"))


def _fixture_tq(profile="001"):
    """Read the fixture profile's T (K) and Q (ppmv moist) vectors."""
    atm = _FIX / "in" / "profiles" / profile / "atm"
    return np.loadtxt(atm / "t.txt"), np.loadtxt(atm / "q.txt")


def _fixture_p_half(profile="001"):
    """The fixture profile's p_half grid (the grid the run uses; model T/Q ride it)."""
    return np.loadtxt(_FIX / "in" / "profiles" / profile / "atm" / "p_half.txt")


def _namelist_counts(case_root):
    """Read patched (nprofiles, nchannels) from out/rttov_test.txt."""
    txt = (case_root / "out" / "rttov_test.txt").read_text()
    npro = int(re.search(r"defn%nprofiles\s*=\s*(\d+)", txt).group(1))
    nch = int(re.search(r"defn%nchannels\s*=\s*(\d+)", txt).group(1))
    return npro, nch


def _rttov_input_from_arrays(t_vec, q_vec, channels=_CHANNELS, p_half=None,
                             p_lay=None, surface=None, geometry=None) -> RttovInput:
    """Pack a single-profile RttovInput on the given layer vectors (T[K], Q[ppmv]).

    p_half defaults to the FIXTURE grid (the run keeps it; a mismatched p_half is
    rejected by write_rttov_case). Pass an explicit p_half / p_lay / surface /
    geometry to exercise the writer's reject-don't-drop guards.
    """
    if p_half is None:
        p_half = _fixture_p_half()
    prof = type("P", (), {})()
    prof.t_lay = torch.as_tensor(t_vec, dtype=torch.float64)
    prof.q_lay = torch.as_tensor(q_vec, dtype=torch.float64)
    prof.p_lay = None if p_lay is None else torch.as_tensor(p_lay, dtype=torch.float64)
    prof.p_half = torch.as_tensor(p_half, dtype=torch.float64)
    cfg = RttovInputConfig(coef_id="ami_501_test", channels=channels,
                           surface=surface, geometry=geometry)
    return pack_rttov_input(prof, cfg)


def _cloud_fixture_tq(profile="001"):
    """The CLOUD fixture profile's T (K), Q (ppmv), p_half grid."""
    atm = _CFIX / "in" / "profiles" / profile / "atm"
    return (np.loadtxt(atm / "t.txt"), np.loadtxt(atm / "q.txt"),
            np.loadtxt(atm / "p_half.txt"))


def _cloud_rttov_input(channels=_CHANNELS, deff_liq=20.0, deff_ice=45.0, drop=None):
    """Pack a single-profile all-sky cloud RttovInput on the cloud-fixture grid.

    Deterministic synthetic cloud: ice aloft (layers 15-25), liquid lower (40-50),
    g/m^3 content + micron Deff + binary cloud fraction. Returns (RttovInput, ref)
    where ref holds the expected per-layer arrays for overlay round-trip checks.
    ``drop`` removes one cloud key after packing (to exercise the partial-set guard).
    """
    from kdm6.obs.model_profile_builder import RttovProfileTensors
    t_vec, q_vec, ph = _cloud_fixture_tq()
    nlay = len(t_vec)
    clw = np.zeros(nlay); clw[40:50] = 0.10
    ciw = np.zeros(nlay); ciw[15:25] = 0.03
    dl = np.full(nlay, float(deff_liq))
    di = np.full(nlay, float(deff_ice))
    cfrac = np.zeros(nlay); cfrac[15:50] = 1.0
    f64 = torch.float64
    prof = RttovProfileTensors(
        t_lay=torch.as_tensor(t_vec, dtype=f64), q_lay=torch.as_tensor(q_vec, dtype=f64),
        p_lay=None, p_half=torch.as_tensor(ph, dtype=f64),
        clw=torch.as_tensor(clw, dtype=f64), ciw=torch.as_tensor(ciw, dtype=f64),
        deff_liq=torch.as_tensor(dl, dtype=f64), deff_ice=torch.as_tensor(di, dtype=f64),
        cfrac=torch.as_tensor(cfrac, dtype=f64))
    rin = pack_rttov_input(prof, RttovInputConfig(coef_id="ami_cloud", channels=channels))
    if drop is not None:
        rin.profile.pop(drop)
    return rin, dict(clw=clw, ciw=ciw, deff_liq=dl, deff_ice=di, cfrac=cfrac)


# ---------------------------------------------------------------- overlay (no run)
@needs_fixture
def test_overlay_roundtrips_fixture_tq(tmp_path):
    """write_rttov_case overlays atm/t.txt + q.txt with the RttovInput values
    (%.6E), and trims the case to nprofiles=1 (channels/lprofiles + profile dirs)."""
    t_vec, q_vec = _fixture_tq()
    rin = _rttov_input_from_arrays(t_vec, q_vec)
    case_out = write_rttov_case(rin, tmp_path / "case")
    assert case_out == tmp_path / "case" / "out"

    prof_root = tmp_path / "case" / "in" / "profiles"
    assert sorted(d.name for d in prof_root.iterdir() if d.is_dir()) == ["001"]  # trimmed 6 -> 1
    back_t = np.loadtxt(prof_root / "001" / "atm" / "t.txt")
    back_q = np.loadtxt(prof_root / "001" / "atm" / "q.txt")
    # %.6E round-trip: ~6 sig digits.
    assert np.allclose(back_t, t_vec, rtol=1e-6, atol=0)
    assert np.allclose(back_q, q_vec, rtol=1e-6, atol=0)
    # channels.txt / lprofiles.txt authored from config (1 profile, 16 channels).
    chan = [ln for ln in (tmp_path / "case" / "in" / "channels.txt").read_text().splitlines() if ln.strip()]
    lpro = [ln for ln in (tmp_path / "case" / "in" / "lprofiles.txt").read_text().splitlines() if ln.strip()]
    assert chan == ["1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16"]
    assert lpro == ["1 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1"]
    # authoritative namelist counts patched to (nprofiles=1, nchannels=1*16).
    assert _namelist_counts(tmp_path / "case") == (1, 16)


@needs_fixture
def test_overlay_channels_authored_from_config_not_fixture(tmp_path):
    """channels.txt/lprofiles.txt + namelist counts come from config.channels, NOT
    the fixture's 1..16 -- else a different requested band would silently run the
    fixture's channels (Codex A2). Subset (7,8,9,10) -> 4 channels per profile."""
    t_vec, q_vec = _fixture_tq()
    rin = _rttov_input_from_arrays(t_vec, q_vec, channels=(7, 8, 9, 10))
    write_rttov_case(rin, tmp_path / "case")
    chan = [ln for ln in (tmp_path / "case" / "in" / "channels.txt").read_text().splitlines() if ln.strip()]
    lpro = [ln for ln in (tmp_path / "case" / "in" / "lprofiles.txt").read_text().splitlines() if ln.strip()]
    assert chan == ["7 8 9 10"]
    assert lpro == ["1 1 1 1"]
    assert _namelist_counts(tmp_path / "case") == (1, 4)   # total chanprof = 1*4


@needs_fixture
def test_overlay_does_not_mutate_fixture(tmp_path):
    before = (_FIX / "in" / "profiles" / "001" / "atm" / "t.txt").read_text()
    t_vec, q_vec = _fixture_tq()
    write_rttov_case(_rttov_input_from_arrays(t_vec + 5.0, q_vec), tmp_path / "case")
    after = (_FIX / "in" / "profiles" / "001" / "atm" / "t.txt").read_text()
    assert before == after  # never touches the source


@needs_fixture
def test_overlay_length_mismatch_raises(tmp_path):
    nlay = _fixture_nlayers()
    short = nlay - 1                    # one layer short of the fixture grid
    t_vec = np.full(short, 250.0)
    q_vec = np.full(short, 1000.0)
    # self-consistent p_half (short+1) so pack passes; the OVERLAY length guard
    # (short != fixture nlay) is what must fire.
    rin = _rttov_input_from_arrays(t_vec, q_vec, p_half=np.linspace(0.0, 950.0, short + 1))
    with pytest.raises(ValueError, match="fixture layer count"):
        write_rttov_case(rin, tmp_path / "case")


@needs_fixture
def test_overlay_exists_without_overwrite_raises(tmp_path):
    t_vec, q_vec = _fixture_tq()
    rin = _rttov_input_from_arrays(t_vec, q_vec)
    (tmp_path / "case").mkdir()
    with pytest.raises(FileExistsError):
        write_rttov_case(rin, tmp_path / "case")
    # overwrite=True succeeds.
    write_rttov_case(rin, tmp_path / "case", overwrite=True)


@needs_fixture
def test_overlay_refuses_more_profiles_than_fixture(tmp_path):
    t_vec, q_vec = _fixture_tq()
    nlay = len(t_vec)
    # 7-profile input vs 6-profile fixture.
    prof = type("P", (), {})()
    prof.t_lay = torch.as_tensor(np.tile(t_vec, (7, 1)), dtype=torch.float64)
    prof.q_lay = torch.as_tensor(np.tile(q_vec, (7, 1)), dtype=torch.float64)
    prof.p_lay = None
    prof.p_half = torch.linspace(5.0, 1010.0, nlay + 1, dtype=torch.float64)
    rin = pack_rttov_input(prof, RttovInputConfig(coef_id="x", channels=_CHANNELS))
    with pytest.raises(ValueError, match="only"):
        write_rttov_case(rin, tmp_path / "case")


@needs_fixture
def test_overlay_rejects_mismatched_p_half(tmp_path):
    """A P_HALF that differs from the fixture grid is rejected (model T/Q would be
    mis-gridded since the run keeps the fixture p_half) -- reject-don't-drop."""
    t_vec, q_vec = _fixture_tq()
    bad_ph = np.linspace(5.0, 1010.0, len(t_vec) + 1)   # not the fixture grid
    rin = _rttov_input_from_arrays(t_vec, q_vec, p_half=bad_ph)
    with pytest.raises(ValueError, match="fixture grid"):
        write_rttov_case(rin, tmp_path / "case")


@needs_fixture
def test_overlay_requires_p_half(tmp_path):
    """P_HALF is the grid witness -- absent it, the writer cannot verify the model
    T/Q are on the fixture grid, so it must reject rather than blindly trust."""
    t_vec, q_vec = _fixture_tq()
    prof = type("P", (), {})()
    prof.t_lay = torch.as_tensor(t_vec, dtype=torch.float64)
    prof.q_lay = torch.as_tensor(q_vec, dtype=torch.float64)
    prof.p_lay = None
    prof.p_half = None                                   # no grid witness
    rin = pack_rttov_input(prof, RttovInputConfig(coef_id="x", channels=_CHANNELS))
    assert "P_HALF" not in rin.profile
    with pytest.raises(ValueError, match="P_HALF"):
        write_rttov_case(rin, tmp_path / "case")


@needs_fixture
def test_overlay_accepts_canonical_layer_pressure(tmp_path):
    """The interp path is honored: profile['P'] == fixture_layer_pressure() (the
    canonical layer grid the caller interpolates onto) is accepted."""
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure
    t_vec, q_vec = _fixture_tq()
    rin = _rttov_input_from_arrays(t_vec, q_vec, p_lay=fixture_layer_pressure())
    assert "P" in rin.profile
    write_rttov_case(rin, tmp_path / "case")            # no raise


@needs_fixture
def test_overlay_rejects_noncanonical_layer_pressure(tmp_path):
    """profile['P'] off the canonical fixture layer grid is rejected even when P_HALF
    matches (T/Q interpolated onto the wrong layers) -- reject-don't-drop."""
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure
    t_vec, q_vec = _fixture_tq()
    p_lay = fixture_layer_pressure().copy()
    p_lay[10] *= 1.05                                   # nudge one layer off the canonical grid
    rin = _rttov_input_from_arrays(t_vec, q_vec, p_lay=p_lay)
    with pytest.raises(ValueError, match="canonical layer"):
        write_rttov_case(rin, tmp_path / "case")


@needs_fixture
def test_fixture_layer_pressure_reference_grid(tmp_path):
    """fixture_layer_pressure() gives a usable interpolation target: right length
    (nlayers) and strictly inside the fixture half-levels (incl. the TOA p_half=0)."""
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure
    ph = _fixture_p_half()
    lay = fixture_layer_pressure()
    assert lay.shape == (len(ph) - 1,)
    assert np.all((lay > ph[:-1]) & (lay < ph[1:]))   # bracketed, TOA layer (0, ph[1]) included


@needs_fixture
def test_overlay_rejects_noninteger_channels(tmp_path):
    """Channel ids are coerced strictly: a fractional id (7.9) would silently
    truncate to a different band (7) -- reject instead. Integral float (7.0) ok."""
    t_vec, q_vec = _fixture_tq()
    for bad in [(7.9,), (0,), (-3,), (True,)]:
        rin = _rttov_input_from_arrays(t_vec, q_vec, channels=bad)
        with pytest.raises(ValueError, match="channel"):
            write_rttov_case(rin, tmp_path / "case", overwrite=True)
    # integral float is accepted and written as the integer id.
    rin = _rttov_input_from_arrays(t_vec, q_vec, channels=(7.0, 8.0))
    write_rttov_case(rin, tmp_path / "case", overwrite=True)
    chan = [ln for ln in (tmp_path / "case" / "in" / "channels.txt").read_text().splitlines() if ln.strip()]
    assert chan == ["7 8"]


@needs_fixture
def test_overlay_rejects_surface_or_geometry(tmp_path):
    """Non-None surface/geometry are not yet written into the case -> raise rather
    than silently using the fixture's (reject-don't-drop)."""
    t_vec, q_vec = _fixture_tq()
    rin = _rttov_input_from_arrays(t_vec, q_vec, surface={"skin_t": 290.0})
    with pytest.raises(NotImplementedError, match="surface/geometry"):
        write_rttov_case(rin, tmp_path / "case")


@needs_fixture
def test_overlay_rejects_bad_fixture_contract(tmp_path):
    """A fixture whose namelist computes radiance-K (adk_bt=.FALSE.) is rejected --
    the run would silently produce K that is not BT-K (defends a wrong fixture)."""
    badfix = tmp_path / "badfix"
    shutil.copytree(_FIX, badfix)
    cfg = badfix / "out" / "rttov_test.txt"
    cfg.write_text(re.sub(r"(defn%opts%config%adk_bt\s*=\s*)\.TRUE\.",
                          r"\g<1>.FALSE.", cfg.read_text()))
    t_vec, q_vec = _fixture_tq()
    rin = _rttov_input_from_arrays(t_vec, q_vec)
    with pytest.raises(ValueError, match="adk_bt"):
        write_rttov_case(rin, tmp_path / "case", fixture_case_dir=badfix)


# ---------------------------------------------------------- all-sky cloud overlay
@needs_cloud_fixture
def test_cloud_overlay_writes_hydro_files(tmp_path):
    """A full cloud RttovInput defaults to the AMI cloud fixture and overlays the
    three cloud input files: hydro.txt [nlay x 8] (liquid HYDRO6 -> col idx5, ice
    HYDRO7 -> col idx6, all other slots 0), hydro_deff.txt [nlay x 7] (model Deff in
    the same liquid/ice cols), hydro_frac.txt (a hydro_frac_eff line + per-layer
    CFRAC). The parametrized-Deff fallback (deff_param.txt) is preserved (the driver
    reads it unconditionally; the positive-Deff gate prefers the model's explicit Deff)."""
    rin, ref = _cloud_rttov_input()                         # no fixture_case_dir -> cloud fixture
    write_rttov_case(rin, tmp_path / "case")
    atm = tmp_path / "case" / "in" / "profiles" / "001" / "atm"
    nlay = len(ref["clw"])

    H = np.loadtxt(atm / "hydro.txt")
    assert H.shape == (nlay, 8)
    assert np.allclose(H[:, 5], ref["clw"], rtol=1e-6, atol=0)     # liquid content (slot 6)
    assert np.allclose(H[:, 6], ref["ciw"], rtol=1e-6, atol=0)     # ice content (slot 7)
    assert np.all(H[:, [0, 1, 2, 3, 4, 7]] == 0.0)                 # OPAC 1-5 + Baran: zero

    D = np.loadtxt(atm / "hydro_deff.txt")
    assert D.shape == (nlay, 7)                                    # nhydro - 1 (Baran has no Deff)
    assert np.allclose(D[:, 5], ref["deff_liq"], rtol=1e-6, atol=0)
    assert np.allclose(D[:, 6], ref["deff_ice"], rtol=1e-6, atol=0)
    assert np.all(D[:, [0, 1, 2, 3, 4]] == 0.0)

    frac = [ln for ln in (atm / "hydro_frac.txt").read_text().splitlines() if ln.strip()]
    assert len(frac) == 1 + nlay                                   # eff line + per-layer CFRAC
    assert np.allclose([float(x) for x in frac[1:]], ref["cfrac"], rtol=1e-6, atol=0)

    assert (atm / "deff_param.txt").is_file()                      # param fallback preserved


@needs_cloud_fixture
def test_cloud_overlay_does_not_mutate_fixture(tmp_path):
    before = (_CFIX / "in" / "profiles" / "001" / "atm" / "hydro.txt").read_text()
    rin, _ = _cloud_rttov_input()
    write_rttov_case(rin, tmp_path / "case")
    after = (_CFIX / "in" / "profiles" / "001" / "atm" / "hydro.txt").read_text()
    assert before == after


@needs_cloud_fixture
def test_cloud_overlay_partial_set_rejected(tmp_path):
    """A partial cloud set (missing CFRAC) is rejected before any FS mutation -- the
    missing field would inherit the fixture's stale value (silently wrong cloud)."""
    rin, _ = _cloud_rttov_input(drop="CFRAC")
    assert "HYDRO6" in rin.profile and "CFRAC" not in rin.profile
    with pytest.raises(ValueError, match="partial cloud"):
        write_rttov_case(rin, tmp_path / "case")
    assert not (tmp_path / "case").exists()                        # rejected before copytree


@needs_fixture
@needs_cloud_fixture
def test_cloud_input_on_clearsky_fixture_rejected(tmp_path):
    """A cloud RttovInput forced onto the clear-sky ami/501 fixture (no f_hydro in the
    namelist) is rejected -- the overlaid cloud would run clear-sky (reject-don't-drop)."""
    rin, _ = _cloud_rttov_input()
    with pytest.raises(ValueError, match="clear-sky"):
        write_rttov_case(rin, tmp_path / "case", fixture_case_dir=_FIX)


@needs_cloud_fixture
def test_cloud_overlay_rejects_nonpositive_deff_in_cloudy_layer(tmp_path):
    """A non-positive Deff where content > 0 is rejected (before any FS mutation):
    RTTOV's positive-Deff gate would SILENTLY fall back to deff_param, dropping the
    model's explicit diameter -- the exact silent-drop the Deff adjoint can't survive."""
    rin, _ = _cloud_rttov_input()                           # ciw[20]=0.03 (>0)
    rin.profile["HYDRO_DEFF7"][0][20] = 0.0                 # ice Deff 0 in a cloudy layer
    with pytest.raises(ValueError, match="must be > 0 wherever HYDRO7"):
        write_rttov_case(rin, tmp_path / "case")
    assert not (tmp_path / "case").exists()                 # rejected before copytree


@needs_cloud_fixture
def test_cloud_overlay_allows_nonpositive_deff_in_clear_layer(tmp_path):
    """Deff <= 0 in a CLEAR layer (content 0 there) is fine -- the guard is
    content-coupled, not blanket-positive (RTTOV ignores Deff where content==0)."""
    rin, _ = _cloud_rttov_input()                           # ciw[0]=0
    rin.profile["HYDRO_DEFF7"][0][0] = 0.0
    write_rttov_case(rin, tmp_path / "case")                # no raise


@needs_cloud_fixture
def test_cloud_overlay_rejects_negative_content_and_bad_cfrac(tmp_path):
    rin, _ = _cloud_rttov_input()
    rin.profile["HYDRO6"][0][45] = -0.1                     # negative liquid mass
    with pytest.raises(ValueError, match="HYDRO6 must be finite and >= 0"):
        write_rttov_case(rin, tmp_path / "case")
    rin2, _ = _cloud_rttov_input()
    rin2.profile["CFRAC"][0][20] = 1.5                      # fraction > 1
    with pytest.raises(ValueError, match=r"CFRAC must be finite and in \[0, 1\]"):
        write_rttov_case(rin2, tmp_path / "case")


@needs_cloud_fixture
def test_cloud_overlay_rejects_unrecognized_hydro_key(tmp_path):
    """A forbidden MW RTTOV-SCATT slot (HYDRO1) alongside the AMI cloud set is
    rejected, not silently dropped (reject-don't-drop)."""
    rin, _ = _cloud_rttov_input()
    rin.profile["HYDRO1"] = rin.profile["HYDRO6"].copy()
    with pytest.raises(ValueError, match="unrecognized cloud-family"):
        write_rttov_case(rin, tmp_path / "case")


@needs_fixture
def test_unrecognized_hydro_key_on_clearsky_rejected(tmp_path):
    """Even with NO recognized cloud key, a stray HYDRO* key is rejected -- otherwise
    a misspelled HYDRO6 would silently run clear-sky."""
    t_vec, q_vec = _fixture_tq()
    rin = _rttov_input_from_arrays(t_vec, q_vec)
    rin.profile["HYDRO1"] = np.zeros(len(t_vec))
    with pytest.raises(ValueError, match="unrecognized cloud-family"):
        write_rttov_case(rin, tmp_path / "case")


@needs_cloud_fixture
def test_cloud_post_copy_failure_leaves_no_partial_case(tmp_path):
    """A failure AFTER copytree (off-grid P_HALF caught inside _populate_case) must
    remove the partial case, so a retry to the SAME dir doesn't hit FileExistsError."""
    rin, _ = _cloud_rttov_input()
    rin.profile["P_HALF"][0][:] = rin.profile["P_HALF"][0] + 1.0   # off the fixture grid
    with pytest.raises(ValueError, match="fixture grid"):
        write_rttov_case(rin, tmp_path / "case")
    assert not (tmp_path / "case").exists()                        # cleaned up (no partial)
    rin2, _ = _cloud_rttov_input()
    write_rttov_case(rin2, tmp_path / "case")                      # retry, no overwrite=True


@needs_cloud_fixture
def test_cloud_overlay_rejects_mmr_hydro_true(tmp_path):
    """The model emits g/m^3 content -> a fixture with mmr_hydro=T (kg/kg) would
    silently mis-scale it by orders of magnitude. Reject (unit contract)."""
    badfix = tmp_path / "badfix"
    shutil.copytree(_CFIX, badfix)
    mmr = badfix / "in" / "profiles" / "001" / "atm" / "mmr_hydro_aer.txt"
    mmr.write_text(re.sub(r"(?im)(mmr_hydro\s*=\s*)F", r"\g<1>T", mmr.read_text()))
    rin, _ = _cloud_rttov_input()
    with pytest.raises(ValueError, match="mmr_hydro = F"):
        write_rttov_case(rin, tmp_path / "case", fixture_case_dir=badfix)


@needs_cloud_fixture
def test_cloud_overlay_rejects_missing_mmr_file(tmp_path):
    """mmr_hydro has NO default when the unit file is absent (driver reads it only on
    INQUIRE) -> an absent file leaves the unit undefined. Reject."""
    badfix = tmp_path / "badfix"
    shutil.copytree(_CFIX, badfix)
    (badfix / "in" / "profiles" / "001" / "atm" / "mmr_hydro_aer.txt").unlink()
    rin, _ = _cloud_rttov_input()
    with pytest.raises(FileNotFoundError, match="mmr_hydro_aer.txt"):
        write_rttov_case(rin, tmp_path / "case", fixture_case_dir=badfix)


@needs_cloud_fixture
def test_cloud_overlay_rejects_wrong_hydro_columns(tmp_path):
    """The writer's liquid=col6/ice=col7/nhydro=8 layout is hydrotable-specific. A
    fixture hydro.txt with a different column count (different ntypes hydrotable) would
    silently mis-slot liquid/ice -> reject before overwriting."""
    badfix = tmp_path / "badfix"
    shutil.copytree(_CFIX, badfix)
    h = badfix / "in" / "profiles" / "001" / "atm" / "hydro.txt"
    nlay = len(_cloud_fixture_tq()[0])
    h.write_text("".join(" ".join(["0.000000E+00"] * 6) + "\n" for _ in range(nlay)))  # 6 cols
    rin, _ = _cloud_rttov_input()
    with pytest.raises(ValueError, match="columns but the AMI all-sky writer assumes"):
        write_rttov_case(rin, tmp_path / "case", fixture_case_dir=badfix)


@needs_cloud_fixture
def test_cloud_overlay_rejects_missing_hydrotable_entry(tmp_path):
    """A cloud fixture whose in/coef.txt has no f_hydrotable would have no VIS/IR
    scattering optical properties (and an undefined slot<->type map). Reject."""
    badfix = tmp_path / "badfix"
    shutil.copytree(_CFIX, badfix)
    coef = badfix / "in" / "coef.txt"
    coef.write_text(re.sub(r"(?im)^(\s*defn%f_hydrotable\s*=\s*).*$", r"\g<1>''", coef.read_text()))
    rin, _ = _cloud_rttov_input()
    with pytest.raises(ValueError, match="f_hydrotable"):
        write_rttov_case(rin, tmp_path / "case", fixture_case_dir=badfix)


@needs_cloud_fixture
def test_solar_observable_rejects_no_adk_refl_fixture(tmp_path):
    """A solar channel requested but the fixture has adk_refl=.FALSE. -> the solar K rows
    are BT-K, not d(REFL); merging a REFL observable onto BT-K rows is a silent wrong
    gradient. write_rttov_case(solar_channels=...) must reject (mirrors the adk_bt check)."""
    badfix = tmp_path / "badfix"
    shutil.copytree(_CFIX, badfix)
    nl = badfix / "out" / "rttov_test.txt"
    nl.write_text(re.sub(r"(defn%opts%config%adk_refl\s*=\s*)\.TRUE\.", r"\g<1>.FALSE.",
                         nl.read_text()))
    rin, _ = _cloud_rttov_input()
    with pytest.raises(ValueError, match="adk_refl"):
        write_rttov_case(rin, tmp_path / "case", fixture_case_dir=badfix, solar_channels=(1,))
    # without solar_channels the SAME fixture is fine (IR-only: no solar contract).
    write_rttov_case(rin, tmp_path / "case", fixture_case_dir=badfix, overwrite=True)


# ------------------------------------------------- cloud K adapter (Phase 6, no run)
def _flat_typemajor(nprof, nch, ntype, nlay):
    """Synthetic flat K block, type-major: value[type,layer] = type*100 + layer."""
    v = np.array([t * 100 + l for t in range(ntype) for l in range(nlay)], dtype=float)
    return np.broadcast_to(v, (nprof, nch, ntype * nlay)).copy()


def test_add_cloud_k_slots_reshape_and_slots():
    """add_cloud_k_slots reshapes the flat type-major HYDRO/HYDRO_DEFF blocks and
    extracts liquid (col 5) / ice (col 6) -> per-slot keys (nprof, nch, nlay)."""
    from kdm6.obs.rttov_case_writer import add_cloud_k_slots
    nprof, nch, nlay = 2, 3, 4
    k = {"T": np.zeros((nprof, nch, nlay)).tolist(),
         "HYDRO": _flat_typemajor(nprof, nch, 8, nlay).tolist(),
         "HYDRO_DEFF": _flat_typemajor(nprof, nch, 7, nlay).tolist()}
    add_cloud_k_slots(k, nlay=nlay)
    lay = np.arange(nlay, dtype=float)
    for key, typ in (("HYDRO6", 5), ("HYDRO7", 6), ("HYDRO_DEFF6", 5), ("HYDRO_DEFF7", 6)):
        got = np.asarray(k[key])
        assert got.shape == (nprof, nch, nlay), key
        assert np.allclose(got, typ * 100 + lay), key   # exact slot + layer order


def test_add_cloud_k_slots_rejects_bad_flat_length():
    """A flat length != ntype*nlay (wrong hydrotable / layer count) is rejected, not
    silently mis-slotted into a wrong-but-finite gradient."""
    from kdm6.obs.rttov_case_writer import add_cloud_k_slots
    k = {"HYDRO": np.zeros((1, 1, 8 * 4 + 1)).tolist()}   # 33 != 8*4
    with pytest.raises(ValueError, match="slot layout does not hold"):
        add_cloud_k_slots(k, nlay=4)


def test_add_cloud_k_slots_noop_clearsky():
    """No HYDRO blocks (clear-sky K) -> no-op (no per-slot keys added)."""
    from kdm6.obs.rttov_case_writer import add_cloud_k_slots
    k = {"T": [[[0.0, 0.0]]], "Q": [[[0.0, 0.0]]]}
    add_cloud_k_slots(k, nlay=2)
    assert "HYDRO6" not in k and "HYDRO_DEFF6" not in k


# ----------------------------------------- solar observable merge (Phase 7, no run)
def test_merge_solar_observable_picks_refl_for_solar():
    """The per-channel observable = REFL for solar channels, BT for thermal."""
    from kdm6.obs.rttov_case_writer import merge_solar_observable
    bt = np.array([[270.0, 280.0, 290.0, 300.0]])
    refl = np.array([[0.9, 0.8, 0.0, 0.0]])
    channels = (1, 2, 7, 8)
    out = merge_solar_observable(bt, refl, channels, solar_channels=(1, 2))
    assert np.allclose(out, [[0.9, 0.8, 290.0, 300.0]])      # ch1/2 -> refl; ch7/8 -> bt


def test_merge_solar_observable_empty_noop_and_unknown_id_rejected():
    from kdm6.obs.rttov_case_writer import merge_solar_observable
    bt = np.array([[270.0, 280.0]])
    refl = np.array([[0.9, 0.8]])
    assert merge_solar_observable(bt, refl, (7, 8), ()) is bt           # no solar -> unchanged
    # a solar id not in the run's channels is REJECTED (mirrors ir_channel_gate): a
    # partial mis-map would write REFL into a BT-K column -> silent wrong gradient.
    with pytest.raises(ValueError, match="not in the run's channels"):
        merge_solar_observable(bt, refl, (7, 8), (1, 6))


def test_merge_solar_observable_rejects_missing_refl():
    """A solar channel requested but no REFL (solar not enabled) is rejected -- not a
    silent BT=0 solar observable (whose REFL-K would still be live -> wrong gradient)."""
    from kdm6.obs.rttov_case_writer import merge_solar_observable
    bt = np.array([[270.0, 280.0]])
    with pytest.raises(ValueError, match="no REFL"):
        merge_solar_observable(bt, None, (1, 7), solar_channels=(1,))


# ---------------------------------------------------------------- LIVE RTTOV
@needs_live
def test_live_run_k_reproduces_fixture_bt(tmp_path):
    """make_live_run_k overlays the fixture's OWN T/Q back and runs RTTOV; the BT
    must reproduce the fixture's known-good radiance (round-trip), and K['T'],
    K['Q'] come back with [nprof, nch, nlay] shape."""
    t_vec, q_vec = _fixture_tq()
    rin = _rttov_input_from_arrays(t_vec, q_vec)
    run_k = make_live_run_k(tmp_path / "live_case")
    bt, k, rad_quality = run_k(rin)

    bt = np.asarray(bt)
    assert bt.shape == (1, 16)
    # reference: the fixture's stored 6-profile radiance, profile 0.
    ref = parse_rttov_radiance(_FIX / "out" / "k" / "radiance.txt", nchannels=16)
    ref_bt0 = np.asarray(ref["bt"][0])
    assert np.allclose(bt[0], ref_bt0, rtol=1e-4, atol=1e-2), (bt[0], ref_bt0)
    # IR channels (7..16) are physical brightness temperatures; solar (1..6) are 0 in BT.
    assert np.all((bt[0, 6:] > 150.0) & (bt[0, 6:] < 350.0))
    nlay = len(t_vec)
    assert np.asarray(k["T"]).shape == (1, 16, nlay)
    assert np.asarray(k["Q"]).shape == (1, 16, nlay)
    assert np.asarray(rad_quality).shape == (1, 16)


@needs_live
def test_live_run_k_honors_subset_channels(tmp_path):
    """Requesting a SUBSET of channels actually runs THOSE channels: BT for IR
    channels (7,8,9,10) must equal the fixture full-run's channels 7..10 (indices
    6..9), proving channels.txt is authored from config, not the fixture (A2)."""
    t_vec, q_vec = _fixture_tq()
    rin = _rttov_input_from_arrays(t_vec, q_vec, channels=(7, 8, 9, 10))
    bt, k, rad_quality = make_live_run_k(tmp_path / "live_case")(rin)
    bt = np.asarray(bt)
    assert bt.shape == (1, 4)
    ref = parse_rttov_radiance(_FIX / "out" / "k" / "radiance.txt", nchannels=16)
    ref_bt0 = np.asarray(ref["bt"][0])
    assert np.allclose(bt[0], ref_bt0[6:10], rtol=1e-4, atol=1e-2), (bt[0], ref_bt0[6:10])
    assert np.asarray(k["T"]).shape == (1, 4, len(t_vec))


@needs_live
def test_live_obs_operator_autograd_through_real_k(tmp_path):
    """Full closure with REAL RTTOV K: model leaves (th, qv) -> model_to_rttov_tensors
    -> RttovObsOp.apply(live run_k) -> compute_obs_loss -> autograd.grad. The
    fixture's own profile is reproduced via th=T (pii=1) and qv=invert(Q), so the
    run stays within RTTOV limits; grads must be finite and nonzero (real K used)."""
    t_vec, q_vec = _fixture_tq()
    nlay = len(t_vec)

    # invert Q(ppmv moist) -> qv(mixing_ratio_kgkg_dry) so ppmv_moist(qv) == Q:
    #   f = Q/1e6;  w = M_v * f * (1/M_d) / (1 - f)
    M_DRY, M_VAP = 28.9647e-3, 18.01528e-3
    f = q_vec / 1.0e6
    qv_vec = M_VAP * f * (1.0 / M_DRY) / (1.0 - f)

    th = torch.tensor(t_vec, dtype=torch.float64, requires_grad=True)   # pii=1 -> t_lay=T
    qv = torch.tensor(qv_vec, dtype=torch.float64, requires_grad=True)
    zeros = torch.zeros(nlay, dtype=torch.float64)
    leaves = State(th=th, qv=qv, qc=zeros, qr=zeros, qi=zeros, qs=zeros, qg=zeros,
                   nccn=zeros, nc=zeros, ni=zeros, nr=zeros, bg=zeros)
    ones = torch.ones(nlay, dtype=torch.float64)
    p_model = torch.linspace(1.0, 940.0, nlay, dtype=torch.float64)        # ascending; passthrough
    forcing = Forcing(rho=ones, pii=ones, p=p_model, delz=ones)

    profile_cfg = RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry",
        rttov_layer_pressure=None,                                         # passthrough (already 69-layer)
        # the model T/Q ride the FIXTURE grid -> p_half must BE the fixture p_half.
        rttov_level_pressure=torch.as_tensor(_fixture_p_half(), dtype=torch.float64))
    input_cfg = RttovInputConfig(coef_id="ami_501_test", channels=_CHANNELS)
    run_k = make_live_run_k(tmp_path / "live_case")

    prof = model_to_rttov_tensors(leaves, forcing, profile_cfg)
    # q_lay reproduces the fixture Q within fp (inversion round-trip).
    assert torch.allclose(prof.q_lay, torch.as_tensor(q_vec, dtype=torch.float64), rtol=1e-9)
    bt_hat, rad_quality = RttovObsOp.apply(
        run_k, input_cfg, prof.t_lay, prof.q_lay, prof.p_lay, prof.p_half)

    # obs BT = 0 -> IR residual ~250 K -> nonzero loss/gradient on usable channels.
    obs = {"bt": torch.zeros(1, 16, dtype=torch.float64)}
    mask = _build_mask(obs, rad_quality)
    assert float(mask.sum()) > 0.0, "fixture profile should have usable (rad_quality==0) channels"
    j = compute_obs_loss(bt_hat, obs, mask, sigma=1.0)
    g_th, g_qv = torch.autograd.grad(j, [th, qv])

    assert torch.isfinite(g_th).all() and torch.isfinite(g_qv).all()
    # real K -> at least one channel sensitive to T and to Q.
    assert g_th.abs().sum().item() > 0.0
    assert g_qv.abs().sum().item() > 0.0


# ---------------------------------------------------------- LIVE all-sky cloud
@needs_cloud_live
def test_live_cloud_run_k_emits_cloud_bt(tmp_path):
    """make_live_run_k auto-selects the cloud fixture for a cloud RttovInput, writes
    hydro/hydro_deff/hydro_frac, runs RTTOV, and returns physical IR cloud BT + K of
    the right shape -- the explicit hydro_deff.txt does not break the run."""
    rin, _ = _cloud_rttov_input()
    bt, k, rad_quality = make_live_run_k(tmp_path / "cloud_case")(rin)
    bt = np.asarray(bt)
    assert bt.shape == (1, 16)
    assert np.all((bt[0, 6:] > 150.0) & (bt[0, 6:] < 350.0))       # IR channels: physical BT
    nlay = len(_cloud_fixture_tq()[0])
    assert np.asarray(k["T"]).shape == (1, 16, nlay)
    assert np.asarray(rad_quality).shape == (1, 16)


@needs_cloud_live
def test_live_cloud_explicit_deff_is_honored(tmp_path):
    """The model's explicit hydro_deff.txt must CHANGE the BT vs a different ice Deff
    -- proving RTTOV's positive-Deff gate uses the model Deff, not the parametrized
    deff_param.txt fallback (else the model's DSD effective diameter is silently lost,
    and the Deff adjoint would be meaningless). reject-don't-drop, validated live."""
    rin_a, _ = _cloud_rttov_input(deff_ice=30.0)
    rin_b, _ = _cloud_rttov_input(deff_ice=90.0)
    bt_a = np.asarray(make_live_run_k(tmp_path / "a")(rin_a)[0])
    bt_b = np.asarray(make_live_run_k(tmp_path / "b")(rin_b)[0])
    # ice scattering differs with effective diameter -> at least one IR channel moves.
    assert np.max(np.abs(bt_a[0, 6:] - bt_b[0, 6:])) > 0.05, (bt_a[0, 6:], bt_b[0, 6:])


@needs_cloud_live
def test_live_cloud_obs_operator_autograd_through_real_k(tmp_path):
    """Phase 6 milestone: the all-sky autograd loop closes through REAL cloud K.

    cloud tensors (content + effective diameter) -> RttovObsOp.apply(live cloud run_k)
    -> compute_obs_loss -> autograd.grad. The cloud-K adapter must wire HYDRO6/7
    (content) and HYDRO_DEFF6/7 (Deff) from RTTOV's flat PROFILES_K so:
      * content grads (clw, ciw) are finite + nonzero, AND
      * Deff grads (deff_liq, deff_ice) are finite + nonzero -- the Deff adjoint is
        LIVE (the getHydroDeffNK probe: HYDRO_DEFF K reaches the covector, not
        connected-zero), and localizes to the cloudy layers it was fed in."""
    from kdm6.obs.rttov_input_builder import RttovInputConfig
    from kdm6.obs.rttov_obs_operator import RttovObsOp, _build_mask
    from kdm6.obs.obs_loss import compute_obs_loss

    t_vec, q_vec, ph = _cloud_fixture_tq()
    nlay = len(t_vec)
    f64 = torch.float64
    t = torch.tensor(t_vec, dtype=f64)
    q = torch.tensor(q_vec, dtype=f64)
    p_half = torch.tensor(ph, dtype=f64)
    clw_np = np.zeros(nlay); clw_np[40:50] = 0.10          # liquid lower
    ciw_np = np.zeros(nlay); ciw_np[15:25] = 0.03          # ice aloft
    cfrac_np = np.zeros(nlay); cfrac_np[15:50] = 1.0
    clw = torch.tensor(clw_np, dtype=f64, requires_grad=True)
    ciw = torch.tensor(ciw_np, dtype=f64, requires_grad=True)
    deff_liq = torch.full((nlay,), 20.0, dtype=f64, requires_grad=True)
    deff_ice = torch.full((nlay,), 45.0, dtype=f64, requires_grad=True)
    cfrac = torch.tensor(cfrac_np, dtype=f64)              # cfrac detached (non-diff)

    cfg = RttovInputConfig(coef_id="ami_cloud", channels=_CHANNELS)
    run_k = make_live_run_k(tmp_path / "cloud_case")       # cloud RttovInput -> cloud fixture
    bt_hat, rad_quality = RttovObsOp.apply(
        run_k, cfg, t, q, None, p_half, clw, ciw, deff_liq, deff_ice, cfrac)

    obs = {"bt": torch.zeros(1, 16, dtype=f64)}            # obs BT 0 -> large IR residual
    mask = _build_mask(obs, rad_quality)
    assert float(mask.sum()) > 0.0
    j = compute_obs_loss(bt_hat, obs, mask, sigma=1.0)
    g_clw, g_ciw, g_dl, g_di = torch.autograd.grad(j, [clw, ciw, deff_liq, deff_ice])

    for g in (g_clw, g_ciw, g_dl, g_di):
        assert torch.isfinite(g).all()
    # content K (HYDRO6/7) live:
    assert float(g_clw.abs().sum()) > 0.0 and float(g_ciw.abs().sum()) > 0.0
    # Deff adjoint (HYDRO_DEFF6/7) LIVE -- the Phase 6 crux (else nc/ni have no obs path):
    assert float(g_dl.abs().sum()) > 0.0, "liquid Deff adjoint dead (HYDRO_DEFF6 K not wired)"
    assert float(g_di.abs().sum()) > 0.0, "ice Deff adjoint dead (HYDRO_DEFF7 K not wired)"
    # correct slot+layer wiring: Deff grad localizes to the cloudy layers it was fed in.
    assert float(g_di[15:25].abs().sum()) > 0.0          # ice Deff grad in the ice layers
    assert float(g_dl[40:50].abs().sum()) > 0.0          # liquid Deff grad in the liquid layers


@needs_cloud_live
def test_live_cloud_full_model_closure_nc_ni_through_deff(tmp_path):
    """Phase 6 NORTH STAR: the all-sky loop closes from MODEL leaves through the
    bridge AND live cloud K. model_to_rttov_tensors(cloud=True) maps qc/qi/qs -> content
    and nc/ni -> effective radius -> Deff; RttovObsOp.apply(live cloud run_k) ->
    compute_obs_loss -> autograd.grad. nc/ni reach BT ONLY through HYDRO_DEFF6/7, so a
    finite NONZERO nc/ni gradient proves the live Deff adjoint flows all the way back to
    the number concentrations (the design's nc/ni-via-Deff claim, end to end)."""
    from kdm6.obs.rttov_input_builder import RttovInputConfig
    from kdm6.obs.rttov_obs_operator import RttovObsOp, _build_mask
    from kdm6.obs.obs_loss import compute_obs_loss

    t_vec, q_vec, ph = _cloud_fixture_tq()
    nlay = len(t_vec)
    f64 = torch.float64
    M_DRY, M_VAP = 28.9647e-3, 18.01528e-3                # invert Q(ppmv moist) -> qv
    f = q_vec / 1.0e6
    qv_vec = M_VAP * f * (1.0 / M_DRY) / (1.0 - f)

    def band(lo, hi, val):
        a = np.zeros(nlay); a[lo:hi] = val; return a
    # Cloud chosen so BOTH (a) the cloud-sensitive IR channels stay usable and (b) the
    # number->Deff slopes are UNCLAMPED so nc/ni actually reach Deff:
    #  - THIN enough: a thick cloud saturates the IR channels, RTTOV flags them
    #    (rad_quality bit 15), _build_mask drops them, only bt=0 solar channels survive
    #    -> zero residual. qi=1.5e-4/qc=1e-4 keeps IR channels [6,11-15] usable.
    #  - ni=5e4 (not 5e5): a higher ni clamps the ice DSD slope, severing ni->Deff (a
    #    builder regime, cf. test_cloud_path_fd_vjp _mk_col); ni=5e4 sits in the
    #    unclamped ice-slope band so d(deff_ice)/d(ni) != 0 and the ni adjoint is live.
    qc = band(40, 50, 1.0e-4)                             # liquid cloud (lower trop)
    qi = band(15, 25, 1.5e-4)                             # ice cloud (upper trop)
    qs = band(15, 25, 3.0e-5)
    nc = band(40, 50, 6.0e7)                              # liquid number -> reff -> Deff
    ni = band(15, 25, 5.0e4)                              # ice number (unclamped slope band)
    zeros = np.zeros(nlay)

    def leaf(a):
        return torch.tensor(a, dtype=f64, requires_grad=True)
    th = torch.tensor(t_vec, dtype=f64, requires_grad=True)   # pii=1 -> t_lay = th
    qv = leaf(qv_vec)
    qc_t, qi_t, qs_t, nc_t, ni_t = leaf(qc), leaf(qi), leaf(qs), leaf(nc), leaf(ni)
    z = torch.tensor(zeros, dtype=f64)
    state = State(th=th, qv=qv, qc=qc_t, qr=z, qi=qi_t, qs=qs_t, qg=z,
                  nccn=torch.full((nlay,), 1.0e9, dtype=f64), nc=nc_t, ni=ni_t, nr=z, bg=z)
    rho = torch.tensor(np.linspace(0.05, 1.15, nlay), dtype=f64)    # TOA->surface
    ones = torch.ones(nlay, dtype=f64)
    forcing = Forcing(rho=rho, pii=ones, p=torch.tensor(np.linspace(2.0e3, 1.0e5, nlay), dtype=f64),
                      delz=torch.full((nlay,), 500.0, dtype=f64))

    profile_cfg = RttovProfileConfig(
        gas_units=2, qv_convention="mixing_ratio_kgkg_dry", rttov_layer_pressure=None,
        rttov_level_pressure=torch.tensor(ph, dtype=f64), cloud=True)
    prof = model_to_rttov_tensors(state, forcing, profile_cfg)
    input_cfg = RttovInputConfig(coef_id="ami_cloud", channels=_CHANNELS)
    run_k = make_live_run_k(tmp_path / "cloud_case")

    bt_hat, rad_quality = RttovObsOp.apply(
        run_k, input_cfg, prof.t_lay, prof.q_lay, prof.p_lay, prof.p_half,
        prof.clw, prof.ciw, prof.deff_liq, prof.deff_ice, prof.cfrac)
    obs = {"bt": torch.zeros(1, 16, dtype=f64)}
    mask = _build_mask(obs, rad_quality)
    assert float(mask.sum()) > 0.0
    j = compute_obs_loss(bt_hat, obs, mask, sigma=1.0)
    g = torch.autograd.grad(j, [th, qc_t, qi_t, qs_t, nc_t, ni_t], allow_unused=True,
                            materialize_grads=True)
    g_th, g_qc, g_qi, g_qs, g_nc, g_ni = g
    for name, gg in zip(("th", "qc", "qi", "qs", "nc", "ni"), g):
        assert torch.isfinite(gg).all(), name
    # content path (qc/qi/qs -> HYDRO6/7) live:
    assert float(g_qc.abs().sum()) > 0.0 and float(g_qi.abs().sum()) > 0.0
    # NORTH STAR: nc/ni reach BT ONLY through Deff -> nonzero grad proves the live
    # HYDRO_DEFF adjoint closes back to the number concentrations.
    assert float(g_nc.abs().sum()) > 0.0, "nc adjoint dead -> live liquid Deff path broken"
    assert float(g_ni.abs().sum()) > 0.0, "ni adjoint dead -> live ice Deff path broken"


@needs_cloud_live
def test_live_solar_reflectance_observable_and_refl_k(tmp_path):
    """Phase 7: the SOLAR channels use the REFLECTANCE observable + live REFL-K.

    With solar_channels set, make_live_run_k returns the per-channel observable = REFL
    for ch1-6 (in [0,~1.x], NOT a 200-300 K BT) and BT for the IR channels. The RTTOV K
    is already per-channel-type (REFL-K for solar, verified by FD), so gating the loss
    to ONLY the solar channels and differentiating proves the live reflectance adjoint:
    cloud content + Deff -> REFL -> loss -> grad is finite + nonzero, driven purely by
    the solar/REFL path (BT-K for a solar channel is ~0)."""
    from kdm6.obs.rttov_input_builder import RttovInputConfig
    from kdm6.obs.rttov_obs_operator import RttovObsOp, _build_mask
    from kdm6.obs.obs_loss import compute_obs_loss

    t_vec, q_vec, ph = _cloud_fixture_tq()
    nlay = len(t_vec); f64 = torch.float64
    t = torch.tensor(t_vec, dtype=f64); q = torch.tensor(q_vec, dtype=f64)
    p_half = torch.tensor(ph, dtype=f64)
    clw_np = np.zeros(nlay); clw_np[40:50] = 0.05         # thin reflective liquid
    ciw_np = np.zeros(nlay); ciw_np[15:25] = 0.01
    cfrac_np = np.zeros(nlay); cfrac_np[15:50] = 1.0
    clw = torch.tensor(clw_np, dtype=f64, requires_grad=True)
    ciw = torch.tensor(ciw_np, dtype=f64, requires_grad=True)
    deff_liq = torch.full((nlay,), 20.0, dtype=f64, requires_grad=True)
    deff_ice = torch.full((nlay,), 45.0, dtype=f64, requires_grad=True)
    cfrac = torch.tensor(cfrac_np, dtype=f64)

    cfg = RttovInputConfig(coef_id="ami_cloud", channels=_CHANNELS)
    solar = (1, 2, 3, 4, 5, 6)
    run_k = make_live_run_k(tmp_path / "solar_case", solar_channels=solar)
    y_hat, rad_quality = RttovObsOp.apply(run_k, cfg, t, q, None, p_half,
                                          clw, ciw, deff_liq, deff_ice, cfrac)
    y = y_hat.detach().numpy()[0]
    # solar channels carry REFLECTANCE (small, dimensionless), IR carry BT (Kelvin).
    assert np.all(y[:6] < 5.0) and np.any(y[:6] > 0.01), y[:6]
    assert np.all((y[6:] > 150.0) & (y[6:] < 350.0)), y[6:]

    # SOLAR-ISOLATED grad: gate the loss to ONLY the solar channels so it is driven
    # purely by REFL + REFL-K. A nonzero cloud grad here proves the reflectance adjoint
    # (a solar channel's BT-K is ~0, so this signal can only come from REFL-K).
    solar_gate = torch.zeros(1, 16, dtype=f64); solar_gate[0, :6] = 1.0
    obs = {"bt": torch.zeros(1, 16, dtype=f64), "channel_gate": solar_gate}
    mask = _build_mask(obs, rad_quality)
    assert float(mask.sum()) > 0.0, "need >=1 usable solar channel (rad_quality==0)"
    j = compute_obs_loss(y_hat, obs, mask, sigma=0.1)     # reflectance-scale sigma
    g_clw, g_ciw, g_dl, g_di = torch.autograd.grad(
        j, [clw, ciw, deff_liq, deff_ice], allow_unused=True, materialize_grads=True)
    for g in (g_clw, g_ciw, g_dl, g_di):
        assert torch.isfinite(g).all()
    # liquid content + Deff drive the solar reflectance -> live REFL-K grad.
    assert float(g_clw.abs().sum()) > 0.0, "liquid content REFL adjoint dead"
    assert float(g_dl.abs().sum()) > 0.0, "liquid Deff REFL adjoint dead"
