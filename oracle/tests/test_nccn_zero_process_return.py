"""Selected consumer boundary checks, not full atmospheric-state certification."""
import sys
from pathlib import Path
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from harness.nccn_return_candidate import exact_zero_return
from kdm6.coordinator import (CoordinatorState, CoordinatorForcing,
    apply_satadj_step_torch, default_coordinator_params, default_warm_phase_params)
from kdm6.thermo import compute_qs_water


def test_actual_cloud_zero_transfer_keeps_nc_tangent():
    z = lambda value: torch.full((1, 1), value, dtype=torch.float64)
    rho, number = z(.9), z(1e9)
    entry = number * rho
    state = CoordinatorState(qv=z(0), qc=z(0), qr=z(0), qs=z(0), qg=z(0),
        qi=z(0), nc=z(0), nr=z(0), ni=z(0), brs=z(0), t=z(290))
    forcing = CoordinatorForcing(p=z(9e4), den=z(1), delz=z(500), dend=rho)
    params = default_coordinator_params().thermo
    state = state._replace(qv=compute_qs_water(state.t, forcing.p, params=params))

    def volume_output(nc):
        _, nout = apply_satadj_step_torch(state._replace(nc=nc), forcing,
            z(2.5e6), z(1004), default_warm_phase_params().satadj, params,
            dtcld=6., nccn=entry)
        return nout

    def selected(nc):
        return exact_zero_return(number, entry, volume_output(nc), rho)

    def naive(nc):
        nout = volume_output(nc)
        return torch.where(nout == entry, number, nout / rho)

    assert torch.equal(volume_output(z(0)), entry)
    value, tangent = torch.func.jvp(selected, (z(0),), (z(1),))
    _, erased = torch.func.jvp(naive, (z(0),), (z(1),))
    assert torch.equal(value, number)
    torch.testing.assert_close(tangent, 1 / rho, rtol=0, atol=0)
    assert torch.equal(erased, z(0))
    # NC-only perturbation probes this consumer's selected clamp branch; it
    # does not certify an admissible full microphysics/DSD input direction.
    # Use one-sided differences to avoid crossing the NC>=0 clamp.
    step = 1e4
    difference = (selected(z(step)) - selected(z(0))) / step
    torch.testing.assert_close(tangent, difference, rtol=1e-10, atol=0)
    live = z(0).requires_grad_()
    adjoint = torch.autograd.grad(selected(live).sum(), live)[0]
    torch.testing.assert_close(adjoint, tangent, rtol=0, atol=0)


def test_zero_only_selector_still_has_adjacent_output_quantization():
    n = torch.tensor(16749932467.066803, dtype=torch.float64)
    rho = torch.tensor(1.2358801284298226, dtype=torch.float64)
    nin = n * rho
    values = [torch.tensor(np.nextafter(nin.item(), toward), dtype=torch.float64)
              for toward in (-np.inf, np.inf)]
    outputs = [exact_zero_return(n, nin, nout, rho).item() for nout in values]
    assert exact_zero_return(n, nin, nin, rho).item() == n.item()
    assert outputs[0] == n.item() - np.spacing(n.item())
    assert outputs[1] == n.item() + 2 * np.spacing(n.item())
