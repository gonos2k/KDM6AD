"""Opt-in fixed observation-error contract at the all-sky worker seam."""
from __future__ import annotations

import math

import numpy as np
import torch

import kdm6.obs.rttov_case_writer as case_writer
from kdm6.obs.allsky_shard import sharded_allsky
from kdm6.obs.obs_loss import compute_obs_loss
from kdm6.rttov_bridge import freeze_dry_air_density
from kdm6.state import Forcing, State

F64 = {"dtype": torch.float64}
CHANNELS = (8, 9, 10)
NLEV = 3


class _SynchronousPool:
    def __init__(self):
        self.jobs = []

    def map(self, function, jobs):
        self.jobs.extend(jobs)
        return [function(job) for job in jobs]


def _inputs():
    def rows(values):
        return torch.tensor(values, **F64)

    state = State(
        th=rows([[288.0, 281.0, 274.0], [286.0, 279.0, 272.0],
                 [284.0, 277.0, 270.0]]),
        qv=rows([[0.020, 0.014, 0.008], [0.018, 0.013, 0.007],
                 [0.016, 0.012, 0.006]]),
        qc=torch.full((3, NLEV), 1.0e-3, **F64),
        qr=torch.full((3, NLEV), 1.0e-4, **F64),
        qi=torch.full((3, NLEV), 1.0e-4, **F64),
        qs=torch.full((3, NLEV), 1.0e-4, **F64),
        qg=torch.zeros((3, NLEV), **F64),
        nccn=torch.full((3, NLEV), 1.0e8, **F64),
        nc=torch.full((3, NLEV), 1.0e8, **F64),
        ni=torch.full((3, NLEV), 1.0e6, **F64),
        nr=torch.full((3, NLEV), 1.0e4, **F64),
        bg=torch.zeros((3, NLEV), **F64))
    background = state._replace(qv=state.qv * 0.97)
    pressure = rows([[100000.0, 80000.0, 60000.0]] * 3)
    forcing = Forcing(
        rho=rows([[1.0, 0.8, 0.6]] * 3),
        pii=(pressure / 100000.0) ** 0.286,
        p=pressure, delz=rows([[400.0, 500.0, 600.0]] * 3))
    rho_d = freeze_dry_air_density(background, forcing)
    rttov_cfg = {
        "dry_number": False,
        "coef_id": "analytic-KMA",
        "channels": CHANNELS,
        "rho_d": rho_d,
        "p_lay": np.array([600.0, 800.0, 1000.0]),
        "p_half": np.array([550.0, 700.0, 900.0, 1100.0]),
        "t_ref": np.array([250.0, 265.0, 280.0]),
        "q_ref": np.array([5.0, 200.0, 4000.0]),
        "t_blend_octaves": 0.0,
        "q_blend_octaves": 0.0,
    }
    return state, forcing, torch.tensor([2.0, 1.0, 2.0], **F64), rttov_cfg


def _install_analytic_rttov(monkeypatch):
    """Mock only the RTTOV boundary; return BT and exact matching first-order K."""
    tw = np.array([0.25, 0.50, 0.75], dtype=np.float64)
    qw = np.array([0.60, 0.30, 0.10], dtype=np.float64)
    tscale = np.array([0.015, 0.020, 0.025], dtype=np.float64)
    qscale = np.array([1.0e-4, 1.5e-4, 2.0e-4], dtype=np.float64)

    def factory(case_dir, **kwargs):
        def run_k(rin):
            t = np.asarray(rin.profile["T"], dtype=np.float64)
            q = np.asarray(rin.profile["Q"], dtype=np.float64)
            bt = (245.0 + (t * tw[None, :]).sum(axis=1, keepdims=True)
                  * tscale[None, :]
                  + (q * qw[None, :]).sum(axis=1, keepdims=True)
                  * qscale[None, :])
            nprof, nlay = t.shape
            kt = np.broadcast_to(tscale[None, :, None]
                                 * tw[None, None, :], (nprof, 3, nlay)).copy()
            kq = np.broadcast_to(qscale[None, :, None]
                                 * qw[None, None, :], (nprof, 3, nlay)).copy()
            zeros = np.zeros((nprof, 3, nlay), dtype=np.float64)
            return bt, {"T": kt, "Q": kq, "HYDRO6": zeros.copy(),
                        "HYDRO7": zeros.copy(), "HYDRO_DEFF6": zeros.copy(),
                        "HYDRO_DEFF7": zeros.copy()}, np.zeros((nprof, 3))

        run_k.solar_channels = ()
        run_k.bt_coordinate = "kma_v3_0"
        return run_k

    monkeypatch.setattr(case_writer, "make_live_run_k", factory)


