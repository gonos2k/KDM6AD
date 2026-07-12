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

from kdm6.da_partition import PartitionSpec


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
    # Physical caps hold at BOTH audit times — t0 (analysis initial state)
    # and the slot state the observation actually saw (re-review #7).
    assert rep["pathology_t0"] == {}, rep["pathology_t0"]
    assert rep["pathology_slot"] == {}, rep["pathology_slot"]
    assert rep["nonfinite_fields_t0"] == [] and rep["nonfinite_fields_slot"] == []
    assert rep["offset_source"] == "data" and rep["obs_valid_time_utc"]
    assert "xslot_a_qc" in fields                       # slot states archived
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


def test_driver_input_validation_caps_qvlevels_xland():
    """Re-review residuals: caps must be None or int>=0 (negative slices
    silently truncate), qv_levels must be an int in [0, K], xland must be
    the WRF {1, 2} contract. Reuses the CI-safe synthetic frame."""
    import pytest
    import torch
    from kdm6 import thermo
    from kdm6.da_fulldomain import run_fulldomain_analysis
    from kdm6.state import Forcing, State

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
    fr.meta = dict(nx=1, ny=1, kme=2, valid_time_utc="2025-07-19_00:00:00")

    class Obs:
        pass
    co = Obs()
    co.bt = torch.full((1, 16), 260.0, dtype=torch.float64)
    co.obs_quality = torch.zeros((1, 16), dtype=torch.float64)
    co.valid_time_utc = "202507190005"
    grids = dict(p_lay=[500.0], p_half=[450.0, 550.0],
                 t_ref=[250.0], q_ref=[10.0])

    def run(**kw):
        return run_fulldomain_analysis(fr, co, grids, "/tmp/unused",
                                       boundary=0, channels=tuple(range(16)),
                                       **kw)

    with pytest.raises(ValueError, match="max_cloudy"):
        run(max_cloudy=-1)
    with pytest.raises(ValueError, match="max_clear"):
        run(max_clear=-2)
    for bad in (-1, 1.5, True):
        with pytest.raises(ValueError, match="qv_levels"):
            run(qv_levels=bad)
    fr.xland = torch.tensor([-999.0])
    with pytest.raises(ValueError, match="xland"):
        run()
    fr.xland = torch.ones(1, dtype=torch.float64)
    # explicit offset conflicting with data-derived one must fail closed
    with pytest.raises(ValueError, match="obs_offset_s"):
        run(obs_offset_s=0.0)          # data says 300 s, caller says 0


def test_evaluate_artifact_gates():
    """Codex regression: the evidence runner must ENFORCE the acceptance
    gates, not merely report them — a run with slot-time pathology or a
    non-descending J must be rejected (exit nonzero), never a
    passing-looking artifact."""
    from kdm6.da_fulldomain import evaluate_artifact_gates

    good = dict(j_trace=[dict(total=100.0), dict(total=90.0)],
                omb=5.0, oma=4.0, pathology_t0={}, pathology_slot={},
                nonfinite_fields_t0=[], nonfinite_fields_slot=[],
                grad_theta_norm_final=0.1)
    gates = evaluate_artifact_gates(good)
    assert gates["accepted"] is True
    assert all(v for k, v in gates.items() if k != "accepted")

    for corrupt, expect_fail in (
            (dict(pathology_slot={"qi": dict(max=2541.0, n_over=91)}),
             "pathology_slot_empty"),
            (dict(j_trace=[dict(total=100.0), dict(total=101.0)]),
             "j_descended"),
            (dict(oma=6.0), "oma_le_omb"),
            (dict(nonfinite_fields_slot=["qc"]), "no_nonfinite_slot"),
            (dict(grad_theta_norm_final=float("nan")), "finite_diagnostics")):
        rep = dict(good, **corrupt)
        gates = evaluate_artifact_gates(rep)
        assert gates["accepted"] is False, corrupt
        assert gates[expect_fail] is False, corrupt


def _good_conserving_report():
    """A COMPLETE conserving evidence report (every field the strengthened
    gates require) — the base for the negative fail-closed matrix."""
    tail = dict(total=90.0, j_state=1.5, j_theta=0.5, j_obs=88.0)
    return dict(
        artifact_role="conserving_stress", conserving=True,
        j_trace=[dict(total=100.0), dict(total=91.0), tail],
        n_window_evals=2, n_audit_evals=1,
        jb_final=1.5, jtheta_final=0.5, jobs_final=88.0,   # sums to 90.0
        grad_norm_final=3.0,
        grad_theta_norm_final=0.1, grad_w_norm_final=2.0,
        omb=5.0, oma=4.0, pathology_t0={}, pathology_slot={},
        nonfinite_fields_t0=[], nonfinite_fields_slot=[],
        water_budget=dict(pw_stage_err_max=3.0e-16,
                          dtw_qv_diag_max=1.0e-4,
                          dtw_qv_diag_mean=2.0e-5),
        partition=dict(
            spec=PartitionSpec().as_dict(),
            fingerprint=PartitionSpec().fingerprint()),
        cvt=dict(n_controlled=dict(qc=0, qr=0, qi=0, qs=0, qg=0,
                                   th=100, qv=100)))


