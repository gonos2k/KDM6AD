"""Bounded V1/V2/V4/N1 checks for the opt-in process sensitivity trace."""
from __future__ import annotations

import torch

from kdm6.state import State, Forcing
from kdm6.runtime import kdm6_step
from kdm6.sensitivity_diagnostics import SensitivityTrace, compare_dt_refinement, diagnose_step


def _t2(a, b, rg=False):
    t = torch.tensor([[a, b]], dtype=torch.float64)
    return t.requires_grad_(rg)


def _state(rg=False):
    return State(
        th=_t2(296.8, 282.4, rg), qv=_t2(1.40e-2, 2.0e-3, rg),
        qc=_t2(1.0e-3, 5.0e-4, rg), qr=_t2(1.0e-4, 1.0e-5, rg),
        qi=_t2(2.0e-5, 1.0e-6, rg), qs=_t2(5.0e-5, 5.0e-5, rg),
        qg=_t2(1.0e-5, 1.0e-5, rg), nccn=_t2(1.0e9, 1.0e9, rg),
        nc=_t2(1.0e8, 1.0e8, rg), ni=_t2(1.0e8, 1.0e8, rg),
        nr=_t2(1.0e4, 1.0e3, rg), bg=_t2(1.0e-8, 1.0e-8, rg),
    )


def _forcing():
    return Forcing(rho=_t2(1.089, 0.9567), pii=_t2(0.9704, 0.9031),
                   p=_t2(9.0e4, 7.0e4), delz=_t2(500.0, 500.0))


def _direction():
    x = _state()
    return State(*(torch.full_like(v, 1.0e-6) if n in ("qc", "qr", "qi")
                   else torch.zeros_like(v) for n, v in zip(State._fields, x)))


def test_opt_in_trace_preserves_forward_and_records_applied_boundaries():
    s, f = _state(), _forcing()
    plain, hp = kdm6_step(s, f, dt=20.0, value_only=True)
    hp.close()
    trace = SensitivityTrace()
    traced, ht = kdm6_step(s, f, dt=20.0, value_only=True, diagnostic_trace=trace)
    ht.close()
    for name in State._fields:
        assert torch.equal(getattr(plain, name), getattr(traced, name)), name
    names = [r.name for r in trace.records]
    assert {"d1_melt", "d2_d4_freeze", "warm", "cold", "warm_limited",
            "cold_limited", "d5_limited", "state_update", "satadj",
            "cleanup", "dsd_limiter"}.issubset(names)
    warm = trace.by_name("warm")[0]
    assert warm.metadata["upstream_to_cold"] == "warm.prevp"
    assert warm.rate_summary()["praut"]["finite"]
    assert "qc" in trace.by_name("state_update")[0].applied_delta_summary()
    assert trace.by_name("warm_limited")[0].applied_delta_summary() == {}


def test_opt_in_trace_preserves_jvp_and_vjp_products_bitwise():
    s, f, v = _state(True), _forcing(), _direction()
    cov = State(*(torch.ones_like(x) for x in s))
    plain, hp = kdm6_step(s, f, dt=20.0)
    traced_state = _state(True)
    trace = SensitivityTrace()
    traced, ht = kdm6_step(traced_state, f, dt=20.0, diagnostic_trace=trace)
    j_plain, j_trace = hp.jvp(v), ht.jvp(v)
    a_plain, a_trace = hp.vjp(cov, retain_graph=True), ht.vjp(cov, retain_graph=True)
    for name in State._fields:
        assert torch.equal(getattr(plain, name), getattr(traced, name)), name
        assert torch.equal(getattr(j_plain, name), getattr(j_trace, name)), f"jvp[{name}]"
        assert torch.equal(getattr(a_plain, name), getattr(a_trace, name)), f"vjp[{name}]"
    hp.close(); ht.close()