def _evaluate(state, forcing, xland, rttov_cfg, target, mask, cidx, root,
              pool, *, sigma=None, bias=None, grad=True):
    return sharded_allsky(
        state, forcing, cidx, target, mask, xland, rttov_cfg, str(root),
        n_workers=2, grad=grad, huber_delta=1.0, pool=pool,
        **({} if sigma is None else {"obs_sigma": sigma}),
        **({} if bias is None else {"obs_bias": bias}))


def test_fixed_errors_route_by_requested_column_and_match_vjp_fd(
        monkeypatch, tmp_path):
    _install_analytic_rttov(monkeypatch)
    state, forcing, xland, rttov_cfg = _inputs()
    cidx = torch.tensor([2, 0], dtype=torch.int64)  # nontrivial output order
    base_pool = _SynchronousPool()
    base = _evaluate(state, forcing, xland, rttov_cfg,
                     torch.zeros((3, 3), **F64), torch.ones((3, 3), **F64),
                     cidx, tmp_path / "base", base_pool, grad=False)

    sigma = torch.tensor([1.5, 2.0, 4.0], **F64)
    bias = torch.tensor([[0.1, -0.2, 0.3], [0.4, 0.5, -0.6],
                         [-0.7, 0.8, 0.9]], **F64)
    target = torch.zeros((3, 3), **F64)
    target[cidx] = base["bt"] + torch.tensor([[0.3, 2.0, 4.0],
                                              [-0.5, 3.0, -2.0]], **F64)
    target[2, 2] = float("nan")  # masked NaN is safe and contributes zero
    mask = torch.tensor([[1.0, 1.0, 1.0], [1.0, 1.0, 1.0],
                         [1.0, 0.0, 0.0]], **F64)
    pool = _SynchronousPool()

    def run(trial_state, label):
        return _evaluate(trial_state, forcing, xland, rttov_cfg,
                         target, mask, cidx, tmp_path / label, pool,
                         sigma=sigma, bias=bias, grad=True)

    result = run(state, "fixed_base")
    assert result["bt"].shape == (2, 3)
    assert torch.equal(result["rq"], torch.zeros((2, 3), **F64))
    assert len(pool.jobs) == 2
    # Each selected column is placed in its own worker job, preserving cidx order.
    assert [job["worker_id"] for job in pool.jobs] == [0, 1]
    assert [job["obs_bias"].shape for job in pool.jobs] == [(1, 3), (1, 3)]
    torch.testing.assert_close(
        torch.as_tensor(result["j"], **F64),
        sum(compute_obs_loss(
            result["bt"][i:i + 1],
            {"bt": target[cidx[i]:cidx[i] + 1],
             "bias": bias[cidx[i]:cidx[i] + 1]},
            mask[cidx[i]:cidx[i] + 1], sigma, delta=1.0)
            for i in range(cidx.numel())), rtol=0.0, atol=1e-12)

    direction = torch.zeros_like(state.qv)
    direction[cidx] = state.qv[cidx] * 0.05
    vjp = float((result["adj"][1] * direction[cidx]).sum())
    h = 1.0e-3
    costs = []
    for sign, name in ((1.0, "fixed_plus"), (-1.0, "fixed_minus")):
        trial = state._replace(qv=state.qv + sign * h * direction)
        costs.append(float(run(trial, name)["j"]))
    fd = (costs[0] - costs[1]) / (2.0 * h)
    assert math.isfinite(vjp) and math.isfinite(fd)
    assert math.isclose(vjp, fd, rel_tol=3e-5, abs_tol=1e-9)


def test_legacy_worker_payload_omits_fixed_error_keys(monkeypatch, tmp_path):
    _install_analytic_rttov(monkeypatch)
    state, forcing, xland, rttov_cfg = _inputs()
    cidx = torch.tensor([2, 0], dtype=torch.int64)
    pool = _SynchronousPool()
    _evaluate(state, forcing, xland, rttov_cfg,
              torch.zeros((3, 3), **F64), torch.ones((3, 3), **F64),
              cidx, tmp_path / "legacy", pool, grad=False)
    assert pool.jobs
    assert all("obs_sigma" not in job and "obs_bias" not in job
               for job in pool.jobs)
