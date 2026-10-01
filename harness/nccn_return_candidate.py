"""Small float64 experiment for returning volume-based number updates.

The production code is intentionally untouched. ``applied`` is the applied
volume concentration amount, positive for removal and negative for addition.
"""

import json
from pathlib import Path

import numpy as np
import torch


def direct_return(n_in: torch.Tensor, applied: torch.Tensor,
                  rho: torch.Tensor) -> torch.Tensor:
    """Convert the updated volume number directly back to mixing ratio."""
    n_in_volume = n_in * rho
    n_out_volume = n_in_volume - applied
    return n_out_volume / rho


def delta_return(n_in: torch.Tensor, applied: torch.Tensor,
                 rho: torch.Tensor) -> torch.Tensor:
    """Return the applied volume increment around the incoming number state."""
    n_in_volume = n_in * rho
    n_out_volume = n_in_volume - applied
    return n_in + (n_out_volume - n_in_volume) / rho


def delta_return_with_direct_fallback(
    n_in: torch.Tensor, applied: torch.Tensor, rho: torch.Tensor
) -> torch.Tensor:
    """Experimental large-change fallback; not a production recommendation."""
    n_in_volume = n_in * rho
    n_out_volume = n_in_volume - applied
    delta = n_out_volume - n_in_volume
    candidate = n_in + delta / rho
    direct = n_out_volume / rho
    return torch.where(torch.abs(delta) > 0.5 * torch.abs(n_in_volume), direct, candidate)


def _scalar(value: float, *, requires_grad: bool = False) -> torch.Tensor:
    return torch.tensor(value, dtype=torch.float64, requires_grad=requires_grad)


def baseline_level10(path: str | Path) -> dict:
    """Replay level-10 qv directional endpoints from extracted fixture scalars."""
    fixture = json.loads(Path(path).read_text())
    level = int(fixture["level"])
    qv = float(fixture["qv"])
    dqv = float(fixture["dqv"])
    n_in = float(fixture["n"])
    rho_air = float(fixture["rho_m"])

    # The host/runtime forms dry density from entry qv and uses that same
    # density for the conversion back to mixing ratio. For the directional
    # endpoints, rebuild both N_in and rho_dry at qv_entry ± h*dqv.
    h = float(fixture["h"])
    applied = _scalar(0.0)
    endpoint = {}
    for label, sign in (("plus", 1.0), ("minus", -1.0)):
        qv_endpoint = qv + sign * h * dqv
        rho_endpoint = _scalar(rho_air / (1.0 + qv_endpoint))
        n = _scalar(n_in)
        nin_volume = n * rho_endpoint
        nout_volume = nin_volume - applied
        direct = nout_volume / rho_endpoint
        delta = n + (nout_volume - nin_volume) / rho_endpoint
        expected = float.fromhex(fixture[f"{label}_hex"])
        endpoint[f"{label}_qv"] = qv_endpoint
        endpoint[f"{label}_rho_dry"] = float(rho_endpoint)
        endpoint[f"{label}_expected"] = expected
        endpoint[f"{label}_direct"] = float(direct)
        endpoint[f"{label}_delta"] = float(delta)
        endpoint[f"{label}_direct_hex"] = float(direct).hex()
        endpoint[f"{label}_delta_hex"] = float(delta).hex()
        endpoint[f"{label}_expected_hex"] = expected.hex()

    def ulps(a: float, b: float) -> int:
        # Inputs are positive finite values here, so their IEEE bit patterns
        # have the same ordering as their numerical values.
        ai = np.asarray(np.float64(a)).view(np.uint64).item()
        bi = np.asarray(np.float64(b)).view(np.uint64).item()
        return abs(int(ai) - int(bi))

    return {
        "level": level,
        "source_npz_sha256": fixture["source_npz_sha256"],
        "qv": qv,
        "qv_direction": dqv,
        **endpoint,
        "plus_direct_ulp_error": ulps(endpoint["plus_direct"], endpoint["plus_expected"]),
        "minus_direct_ulp_error": ulps(endpoint["minus_direct"], endpoint["minus_expected"]),
        "plus_delta_ulp_error": ulps(endpoint["plus_delta"], endpoint["plus_expected"]),
        "minus_delta_ulp_error": ulps(endpoint["minus_delta"], endpoint["minus_expected"]),
    }
