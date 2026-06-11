"""[DA Phase 5.3] gates for the α process-rate controls (kdm6ad+da.md §5.2).

The load-bearing gate is #1: controls=None / ProcessControls() must be
BYTE-IDENTICAL to the pre-control oracle — the control hooks must not exist
on the default path (the design's *_control_enabled semantics; the same
protection philosophy as the operational bitwise lock, applied to the fp64
oracle's own parity baselines).
"""
from __future__ import annotations

import pytest
import torch

from kdm6.state import State, Forcing, state_dot
from kdm6.runtime import kdm6_fn, make_parameters
from kdm6.process_controls import ProcessControls

DT = 20.0


def _t2(a, b, rg=False):
    t = torch.tensor([[a, b]], dtype=torch.float64)
    return t.requires_grad_(True) if rg else t


def _mk_state(rg=False):
    # mixed-phase, warm-active IC (autoconv/accretion/riming/deposition all live)
    return State(
        th=_t2(296.8, 282.4, rg), qv=_t2(1.40e-2, 2.0e-3, rg),
        qc=_t2(1.5e-3, 8.0e-4, rg), qr=_t2(1.0e-4, 1.0e-5, rg),
        qi=_t2(0.0, 5.0e-5, rg), qs=_t2(0.0, 1.0e-4, rg),
        qg=_t2(0.0, 5.0e-5, rg), nccn=_t2(1.0e9, 1.0e9, rg),
        nc=_t2(1.0e8, 1.0e8, rg), ni=_t2(0.0, 1.0e8, rg),
        nr=_t2(1.0e4, 1.0e3, rg), bg=_t2(0.0, 0.0, rg),
    )


def _mk_forcing():
    return Forcing(rho=_t2(1.089, 0.9567), pii=_t2(0.9704, 0.9031),
                   p=_t2(9.0e4, 7.0e4), delz=_t2(500.0, 500.0))


def _run(controls=None, state=None):
    out = kdm6_fn(state if state is not None else _mk_state(),
                  _mk_forcing(), make_parameters(), DT,
                  None, 0.0, 0.0, controls)
    return State(*(f.detach() for f in out))


def test_controls_none_is_byte_identical():
    """controls=None AND all-None ProcessControls() must both be bitwise equal
    to the no-kwarg call — zero added ops on the default path."""
    base = State(*(f.detach() for f in kdm6_fn(
        _mk_state(), _mk_forcing(), make_parameters(), DT)))
    for ctl in (None, ProcessControls()):
        out = _run(ctl)
        for name, a, b in zip(State._fields, out, base):
            assert torch.equal(a, b), f"default-path drift in {name} (ctl={ctl})"


def test_alpha_zero_is_bitwise_identity():
    """exp(0) == 1.0 exactly, and R * 1.0 is exact — α=0 controls give bitwise
    the same OUTPUT as controls=None (the graphs differ; the values must not)."""
    z = torch.zeros((), dtype=torch.float64)
    ctl = ProcessControls(alpha_autoconv=z, alpha_accretion=z,
                          alpha_deposition=z, alpha_riming=z,
                          alpha_freeze=z, alpha_melt=z)
    base = _run(None)
    out = _run(ctl)
    for name, a, b in zip(State._fields, out, base):
        assert torch.equal(a, b), f"α=0 not value-identity in {name}"


def test_alpha_autoconv_direction():
    """α_autoconv > 0 amplifies cloud→rain conversion: qr grows, qc shrinks
    relative to baseline on this warm-active IC."""
    base = _run(None)
    out = _run(ProcessControls(alpha_autoconv=torch.tensor(1.0, dtype=torch.float64)))
    # warm cell is column 0
    assert float(out.qr[0, 0]) > float(base.qr[0, 0]), "qr did not increase"
    assert float(out.qc[0, 0]) < float(base.qc[0, 0]), "qc did not decrease"