def test_evaluate_artifact_gates_conserving_and_audit():
    """Conserving evidence artifacts carry three additional ENFORCED gates:
    P_w water conservation, the strengthened final-audit consistency, and
    the conserving contract (partition schema v2 + zero mass-hydro diagonal
    controls)."""
    from kdm6.da_fulldomain import evaluate_artifact_gates

    gates = evaluate_artifact_gates(_good_conserving_report())
    assert gates["accepted"] is True
    assert gates["pw_conserved"] is True
    assert gates["final_audited"] is True
    assert gates["conserving_contract"] is True

    # legacy reports (no conserving keys at all) keep their gate set
    legacy = dict(j_trace=[dict(total=100.0), dict(total=90.0)],
                  omb=5.0, oma=4.0, pathology_t0={}, pathology_slot={},
                  nonfinite_fields_t0=[], nonfinite_fields_slot=[],
                  grad_theta_norm_final=0.1)
    gates = evaluate_artifact_gates(legacy)
    assert gates["accepted"] is True
    for k in ("pw_conserved", "final_audited", "conserving_contract"):
        assert k not in gates


def test_conserving_gates_fail_closed_on_missing_fields():
    """Reviewer P1: a conserving run whose evidence fields REGRESS AWAY must
    fail the gates, never silently pass with a smaller gate set — every
    missing/None/malformed field evaluates to False."""
    from kdm6.da_fulldomain import evaluate_artifact_gates

    base = _good_conserving_report()

    def gate_of(mutation, gate):
        rep = json.loads(json.dumps(base))          # deep copy
        mutation(rep)
        gates = evaluate_artifact_gates(rep)
        assert gates["accepted"] is False, (gate, mutation)
        assert gates[gate] is False, (gate, mutation)

    # pw_conserved fail-closed
    gate_of(lambda r: r.pop("water_budget"), "pw_conserved")
    gate_of(lambda r: r.update(water_budget=None), "pw_conserved")
    gate_of(lambda r: r["water_budget"].pop("pw_stage_err_max"),
            "pw_conserved")
    gate_of(lambda r: r["water_budget"].update(pw_stage_err_max=1.0e-6),
            "pw_conserved")
    gate_of(lambda r: r["water_budget"].update(
        pw_stage_err_max=float("nan")), "pw_conserved")
    # final_audited fail-closed + consistency
    gate_of(lambda r: r.pop("n_audit_evals"), "final_audited")
    gate_of(lambda r: r.update(n_audit_evals=0), "final_audited")
    gate_of(lambda r: r.pop("n_window_evals"), "final_audited")
    gate_of(lambda r: r.update(n_window_evals=5), "final_audited")
    gate_of(lambda r: r.pop("jb_final"), "final_audited")
    gate_of(lambda r: r.update(jb_final=1.6), "final_audited")   # sum breaks
    gate_of(lambda r: r.update(grad_w_norm_final=float("inf")),
            "final_audited")
    # a CONSERVING run has a live partition: grad_w_norm_final must exist
    # and be finite — a missing/None w-gradient diagnostic is fail-closed
    # (Codex: the is-not-None skip made this pass silently)
    gate_of(lambda r: r.pop("grad_w_norm_final"), "final_audited")
    gate_of(lambda r: r.update(grad_w_norm_final=None), "final_audited")
    # conserving contract fail-closed
    gate_of(lambda r: r.pop("partition"), "conserving_contract")
    gate_of(lambda r: r["partition"]["spec"].update(version=1),
            "conserving_contract")
    gate_of(lambda r: r["cvt"]["n_controlled"].update(qc=5),
            "conserving_contract")
    gate_of(lambda r: r.pop("cvt"), "conserving_contract")

    # numeric-domain strictness: impossible values fail (reviewer P2)
    gate_of(lambda r: r["water_budget"].update(pw_stage_err_max=-1.0),
            "pw_conserved")
    gate_of(lambda r: r.update(grad_theta_norm_final=-0.1), "final_audited")
    gate_of(lambda r: r.update(grad_norm_final=-3.0), "final_audited")
    # negative J component compensated inside the total: per-component
    # trace-tail comparison catches it
    def _compensate(r):
        r.update(jb_final=-1.5, jobs_final=91.0)
        r["j_trace"][-1].update(j_state=-1.5, j_obs=91.0)
    gate_of(_compensate, "final_audited")
    gate_of(lambda r: r["j_trace"][-1].update(j_obs=87.0), "final_audited")
    # type strictness: bool/float masquerading as counts/version
    gate_of(lambda r: r.update(n_audit_evals=True), "final_audited")
    gate_of(lambda r: r.update(n_audit_evals=1.0), "final_audited")
    gate_of(lambda r: r.update(n_window_evals=2.0), "final_audited")
    gate_of(lambda r: r["partition"]["spec"].update(version=2.0),
            "conserving_contract")
    gate_of(lambda r: r["cvt"]["n_controlled"].update(qc=False),
            "conserving_contract")
    gate_of(lambda r: r["cvt"]["n_controlled"].update(qc=0.0),
            "conserving_contract")
    # deep v2 schema: every spec field and the fingerprint are load-bearing
    gate_of(lambda r: r["partition"]["spec"].pop("control_units"),
            "conserving_contract")
    gate_of(lambda r: r["partition"]["spec"].pop("sigma_rule"),
            "conserving_contract")
    gate_of(lambda r: r["partition"]["spec"].update(
        channels=list(reversed(r["partition"]["spec"]["channels"]))),
            "conserving_contract")
    gate_of(lambda r: r["partition"]["spec"].update(alpha_total=0.4),
            "conserving_contract")            # fingerprint no longer matches
    gate_of(lambda r: r["partition"].update(fingerprint="deadbeef"),
            "conserving_contract")
    # malformed CONTAINER types must evaluate False, not crash the gate
    # (Codex: a non-dict spec raised AttributeError out of the try)
    gate_of(lambda r: r["partition"].update(spec="v2"), "conserving_contract")
    gate_of(lambda r: r["partition"].update(spec=[2]), "conserving_contract")
    gate_of(lambda r: r.update(partition="conserving"), "conserving_contract")
    gate_of(lambda r: r["cvt"].update(n_controlled=[0, 0, 0, 0, 0]),
            "conserving_contract")
    gate_of(lambda r: r.update(j_trace=5), "final_audited")
    # OMA/OMB and every trace total/component are nonnegative finite
    # non-bool numbers (reviewer round: -1 K stats and True totals passed)
    gate_of(lambda r: r.update(omb=-1.0), "oma_le_omb")
    gate_of(lambda r: r.update(oma=-2.0, omb=-1.0), "oma_le_omb")
    gate_of(lambda r: r.update(oma=None), "oma_le_omb")      # False, no crash
    gate_of(lambda r: r["j_trace"][1].update(total=-1.0), "j_descended")
    gate_of(lambda r: r["j_trace"][1].update(total=True), "j_descended")
    def _bool_tail(r):
        r.update(jb_final=1.0, jobs_final=88.5)
        r["j_trace"][-1].update(j_state=True, j_obs=88.5)
        # True == 1.0 numerically — the component type check must reject
    gate_of(_bool_tail, "final_audited")
    # JSON-valid huge ints overflow math.isfinite — normalized to False
    gate_of(lambda r: r["water_budget"].update(pw_stage_err_max=10**309),
            "pw_conserved")
    gate_of(lambda r: r.update(jobs_final=10**309), "final_audited")
    # bool alpha_total (True == 1.0) with a consistently-recomputed
    # fingerprint must still fail: PartitionSpec rejects bool
    def _bool_alpha(r):
        r["partition"]["spec"].update(alpha_total=True)
    gate_of(_bool_alpha, "conserving_contract")
    gate_of(lambda r: r.update(j_trace=[]), "final_audited")
    gate_of(lambda r: r["j_trace"].__setitem__(-1, 90.0), "final_audited")

    # the trigger is conserving=True OR artifact_role — role alone suffices
    rep = json.loads(json.dumps(base))
    del rep["conserving"]
    del rep["water_budget"]
    gates = evaluate_artifact_gates(rep)
    assert gates["accepted"] is False and gates["pw_conserved"] is False


