"""Same-entry density in one fp64 KDM-to-optical transition, not a DA window."""
from pathlib import Path
import numpy as np
import pytest
import torch

from kdm6.state import State, Forcing
from kdm6.runtime import _kdm6_pure, make_parameters
from kdm6.sed_conservative import CONSERVATIVE_SED_FNS
from kdm6.obs.model_profile_builder import RttovProfileConfig, model_to_rttov_tensors


def native():
    p = Path(__file__).resolve().parents[2] / 'harness/evidence/C5_supported_profile_2026-10-03.npz'
    with np.load(p) as a:
        s = State(*(torch.tensor(x, dtype=torch.float64)[None, :] for x in a['native_state_bottom_up']))
        f = Forcing(*(torch.tensor(x, dtype=torch.float64)[None, :] for x in a['native_forcing_bottom_up']))
    return s, f


def step(s, f):
    return _kdm6_pure(s, f, make_parameters(), dt=20., xland=torch.tensor([2.]),
                      ncmin_land=10., ncmin_sea=10., dry_number=True,
                      normalize_ice_handoff=True, sed_substep_fns=CONSERVATIVE_SED_FNS)


def column(x):
    return type(x)(*(v[0].flip(0) for v in x))


def profile(s, f, entry):
    cfg = RttovProfileConfig(2, 'mixing_ratio_kgkg_dry', cloud=True, dry_number=True)
    return model_to_rttov_tensors(column(s), column(f), cfg, xland=torch.tensor([2.]),
                                  ncmin_land=10., ncmin_sea=10., entry_qv=entry[0].flip(0))


def test_native_transition_uses_entry_not_output_humidity():
    s, f = native()
    y = step(s, f)
    assert not torch.equal(y.qv, s.qv)
    p = profile(y, f, s.qv)
    rho = (f.rho / (1 + s.qv))[0].flip(0)
    expected = 1000 * rho * y.qc[0].flip(0)
    assert torch.equal(p.clw, expected)
    wrong = 1000 * (f.rho / (1 + y.qv))[0].flip(0) * y.qc[0].flip(0)
    assert torch.any(expected != wrong)
    fixed = RttovProfileConfig(2, 'mixing_ratio_kgkg_dry', cloud=True, rho_d=rho, dry_number=True)
    q = model_to_rttov_tensors(column(y), column(f), fixed, xland=torch.tensor([2.]),
                              ncmin_land=10., ncmin_sea=10.)
    for name in ('t_lay', 'q_lay', 'clw', 'ciw', 'deff_liq', 'deff_ice', 'cfrac'):
        assert torch.equal(getattr(p, name), getattr(q, name))


def test_native_coupled_qv_jvp_vjp_and_independent_fd():
    s, f = native()
    def chain(qv):
        p = profile(step(s._replace(qv=qv), f), f, qv)
        return p.t_lay, p.q_lay, p.clw, p.ciw, p.deff_liq, p.deff_ice
    direction = .01 * s.qv
    base, jv = torch.func.jvp(chain, (s.qv,), (direction,))
    h = 1e-4
    fd = tuple((a-b)/(2*h) for a, b in zip(chain(s.qv+h*direction), chain(s.qv-h*direction)))
    for a, b in zip(jv, fd):
        assert torch.isfinite(a).all() and torch.isfinite(b).all()
        scale = torch.maximum(a.abs().max(), b.abs().max()).clamp_min(1e-30)
        assert (a-b).abs().max()/scale < 1e-5
    seeds = tuple(torch.linspace(-.7, .8, len(x), dtype=x.dtype) for x in base)
    _, pullback = torch.func.vjp(chain, s.qv)
    adj, = pullback(seeds)
    lhs = sum((a*b).sum() for a, b in zip(jv, seeds))
    torch.testing.assert_close(lhs, (direction*adj).sum(), rtol=1e-12, atol=0.)
    assert torch.count_nonzero(jv[2]) > 0


def test_entry_density_requires_an_unambiguous_dry_cloud_contract():
    s, f = native()
    c, fc = column(s), column(f)
    cfg = RttovProfileConfig(2, 'mixing_ratio_kgkg_dry', cloud=True, dry_number=True)
    rho = fc.rho / (1+c.qv)
    with pytest.raises(ValueError, match='not both'):
        model_to_rttov_tensors(c, fc, cfg._replace(rho_d=rho), entry_qv=c.qv)
    with pytest.raises(ValueError, match='dry_number=True'):
        model_to_rttov_tensors(c, fc, cfg._replace(dry_number=False), entry_qv=c.qv)