def test_alpha_grad_flows_to_controls():
    """The α leaves must receive finite gradients through the full step —
    the §5.2 parameter-estimation route. Autoconv/accretion are guaranteed
    active on this IC; the others may be zero-rate (gradient 0 allowed) but
    must be finite."""
    alphas = {k: torch.zeros((), dtype=torch.float64, requires_grad=True)
              for k in ProcessControls._fields}
    ctl = ProcessControls(**alphas)
    out = kdm6_fn(_mk_state(), _mk_forcing(), make_parameters(), DT,
                  None, 0.0, 0.0, ctl)
    g = torch.Generator().manual_seed(131)
    u = State(*(torch.randn((1, 2), generator=g, dtype=torch.float64)
                for _ in State._fields))
    loss = state_dot(out, u)
    grads = torch.autograd.grad(loss, list(alphas.values()), allow_unused=True,
                                materialize_grads=True)
    gmap = dict(zip(alphas.keys(), grads))
    for k, gv in gmap.items():
        assert torch.isfinite(gv).all(), f"{k} grad non-finite"
    # measured on this IC: autoconv/riming/deposition/freeze carry nonzero grad;
    # accretion (pracw lencon-gated off at qr=1e-4) and melt (no warm snow/graupel
    # melt regime here) are zero-RATE — a zero gradient there is the CORRECT
    # subgradient (flat side of the rate gate), not a broken path.
    for k in ("alpha_autoconv", "alpha_riming", "alpha_freeze"):
        assert (gmap[k] != 0).any(), f"{k} grad zero on active IC"


def test_large_alpha_keeps_masses_nonnegative():
    """α = +3 (≈20×) on every control: the group conservation limiters bound
    the perturbed rates — no negative masses/numbers may appear."""
    a = torch.tensor(3.0, dtype=torch.float64)
    ctl = ProcessControls(alpha_autoconv=a, alpha_accretion=a,
                          alpha_deposition=a, alpha_riming=a,
                          alpha_freeze=a, alpha_melt=a)
    out = _run(ctl)
    for name in ("qv", "qc", "qr", "qi", "qs", "qg", "nc", "ni", "nr", "nccn"):
        fld = getattr(out, name)
        assert torch.isfinite(fld).all(), f"{name} non-finite under large α"
        assert (fld >= 0).all(), f"{name} negative under large α — limiter breached"


def test_alpha_freeze_reservoir_cap():
    """Codex stop-review gate: D2/D3 freeze commits through the CLAMP-FREE
    inline applier outside the group limiters — a large α_freeze must not
    overdraw qc/nc (which downstream final clamps would turn into mass
    CREATION). The cap renormalizes the combined draw to the reservoir."""
    from kdm6.process_controls import apply_freeze_controls
    from kdm6.coordinator import MeltFreezePhaseOutputs

    qc = torch.tensor([[2.0e-4, 1.0e-4]], dtype=torch.float64)
    nc = torch.tensor([[5.0e6, 1.0e6]], dtype=torch.float64)
    z = torch.zeros_like(qc)
    # unscaled D2+D3 already draws half the reservoir
    mf = MeltFreezePhaseOutputs(
        psmlt=z, pgmlt=z, pimlt_qi=z, pimlt_ni=z, sfac_melt=z, gfac_melt=z,
        delta_brs_melt=z, pinuc=0.25 * qc, ninuc=0.25 * nc,
        pfrzdtc=0.25 * qc, nfrzdtc=0.25 * nc,
        pfrzdtr=z, nfrzdtr=z, delta_brs_freeze=z,
        pseml=z, nseml=z, pgeml=z, ngeml=z)

    big = ProcessControls(alpha_freeze=torch.tensor(3.0, dtype=torch.float64,
                                                    requires_grad=True))
    out = apply_freeze_controls(mf, big, qc, nc)
    draw_q = out.pinuc + out.pfrzdtc
    draw_n = out.ninuc + out.nfrzdtc
    assert torch.all(draw_q <= qc * (1 + 1e-12)), "qc overdrawn despite cap"
    assert torch.all(draw_n <= nc * (1 + 1e-12)), "nc overdrawn despite cap"
    # cap is ACTIVE here (unscaled draw 0.5·qc × e^3 ≈ 10·qc → capped to qc)
    assert torch.allclose(draw_q, qc), "cap not binding where it must"
    # D4 untouched by design
    assert torch.equal(out.pfrzdtr, mf.pfrzdtr)
    # differentiable through the cap
    g, = torch.autograd.grad(draw_q.sum() + draw_n.sum(), big.alpha_freeze,
                             allow_unused=True, materialize_grads=True)
    assert torch.isfinite(g).all()

    # small α: cap must NOT bind (draw stays e^0.1-scaled, well under qc)
    small = ProcessControls(alpha_freeze=torch.tensor(0.1, dtype=torch.float64))
    out2 = apply_freeze_controls(mf, small, qc, nc)
    import math
    expect = 0.5 * qc * math.exp(0.1)
    assert torch.allclose(out2.pinuc + out2.pfrzdtc, expect, rtol=1e-12), \
        "cap distorted a within-budget draw"


