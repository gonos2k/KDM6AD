from __future__ import annotations

import math

import torch

from kdm6 import constants as c
from kdm6.slope import (
    compute_supcol,
    default_slope_params,
    n0sfac,
    slope_kdm6_torch,
    slope_rain_torch,
)


def _base_inputs(
    *,
    requires_grad: bool = False,
) -> dict[str, torch.Tensor]:
    dtype = torch.float64
    qr = torch.tensor([[2.0e-6, 3.5e-6]], dtype=dtype, requires_grad=requires_grad)
    qs = torch.tensor([[1.4e-6, 2.8e-6]], dtype=dtype, requires_grad=requires_grad)
    qg = torch.tensor([[1.8e-6, 2.2e-6]], dtype=dtype, requires_grad=requires_grad)
    qi = torch.tensor([[1.2e-7, 2.4e-7]], dtype=dtype, requires_grad=requires_grad)
    nr = torch.tensor([[1.2e6, 8.0e5]], dtype=dtype, requires_grad=requires_grad)
    ni = torch.tensor([[8.0e4, 1.1e5]], dtype=dtype, requires_grad=requires_grad)
    den = torch.tensor([[1.1, 0.95]], dtype=dtype)
    denfac = torch.tensor([[0.98, 1.04]], dtype=dtype)
    t = torch.tensor([[268.15, 258.15]], dtype=dtype)
    bvtg = torch.tensor([[0.5316, 0.5299]], dtype=dtype)
    pidn0g = torch.tensor([[2.5e5, 3.1e5]], dtype=dtype)
    pvtg = torch.tensor([[95.0, 110.0]], dtype=dtype)
    params = default_slope_params()
    rslopegbmax = torch.pow(
        torch.full_like(bvtg, params.rslopegmax),
        bvtg,
    )
    return {
        "qr": qr,
        "qs": qs,
        "qg": qg,
        "qi": qi,
        "nr": nr,
        "ni": ni,
        "den": den,
        "denfac": denfac,
        "t": t,
        "pidn0g": pidn0g,
        "pvtg": pvtg,
        "bvtg": bvtg,
        "rslopegbmax": rslopegbmax,
    }


def test_default_slope_params_finite():
    params = default_slope_params()
    for field in params._fields:
        value = getattr(params, field)
        assert math.isfinite(value), field
        assert value > 0.0, field


def test_n0sfac_clamp():
    t = torch.tensor([[500.0, 273.15, 153.15, 100.0]], dtype=torch.float64)
    fac = n0sfac(compute_supcol(t))
    max_fac = c.N0SMAX / c.N0S

    assert torch.all(fac >= 1.0)
    assert torch.all(fac <= max_fac)
    assert fac[0, 0].item() == 1.0
    assert fac[0, 1].item() == 1.0
    assert fac[0, 2].item() == max_fac
    assert fac[0, 3].item() == max_fac