def test_expected_conserving_external_contract():
    """Reviewer P1: the runner-known mode is an EXTERNAL contract — losing
    BOTH self-declaration markers must not shrink the gate set when the
    runner says the run was conserving."""
    from kdm6.da_fulldomain import evaluate_artifact_gates

    base = _good_conserving_report()
    gates = evaluate_artifact_gates(base, expected_conserving=True)
    assert gates["accepted"] is True and gates["conserving_marker"] is True

    # both markers lost + contract corrupted: with the external contract the
    # full conserving gate set is STILL generated and fails
    rep = json.loads(json.dumps(base))
    del rep["conserving"]
    rep["artifact_role"] = "pathology_stress"
    del rep["grad_w_norm_final"]
    rep["cvt"]["n_controlled"]["qc"] = 1
    gates = evaluate_artifact_gates(rep, expected_conserving=True)
    assert gates["accepted"] is False
    assert gates["conserving_marker"] is False
    assert gates["final_audited"] is False        # grad_w required
    assert gates["conserving_contract"] is False  # qc controlled

    # mode confusion the other way: runner says non-conserving but the
    # report declares conserving
    gates = evaluate_artifact_gates(base, expected_conserving=False)
    assert gates["conserving_marker"] is False and gates["accepted"] is False

    # under the external contract BOTH markers are checked individually
    # (the OR inference hid absence/typos/mutual contradiction)
    for mutate in (
            lambda r: r.pop("conserving"),               # flag missing
            lambda r: r.pop("artifact_role"),            # role missing
            lambda r: r.update(conserving=False),        # contradiction
            lambda r: r.update(artifact_role="typo_stress")):
        rep = json.loads(json.dumps(base))
        mutate(rep)
        gates = evaluate_artifact_gates(rep, expected_conserving=True)
        assert gates["conserving_marker"] is False, mutate
        assert gates["accepted"] is False

    # non-conserving report under the external contract: markers must be
    # exactly (False, pathology_stress) and the audit gate stays enforced
    legacy = dict(conserving=False, artifact_role="pathology_stress",
                  j_trace=[dict(total=100.0), dict(total=91.0),
                           dict(total=90.0, j_state=1.5, j_theta=0.5,
                                j_obs=88.0)],
                  n_window_evals=2, n_audit_evals=1,
                  jb_final=1.5, jtheta_final=0.5, jobs_final=88.0,
                  grad_norm_final=3.0, grad_theta_norm_final=0.1,
                  partition=None, water_budget=None, grad_w_norm_final=None,
                  omb=5.0, oma=4.0, pathology_t0={}, pathology_slot={},
                  nonfinite_fields_t0=[], nonfinite_fields_slot=[])
    gates = evaluate_artifact_gates(legacy, expected_conserving=False)
    assert gates["accepted"] is True
    assert gates["conserving_marker"] is True
    assert gates["nonconserving_payload_absent"] is True
    assert "conserving_contract" not in gates
    # runner says non-conserving: any conserving-only payload is a
    # mode/payload contradiction — each item alone must fail (reviewer P1)
    for mutate in (lambda r: r.update(partition=dict(spec=dict(version=2))),
                   lambda r: r.update(grad_w_norm_final=2.0),
                   lambda r: r.update(water_budget=dict(
                       pw_stage_err_max=1.0e-16)),
                   lambda r: r.pop("partition"),
                   lambda r: r.pop("water_budget"),
                   lambda r: r.pop("grad_w_norm_final")):
        rep = json.loads(json.dumps(legacy))
        mutate(rep)
        gates = evaluate_artifact_gates(rep, expected_conserving=False)
        assert gates["nonconserving_payload_absent"] is False, mutate
        assert gates["accepted"] is False
    for mutate in (lambda r: r.pop("conserving"),
                   lambda r: r.pop("artifact_role"),
                   lambda r: r.update(artifact_role="typo_stress")):
        rep = json.loads(json.dumps(legacy))
        mutate(rep)
        gates = evaluate_artifact_gates(rep, expected_conserving=False)
        assert gates["conserving_marker"] is False, mutate
    # under the external contract the v-block gradient is REQUIRED evidence
    nov = json.loads(json.dumps(legacy))
    del nov["grad_norm_final"]
    gates = evaluate_artifact_gates(nov, expected_conserving=False)
    assert gates["accepted"] is False and gates["final_audited"] is False
    # reviewer P1: dropping the WHOLE audit block under a non-conserving
    # external contract must not delete the gate — it must fail
    noaudit = json.loads(json.dumps(legacy))
    for k in ("n_audit_evals", "n_window_evals", "jb_final",
              "jtheta_final", "jobs_final", "grad_norm_final"):
        del noaudit[k]
    gates = evaluate_artifact_gates(noaudit, expected_conserving=False)
    assert "final_audited" in gates
    assert gates["final_audited"] is False and gates["accepted"] is False


