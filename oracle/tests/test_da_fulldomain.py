"""v9 전 도메인 all-sky dual CVT 분석 — 캡 축소 스모크 게이트.

전체 J-부분공간 실행(수십 분)의 축소판: cloudy 12 + clear 50, 2 워커,
max_iter=2. 게이트: J 하강, O−A ≤ O−B, hydrometeor 증분 비영, 보고 dict의
캡 정직 기록. 외부 자산 4종(LC05/GK2A/검정/live cloud RTTOV) 없으면 skip.
"""
from __future__ import annotations

import json

import pytest
import torch

from test_real_innovation_lc05 import _CAL, _GK2A, _WRFIN, needs_all


@needs_all
def test_fulldomain_smoke_capped(tmp_path):
    import numpy as np
    from kdm6.da_fulldomain import run_fulldomain_analysis
    from kdm6.io.frame_reader import read_wrfout_frame
    from kdm6.obs.gk2a_l1b import (CLEAN_IR_CHANNELS, load_cal_table,
                                   read_ko_slot, slot_files)
    from kdm6.obs.obs_ingest import payload_to_column_obs
    from kdm6.obs.rttov_case_writer import fixture_layer_pressure
    from test_rttov_case_writer import (_CHANNELS, _HAVE_CLOUD_EXE,
                                        _fixture_p_half, _fixture_tq)
    if not _HAVE_CLOUD_EXE:
        pytest.skip("live cloud RTTOV (ami_cloud) 부재")

    fr = read_wrfout_frame(str(_WRFIN), 0)
    cal = load_cal_table(_CAL)
    pl = read_ko_slot(slot_files(_GK2A, "202507190000",
                                 channels=CLEAN_IR_CHANNELS), cal, stride=8)
    co = payload_to_column_obs(pl, fr.meta["lat"], fr.meta["lon"],
                               max_dist_km=4.0)
    tr, qr = _fixture_tq()
    grids = dict(p_lay=fixture_layer_pressure(), p_half=_fixture_p_half(),
                 t_ref=tr, q_ref=qr)

    # time_tolerance_s=300 is an EXPLICIT time-representativeness statement:
    # the 00:00 UTC obs is compared against the 00:05 slot state (obs_time=1
    # puts M in the obs term); the data-derived offset is 0 s.
    # qv_levels covers ALL levels: an a-priori cloud-analysis B choice fixed
    # before the run (never switched by the observed cloud — review #8);
    # upper-level regime-2 cloud tops need qv control there.
    rep = run_fulldomain_analysis(
        fr, co, grids, str(tmp_path / "v9smoke"),
        n_workers=2, max_iter=2, max_cloudy=12, max_clear=50,
        channels=_CHANNELS, pseudo_rh=True, time_tolerance_s=300.0,
        qv_levels=int(fr.meta["kme"]),
        save_fields=str(tmp_path / "fields.npz"))

    json.dumps(rep)                                      # report serializable
    fields = np.load(tmp_path / "fields.npz")            # imagery archive
    assert fields["xa_qc"].shape == fields["xb_qc"].shape
    assert fields["bt_b"].shape == fields["y_bt"].shape  # regime diagnostics
    # Re-review: physical classification vs operator routing are SEPARATE
    # sets — the all-sky routing set is model-cloudy plus regime-2 columns,
    # while the 4-regime report uses the physical set only.
    assert rep["obs_time"] == 1 and rep["huber_delta"] == 3.0
    # theta observability is physics/gate dependent (operational ncmin can
    # legitimately close the autoconversion branches for a small scene) —
    # the theta CHAIN is proven by the CI-safe dual FD tests; here we only
    # require the diagnostic to be present and finite.
    import math as _math
    assert _math.isfinite(rep["grad_theta_norm_final"])
    assert rep["n_model_cloudy"] == 12                   # slot-time physical
    assert rep["n_allsky_routed"] == 12 + rep["n_regime2"]
    assert rep["n_clear_operator"] + rep["n_regime2"] + 12 == rep["n_subspace"]
    assert int(fields["n_allsky"]) == rep["n_allsky_routed"]
    # 4-regime stratified report: keys complete, counts bounded, and the
    # clear/cloudy regime is NOT emptied by the routing (review #2)
    assert set(rep["regimes"]) == {"clear_clear", "clear_cloudy",
                                   "cloudy_cloudy", "cloudy_clear"}
    assert sum(r["n"] for r in rep["regimes"].values()) <= rep["n_subspace"]
    assert rep["regimes"]["clear_cloudy"]["n"] >= rep["n_regime2"]
    assert rep["caps"]["max_cloudy"] == 12
    assert rep["n_valid"] > 0
    assert rep["j_trace"][-1]["total"] < rep["j_trace"][0]["total"]
    assert rep["oma"] <= rep["omb"], (rep["oma"], rep["omb"])
    hydro = max(rep["increment_norms"][f] for f in ("qc", "qi", "qs", "nc"))
    assert hydro > 0.0, "no hydrometeor increment at t0"
    assert rep["pathology"] == {}, rep["pathology"]      # physical caps hold
    for f in ("qr", "qg", "nr", "nccn", "bg"):           # default-off fields
        assert rep["increment_norms"][f] == 0.0, f