def test_slope_kdm6_branches_to_max():
    params = default_slope_params()
    shape = (2, 3)
    dtype = torch.float64

    qr = torch.zeros(shape, dtype=dtype)
    qs = torch.zeros(shape, dtype=dtype)
    qg = torch.zeros(shape, dtype=dtype)
    qi = torch.zeros(shape, dtype=dtype)
    nr = torch.zeros(shape, dtype=dtype)
    ni = torch.zeros(shape, dtype=dtype)
    den = torch.ones(shape, dtype=dtype)
    denfac = torch.ones(shape, dtype=dtype)
    t = torch.full(shape, 263.15, dtype=dtype)
    bvtg = torch.full(shape, 0.5316, dtype=dtype)
    rslopegbmax = torch.pow(torch.full(shape, params.rslopegmax, dtype=dtype), bvtg)
    pidn0g = torch.zeros(shape, dtype=dtype)
    pvtg = torch.full(shape, 100.0, dtype=dtype)

    out = slope_kdm6_torch(
        qr=qr,
        qs=qs,
        qg=qg,
        qi=qi,
        nr=nr,
        ni=ni,
        den=den,
        denfac=denfac,
        t=t,
        pidn0g=pidn0g,
        pvtg=pvtg,
        bvtg=bvtg,
        rslopegbmax=rslopegbmax,
        params=params,
    )

    assert torch.allclose(out.rslope_r, torch.full_like(qr, params.rslopermax))
    assert torch.allclose(out.rslope_s, torch.full_like(qs, params.rslopesmax))
    assert torch.allclose(out.rslope_g, torch.full_like(qg, params.rslopegmax))
    assert torch.allclose(out.rslope_i, torch.full_like(qi, params.rslopeimax))
    assert torch.allclose(out.rslopeb_r, torch.full_like(qr, params.rsloperbmax))
    assert torch.allclose(out.rslopeb_s, torch.full_like(qs, params.rslopesbmax))
    assert torch.allclose(out.rslopeb_g, rslopegbmax)
    assert torch.allclose(out.rslopeb_i, torch.full_like(qi, params.rslopeibmax))
    assert torch.allclose(out.rslopemu_r, torch.full_like(qr, params.rslopermmax))
    assert torch.allclose(out.rslopemu_s, torch.full_like(qs, params.rslopesmmax))
    assert torch.allclose(out.rslopemu_g, torch.full_like(qg, params.rslopegmmax))
    assert torch.allclose(out.rslopemu_i, torch.full_like(qi, params.rslopeimmax))
    assert torch.allclose(out.rsloped_r, torch.full_like(qr, params.rsloperdmax))
    assert torch.allclose(out.rsloped_s, torch.full_like(qs, params.rslopesdmax))
    assert torch.allclose(out.rsloped_g, torch.full_like(qg, params.rslopegdmax))
    assert torch.allclose(out.rsloped_i, torch.full_like(qi, params.rslopeidmax))
    assert torch.allclose(out.rslope2_r, torch.full_like(qr, params.rsloper2max))
    assert torch.allclose(out.rslope2_s, torch.full_like(qs, params.rslopes2max))
    assert torch.allclose(out.rslope2_g, torch.full_like(qg, params.rslopeg2max))
    assert torch.allclose(out.rslope2_i, torch.full_like(qi, params.rslopei2max))
    assert torch.allclose(out.rslope3_r, torch.full_like(qr, params.rsloper3max))
    assert torch.allclose(out.rslope3_s, torch.full_like(qs, params.rslopes3max))
    assert torch.allclose(out.rslope3_g, torch.full_like(qg, params.rslopeg3max))
    assert torch.allclose(out.rslope3_i, torch.full_like(qi, params.rslopei3max))


def test_slope_kdm6_above_threshold_grad():
    params = default_slope_params()
    inputs = _base_inputs(requires_grad=True)

    out = slope_kdm6_torch(
        qr=inputs["qr"],
        qs=inputs["qs"],
        qg=inputs["qg"],
        qi=inputs["qi"],
        nr=inputs["nr"],
        ni=inputs["ni"],
        den=inputs["den"],
        denfac=inputs["denfac"],
        t=inputs["t"],
        pidn0g=inputs["pidn0g"],
        pvtg=inputs["pvtg"],
        bvtg=inputs["bvtg"],
        rslopegbmax=inputs["rslopegbmax"],
        params=params,
    )

    for tensor in out:
        assert torch.isfinite(tensor).all()

    loss = torch.zeros((), dtype=torch.float64)
    for tensor in out:
        loss = loss + tensor.sum()
    loss.backward()

    for name in ("qr", "qs", "qg", "qi", "nr", "ni"):
        grad = inputs[name].grad
        assert grad is not None, name
        assert torch.isfinite(grad).all(), name


def test_slope_rain_consistency():
    params = default_slope_params()
    inputs = _base_inputs(requires_grad=False)
    zeros = torch.zeros_like(inputs["qr"])

    multi = slope_kdm6_torch(
        qr=inputs["qr"],
        qs=zeros,
        qg=zeros,
        qi=zeros,
        nr=inputs["nr"],
        ni=zeros,
        den=inputs["den"],
        denfac=inputs["denfac"],
        t=inputs["t"],
        pidn0g=zeros,
        pvtg=torch.zeros_like(inputs["pvtg"]),
        bvtg=inputs["bvtg"],
        rslopegbmax=inputs["rslopegbmax"],
        params=params,
    )
    rain = slope_rain_torch(
        qr=inputs["qr"],
        nr=inputs["nr"],
        den=inputs["den"],
        denfac=inputs["denfac"],
        t=inputs["t"],
        params=params,
    )

    assert torch.allclose(rain.rslope_r, multi.rslope_r)
    assert torch.allclose(rain.rslopeb_r, multi.rslopeb_r)
    assert torch.allclose(rain.rslopemu_r, multi.rslopemu_r)
    assert torch.allclose(rain.rsloped_r, multi.rsloped_r)
    assert torch.allclose(rain.rslope2_r, multi.rslope2_r)
    assert torch.allclose(rain.rslope3_r, multi.rslope3_r)
    assert torch.allclose(rain.vt_r, multi.vt_r)
    assert torch.allclose(rain.vtn_r, multi.vtn_r)