@needs_all
def test_fulldomain_smoke_conserving_capped(tmp_path):
    """Conserving-mode driver smoke: mass-hydro diagonal sigma zeroed, the
    partition stage live, water budget split into the P_w stage error
    (roundoff) and the deliberate qv-diagonal change, finals authoritative
    (single audit closure)."""
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
    rep = run_fulldomain_analysis(
        fr, co, grids, str(tmp_path / "v10smoke"),
        n_workers=2, max_iter=2, max_cloudy=12, max_clear=50,
        channels=_CHANNELS, pseudo_rh=True, time_tolerance_s=300.0,
        qv_levels=int(fr.meta["kme"]), conserving=True)

    json.dumps(rep)
    assert rep["conserving"] is True
    assert rep["partition"]["spec"]["version"] == 2
    assert rep["n_audit_evals"] == 1
    assert len(rep["j_trace"]) == rep["n_window_evals"] + 1
    assert rep["j_trace"][-1]["total"] == pytest.approx(
        rep["jb_final"] + rep["jtheta_final"] + rep["jobs_final"], rel=1e-15)
    # water budget separation: P_w stage conserves to roundoff; total-water
    # change is carried by the qv diagonal dof alone
    wb = rep["water_budget"]
    assert wb["pw_stage_err_max"] < 1.0e-12
    assert wb["definition"] == "unweighted_vertical_level_sum"
    assert wb["dtw_qv_diag_mean_abs"] >= abs(wb["dtw_qv_diag_mean"])
    # 4-regime coverage honesty (reviewer caveat 3)
    assert rep["n_unclassified_ir105"] >= 0
    assert 0.0 <= rep["regime_coverage"] <= 1.0
    # conserving contract: mass-hydro diagonal controls are OFF; species
    # move only through partitions (channels touch qc/qi at t0)
    assert rep["cvt"]["n_controlled"]["qc"] == 0
    assert rep["cvt"]["n_controlled"]["qi"] == 0
    assert rep["cvt"]["n_controlled"]["qs"] == 0


def test_runner_cli_rejects_typo_flags():
    """A --conservng typo must fail loudly (argparse), never run silently
    as non-conserving; the light top-level imports keep this CI-safe."""
    import subprocess
    import sys as _sys
    from pathlib import Path
    script = str(Path(__file__).resolve().parents[1]
                 / "scripts" / "run_fulldomain_lc05.py")
    r = subprocess.run([_sys.executable, script, "out.json", "case",
                        "--conservng"], capture_output=True, text=True,
                       timeout=60)
    assert r.returncode != 0
    assert "conservng" in r.stderr


def test_runner_manifest_argv_lossless(monkeypatch, tmp_path):
    """The manifest must record the ACTUAL argv losslessly: a joined string
    cannot round-trip paths with spaces (Codex). The authoritative record
    is the argv array; the display command is shlex-quoted so it splits
    back to the exact argv."""
    import importlib.util
    import shlex
    import sys as _sys
    from pathlib import Path
    script = (Path(__file__).resolve().parents[1]
              / "scripts" / "run_fulldomain_lc05.py")
    spec = importlib.util.spec_from_file_location("rfl05", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)              # __main__ guard: nothing runs
    f1, f2 = tmp_path / "wrfin", tmp_path / "cal.json"
    f1.write_bytes(b"x")
    f2.write_bytes(b"{}")
    monkeypatch.setattr(mod, "WRFIN", str(f1))
    monkeypatch.setattr(mod, "CAL", str(f2))
    monkeypatch.setattr(_sys, "argv",
                        ["oracle/scripts/run_fulldomain_lc05.py",
                         "/tmp/out dir/v.json", "case root/x",
                         "--conserving"])
    monkeypatch.setattr(mod, "rttov_provenance", lambda: {"stub": True})
    man = mod.snapshot_provenance([], allow_dirty=True)
    argv = [_sys.executable, *_sys.argv]
    assert man["argv"] == argv                # lossless authoritative record
    assert shlex.split(man["command"]) == argv  # display form round-trips