def test_process_trace_fd_and_duality_report_are_local_and_explicit():
    s, f, v = _state(), _forcing(), _direction()
    cov = State(*(torch.ones_like(x) for x in s))
    report = diagnose_step(s, f, v, dt=20.0, epsilon=1.0e-4, covector=cov)
    assert "0:warm" in report.stages
    assert "0:warm_limited" in report.stages
    for rate in ("praut", "pracw", "prevp"):
        check = report.stage_fd["0:warm"][rate]
        assert abs(check["fd_sum"]) > 1.0e-14
        assert check["abs_error"] < abs(check["fd_sum"]) * 1.0e-4
        assert check["finite"]
        scale = torch.tensor(check["fd_values"]).abs().max().item()
        assert check["max_abs_error"] < scale * 1.0e-4
    assert "0:warm_limited" not in report.applied_fd
    assert report.branch_comparison["0:warm"]["counts_unchanged"]
    assert report.branch_comparison["0:warm"]["masks_equal"]
    assert report.applied_fd["0:d2_d4_freeze"]["qc"]["abs_error"] < 1.0e-8
    assert report.causal_links["warm.prevp->state_update.qv"]["structurally_connected"]
    assert report.causal_links["warm.prevp->state_update.qv"]["max_abs_derivative"] > 1.0
    assert report.subcycles and report.subcycles[0]["mstep_main"] >= 1
    assert report.duality["abs_error"] < 1.0e-9
    for name in State._fields:
        scale = max(report.final_jvp_max_abs[name], report.final_fd_max_abs[name], 1.0e-30)
        assert report.final_fd_abs_error[name] / scale < 1.0e-3
    assert report.water["measure"] == "rho * delz * (qv+qc+qr+qi+qs+qg)"
    assert report.water["ad_fd_abs_error"] < 1.0e-8
    assert report.water["d2_d4_freeze"]["max_abs_value"] < 1.0e-7


def test_selected_rate_fd_is_stable_over_valid_epsilon_window():
    s, f, v = _state(), _forcing(), _direction()
    checks = []
    for eps in (1.0e-3, 1.0e-4, 1.0e-5):
        report = diagnose_step(s, f, v, dt=20.0, epsilon=eps)
        check = report.stage_fd["0:warm"]["praut"]
        checks.append(check)
        assert abs(check["fd_sum"]) > 1.0e-14
        assert check["abs_error"] < abs(check["fd_sum"]) * 1.0e-3
    assert max(abs(x["fd_sum"] - checks[1]["fd_sum"]) for x in checks) < 1.0e-9


def test_dt_refinement_reports_state_and_tangent_separately():
    report = compare_dt_refinement(_state(), _forcing(), _direction(), dt=20.0)
    assert report["interval"] == 20.0
    assert len(report["coarse_signature"]) > 0
    assert len(report["refined_signature"]) > 0
    assert report["coarse_subcycles"][0]["mstep_main"] >= 1
    assert report["open"]
    assert set(report["state_max_abs_difference"]) == set(State._fields)


def test_topology_record_distinguishes_equal_counts_in_different_cells():
    """A moved phase cell and swapped column subcycles must remain distinguishable."""
    traces = [SensitivityTrace(), SensitivityTrace()]
    for trace, mask, counts in zip(
        traces, ([[True, False]], [[False, True]]), ([1, 2], [2, 1])
    ):
        trace.record_stage("phase", 0, 20.0, None, None,
                           branch=torch.tensor(mask))
        trace.record_subcycle(0, mstep_main=2, mstep_ice=1,
                              main_by_column=torch.tensor(counts),
                              ice_by_column=torch.tensor([1, 1]))
    a, b = [trace.records[0].branch_summary() for trace in traces]
    assert a["active_count"] == b["active_count"] == 1
    assert a["mask_sha256"] != b["mask_sha256"]
    assert traces[0].subcycles != traces[1].subcycles


def test_local_directional_evidence_does_not_hide_opposing_cells():
    from kdm6.sensitivity_diagnostics import _directional_values, _cell_fd_comparison

    leaves = _state(True)
    direction = State(*(torch.ones_like(x) if n == "qc" else torch.zeros_like(x)
                        for n, x in zip(State._fields, leaves)))
    x = leaves.qc[0, 0]
    values = torch.stack((x, -x))
    ad = _directional_values(values, leaves, direction)
    expected = torch.tensor([1.0, -1.0], dtype=torch.float64)
    assert torch.equal(ad, expected)
    # A broken derivative returning two zeros would pass the old sum check.
    broken = _cell_fd_comparison(torch.zeros_like(ad), expected)
    assert broken["abs_error"] == 0.0
    assert broken["max_abs_error"] == 1.0
    assert broken["max_error_cell"] == [0]