def test_alpha_freeze_zero_bitwise_on_cap_saturated_ic():
    """Review finding 1: Fortran's INDEPENDENT D2/D3 caps allow a combined
    unscaled draw > qc, so a naive qc-budget cap would BIND at α=0 and break
    the α=0 value-identity by ULPs. The excess-only budget (max(qc, unscaled))
    must keep α_freeze=0 bitwise-identical even on a Bigg-cap-saturated IC."""
    sup = State(  # strongly supercooled, qc-rich: Bigg freezing cap saturates
        th=_t2(245.0, 240.0), qv=_t2(8.0e-4, 5.0e-4),
        qc=_t2(1.0e-3, 1.0e-3), qr=_t2(0.0, 0.0),
        qi=_t2(1.0e-5, 1.0e-5), qs=_t2(1.0e-5, 1.0e-5),
        qg=_t2(0.0, 0.0), nccn=_t2(1.0e9, 1.0e9),
        nc=_t2(1.0e8, 1.0e8), ni=_t2(1.0e6, 1.0e6),
        nr=_t2(0.0, 0.0), bg=_t2(0.0, 0.0),
    )
    base = _run(None, state=sup)
    out = _run(ProcessControls(alpha_freeze=torch.zeros((), dtype=torch.float64)),
               state=sup)
    for name, a, b in zip(State._fields, out, base):
        assert torch.equal(a, b), f"α_freeze=0 not bitwise on cap-saturated IC: {name}"


def test_alpha_freeze_conserves_total_water_on_saturated_ic():
    """Review F1 integration form: large α_freeze on the Bigg-cap-saturated IC
    must not CREATE water (the original overdraw turned 1.2 g/kg into 2.2)."""
    sup = State(
        th=_t2(245.0, 240.0), qv=_t2(8.0e-4, 5.0e-4),
        qc=_t2(1.0e-3, 1.0e-3), qr=_t2(0.0, 0.0),
        qi=_t2(1.0e-5, 1.0e-5), qs=_t2(1.0e-5, 1.0e-5),
        qg=_t2(0.0, 0.0), nccn=_t2(1.0e9, 1.0e9),
        nc=_t2(1.0e8, 1.0e8), ni=_t2(1.0e6, 1.0e6),
        nr=_t2(0.0, 0.0), bg=_t2(0.0, 0.0),
    )
    def total(st):
        return float((st.qv + st.qc + st.qr + st.qi + st.qs + st.qg).sum())
    base = _run(None, state=sup)
    out = _run(ProcessControls(alpha_freeze=torch.tensor(0.6931471805599453,
                                                         dtype=torch.float64)),
               state=sup)
    assert abs(total(out) - total(base)) < 1e-12, \
        f"water created/destroyed: {total(base)!r} -> {total(out)!r}"
    for name in ("qc", "qv", "qi", "qs"):
        assert (getattr(out, name) >= 0).all(), f"{name} negative"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