def _load_runner():
    import importlib.util
    from pathlib import Path
    script = (Path(__file__).resolve().parents[1]
              / "scripts" / "run_fulldomain_lc05.py")
    spec = importlib.util.spec_from_file_location("rfl05x", script)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_runner_provenance_snapshot_and_drift(monkeypatch, tmp_path):
    """Reviewer P1: provenance must be SNAPSHOT before the analysis reads
    anything and re-checked at the end — a mid-run HEAD/input change makes
    the manifest describe code/inputs the run never used. The drift check
    reports every mismatch; a clean end state reports none."""
    mod = _load_runner()
    f1, f2 = tmp_path / "wrfin", tmp_path / "cal.json"
    f1.write_bytes(b"input-a")
    f2.write_bytes(b"{}")
    monkeypatch.setattr(mod, "WRFIN", str(f1))
    monkeypatch.setattr(mod, "CAL", str(f2))
    git_state = {"sha": "a" * 40, "dirty": ""}
    monkeypatch.setattr(mod, "_git", lambda *a: (
        git_state["sha"] if a[0] == "rev-parse" else git_state["dirty"]))
    monkeypatch.setattr(mod, "_git_bytes", lambda *a: (
        b"" if a[0] == "ls-files" else git_state["dirty"].encode()))

    monkeypatch.setattr(mod, "rttov_provenance", lambda: {"stub": True})
    man = mod.snapshot_provenance([])
    assert man["code_sha"] == "a" * 40 and man["code_dirty"] is False
    assert man["argv"][0] and isinstance(man["argv"], list)
    assert "cwd" in man and man["cwd"]
    # -O provenance: sys.flags works on every supported interpreter;
    # sys.orig_argv is recorded when the interpreter provides it (3.10+)
    assert man["python_optimize"] == 0
    assert "process_argv" in man
    assert mod.check_provenance_drift(man) == {}      # clean end state

    f1.write_bytes(b"input-CHANGED")                  # mid-run input drift
    drift = mod.check_provenance_drift(man)
    assert str(f1) in drift["inputs_changed"]
    f1.write_bytes(b"input-a")
    git_state["sha"] = "b" * 40                       # mid-run HEAD move
    drift = mod.check_provenance_drift(man)
    assert drift["code_sha"] == ("a" * 40, "b" * 40)
    git_state["sha"] = "a" * 40
    git_state["dirty"] = " M x.py"                    # tree went dirty
    drift = mod.check_provenance_drift(man)
    assert drift["code_dirty"] == (False, True)


def test_runner_dirty_content_drift_detected(monkeypatch, tmp_path):
    """Codex: a Boolean dirty flag misses drift WITHIN a dirty tree — the
    same True/True with an unchanged HEAD hides a mid-run edit to the
    uncommitted changes (and to untracked file content, which porcelain
    names but git diff does not carry)."""
    mod = _load_runner()
    f1, f2 = tmp_path / "wrfin", tmp_path / "cal.json"
    f1.write_bytes(b"x")
    f2.write_bytes(b"{}")
    monkeypatch.setattr(mod, "WRFIN", str(f1))
    monkeypatch.setattr(mod, "CAL", str(f2))
    git_state = {"sha": "a" * 40, "status": " M x.py", "diff": "-a\n+b"}
    monkeypatch.setattr(mod, "_git", lambda *a: (
        git_state["sha"] if a[0] == "rev-parse"
        else git_state["status"] if a[0] == "status"
        else git_state["diff"]))
    monkeypatch.setattr(mod, "_git_bytes", lambda *a: (
        b"" if a[0] == "ls-files"
        else git_state["status"].encode() if a[0] == "status"
        else git_state["diff"].encode()))

    monkeypatch.setattr(mod, "rttov_provenance", lambda: {"stub": True})
    man = mod.snapshot_provenance([], allow_dirty=True)
    assert man["code_dirty"] is True
    assert isinstance(man["code_dirty_sha256"], str)
    assert mod.check_provenance_drift(man) == {}

    git_state["diff"] = "-a\n+CHANGED"     # dirty stays True, SHA unchanged
    drift = mod.check_provenance_drift(man)
    assert "code_dirty_sha256" in drift and "code_dirty" not in drift

    # untracked content: porcelain only NAMES it — the digest must hash
    # the file bytes so a mid-run rewrite is visible
    repo = tmp_path / "repo"
    (repo / "oracle").mkdir(parents=True)
    (repo / "untracked.txt").write_bytes(b"v1")
    monkeypatch.setattr(mod, "_ORACLE", repo / "oracle")
    git_state["diff"] = "-a\n+b"
    git_state["status"] = "?? untracked.txt"
    man2 = mod.snapshot_provenance([], allow_dirty=True)
    assert mod.check_provenance_drift(man2) == {}
    (repo / "untracked.txt").write_bytes(b"v2-CHANGED")
    drift = mod.check_provenance_drift(man2)
    assert "code_dirty_sha256" in drift


def test_runner_untracked_special_filenames_hashed(monkeypatch, tmp_path):
    """Codex: git's default porcelain C-quotes special filenames
    ('?? "my file.txt"') — a literal-line parser looks up the quoted
    string, finds nothing, and silently skips the content hash. The -z
    porcelain form is unquoted/NUL-separated; rename entries carry an
    extra origin record that must be skipped."""
    mod = _load_runner()
    f1, f2 = tmp_path / "wrfin", tmp_path / "cal.json"
    f1.write_bytes(b"x")
    f2.write_bytes(b"{}")
    monkeypatch.setattr(mod, "WRFIN", str(f1))
    monkeypatch.setattr(mod, "CAL", str(f2))
    repo = tmp_path / "repo"
    (repo / "oracle").mkdir(parents=True)
    special = repo / "my file.txt"
    special.write_bytes(b"v1")
    monkeypatch.setattr(mod, "_ORACLE", repo / "oracle")

    monkeypatch.setattr(mod, "_git", lambda *a: "a" * 40)

    def fake_git_bytes(*a):
        if a[0] == "ls-files":
            return b""
        if a[0] == "status":
            # -z form: NUL-separated, UNQUOTED (the default porcelain would
            # C-quote the special name); rename entry with origin record
            return b"R  new.py\0old.py\0?? my file.txt\0"
        return b"-a\n+b"
    monkeypatch.setattr(mod, "_git_bytes", fake_git_bytes)

    monkeypatch.setattr(mod, "rttov_provenance", lambda: {"stub": True})
    man = mod.snapshot_provenance([], allow_dirty=True)
    assert mod.check_provenance_drift(man) == {}
    special.write_bytes(b"v2-CHANGED")            # content drift must be seen
    drift = mod.check_provenance_drift(man)
    assert "code_dirty_sha256" in drift, drift