# ── P0 검토 수정: Huber 손실 / regime-2 선택 (CI-safe 단위) ──────────────────

def test_part_loss_huber_matches_obs_loss():
    """전 도메인 파트 손실이 obs_loss._huber와 동일 산식 (P0-3: 순수 이차의
    비물리 증분 유인 제거 — v9.1 qi 폭주의 처방)."""
    import torch
    from kdm6.da_fulldomain import _part_loss
    from kdm6.obs.obs_loss import _huber

    g = torch.Generator().manual_seed(5)
    bt = 250.0 + 30.0 * torch.randn((3, 4), generator=g, dtype=torch.float64)
    y = 250.0 + 5.0 * torch.randn((3, 4), generator=g, dtype=torch.float64)
    mask = (torch.rand((3, 4), generator=g) > 0.3).double()
    # δ=None → 기존 순수 이차 (bitwise 호환)
    r = mask * (bt - y)
    assert torch.equal(_part_loss(bt, y, mask, None), 0.5 * (r * r).sum())
    # δ 지정 → Huber
    assert torch.allclose(_part_loss(bt, y, mask, 3.0), _huber(r, 3.0).sum(),
                          rtol=0.0, atol=0.0)


def test_select_regime2_positions():
    """모델-맑음(clear_pos) ∧ 관측-구름(ir 유효 & BT<270) 위치의 동결 선택."""
    import torch
    from kdm6.da_fulldomain import select_regime2_positions

    y_bt = torch.full((6, 16), 280.0, dtype=torch.float64)
    y_rq = torch.zeros((6, 16), dtype=torch.float64)
    y_bt[1, 12] = 250.0                      # clear_pos 안 + 관측 구름 → 선택
    y_bt[2, 12] = 250.0                      # cloudy_pos → 제외 (regime 3)
    y_bt[4, 12] = 250.0
    y_rq[4, 12] = 1.0                        # ir 무효 → 제외
    clear_pos = torch.tensor([1, 3, 4, 5])
    r2 = select_regime2_positions(y_bt, y_rq, clear_pos)
    assert r2.tolist() == [1]


def test_part_loss_masked_nonfinite_safe():
    """Codex regression: a non-finite obs value in a masked (invalid) channel
    must not poison j via 0*NaN=NaN — same replace-before-_huber discipline
    as compute_obs_loss."""
    import torch
    from kdm6.da_fulldomain import _part_loss

    bt = torch.tensor([[250.0, 260.0]], dtype=torch.float64)
    y = torch.tensor([[float("nan"), 255.0]], dtype=torch.float64)
    mask = torch.tensor([[0.0, 1.0]], dtype=torch.float64)   # NaN channel is masked out
    for delta in (None, 3.0):
        j = _part_loss(bt, y, mask, delta)
        assert bool(torch.isfinite(j)), (delta, float(j))
    y_inf = torch.tensor([[float("inf"), 255.0]], dtype=torch.float64)
    for delta in (None, 3.0):
        assert bool(torch.isfinite(_part_loss(bt, y_inf, mask, delta))), delta


