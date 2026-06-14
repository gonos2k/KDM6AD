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
    default_fixture_case_dir, make_live_run_k, write_rttov_case)
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
def test_overlay_rejects_layer_pressure(tmp_path):
    """profile['P'] (layer pressure) is rejected, not silently accepted: the run
    derives layers from the fixture p_half and never honors a layer-pressure input,
    so accepting it (even a bracketed one) would silently honor an unused grid."""
    t_vec, q_vec = _fixture_tq()
    ph = _fixture_p_half()
    p_lay = np.sqrt(ph[1:] * np.clip(ph[:-1], 1e-9, None))   # plausible (bracketed) grid
    rin = _rttov_input_from_arrays(t_vec, q_vec, p_lay=p_lay)
    assert "P" in rin.profile
    with pytest.raises(ValueError, match="layer pressure"):
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