def test_runner_git_failures_are_loud(monkeypatch, tmp_path):
    """_git must raise on nonzero return codes and reject malformed SHAs —
    a failed git call must never be recorded as empty-SHA/dirty=False."""
    mod = _load_runner()
    f1, f2 = tmp_path / "a", tmp_path / "b"
    f1.write_bytes(b"x")
    f2.write_bytes(b"y")
    monkeypatch.setattr(mod, "WRFIN", str(f1))
    monkeypatch.setattr(mod, "CAL", str(f2))

    class R:
        returncode = 128
        stdout, stderr = "", "fatal: not a git repository"
    monkeypatch.setattr(mod.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(RuntimeError, match="git"):
        mod._git("rev-parse", "HEAD")
    monkeypatch.setattr(mod, "_git",
                        lambda *a: "" if a[0] == "rev-parse" else "")
    monkeypatch.setattr(mod, "_git_bytes", lambda *a: b"")
    monkeypatch.setattr(mod, "rttov_provenance", lambda: {"stub": True})
    with pytest.raises(RuntimeError, match="SHA"):
        mod.snapshot_provenance([])


def test_runner_cli_rejects_prefix_abbreviation():
    """allow_abbrev=False: --conserv must NOT silently expand to
    --conserving (exit code exactly 2, flag named in stderr) — same for
    the typo case."""
    import subprocess
    import sys as _sys
    from pathlib import Path
    script = str(Path(__file__).resolve().parents[1]
                 / "scripts" / "run_fulldomain_lc05.py")
    for bad in ("--conserv", "--conservng"):
        r = subprocess.run([_sys.executable, script, "o.json", "c", bad],
                           capture_output=True, text=True, timeout=60)
        assert r.returncode == 2, bad
        assert bad in r.stderr, bad


def _mk_fixture_tree(root, exe):
    """Synthetic RTTOV fixture: run.sh naming the exe, coef prefix/name,
    hydrotable — the same resolution surface the real fixtures expose."""
    (root / "out").mkdir(parents=True)
    (root / "in").mkdir()
    (root / "out" / "run.sh").write_text(f"{exe} > log\n")
    coefdir = root / "coefs"
    coefdir.mkdir()
    (coefdir / "rt.dat").write_text("COEF-V1")
    (coefdir / "hydro.dat").write_text("HYDRO-V1")
    (root / "out" / "rttov_test.txt").write_text(
        f"  defn%coef_prefix = '{coefdir}'\n")
    (root / "in" / "coef.txt").write_text(
        "  defn%f_coef = 'rt.dat'\n  defn%f_hydrotable = 'hydro.dat'\n")


def test_rttov_provenance_assets_hashed_and_drift(monkeypatch, tmp_path):
    """Reviewer P1-1: the science actually consumes the RTTOV exe, rtcoef,
    hydrotable, and the whole fixture tree — all must be resolved once,
    hashed into the manifest (Merkle over the tree), env recorded, and
    re-checked at the end."""
    mod = _load_runner()
    exe = tmp_path / "rttov_test.exe"
    exe.write_bytes(b"EXE-V1")
    clear, cloud = tmp_path / "clear", tmp_path / "cloud"
    _mk_fixture_tree(clear, exe)
    _mk_fixture_tree(cloud, exe)
    monkeypatch.setenv("AD_RTTOV_HOME", str(tmp_path / "adr"))
    monkeypatch.delenv("KDM6_RTTOV_RUNTIME", raising=False)

    rt = mod.rttov_provenance(fixtures={"clear_fixture": clear,
                                        "cloud_fixture": cloud})
    assert rt["env"]["AD_RTTOV_HOME"] == str(tmp_path / "adr")
    assert rt["env"]["KDM6_RTTOV_RUNTIME"] is None
    for name in ("clear_fixture", "cloud_fixture"):
        e = rt[name]
        assert e["path"] and len(e["tree_sha256"]) == 64
        assert e["exe"]["path"] == str(exe) and len(e["exe"]["sha256"]) == 64
        assert e["coef"]["path"].endswith("rt.dat")
        assert e["hydrotable"]["path"].endswith("hydro.dat")

    # end-of-run recheck: exe/coef/hydrotable/tree content drift is caught
    ok = mod._rttov_recheck(rt)
    assert ok == {}
    exe.write_bytes(b"EXE-CHANGED")
    drift = mod._rttov_recheck(rt)
    assert any("exe" in k for k in drift), drift
    exe.write_bytes(b"EXE-V1")
    (clear / "in" / "extra.txt").write_text("new file")   # tree drift
    drift = mod._rttov_recheck(rt)
    assert any("clear_fixture" in k for k in drift), drift


def test_snapshot_requires_clean_tree_by_default(monkeypatch, tmp_path):
    """Reviewer P1-3: evidence runs enforce code_dirty=False — a dirty tree
    aborts the snapshot unless --allow-dirty is given explicitly."""
    mod = _load_runner()
    f1, f2 = tmp_path / "a", tmp_path / "b"
    f1.write_bytes(b"x")
    f2.write_bytes(b"y")
    monkeypatch.setattr(mod, "WRFIN", str(f1))
    monkeypatch.setattr(mod, "CAL", str(f2))
    monkeypatch.setattr(mod, "rttov_provenance", lambda: {"stub": True})
    monkeypatch.setattr(mod, "_git", lambda *a: (
        "a" * 40 if a[0] == "rev-parse" else " M x.py"))
    monkeypatch.setattr(mod, "_git_bytes", lambda *a: b" M x.py\0")
    with pytest.raises(RuntimeError, match="dirty"):
        mod.snapshot_provenance([])
    man = mod.snapshot_provenance([], allow_dirty=True)
    assert man["code_dirty"] is True


def test_snapshot_rejects_index_hint_bypass(monkeypatch, tmp_path):
    """Reviewer P1-3: assume-unchanged / skip-worktree entries make a
    modified file invisible to status/diff — detect via ls-files -v and
    reject the snapshot."""
    mod = _load_runner()
    f1, f2 = tmp_path / "a", tmp_path / "b"
    f1.write_bytes(b"x")
    f2.write_bytes(b"y")
    monkeypatch.setattr(mod, "WRFIN", str(f1))
    monkeypatch.setattr(mod, "CAL", str(f2))
    monkeypatch.setattr(mod, "rttov_provenance", lambda: {"stub": True})
    for tag in ("h code.py", "S code.py"):
        monkeypatch.setattr(mod, "_git", lambda *a: "a" * 40)
        monkeypatch.setattr(mod, "_git_bytes", lambda *a, _t=tag: (
            _t.encode() if a[0] == "ls-files" else b""))
        with pytest.raises(RuntimeError, match="assume-unchanged|skip-worktree"):
            mod.snapshot_provenance([])


def test_missing_input_is_drift_not_crash(monkeypatch, tmp_path):
    """Reviewer P2: an input deleted mid-run must surface as inputs_changed
    drift (so the rejection manifest is still written), not abort with
    FileNotFoundError."""
    mod = _load_runner()
    f1, f2 = tmp_path / "a", tmp_path / "b"
    f1.write_bytes(b"x")
    f2.write_bytes(b"y")
    monkeypatch.setattr(mod, "WRFIN", str(f1))
    monkeypatch.setattr(mod, "CAL", str(f2))
    monkeypatch.setattr(mod, "rttov_provenance", lambda: {"stub": True})
    monkeypatch.setattr(mod, "_git", lambda *a: (
        "a" * 40 if a[0] == "rev-parse" else ""))
    monkeypatch.setattr(mod, "_git_bytes", lambda *a: b"")
    man = mod.snapshot_provenance([])
    f1.unlink()
    drift = mod.check_provenance_drift(man)
    assert str(f1) in drift["inputs_changed"]


def test_output_paths_must_be_disjoint_from_inputs(tmp_path):
    """Reviewer P2: out/case paths equal to, inside, or containing an input
    path would let the run overwrite its own provenance inputs."""
    mod = _load_runner()
    inp = tmp_path / "inputs" / "wrfin"
    inp.parent.mkdir()
    inp.write_bytes(b"x")
    mod._assert_disjoint([str(tmp_path / "out" / "v.json")], [str(inp)])
    mod._assert_disjoint([str(inp.parent / "sibling")], [str(inp)])
    for bad in (str(inp), str(tmp_path / "inputs"), str(tmp_path)):
        with pytest.raises(ValueError, match="disjoint"):
            mod._assert_disjoint([bad], [str(inp)])


def test_finalize_artifact_quarantines_rejected(tmp_path):
    """Reviewer P1-2: a drift/gate-rejected run must NOT leave files under
    the canonical approved names — gates carry provenance_stable, accepted
    is recomputed, and every artifact lands under *.rejected."""
    mod = _load_runner()
    staging = tmp_path / "v.json.fields.npz.staging"
    staging.write_bytes(b"NPZ")
    out = str(tmp_path / "v.json")
    rep = dict(gates={"j_descended": True, "accepted": True}, wall_s=1.0)
    man = dict(inputs={})

    ok = mod.finalize_artifact(rep, man, {}, out, str(staging))
    assert ok is True
    assert rep["gates"]["provenance_stable"] is True
    assert (tmp_path / "v.json").exists()
    assert (tmp_path / "v.json.fields.npz").exists()
    assert (tmp_path / "v.json.manifest.json").exists()

    staging.write_bytes(b"NPZ2")
    out2 = str(tmp_path / "w.json")
    rep2 = dict(gates={"j_descended": True, "accepted": True}, wall_s=1.0)
    drift = dict(code_sha=("a" * 40, "b" * 40))
    ok = mod.finalize_artifact(rep2, dict(inputs={}), drift, out2,
                               str(staging))
    assert ok is False
    assert rep2["gates"]["provenance_stable"] is False
    assert rep2["gates"]["accepted"] is False
    assert not (tmp_path / "w.json").exists()          # no approved-looking name
    assert (tmp_path / "w.json.rejected").exists()
    assert (tmp_path / "w.json.fields.npz.rejected").exists()
    assert (tmp_path / "w.json.manifest.json.rejected").exists()
    rejected = json.loads((tmp_path / "w.json.rejected").read_text())
    assert rejected["gates"]["accepted"] is False


def test_runner_refuses_existing_outputs(tmp_path):
    """Codex: a rejected rerun over the same OUT_JSON would leave the
    PREVIOUS run's approved artifacts at the canonical names next to the
    new *.rejected files — an archive step would collect stale evidence.
    Evidence artifacts are immutable: the runner fails fast BEFORE the
    (hour-long) run if ANY candidate output name already exists."""
    mod = _load_runner()
    out = str(tmp_path / "v.json")
    mod._assert_fresh_outputs(out)                     # clean dir: fine
    for stale in ("", ".rejected", ".fields.npz", ".fields.npz.rejected",
                  ".manifest.json", ".manifest.json.rejected",
                  ".fields.npz.staging"):
        p = tmp_path / ("v.json" + stale)
        p.write_bytes(b"old")
        with pytest.raises(FileExistsError, match="already exists"):
            mod._assert_fresh_outputs(out)
        p.unlink()
    mod._assert_fresh_outputs(out)


def test_finalize_artifact_never_overwrites(tmp_path):
    """Codex TOCTOU: paths created AFTER the fresh-outputs check (hour-long
    run window, or a concurrent runner passing the same check) must not be
    silently replaced — final placement is exclusive-create (open 'x') and
    atomic no-replace (link+unlink instead of rename)."""
    mod = _load_runner()
    staging = tmp_path / "x.json.fields.npz.staging"
    staging.write_bytes(b"NEW")
    out = str(tmp_path / "x.json")
    rep = dict(gates={"g": True, "accepted": True}, wall_s=1.0)

    (tmp_path / "x.json.fields.npz").write_bytes(b"OLD")   # appeared mid-run
    with pytest.raises(FileExistsError):
        mod.finalize_artifact(rep, dict(inputs={}), {}, out, str(staging))
    assert staging.exists()                                # staging preserved
    assert (tmp_path / "x.json.fields.npz").read_bytes() == b"OLD"
    (tmp_path / "x.json.fields.npz").unlink()

    (tmp_path / "x.json").write_text("OLD-JSON")           # json appeared
    rep2 = dict(gates={"g": True, "accepted": True}, wall_s=1.0)
    with pytest.raises(FileExistsError):
        mod.finalize_artifact(rep2, dict(inputs={}), {}, out, str(staging))
    assert (tmp_path / "x.json").read_text() == "OLD-JSON"


def test_finalize_collision_rollback_no_partials(tmp_path):
    """Codex: a LATE json/manifest collision must not leave a partial
    artifact set nor consume the retry staging — placement is
    all-or-nothing (own files rolled back, staging preserved, atomic
    npz link last)."""
    mod = _load_runner()
    staging = tmp_path / "y.json.fields.npz.staging"
    out = str(tmp_path / "y.json")

    def fresh_rep():
        return dict(gates={"g": True, "accepted": True}, wall_s=1.0)

    # manifest collision: the json we created is rolled back, npz unplaced
    staging.write_bytes(b"NEW")
    (tmp_path / "y.json.manifest.json").write_text("OLD-MAN")
    with pytest.raises(FileExistsError):
        mod.finalize_artifact(fresh_rep(), dict(inputs={}), {}, out,
                              str(staging))
    assert staging.exists()
    assert not (tmp_path / "y.json").exists()          # rolled back
    assert not (tmp_path / "y.json.fields.npz").exists()
    assert (tmp_path / "y.json.manifest.json").read_text() == "OLD-MAN"
    (tmp_path / "y.json.manifest.json").unlink()

    # npz collision: json AND manifest rolled back, staging preserved
    (tmp_path / "y.json.fields.npz").write_bytes(b"OLD-NPZ")
    with pytest.raises(FileExistsError):
        mod.finalize_artifact(fresh_rep(), dict(inputs={}), {}, out,
                              str(staging))
    assert staging.exists()
    assert not (tmp_path / "y.json").exists()
    assert not (tmp_path / "y.json.manifest.json").exists()
    assert (tmp_path / "y.json.fields.npz").read_bytes() == b"OLD-NPZ"
    (tmp_path / "y.json.fields.npz").unlink()

    # json collision: staging preserved, npz unplaced (no partials)
    (tmp_path / "y.json").write_text("OLD-JSON")
    with pytest.raises(FileExistsError):
        mod.finalize_artifact(fresh_rep(), dict(inputs={}), {}, out,
                              str(staging))
    assert staging.exists()
    assert not (tmp_path / "y.json.fields.npz").exists()
    assert not (tmp_path / "y.json.manifest.json").exists()
    (tmp_path / "y.json").unlink()

    # clean retry after any collision succeeds with the SAME staging
    ok = mod.finalize_artifact(fresh_rep(), dict(inputs={}), {}, out,
                               str(staging))
    assert ok is True and not staging.exists()
    assert (tmp_path / "y.json.fields.npz").read_bytes() == b"NEW"


def test_rollback_only_removes_owned_files(tmp_path):
    """Codex: rollback-by-path can delete ANOTHER process's file if ours
    was swapped in the window, and a vanished file masks the original
    collision with FileNotFoundError. Rollback must verify ownership —
    the final must still be the SAME inode as the owned temp it was
    linked from — and never raise."""
    import os
    mod = _load_runner()
    tmp = tmp_path / "t1"
    tmp.write_bytes(b"X")
    final = tmp_path / "f1"
    os.link(tmp, final)                                # ours: same inode
    other_tmp = tmp_path / "t2"
    other_tmp.write_bytes(b"Y")
    foreign = tmp_path / "f2"
    foreign.write_bytes(b"THEIRS")                     # NOT ours (swapped)
    gone_tmp = tmp_path / "t3"
    gone_tmp.write_bytes(b"Z")
    mod._rollback_linked([(str(tmp), str(final)),
                          (str(other_tmp), str(foreign)),
                          (str(gone_tmp), str(tmp_path / "missing"))])
    assert not final.exists()                          # owned -> removed
    assert foreign.read_bytes() == b"THEIRS"           # foreign -> untouched