def test_part_loss_rejects_bad_delta():
    """Review #6: huber_delta=0 silently zeroes the obs cost/gradient and a
    negative delta allows negative cost — only None or finite>0 is legal
    (same validation as compute_obs_loss)."""
    import pytest
    import torch
    from kdm6.da_fulldomain import _part_loss

    bt = torch.zeros((1, 2), dtype=torch.float64)
    y = torch.ones((1, 2), dtype=torch.float64)
    m = torch.ones((1, 2), dtype=torch.float64)
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            _part_loss(bt, y, m, bad)


def test_obs_time_alignment_check():
    """Review #1: the obs slot time t0 + obs_time*dt must match the obs
    valid-time offset within tolerance — a silent 5-min displacement must
    fail loudly when outside the stated tolerance."""
    import pytest
    from kdm6.da_fulldomain import check_obs_time_alignment

    check_obs_time_alignment(1, 300.0, obs_offset_s=0.0,
                             time_tolerance_s=300.0)      # boundary: pass
    with pytest.raises(ValueError, match="obs valid time"):
        check_obs_time_alignment(1, 300.0, obs_offset_s=0.0,
                                 time_tolerance_s=299.0)
    with pytest.raises(ValueError, match="obs valid time"):
        check_obs_time_alignment(2, 600.0, obs_offset_s=0.0,
                                 time_tolerance_s=600.0)


def test_pseudo_qv_overlap_validation():
    """Review #5: a pseudo-RH level with sigma_qv == 0 everywhere in a
    column has exactly zero CVT gradient — the composition must be rejected
    instead of silently doing nothing."""
    import pytest
    import torch
    from kdm6.da_fulldomain import validate_pseudo_qv_overlap

    sigma_qv = torch.zeros((3, 5), dtype=torch.float64)
    sigma_qv[:, :2] = 0.08                       # only levels 0-1 controlled
    cols = torch.tensor([0, 2])
    levels_ok = torch.tensor([[True, False, False, False, False],
                              [True, True, False, False, False]])
    validate_pseudo_qv_overlap(sigma_qv, cols, levels_ok)  # passes
    levels_dead = torch.tensor([[False, False, False, True, False],
                                [True, False, False, False, False]])
    with pytest.raises(ValueError, match="no CVT-controlled qv level"):
        validate_pseudo_qv_overlap(sigma_qv, cols, levels_dead)


def test_obs_time_alignment_rejects_nonfinite():
    """Codex regression: NaN comparisons are False, so non-finite dt/offset/
    tolerance silently passed the alignment check (fail-open) — must raise."""
    import pytest
    from kdm6.da_fulldomain import check_obs_time_alignment

    nan, inf = float("nan"), float("inf")
    for kw in (dict(dt=nan, obs_offset_s=0.0, time_tolerance_s=300.0),
               dict(dt=300.0, obs_offset_s=nan, time_tolerance_s=300.0),
               dict(dt=300.0, obs_offset_s=0.0, time_tolerance_s=nan),
               dict(dt=inf, obs_offset_s=0.0, time_tolerance_s=300.0),
               dict(dt=-300.0, obs_offset_s=0.0, time_tolerance_s=300.0),
               dict(dt=300.0, obs_offset_s=0.0, time_tolerance_s=-1.0)):
        with pytest.raises(ValueError):
            check_obs_time_alignment(1, kw["dt"],
                                     obs_offset_s=kw["obs_offset_s"],
                                     time_tolerance_s=kw["time_tolerance_s"])


def test_utc_parse_and_offset_derivation():
    """Review #1: valid times must come from the DATA, not caller-typed
    numbers. Parse GK2A stamps (yyyymmddHHMM) and WRF Times
    (YYYY-MM-DD_HH:MM:SS) and derive the obs-frame offset in seconds."""
    import pytest
    from kdm6.da_fulldomain import derive_obs_offset_s, parse_utc_s

    t_frame = parse_utc_s("2025-07-19_00:00:00")     # WRF Times format
    t_obs = parse_utc_s("202507190010")              # GK2A stamp format
    assert t_obs - t_frame == 600.0
    assert derive_obs_offset_s("202507190010", "2025-07-19_00:00:00") == 600.0
    with pytest.raises(ValueError):
        parse_utc_s("not-a-time")


def test_clear_bt_chunked_empty_partition():
    """Review #6: an all-cloudy / all-regime2 scene leaves the clear
    partition empty — torch.cat over zero chunks must not crash; return
    (0, nch) tensors without touching RTTOV."""
    import torch
    from kdm6.da_fulldomain import _clear_bt_chunked
    from kdm6.state import Forcing, State

    empty = State(*(torch.zeros((0, 3), dtype=torch.float64)
                    for _ in range(12)))
    fc = Forcing(*(torch.zeros((0, 3), dtype=torch.float64)
                   for _ in range(4)))
    bt, rq = _clear_bt_chunked(empty, fc, None, 16)   # cfg unused when empty
    assert bt.shape == (0, 16) and rq.shape == (0, 16)


def test_pseudo_sigma_p_validated():
    """Review #8 addendum: sigma_p flows into a division — must be finite>0."""
    import pytest
    import torch
    from kdm6.da_regime2 import pseudo_rh_term
    from kdm6.state import State

    x = State(*(torch.ones((2, 3), dtype=torch.float64) for _ in range(12)))
    cols = torch.tensor([0])
    target = torch.ones((1, 3), dtype=torch.float64)
    for bad in (0.0, -1.0, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            pseudo_rh_term(x, cols, target, sigma_p=bad)


def test_post_cap_empty_subspace_rejected():
    """Codex regression: caps can empty the working subspace after the
    slot-time partition (e.g. max_cloudy=0, max_clear=0) — reject instead
    of running the minimizer over zero columns. CI-safe: reaches the check
    before any RTTOV call (the slot forward is the pure-torch oracle)."""
    import pytest
    import torch
    from kdm6 import thermo
    from kdm6.da_fulldomain import run_fulldomain_analysis
    from kdm6.state import Forcing, State

    K = 2
    th = torch.tensor([[296.8, 282.4]], dtype=torch.float64)
    pii = torch.tensor([[0.9704, 0.9031]], dtype=torch.float64)
    p = torch.tensor([[9.0e4, 7.0e4]], dtype=torch.float64)
    qs = thermo.compute_qs_water(th * pii, p,
                                 params=thermo.default_thermo_params())
    z = torch.zeros_like(th)
    state = State(th=th, qv=0.9 * qs, qc=z.clone(), qr=z.clone(),
                  qi=z.clone(), qs=z.clone(), qg=z.clone(),
                  nccn=torch.full_like(th, 1.0e9), nc=z.clone(),
                  ni=z.clone(), nr=z.clone(), bg=z.clone())
    forcing = Forcing(rho=torch.full_like(th, 1.0), pii=pii, p=p,
                      delz=torch.full_like(th, 500.0))

    class Frame:
        pass
    fr = Frame()
    fr.state, fr.forcing = state, forcing
    fr.xland = torch.ones(1, dtype=torch.float64)
    fr.meta = dict(nx=1, ny=1, kme=K, valid_time_utc="2025-07-19_00:00:00")

    class Obs:
        pass
    co = Obs()
    co.bt = torch.full((1, 16), 260.0, dtype=torch.float64)
    co.obs_quality = torch.zeros((1, 16), dtype=torch.float64)
    co.valid_time_utc = "202507190005"

    grids = dict(p_lay=[500.0], p_half=[450.0, 550.0],
                 t_ref=[250.0], q_ref=[10.0])
    # The message must carry the PRE-cap partition sizes (this synthetic
    # scene is 0 cloudy / 1 clear before the caps zero it out).
    with pytest.raises(ValueError,
                       match=r"partition 0 cloudy / 1 clear before caps"):
        run_fulldomain_analysis(fr, co, grids, "/tmp/unused",
                                boundary=0, max_cloudy=0, max_clear=0,
                                channels=tuple(range(16)))
